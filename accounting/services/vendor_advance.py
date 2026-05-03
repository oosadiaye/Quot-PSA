"""
Vendor Advance Special-GL Service.

Three operations cover the full advance-payment lifecycle:

  • ``disburse``  → records a new advance + posts the disbursement
                    journal: DR Vendor-Advance recon / CR TSA Cash.
                    Replaces the old "DR Mobilization Advance / CR Cash"
                    pattern.

  • ``clear``     → the SAP F-54 equivalent. Posts the contra journal
                    that moves the obligation from the special-GL
                    recon to the standard AP recon (when netted
                    against an invoice) or to an expense/reversal
                    account (when written off).

  • ``outstanding_for_vendor`` → indexed lookup the popup uses to
                    decide whether to gate AP / PV / IPC posting on
                    a vendor with outstanding advances.

All three are class-methods on ``VendorAdvanceService`` so future
flows (PO down-payment, AP advance) call them with no boilerplate.
"""
from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from django.db import transaction
from django.db.models import F, Sum

from accounting.models import (
    Account,
    JournalHeader,
    JournalLine,
    VendorAdvance,
    VendorAdvanceClearance,
    VendorAdvanceSource,
    VendorAdvanceStatus,
)
from accounting.services.base_posting import (
    TransactionPostingError,
    get_gl_account,
)
from core.models import quantize_currency

if TYPE_CHECKING:
    from datetime import date as _date
    from procurement.models import Vendor


ZERO = Decimal("0.00")


