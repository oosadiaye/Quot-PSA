"""
PV Factory
==========
Centralised factory for creating draft :class:`PaymentVoucherGov`
records from upstream "thing-being-paid" documents (vendor invoices,
contract IPCs, etc.).

The pattern: upstream caller hands us a source document; we denormalise
its key fields (amount, payee, GL/MDA classification) onto a fresh PV
in DRAFT status so the operator can review/edit/approve in the PV
detail page. Idempotency is handled per source — re-calling for the
same source returns the existing draft instead of creating a duplicate.

Why a separate module: keeps :mod:`contracts.services.ipc_service`
pure (it owns the IPC lifecycle, not PV creation), and lets future
upstream documents (e.g. utility bills, recurring contracts) reuse the
same factory without circular deps.
"""
from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from django.db import transaction

if TYPE_CHECKING:
    from accounting.models.receivables import VendorInvoice
    from accounting.models.treasury import PaymentVoucherGov
    from contracts.models.payment import MobilizationPayment
    from django.contrib.auth.models import AbstractUser


class PVFactoryError(Exception):
    """Raised when the source document cannot produce a draft PV."""


@transaction.atomic
def create_draft_voucher_from_invoice(
    *,
    invoice: "VendorInvoice",
    actor: "AbstractUser",
    notes: str = "",
) -> "PaymentVoucherGov":
    """Create (or fetch existing) draft PaymentVoucherGov for a vendor invoice.

    Pre-fills:
      • payee_*       ← invoice.vendor (vendor master)
      • gross_amount  ← invoice.balance_due (handles partial payments)
      • narration     ← "Payment for invoice <num> (<vendor>)"
      • source_document / invoice_number ← invoice number
      • invoice_date  ← invoice.invoice_date
      • ncoa_code     ← first active NCoACode (placeholder; operator
                        adjusts before approval — VendorInvoice's
                        ``account`` FK is a normal Account, not an
                        NCoACode, so there's no direct mapping)
      • tsa_account   ← first active TSA
      • status        ← DRAFT

    Idempotent: if a PV already references this invoice's number, that
    PV is returned unchanged. Safe to retry on network failure.

    Raises:
      PVFactoryError — when prerequisites missing (vendor, TSA, NCoA).
    """
    from accounting.models.gl import TransactionSequence
    from accounting.models.ncoa import NCoACode
    from accounting.models.treasury import PaymentVoucherGov, TreasuryAccount

    if not invoice.vendor_id:
        raise PVFactoryError(
            "Invoice has no vendor — set the vendor before creating a "
            "Payment Voucher."
        )

    # Idempotency: existing PV for the same invoice_number wins.
    existing = (
        PaymentVoucherGov.objects
        .filter(invoice_number=invoice.invoice_number)
        .order_by("-id")
        .first()
    )
    if existing is not None:
        return existing

    tsa = TreasuryAccount.objects.filter(is_active=True).first()
    if tsa is None:
        raise PVFactoryError(
            "No active Treasury Account configured. Configure a TSA "
            "before raising vouchers."
        )

    # ── MDA-aware NCoA selection ───────────────────────────────────────
    # The invoice carries a legacy ``accounting.MDA`` FK. We bridge it
    # to the NCoA world through ``AdministrativeSegment.legacy_mda``
    # (OneToOne) and pick the first active NCoACode whose
    # ``administrative`` matches. This makes the draft PV inherit the
    # invoice's MDA classification automatically — operators no longer
    # have to reselect it. If no matching NCoACode exists yet (e.g.,
    # the bridge hasn't been seeded for that MDA), we fall back to the
    # first active NCoACode and the operator can refine on the PV
    # detail page; the failure mode is recoverable, not blocking.
    ncoa = None
    legacy_mda_id = getattr(invoice, "mda_id", None)
    if legacy_mda_id:
        ncoa = (
            NCoACode.objects
            .filter(
                is_active=True,
                administrative__legacy_mda_id=legacy_mda_id,
            )
            .select_related("administrative")
            .order_by("id")
            .first()
        )
    if ncoa is None:
        ncoa = NCoACode.objects.filter(is_active=True).first()
    if ncoa is None:
        raise PVFactoryError(
            "No active NCoA codes configured. Seed the chart of "
            "accounts before raising vouchers."
        )

    vendor = invoice.vendor
    voucher_number = TransactionSequence.get_next(
        "payment_voucher", prefix="PV-",
    )

    balance_due = invoice.balance_due
    if balance_due is None or Decimal(balance_due) <= 0:
        # Fall back to total_amount when balance_due is zero/None — a
        # zero-balance invoice still needs a voucher in some workflows
        # (e.g. recording a $0 retainer adjustment); the operator can
        # set the gross to the right number on the PV form.
        balance_due = invoice.total_amount or Decimal("0")

    # Build a narration that surfaces the MDA — useful for treasury
    # operators scanning the PV list to know which ministry owns the
    # spend without having to drill into each row's NCoA segments.
    mda_name = ""
    if getattr(invoice, "mda", None) is not None:
        mda_name = getattr(invoice.mda, "name", "") or ""

    base_narration = (
        f"Payment for invoice {invoice.invoice_number} "
        f"({getattr(vendor, 'name', 'vendor')})"
    )
    if mda_name:
        base_narration = f"[{mda_name}] {base_narration}"
    narration = (notes or base_narration)[:500]

    pv = PaymentVoucherGov.objects.create(
        voucher_number=voucher_number,
        payment_type="VENDOR",
        ncoa_code=ncoa,
        appropriation=None,
        payee_name=getattr(vendor, "name", "") or invoice.invoice_number,
        payee_account=getattr(vendor, "bank_account_number", "") or "",
        payee_bank=getattr(vendor, "bank_name", "") or "",
        gross_amount=balance_due,
        wht_amount=Decimal("0"),
        narration=narration,
        tsa_account=tsa,
        source_document=invoice.invoice_number or "",
        invoice_number=invoice.invoice_number or "",
        invoice_date=invoice.invoice_date,
        status="DRAFT",
        created_by=actor,
        updated_by=actor,
    )
    return pv


