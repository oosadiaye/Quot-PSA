"""
AI invoice scan → Draft VendorInvoice.

Turns an uploaded supplier invoice (image or PDF) into a Draft
``VendorInvoice`` by sending page images to the tenant's configured
``extraction`` model and mapping the returned JSON onto the invoice.

The guardrails — refusing when AI is off, the redaction policy, cost and
the audit row — all live in :func:`superadmin.ai_client.call_model`. This
module only rasterises the file, prompts, parses the JSON and maps it,
leaving a Draft the operator reviews and approves like any other.
"""
from __future__ import annotations

import base64
import io
import json
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.core.files.base import ContentFile
from django.db import connection

from superadmin.ai_client import AIRefused, call_model
from superadmin.ai_models import TenantAISetting

MAX_PDF_PAGES = 3
MAX_IMAGE_DIM = 2200
MAX_FILE_BYTES = 15 * 1024 * 1024  # 15 MB

EXTRACTION_SYSTEM = (
    "You are an accounts-payable data extractor for a Nigerian public-sector "
    "finance system. You are given one or more page images of a SINGLE supplier "
    "invoice. Read it and return ONLY a JSON object — no prose, no code fences — "
    "with exactly these keys: "
    '"invoice_number", "vendor_name", "reference", "invoice_date", "due_date", '
    '"currency_code", "subtotal", "tax_amount", "total_amount", "line_items". '
    "Rules: dates as YYYY-MM-DD; amounts as plain numbers (no currency symbol or "
    "thousands separators); currency_code as an ISO code (NGN, USD, …); line_items "
    'as an array of {"description", "amount"}; use null for any field not present '
    "on the invoice. Do not invent values."
)

EXTRACTION_PROMPT = (
    "Extract the invoice fields from the attached page image(s) and return the "
    "JSON object described. If several totals appear, total_amount is the final "
    "gross amount payable."
)


def get_extraction_setting():
    """The (tenant, TenantAISetting) for extraction, or an ``AIRefused``.

    Absence of a row means the capability is switched off — enabling it is
    a platform decision, so this never falls back to a default provider.
    """
    tenant = getattr(connection, "tenant", None)
    if tenant is None or getattr(tenant, "schema_name", "public") == "public":
        raise AIRefused("Document extraction is only available inside a tenant.")
    setting = (
        TenantAISetting.objects
        .select_related("provider")
        .filter(tenant=tenant, capability="extraction")
        .first()
    )
    if setting is None:
        raise AIRefused(
            "AI document extraction is not enabled for this organisation. "
            "An administrator must switch it on in AI settings."
        )
    return tenant, setting


def file_to_image_data_urls(raw: bytes, content_type: str, filename: str) -> list[str]:
    """Page images as ``data:`` URLs — one per PDF page, or the image itself."""
    is_pdf = content_type == "application/pdf" or (filename or "").lower().endswith(".pdf")
    if is_pdf:
        return _pdf_to_data_urls(raw)
    return [_image_to_data_url(raw, content_type or "image/png")]


def _image_to_data_url(raw: bytes, content_type: str) -> str:
    # Downscale oversized photos so the request stays small and cheap; send
    # the original bytes unchanged if Pillow cannot open them.
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(raw))
        if max(img.size) > MAX_IMAGE_DIM:
            img.thumbnail((MAX_IMAGE_DIM, MAX_IMAGE_DIM))
            buf = io.BytesIO()
            img.convert("RGB").save(buf, format="JPEG", quality=85)
            raw, content_type = buf.getvalue(), "image/jpeg"
    except Exception:
        pass
    return f"data:{content_type};base64,{base64.b64encode(raw).decode()}"


def _pdf_to_data_urls(raw: bytes) -> list[str]:
    import pymupdf as fitz  # PyMuPDF — pure-pip, no system dependency

    urls: list[str] = []
    with fitz.open(stream=raw, filetype="pdf") as doc:
        for i, page in enumerate(doc):
            if i >= MAX_PDF_PAGES:
                break
            pix = page.get_pixmap(dpi=150)
            urls.append("data:image/png;base64," + base64.b64encode(pix.tobytes("png")).decode())
    if not urls:
        raise ValueError("The PDF had no readable pages.")
    return urls


