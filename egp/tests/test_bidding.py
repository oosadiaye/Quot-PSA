"""Sealed bids: encrypted at rest, bound to their tender and bidder, readable only after the recorded opening; who may bid, and
what a supplier can and cannot see."""
import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from core.models import TenantModule
from core.permissions import invalidate_module_cache
from egp import bidding, sealed
from egp.models import Bid, BidderRegistration, BidOpening, TenderNotice
from procurement.tests.test_supplier_portal import make_vendor, supplier_client, switch_portal  # noqa: F401
from procurement.tests.test_supplier_portal import tenant_schema  # noqa: F401  (autouse)
from procurement.tests.test_vendor_role_containment import _tenant, client_with_role

pytestmark = pytest.mark.django_db
PORTAL = '/api/v1/supplier-portal/tenders/'
BID = {'price': '1250000.00', 'completion_days': 30, 'validity_days': 90, 'technical_note': 'Own plant and crew'}


def egp_module(active=True):
    TenantModule.objects.update_or_create(module_name='egp', defaults={'is_active': active})
    invalidate_module_cache(_tenant().pk, 'egp')


@pytest.fixture(autouse=True)
def clean(db):
    BidOpening.objects.all().delete()
    Bid.objects.all().delete()
    BidderRegistration.objects.filter(vendor__code__startswith='SP-').delete()
    TenderNotice.objects.filter(reference__startswith='TST-').delete()
    egp_module(True)
    yield
    egp_module(False)


def tender(ref=None, *, status='published', closes_in=7):
    ref = ref or f'TST-{uuid.uuid4().hex[:8]}'
    return TenderNotice.objects.create(reference=ref, title=f'Tender {ref}', status=status,
                                       closing_date=timezone.localdate() + timedelta(days=closes_in))


def registered(code, **kw):
    v = make_vendor(code)
    BidderRegistration.objects.create(vendor=v, status=kw.pop('status', 'registered'), **kw)
    return v


def close_it(t):
    """The closing date passes."""
    TenderNotice.objects.filter(pk=t.pk).update(closing_date=timezone.localdate() - timedelta(days=1))
    t.refresh_from_db()


# ── sealing ───────────────────────────────────────────────────────────────────────────────────────────────────

def test_a_sealed_bid_does_not_contain_what_it_says():
    blob, digest = sealed.seal(1, 2, {'price': '1250000.00', 'technical_note': 'Own plant and crew'})
    assert b'1250000' not in blob and b'Own plant' not in blob and len(digest) == 64


def test_a_sealed_bid_reads_back_for_its_own_tender_and_bidder_only():
    blob, _ = sealed.seal(1, 2, {'price': '10'})
    assert sealed.unseal(1, 2, blob) == {'price': '10'}
    with pytest.raises(sealed.SealedError):
        sealed.unseal(9, 2, blob)                       # moved to another tender
    with pytest.raises(sealed.SealedError):
        sealed.unseal(1, 3, blob)                       # passed off as another bidder's


def test_an_altered_bid_is_refused_not_misread():
    blob, _ = sealed.seal(1, 2, {'price': '10'})
    tampered = blob[:-1] + bytes([blob[-1] ^ 1])
    with pytest.raises(sealed.SealedError, match='altered'):
        sealed.unseal(1, 2, tampered)


# ── who may bid ───────────────────────────────────────────────────────────────────────────────────────────────

def test_a_supplier_who_is_not_registered_cannot_bid():
    with pytest.raises(bidding.BiddingError, match='not registered as a bidder'):
        bidding.submit(make_vendor('SP-E1'), tender(), **BID)


def test_a_pending_or_suspended_registration_cannot_bid():
    t = tender()
    with pytest.raises(bidding.BiddingError, match='waiting for the procurement office'):
        bidding.submit(registered('SP-E2', status='pending'), t, **BID)
    with pytest.raises(bidding.BiddingError, match='suspended'):
        bidding.submit(registered('SP-E3', status='suspended'), t, **BID)


