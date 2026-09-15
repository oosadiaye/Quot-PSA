"""
The over-allocation guard.

No database: the rule is arithmetic over three figures we already hold.

The case that matters most is the one the previous implementation got
wrong — an invoice part-paid and then refused its own outstanding
balance, because a posted allocation was counted both in ``paid_amount``
and again in the sum of allocations.
"""
from __future__ import annotations

from decimal import Decimal

from django.test import SimpleTestCase

from accounting.services.allocation_guard import (
    check_allocation,
    remaining_allocatable,
)

D = Decimal


class RemainingTests(SimpleTestCase):

    def test_nothing_paid_leaves_the_whole_invoice(self):
        assert remaining_allocatable(
            total_amount=D("1000000"), paid_amount=D("0"), pending_allocated=D("0"),
        ) == D("1000000")

    def test_posted_payments_reduce_the_remainder(self):
        assert remaining_allocatable(
            total_amount=D("1000000"), paid_amount=D("600000"), pending_allocated=D("0"),
        ) == D("400000")

    def test_draft_allocations_also_reduce_the_remainder(self):
        # Two clerks must not each allocate the full balance.
        assert remaining_allocatable(
            total_amount=D("1000000"), paid_amount=D("0"), pending_allocated=D("250000"),
        ) == D("750000")

    def test_an_over_allocated_invoice_has_zero_room_not_negative(self):
        # A negative remainder would be quoted back in the error message.
        assert remaining_allocatable(
            total_amount=D("1000000"), paid_amount=D("1200000"), pending_allocated=D("0"),
        ) == D("0")

    def test_money_stays_decimal(self):
        out = remaining_allocatable(
            total_amount=D("0.30"), paid_amount=D("0.10"), pending_allocated=D("0.00"),
        )
        assert out == D("0.20")
        assert isinstance(out, Decimal)


class CheckAllocationTests(SimpleTestCase):

    def test_the_exact_outstanding_balance_is_allowed(self):
        # The regression this guard was rewritten for. A 1,000,000
        # invoice with 600,000 already posted must accept an allocation
        # of exactly 400,000 — the old rule counted the posted 600,000
        # twice and refused it, making staged payment impossible.
        assert check_allocation(
            amount=D("400000"), total_amount=D("1000000"),
            paid_amount=D("600000"), pending_allocated=D("0"),
        ) is None

    def test_a_penny_over_the_balance_is_refused(self):
        error = check_allocation(
            amount=D("400000.01"), total_amount=D("1000000"),
            paid_amount=D("600000"), pending_allocated=D("0"),
        )
        assert error and "exceeds" in error

    def test_the_message_quotes_the_real_remaining_amount(self):
        # An error that names the wrong figure sends a clerk looking for
        # a problem that is not there.
        error = check_allocation(
            amount=D("999999"), total_amount=D("1000000"),
            paid_amount=D("600000"), pending_allocated=D("0"),
        )
        assert "400000" in error

    def test_a_second_draft_allocation_cannot_reuse_the_same_balance(self):
        # 400,000 left, 400,000 already claimed by another draft payment.
        error = check_allocation(
            amount=D("400000"), total_amount=D("1000000"),
            paid_amount=D("600000"), pending_allocated=D("400000"),
        )
        assert error is not None

    def test_a_fully_paid_invoice_accepts_nothing(self):
        error = check_allocation(
            amount=D("0.01"), total_amount=D("1000000"),
            paid_amount=D("1000000"), pending_allocated=D("0"),
        )
        assert error is not None

    def test_zero_and_negative_allocations_are_refused(self):
        for bad in (D("0"), D("-100")):
            error = check_allocation(
                amount=bad, total_amount=D("1000000"),
                paid_amount=D("0"), pending_allocated=D("0"),
            )
            assert error and "greater than zero" in error

    def test_paying_an_untouched_invoice_in_full_is_allowed(self):
        assert check_allocation(
            amount=D("1000000"), total_amount=D("1000000"),
            paid_amount=D("0"), pending_allocated=D("0"),
        ) is None

    def test_successive_instalments_each_succeed(self):
        # Walk a realistic three-tranche settlement. Each step passes
        # with the balance the previous one left, which the old rule
        # made impossible from the second tranche onwards.
        total, paid = D("1000000"), D("0")
        for tranche in (D("400000"), D("400000"), D("200000")):
            assert check_allocation(
                amount=tranche, total_amount=total,
                paid_amount=paid, pending_allocated=D("0"),
            ) is None, f"tranche {tranche} refused at paid={paid}"
            paid += tranche          # the payment posts
        assert paid == total
