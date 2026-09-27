"""CSV template + bulk import for Payment Documents. Rows sharing a
``document_ref`` group into one Draft document. Never auto-posts."""
from __future__ import annotations

import csv
import io
from decimal import Decimal, InvalidOperation

from django.db import transaction

TEMPLATE_COLUMNS = [
    "document_ref", "bank_account_number", "account_code", "vendor_code",
    "debit", "credit", "memo",
]


def build_template_csv() -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(TEMPLATE_COLUMNS)
    writer.writerow(["SAL-2026-03", "0000000001", "21050000", "", "90000.00", "0.00", "March net pay"])
    return buf.getvalue()


def parse_rows(file_bytes: bytes) -> list[dict]:
    text = file_bytes.decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text)))


def _dec(value) -> Decimal:
    try:
        return Decimal(str(value or "0").strip() or "0")
    except (InvalidOperation, AttributeError):
        return Decimal("0.00")


@transaction.atomic
def import_payment_documents_from_rows(rows: list[dict], *, source: str = "import") -> list:
    """Group rows by ``document_ref`` into Draft PaymentDocuments."""
    from accounting.models import Account, BankAccount, PaymentDocument, PaymentDocumentLine, TransactionSequence
    from procurement.models import Vendor

    groups: dict[str, list[dict]] = {}
    for row in rows:
        groups.setdefault((row.get("document_ref") or "").strip(), []).append(row)

    created = []
    for ref, group in groups.items():
        first = group[0]
        bank = BankAccount.objects.get(account_number=(first.get("bank_account_number") or "").strip())
        doc = PaymentDocument.objects.create(
            document_number=TransactionSequence.get_next("payment_document", "PD-"),
            bank_account=bank, reference_number=ref, description=f"Imported {ref}", source=source,
        )
        for row in group:
            account = Account.objects.get(code=(row.get("account_code") or "").strip())
            vendor = None
            vcode = (row.get("vendor_code") or "").strip()
            if vcode:
                vendor = Vendor.objects.filter(code=vcode).first()
            PaymentDocumentLine.objects.create(
                payment_document=doc, account=account, vendor=vendor,
                debit=_dec(row.get("debit")), credit=_dec(row.get("credit")),
                memo=(row.get("memo") or "")[:255],
            )
        created.append(doc)
    return created
