"""Vendor open-item clearing — SAP F-44 style.

``accounting.services.vendor_open_items.clear_open_items`` matches available
vendor credit against open invoices (FIFO, capped). Two paths:

* **payment** — an unapplied posted payment is linked to an invoice via a new
  ``PaymentAllocation``. GL-neutral: no journal is created.
* **advance** — an outstanding ``VendorAdvance`` is cleared against the invoice
  via ``VendorAdvanceService.clear``, which posts DR AP / CR Vendor-Advance.

Both bump ``VendorInvoice.paid_amount`` (through the ImmutableModelMixin escape
hatch) so ``balance_due`` drops and the status settles to Partially Paid / Paid.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest


def _posted_invoice(vendor, total, *, number):
    """A Posted vendor invoice with nothing paid yet."""
    from accounting.models.receivables import VendorInvoice
    return VendorInvoice.objects.create(
        vendor=vendor, invoice_number=number, invoice_date=date(2026, 1, 10),
        total_amount=Decimal(total), paid_amount=Decimal("0.00"), status="Posted",
    )


# ── Payment path (GL-neutral) ─────────────────────────────────────────────

@pytest.mark.django_db
class TestClearWithUnappliedPayment:

    def test_unapplied_payment_clears_invoice_gl_neutral(
        self, batch_vendor, make_posted_payment,
    ):
        from accounting.models import JournalHeader
        from accounting.models.receivables import PaymentAllocation
        from accounting.services.vendor_open_items import clear_open_items

        inv = _posted_invoice(batch_vendor, "1000.00", number="VINV-A1")
        make_posted_payment(vendor=batch_vendor, amount="1000.00")  # no allocations
        journals_before = JournalHeader.objects.count()

        result = clear_open_items(batch_vendor)

        assert result["total_cleared"] == "1000.00"
        alloc = PaymentAllocation.objects.get(invoice=inv)
        assert alloc.amount == Decimal("1000.00")
        inv.refresh_from_db()
        assert inv.paid_amount == Decimal("1000.00")
        assert inv.status == "Paid"
        # GL-neutral: the payment already hit AP, so clearing posts nothing.
        assert JournalHeader.objects.count() == journals_before

    def test_partial_payment_leaves_invoice_partially_paid(
        self, batch_vendor, make_posted_payment,
    ):
        from accounting.services.vendor_open_items import clear_open_items

        inv = _posted_invoice(batch_vendor, "1000.00", number="VINV-A2")
        make_posted_payment(vendor=batch_vendor, amount="600.00")

        clear_open_items(batch_vendor)

        inv.refresh_from_db()
        assert inv.paid_amount == Decimal("600.00")
        assert inv.status == "Partially Paid"

    def test_never_over_applies_a_large_payment(
        self, batch_vendor, make_posted_payment,
    ):
        """A payment larger than the invoice only draws the invoice's balance;
        the remainder stays available (unallocated)."""
        from accounting.models.receivables import PaymentAllocation
        from accounting.services.vendor_open_items import clear_open_items

        inv = _posted_invoice(batch_vendor, "400.00", number="VINV-A3")
        pmt = make_posted_payment(vendor=batch_vendor, amount="1000.00")

        clear_open_items(batch_vendor)

        alloc = PaymentAllocation.objects.get(payment=pmt, invoice=inv)
        assert alloc.amount == Decimal("400.00")     # capped at balance_due
        inv.refresh_from_db()
        assert inv.status == "Paid"

    def test_manual_invoice_ids_restricts_scope(
        self, batch_vendor, make_posted_payment,
    ):
        from accounting.services.vendor_open_items import clear_open_items

        inv1 = _posted_invoice(batch_vendor, "500.00", number="VINV-A4")
        inv2 = _posted_invoice(batch_vendor, "500.00", number="VINV-A5")
        make_posted_payment(vendor=batch_vendor, amount="1000.00")

        # Only clear inv2.
        clear_open_items(batch_vendor, invoice_ids=[inv2.id])

        inv1.refresh_from_db(); inv2.refresh_from_db()
        assert inv1.status == "Posted" and inv1.paid_amount == Decimal("0.00")
        assert inv2.status == "Paid" and inv2.paid_amount == Decimal("500.00")

    def test_fifo_oldest_invoice_first(self, batch_vendor, make_posted_payment):
        """Limited credit clears the oldest invoice first."""
        from accounting.models.receivables import VendorInvoice
        from accounting.services.vendor_open_items import clear_open_items

        old = VendorInvoice.objects.create(
            vendor=batch_vendor, invoice_number="VINV-OLD", invoice_date=date(2026, 1, 1),
            total_amount=Decimal("500.00"), paid_amount=Decimal("0.00"), status="Posted",
        )
        new = VendorInvoice.objects.create(
            vendor=batch_vendor, invoice_number="VINV-NEW", invoice_date=date(2026, 6, 1),
            total_amount=Decimal("500.00"), paid_amount=Decimal("0.00"), status="Posted",
        )
        make_posted_payment(vendor=batch_vendor, amount="500.00")   # only enough for one

        clear_open_items(batch_vendor)

        old.refresh_from_db(); new.refresh_from_db()
        assert old.status == "Paid"
        assert new.status == "Posted" and new.paid_amount == Decimal("0.00")


# ── Advance path (posts the contra journal) ───────────────────────────────

@pytest.fixture
def advance_recon_account(db):
    from accounting.models import Account
    acc, _ = Account.objects.get_or_create(
        code="31050000",
        defaults={
            "name": "Vendor Advances (Special GL)", "account_type": "Asset",
            "is_active": True, "reconciliation_type": "vendor_advance",
        },
    )
    return acc


@pytest.fixture
def ap_recon_account(db):
    """A standard AP recon account so ``get_vendor_ap_account`` resolves via
    the fallback (the test vendor has no category)."""
    from accounting.models import Account
    acc, _ = Account.objects.get_or_create(
        code="21010101",
        defaults={
            "name": "Accounts Payable (Control)", "account_type": "Liability",
            "is_active": True, "reconciliation_type": "accounts_payable",
        },
    )
    return acc


@pytest.mark.django_db(transaction=True)
class TestClearWithAdvance:

    def test_advance_clears_invoice_and_posts_contra_journal(
        self, advance_recon_account, ap_recon_account,
        bank_account_for_batch, batch_vendor, superuser, open_fiscal_period,
    ):
        from accounting.models.vendor_advance import VendorAdvanceStatus
        from accounting.services.vendor_advance import VendorAdvanceService
        from accounting.services.vendor_open_items import clear_open_items

        # A ₦500 outstanding advance for the vendor.
        adv = VendorAdvanceService.disburse(
            vendor=batch_vendor, amount=Decimal("500.00"), source_type="AP_DOWNPAYMENT",
            source_id=None, reference="DP-OI-1", posting_date=date.today(),
            actor=superuser, bank_account=bank_account_for_batch, notes="pytest",
            deductions=[],
        )
        inv = _posted_invoice(batch_vendor, "500.00", number="VINV-ADV")

        result = clear_open_items(batch_vendor, actor=superuser)

        assert result["total_cleared"] == "500.00"
        adv.refresh_from_db()
        assert adv.amount_recovered == Decimal("500.00")
        assert adv.status == VendorAdvanceStatus.CLEARED
        inv.refresh_from_db()
        assert inv.paid_amount == Decimal("500.00")
        assert inv.status == "Paid"
        # A contra clearance journal was posted (DR AP / CR Vendor-Advance).
        clearance = adv.clearances.first()
        assert clearance is not None
        j = clearance.clearing_journal
        lines = list(j.lines.all())
        dr = sum((l.debit or 0) for l in lines)
        cr = sum((l.credit or 0) for l in lines)
        assert dr == cr == Decimal("500.00")
        # The obligation leaves the Vendor-Advance special-GL (credit) and
        # lands in an AP control account (debit). The concrete AP account is
        # whatever get_vendor_ap_account resolves — the tenant seed already
        # carries one, so assert the shape, not a fixed id.
        assert any(l.account_id == advance_recon_account.id and l.credit == Decimal("500.00")
                   for l in lines), "Vendor-Advance recon should be credited"
        ap_debit = next((l for l in lines if (l.debit or 0) == Decimal("500.00")
                         and l.account_id != advance_recon_account.id), None)
        assert ap_debit is not None and ap_debit.account.reconciliation_type == "accounts_payable"
