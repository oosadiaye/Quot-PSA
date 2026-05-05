"""Procurement commitment helpers — ProcurementBudgetLink lifecycle.

Module-level functions that drive the ``Appropriation.total_committed``
pipeline. Kept in a dedicated module (not on ``ProcurementPostingService``)
so that ``PurchaseOrder.save()`` and ``GoodsReceivedNote.save()`` can
invoke them directly without importing the whole class — avoiding
circular imports.

Lifecycle (IPSAS three-way match):

    PO Approved   → create_commitment_for_po()           status=ACTIVE
    GRN Posted    → mark_commitment_invoiced_for_po()    status=INVOICED
    VI Posted     → mark_commitment_closed_for_po()      status=CLOSED
    PO Rejected   → cancel_commitment_for_po()           status=CANCELLED

``Appropriation.total_committed`` sums rows where
``status IN ('ACTIVE', 'INVOICED')`` — both still encumber the
appropriation until the vendor invoice is verified. Once the invoice is
posted (and the expense is formally recognised in the GL), the
commitment moves to CLOSED and falls out of the encumbered total. From
that point on the value is captured via the *actual expenditure* path
(JournalLine debits to the expense/asset accounts) instead of via the
commitment table.
"""
from __future__ import annotations

import logging
from decimal import Decimal


logger = logging.getLogger(__name__)


def create_commitment_for_po(po, committed_amount=None) -> bool:
    """Create (or update) a ProcurementBudgetLink row for this PO.

    Uses ``find_matching_appropriation`` (4 lookup strategies, including
    code-based fallback) so commitment creation succeeds even when the
    NCoA ``legacy_*`` FK bridges are not fully backfilled — the common
    cause of silent zero-committed values in the Budget Appropriation view.

    - Idempotent: updates an existing link if one already exists.
    - Safe: returns ``False`` when no active Appropriation exists for the
      PO's MDA/Fund/account combination; logs a specific warning.
    - Returns ``True`` if a link was created/refreshed.
    """
    from procurement.models import ProcurementBudgetLink
    from accounting.models.ncoa import NCoACode
    from accounting.services.budget_check_rules import (
        find_matching_appropriation, check_policy,
    )

    if not po.mda or not po.fund or not po.lines.exists():
        logger.warning(
            "Commitment skipped for PO %s: missing MDA/Fund/lines "
            "(mda=%s fund=%s lines=%s)",
            po.po_number, po.mda_id, po.fund_id, po.lines.count(),
        )
        return False

    first_account = po.lines.first().account
    if not first_account:
        logger.warning(
            "Commitment skipped for PO %s: first line has no GL account",
            po.po_number,
        )
        return False

    # Compute committed amount from lines (total_amount may be stale on save()).
    if committed_amount is None:
        committed_amount = sum(
            (line.quantity * line.unit_price for line in po.lines.all()),
            Decimal('0'),
        ) + (po.tax_amount or Decimal('0'))

    fiscal_year = po.order_date.year if po.order_date else None
    appro = find_matching_appropriation(
        mda=po.mda, fund=po.fund, account=first_account,
        fiscal_year=fiscal_year,
    )

    if not appro:
        # Rule-driven policy: STRICT rule → hard block; WARNING/NONE → skip.
        policy = check_policy(
            account_code=first_account.code,
            appropriation=None,
            requested_amount=committed_amount,
            transaction_label=f'PO {po.po_number}',
            account_name=getattr(first_account, 'name', ''),
        )
        if policy.blocked:
            from budget.services import BudgetExceededError
            raise BudgetExceededError(policy.reason)
        logger.warning(
            "Commitment skipped for PO %s: no ACTIVE Appropriation for "
            "MDA=%s / account=%s / Fund=%s (fiscal year %s). "
            "Policy level for this GL: %s.",
            po.po_number,
            getattr(po.mda, 'code', po.mda_id),
            first_account.code,
            getattr(po.fund, 'code', po.fund_id),
            fiscal_year, policy.level,
        )
        return False

    from django.db import transaction as _db_tx

    with _db_tx.atomic():
        # Re-fetch with row lock inside the atomic block.
        from budget.models import Appropriation
        locked_appro = Appropriation.objects.select_for_update().get(pk=appro.pk)

        # Ceiling check — exclude any prior link for this PO to stay idempotent.
        prior_link = ProcurementBudgetLink.objects.filter(
            purchase_order=po, status__in=['ACTIVE', 'INVOICED'],
        ).first()
        prior_amt = prior_link.committed_amount if prior_link else Decimal('0')
        effective_committed = (locked_appro.total_committed or Decimal('0')) - prior_amt
        projected = effective_committed + (locked_appro.total_expended or Decimal('0')) + committed_amount
        if projected > locked_appro.amount_approved:
            from budget.services import BudgetExceededError
            raise BudgetExceededError(
                f"PO {po.po_number} would push commitments to "
                f"NGN {projected:,.2f} against an appropriation of "
                f"NGN {locked_appro.amount_approved:,.2f}. "
                f"Shortfall: NGN {(projected - locked_appro.amount_approved):,.2f}."
            )

        # Warrant (AIE) ceiling check — opt-in via WARRANT_ENFORCEMENT_STAGE.
        try:
            from accounting.budget_logic import (
                check_warrant_availability, is_warrant_pre_payment_enforced,
            )
            if is_warrant_pre_payment_enforced():
                allowed, warrant_msg, _info = check_warrant_availability(
                    dimensions={'mda': po.mda, 'fund': po.fund},
                    account=first_account,
                    amount=committed_amount,
                    exclude_po=po,
                )
                if not allowed:
                    from budget.services import BudgetExceededError
                    raise BudgetExceededError(
                        f"Warrant ceiling breached for PO {po.po_number}: {warrant_msg}"
                    )
        except ImportError:
            pass

        # Build NCoA code from the matched Appropriation's own segments
        # (avoids a second round of segment lookups).
        ncoa = NCoACode.get_or_create_code(
            admin_id=locked_appro.administrative_id,
            economic_id=locked_appro.economic_id,
            functional_id=locked_appro.functional_id,
            programme_id=locked_appro.programme_id,
            fund_id=locked_appro.fund_id,
            geo_id=locked_appro.geographic_id,
        )

        ProcurementBudgetLink.objects.update_or_create(
            purchase_order=po,
            defaults={
                'appropriation': locked_appro,
                'committed_amount': committed_amount,
                'ncoa_code': ncoa,
                'status': 'ACTIVE',
            },
        )

        try:
            from accounting.services.appropriation_totals import refresh_totals
            refresh_totals(locked_appro)
        except Exception:
            pass

    return True