@transaction.atomic
def create_draft_voucher_from_mobilization(
    *,
    payment: "MobilizationPayment",
    actor: "AbstractUser",
    notes: str = "",
) -> "PaymentVoucherGov":
    """Create (or fetch existing) draft PaymentVoucherGov for a
    mobilisation advance.

    Pre-fills:
      • payee_*       ← contract.vendor (vendor master)
      • gross_amount  ← payment.amount (advance amount, no deductions)
      • narration     ← "Mobilisation advance — <contract> (<vendor>)"
      • source_document ← contract number + " — Mobilisation"
      • ncoa_code     ← contract.ncoa_code (the contract's own NCoA
                        line, not a placeholder — mobilisation hits
                        the same appropriation as the contract itself)
      • appropriation ← payment_voucher reuses contract.appropriation
      • tsa_account   ← first active TSA (operator can change)
      • status        ← DRAFT
      • wht_amount    ← 0 (mobilisation advances are not subject to
                          withholding — that hits the IPCs that claw
                          the advance back, not the advance itself)

    Idempotent: if ``payment.payment_voucher`` is already set, that
    PV is returned unchanged. Safe to retry on network failure or
    operator double-click.

    Raises:
      PVFactoryError — when prerequisites missing (vendor, TSA, NCoA).
    """
    from accounting.models.gl import TransactionSequence
    from accounting.models.treasury import PaymentVoucherGov, TreasuryAccount

    # Idempotency: existing PV linkage wins.
    if payment.payment_voucher_id:
        return payment.payment_voucher

    contract = payment.contract
    if not contract.vendor_id:
        raise PVFactoryError(
            "Contract has no vendor — set the vendor before scheduling "
            "the mobilisation advance for payment."
        )
    if not contract.ncoa_code_id:
        raise PVFactoryError(
            "Contract has no NCoA classification — assign segments "
            "before scheduling mobilisation."
        )

    tsa = TreasuryAccount.objects.filter(is_active=True).first()
    if tsa is None:
        raise PVFactoryError(
            "No active Treasury Account configured. Configure a TSA "
            "before scheduling mobilisation."
        )

    vendor = contract.vendor
    voucher_number = TransactionSequence.get_next(
        "payment_voucher", prefix="PV-",
    )

    base_narration = (
        f"Mobilisation advance — {contract.contract_number or contract.pk} "
        f"({getattr(vendor, 'name', 'vendor')})"
    )
    narration = (notes or base_narration)[:500]

    # ``payment.reference_number`` (e.g. ``MOB-DSG/WORKS/2026/003``) is
    # the canonical cross-document idempotency key. We write it to the
    # PV's ``source_document`` field so a duplicate-detection query
    # (``filter(source_document=payment.reference_number)``) can find
    # this PV later — e.g. if the link on MobilizationPayment is lost
    # to a data-fix mistake, this gives us a recovery path.
    pv = PaymentVoucherGov.objects.create(
        voucher_number=voucher_number,
        # A mobilisation IS a supplier advance against the contract, so
        # it must be tagged as one — ``payment_type='ADVANCE'`` +
        # ``special_gl_indicator='A'`` + the ``vendor`` FK. This is the
        # exact triple ``ensure_draft_payment_for_pv`` checks to route
        # the draft Payment down the Special-GL advance path
        # (DR Vendor-Advance recon / CR Bank, no invoice allocation),
        # so mobilisation now rides the SAME central pipeline as a manual
        # vendor advance rather than a bespoke bypass.
        payment_type="ADVANCE",
        special_gl_indicator="A",
        vendor=vendor,
        ncoa_code=contract.ncoa_code,
        # The contract may not have an Appropriation FK populated
        # (it's optional on the model); leaving None lets the
        # treasury workflow's appropriation lookup pick the right
        # one at posting time via NCoA + fiscal year.
        appropriation=getattr(contract, "appropriation", None),
        payee_name=getattr(vendor, "name", "") or "",
        payee_account=getattr(vendor, "bank_account_number", "") or "",
        payee_bank=getattr(vendor, "bank_name", "") or "",
        gross_amount=payment.amount,
        wht_amount=Decimal("0"),
        net_amount=payment.amount,
        narration=narration,
        tsa_account=tsa,
        source_document=payment.reference_number,
        status="DRAFT",
        created_by=actor,
        updated_by=actor,
    )
    return pv


