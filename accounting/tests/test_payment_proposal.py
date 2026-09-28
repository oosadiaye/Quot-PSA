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
