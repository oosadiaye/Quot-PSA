"""Milestone-as-invoice — the centralised-AP replacement for IPCs.

Approving a milestone posts its accrual and materialises a ``VendorInvoice`` in
one atomic step (real-time to the sub-ledger, like a GRN-verified invoice):

    DR  Expense (one line per MilestoneInvoiceLine)   Σ line.amount = gross
    CR  Vendor Accounts Payable (vendor recon)        gross

**Retention is a LIEN, never journalled.** The invoice is booked at **gross**;
its ``retention_withheld`` (= ``contract.retention_rate% × gross``) freezes that
slice of the AP payable from disbursement until released. ``ContractBalance``
tracks ``cumulative_gross_certified`` and ``retention_held`` as memos.

See docs/superpowers/specs/2026-09-23-centralize-ap-ipc-as-invoice-design.md.
"""
from __future__ import annotations

from datetime import date as _date
from decimal import Decimal, ROUND_HALF_UP

from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

ZERO = Decimal("0.00")


def _q(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class MilestoneInvoiceService:
    """Approve a milestone → post the accrual + create the AP invoice."""

    @classmethod
    @transaction.atomic
    def approve_and_invoice(cls, *, milestone, actor, posting_date=None):
        from contracts.models import ContractBalance, MilestoneStatus
        from accounting.models import JournalHeader, JournalLine, VendorInvoice
        from accounting.services.base_posting import TransactionPostingError
        from accounting.services.ipsas_journal_service import IPSASJournalService
        from accounting.services.procurement_posting import get_vendor_ap_account

        posting_date = posting_date or _date.today()
        contract = milestone.contract

        if milestone.status == MilestoneStatus.INVOICED:
            raise TransactionPostingError("Milestone is already invoiced.")

        lines = list(milestone.lines.select_related("account").all())
        if not lines:
            raise TransactionPostingError(
                "Add at least one appropriation line before approving this milestone."
            )
        gross = _q(sum((_q(l.amount) for l in lines), ZERO))
        if gross <= ZERO:
            raise TransactionPostingError("Milestone gross must be greater than zero.")

        # Retention lien — memo only, never posted.
        rate = _q(getattr(contract, "retention_rate", 0) or 0)
        retention = _q(gross * rate / Decimal("100"))

        # One invoice per milestone (idempotent — safe on retry).
        ref = f"{contract.contract_number or 'CONTRACT'}/M{milestone.milestone_number}"
        existing = VendorInvoice.all_objects.filter(invoice_number=ref).first()
        if existing is not None:
            return existing

        ap_account, _src = get_vendor_ap_account(contract.vendor)
        ncoa = contract.ncoa_code

        # ── Journal: DR Expense per coding line / CR Vendor-AP (gross) ──
        journal = JournalHeader.objects.create(
            posting_date=posting_date,
            reference_number=ref,
            document_number=ref,
            description=f"Milestone invoice — {ref} ({milestone.description[:80]})",
            mda=getattr(getattr(ncoa, "administrative", None), "legacy_mda", None),
            fund=getattr(getattr(ncoa, "fund", None), "legacy_fund", None),
            function=getattr(getattr(ncoa, "functional", None), "legacy_function", None),
            program=getattr(getattr(ncoa, "programme", None), "legacy_program", None),
            geo=getattr(getattr(ncoa, "geographic", None), "legacy_geo", None),
            status="Draft",
            source_module="contract_milestone",
            source_document_id=milestone.pk,
            posted_by=actor,
        )
        for line in lines:
            JournalLine.objects.create(
                header=journal, account=line.account,
                debit=_q(line.amount), credit=ZERO,
                memo=(line.description or f"Milestone {milestone.milestone_number}")[:255],
            )
        JournalLine.objects.create(
            header=journal, account=ap_account,
            debit=ZERO, credit=gross,
            memo=f"AP — {ref} ({getattr(contract.vendor, 'name', '')})"[:255],
        )
        # Fail closed — a posting error rolls back the whole approval.
        IPSASJournalService.post_journal(journal, actor)

        # ── VendorInvoice — booked GROSS; retention is the lien ──
        desc = (
            f"Milestone {milestone.milestone_number} — {contract.contract_number} · "
            f"Gross ₦{gross:,.2f}"
        )
        if retention > ZERO:
            desc += f" · Retention lien ₦{retention:,.2f} (payable now ₦{gross - retention:,.2f})"
        invoice = VendorInvoice.objects.create(
            invoice_number=ref,
            reference=contract.contract_number or "",
            description=desc,
            vendor=contract.vendor,
            invoice_date=posting_date,
            due_date=posting_date,
            account=lines[0].account,
            mda=journal.mda, fund=journal.fund, function=journal.function,
            program=journal.program, geo=journal.geo,
            subtotal=gross, total_amount=gross, paid_amount=ZERO,
            retention_withheld=retention,
            status="Posted",
            journal_entry=journal,
        )

        # ── ContractBalance: certified += gross ──
        # Race-safe F() update; the DB trigger enforces
        # certified + pending_voucher ≤ ceiling and released ≤ held.
        #
        # NB: retention_held is NOT touched here. ``ContractActivationService``
        # seeds it lump-sum with the contract's full retention reserve
        # (original_sum × retention_rate) at activation, so accruing per
        # milestone would double-count. The actual per-invoice lien lives on
        # ``VendorInvoice.retention_withheld`` (set above); the contract-level
        # retention_held stays the reserve ceiling that Release-Retention draws
        # down. See memory: retention_held-double-count.
        balance = ContractBalance.objects.select_for_update().get(pk=contract.pk)
        try:
            ContractBalance.objects.filter(pk=balance.pk).update(
                cumulative_gross_certified=F("cumulative_gross_certified") + gross,
                version=F("version") + 1,
                updated_at=timezone.now(),
            )
        except IntegrityError as exc:
            raise TransactionPostingError(
                "Milestone would push certified value over the contract ceiling. "
                "Raise a variation first."
            ) from exc

        milestone.status = MilestoneStatus.INVOICED
        milestone.updated_by = actor
        milestone.save(update_fields=["status", "updated_by", "updated_at"])

        return invoice

    @classmethod
    @transaction.atomic
    def sync_contract_paid(cls, *, contract):
        """Recompute ``ContractBalance.cumulative_gross_paid`` from the paid
        amounts of the contract's milestone invoices.

        This REPLACES the fragile IPC ``mark_paid`` post-commit cascade: the
        contract's paid figure is *derived* from the AP subledger (the milestone
        invoices' ``paid_amount``), so it can never drift from the GL. Idempotent
        — safe to call after any payment. Retention held reduces ``paid_amount``,
        so a contract can't reach ``paid == certified`` (and therefore can't
        close) until its retention is released and paid.
        """
        from django.db.models import Sum
        from accounting.models import VendorInvoice
        from contracts.models import ContractBalance

        paid = _q(
            VendorInvoice.objects
            .filter(reference=contract.contract_number)
            .aggregate(s=Sum("paid_amount"))["s"] or ZERO
        )
        balance = ContractBalance.objects.select_for_update().get(pk=contract.pk)
        # The DB trigger enforces paid ≤ certified; clamp defensively so a
        # rounding overshoot can't trip it.
        new_paid = min(paid, _q(balance.cumulative_gross_certified))
        if _q(balance.cumulative_gross_paid) != new_paid:
            ContractBalance.objects.filter(pk=balance.pk).update(
                cumulative_gross_paid=new_paid,
                version=F("version") + 1,
                updated_at=timezone.now(),
            )
            balance.refresh_from_db()
        return balance

    @classmethod
    @transaction.atomic
    def release_retention(cls, *, contract, actor):
        """Release the contract's held retention lien.

        Lifts the ``retention_withheld`` freeze on every milestone invoice of
        the contract (so the frozen slice becomes payable through the normal AP
        flow) and records it in ``ContractBalance.retention_released``. **Posts
        nothing** — retention was never journalled; this only unfreezes it.
        """
        from contracts.models import ContractBalance
        from accounting.models import VendorInvoice
        from accounting.services.base_posting import TransactionPostingError

        balance = ContractBalance.objects.select_for_update().get(pk=contract.pk)
        releasable = _q(balance.retention_held) - _q(balance.retention_released)
        if releasable <= ZERO:
            raise TransactionPostingError("No retention is held to release on this contract.")

        invoices = list(
            VendorInvoice.objects.filter(
                reference=contract.contract_number,
                retention_withheld__gt=ZERO,
            )
        )
        released_total = ZERO
        for inv in invoices:
            released_total += _q(inv.retention_withheld)
            inv.retention_withheld = ZERO
            # Posted row — same escape hatch the payment-post propagation uses.
            inv.save(_allow_status_change=True)

        if released_total <= ZERO:
            raise TransactionPostingError(
                "No withheld retention found on this contract's milestone invoices."
            )

        ContractBalance.objects.filter(pk=balance.pk).update(
            retention_released=F("retention_released") + released_total,
            version=F("version") + 1,
            updated_at=timezone.now(),
        )
        return {"released": str(released_total), "invoices_unfrozen": len(invoices)}
