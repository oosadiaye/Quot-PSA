"""
Payment reconciliation queue (H2 follow-up — WS6).

When a payment is posted and the cascade to mark linked IPCs as paid
fails for some of them (e.g. SoD rejection, schema drift, transient
error), the cash journal has ALREADY committed and money has left the
TSA. The IPC stays in ``VOUCHER_RAISED`` and ``ContractBalance.
cumulative_gross_paid`` does NOT advance — the contract is in a state
where the books say "this much was paid" (GL cash leg) but the
sub-ledger says "this much is still owed" (IPC + ContractBalance).

The original Group B fix surfaced this via a ``_cascade_critical_failures``
field on the API response with ``207 Multi-Status``. A UI client that
ignores the warnings would still believe payment succeeded; the
divergence would only surface at contract closure (when the
``_assert_no_open_ipcs`` check fires) or during the next AR/AP aging
reconciliation pass (when the M3 ``gl_reconciliation_warning`` fires).

This module persists the failure so:

1. Operators can see the queue of pending reconciliations via a
   dedicated admin/API endpoint.
2. ``ContractClosureService`` can pre-flight-check the queue and
   refuse to close a contract whose linked IPCs have unresolved
   cascade failures.
3. A background task (out of scope for this commit) can retry the
   mark_paid step once the upstream issue is fixed.

The "fix it" path: an operator resolves the upstream issue (e.g.
adjusts SoD configuration, retries the IPC mark_paid through the
admin), then marks the row ``resolved=True`` with a resolution note.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class PaymentCascadeFailure(models.Model):
    """A pending reconciliation owed because a payment cascade step
    failed AFTER the cash journal was committed.

    See module docstring for the full design rationale.
    """

    payment = models.ForeignKey(
        'accounting.Payment',
        on_delete=models.PROTECT,
        related_name='cascade_failures',
        help_text='The payment whose cascade failed.',
    )
    ipc = models.ForeignKey(
        'contracts.InterimPaymentCertificate',
        on_delete=models.PROTECT,
        related_name='cascade_failures',
        null=True, blank=True,
        help_text='The IPC whose mark_paid step failed. Null for non-IPC '
                  'cascade failures (e.g. AR receipt allocation).',
    )

    # ── Context preserved for diagnosis ────────────────────────────────
    error_class = models.CharField(
        max_length=120, blank=True, default='',
        help_text='Exception class name, for triage filtering.',
    )
    error_message = models.TextField(
        help_text='Full exception message at the time of failure.',
    )
    error_context = models.JSONField(
        default=dict, blank=True,
        help_text='Extra structured context (caller user, source action, '
                  'request id, etc).',
    )

    # ── Lifecycle ──────────────────────────────────────────────────────
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    resolved = models.BooleanField(default=False, db_index=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='+',
        help_text='User who marked the failure resolved.',
    )
    resolution_note = models.TextField(
        blank=True, default='',
        help_text='What was done to resolve. Auditable.',
    )

    class Meta:
        app_label = 'accounting'
        verbose_name = 'Payment cascade failure'
        verbose_name_plural = 'Payment cascade failures'
        ordering = ['-created_at']
        indexes = [
            # Fast lookup for ContractClosureService pre-flight: "any
            # unresolved failure for this contract's IPCs?"
            models.Index(
                fields=['ipc', 'resolved'],
                name='pcf_ipc_resolved_idx',
            ),
        ]
        # V3 — resolving a cascade failure has real financial impact
        # (it asserts the sub-ledger / GL divergence has been hand-
        # reconciled). The auto-generated ``change_paymentcascadefailure``
        # is too broad — any user who can edit the row would qualify.
        # The dedicated ``resolve_paymentcascadefailure`` perm narrows
        # this to operators with explicit grant.
        permissions = (
            ('resolve_paymentcascadefailure', 'Can resolve payment cascade failures'),
        )

    def __str__(self) -> str:
        state = 'resolved' if self.resolved else 'pending'
        return (
            f'PaymentCascadeFailure(payment={self.payment_id}, '
            f'ipc={self.ipc_id}, {state})'
        )

    def mark_resolved(self, *, user, note: str = '') -> None:
        """Mark this failure resolved. Auditable.

        Use after the operator has corrected the upstream issue and
        either retried the cascade step manually or confirmed it is
        no longer needed. The row is NOT deleted — the audit trail
        persists.
        """
        self.resolved = True
        self.resolved_at = timezone.now()
        self.resolved_by = user
        if note:
            self.resolution_note = note
        self.save(update_fields=[
            'resolved', 'resolved_at', 'resolved_by', 'resolution_note',
        ])
