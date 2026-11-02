"""From opened bids to an award: assess each bid, rank the responsive ones, award one, and raise the draft purchase order.

The award does not approve spending. It creates a *draft* purchase order for the winning supplier, which then goes through the
usual order approval, where the procurement thresholds and the certificate of no objection are applied as for any order.
"""
from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from . import bidding
from .models import Bid, BidOpening, BidScore, EvaluationCriterion, TenderAward, TenderNotice

ASSESSMENTS = ('responsive', 'non_responsive', 'disqualified')


class AwardingError(Exception):
    """A refusal a person can act on; the message is shown as it is."""


def _require_opened(tender: TenderNotice) -> None:
    if not BidOpening.objects.filter(tender=tender).exists():
        raise AwardingError('The bids have not been opened yet. Record the opening before assessing or awarding.')


@transaction.atomic
def assess(bid: Bid, status: str, user, *, note: str = '') -> Bid:
    """Rule on an opened bid: responsive (it meets the requirements), not responsive, or disqualified."""
    if status not in ASSESSMENTS:
        raise AwardingError('A bid is assessed as responsive, non-responsive or disqualified.')
    _require_opened(bid.tender)
    if bid.status in ('submitted', 'withdrawn'):
        raise AwardingError('Only an opened bid can be assessed.')
    if TenderAward.objects.filter(tender=bid.tender).exists():
        raise AwardingError('This tender has already been awarded, so its bids can no longer be reassessed.')
    if status != 'responsive' and not note.strip():
        raise AwardingError('Give the reason a bid is ruled out, so the supplier and the auditors can see why.')
    bid.status, bid.assessment_note = status, note.strip()
    bid.save(update_fields=['status', 'assessment_note', 'updated_at'])
    return bid


def _score(bid: Bid) -> Decimal | None:
    """The weighted evaluation score out of 100, when the committee has scored this bid."""
    weights = {c.pk: Decimal(c.weight) for c in EvaluationCriterion.objects.filter(committee__tender_id=bid.tender_id)}
    total = sum(weights.values(), Decimal('0'))
    scores = list(BidScore.objects.filter(bid=bid, criterion_id__in=weights))
    if not weights or not scores or total <= 0:
        return None
    return (sum((Decimal(s.score) * weights[s.criterion_id] for s in scores), Decimal('0')) / total).quantize(Decimal('0.01'))


def ranking(tender: TenderNotice) -> list[dict]:
    """The opened bids with price and score, the lowest price first. Withdrawn and unopened bids do not appear."""
    _require_opened(tender)
    rows = []
    for bid in Bid.objects.filter(tender=tender).exclude(status__in=('submitted', 'withdrawn')).select_related('bidder__vendor'):
        body = bidding.contents(bid)
        rows.append({'bid': bid.pk, 'bidder': bid.bidder.vendor.name, 'status': bid.status, 'note': bid.assessment_note,
                     'price': body['price'], 'completion_days': body['completion_days'], 'score': _score(bid)})
    return sorted(rows, key=lambda r: (r['status'] != 'responsive', Decimal(r['price'])))


@transaction.atomic
def award(tender: TenderNotice, bid: Bid, user, *, mda, fund, function, program, geo, account) -> TenderAward:
    """Award the tender to a responsive bid and raise a draft purchase order for the supplier at its bid price."""
    from procurement.models import PurchaseOrder, PurchaseOrderLine

    _require_opened(tender)
    if bid.tender_id != tender.pk:
        raise AwardingError('That bid is not on this tender.')
    if bid.status != 'responsive':
        raise AwardingError('Only a bid that has been assessed as responsive can be awarded.')
    if TenderAward.objects.filter(tender=tender).exists():
        raise AwardingError('This tender has already been awarded.')
    amount = Decimal(bidding.contents(bid)['price'])
    try:
        po = PurchaseOrder.objects.create(
            mda=mda, vendor=bid.bidder.vendor, order_date=timezone.localdate(), fund=fund, function=function, program=program, geo=geo,
            status='Draft', notes=f'Awarded from tender {tender.reference}: {tender.title}',
        )
        PurchaseOrderLine.objects.create(po=po, item_description=tender.title[:255], quantity=Decimal('1'), unit_price=amount, account=account)
    except ValidationError as exc:
        raise AwardingError(' '.join(exc.messages)) from exc
    return TenderAward.objects.create(tender=tender, winning_bid=bid, status='approved', award_amount=amount, purchase_order=po,
                                      awarded_at=timezone.now(), awarded_by=user)
