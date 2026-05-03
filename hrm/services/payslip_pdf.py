"""Payslip PDF renderer.

Generates a branded, A4 PDF payslip from a :class:`PayrollLine` using
WeasyPrint.  The layout mirrors the SuperAdmin email-template gradient
(``#242a88 → #2e35a0``) so every employee-facing document speaks the
same visual language.
"""
from __future__ import annotations

import io
import logging
from decimal import Decimal
from typing import Any

from django.template import Context, Template

from hrm.models import PayrollLine

logger = logging.getLogger(__name__)

# Brand tokens mirrored from superadmin/email_rendering.py
BRAND_PRIMARY = "#242a88"
BRAND_PRIMARY_ALT = "#2e35a0"

_TEMPLATE = Template(
    """
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Payslip - {{ employee_number }} - {{ period_label }}</title>
  <style>
    @page {
      size: A4;
      margin: 18mm 14mm;
    }
    body {
      font-family: "Helvetica", "Arial", sans-serif;
      color: #0f172a;
      font-size: 11pt;
      margin: 0;
      padding: 0;
    }
    .header {
      background: linear-gradient(135deg, {{ brand_primary }} 0%, {{ brand_primary_alt }} 100%);
      color: #ffffff;
      padding: 18pt 20pt;
      border-radius: 6pt;
    }
    .header h1 {
      margin: 0;
      font-size: 18pt;
      letter-spacing: 0.4pt;
    }
    .header .sub {
      margin-top: 3pt;
      font-size: 10pt;
      opacity: 0.85;
    }
    .meta {
      margin-top: 16pt;
      width: 100%;
      border-collapse: collapse;
    }
    .meta td {
      padding: 4pt 6pt;
      vertical-align: top;
    }
    .meta .label {
      color: #64748b;
      font-size: 9.5pt;
      text-transform: uppercase;
      letter-spacing: 0.3pt;
      width: 35%;
    }
    .meta .value {
      font-weight: 600;
    }
    .section-title {
      margin-top: 18pt;
      margin-bottom: 4pt;
      font-size: 11pt;
      font-weight: 700;
      color: {{ brand_primary }};
      text-transform: uppercase;
      letter-spacing: 0.4pt;
      border-bottom: 1.2pt solid {{ brand_primary }};
      padding-bottom: 3pt;
    }
    table.lines {
      width: 100%;
      border-collapse: collapse;
      margin-top: 6pt;
    }
    table.lines th,
    table.lines td {
      padding: 6pt 8pt;
      font-size: 10.5pt;
      border-bottom: 0.5pt solid #e2e8f0;
    }
    table.lines th {
      text-align: left;
      background: #f8fafc;
      color: #475569;
      text-transform: uppercase;
      font-size: 9pt;
      letter-spacing: 0.3pt;
    }
    table.lines td.amount,
    table.lines th.amount {
      text-align: right;
      font-variant-numeric: tabular-nums;
    }
    .totals {
      margin-top: 14pt;
      width: 100%;
      border-collapse: collapse;
    }
    .totals td {
      padding: 6pt 8pt;
      font-size: 11pt;
    }
    .totals td.label {
      color: #475569;
      text-align: right;
      width: 70%;
    }
    .totals td.value {
      text-align: right;
      font-weight: 700;
      font-variant-numeric: tabular-nums;
    }
    .net {
      background: {{ brand_primary }};
      color: #ffffff;
      border-radius: 6pt;
    }
    .net td {
      font-size: 13pt;
      font-weight: 700;
    }
    .footer {
      margin-top: 22pt;
      padding-top: 8pt;
      border-top: 0.5pt solid #e2e8f0;
      font-size: 9pt;
      color: #94a3b8;
      text-align: center;
    }
  </style>
</head>
<body>
  <div class="header">
    <h1>{{ organization_name }}</h1>
    <div class="sub">Payslip &middot; {{ period_label }}</div>
  </div>

  <table class="meta">
    <tr>
      <td class="label">Employee</td>
      <td class="value">{{ employee_name }} ({{ employee_number }})</td>
      <td class="label">Department</td>
      <td class="value">{{ department }}</td>
    </tr>
    <tr>
      <td class="label">Position</td>
      <td class="value">{{ position }}</td>
      <td class="label">Payment Date</td>
      <td class="value">{{ payment_date }}</td>
    </tr>
    <tr>
      <td class="label">Bank</td>
      <td class="value">{{ bank_name }}</td>
      <td class="label">Account</td>
      <td class="value">{{ bank_account_masked }}</td>
    </tr>
  </table>

  <div class="section-title">Earnings</div>
  <table class="lines">
    <thead>
      <tr><th>Component</th><th class="amount">Amount</th></tr>
    </thead>
    <tbody>
      <tr><td>Basic Salary</td><td class="amount">{{ basic_salary }}</td></tr>
      {% for row in earnings %}
      <tr><td>{{ row.name }}</td><td class="amount">{{ row.amount }}</td></tr>
      {% endfor %}
      {% if overtime_amount_display %}
      <tr><td>Overtime ({{ overtime_hours }} hrs)</td><td class="amount">{{ overtime_amount_display }}</td></tr>
      {% endif %}
    </tbody>
  </table>

  <div class="section-title">Deductions</div>
  <table class="lines">
    <thead>
      <tr><th>Component</th><th class="amount">Amount</th></tr>
    </thead>
    <tbody>
      <tr><td>PAYE Tax</td><td class="amount">{{ tax_deduction }}</td></tr>
      <tr><td>Pension</td><td class="amount">{{ pension_deduction }}</td></tr>
      {% for row in deductions %}
      <tr><td>{{ row.name }}</td><td class="amount">{{ row.amount }}</td></tr>
      {% endfor %}
      {% if other_deductions_display %}
      <tr><td>Other Deductions</td><td class="amount">{{ other_deductions_display }}</td></tr>
      {% endif %}
    </tbody>
  </table>

  <table class="totals">
    <tr><td class="label">Gross Salary</td><td class="value">{{ gross_salary }}</td></tr>
    <tr><td class="label">Total Deductions</td><td class="value">{{ total_deductions }}</td></tr>
  </table>

  <table class="totals net">
    <tr><td class="label" style="color:#fff;">Net Pay</td><td class="value" style="color:#fff;">{{ net_salary }}</td></tr>
  </table>

  <div class="footer">
    This is a system-generated payslip. Please retain for your records.
  </div>
</body>
</html>
"""
)


