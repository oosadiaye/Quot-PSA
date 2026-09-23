"""Milestone-as-invoice (centralised AP) — approving a milestone posts the
accrual + a VendorInvoice, with retention held as a LIEN (never journalled).

DR Expense (per appropriation line) / CR Vendor-AP (gross). The invoice is
booked GROSS; ``retention_withheld`` freezes retention_rate% of it from
disbursement until released. See the AP-centralisation design doc.
"""
from __future__ import annotations

from decimal import Decimal

import pytest


def _milestone_with_lines(contract, expense_account, *, number=1, amount="20000000.00"):
    from contracts.models import MilestoneSchedule, MilestoneInvoiceLine, MilestoneStatus
    ms = MilestoneSchedule.objects.create(
        contract=contract, milestone_number=number,
        description="Foundation works",
        scheduled_value=Decimal(amount),
        percentage_weight=Decimal("20.000"),
        status=MilestoneStatus.COMPLETED,
    )
    MilestoneInvoiceLine.objects.create(
        milestone=ms, account=expense_account,
        description="Foundation works", amount=Decimal(amount),
    )
    return ms


@pytest.mark.django_db(transaction=True)
class TestMilestoneInvoice:

    def test_approve_posts_gross_invoice_with_retention_lien(
        self, activated_contract, _legacy_accounts, approver,
    ):
        from contracts.models import ContractBalance, MilestoneStatus
        from contracts.services.milestone_invoice_service import MilestoneInvoiceService

        ms = _milestone_with_lines(activated_contract, _legacy_accounts.expense, amount="20000000.00")

        invoice = MilestoneInvoiceService.approve_and_invoice(milestone=ms, actor=approver)

        # Booked GROSS; retention is a lien (5% of 20M = 1M), payable now 19M.
        assert invoice.total_amount == Decimal("20000000.00")
        assert invoice.retention_withheld == Decimal("1000000.00")
        assert invoice.payable_now == Decimal("19000000.00")
        assert invoice.status == "Posted"

        # Journal balanced DR Expense 20M == CR AP 20M — and NO retention line.
        j = invoice.journal_entry
        lines = list(j.lines.all())
        dr = sum((l.debit or 0) for l in lines)
        cr = sum((l.credit or 0) for l in lines)
        assert dr == cr == Decimal("20000000.00")
        assert not any(l.account_id == _legacy_accounts.retention.id for l in lines), \
            "retention must NOT be journalled — it is a lien"
        assert any(l.account_id == _legacy_accounts.expense.id and l.debit == Decimal("20000000.00")
                   for l in lines)
        assert any(l.account_id == _legacy_accounts.ap.id and l.credit == Decimal("20000000.00")
                   for l in lines)

        # ContractBalance: certified += gross, retention_held += retention.
        bal = ContractBalance.objects.get(pk=activated_contract.pk)
        assert bal.cumulative_gross_certified == Decimal("20000000.00")
        assert bal.retention_held == Decimal("1000000.00")

        ms.refresh_from_db()
        assert ms.status == MilestoneStatus.INVOICED

    def test_requires_appropriation_lines(self, activated_contract, _legacy_accounts, approver):
        from contracts.models import MilestoneSchedule, MilestoneStatus
        from accounting.services.base_posting import TransactionPostingError
        from contracts.services.milestone_invoice_service import MilestoneInvoiceService

        ms = MilestoneSchedule.objects.create(
            contract=activated_contract, milestone_number=3,
            description="No lines", scheduled_value=Decimal("1000.00"),
            percentage_weight=Decimal("1.000"), status=MilestoneStatus.COMPLETED,
        )
        with pytest.raises(TransactionPostingError):
            MilestoneInvoiceService.approve_and_invoice(milestone=ms, actor=approver)

    def test_reapprove_is_rejected(self, activated_contract, _legacy_accounts, approver):
        from accounting.services.base_posting import TransactionPostingError
        from contracts.services.milestone_invoice_service import MilestoneInvoiceService

        ms = _milestone_with_lines(activated_contract, _legacy_accounts.expense, number=4, amount="5000000.00")
        MilestoneInvoiceService.approve_and_invoice(milestone=ms, actor=approver)
        with pytest.raises(TransactionPostingError):
            MilestoneInvoiceService.approve_and_invoice(milestone=ms, actor=approver)

    def test_release_retention_unfreezes_lien_with_no_posting(
        self, activated_contract, _legacy_accounts, approver,
    ):
        from accounting.models import JournalHeader
        from contracts.models import ContractBalance
        from contracts.services.milestone_invoice_service import MilestoneInvoiceService

        ms = _milestone_with_lines(activated_contract, _legacy_accounts.expense, number=5, amount="20000000.00")
        invoice = MilestoneInvoiceService.approve_and_invoice(milestone=ms, actor=approver)
        assert invoice.retention_withheld == Decimal("1000000.00")
        assert invoice.payable_now == Decimal("19000000.00")
        journals_before = JournalHeader.objects.count()

        result = MilestoneInvoiceService.release_retention(contract=activated_contract, actor=approver)

        assert result["released"] == "1000000.00"
        invoice.refresh_from_db()
        assert invoice.retention_withheld == Decimal("0.00")
        assert invoice.payable_now == Decimal("20000000.00")   # now fully payable
        bal = ContractBalance.objects.get(pk=activated_contract.pk)
        assert bal.retention_released == Decimal("1000000.00")
        # Release posts NOTHING — retention is a lien, never journalled.
        assert JournalHeader.objects.count() == journals_before
