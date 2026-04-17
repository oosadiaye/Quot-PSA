"""
Statutory XML export + XSD validation.

Provides a single validator entry point used by:
  * FIRS WHT monthly return (XSD: ``accounting/schemas/firs_wht.xsd``)
  * FIRS VAT monthly return (XSD: ``accounting/schemas/firs_vat.xsd``)
  * PENCOM pension schedule (XSD: ``accounting/schemas/pencom_pension.xsd``)

The validator is optional — it only runs if the ``lxml`` package is
installed. Without lxml the service still produces XML but skips the
schema check and emits a warning through ``ValidationResult.warnings``.
This keeps the dev/CI footprint small while allowing production
deployments to pin ``lxml`` and enforce schema compliance.

All validators return a :class:`ValidationResult` dataclass — the
exporters never raise on malformed output so callers can always see
the full error report (not just the first XSD violation).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET


SCHEMA_DIR = Path(__file__).resolve().parent.parent / 'schemas'


# ---------------------------------------------------------------------------
# Validation result
# ---------------------------------------------------------------------------
@dataclass
class ValidationResult:
    is_valid: bool
    schema_path: str = ''
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def assert_valid(self) -> None:
        if not self.is_valid:
            raise XSDValidationError(
                f'XML failed schema validation against {self.schema_path}: '
                + '; '.join(self.errors[:5])
            )


class XSDValidationError(Exception):
    """Raised by ``ValidationResult.assert_valid`` when XML violates schema."""


def validate_xml(xml_bytes: bytes, schema_filename: str) -> ValidationResult:
    """Validate ``xml_bytes`` against ``accounting/schemas/<schema_filename>``.

    Returns a :class:`ValidationResult` — never raises on schema
    failure (the caller can decide to raise via ``assert_valid()``).
    """
    schema_path = SCHEMA_DIR / schema_filename
    if not schema_path.exists():
        return ValidationResult(
            is_valid=False,
            schema_path=str(schema_path),
            errors=[f'Schema file not found: {schema_path}'],
        )

    # Well-formedness check — done without lxml so it always runs.
    try:
        ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        return ValidationResult(
            is_valid=False,
            schema_path=str(schema_path),
            errors=[f'XML is not well-formed: {exc}'],
        )

    # Optional XSD validation via lxml.
    try:
        from lxml import etree as lxml_etree
    except ImportError:
        return ValidationResult(
            is_valid=True,            # well-formedness passed
            schema_path=str(schema_path),
            warnings=[
                'lxml not installed — XSD validation skipped. '
                'Install "lxml>=5.0" in production.'
            ],
        )

    try:
        with schema_path.open('rb') as fp:
            schema_doc = lxml_etree.XML(fp.read())
        schema = lxml_etree.XMLSchema(schema_doc)
    except lxml_etree.XMLSchemaParseError as exc:
        return ValidationResult(
            is_valid=False,
            schema_path=str(schema_path),
            errors=[f'Schema itself is malformed: {exc}'],
        )

    try:
        xml_doc = lxml_etree.fromstring(xml_bytes)
    except lxml_etree.XMLSyntaxError as exc:
        return ValidationResult(
            is_valid=False,
            schema_path=str(schema_path),
            errors=[f'XML parse failed under lxml: {exc}'],
        )

    if schema.validate(xml_doc):
        return ValidationResult(is_valid=True, schema_path=str(schema_path))

    errs = [str(e) for e in schema.error_log]
    return ValidationResult(
        is_valid=False,
        schema_path=str(schema_path),
        errors=errs,
    )


# ---------------------------------------------------------------------------
# FIRS WHT exporter
# ---------------------------------------------------------------------------
@dataclass
class WHTLine:
    payee_name: str
    payee_tin: str | None
    payee_type: str        # COMPANY | INDIVIDUAL | PARTNERSHIP
    invoice_number: str
    invoice_date: str      # YYYY-MM-DD
    gross_amount: Decimal
    wht_rate: Decimal
    wht_amount: Decimal
    nature_of_payment: str # CONTRACT | RENT | ...


def build_firs_wht_xml(
    *,
    taxpayer_tin: str,
    taxpayer_name: str,
    year: int,
    month: int,
    return_type: str,
    prepared_by: str,
    prepared_at_iso: str,
    lines: Iterable[WHTLine],
) -> bytes:
    """Return a FIRS WHT return as UTF-8 XML bytes.

    Caller is responsible for preparing lines (from WithholdingTax /
    PaymentVoucherGov records). This function just serialises — no DB
    access — which makes it trivially unit-testable.
    """
    root = ET.Element('WHTReturn')

    header = ET.SubElement(root, 'Header')
    ET.SubElement(header, 'TaxpayerTIN').text = taxpayer_tin
    ET.SubElement(header, 'TaxpayerName').text = taxpayer_name
    ET.SubElement(header, 'PeriodYear').text = f'{year:04d}'
    ET.SubElement(header, 'PeriodMonth').text = str(month)
    ET.SubElement(header, 'ReturnType').text = return_type
    ET.SubElement(header, 'PreparedBy').text = prepared_by
    ET.SubElement(header, 'PreparedAt').text = prepared_at_iso

    line_list = list(lines)
    total_gross = sum((ln.gross_amount for ln in line_list), Decimal('0'))
    total_wht = sum((ln.wht_amount for ln in line_list), Decimal('0'))

    summary = ET.SubElement(root, 'Summary')
    ET.SubElement(summary, 'LineCount').text = str(len(line_list))
    ET.SubElement(summary, 'TotalGross').text = _fmt_amount(total_gross)
    ET.SubElement(summary, 'TotalWHT').text = _fmt_amount(total_wht)

    lines_el = ET.SubElement(root, 'Lines')
    for ln in line_list:
        le = ET.SubElement(lines_el, 'Line')
        ET.SubElement(le, 'PayeeName').text = ln.payee_name
        if ln.payee_tin:
            ET.SubElement(le, 'PayeeTIN').text = ln.payee_tin
        ET.SubElement(le, 'PayeeType').text = ln.payee_type
        ET.SubElement(le, 'InvoiceNumber').text = ln.invoice_number
        ET.SubElement(le, 'InvoiceDate').text = ln.invoice_date
        ET.SubElement(le, 'GrossAmount').text = _fmt_amount(ln.gross_amount)
        ET.SubElement(le, 'WHTRate').text = _fmt_rate(ln.wht_rate)
        ET.SubElement(le, 'WHTAmount').text = _fmt_amount(ln.wht_amount)
        ET.SubElement(le, 'NatureOfPayment').text = ln.nature_of_payment

    return _serialise(root)


# ---------------------------------------------------------------------------
# FIRS VAT exporter
# ---------------------------------------------------------------------------
def build_firs_vat_xml(
    *,
    taxpayer_tin: str,
    taxpayer_name: str,
    year: int,
    month: int,
    return_type: str,
    output_standard: Decimal,
    output_zero: Decimal,
    output_exempt: Decimal,
    output_vat_collected: Decimal,
    input_standard: Decimal,
    input_zero: Decimal,
    input_exempt: Decimal,
    input_vat_paid: Decimal,
    vat_credit_b_f: Decimal = Decimal('0'),
) -> bytes:
    """Return a FIRS VAT monthly return as UTF-8 XML bytes."""
    root = ET.Element('VATReturn')

    header = ET.SubElement(root, 'Header')
    ET.SubElement(header, 'TaxpayerTIN').text = taxpayer_tin
    ET.SubElement(header, 'TaxpayerName').text = taxpayer_name
    ET.SubElement(header, 'PeriodYear').text = f'{year:04d}'
    ET.SubElement(header, 'PeriodMonth').text = str(month)
    ET.SubElement(header, 'ReturnType').text = return_type

    outs = ET.SubElement(root, 'Outputs')
    ET.SubElement(outs, 'StandardRated').text = _fmt_amount(output_standard)
    ET.SubElement(outs, 'ZeroRated').text = _fmt_amount(output_zero)
    ET.SubElement(outs, 'Exempt').text = _fmt_amount(output_exempt)
    ET.SubElement(outs, 'VATCollected').text = _fmt_amount(output_vat_collected)

    ins = ET.SubElement(root, 'Inputs')
    ET.SubElement(ins, 'StandardRated').text = _fmt_amount(input_standard)
    ET.SubElement(ins, 'ZeroRated').text = _fmt_amount(input_zero)
    ET.SubElement(ins, 'Exempt').text = _fmt_amount(input_exempt)
    ET.SubElement(ins, 'VATPaid').text = _fmt_amount(input_vat_paid)

    comp = ET.SubElement(root, 'Computation')
    ET.SubElement(comp, 'OutputVAT').text = _fmt_amount(output_vat_collected)
    ET.SubElement(comp, 'InputVAT').text = _fmt_amount(input_vat_paid)
    # Payable may be negative when input > output → refund position.
    payable = output_vat_collected - input_vat_paid - vat_credit_b_f
    ET.SubElement(comp, 'VATPayable').text = _fmt_amount_signed(payable)
    if vat_credit_b_f:
        ET.SubElement(comp, 'VATCredit').text = _fmt_amount(vat_credit_b_f)

    return _serialise(root)


# ---------------------------------------------------------------------------
# PENCOM pension schedule exporter
# ---------------------------------------------------------------------------
@dataclass
class PENCOMContribution:
    employee_pin: str       # PenCom PIN (11 digits)
    surname: str
    first_name: str
    other_names: str
    date_of_birth: str      # YYYY-MM-DD
    employer_contribution: Decimal
    employee_contribution: Decimal
    month: int
    year: int


def build_pencom_schedule_xml(
    *,
    employer_rc_number: str,
    employer_name: str,
    pfa_code: str,
    period_year: int,
    period_month: int,
    rows: Iterable[PENCOMContribution],
) -> bytes:
    """Build a PENCOM pension remittance schedule XML."""
    rows_list = list(rows)
    root = ET.Element('PencomSchedule')

    header = ET.SubElement(root, 'Header')
    ET.SubElement(header, 'EmployerRC').text = employer_rc_number
    ET.SubElement(header, 'EmployerName').text = employer_name
    ET.SubElement(header, 'PFACode').text = pfa_code
    ET.SubElement(header, 'PeriodYear').text = f'{period_year:04d}'
    ET.SubElement(header, 'PeriodMonth').text = str(period_month)
    ET.SubElement(header, 'EmployeeCount').text = str(len(rows_list))

    total_er = sum((r.employer_contribution for r in rows_list), Decimal('0'))
    total_ee = sum((r.employee_contribution for r in rows_list), Decimal('0'))

    summary = ET.SubElement(root, 'Summary')
    ET.SubElement(summary, 'TotalEmployer').text = _fmt_amount(total_er)
    ET.SubElement(summary, 'TotalEmployee').text = _fmt_amount(total_ee)
    ET.SubElement(summary, 'GrandTotal').text = _fmt_amount(total_er + total_ee)

    contributions = ET.SubElement(root, 'Contributions')
    for r in rows_list:
        c = ET.SubElement(contributions, 'Contribution')
        ET.SubElement(c, 'PIN').text = r.employee_pin
        ET.SubElement(c, 'Surname').text = r.surname
        ET.SubElement(c, 'FirstName').text = r.first_name
        if r.other_names:
            ET.SubElement(c, 'OtherNames').text = r.other_names
        ET.SubElement(c, 'DateOfBirth').text = r.date_of_birth
        ET.SubElement(c, 'EmployerContribution').text = _fmt_amount(r.employer_contribution)
        ET.SubElement(c, 'EmployeeContribution').text = _fmt_amount(r.employee_contribution)

    return _serialise(root)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _fmt_amount(v: Decimal | int | float) -> str:
    return f'{Decimal(str(v)):.2f}'


def _fmt_amount_signed(v: Decimal | int | float) -> str:
    # VATPayable is the only field that legitimately goes negative.
    return f'{Decimal(str(v)):.2f}'


def _fmt_rate(v: Decimal | int | float) -> str:
    # e.g. 10.00, 5.00
    return f'{Decimal(str(v)):.2f}'


def _serialise(root: ET.Element) -> bytes:
    ET.indent(root, space='  ')
    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding='utf-8')