def test_an_expired_certificate_or_tax_clearance_cannot_bid():
    yesterday = timezone.localdate() - timedelta(days=1)
    with pytest.raises(bidding.BiddingError, match='certificate has expired'):
        bidding.submit(registered('SP-E4', certificate_expiry=yesterday), tender(), **BID)
    with pytest.raises(bidding.BiddingError, match='tax clearance has expired'):
        bidding.submit(registered('SP-E5', tax_clearance_expiry=yesterday), tender(), **BID)


def test_a_closed_or_unpublished_tender_takes_no_bids():
    v = registered('SP-E6')
    with pytest.raises(bidding.BiddingError, match='closed to bids'):
        bidding.submit(v, tender('TST-OLD', closes_in=-1), **BID)
    with pytest.raises(bidding.BiddingError, match='closed to bids'):
        bidding.submit(v, tender('TST-DRAFT', status='draft'), **BID)


def test_a_bid_needs_a_real_price_and_times():
    v, t = registered('SP-E7'), tender()
    for bad in ({'price': '0'}, {'price': 'abc'}, {'completion_days': 0}, {'validity_days': 0}):
        with pytest.raises(bidding.BiddingError):
            bidding.submit(v, t, **{**BID, **bad})


def test_bidding_again_replaces_the_bid_and_withdrawing_takes_it_back():
    v, t = registered('SP-E8'), tender()
    first = bidding.submit(v, t, **BID)
    again = bidding.submit(v, t, **{**BID, 'price': '1100000.00'})
    assert first.pk == again.pk and Bid.objects.filter(tender=t).count() == 1 and again.payload_hash != first.payload_hash
    assert bidding.withdraw(v, again).status == 'withdrawn'
    assert bidding.submit(v, t, **BID).status == 'submitted'              # and may bid afresh


def test_what_a_bid_says_is_stored_sealed():
    v, t = registered('SP-E9'), tender()
    bid = Bid.objects.get(pk=bidding.submit(v, t, **BID).pk)
    assert b'1250000' not in bytes(bid.encrypted_payload)


# ── the opening ───────────────────────────────────────────────────────────────────────────────────────────────

def test_bids_cannot_be_opened_while_the_tender_is_open():
    with pytest.raises(bidding.BiddingError, match='still open for bids'):
        bidding.open_bids(tender(), None, attendance=['A. Obi'])


def test_an_opening_needs_witnesses():
    with pytest.raises(bidding.BiddingError, match='present at the opening'):
        bidding.open_bids(tender(closes_in=-1), None, attendance=['  '])


def test_a_bid_stays_sealed_until_the_opening_and_reads_after_it():
    v, t = registered('SP-E10'), tender(closes_in=1)
    bid = bidding.submit(v, t, **BID)
    with pytest.raises(bidding.BiddingError, match='still sealed'):
        bidding.contents(bid)
    close_it(t)
    opening = bidding.open_bids(t, None, attendance=['A. Obi', 'B. Eze'], minutes='Opened in public')
    bid.refresh_from_db()
    assert bid.status == 'opened' and bid.opened_at and opening.attendance == ['A. Obi', 'B. Eze']
    assert bidding.contents(bid)['price'] == '1250000.00'
    t.refresh_from_db()
    assert t.status == 'closed'


def test_a_withdrawn_bid_is_never_opened_and_a_second_opening_is_refused():
    v, t = registered('SP-E11'), tender(closes_in=1)
    bid = bidding.submit(v, t, **BID)
    bidding.withdraw(v, bid)
    close_it(t)
    bidding.open_bids(t, None, attendance=['A. Obi'])
    bid.refresh_from_db()
    assert bid.status == 'withdrawn'
    with pytest.raises(bidding.BiddingError, match='already been opened'):
        bidding.open_bids(t, None, attendance=['A. Obi'])


# ── the supplier's API ────────────────────────────────────────────────────────────────────────────────────────

def test_a_supplier_sees_open_tenders_and_whether_it_may_bid():
    switch_portal()
    tender('TST-A'), tender('TST-B', closes_in=-2)
    body = supplier_client(make_vendor('SP-E12')).get(PORTAL).json()
    assert [t['reference'] for t in body['tenders']] == ['TST-A']
    assert body['eligible'] is False and 'not registered' in body['reason'] and body['registration_status'] == 'none'


