"""The revenue lifecycle: issue an assessment, run a billing cycle, age overdue notices, issue a clearance certificate."""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from accounting.models import Account, RevenueHead
from revenue_admin import lifecycle
from revenue_admin.lifecycle import ClearanceRefused, LifecycleError
from revenue_admin.models import (
    ArrearsLedger, Assessment, BillingRun, DemandNotice, TaxAccount, Taxpayer, TaxClearanceCertificate,
)

pytestmark = pytest.mark.django_db
D = Decimal
TODAY = date(2026, 6, 15)


@pytest.fixture
def head():
    econ, _ = Account.objects.get_or_create(
        code="1RL0001", defaults={"name": "Lifecycle revenue", "account_type": "Revenue"})
    h, _ = RevenueHead.objects.get_or_create(
        code="RL0001", defaults={"name": "Lifecycle head", "economic_segment": econ, "revenue_type": "OTHER"})
    return h


@pytest.fixture
def taxpayer():
    return Taxpayer.objects.create(tin="TIN-RL-1", full_name="Bola Ade")


def _assessment(taxpayer, head, amount="1000", year=2026, status="draft"):
    return Assessment.objects.create(
        taxpayer=taxpayer, revenue_head=head, fiscal_year=year, assessed_amount=D(amount), status=status)


# ── issue ────────────────────────────────────────────────────────────────────

def test_issuing_an_assessment_creates_one_demand_notice_and_raises_the_liability(taxpayer, head):
    a = _assessment(taxpayer, head, "1000")
    TaxAccount.objects.create(taxpayer=taxpayer, revenue_head=head, running_balance=D("200"))

    notice = lifecycle.issue_assessment(a, today=TODAY)

    a.refresh_from_db()
    assert a.status == "issued" and a.issued_at is not None
    assert (notice.amount_due, notice.status, notice.assessment_id) == (D("1000"), "issued", a.pk)
    assert notice.due_date == TODAY + timedelta(days=lifecycle.PAYMENT_TERM_DAYS)
    assert notice.notice_number.startswith("DN-")
    assert TaxAccount.objects.get(taxpayer=taxpayer, revenue_head=head).running_balance == D("1200")


def test_issuing_twice_does_not_make_a_second_notice(taxpayer, head):
    a = _assessment(taxpayer, head)
    first = lifecycle.issue_assessment(a, today=TODAY)
    again = lifecycle.issue_assessment(a, today=TODAY)
    assert first.pk == again.pk
    assert DemandNotice.objects.filter(assessment=a).count() == 1
    assert TaxAccount.objects.get(taxpayer=taxpayer, revenue_head=head).running_balance == D("1000")


def test_only_a_draft_with_an_amount_can_be_issued(taxpayer, head):
    with pytest.raises(LifecycleError):
        lifecycle.issue_assessment(_assessment(taxpayer, head, "0"), today=TODAY)
    with pytest.raises(LifecycleError):
        lifecycle.issue_assessment(_assessment(taxpayer, head, "50", status="objected"), today=TODAY)


# ── billing run ──────────────────────────────────────────────────────────────

def test_a_billing_run_issues_every_draft_assessment_of_its_head_and_year(taxpayer, head):
    other = Taxpayer.objects.create(tin="TIN-RL-2", full_name="Chidi Eze")
    _assessment(taxpayer, head, "400")
    _assessment(other, head, "600")
    _assessment(other, head, "999", year=2025)               # another year: not part of this run
    run = BillingRun.objects.create(revenue_head=head, fiscal_year=2026, cycle="Annual 2026")

    lifecycle.process_billing_run(run, today=TODAY)

    run.refresh_from_db()
    assert (run.status, run.notices_created, run.total_amount) == ("processed", 2, D("1000"))
    assert run.processed_at is not None
    assert DemandNotice.objects.filter(billing_run=run).count() == 2


def test_a_processed_billing_run_cannot_be_run_again(taxpayer, head):
    _assessment(taxpayer, head)
    run = BillingRun.objects.create(revenue_head=head, fiscal_year=2026)
    lifecycle.process_billing_run(run, today=TODAY)
    with pytest.raises(LifecycleError):
        lifecycle.process_billing_run(run, today=TODAY)


# ── ageing ───────────────────────────────────────────────────────────────────

def test_ageing_marks_past_due_unpaid_notices_overdue_and_counts_arrears_days(taxpayer, head):
    late = DemandNotice.objects.create(
        taxpayer=taxpayer, notice_number="DN-T-1", amount_due=D("100"), due_date=TODAY - timedelta(days=10))
    partly = DemandNotice.objects.create(
        taxpayer=taxpayer, notice_number="DN-T-2", amount_due=D("100"), amount_paid=D("40"), status="partial",
        due_date=TODAY - timedelta(days=1))
    paid = DemandNotice.objects.create(
        taxpayer=taxpayer, notice_number="DN-T-3", amount_due=D("100"), amount_paid=D("100"), status="paid",
        due_date=TODAY - timedelta(days=90))
    notdue = DemandNotice.objects.create(
        taxpayer=taxpayer, notice_number="DN-T-4", amount_due=D("100"), due_date=TODAY + timedelta(days=5))
    arrears = ArrearsLedger.objects.create(
        taxpayer=taxpayer, revenue_head=head, fiscal_year=2024, amount=D("70"), arrears_date=TODAY - timedelta(days=120))

    summary = lifecycle.update_ageing(as_of=TODAY)

    for n in (late, partly, paid, notdue, arrears):
        n.refresh_from_db()
    assert (late.status, partly.status, paid.status, notdue.status) == ("overdue", "overdue", "paid", "issued")
    assert arrears.ageing_days == 120
    assert summary.notices_marked_overdue == 2


# ── clearance certificate ────────────────────────────────────────────────────

def test_a_taxpayer_with_nothing_owing_is_cleared(taxpayer):
    cert = lifecycle.issue_clearance_certificate(taxpayer, fiscal_year=2026, today=TODAY)
    assert cert.status == "issued" and cert.certificate_number.startswith("TCC-")
    assert cert.expiry_date == date(2026, 12, 31)


def test_unsettled_arrears_or_an_unpaid_notice_refuse_clearance_and_say_why(taxpayer, head):
    ArrearsLedger.objects.create(taxpayer=taxpayer, revenue_head=head, fiscal_year=2024, amount=D("10"))
    DemandNotice.objects.create(taxpayer=taxpayer, notice_number="DN-T-9", amount_due=D("5"), due_date=TODAY - timedelta(days=3))
    with pytest.raises(ClearanceRefused) as refused:
        lifecycle.issue_clearance_certificate(taxpayer, fiscal_year=2026, today=TODAY)
    assert "arrears" in str(refused.value).lower() and "notice" in str(refused.value).lower()
    assert TaxClearanceCertificate.objects.count() == 0


def test_a_notice_not_yet_due_does_not_block_clearance(taxpayer):
    DemandNotice.objects.create(taxpayer=taxpayer, notice_number="DN-T-8", amount_due=D("5"), due_date=TODAY + timedelta(days=20))
    assert lifecycle.issue_clearance_certificate(taxpayer, fiscal_year=2026, today=TODAY).status == "issued"
