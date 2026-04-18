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

    Matches on the 3 budget control pillars: Administrative (MDA),
    Economic (first line's account), and Fund. Uses the ``legacy_*``
    OneToOne bridges on NCoA segments to translate legacy FK ids to
    the NCoA segment ids used by Appropriation.

    - Idempotent: if a link already exists for this PO, update its
      ``committed_amount`` and ``status`` back to 'ACTIVE' instead of
      raising.
    - Safe: returns ``False`` (no-op) when prerequisites are missing
      (no MDA/Fund/lines, no matching Appropriation, no NCoA bridge).
    - Returns ``True`` if a link was created/refreshed.
    - Logs a specific warning identifying which pillar failed so
      operators can diagnose "why is my PO not showing in the
      Execution Report?".
    """
    from procurement.models import ProcurementBudgetLink
    from budget.models import Appropriation
    from accounting.models.ncoa import (
        AdministrativeSegment, EconomicSegment, FunctionalSegment,
        ProgrammeSegment, FundSegment, GeographicSegment, NCoACode,
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

    # When called from the save() hook, compute total from lines since
    # ``total_amount`` may still be stale until after super().save().
    if committed_amount is None:
        from decimal import Decimal as _D
        committed_amount = sum(
            (line.quantity * line.unit_price for line in po.lines.all()),
            _D('0'),
        ) + (po.tax_amount or _D('0'))

    admin_seg = AdministrativeSegment.objects.filter(legacy_mda=po.mda).first()
    econ_seg = EconomicSegment.objects.filter(legacy_account=first_account).first()
    fund_seg = FundSegment.objects.filter(legacy_fund=po.fund).first()
    missing = [
        name for name, seg in (
            ('administrative', admin_seg),
            ('economic', econ_seg),
            ('fund', fund_seg),
        ) if seg is None
    ]
    if missing:
        logger.warning(
            "Commitment skipped for PO %s: missing NCoA bridge(s) %s. "
            "Check that legacy_mda/legacy_account/legacy_fund FKs are "
            "populated on the NCoA segments.",
            po.po_number, missing,
        )
        return False

    # Exact match first, then walk up the EconomicSegment parent chain so
    # a PO coded to a leaf (e.g. 23100100 Acquisition of Land) can commit
    # against an Appropriation created at the parent level (e.g. 23000000
    # Capital Expenditure). This rollup behaviour matches how many IFMIS
    # systems work — budget is set at a summary level, transactions post
    # at the detail level.
    candidates = [econ_seg]
    cursor = econ_seg.parent
    while cursor is not None:
        candidates.append(cursor)
        cursor = cursor.parent

    # ── S1-10 — Atomic commitment under row lock ──────────────────────
    # Wrap the read-check-write sequence in a transaction with
    # ``select_for_update`` so two concurrent PO posts against the same
    # appropriation cannot both pass when only one fits. Without this the
    # 3-pillar ceiling is advisory only — classic TOCTOU bug.
    from django.db import transaction as _db_tx

    with _db_tx.atomic():
        appro = (
            Appropriation.objects
            .select_for_update()
            .filter(
                administrative=admin_seg,
                economic__in=candidates,
                fund=fund_seg,
                status='ACTIVE',
            )
            .first()
        )
        if not appro:
            # Rule-driven policy: when the GL account has a STRICT rule,
            # "no appropriation" is a HARD STOP — we raise so the PO
            # approval fails loudly. For WARNING/NONE rules we keep the
            # legacy silent-skip behaviour (the PO posts without a
            # commitment record).
            from accounting.services.budget_check_rules import check_policy
            policy = check_policy(
                account_code=first_account.code,
                appropriation=None,
                requested_amount=committed_amount,
                transaction_label=f'PO {po.po_number}',
            )
            if policy.blocked:
                from budget.services import BudgetExceededError
                raise BudgetExceededError(policy.reason)
            logger.warning(
                "Commitment skipped for PO %s: no ACTIVE Appropriation for "
                "MDA=%s / Econ=%s (or ancestors: %s) / Fund=%s. Approve an "
                "appropriation for this combination to back the PO. "
                "Policy level for this GL: %s.",
                po.po_number, admin_seg.code, econ_seg.code,
                [c.code for c in candidates[1:]] or 'none',
                fund_seg.code, policy.level,
            )
            return False

        # Ceiling check: already-committed + already-expended + this PO
        # must not exceed the approved appropriation.
        existing = (appro.total_committed or Decimal('0'))
        expended = (appro.total_expended or Decimal('0'))
        # ``update_or_create`` may replace our own link — exclude its prior
        # committed_amount from the ceiling so re-posting the same PO
        # doesn't double-count.
        prior_link = ProcurementBudgetLink.objects.filter(
            purchase_order=po, status__in=['ACTIVE', 'INVOICED'],
        ).first()
        prior_amt = prior_link.committed_amount if prior_link else Decimal('0')
        effective_committed = existing - prior_amt
        projected = effective_committed + expended + committed_amount
        if projected > appro.amount_approved:
            from budget.services import BudgetExceededError
            logger.warning(
                "Commitment REJECTED for PO %s: projected %s exceeds "
                "appropriation %s (approved %s).",
                po.po_number, projected, appro.code if hasattr(appro, 'code') else appro.pk,
                appro.amount_approved,
            )
            raise BudgetExceededError(
                f"PO {po.po_number} would push commitments to "
                f"NGN {projected:,.2f} against an appropriation of "
                f"NGN {appro.amount_approved:,.2f}. "
                f"Shortfall: NGN {(projected - appro.amount_approved):,.2f}."
            )

        # ── S1-11 — Warrant (AIE) ceiling check at commitment time ──
        # Appropriation is the annual legal ceiling; the warrant/AIE is
        # the quarterly cash release that must cover the commitment. An
        # MDA with an approved appropriation but no released warrant for
        # the current quarter may NOT commit. Previously this check only
        # ran at invoice time — we now enforce it at both commitment
        # (here) and payment (post_payment view).
        try:
            from accounting.budget_logic import check_warrant_availability
            allowed, warrant_msg, _info = check_warrant_availability(
                dimensions={'mda': po.mda, 'fund': po.fund},
                account=po.account if hasattr(po, 'account') else None,
                amount=committed_amount,
                exclude_po=po,
            )
            if not allowed:
                from budget.services import BudgetExceededError
                raise BudgetExceededError(
                    f"Warrant ceiling breached for PO {po.po_number}: {warrant_msg}"
                )
        except ImportError:
            # check_warrant_availability missing — skip gracefully rather
            # than blocking PO posting on a dev-only config.
            pass

        # Optional reporting segments
        func_seg = FunctionalSegment.objects.filter(legacy_function=po.function).first() if po.function else None
        prog_seg = ProgrammeSegment.objects.filter(legacy_program=po.program).first() if po.program else None
        geo_seg = GeographicSegment.objects.filter(legacy_geo=po.geo).first() if po.geo else None

        ncoa = NCoACode.get_or_create_code(
            admin_id=admin_seg.pk,
            economic_id=econ_seg.pk,
            functional_id=func_seg.pk if func_seg else None,
            programme_id=prog_seg.pk if prog_seg else None,
            fund_id=fund_seg.pk,
            geo_id=geo_seg.pk if geo_seg else None,
        )

        ProcurementBudgetLink.objects.update_or_create(
            purchase_order=po,
            defaults={
                'appropriation': appro,
                'committed_amount': committed_amount,
                'ncoa_code': ncoa,
                'status': 'ACTIVE',
            },
        )
        # P6-T2 — keep the denormalised Appropriation totals in sync.
        try:
            from accounting.services.appropriation_totals import refresh_totals
            refresh_totals(appro)
        except Exception:
            pass
    return True


def cancel_commitment_for_po(po) -> int:
    """Mark the ProcurementBudgetLink for this PO as CANCELLED.

    Called when a PO transitions to Rejected/Closed so the appropriation's
    committed balance is released. Returns the number of rows updated
    (0 if no active link, 1 when cancelled, never >1 because PO→Link is
    a OneToOne).
    """
    from procurement.models import ProcurementBudgetLink
    link = ProcurementBudgetLink.objects.filter(purchase_order=po).first()
    n = ProcurementBudgetLink.objects.filter(
        purchase_order=po, status__in=['ACTIVE', 'INVOICED'],
    ).update(status='CANCELLED')
    if n and link:
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

    Returns the number of rows updated (typically 1 from INVOICED, also
    accepts ACTIVE for the rare "no-GRN direct invoice" path). Idempotent
    — calling it again on a CLOSED link is a no-op.
    """
    from procurement.models import ProcurementBudgetLink
    link = ProcurementBudgetLink.objects.filter(purchase_order=po).first()
    n = ProcurementBudgetLink.objects.filter(
        purchase_order=po, status__in=['ACTIVE', 'INVOICED'],
    ).update(status='CLOSED')
    if n and link:
        try:
            from accounting.services.appropriation_totals import refresh_totals
            refresh_totals(link.appropriation)
        except Exception:
            pass
    return n