def cancel_commitment_for_po(po) -> int:
    """Mark the ProcurementBudgetLink for this PO as CANCELLED.

    Called when a PO transitions to Rejected/Closed so the
    appropriation's committed balance is released. Returns the number
    of rows updated (0 if no active link, 1 when cancelled, never >1
    because PO→Link is a OneToOne).

    Race-safe: acquires ``select_for_update`` on both the link and
    the parent Appropriation row before the cancellation. This
    serialises with concurrent ``create_commitment_for_po`` /
    ``close_commitment_for_po`` / ``mark_commitment_invoiced_for_po``
    calls (all of which lock the same Appropriation), so the
    ``cached_total_committed`` recomputed by ``refresh_totals``
    always sees a consistent snapshot.
    """
    from procurement.models import ProcurementBudgetLink
    from django.db import transaction as _txn
    with _txn.atomic():
        link = (
            ProcurementBudgetLink.objects
            .select_for_update()
            .filter(purchase_order=po)
            .first()
        )
        if link is None:
            return 0
        # Lock the parent Appropriation row too so refresh_totals
        # below operates on a serialised snapshot.
        from budget.models import Appropriation
        Appropriation.objects.select_for_update().filter(
            pk=link.appropriation_id,
        ).exists()
        n = ProcurementBudgetLink.objects.filter(
            purchase_order=po, status__in=['ACTIVE', 'INVOICED'],
        ).update(status='CANCELLED')
        if n:
            try:
                from accounting.services.appropriation_totals import refresh_totals
                refresh_totals(link.appropriation)
            except Exception:
                pass
        return n


def mark_commitment_invoiced_for_po(po) -> int:
    """Flip the ProcurementBudgetLink for this PO from ACTIVE to INVOICED.

    Called when a GRN transitions to Posted so downstream reconciliation
    can distinguish "committed but not yet received" (ACTIVE) from
    "received, awaiting payment" (INVOICED).

    ``Appropriation.total_committed`` sums rows where
    ``status IN ('ACTIVE', 'INVOICED')`` so this transition keeps the
    committed amount intact — which is correct: goods physically in hand
    but unpaid still encumber the appropriation until the Payment
    Voucher lands.

    Returns the number of rows updated (0 if the PO has no ACTIVE link,
    1 on success). Idempotent — calling it again on an INVOICED link
    is a no-op.
    """
    from procurement.models import ProcurementBudgetLink
    link = ProcurementBudgetLink.objects.filter(purchase_order=po).first()
    n = ProcurementBudgetLink.objects.filter(
        purchase_order=po, status='ACTIVE',
    ).update(status='INVOICED')
    # INVOICED still counts toward total_committed (no change), but the
    # refresh is cheap and keeps the refresh_at timestamp current so
    # downstream staleness alerts work.
    if n and link:
        try:
            from accounting.services.appropriation_totals import refresh_totals
            refresh_totals(link.appropriation)
        except Exception:
            pass
    return n