def parse_extraction(text: str) -> dict:
    """The first JSON object in the model's reply, code-fence tolerant."""
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", text).strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("The model did not return a JSON object.")
    return json.loads(match.group(0))


def _to_decimal(value) -> Decimal | None:
    if value in (None, "", "null"):
        return None
    try:
        return Decimal(str(value).replace(",", "").replace("₦", "").strip())
    except (InvalidOperation, ValueError):
        return None


def _to_date(value):
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(str(value).strip(), fmt).date()
        except ValueError:
            continue
    return None


def extract_invoice_to_draft(uploaded_file) -> dict:
    """Scan one uploaded invoice file and create a Draft VendorInvoice.

    Returns the new draft's id plus the raw extraction and any warnings, so
    the UI can open the draft for review. Raises ``AIRefused`` when the
    capability is off and ``ValueError`` on a bad file / unparseable reply.
    """
    tenant, setting = get_extraction_setting()

    raw = uploaded_file.read()
    if not raw:
        raise ValueError("The uploaded file is empty.")
    if len(raw) > MAX_FILE_BYTES:
        raise ValueError("File is larger than the 15 MB limit.")

    content_type = getattr(uploaded_file, "content_type", "") or ""
    filename = getattr(uploaded_file, "name", "") or "scan"
    images = file_to_image_data_urls(raw, content_type, filename)

    result = call_model(
        tenant=tenant,
        setting=setting,
        prompt=EXTRACTION_PROMPT,
        system=EXTRACTION_SYSTEM,
        images=images,
        max_tokens=1500,
        subject={"kind": "vendor_invoice_scan", "pages": len(images)},
    )
    extracted = parse_extraction(result.text)
    invoice, warnings = _build_draft(extracted, raw, filename)

    return {
        "invoice_id": invoice.id,
        "invoice_number": invoice.invoice_number,
        "matched_vendor": invoice.vendor.name if invoice.vendor_id else None,
        "extracted": extracted,
        "warnings": warnings,
        "ai": {
            "model_id": result.model_id,
            "cost_usd": str(result.cost_usd),
            "call_id": result.call_id,
            "pages": len(images),
        },
    }


def _build_draft(extracted: dict, raw: bytes, filename: str):
    from accounting.models.gl import Currency
    from accounting.models.receivables import VendorInvoice
    from procurement.models import Vendor

    warnings: list[str] = []

    subtotal = _to_decimal(extracted.get("subtotal")) or Decimal("0")
    tax = _to_decimal(extracted.get("tax_amount")) or Decimal("0")
    total = _to_decimal(extracted.get("total_amount"))
    if total is None:
        total = subtotal + tax
    inv_date = _to_date(extracted.get("invoice_date")) or date.today()
    due_date = _to_date(extracted.get("due_date")) or inv_date

    vendor = None
    vname = (extracted.get("vendor_name") or "").strip()
    if vname:
        vendor = (
            Vendor.objects.filter(name__iexact=vname).first()
            or Vendor.objects.filter(name__icontains=vname).first()
        )
        if vendor is None:
            warnings.append(f"Supplier “{vname}” was not found — pick the supplier on the draft.")

    currency = None
    ccode = (extracted.get("currency_code") or "").strip().upper()
    if ccode:
        currency = Currency.objects.filter(code__iexact=ccode).first()

    lines = extracted.get("line_items") or []
    if isinstance(lines, list) and lines:
        desc = "; ".join(
            str(li.get("description")) for li in lines
            if isinstance(li, dict) and li.get("description")
        )[:2000]
    else:
        desc = f"Scanned invoice{f' from {vname}' if vname else ''}"

    invoice = VendorInvoice(
        invoice_number=(extracted.get("invoice_number") or "").strip()[:50],
        reference=(extracted.get("reference") or "").strip()[:100],
        description=desc,
        vendor=vendor,
        invoice_date=inv_date,
        due_date=due_date,
        subtotal=subtotal,
        tax_amount=tax,
        total_amount=total if total and total > 0 else Decimal("0"),
        currency=currency,
        status="Draft",
    )
    # Keep the scanned document as the invoice's attachment for the audit trail.
    try:
        invoice.attachment.save(filename, ContentFile(raw), save=False)
    except Exception:
        pass
    invoice.save()

    if not total or total <= 0:
        warnings.append("No total amount was read — enter it on the draft before posting.")
    return invoice, warnings