def _fmt(value: Decimal | float | int | None) -> str:
    if value is None:
        return "-"
    try:
        dec = Decimal(value)
    except Exception:
        return str(value)
    return f"{dec:,.2f}"


def _mask_account(account: str) -> str:
    if not account:
        return "-"
    tail = account[-4:]
    return f"****{tail}"


def _build_context(line: PayrollLine, organization_name: str) -> dict[str, Any]:
    employee = line.employee
    period = line.payroll_run.period
    earnings = [
        {"name": row.component.name, "amount": _fmt(row.amount)}
        for row in line.earnings.select_related("component").all()
    ]
    deductions = [
        {"name": row.component.name, "amount": _fmt(row.amount)}
        for row in line.deductions.select_related("component").all()
    ]

    return {
        "brand_primary": BRAND_PRIMARY,
        "brand_primary_alt": BRAND_PRIMARY_ALT,
        "organization_name": organization_name or "Payslip",
        "employee_number": employee.employee_number,
        "employee_name": employee.user.get_full_name() or employee.user.username,
        "department": getattr(employee.department, "name", "-"),
        "position": getattr(employee.position, "title", None) or getattr(employee.position, "name", "-"),
        "period_label": f"{period.start_date.strftime('%b %Y')}",
        "payment_date": period.payment_date.strftime("%d %b %Y") if period.payment_date else "-",
        "bank_name": line.bank_name or getattr(employee, "bank_name", "-") or "-",
        "bank_account_masked": _mask_account(line.bank_account or getattr(employee, "bank_account", "")),
        "basic_salary": _fmt(line.basic_salary),
        "earnings": earnings,
        "deductions": deductions,
        "overtime_hours": _fmt(line.overtime_hours),
        "overtime_amount_display": _fmt(line.overtime_amount) if line.overtime_amount else None,
        "tax_deduction": _fmt(line.tax_deduction),
        "pension_deduction": _fmt(line.pension_deduction),
        "other_deductions_display": _fmt(line.other_deductions) if line.other_deductions else None,
        "gross_salary": _fmt(line.gross_salary),
        "total_deductions": _fmt(line.total_deductions),
        "net_salary": _fmt(line.net_salary),
    }


def render_payslip_html(line: PayrollLine, organization_name: str = "") -> str:
    """Render the payslip HTML (useful for previews)."""
    ctx = _build_context(line, organization_name)
    return _TEMPLATE.render(Context(ctx))


def render_payslip_pdf(line: PayrollLine, organization_name: str = "") -> bytes:
    """Render the payslip as a PDF byte string.

    Raises :class:`RuntimeError` when WeasyPrint cannot import its native
    dependencies (so the caller can surface a friendly error).
    """
    try:
        from weasyprint import HTML  # type: ignore
    except Exception as exc:  # pragma: no cover - import guard
        logger.exception("WeasyPrint import failed")
        raise RuntimeError(
            "PDF renderer unavailable. Please install WeasyPrint and its "
            "native dependencies (pango, cairo)."
        ) from exc

    html = render_payslip_html(line, organization_name=organization_name)
    buffer = io.BytesIO()
    HTML(string=html).write_pdf(target=buffer)
    return buffer.getvalue()
