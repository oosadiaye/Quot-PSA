"""Virement service — the ONLY place that mutates Appropriation amounts.

Every caller that wants to move budget between appropriations must go
through ``apply_virement()``. Doing it inline in a view would risk:
  * skipping the available_balance guard (over-virement)
  * skipping the fiscal-year check (cross-year leak)
  * forgetting to reset cached totals (stale Variance report)
  * not creating the audit snapshot (no way to reconstruct history)

The service wraps everything in a single ``transaction.atomic()`` block
with ``select_for_update()`` on both appropriation rows so two
concurrent virements from the same source can't both read the same
available balance and over-draw it.
"""
from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.utils import timezone


class VirementError(Exception):
    """Raised when a virement fails its integrity checks."""
    pass


def _generate_reference_number() -> str:
    """VIR-YYYY-#### with a gap-free per-year sequence."""
    from budget.models import AppropriationVirement
    year = timezone.now().year
    prefix = f'VIR-{year}-'
    last = (
        AppropriationVirement.objects
        .filter(reference_number__startswith=prefix)
        .order_by('-reference_number')
        .first()
    )
    next_seq = 1
    if last:
        try:
            next_seq = int(last.reference_number.rsplit('-', 1)[-1]) + 1
        except (ValueError, IndexError):
            next_seq = 1
    return f'{prefix}{next_seq:04d}'


def create_virement(
    *,
    from_appropriation,
    to_appropriation,
    amount: Decimal,
    reason: str,
    user,
) -> 'AppropriationVirement':
    """Validate + persist a new virement in DRAFT status.

    Pre-flight checks (cheap, catch obvious errors before the user
    commits to the workflow):
      * source and target are distinct rows
      * both belong to the same fiscal_year
      * amount > 0
      * source.available_balance ≥ amount (advisory at create time;
        re-checked at apply time to guard against concurrent draws)
    """
    from budget.models import AppropriationVirement
    amount = Decimal(str(amount))
    if from_appropriation.pk == to_appropriation.pk:
        raise VirementError('Source and target must be different appropriations.')
    if amount <= 0:
        raise VirementError('Amount must be positive.')
    if from_appropriation.fiscal_year_id != to_appropriation.fiscal_year_id:
        raise VirementError(
            'Virement must be within the same fiscal year '
            '(cross-year transfers require a Supplementary).'
        )
    available = from_appropriation.available_balance
    if amount > available:
        raise VirementError(
            f'Source appropriation has only NGN {available:,.2f} available '
            f'(requested NGN {amount:,.2f}). Reduce the virement or commit '
            f'fewer funds on the source first.'
        )

    return AppropriationVirement.objects.create(
        reference_number=_generate_reference_number(),
        from_appropriation=from_appropriation,
        to_appropriation=to_appropriation,
        amount=amount,
        reason=reason,
        status='DRAFT',
        submitted_by=user,
    )


def submit_virement(virement, user) -> 'AppropriationVirement':
    """DRAFT → SUBMITTED. Author sign-off prior to approval."""
    if virement.status != 'DRAFT':
        raise VirementError(
            f'Cannot submit a virement in {virement.get_status_display()} status.'
        )
    virement.status = 'SUBMITTED'
    virement.submitted_at = timezone.now()
    virement.submitted_by = user
    virement.save(update_fields=['status', 'submitted_at', 'submitted_by'])
    return virement


@transaction.atomic
def approve_and_apply_virement(virement, user) -> 'AppropriationVirement':
    """SUBMITTED → APPROVED → APPLIED in one transaction.

    The "apply" leg is where the money actually moves:
      1. Re-check source.available_balance under a row lock.
      2. Snapshot pre-balances for audit.
      3. ``from.amount_approved -= amount``
      4. ``to.amount_approved   += amount``
      5. Reset denormalised totals on both rows so the JournalHeader
         post-save signal (or next resync) recomputes against the new
         ceiling.
      6. Stamp virement audit fields.
    """
    from budget.models import AppropriationVirement, Appropriation

    if virement.status not in ('DRAFT', 'SUBMITTED'):
        raise VirementError(
            f'Cannot approve a virement in {virement.get_status_display()} status.'
        )

    # Row-lock both appropriations in pk order to avoid deadlocks.
    ids = sorted([virement.from_appropriation_id, virement.to_appropriation_id])
    locked = {
        a.pk: a for a in Appropriation.objects.select_for_update().filter(pk__in=ids)
    }
    source = locked[virement.from_appropriation_id]
    target = locked[virement.to_appropriation_id]

    # Re-check available balance now that we hold the lock
    available = source.available_balance
    if virement.amount > available:
        raise VirementError(
            f'Source appropriation now has only NGN {available:,.2f} available '
            f'(virement requested NGN {virement.amount:,.2f}). Another '
            f'transaction may have drawn it down since the virement was '
            f'created.'
        )

    # Snapshot for audit
    virement.from_balance_before = source.amount_approved
    virement.to_balance_before = target.amount_approved

    # Move the money
    source.amount_approved = (source.amount_approved or Decimal('0')) - virement.amount
    target.amount_approved = (target.amount_approved or Decimal('0')) + virement.amount

    # Reset cached totals so next read recomputes against the new ceiling
    source.cached_total_committed = None
    source.cached_total_expended = None
    target.cached_total_committed = None
    target.cached_total_expended = None

    source.save(update_fields=[
        'amount_approved',
        'cached_total_committed', 'cached_total_expended',
    ])
    target.save(update_fields=[
        'amount_approved',
        'cached_total_committed', 'cached_total_expended',
    ])

    virement.from_balance_after = source.amount_approved
    virement.to_balance_after = target.amount_approved
    virement.status = 'APPLIED'
    virement.approved_by = user
    virement.approved_at = timezone.now()
    virement.applied_at = timezone.now()
    virement.save(update_fields=[
        'from_balance_before', 'from_balance_after',
        'to_balance_before', 'to_balance_after',
        'status', 'approved_by', 'approved_at', 'applied_at',
    ])

    # Rebuild denormalised totals so the Variance report is accurate
    from accounting.services.appropriation_totals import refresh_totals
    refresh_totals(source)
    refresh_totals(target)

    return virement


def reject_virement(virement, user, reason: str) -> 'AppropriationVirement':
    if virement.status in ('APPLIED', 'REJECTED', 'CANCELLED'):
        raise VirementError(
            f'Cannot reject a virement in {virement.get_status_display()} status.'
        )
    virement.status = 'REJECTED'
    virement.rejection_reason = reason
    virement.approved_by = user
    virement.approved_at = timezone.now()
    virement.save(update_fields=[
        'status', 'rejection_reason', 'approved_by', 'approved_at',
    ])
    return virement
