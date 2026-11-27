"""A posted revenue collection reduces what the taxpayer owes, once, oldest debt first.

Order of application: unsettled arrears (oldest first), then open demand notices (earliest due first). An unknown TIN or
an over-payment is recorded, never lost, and never drives a balance negative. Replaying the same receipt changes nothing.
"""
from datetime import date
from decimal import Decimal

import pytest

from accounting.models import Account, RevenueHead
from revenue_admin.models import ArrearsLedger, CollectionApplication, DemandNotice, Taxpayer, TaxAccount
from revenue_admin.services import apply_collection

pytestmark = pytest.mark.django_db

D = Decimal


def _head(code, name):
    econ, _ = Account.objects.get_or_create(
        code=f"1{code}", defaults={"name": f"{name} revenue", "account_type": "Revenue"},
    )
    head, _ = RevenueHead.objects.get_or_create(
        code=code, defaults={"name": name, "economic_segment": econ, "revenue_type": "OTHER"},
    )
    return head


@pytest.fixture
def head():
    return _head("RA0001", "Ground rent")


@pytest.fixture
def other_head():
    return _head("RA0002", "Business premises")


@pytest.fixture
def taxpayer():
    return Taxpayer.objects.create(tin="TIN-RA-1", full_name="Ada Obi")


def _arrears(taxpayer, head, amount, year):
    return ArrearsLedger.objects.create(
        taxpayer=taxpayer, revenue_head=head, fiscal_year=year, amount=D(amount), arrears_date=date(year, 12, 31),
    )


def _notice(taxpayer, number, due, paid="0", when=date(2026, 3, 1)):
    return DemandNotice.objects.create(
        taxpayer=taxpayer, notice_number=number, amount_due=D(due), amount_paid=D(paid), due_date=when,
    )


def test_pays_oldest_arrears_first_then_the_notice(taxpayer, head):
    old = _arrears(taxpayer, head, "300", 2024)
    newer = _arrears(taxpayer, head, "200", 2025)
    notice = _notice(taxpayer, "DN-1", "500")

    result = apply_collection(receipt_number="R-1", payer_tin="TIN-RA-1", revenue_head=head, amount=D("600"))

    old.refresh_from_db(); newer.refresh_from_db(); notice.refresh_from_db()
    assert (old.amount, old.is_settled) == (D("0"), True)
    assert (newer.amount, newer.is_settled) == (D("0"), True)
    assert (notice.amount_paid, notice.status) == (D("100"), "partial")
    assert result.applied == D("600") and result.unapplied == D("0")


def test_a_fully_paid_notice_is_marked_paid(taxpayer, head):
    notice = _notice(taxpayer, "DN-2", "250")
    apply_collection(receipt_number="R-2", payer_tin="TIN-RA-1", revenue_head=head, amount=D("250"))
    notice.refresh_from_db()
    assert (notice.amount_paid, notice.status) == (D("250"), "paid")


def test_replaying_the_same_receipt_changes_nothing(taxpayer, head):
    arrears = _arrears(taxpayer, head, "300", 2024)
    first = apply_collection(receipt_number="R-3", payer_tin="TIN-RA-1", revenue_head=head, amount=D("100"))
    second = apply_collection(receipt_number="R-3", payer_tin="TIN-RA-1", revenue_head=head, amount=D("100"))
    arrears.refresh_from_db()
    assert arrears.amount == D("200")                      # reduced once, not twice
    assert first.already_applied is False and second.already_applied is True
    assert CollectionApplication.objects.filter(collection_receipt="R-3").count() == 1


def test_an_overpayment_is_kept_as_unapplied_credit_and_balances_never_go_negative(taxpayer, head):
    arrears = _arrears(taxpayer, head, "100", 2024)
    result = apply_collection(receipt_number="R-4", payer_tin="TIN-RA-1", revenue_head=head, amount=D("160"))
    arrears.refresh_from_db()
    assert arrears.amount == D("0") and arrears.is_settled is True
    assert result.applied == D("100") and result.unapplied == D("60")
    credit = CollectionApplication.objects.get(collection_receipt="R-4", arrears__isnull=True, demand_notice__isnull=True)
    assert credit.amount == D("60")


def test_an_unknown_tin_is_recorded_and_changes_nothing(taxpayer, head):
    arrears = _arrears(taxpayer, head, "100", 2024)
    result = apply_collection(receipt_number="R-5", payer_tin="NO-SUCH-TIN", revenue_head=head, amount=D("100"))
    arrears.refresh_from_db()
    assert arrears.amount == D("100")
    assert result.applied == D("0") and result.unapplied == D("100")
    assert apply_collection(receipt_number="R-5", payer_tin="NO-SUCH-TIN", revenue_head=head, amount=D("100")).already_applied


def test_arrears_of_another_revenue_head_are_left_alone(taxpayer, head, other_head):
    other = _arrears(taxpayer, other_head, "100", 2024)
    apply_collection(receipt_number="R-6", payer_tin="TIN-RA-1", revenue_head=head, amount=D("100"))
    other.refresh_from_db()
    assert other.amount == D("100") and other.is_settled is False


def test_the_tin_match_ignores_case_and_surrounding_spaces(taxpayer, head):
    arrears = _arrears(taxpayer, head, "100", 2024)
    apply_collection(receipt_number="R-7", payer_tin="  tin-ra-1 ", revenue_head=head, amount=D("40"))
    arrears.refresh_from_db()
    assert arrears.amount == D("60")


def test_the_tax_account_balance_falls_by_what_was_applied(taxpayer, head):
    account = TaxAccount.objects.create(taxpayer=taxpayer, revenue_head=head, running_balance=D("500"))
    _arrears(taxpayer, head, "500", 2024)
    apply_collection(receipt_number="R-8", payer_tin="TIN-RA-1", revenue_head=head, amount=D("120"))
    account.refresh_from_db()
    assert account.running_balance == D("380")