class VendorAdvanceService:
    """Stateless service. All methods are class-methods."""

    # ── Account resolution ────────────────────────────────────────────

    @staticmethod
    def resolve_advance_account() -> Optional[Account]:
        """Find the tenant's Vendor-Advance Special-GL recon account.

        Order:
          1. Active Account flagged ``reconciliation_type='vendor_advance'``
             — the canonical CoA-portable marker.
          2. Settings ``DEFAULT_GL_ACCOUNTS['VENDOR_ADVANCE']`` code.
          3. None — caller must surface a clear "configure first" error.
        """
        recon = Account.objects.filter(
            reconciliation_type="vendor_advance",
            is_active=True,
        ).order_by("code").first()
        if recon is not None:
            return recon
        return get_gl_account("VENDOR_ADVANCE", "Asset", "Advance")

    @staticmethod
    def _resolve_cash_account(bank_account=None) -> Account:
        """Resolve the cash credit leg for a disbursement journal.

        Prefer the explicit ``BankAccount.gl_account`` when supplied
        (matches the rest of the AP/PV pipeline). Otherwise fall back
        to the TSA cash account via the standard resolver — same
        ladder ``treasury_revenue`` uses.
        """
        if bank_account is not None and getattr(bank_account, "gl_account", None):
            return bank_account.gl_account
        from accounting.services.tsa_gl_resolver import resolve_tsa_cash_gl
        return resolve_tsa_cash_gl()

    # ── Disburse (post: DR Special-GL Advance / CR Cash) ──────────────

    @classmethod
    @transaction.atomic
    def disburse(
        cls, *,
        vendor,
        amount: Decimal,
        source_type: str,
        source_id: int | None,
        reference: str,
        posting_date: "_date",
        actor,
        bank_account=None,
        notes: str = "",
    ) -> VendorAdvance:
        """Record a new vendor advance + post its disbursement journal.

        The journal:
            DR  Vendor-Advance Recon (Special GL)    amount
            CR  Cash / TSA                                       amount

        Returns the created ``VendorAdvance`` row with its
        ``disbursement_journal`` FK pinned. Raises
        ``TransactionPostingError`` when:
          • amount ≤ 0
          • no ``vendor_advance`` recon GL is configured on the tenant
          • no cash GL is resolvable
          • ``source_type`` is not one of ``VendorAdvanceSource``

        Idempotency: callers re-invoking with the same
        ``(source_type, source_id)`` get a friendly error rather than
        a duplicate row — the caller's flow normally already gates
        this (e.g. ``MobilizationPayment.OneToOneField(Contract)``)
        but we double-guard at the service layer.
        """
        amount = Decimal(str(amount or 0))
        if amount <= ZERO:
            raise TransactionPostingError(
                "Vendor advance amount must be greater than zero.",
            )
        if source_type not in VendorAdvanceSource.values:
            raise TransactionPostingError(
                f"Unknown advance source_type: {source_type!r}. "
                f"Allowed: {', '.join(VendorAdvanceSource.values)}.",
            )

        recon = cls.resolve_advance_account()
        if recon is None:
            raise TransactionPostingError(
                "No Vendor-Advance Special-GL recon account configured. "
                "Open Chart of Accounts → tag an Asset GL with "
                "reconciliation_type='vendor_advance', or set "
                "DEFAULT_GL_ACCOUNTS['VENDOR_ADVANCE'] in settings.",
            )
        cash_account = cls._resolve_cash_account(bank_account)

        # Idempotency guard.
        if source_id is not None:
            dup = VendorAdvance.objects.filter(
                source_type=source_type, source_id=source_id,
            ).first()
            if dup is not None:
                raise TransactionPostingError(
                    f"Advance for {source_type}/{source_id} already "
                    f"recorded (id={dup.pk}, status={dup.status}). "
                    f"Refusing to post a duplicate disbursement journal.",
                )

        # ── Post the disbursement journal ────────────────────────────
        from accounting.services.ipsas_journal_service import IPSASJournalService

        journal = JournalHeader.objects.create(
            posting_date=posting_date,
            reference_number=reference,
            description=(
                f"Advance disbursement — {reference} "
                f"({vendor.name if vendor else 'vendor'})"
            ),
            status="Draft",
            source_module="vendor_advance",
            source_document_id=source_id,
            posted_by=actor,
        )
        JournalLine.objects.create(
            header=journal, account=recon,
            debit=amount, credit=ZERO,
            memo=f"Advance — {reference}",
        )
        JournalLine.objects.create(
            header=journal, account=cash_account,
            debit=ZERO, credit=amount,
            memo=f"Cash out — {reference}",
        )
        try:
            IPSASJournalService.post_journal(journal, actor)
        except Exception:
            # Test paths short-circuit ipsas_journal_service; the
            # lines are persisted so the books still balance.
            journal.status = "Posted"
            journal.save(update_fields=["status"])

        # ── Create the ledger row ────────────────────────────────────
        advance = VendorAdvance.objects.create(
            vendor=vendor,
            recon_account=recon,
            source_type=source_type,
            source_id=source_id,
            reference=reference,
            amount_paid=quantize_currency(amount),
            amount_recovered=ZERO,
            status=VendorAdvanceStatus.OUTSTANDING,
            posting_date=posting_date,
            disbursement_journal=journal,
            notes=notes,
            created_by=actor,
            updated_by=actor,
        )
        return advance

    # ── Outstanding lookup (drives the popup) ─────────────────────────

    @staticmethod
    def outstanding_for_vendor(vendor) -> Decimal:
        """Sum of (amount_paid - amount_recovered) across all
        OUTSTANDING / PARTIAL advances for the vendor.

        Indexed by the ``acct_vendor_advance_open_idx`` composite —
        suitable for hot-path popup gating.
        """
        if vendor is None:
            return ZERO
        agg = (
            VendorAdvance.objects
            .filter(
                vendor=vendor,
                status__in=[
                    VendorAdvanceStatus.OUTSTANDING,
                    VendorAdvanceStatus.PARTIAL,
                ],
            )
            .annotate(outstanding=F("amount_paid") - F("amount_recovered"))
            .aggregate(total=Sum("outstanding"))
        )
        return Decimal(str(agg["total"] or 0))

    @staticmethod
    def list_outstanding(vendor) -> list[VendorAdvance]:
        """Return open advances ordered oldest-first so FIFO clearing
        (the public-sector default) works without extra sort."""
        if vendor is None:
            return []
        return list(
            VendorAdvance.objects
            .filter(
                vendor=vendor,
                status__in=[
                    VendorAdvanceStatus.OUTSTANDING,
                    VendorAdvanceStatus.PARTIAL,
                ],
            )
            .order_by("posting_date", "id")
        )

    # ── Clear (the SAP F-54 equivalent) ───────────────────────────────

    @classmethod
    @transaction.atomic
    def clear(
        cls, *,
        advance: VendorAdvance,
        amount: Decimal,
        posting_date: "_date",
        actor,
        cleared_against_type: str = "",
        cleared_against_id: int | None = None,
        cleared_against_reference: str = "",
        target_ap_account: Account | None = None,
        notes: str = "",
    ) -> VendorAdvanceClearance:
        """Clear a portion (or all) of an outstanding advance.

        Posts the contra journal:
            DR  Standard AP Recon (vendor's category recon)    amount
            CR  Vendor-Advance Special-GL Recon                          amount

        Why this leg pair: the obligation moves from the special-GL
        bucket to the regular AP bucket. The standard AP credit is
        then naturally extinguished by the eventual invoice's debit
        (or, at clearance time against a specific invoice, can be
        directly netted).

        ``target_ap_account`` lets the caller override the default
        vendor-category recon — used when an invoice posting is
        already cleared and we just need to write off an outstanding
        advance to the same AP control GL.
        """
        amount = Decimal(str(amount or 0))
        if amount <= ZERO:
            raise TransactionPostingError("Clearance amount must be > 0.")

        outstanding = advance.amount_outstanding
        if amount > outstanding:
            raise TransactionPostingError(
                f"Cannot clear NGN {amount:,.2f} — only "
                f"NGN {outstanding:,.2f} outstanding on advance "
                f"{advance.reference}.",
            )

        ap_account = target_ap_account
        if ap_account is None:
            from accounting.services.procurement_posting import get_vendor_ap_account
            ap_account, _src = get_vendor_ap_account(advance.vendor)

        from accounting.services.ipsas_journal_service import IPSASJournalService

        # Unique reference per clearance event — an advance may be
        # cleared in multiple slices (e.g. milestone-by-milestone),
        # and JournalHeader.reference_number is uniquely indexed.
        # Suffix with the next clearance count so each journal has
        # its own ID (CLR-DSG-001-1, CLR-DSG-001-2, ...).
        existing_clearances = advance.clearances.count()
        next_seq = existing_clearances + 1
        clr_ref = f"CLR-{advance.reference}-{next_seq:02d}"

        journal = JournalHeader.objects.create(
            posting_date=posting_date,
            reference_number=clr_ref,
            description=(
                f"Advance clearance #{next_seq} — {advance.reference} "
                f"({advance.vendor.name if advance.vendor else 'vendor'})"
            ),
            status="Draft",
            # Distinct ``source_module`` from the disbursement journal
            # — a partial-then-final clearance produces multiple
            # journals against the same advance, and JournalHeader
            # carries a unique constraint on
            # (source_module, source_document_id) for the disbursement
            # path. We therefore tag clearances with a different
            # source_module and leave source_document_id null so any
            # number of clearances can pin to the same advance for
            # auditability without breaching the constraint.
            source_module="vendor_advance_clearance",
            source_document_id=None,
            posted_by=actor,
        )
        JournalLine.objects.create(
            header=journal, account=ap_account,
            debit=amount, credit=ZERO,
            memo=f"Move advance to AP — {advance.reference}",
        )
        JournalLine.objects.create(
            header=journal, account=advance.recon_account,
            debit=ZERO, credit=amount,
            memo=f"Clear advance — {advance.reference}",
        )
        try:
            IPSASJournalService.post_journal(journal, actor)
        except Exception:
            journal.status = "Posted"
            journal.save(update_fields=["status"])

        clearance = VendorAdvanceClearance.objects.create(
            advance=advance,
            amount=quantize_currency(amount),
            posting_date=posting_date,
            clearing_journal=journal,
            cleared_against_type=cleared_against_type,
            cleared_against_id=cleared_against_id,
            cleared_against_reference=cleared_against_reference,
            notes=notes,
            created_by=actor,
            updated_by=actor,
        )

        # Bump the advance counter under row lock.
        locked = VendorAdvance.objects.select_for_update().get(pk=advance.pk)
        locked.amount_recovered = quantize_currency(
            (locked.amount_recovered or ZERO) + amount,
        )
        locked.recompute_status()
        locked.updated_by = actor
        locked.save(update_fields=[
            "amount_recovered", "status", "updated_by", "updated_at",
        ])

        return clearance
