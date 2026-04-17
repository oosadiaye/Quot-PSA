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
    return appropriation.commitments.filter(
        status__in=['ACTIVE', 'INVOICED'],
    ).aggregate(t=Sum('committed_amount'))['t'] or Decimal('0')


def _compute_expended(appropriation) -> Decimal:
    """Canonical expenditure figure — CLOSED commitments + direct AP + direct PV.

    Mirrors the fallback computation inside ``Appropriation.total_expended``
    but lives outside the model so callers can compute without touching
    the model property (which would recursively read the cache).
    """
    closed = appropriation.commitments.filter(status='CLOSED').aggregate(
        t=Sum('committed_amount'),
    )['t'] or Decimal('0')

    # Direct-invoice and direct-PV contributions are computed by the
    # model's live-path code. Re-running the full property with the
    # cache set to None gives us the authoritative live number without
    # duplicating the 60 lines of economic-parent-chain walking.
    prior_expended = appropriation.cached_total_expended
    prior_committed = appropriation.cached_total_committed
    try:
        appropriation.cached_total_expended = None
        appropriation.cached_total_committed = None
        live = appropriation.total_expended
    finally:
        appropriation.cached_total_expended = prior_expended
        appropriation.cached_total_committed = prior_committed
    return live if live else closed


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
