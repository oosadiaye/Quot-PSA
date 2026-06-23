"""TSA Reconciliation completion service.

Extracted from ``accounting/views/tsa_reconciliation_views.py:TSAReconciliationViewSet.complete``
so the same logic can be called from both the DRF action (operator-initiated, MFA-gated) and
the ``document_approval_completed`` signal receiver (workflow-triggered).

Entry point:
    complete_reconciliation(reconciliation, user=None)

What it does:
    1. Sets ``TSAReconciliation.status = 'COMPLETED'``, stamps ``completed_at``
       and ``completed_by``.
    2. Flags all matched ``PaymentInstruction`` rows as ``is_reconciled=True``
       (H1 requirement).
    3. Flags all matched ``RevenueCollection`` rows as ``is_reconciled=True``
       (H1 requirement).
    4. Locks the linked ``TSABankStatement`` to ``status='COMPLETED'`` so no
       further line matches can be made.

MFA bypass note:
    The view's ``complete`` action enforces ``RequiresMFA`` *in addition to*
    ``CanReconcileTSA``. When the signal receiver calls this function the MFA
    gate is **not** re-checked here — the workflow approval itself is the
    authorisation gate (the approver authenticated with MFA at the point of
    workflow submission and approval). Do NOT add MFA enforcement to this
    function; keep the authorisation boundary at the approval call site. This
    is consistent with how other re-raise receivers (e.g. appropriation,
    virement) are wired — the workflow is the single gate, not a secondary
    per-service MFA check.

Failure: raises any DB or integrity error so the signal receiver can
    re-raise and roll back the approval (half-completed reconciliations
    would create duplicate-reconciliation risk on the next cycle).
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

if TYPE_CHECKING:
    from accounting.models.tsa_reconciliation import TSAReconciliation

logger = logging.getLogger(__name__)


def complete_reconciliation(
    reconciliation: "TSAReconciliation",
    user=None,
) -> "TSAReconciliation":
    """Finalise a TSA reconciliation session.

    Parameters
    ----------
    reconciliation:
        A ``TSAReconciliation`` instance that is NOT yet ``'COMPLETED'``.
        The caller is responsible for the idempotency pre-check (skip if
        ``status == 'COMPLETED'``); this function does NOT re-check.
    user:
        The acting user (stamped as ``completed_by``). May be ``None`` when
        called from the signal receiver.

    Returns
    -------
    TSAReconciliation
        The same instance with updated ``status``, ``completed_at``, and
        ``completed_by`` fields.

    Raises
    ------
    Exception
        Any DB or integrity error propagates to the caller so the surrounding
        atomic can roll back the partial completion.
    """
    from accounting.models import (
        TSABankStatement,
        TSABankStatementLine,
        PaymentInstruction,
        RevenueCollection,
        TSAReconciliation,
    )

    with transaction.atomic():
        # Lock the reconciliation row under select_for_update to prevent a
        # concurrent complete call (e.g. operator-button + workflow receiver
        # racing on the same record).
        locked = (
            TSAReconciliation.objects
            .select_for_update()
            .get(pk=reconciliation.pk)
        )

        # Idempotency double-check under lock — prevents the race where two
        # concurrent callers both pass the outer status check.
        if locked.status == 'COMPLETED':
            return locked

        locked.status = 'COMPLETED'
        locked.completed_at = timezone.now()
        locked.completed_by = user
        locked.save(update_fields=['status', 'completed_at', 'completed_by'])

        # H1 — flag matched book records as reconciled.
        if locked.statement_import_id:
            matched_lines = TSABankStatementLine.objects.filter(
                statement_id=locked.statement_import_id,
                match_status__in=['AUTO', 'MANUAL'],
            )
            matched_payment_ids = [
                line.matched_payment_id
                for line in matched_lines
                if line.matched_payment_id
            ]
            matched_revenue_ids = [
                line.matched_revenue_id
                for line in matched_lines
                if line.matched_revenue_id
            ]
            if matched_payment_ids:
                PaymentInstruction.objects.filter(
                    id__in=matched_payment_ids,
                ).update(
                    is_reconciled=True,
                    reconciliation=locked,
                )
            if matched_revenue_ids:
                RevenueCollection.objects.filter(
                    id__in=matched_revenue_ids,
                ).update(
                    is_reconciled=True,
                    reconciliation=locked,
                )

            # Lock the bank statement from further edits.
            TSABankStatement.objects.filter(
                pk=locked.statement_import_id,
            ).update(status='COMPLETED')

    return locked
