"""Travel request, approval, advance, retirement, with the ledger as the judge."""
from decimal import Decimal

import pytest

from accounting.models import JournalLine
from staff_advances import lifecycle
from staff_advances.lifecycle import AdvanceError
from staff_advances.models import StaffAdvance, TravelRequest, TravelRetirement

D = Decimal


@pytest.fixture
def request_(employee):
    return TravelRequest.objects.create(employee=employee, destination="Asaba", estimated_cost=D("800.00"))


# The order of the steps (no ledger, so no flush cost).

@pytest.mark.django_db
def test_the_steps_run_in_order_and_each_refuses_the_wrong_state(request_):
    with pytest.raises(AdvanceError):
        lifecycle.approve_travel_request(request_)                       # not submitted yet
    lifecycle.submit_travel_request(request_)
    with pytest.raises(AdvanceError):
        lifecycle.submit_travel_request(request_)                        # already submitted
    lifecycle.approve_travel_request(request_)
    assert request_.status == "approved"
    with pytest.raises(AdvanceError):
        lifecycle.reject_travel_request(request_, "too late")            # only a submitted request can be rejected


@pytest.mark.django_db
def test_a_request_needs_a_destination_a_cost_and_sane_dates(employee):
    with pytest.raises(AdvanceError):
        lifecycle.submit_travel_request(TravelRequest.objects.create(employee=employee, destination="  ", estimated_cost=D("5")))
    with pytest.raises(AdvanceError):
        lifecycle.submit_travel_request(TravelRequest.objects.create(employee=employee, destination="X", estimated_cost=D("0")))
    with pytest.raises(AdvanceError):
        lifecycle.submit_travel_request(TravelRequest.objects.create(
            employee=employee, destination="X", estimated_cost=D("5"), start_date="2026-05-10", end_date="2026-05-01"))


@pytest.mark.django_db
def test_rejecting_needs_a_reason_and_records_it(request_):
    lifecycle.submit_travel_request(request_)
    with pytest.raises(AdvanceError):
        lifecycle.reject_travel_request(request_, "  ")
    lifecycle.reject_travel_request(request_, "No budget this quarter")
    request_.refresh_from_db()
    assert request_.status == "rejected" and "No budget this quarter" in request_.purpose


# Money (transactional: posts real journals).

@pytest.mark.django_db(transaction=True)
def test_advance_then_retire_spent_plus_returned_clears_the_advance_and_balances(request_, gl, actor, open_fiscal_period):
    lifecycle.submit_travel_request(request_)
    lifecycle.approve_travel_request(request_)

    travel = lifecycle.advance_travel(request_, actor=actor, bank_account=gl.bank)
    advance = StaffAdvance.objects.get(pk=travel.staff_advance_id)
    request_.refresh_from_db()
    assert request_.status == "advanced" and advance.amount == D("800.00") and advance.journal_id

    retirement = TravelRetirement.objects.create(travel_advance=travel, amount=D("650.00"), balance_returned=D("150.00"))
    lifecycle.retire_travel(retirement, actor=actor, expense_account=gl.expense, bank_account=gl.bank)

    advance.refresh_from_db()
    request_.refresh_from_db()
    assert (advance.recovered_amount, advance.status) == (D("800.00"), "CLEARED")
    assert request_.status == "retired"
    # The recon account nets to zero for this advance: 800 out, 650 expensed, 150 back in cash.
    lines = JournalLine.objects.filter(account=gl.recon, header__source_module__startswith="staff_advance")
    assert sum(l.debit for l in lines) == sum(l.credit for l in lines) == D("800.00")


@pytest.mark.django_db(transaction=True)
def test_a_retirement_that_does_not_account_for_the_whole_advance_is_refused_and_posts_nothing(request_, gl, actor, open_fiscal_period):
    lifecycle.submit_travel_request(request_)
    lifecycle.approve_travel_request(request_)
    travel = lifecycle.advance_travel(request_, actor=actor, bank_account=gl.bank)
    before = JournalLine.objects.count()
    short = TravelRetirement.objects.create(travel_advance=travel, amount=D("500.00"), balance_returned=D("100.00"))
    with pytest.raises(AdvanceError, match="whole advance"):
        lifecycle.retire_travel(short, actor=actor, expense_account=gl.expense, bank_account=gl.bank)
    assert JournalLine.objects.count() == before
    advance = StaffAdvance.objects.get(pk=travel.staff_advance_id)
    assert advance.recovered_amount == D("0")


@pytest.mark.django_db(transaction=True)
def test_an_advance_cannot_be_paid_twice_or_retired_twice(request_, gl, actor, open_fiscal_period):
    lifecycle.submit_travel_request(request_)
    lifecycle.approve_travel_request(request_)
    travel = lifecycle.advance_travel(request_, actor=actor, bank_account=gl.bank)
    with pytest.raises(AdvanceError):
        lifecycle.advance_travel(request_, actor=actor, bank_account=gl.bank)          # no longer 'approved'
    done = TravelRetirement.objects.create(travel_advance=travel, amount=D("800.00"), balance_returned=D("0"))
    lifecycle.retire_travel(done, actor=actor, expense_account=gl.expense, bank_account=gl.bank)
    again = TravelRetirement.objects.create(travel_advance=travel, amount=D("800.00"), balance_returned=D("0"))
    with pytest.raises(AdvanceError, match="already been retired"):
        lifecycle.retire_travel(again, actor=actor, expense_account=gl.expense, bank_account=gl.bank)
