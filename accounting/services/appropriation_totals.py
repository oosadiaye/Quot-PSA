"""P6-T2 — maintenance layer for Appropriation denormalised totals.

The ``Appropriation.cached_total_committed`` and
``Appropriation.cached_total_expended`` columns replace repeated
aggregate queries on Appropriation card loads. This module owns the
write-side: every place that creates, closes, or cancels a commitment —
or posts a direct (no-PO) vendor invoice — must call
``refresh_totals(appropriation)``.

Wiring points (call sites, not signals, so the cache stays deterministic
and easy to audit):
  * ``procurement.services.commitments.create_commitment_for_po``
  * ``procurement.services.commitments.close_commitment``
  * ``procurement.services.commitments.cancel_commitment``
  * ``accounting.services.post_invoice`` (direct AP path)
  * ``accounting.services.pay_voucher``   (direct PV path)

A full rebuild is available via the ``resync_appropriation_totals``
management command and runs as part of the monthly close checklist.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone


def _compute_committed(appropriation) -> Decimal:
    """Mirror ``Appropriation.total_committed`` — OPEN PO commitments only.

    In standard public-sector accounting (Nigeria IFMIS / IPSAS) the
    appropriation execution stages are mutually exclusive on the same
    money: a given ₦100 is either Committed (reserved by a PO/contract
    pending invoice verification) OR Expended (recognised as actual
    spend). The same amount must NEVER appear in both columns,
    otherwise ``available_balance = approved - committed - expended``
    deducts it twice and AVAILABLE goes negative even when the
    appropriation is actually under-spent.

    Direct disbursements (manual JEs, AP invoices with no PO, PVs paid
    without a source document) skip the commitment stage by design —
    the act of posting IS the act of expending. They belong in
    ``_compute_expended`` only, NOT here. The model property
    ``Appropriation.total_committed`` already encodes this rule
    (queries ACTIVE+INVOICED PO commitments only, with no ``+ direct``
    addition); this cache-writer was inconsistent with the property
    and produced inflated COMMITTED values + negative AVAILABLE on
    every appropriation with direct activity.

    Keep this in sync with the property so the cache and live read
    agree on the meaning of "committed".
    """
    open_po = appropriation.commitments.filter(
        status__in=['ACTIVE', 'INVOICED'],
    ).aggregate(t=Sum('committed_amount'))['t'] or Decimal('0')
    return open_po


def _compute_expended(appropriation) -> Decimal:
    """Canonical expenditure — CLOSED PO commitments + direct disbursements.

    Mirrors ``Appropriation.total_expended`` without touching the cache
    property (which would read itself recursively).

    Direct disbursements (manual JEs, AP-no-PO invoices, direct PVs)
    are intentionally counted ONLY here — never in ``_compute_committed``
    above — because posting a direct expense recognises the spend
    immediately without an intermediate commitment stage. The PO
    flow goes Committed (ACTIVE/INVOICED) → Expended (CLOSED); the
    direct flow goes straight to Expended.
    """
    closed = appropriation.commitments.filter(status='CLOSED').aggregate(
        t=Sum('committed_amount'),
    )['t'] or Decimal('0')
    return closed + appropriation._compute_direct_disbursements()


@transaction.atomic
def refresh_totals(appropriation) -> None:
    """Recompute and persist cached totals for a single Appropriation.

    Uses ``SELECT ... FOR UPDATE`` on the Appropriation row to serialise
    concurrent commitments — two POs approved in the same second cannot
    both read stale totals and overwrite each other.
    """
    Appropriation = type(appropriation)
    locked = Appropriation.objects.select_for_update().get(pk=appropriation.pk)
    locked.cached_total_committed = _compute_committed(locked)
    locked.cached_total_expended = _compute_expended(locked)
    locked.cached_totals_refreshed_at = timezone.now()
    locked.save(update_fields=[
        'cached_total_committed',
        'cached_total_expended',
        'cached_totals_refreshed_at',
    ])


def refresh_many(appropriations: Iterable) -> int:
    """Refresh a batch. Returns the count processed."""
    count = 0
    for appr in appropriations:
        refresh_totals(appr)
        count += 1
    return count