def _resolve_advance_deductions(gross: Decimal, deductions) -> list[dict]:
    """Validate + server-derive the deduction lines for a vendor advance.

    SECURITY: never trust a client-supplied ``gl_account`` or ``amount``.
    Each incoming line must reference a trusted master record — a
    ``WithholdingTax`` or a ``PaymentDeductionCode`` — and the GL account,
    rate and amount are derived from that record here, server-side. This
    stops an authenticated caller from diverting an advance by naming an
    arbitrary GL (e.g. cash/suspense/control) on a fake "deduction".

    Returns kwargs dicts ready for ``PaymentVoucherDeduction.objects.create``.
    Zero-amount lines (e.g. abolished 0% stamp duty) are dropped. Raises
    ``PVFactoryError`` (→ 400 in the view) for any unknown/misconfigured
    record or when the deduction total is not below the gross advance.
    """
    from accounting.models import WithholdingTax
    from accounting.models.tax import PaymentDeductionCode
    from core.models import quantize_currency

    HUNDRED = Decimal('100')
    resolved: list[dict] = []
    total = Decimal('0')
    for d in (deductions or []):
        wht_id = d.get('withholding_tax')
        code_id = d.get('deduction_code')
        if wht_id:
            wht = WithholdingTax.objects.filter(pk=wht_id, is_active=True).first()
            if wht is None:
                raise PVFactoryError(
                    "A deduction references an unknown or inactive withholding-tax code."
                )
            if wht.withholding_account_id is None:
                raise PVFactoryError(
                    f"Withholding-tax code {wht.code} has no GL account configured."
                )
            rate = wht.rate or Decimal('0')
            amount = quantize_currency(gross * rate / HUNDRED)
            row = dict(
                deduction_type='WHT', description=f"{wht.code} {wht.name}"[:200],
                withholding_tax=wht, deduction_code=None, rate=rate,
                gl_account=wht.withholding_account,
            )
        elif code_id:
            code = PaymentDeductionCode.objects.filter(pk=code_id, is_active=True).first()
            if code is None:
                raise PVFactoryError(
                    "A deduction references an unknown or inactive deduction code."
                )
            if code.gl_account_id is None:
                raise PVFactoryError(
                    f"Deduction code {code.code} has no GL account configured."
                )
            if code.calculation_method == 'fixed':
                rate = Decimal('0')
                amount = quantize_currency(code.fixed_amount or Decimal('0'))
            else:
                rate = code.rate or Decimal('0')
                amount = quantize_currency(gross * rate / HUNDRED)
            row = dict(
                deduction_type=code.deduction_type,
                description=f"{code.code} {code.name}"[:200],
                withholding_tax=None, deduction_code=code, rate=rate,
                gl_account=code.gl_account,
            )
        else:
            raise PVFactoryError(
                "Each deduction must reference a withholding-tax or deduction code."
            )
        if amount <= 0:
            continue  # nothing to withhold (e.g. a 0% code) — drop the line
        row['amount'] = amount
        total += amount
        resolved.append(row)

    if total >= gross:
        raise PVFactoryError(
            f"Total deductions ({total}) must be less than the advance amount ({gross})."
        )
    return resolved


