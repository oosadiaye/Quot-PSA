"""From opened bids to an award: assessing bids, ranking the responsive ones, awarding one, and the draft order the award raises."""
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from egp import awarding, bidding
from egp.models import Bid, BidderRegistration, BidOpening, BidScore, EvaluationCommittee, EvaluationCriterion, TenderAward, TenderNotice
from egp.tests.test_bidding import BID, clean, egp_module, registered, tender  # noqa: F401  (clean is autouse)
from procurement.models import PurchaseOrder
from procurement.tests.test_supplier_portal import make_vendor, supplier_client, switch_portal  # noqa: F401
from procurement.tests.test_supplier_portal import tenant_schema  # noqa: F401
from procurement.tests.test_vendor_role_containment import client_with_role

pytestmark = pytest.mark.django_db
D = Decimal


def dims():
    from accounting.models.gl import Account, Fund, Function, Geo, MDA, Program
    fund, _ = Fund.objects.get_or_create(code='AW1', defaults={'name': 'AW Fund'})
    fn, _ = Function.objects.get_or_create(code='AW1', defaults={'name': 'AW Func'})
    pr, _ = Program.objects.get_or_create(code='AW1', defaults={'name': 'AW Prog'})
    geo, _ = Geo.objects.get_or_create(code='AW1', defaults={'name': 'AW Geo'})
    acct, _ = Account.objects.get_or_create(code='22100994', defaults={'name': 'AW Expense', 'account_type': 'Expense'})
    mda, _ = MDA.objects.get_or_create(code='AW-MDA', defaults={'name': 'AW MDA', 'short_name': 'AWM'})
    return {'mda': mda, 'fund': fund, 'function': fn, 'program': pr, 'geo': geo, 'account': acct}


def opened_tender(prices):
    """A tender with one registered bidder per price, bids opened. Returns the tender and the bids."""
    t = tender(closes_in=1)
    bids = [bidding.submit(registered(f'SP-W{uuid.uuid4().hex[:6]}'), t, **{**BID, 'price': p}) for p in prices]
    TenderNotice.objects.filter(pk=t.pk).update(closing_date=timezone.localdate() - timedelta(days=1))
    t.refresh_from_db()
    bidding.open_bids(t, None, attendance=['A. Obi'])
    for b in bids:
        b.refresh_from_db()
    return t, bids


# ── assessing ─────────────────────────────────────────────────────────────────────────────────────────────────

def test_a_bid_cannot_be_assessed_before_the_opening():
    t = tender(closes_in=1)
    bid = bidding.submit(registered('SP-W1'), t, **BID)
    with pytest.raises(awarding.AwardingError, match='not been opened'):
        awarding.assess(bid, 'responsive', None)


def test_ruling_a_bid_out_needs_a_reason_but_accepting_one_does_not():
    _, (bid, other) = opened_tender(['1000', '2000'])
    with pytest.raises(awarding.AwardingError, match='Give the reason'):
        awarding.assess(bid, 'disqualified', None)
    assert awarding.assess(bid, 'disqualified', None, note='No tax clearance').assessment_note == 'No tax clearance'
    assert awarding.assess(other, 'responsive', None).status == 'responsive'


def test_only_the_three_rulings_exist_and_a_withdrawn_bid_cannot_be_ruled_on():
    t, (bid,) = opened_tender(['1000'])
    with pytest.raises(awarding.AwardingError, match='responsive, non-responsive or disqualified'):
        awarding.assess(bid, 'opened', None)
    Bid.objects.filter(pk=bid.pk).update(status='withdrawn')
    bid.refresh_from_db()
    with pytest.raises(awarding.AwardingError, match='opened bid'):
        awarding.assess(bid, 'responsive', None)


# ── ranking ───────────────────────────────────────────────────────────────────────────────────────────────────

def test_ranking_puts_responsive_bids_first_lowest_price_first():
    t, (high, low, out) = opened_tender(['3000000.00', '1000000.00', '500000.00'])
    awarding.assess(high, 'responsive', None)
    awarding.assess(low, 'responsive', None)
    awarding.assess(out, 'non_responsive', None, note='Missing technical proposal')
    rows = awarding.ranking(t)
    assert [(r['status'], r['price']) for r in rows] == [('responsive', '1000000.00'), ('responsive', '3000000.00'), ('non_responsive', '500000.00')]


def test_ranking_carries_the_committees_weighted_score():
    t, (bid,) = opened_tender(['1000'])
    committee = EvaluationCommittee.objects.create(tender=t, name='Panel')
    tech = EvaluationCriterion.objects.create(committee=committee, name='Technical', weight=D('70'))
    exp = EvaluationCriterion.objects.create(committee=committee, name='Experience', weight=D('30'))
    BidScore.objects.create(bid=bid, criterion=tech, score=D('80'))
    BidScore.objects.create(bid=bid, criterion=exp, score=D('60'))
    assert awarding.ranking(t)[0]['score'] == D('74.00')             # (80 x 70 + 60 x 30) / 100


def test_ranking_before_the_opening_is_refused():
    with pytest.raises(awarding.AwardingError, match='not been opened'):
        awarding.ranking(tender())


# ── awarding ──────────────────────────────────────────────────────────────────────────────────────────────────

