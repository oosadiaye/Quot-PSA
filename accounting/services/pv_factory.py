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
        payment_type="VENDOR",
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
