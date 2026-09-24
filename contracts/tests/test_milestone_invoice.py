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
        # AP is the vendor's *resolved* reconciliation account. When the vendor
        # has no category recon account the resolver falls back to the global
        # 'accounts_payable' recon, so assert against what the service actually
        # resolves rather than assuming the fixture's ap account.
        from accounting.services.procurement_posting import get_vendor_ap_account
        ap_acct, _ = get_vendor_ap_account(activated_contract.vendor)
        assert any(l.account_id == ap_acct.id and l.credit == Decimal("20000000.00")
                   for l in lines)

        # ContractBalance: certified += gross. retention_held is NOT touched by
        # the milestone — it stays the lump-sum reserve seeded at activation
        # (original_sum × retention_rate). The per-invoice lien is on
        # VendorInvoice.retention_withheld (asserted above).
        bal = ContractBalance.objects.get(pk=activated_contract.pk)
        assert bal.cumulative_gross_certified == Decimal("20000000.00")
        assert bal.retention_held == activated_contract.retention_reserve

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

    def test_sync_contract_paid_derives_from_invoice_paid_amount(
        self, activated_contract, _legacy_accounts, approver,
    ):
        from contracts.models import ContractBalance
        from contracts.services.milestone_invoice_service import MilestoneInvoiceService

        ms = _milestone_with_lines(activated_contract, _legacy_accounts.expense, number=6, amount="20000000.00")
        invoice = MilestoneInvoiceService.approve_and_invoice(milestone=ms, actor=approver)

        # Pay the payable-now (19M; 1M retention still frozen).
        invoice.paid_amount = Decimal("19000000.00")
        invoice.save(_allow_status_change=True)
        bal = MilestoneInvoiceService.sync_contract_paid(contract=activated_contract)
        assert bal.cumulative_gross_paid == Decimal("19000000.00")
        # Not yet certified — retention unpaid, so the contract can't close.
        assert bal.cumulative_gross_paid < bal.cumulative_gross_certified

        # After retention release + payment, paid reaches certified.
        invoice.paid_amount = Decimal("20000000.00")
        invoice.save(_allow_status_change=True)
        bal = MilestoneInvoiceService.sync_contract_paid(contract=activated_contract)
        assert bal.cumulative_gross_paid == Decimal("20000000.00")
        assert bal.cumulative_gross_paid == bal.cumulative_gross_certified

    def test_retention_withheld_open_sums_open_liens(
        self, activated_contract, _legacy_accounts, approver,
    ):
        """ContractBalanceSerializer.retention_withheld_open = Σ open invoice
        liens — the operative 'release now' figure the detail page gates on."""
        from contracts.models import ContractBalance
        from contracts.serializers import ContractBalanceSerializer
        from contracts.services.milestone_invoice_service import MilestoneInvoiceService

        bal = ContractBalance.objects.get(pk=activated_contract.pk)
        # No milestone invoiced yet → no open liens.
        assert ContractBalanceSerializer(bal).data["retention_withheld_open"] == "0.00"

        ms = _milestone_with_lines(
            activated_contract, _legacy_accounts.expense, number=7, amount="20000000.00",
        )
        MilestoneInvoiceService.approve_and_invoice(milestone=ms, actor=approver)

        bal = ContractBalance.objects.get(pk=activated_contract.pk)
        # 5% of 20M = 1M withheld on the milestone invoice.
        assert ContractBalanceSerializer(bal).data["retention_withheld_open"] == "1000000.00"

        # Releasing lifts the lien → open falls back to 0.
        MilestoneInvoiceService.release_retention(contract=activated_contract, actor=approver)
        bal = ContractBalance.objects.get(pk=activated_contract.pk)
        assert ContractBalanceSerializer(bal).data["retention_withheld_open"] == "0.00"

    def test_milestone_serializer_nests_posted_payments(
        self, activated_contract, _legacy_accounts, approver,
    ):
        """MilestoneScheduleSerializer.payments lists POSTED settling payments
        (amount = PaymentAllocation.amount); drafts excluded; and the fields
        are empty without the contract-detail context map (list view)."""
        from datetime import date as _date
        from accounting.models import Payment, PaymentAllocation
        from contracts.serializers import MilestoneScheduleSerializer
        from contracts.services.milestone_invoice_service import MilestoneInvoiceService

        ms = _milestone_with_lines(
            activated_contract, _legacy_accounts.expense, number=8, amount="20000000.00",
        )
        invoice = MilestoneInvoiceService.approve_and_invoice(milestone=ms, actor=approver)

        posted = Payment.objects.create(
            payment_number="PAY-SUB-1", payment_method="Wire",
            total_amount=Decimal("19000000.00"), status="Posted",
            payment_date=_date(2026, 3, 2),
        )
        PaymentAllocation.objects.create(
            payment=posted, invoice=invoice, amount=Decimal("19000000.00"),
        )
        draft = Payment.objects.create(
            payment_number="PAY-SUB-2", payment_method="Wire",
            total_amount=Decimal("1000000.00"), status="Draft",
            payment_date=_date(2026, 3, 3),
        )
        PaymentAllocation.objects.create(
            payment=draft, invoice=invoice, amount=Decimal("1000000.00"),
        )

        ms.refresh_from_db()
        ctx = {
            "contract_number": activated_contract.contract_number,
            "milestone_invoice_map": {invoice.invoice_number: invoice},
        }
        data = MilestoneScheduleSerializer(ms, context=ctx).data

        assert data["invoice"]["invoice_number"] == invoice.invoice_number
        pays = data["payments"]
        assert len(pays) == 1                       # posted only, draft excluded
        assert pays[0]["payment_number"] == "PAY-SUB-1"
        assert pays[0]["amount"] == "19000000.00"   # allocation amount
        assert pays[0]["status"] == "Posted"

        # No context map (list view) → no per-milestone resolution.
        bare = MilestoneScheduleSerializer(ms).data
        assert bare["invoice"] is None
        assert bare["payments"] == []
