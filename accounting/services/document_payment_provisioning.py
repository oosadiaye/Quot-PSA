"""Provision the single Draft Outgoing Payment for an approved Payment Document.

Mirrors ``accounting/services/pv_payment_provisioning.ensure_draft_payment_for_pv``:
idempotent (one non-Void ``Payment`` per document, backed by the DB constraint
``uniq_live_payment_per_document``), and the caller owns the transaction. The
Payment's cash-out equals the document's bank-credit total, and the document's
bank account is authoritative (fixed) — the operator does not re-pick it, because
the bank is already an explicit balanced-journal line in the document.
"""
from datetime import date as _date

from django.db import transaction


def ensure_draft_payment_for_document(pd, *, actor=None):
    """Return the live Draft Payment for ``pd``, creating it if absent.

    Never creates a second Payment and never mutates a Posted/Void one. Must be
    called inside a transaction (uses ``select_for_update``); the caller owns it.
    """
    from accounting.models import TransactionSequence
    from accounting.models.receivables import Payment
    from accounting.models.payment_document import PaymentDocument
    from accounting.services.payment_document_posting import _bank_credit, _lines

    # Serialise concurrent provisioning for the same document (the workflow
    # receiver racing a re-submit). The DB partial-unique constraint
    # (uniq_live_payment_per_document) is the belt-and-suspenders backstop.
    PaymentDocument.objects.select_for_update().filter(pk=pd.pk).first()

    existing = pd.cash_payments.exclude(status="Void").order_by("id").first()
    if existing is not None:
        return existing

    bank_gl_id = pd.bank_account.gl_account_id if pd.bank_account_id else None
    cash_out = _bank_credit(_lines(pd), bank_gl_id)
    payment_number = TransactionSequence.get_next("payment", "PAY-")
    return Payment.objects.create(
        payment_number=payment_number,
        payment_date=_date.today(),
        payment_method="Wire",
        reference_number=pd.reference_number or pd.document_number,
        total_amount=cash_out,
        status="Draft",
        payment_document=pd,
        bank_account=pd.bank_account,  # authoritative — fixed from the document
        document_number=payment_number,
        created_by=actor,
    )


@transaction.atomic
def post_document_sourced_payment(payment, *, actor=None):
    """Post an Outgoing Payment that is sourced from a Payment Document.

    Posts the document's OWN balanced journal (DR settlement / CR bank — NOT the
    AP/deduction shape), flips the document to ``Paid`` and the payment to
    ``Posted``, and links the journal to both. This is the single cash-out event
    for a document-sourced proposal, and the seam sub-project B (e-payment) will
    extend (swap the bank-credit leg to a clearing GL + fire the gateway).

    Returns the payment. Raises ``PaymentDocumentError`` if the payment is not
    document-sourced or the document is not ``Approved``.
    """
    from accounting.services.payment_document_posting import (
        post_document_journal, PaymentDocumentError,
    )
    pd = payment.payment_document
    if pd is None:
        raise PaymentDocumentError("Payment is not sourced from a payment document.")
    if pd.status != "Approved":
        raise PaymentDocumentError("The payment document is not approved.")

    journal, cash_out = post_document_journal(pd, actor=actor)
    pd.journal = journal
    pd.status = "Paid"
    pd.save(update_fields=["journal", "status", "updated_at"], _allow_status_change=True)

    payment.journal_entry = journal
    payment.total_amount = cash_out
    payment.status = "Posted"
    payment.save(update_fields=["journal_entry", "total_amount", "status", "updated_at"],
                 _allow_status_change=True)
    return payment