def test_awarding_raises_a_draft_order_for_the_winner_at_its_bid_price():
    t, (bid,) = opened_tender(['1250000.00'])
    awarding.assess(bid, 'responsive', None)
    award = awarding.award(t, bid, None, **dims())
    po = PurchaseOrder.objects.get(pk=award.purchase_order_id)
    assert (award.award_amount, award.status) == (D('1250000.00'), 'approved')
    assert po.status == 'Draft' and po.vendor_id == bid.bidder.vendor_id and t.reference in po.notes
    line = po.lines.get()
    assert (line.quantity, line.unit_price) == (D('1.00'), D('1250000.00'))


def test_only_a_responsive_bid_can_be_awarded():
    t, (bid,) = opened_tender(['1000'])
    with pytest.raises(awarding.AwardingError, match='assessed as responsive'):
        awarding.award(t, bid, None, **dims())


def test_a_tender_is_awarded_once_and_its_bids_are_then_fixed():
    t, (a, b) = opened_tender(['1000', '2000'])
    awarding.assess(a, 'responsive', None)
    awarding.assess(b, 'responsive', None)
    awarding.award(t, a, None, **dims())
    with pytest.raises(awarding.AwardingError, match='already been awarded'):
        awarding.award(t, b, None, **dims())
    with pytest.raises(awarding.AwardingError, match='already been awarded'):
        awarding.assess(b, 'disqualified', None, note='Too late')


def test_a_bid_from_another_tender_cannot_win_this_one():
    t, (bid,) = opened_tender(['1000'])
    other, (foreign,) = opened_tender(['900'])
    awarding.assess(foreign, 'responsive', None)
    with pytest.raises(awarding.AwardingError, match='not on this tender'):
        awarding.award(t, foreign, None, **dims())
    assert not TenderAward.objects.filter(tender=t).exists() and other.pk != t.pk and bid.pk


def test_an_award_to_a_supplier_who_has_not_paid_registration_is_refused_cleanly():
    t, (bid,) = opened_tender(['1000'])
    awarding.assess(bid, 'responsive', None)
    from procurement.models import Vendor
    Vendor.objects.filter(pk=bid.bidder.vendor_id).update(is_active=False)
    with pytest.raises(awarding.AwardingError, match='inactive'):
        awarding.award(t, bid, None, **dims())
    assert not TenderAward.objects.filter(tender=t).exists() and not PurchaseOrder.objects.filter(notes__contains=t.reference).exists()


# ── the API ───────────────────────────────────────────────────────────────────────────────────────────────────

def award_body(bid):
    d = dims()
    return {'bid': bid.pk, 'mda': d['mda'].pk, 'fund': d['fund'].pk, 'function': d['function'].pk, 'program': d['program'].pk,
            'geo': d['geo'].pk, 'account_code': d['account'].code}


def test_an_officer_assesses_ranks_and_awards_through_the_api():
    t, (cheap, dear) = opened_tender(['1000000.00', '2000000.00'])
    admin = client_with_role('admin')
    assert admin.post(f'/api/v1/egp/bids/{cheap.pk}/assess/', {'status': 'responsive'}, format='json').status_code == 200
    assert admin.post(f'/api/v1/egp/bids/{dear.pk}/assess/', {'status': 'disqualified', 'note': 'No clearance'}, format='json').status_code == 200
    ranked = admin.get(f'/api/v1/egp/tenders/{t.pk}/ranking/').json()
    assert [(r['price'], r['status']) for r in ranked] == [('1000000.00', 'responsive'), ('2000000.00', 'disqualified')]
    r = admin.post(f'/api/v1/egp/tenders/{t.pk}/award/', award_body(cheap), format='json')
    assert r.status_code == 201 and r.json()['po_number'].startswith('PO-') and r.json()['amount'] == '1000000.00'


def test_the_award_names_what_is_missing():
    t, (bid,) = opened_tender(['1000'])
    awarding.assess(bid, 'responsive', None)
    admin = client_with_role('admin')
    for key, words in (('fund', 'fund'), ('mda', 'MDA'), ('account_code', 'expense account')):
        body = award_body(bid)
        body[key] = ''
        r = admin.post(f'/api/v1/egp/tenders/{t.pk}/award/', body, format='json')
        assert r.status_code == 400 and words in r.json()['error'], key


def test_the_account_may_be_given_by_id_as_the_screen_does():
    t, (bid,) = opened_tender(['1000'])
    awarding.assess(bid, 'responsive', None)
    body = award_body(bid)
    body['account'] = dims()['account'].pk
    del body['account_code']
    r = client_with_role('admin').post(f'/api/v1/egp/tenders/{t.pk}/award/', body, format='json')
    assert r.status_code == 201, r.json()


def test_a_supplier_cannot_award_or_assess():
    switch_portal()
    t, (bid,) = opened_tender(['1000'])
    c = supplier_client(registered('SP-W2'))
    assert c.post(f'/api/v1/egp/tenders/{t.pk}/award/', award_body(bid), format='json').status_code == 403
    assert c.post(f'/api/v1/egp/bids/{bid.pk}/assess/', {'status': 'responsive'}, format='json').status_code == 403


def test_bids_openings_and_awards_cannot_be_created_or_edited_by_hand():
    t, (bid,) = opened_tender(['1000'])
    admin = client_with_role('admin')
    assert admin.post('/api/v1/egp/bids/', {'tender': t.pk}, format='json').status_code == 405
    assert admin.patch(f'/api/v1/egp/bids/{bid.pk}/', {'status': 'responsive'}, format='json').status_code == 405
    assert admin.post('/api/v1/egp/bid-openings/', {'tender': t.pk}, format='json').status_code == 405
    assert admin.post('/api/v1/egp/awards/', {'tender': t.pk, 'winning_bid': bid.pk}, format='json').status_code == 405