def test_a_supplier_asks_to_be_registered_once():
    switch_portal()
    c = supplier_client(make_vendor('SP-E13'))
    r = c.post(PORTAL + 'registration/', {'categories': ['Works', 'Supplies']}, format='json')
    assert r.status_code == 201 and r.json()['status'] == 'pending'
    assert c.post(PORTAL + 'registration/', {'categories': []}, format='json').status_code == 400


def test_a_registered_supplier_bids_gets_a_receipt_and_sees_its_bid_marked_on_the_tender():
    switch_portal()
    v, t = registered('SP-E14'), tender()
    c = supplier_client(v)
    r = c.post(f'{PORTAL}{t.pk}/bid/', BID, format='json')
    assert r.status_code == 201 and r.json()['status'] == 'submitted' and len(r.json()['receipt']) == 64
    listed = c.get(PORTAL).json()
    assert listed['eligible'] is True and listed['tenders'][0]['my_bid']['status'] == 'submitted'
    assert 'price' not in str(c.get(PORTAL + 'bids/').json())             # the supplier's own list shows status, not contents


def test_an_ineligible_supplier_gets_the_reason_in_words():
    switch_portal()
    r = supplier_client(make_vendor('SP-E15')).post(f'{PORTAL}{tender().pk}/bid/', BID, format='json')
    assert r.status_code == 400 and 'not registered as a bidder' in r.json()['error']


def test_a_supplier_cannot_withdraw_another_suppliers_bid():
    switch_portal()
    t = tender()
    other_bid = bidding.submit(registered('SP-E16'), t, **BID)
    mine = supplier_client(registered('SP-E17'))
    assert mine.post(f'{PORTAL}bids/{other_bid.pk}/withdraw/', {}, format='json').status_code == 404
    assert Bid.objects.get(pk=other_bid.pk).status == 'submitted'


def test_with_the_module_off_the_supplier_is_told_so():
    switch_portal()
    c = supplier_client(make_vendor('SP-E18'))
    egp_module(False)
    assert c.get(PORTAL).status_code == 403


# ── the office's side ─────────────────────────────────────────────────────────────────────────────────────────

def test_the_office_sees_who_bid_but_not_what_until_the_opening():
    t = tender('TST-OFFICE', closes_in=1)
    bidding.submit(registered('SP-E19'), t, **BID)
    admin = client_with_role('admin')
    before = admin.get(f'/api/v1/egp/tenders/{t.pk}/bids/').json()
    assert before['opened'] is False and before['bids'][0]['sealed'] is True and before['bids'][0]['contents'] is None
    assert 'encrypted_payload' not in admin.get('/api/v1/egp/bids/').content.decode()      # the ciphertext is not served at all

    close_it(t)
    done = admin.post(f'/api/v1/egp/tenders/{t.pk}/open-bids/', {'attendance': ['A. Obi', 'B. Eze'], 'minutes': 'In public'}, format='json')
    assert done.status_code == 201 and done.json()['bids_opened'] == 1
    after = admin.get(f'/api/v1/egp/tenders/{t.pk}/bids/').json()
    assert after['opened'] is True and after['bids'][0]['contents']['price'] == '1250000.00'


def test_opening_too_early_comes_back_as_a_clear_message():
    t = tender('TST-EARLY')
    r = client_with_role('admin').post(f'/api/v1/egp/tenders/{t.pk}/open-bids/', {'attendance': ['A. Obi']}, format='json')
    assert r.status_code == 400 and 'still open for bids' in r.json()['error']


def test_a_supplier_cannot_open_bids_or_read_them():
    switch_portal()
    t = tender('TST-SUP', closes_in=-1)
    c = supplier_client(registered('SP-E20'))
    assert c.post(f'/api/v1/egp/tenders/{t.pk}/open-bids/', {'attendance': ['A']}, format='json').status_code == 403
    assert c.get(f'/api/v1/egp/tenders/{t.pk}/bids/').status_code == 403
    assert not BidOpening.objects.filter(tender=t).exists()
