"""The bidding rules: who may bid on what, sealing a bid, withdrawing it, and the recorded opening that releases the bids.

A supplier sees the open tenders and its own bids only. Nobody sees what a bid says until an approver records the opening,
which cannot happen before the tender's closing date.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from . import sealed
from .models import Bid, BidderRegistration, BidOpening, TenderNotice


class BiddingError(Exception):
    """A refusal a person can act on; the message is shown as it is."""


def open_tenders():
    """Tenders a supplier may still bid on: published, and not past their closing date."""
    today = timezone.localdate()
    rows = TenderNotice.objects.filter(status='published')
    return [t for t in rows if t.closing_date is None or t.closing_date >= today]


def registration_of(vendor) -> BidderRegistration | None:
    return BidderRegistration.objects.filter(vendor=vendor).first()


def eligibility(vendor) -> tuple[bool, str]:
    """May this supplier bid at all? The reason is in words when it may not."""
    reg = registration_of(vendor)
    today = timezone.localdate()
    if reg is None:
        return False, 'You are not registered as a bidder yet. Ask for registration first.'
    if reg.status == 'pending':
        return False, 'Your bidder registration is waiting for the procurement office.'
    if reg.status != 'registered':
        return False, f'Your bidder registration is {reg.status}, so you cannot bid.'
    if reg.certificate_expiry and reg.certificate_expiry < today:
        return False, 'Your registration certificate has expired. Renew it before bidding.'
    if reg.tax_clearance_expiry and reg.tax_clearance_expiry < today:
        return False, 'Your tax clearance has expired. Renew it before bidding.'
    return True, ''


def request_registration(vendor, *, categories: list[str]) -> BidderRegistration:
    """A supplier asks to be registered as a bidder. The procurement office checks the evidence and decides."""
    if registration_of(vendor) is not None:
        raise BiddingError('You have already asked to be registered. The procurement office will decide it.')
    return BidderRegistration.objects.create(vendor=vendor, status='pending', categories=[c.strip() for c in categories if c.strip()])


def _money(value, label: str) -> Decimal:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise BiddingError(f'{label} must be a number.') from None
    if amount <= 0:
        raise BiddingError(f'{label} must be more than zero.')
    return amount


@transaction.atomic
def submit(vendor, tender: TenderNotice, *, price, completion_days, validity_days, technical_note: str = '') -> Bid:
    """Seal and record a supplier's bid. Replaces the supplier's earlier bid on the same tender while the tender is open."""
    if tender not in open_tenders():
        raise BiddingError('This tender is closed to bids.')
    ok, why = eligibility(vendor)
    if not ok:
        raise BiddingError(why)
    amount = _money(price, 'The price')
    days = int(_money(completion_days, 'The completion time'))
    validity = int(_money(validity_days, 'The validity of your offer'))
    reg = registration_of(vendor)
    existing = Bid.objects.filter(tender=tender, bidder=reg).first()
    if existing is not None and existing.status not in ('submitted', 'withdrawn'):
        raise BiddingError('Your bid has already been opened and can no longer be changed.')
    blob, digest = sealed.seal(tender.pk, reg.pk, {
        'price': str(amount), 'completion_days': days, 'validity_days': validity, 'technical_note': technical_note.strip(),
    })
    now = timezone.now()
    if existing is None:
        return Bid.objects.create(tender=tender, bidder=reg, status='submitted', submitted_at=now, encrypted_payload=blob, payload_hash=digest)
    existing.status, existing.submitted_at, existing.encrypted_payload, existing.payload_hash = 'submitted', now, blob, digest
    existing.save()
    return existing


@transaction.atomic
def withdraw(vendor, bid: Bid) -> Bid:
    if bid.bidder.vendor_id != vendor.pk:
        raise BiddingError('Not found.')
    if bid.status != 'submitted' or bid.tender not in open_tenders():
        raise BiddingError('This bid can no longer be withdrawn.')
    bid.status = 'withdrawn'
    bid.save(update_fields=['status', 'updated_at'])
    return bid


@transaction.atomic
def open_bids(tender: TenderNotice, user, *, attendance: list[str], minutes: str = '') -> BidOpening:
    """Record the opening: from now the bids can be read. Cannot happen while the tender is still open to bids."""
    if BidOpening.objects.filter(tender=tender).exists():
        raise BiddingError('The bids for this tender have already been opened.')
    if tender.status == 'draft' or tender.status == 'cancelled':
        raise BiddingError('This tender was never open for bids.')
    if tender.closing_date is None or tender.closing_date >= timezone.localdate():
        raise BiddingError('The tender is still open for bids. Bids can be opened only after its closing date.')
    names = [a.strip() for a in attendance if a.strip()]
    if not names:
        raise BiddingError('List who is present at the opening: bids are opened in front of witnesses.')
    opening = BidOpening.objects.create(tender=tender, opened_by=user, attendance=names, minutes=minutes.strip())
    now = timezone.now()
    for bid in Bid.objects.filter(tender=tender, status='submitted'):
        bid.status, bid.opened_at, bid.opened_by = 'opened', now, user
        bid.save(update_fields=['status', 'opened_at', 'opened_by', 'updated_at'])
    tender.status = 'closed'
    tender.save(update_fields=['status', 'updated_at'])
    return opening


def contents(bid: Bid) -> dict:
    """What an opened bid says. Refused while the tender's bids are still sealed."""
    if not BidOpening.objects.filter(tender_id=bid.tender_id).exists() or bid.status in ('submitted', 'withdrawn'):
        raise BiddingError('This bid is still sealed. It can be read only after the opening is recorded.')
    try:
        return sealed.unseal(bid.tender_id, bid.bidder_id, bid.encrypted_payload)
    except sealed.SealedError as exc:
        raise BiddingError(str(exc)) from exc