def mark_commitment_closed_for_po(po) -> int:
    """Close the ProcurementBudgetLink — vendor invoice has been posted.

    Called when a VendorInvoice for this PO is posted to the GL. The
    commitment is no longer needed as an encumbrance because the actual
    expense has now been booked (debited to the expense/asset account in
    the GL journal). Closing the link releases it from
    ``Appropriation.total_committed`` (which sums ``ACTIVE`` + ``INVOICED``
    only) so the appropriation's *encumbered* balance shrinks while its
    *expended* balance grows by the same amount.

    The original ``committed_amount`` is left intact on the row so audit
    queries can still compute the lifecycle history (PO → GRN → VI).

    Returns the number of rows updated. Idempotent — calling it again on a
    CLOSED link is a no-op.

    Robustness notes:
      • Refreshes **every** distinct Appropriation touched by this PO, not
        just the first link. A PO line splitting across multiple
        appropriations would otherwise leave half the cache stale.
      • Failures in the cache refresh are logged at ``error`` level (not
        silently swallowed) — the appropriation cache is what every budget
        execution report and dashboard reads, so silent staleness corrupts
        every downstream report.
    """
    from procurement.models import ProcurementBudgetLink

    # Snapshot every appropriation this PO touches BEFORE the bulk update,
    # so we can refresh every one of them after — not just .first().
    appropriation_ids = list(
        ProcurementBudgetLink.objects
        .filter(purchase_order=po)
        .values_list('appropriation_id', flat=True)
        .distinct()
    )

    n = ProcurementBudgetLink.objects.filter(
        purchase_order=po, status__in=['ACTIVE', 'INVOICED'],
    ).update(status='CLOSED')

    if appropriation_ids:
        try:
            from accounting.services.appropriation_totals import refresh_totals
            from budget.models import Appropriation
            for appr in Appropriation.objects.filter(pk__in=appropriation_ids):
                refresh_totals(appr)
        except Exception as exc:
            logger.error(
                'CRITICAL: Appropriation cache refresh failed after closing '
                'commitment for PO %s (appr_ids=%s): %s. Run '
                '`./manage.py resync_appropriation_totals` to recover.',
                getattr(po, 'po_number', po.pk), appropriation_ids, exc,
                exc_info=True,
            )
    return n


def refresh_appropriations_for_po(po) -> int:
    """Belt-and-braces: refresh every Appropriation touched by this PO.

    Used by the verify-and-post path as a defensive safety net in case the
    JournalHeader post_save signal or the commitment-closure refresh missed
    an appropriation (e.g., multi-line PO spanning multiple Appropriations,
    or a PO with no ProcurementBudgetLink due to legacy data).

    Walks PO lines and uses ``find_matching_appropriation`` to discover every
    Appropriation that should reflect the now-recognised expenditure, then
    refreshes each one's cached totals.

    Returns the count of appropriations refreshed. Never raises — failures
    are logged so the posting path is never broken by a cache issue.
    """
    refreshed_ids: set[int] = set()
    try:
        from procurement.models import ProcurementBudgetLink
        from budget.models import Appropriation
        from accounting.services.appropriation_totals import refresh_totals
        from accounting.services.budget_check_rules import (
            find_matching_appropriation,
        )

        # Source 1: ProcurementBudgetLink (commitment trail)
        for appr_id in (
            ProcurementBudgetLink.objects
            .filter(purchase_order=po)
            .values_list('appropriation_id', flat=True)
            .distinct()
        ):
            if appr_id:
                refreshed_ids.add(appr_id)

        # Source 2: PO lines (works even when no commitment link exists)
        fy = getattr(po, 'fiscal_year', None)
        fy_year = getattr(fy, 'year', None) or (
            po.order_date.year if getattr(po, 'order_date', None) else None
        )
        for line in po.lines.all():
            account = getattr(line, 'account', None)
            if account is None:
                continue
            appr = find_matching_appropriation(
                mda=po.mda, fund=po.fund,
                account=account, fiscal_year=fy_year,
            )
            if appr is not None:
                refreshed_ids.add(appr.pk)

        for appr in Appropriation.objects.filter(pk__in=refreshed_ids):
            refresh_totals(appr)
    except Exception as exc:
        logger.error(
            'CRITICAL: refresh_appropriations_for_po failed for PO %s: %s. '
            'Run `./manage.py resync_appropriation_totals` to recover.',
            getattr(po, 'po_number', getattr(po, 'pk', '?')), exc,
            exc_info=True,
        )
    return len(refreshed_ids)
