"""AI invoice-scan mapping — the JSON→Draft logic, without a live AI call.

The provider round-trip lives in ``superadmin.ai_client.call_model`` and is
covered by its own guardrail tests; here we prove the parsing and the field
mapping that turns a model's JSON into a reviewable Draft VendorInvoice.

``transaction=True`` and uuid-unique names, like the other DB-backed tests.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from accounting.services import ai_invoice_extraction as X

pytestmark = pytest.mark.django_db(transaction=True)


# ── pure helpers (no DB) ────────────────────────────────────────────────

def test_parse_extraction_tolerates_code_fences():
    assert X.parse_extraction('```json\n{"a": 1}\n```') == {"a": 1}
    assert X.parse_extraction('here is the data {"a": 2} thanks') == {"a": 2}


def test_parse_extraction_rejects_non_json():
    with pytest.raises(ValueError):
        X.parse_extraction("sorry, I could not read the invoice")


def test_to_decimal_strips_symbols_and_separators():
    assert X._to_decimal("₦1,200.50") == Decimal("1200.50")
    assert X._to_decimal("450") == Decimal("450")
    assert X._to_decimal(None) is None
    assert X._to_decimal("n/a") is None


def test_to_date_accepts_iso_and_house_format():
    assert str(X._to_date("2026-06-04")) == "2026-06-04"
    assert str(X._to_date("04/06/2026")) == "2026-06-04"
    assert X._to_date(None) is None


# ── mapping to a Draft (DB) ─────────────────────────────────────────────

def _vendor(name):
    from procurement.models import Vendor
    tok = uuid.uuid4().hex[:8]
    return Vendor.objects.create(code=f"V{tok}", name=name)


def test_build_draft_maps_fields_and_matches_vendor():
    vendor = _vendor(f"Acme Works {uuid.uuid4().hex[:6]}")
    extracted = {
        "invoice_number": f"INV-{uuid.uuid4().hex[:6]}",
        "vendor_name": vendor.name,
        "reference": "PO/2026/001",
        "invoice_date": "2026-06-04",
        "due_date": "2026-07-04",
        "currency_code": "NGN",
        "subtotal": "1,000.00",
        "tax_amount": "75.00",
        "total_amount": "1,075.00",
        "line_items": [{"description": "Cement", "amount": "1000"}],
    }

    invoice, warnings = X._build_draft(extracted, b"fake-bytes", "scan.png")

    assert invoice.pk is not None
    assert invoice.status == "Draft"
    assert invoice.vendor_id == vendor.id                       # matched by name
    assert invoice.invoice_number == extracted["invoice_number"]
    assert invoice.reference == "PO/2026/001"
    assert invoice.total_amount == Decimal("1075.00")
    assert invoice.tax_amount == Decimal("75.00")
    assert str(invoice.invoice_date) == "2026-06-04"
    assert str(invoice.due_date) == "2026-07-04"
    assert "Cement" in invoice.description
    assert warnings == []


def test_build_draft_totals_from_subtotal_plus_tax_when_total_missing():
    extracted = {
        "vendor_name": None,
        "subtotal": "200",
        "tax_amount": "15",
        "total_amount": None,
    }
    invoice, warnings = X._build_draft(extracted, b"x", "scan.png")
    assert invoice.total_amount == Decimal("215")
    assert invoice.vendor_id is None


def test_build_draft_warns_on_unknown_vendor_and_missing_total():
    extracted = {"vendor_name": "No Such Supplier ZZZ", "total_amount": "0"}
    invoice, warnings = X._build_draft(extracted, b"x", "scan.png")
    assert invoice.vendor_id is None
    joined = " ".join(warnings)
    assert "was not found" in joined
    assert "No total amount" in joined
