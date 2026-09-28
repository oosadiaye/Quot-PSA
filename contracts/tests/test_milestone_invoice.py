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

    def test_draft_contract_rejects_approve_with_clear_error(
        self, draft_contract, _legacy_accounts, approver,
    ):
        """A milestone on a DRAFT (not-yet-activated) contract has no balance
        ledger. Approve must fail with a clear ``TransactionPostingError`` that
        the view maps to a 400 — never an unhandled ``ContractBalance.DoesNotExist``
        (which surfaced as a 500). Regression for that crash."""
        from contracts.models import ContractBalance, MilestoneStatus
        from accounting.services.base_posting import TransactionPostingError
        from contracts.services.milestone_invoice_service import MilestoneInvoiceService

        assert not ContractBalance.objects.filter(pk=draft_contract.pk).exists()
        ms = _milestone_with_lines(draft_contract, _legacy_accounts.expense, amount="1000000.00")

        with pytest.raises(TransactionPostingError, match=r"[Aa]ctivate"):
            MilestoneInvoiceService.approve_and_invoice(milestone=ms, actor=approver)

        # Nothing posted; the milestone is untouched (the guard fails fast).
        ms.refresh_from_db()
        assert ms.status == MilestoneStatus.COMPLETED

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

    def test_activity_endpoint_aggregates_contract_and_subobject_logs(
        self, activated_contract, _legacy_accounts, approver,
    ):
        """GET /contracts/contracts/{id}/activity/ returns AuditLog entries for
        the contract AND its sub-objects (a milestone), with the actor username,
        newest-first, and excludes unrelated objects."""
        from django.contrib.auth import get_user_model
        from django.contrib.contenttypes.models import ContentType
        from rest_framework.test import APIClient
        from core.models import AuditLog
        from contracts.models import Contract, MilestoneSchedule

        ms = _milestone_with_lines(
            activated_contract, _legacy_accounts.expense, number=9, amount="1000000.00",
        )
        ct_c = ContentType.objects.get_for_model(Contract)
        ct_m = ContentType.objects.get_for_model(MilestoneSchedule)
        AuditLog.objects.create(user=approver, action="CREATE", content_type=ct_c,
                                object_id=activated_contract.id, object_repr="the contract")
        AuditLog.objects.create(user=approver, action="APPROVE", content_type=ct_m,
                                object_id=ms.id, object_repr="the milestone")
        # Unrelated entry (another contract's id) — must be excluded.
        AuditLog.objects.create(user=approver, action="CREATE", content_type=ct_c,
                                object_id=987654, object_repr="other contract")

        su = get_user_model().objects.create(
            username="activity_su", is_superuser=True, is_staff=True,
        )
        client = APIClient(HTTP_X_TENANT_DOMAIN="pytest.localhost")
        client.force_authenticate(su)
        resp = client.get(f"/api/contracts/contracts/{activated_contract.id}/activity/")
        assert resp.status_code == 200, resp.content

        body = resp.json()
        results = body["results"] if isinstance(body, dict) and "results" in body else body
        pairs = {(r["model_name"], r["object_id"]) for r in results}
        assert ("contract", activated_contract.id) in pairs
        assert ("milestoneschedule", ms.id) in pairs
        assert ("contract", 987654) not in pairs      # unrelated excluded
        # Actor is surfaced by username — the approver-authored entries appear.
        # (The feed also carries signal-generated rows whose actor is 'System'
        # in tests, which is the comprehensive audit working as intended.)
        assert approver.username in {r["username"] for r in results}
        # Newest-first ordering.
        stamps = [r["timestamp"] for r in results]
        assert stamps == sorted(stamps, reverse=True)

    def test_milestone_line_serializer_exposes_appropriation_display(
        self, activated_contract, _legacy_accounts, appropriation,
    ):
        """MilestoneInvoiceLineSerializer surfaces the appropriation's economic
        code/name (for the coding-lines editor), null-safe when unset."""
        from contracts.models import MilestoneSchedule, MilestoneInvoiceLine, MilestoneStatus
        from contracts.serializers import MilestoneInvoiceLineSerializer

        ms = MilestoneSchedule.objects.create(
            contract=activated_contract, milestone_number=10, description="coding",
            scheduled_value=Decimal("1000.00"), percentage_weight=Decimal("1.000"),
            status=MilestoneStatus.COMPLETED,
        )
        line = MilestoneInvoiceLine.objects.create(
            milestone=ms, account=_legacy_accounts.expense, appropriation=appropriation,
            description="works", amount=Decimal("1000.00"),
        )
        data = MilestoneInvoiceLineSerializer(line).data
        assert data["appropriation"] == appropriation.id
        assert data["appropriation_code"] == appropriation.economic.code
        assert data["account_code"] == _legacy_accounts.expense.code

        # Null-safe when the line has no appropriation.
        line2 = MilestoneInvoiceLine.objects.create(
            milestone=ms, account=_legacy_accounts.expense, description="y", amount=Decimal("1.00"),
        )
        assert MilestoneInvoiceLineSerializer(line2).data["appropriation_code"] is None

    def test_contract_serializer_exposes_appropriation_label(
        self, activated_contract, appropriation,
    ):
        """ContractSerializer.appropriation_label gives the coding-line editor a
        ready label ('<code> — <name>') to seed the per-line default; null when
        the contract has no appropriation."""
        from contracts.serializers import ContractSerializer

        activated_contract.appropriation = appropriation
        activated_contract.save(update_fields=["appropriation"])
        label = ContractSerializer(activated_contract).data["appropriation_label"]
        assert label == f"{appropriation.economic.code} — {appropriation.economic.name}"

        # Null when unset.
        activated_contract.appropriation = None
        activated_contract.save(update_fields=["appropriation"])
        assert ContractSerializer(activated_contract).data["appropriation_label"] is None

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
        # Acct Doc linkage: the invoice carries its accrual journal id.
        assert data["invoice"]["journal_entry_id"] == invoice.journal_entry_id
        assert data["invoice"]["journal_entry_id"] is not None
        pays = data["payments"]
        assert len(pays) == 1                       # posted only, draft excluded
        assert pays[0]["payment_number"] == "PAY-SUB-1"
        assert pays[0]["amount"] == "19000000.00"   # allocation amount
        assert pays[0]["status"] == "Posted"
        assert "journal_entry_id" in pays[0]        # payment's journal id surfaced

        # No context map (list view) → no per-milestone resolution.
        bare = MilestoneScheduleSerializer(ms).data
        assert bare["invoice"] is None
        assert bare["payments"] == []

    # ── Coding captured at creation + approve auto-posts to AP ────────────

    def test_serializer_create_persists_nested_coding_lines(
        self, activated_contract, _legacy_accounts, appropriation, approver,
    ):
        """POSTing a milestone with a nested ``lines`` list materialises the
        MilestoneInvoiceLine rows (coding captured at creation)."""
        from contracts.serializers import MilestoneScheduleSerializer

        data = {
            "contract": activated_contract.id,
            "milestone_number": 20,
            "description": "Roof",
            "scheduled_value": "1000000.00",
            "percentage_weight": "10.000",
            "lines": [
                {"account": _legacy_accounts.expense.id, "appropriation": appropriation.id,
                 "description": "Roof works", "amount": "600000.00"},
                {"account": _legacy_accounts.expense.id, "description": "Extras", "amount": "400000.00"},
            ],
        }
        ser = MilestoneScheduleSerializer(data=data)
        assert ser.is_valid(), ser.errors
        ms = ser.save(created_by=approver, updated_by=approver)

        lines = list(ms.lines.all())
        assert len(lines) == 2
        assert sum(l.amount for l in lines) == Decimal("1000000.00")
        assert lines[0].appropriation_id == appropriation.id

    def test_serializer_rejects_lines_not_summing_to_scheduled_value(
        self, activated_contract, _legacy_accounts,
    ):
        """Coding lines must total the Scheduled Value (milestone = invoice)."""
        from contracts.serializers import MilestoneScheduleSerializer

        data = {
            "contract": activated_contract.id, "milestone_number": 21,
            "description": "Bad", "scheduled_value": "1000000.00",
            "percentage_weight": "10.000",
            # 600k ≠ 1M
            "lines": [{"account": _legacy_accounts.expense.id, "amount": "600000.00"}],
        }
        ser = MilestoneScheduleSerializer(data=data)
        assert not ser.is_valid()
        assert "lines" in ser.errors

    def test_serializer_locks_lines_after_invoiced(
        self, activated_contract, _legacy_accounts, approver,
    ):
        """Editing coding on an INVOICED milestone is rejected (locked)."""
        from contracts.serializers import MilestoneScheduleSerializer
        from contracts.services.milestone_invoice_service import MilestoneInvoiceService

        ms = _milestone_with_lines(
            activated_contract, _legacy_accounts.expense, number=24, amount="2000000.00",
        )
        MilestoneInvoiceService.approve_and_invoice(milestone=ms, actor=approver)
        ms.refresh_from_db()

        ser = MilestoneScheduleSerializer(
            ms, partial=True,
            data={"lines": [{"account": _legacy_accounts.expense.id, "amount": "2000000.00"}]},
        )
        assert not ser.is_valid()
        assert "lines" in ser.errors

    def test_approve_endpoint_auto_posts_to_ap_register(
        self, activated_contract, _legacy_accounts,
    ):
        """The approve action posts the AP invoice from the milestone's coding
        lines and flips it to INVOICED — it appears in the AP register at once."""
        from rest_framework.test import APIClient
        from django.contrib.auth import get_user_model
        from contracts.models import MilestoneSchedule, MilestoneInvoiceLine, MilestoneStatus
        from accounting.models import VendorInvoice

        ms = MilestoneSchedule.objects.create(
            contract=activated_contract, milestone_number=22, description="Slab",
            scheduled_value=Decimal("5000000.00"), percentage_weight=Decimal("10.000"),
            status=MilestoneStatus.IN_PROGRESS,
        )
        MilestoneInvoiceLine.objects.create(
            milestone=ms, account=_legacy_accounts.expense,
            description="Slab", amount=Decimal("5000000.00"),
        )
        # get_or_create — auth_user (public schema) is not flushed between
        # transaction=True reuse-db runs, so a plain create would collide.
        su, _ = get_user_model().objects.get_or_create(
            username="ms_approve_su", defaults={"is_superuser": True, "is_staff": True},
        )
        client = APIClient(HTTP_X_TENANT_DOMAIN="pytest.localhost")
        client.force_authenticate(su)

        resp = client.post(f"/api/contracts/milestones/{ms.id}/approve/", {}, format="json")
        assert resp.status_code == 200, resp.content

        ms.refresh_from_db()
        assert ms.status == MilestoneStatus.INVOICED
        # In the AP register: a Posted VendorInvoice keyed to the contract.
        inv = (VendorInvoice.objects
               .filter(reference=activated_contract.contract_number)
               .order_by("-id").first())
        assert inv is not None
        assert inv.status == "Posted"
        assert inv.total_amount == Decimal("5000000.00")

    def test_approve_endpoint_without_lines_errors(self, activated_contract):
        """Approving a milestone with no coding lines is rejected (can't post)."""
        from rest_framework.test import APIClient
        from django.contrib.auth import get_user_model
        from contracts.models import MilestoneSchedule, MilestoneStatus

        ms = MilestoneSchedule.objects.create(
            contract=activated_contract, milestone_number=23, description="No coding",
            scheduled_value=Decimal("1000000.00"), percentage_weight=Decimal("5.000"),
            status=MilestoneStatus.IN_PROGRESS,
        )
        su, _ = get_user_model().objects.get_or_create(
            username="ms_nolines_su", defaults={"is_superuser": True, "is_staff": True},
        )
        client = APIClient(HTTP_X_TENANT_DOMAIN="pytest.localhost")
        client.force_authenticate(su)

        resp = client.post(f"/api/contracts/milestones/{ms.id}/approve/", {}, format="json")
        assert resp.status_code == 400
        assert b"line" in resp.content.lower()
        ms.refresh_from_db()
        assert ms.status != MilestoneStatus.INVOICED

    def test_serializer_update_replaces_coding_lines(
        self, activated_contract, _legacy_accounts, approver,
    ):
        """Editing a not-yet-invoiced milestone replaces its coding lines
        (nested PATCH) — the path that lets a legacy, coding-less milestone be
        coded before approval."""
        from contracts.serializers import MilestoneScheduleSerializer
        from contracts.models import MilestoneSchedule, MilestoneStatus

        ms = MilestoneSchedule.objects.create(
            contract=activated_contract, milestone_number=25, description="edit me",
            scheduled_value=Decimal("2000000.00"), percentage_weight=Decimal("2.000"),
            status=MilestoneStatus.IN_PROGRESS,
        )
        assert ms.lines.count() == 0

        ser = MilestoneScheduleSerializer(ms, partial=True, data={
            "lines": [
                {"account": _legacy_accounts.expense.id, "amount": "1500000.00"},
                {"account": _legacy_accounts.expense.id, "amount": "500000.00"},
            ],
        })
        assert ser.is_valid(), ser.errors
        ser.save(updated_by=approver)

        ms.refresh_from_db()
        assert ms.lines.count() == 2
        assert sum(l.amount for l in ms.lines.all()) == Decimal("2000000.00")