@transaction.atomic
def create_draft_voucher_from_advance(
    *,
    vendor,
    amount,
    admin_code: str,
    economic_code: str,
    functional_code: str,
    programme_code: str,
    fund_code: str,
    geo_code: str,
    purpose: str = "",
    reference: str = "",
    due_date=None,
    actor=None,
    deductions=None,
) -> "PaymentVoucherGov":
    """Create a DRAFT PaymentVoucherGov for a vendor down payment.

    The operator supplies the vendor, amount and the full NCoA budget line —
    MDA at the header plus the line item's G/L, fund, functional, geographic
    and programme segments. We resolve the composite NCoA, **budget-check** the
    resulting appropriation (the advance is reserved against the expenditure
    line), and materialise a draft PV. At payment the advance disburses to the
    vendor-advances recon under special G/L "A"; the expense books later when
    the advance clears against the vendor's invoice.

    Raises PVFactoryError for missing prerequisites (TSA, fiscal year, invalid
    segments), and lets budget.services.BudgetExceededError propagate so the
    caller can report a budget shortfall.
    """
    from accounting.models.gl import TransactionSequence
    from accounting.models.treasury import PaymentVoucherGov, TreasuryAccount
    from accounting.models.advanced import FiscalYear
    from accounting.services.ncoa_service import NCoAService, NCoAResolutionError
    from budget.services import BudgetValidationService
    from budget.models import Appropriation

    tsa = TreasuryAccount.objects.filter(is_active=True).first()
    if tsa is None:
        raise PVFactoryError(
            "No active Treasury Account configured. Set up a TSA before "
            "requesting a down payment."
        )

    amount = Decimal(str(amount))

    # Resolve the composite NCoA from the six segments the operator chose.
    try:
        ncoa = NCoAService.resolve_code(
            admin_code=admin_code,
            economic_code=economic_code,
            functional_code=functional_code,
            programme_code=programme_code,
            fund_code=fund_code,
            geo_code=geo_code,
        )
    except NCoAResolutionError as e:
        raise PVFactoryError(f"Invalid budget line: {e}")

    # Budget-line check — reserve the advance against the expenditure line.
    fy = FiscalYear.objects.filter(is_active=True).first()
    if fy is None:
        raise PVFactoryError(
            "No active fiscal year configured — cannot budget-check the advance."
        )
    # Raises BudgetExceededError (→ 400 in the view) when the line has no
    # appropriation or insufficient balance for the amount.
    result = BudgetValidationService.validate_expenditure(
        administrative_id=ncoa.administrative_id,
        economic_id=ncoa.economic_id,
        fund_id=ncoa.fund_id,
        fiscal_year_id=fy.id,
        amount=amount,
        functional_id=ncoa.functional_id,
        programme_id=ncoa.programme_id,
    )
    appropriation = Appropriation.objects.filter(
        pk=result.get('appropriation_id'),
    ).first()

    vendor_name = getattr(vendor, 'name', '') or ''
    narration = (
        f"Vendor down payment — {vendor_name}"
        + (f" ({purpose})" if purpose else "")
    )[:500]
    source = (reference or f"DP/{getattr(vendor, 'code', '') or vendor.pk}")[:100]

    pv = PaymentVoucherGov.objects.create(
        voucher_number=TransactionSequence.get_next('payment_voucher', prefix='PV-'),
        payment_type="ADVANCE",
        ncoa_code=ncoa,
        appropriation=appropriation,  # budget line the advance is checked against
        vendor=vendor,                # links the special-GL advance to the vendor
        special_gl_indicator="A",     # SAP special G/L "A" — down payment
        payee_name=vendor_name[:200],
        payee_account="",
        payee_bank="",
        gross_amount=amount,
        wht_amount=Decimal("0"),
        net_amount=amount,
        narration=narration,
        tsa_account=tsa,
        source_document=source,
        invoice_date=due_date,        # down-payment due date
        status="DRAFT",
        created_by=actor,
    )

    # Deduction lines added at creation (e.g. WHT). The GL/rate/amount are
    # derived server-side from the referenced master record (never the raw
    # client payload — see _resolve_advance_deductions) and applied when the
    # advance disburses at payment.
    resolved_deductions = _resolve_advance_deductions(amount, deductions)
    if resolved_deductions:
        from accounting.models.treasury import PaymentVoucherDeduction
        for row in resolved_deductions:
            PaymentVoucherDeduction.objects.create(payment_voucher=pv, **row)
        pv.save()  # refresh net_amount from the new deduction set

    return pv
