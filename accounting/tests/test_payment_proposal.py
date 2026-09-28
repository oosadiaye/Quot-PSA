from decimal import Decimal
import pytest


@pytest.fixture
def pp_bank(db):
    from accounting.models import Account, BankAccount
    gl, _ = Account.objects.get_or_create(
        code="31010101", defaults={"name": "TSA Cash", "account_type": "Asset",
                                    "is_active": True, "is_postable": True,
                                    "reconciliation_type": "bank_accounting"})
    bank, _ = BankAccount.objects.get_or_create(
        account_number="0000000009",
        defaults={"name": "PP TSA", "bank_name": "CBN", "gl_account": gl,
                  "current_balance": Decimal("1000000.00"), "currency": None})
    return bank


@pytest.mark.django_db
def test_payment_cannot_have_both_pv_and_document(pp_bank):
    """A Payment is PV-sourced OR PD-sourced, never both."""
    from django.db import IntegrityError, transaction
    from accounting.models import Payment, PaymentVoucherGov, PaymentDocument
    # PaymentVoucherGov requires ncoa_code/tsa_account (real FKs, no default);
    # reuse the proven fixture helpers from test_central_payment_processing
    # instead of re-deriving the NCoA segment tree here.
    from accounting.tests.test_central_payment_processing import _ncoa, _tsa
    pv = PaymentVoucherGov.objects.create(
        voucher_number="PV-PP-1", payment_type="VENDOR", ncoa_code=_ncoa(),
        payee_name="Test Payee", narration="payment proposal test",
        tsa_account=_tsa(), gross_amount=Decimal("100.00"), net_amount=Decimal("100.00"))
    pd = PaymentDocument.objects.create(document_number="PD-PP-1", bank_account=pp_bank)
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Payment.objects.create(bank_account=pp_bank, total_amount=Decimal("100.00"),
                                   payment_voucher=pv, payment_document=pd)


# ── Task 2: Payment Document proposal lifecycle ──────────────────────────────

@pytest.mark.django_db
def test_payment_document_has_proposal_statuses(pp_bank):
    from accounting.models import PaymentDocument
    values = {c[0] for c in PaymentDocument._meta.get_field("status").choices}
    assert {"Draft", "Pending Approval", "Approved", "Paid", "Void"} <= values


@pytest.mark.django_db
def test_paid_payment_document_is_immutable(pp_bank):
    """A Paid Payment Document cannot be edited without the _allow_status_change
    escape hatch — the immutability guard extends to the new terminal state."""
    from django.core.exceptions import ValidationError
    from accounting.models import PaymentDocument
    pd = PaymentDocument.objects.create(document_number="PD-IMM-1", bank_account=pp_bank, status="Draft")
    pd.status = "Paid"
    pd.save(_allow_status_change=True)     # a legitimate transition still works
    pd.description = "tampered"
    with pytest.raises(ValidationError):
        pd.save()                          # editing a Paid doc without the hatch is blocked


# ── Task 4: provisioning a Draft Payment for an approved document ─────────────

@pytest.mark.django_db
def test_ensure_draft_payment_for_document_is_idempotent(pp_bank):
    from django.db import transaction
    from accounting.models import PaymentDocument, PaymentDocumentLine, Account, Payment
    from accounting.services.document_payment_provisioning import ensure_draft_payment_for_document
    liab, _ = Account.objects.get_or_create(code="41030103", defaults={
        "name": "WHT", "account_type": "Liability", "is_active": True, "is_postable": True})
    pd = PaymentDocument.objects.create(document_number="PD-PROV-1", bank_account=pp_bank,
                                        reference_number="R1", status="Approved")
    PaymentDocumentLine.objects.create(payment_document=pd, account=liab, debit=Decimal("500.00"))
    PaymentDocumentLine.objects.create(payment_document=pd, account=pp_bank.gl_account, credit=Decimal("500.00"))
    with transaction.atomic():
        p1 = ensure_draft_payment_for_document(pd)
    with transaction.atomic():
        p2 = ensure_draft_payment_for_document(pd)   # idempotent — never a 2nd
    assert p1.pk == p2.pk
    assert p1.payment_document_id == pd.pk
    assert p1.payment_voucher_id is None
    assert p1.status == "Draft"
    assert p1.total_amount == Decimal("500.00")       # cash-out = credit to bank GL
    assert Payment.objects.filter(payment_document=pd).exclude(status="Void").count() == 1


# ── Task 5: posting a document-sourced Outgoing Payment ──────────────────────

@pytest.fixture
def open_period_pp(db):
    from accounting.models import FiscalPeriod
    from datetime import date
    today = date.today()
    fp, _ = FiscalPeriod.objects.get_or_create(
        fiscal_year=today.year, period_number=today.month, period_type="Monthly",
        defaults={"start_date": today.replace(day=1), "end_date": today,
                  "status": "Open", "is_closed": False})
    return fp


@pytest.mark.django_db(transaction=True)
def test_post_document_sourced_payment_posts_journal(pp_bank, open_period_pp):
    from django.db import transaction
    from accounting.models import PaymentDocument, PaymentDocumentLine, Account
    from accounting.services.document_payment_provisioning import (
        ensure_draft_payment_for_document, post_document_sourced_payment)
    liab, _ = Account.objects.get_or_create(code="41030103", defaults={
        "name": "WHT", "account_type": "Liability", "is_active": True, "is_postable": True})
    pd = PaymentDocument.objects.create(document_number="PD-POSTPP-1", bank_account=pp_bank,
                                        reference_number="R2", status="Approved")
    PaymentDocumentLine.objects.create(payment_document=pd, account=liab, debit=Decimal("700.00"))
    PaymentDocumentLine.objects.create(payment_document=pd, account=pp_bank.gl_account, credit=Decimal("700.00"))
    with transaction.atomic():
        pay = ensure_draft_payment_for_document(pd)
    post_document_sourced_payment(pay, actor=None)
    pay.refresh_from_db(); pd.refresh_from_db()
    assert pay.status == "Posted"
    assert pd.status == "Paid"
    assert pd.journal_id is not None
    assert pay.journal_entry_id == pd.journal_id
    j = pd.journal
    assert sum(l.debit for l in j.lines.all()) == sum(l.credit for l in j.lines.all()) == Decimal("700.00")
