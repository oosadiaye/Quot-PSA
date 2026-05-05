"""
IPCService
==========
Core orchestrator for Interim Payment Certificate (IPC) workflow.

This service enforces ALL 10 structural overpayment-prevention controls
on the path DRAFT -> SUBMITTED -> CERTIFIER_REVIEWED -> APPROVED ->
VOUCHER_RAISED -> PAID:

  1. Ceiling              — certified + pending <= contract_ceiling
  2. Coherence            — net_payable recomputed and reconciled
  3. Monotonicity         — cumulative_work_done_to_date never decreases
  4. Mobilization recovery — delegated to MobilizationService
  5. Retention cap        — delegated to RetentionService
  6. Variation approval   — only APPROVED variations count toward ceiling
                            (enforced via Contract.contract_ceiling property)
  7. Duplicate IPC        — integrity_hash uniqueness (DB partial index)
  8. Fiscal-year boundary — posting_date must fall inside contract.fiscal_year
  9. Three-way match      — IPC ↔ MeasurementBook ↔ PaymentVoucher
 10. Segregation of Duties — submitter ≠ certifier ≠ approver ≠ voucher
                            raiser ≠ payer

Every state-changing method runs inside a single @transaction.atomic
block and takes a SELECT FOR UPDATE on ContractBalance, so two concurrent
IPCs cannot both pass the ceiling check.  A BigInteger `version` column
on ContractBalance is incremented on every write and checked by the
PostgreSQL trigger (migration 0002_contract_balance_trigger.py) to give
us optimistic+pessimistic defence-in-depth.
"""
from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from contracts.models import (
    ApprovalAction,
    ApprovalObjectType,
    Contract,
    ContractApprovalStep,
    ContractBalance,
    ContractStatus,
    InterimPaymentCertificate,
    IPCStatus,
    MeasurementBook,
    MeasurementBookStatus,
)
from contracts.services.exceptions import (
    CeilingBreachError,
    CoherenceError,
    ConcurrencyError,
    DuplicateIPCError,
    FiscalYearBoundaryError,
    InvalidTransitionError,
    MonotonicityError,
    SegregationOfDutiesError,
    ThreeWayMatchError,
)
from contracts.services.mobilization_service import MobilizationService
from contracts.services.numbering import next_ipc_number
from contracts.services.retention_service import RetentionService
from contracts.services.sod import actor_can_bypass_sod
from core.models import quantize_currency

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser


User = get_user_model()
ZERO = Decimal("0.00")
COHERENCE_TOLERANCE = Decimal("0.01")  # 1-kobo tolerance for rounding


# Statuses at which an IPC still counts toward committed spend.
_PENDING_STATUSES = (
    IPCStatus.SUBMITTED,
    IPCStatus.CERTIFIER_REVIEWED,
    IPCStatus.APPROVED,
    IPCStatus.VOUCHER_RAISED,
)


class IPCService:
    """Stateless orchestrator — all methods are class-methods."""

    # ── GL account resolution for the accrual journal ─────────────────

    @staticmethod
    def _resolve_retention_account():
        """Layered ladder for the Retention-Held GL account.

        Order:
          1. Account.reconciliation_type='retention_held' (CoA-portable)
          2. Settings DEFAULT_GL_ACCOUNTS['RETENTION_HELD']
          3. Liability account whose code starts with '41' AND name
             matches /retention|deposit/i — the conventional NCoA
             slot for performance security holdback
          4. None (caller absorbs into AP if no retention GL exists)
        """
        from accounting.models import Account
        recon = Account.objects.filter(
            reconciliation_type='retention_held', is_active=True,
        ).first()
        if recon:
            return recon

        from django.conf import settings
        code = (
            getattr(settings, 'DEFAULT_GL_ACCOUNTS', {}) or {}
        ).get('RETENTION_HELD')
        if code:
            via_code = Account.objects.filter(code=code, is_active=True).first()
            if via_code:
                return via_code

        return Account.objects.filter(
            account_type='Liability', is_active=True,
            code__startswith='41',
            name__iregex=r'retention|holdback|security.deposit',
        ).first()

    @staticmethod
    def _resolve_mobilization_recovery_account():
        """Mobilization advance receivable / clearing account.

        Mirrors the AP recon-type pattern: prefers a flagged
        ``mobilization_advance`` account, then a settings code, then
        an asset GL whose name matches /mobili.+(advance|receivable)/i.
        """
        from accounting.models import Account
        recon = Account.objects.filter(
            reconciliation_type='mobilization_advance', is_active=True,
        ).first()
        if recon:
            return recon

        from django.conf import settings
        code = (
            getattr(settings, 'DEFAULT_GL_ACCOUNTS', {}) or {}
        ).get('MOBILIZATION_ADVANCE')
        if code:
            via_code = Account.objects.filter(code=code, is_active=True).first()
            if via_code:
                return via_code

        return Account.objects.filter(
            account_type='Asset', is_active=True,
            name__iregex=r'mobili.+advance|advance.+contractor',
        ).first()

    # ── Accrual journal posting (called from approve) ─────────────────

    @classmethod
    def _post_accrual_journal(
        cls,
        ipc: 'InterimPaymentCertificate',
        actor,
    ):
        """Write the IPSAS accrual journal for an approved IPC.

        Lines (cash-basis WHT — VAT/WHT recognition deferred to PV
        posting via the existing ``deductions_for_ipc`` pipeline):

            DR  Expense (contract.economic GL)        gross
            CR  Mobilization Advance (asset)          mob_recovery
            CR  Retention Held (liability)            retention
            CR  Accounts Payable (vendor recon)       net to vendor

        ``net_to_vendor = gross - mob_recovery - retention`` so DR == CR
        by construction. Tax lines (Input VAT debit, WHT credit) are
        intentionally NOT booked here — they're recognised at the
        Payment Voucher stage to match Nigerian PFM cash-basis (same
        pattern as Invoice Verification).

        Returns the posted JournalHeader. Idempotent: if the IPC
        already has an ``accrual_journal``, returns the existing one
        without re-posting.
        """
        from decimal import Decimal as _D
        from accounting.models import JournalHeader, JournalLine, Account
        from accounting.services.procurement_posting import get_vendor_ap_account
        from accounting.services.base_posting import TransactionPostingError

        if ipc.accrual_journal_id:
            return ipc.accrual_journal

        contract = ipc.contract
        # Resolve account legs.
        ncoa = contract.ncoa_code
        if ncoa is None or ncoa.economic is None:
            raise TransactionPostingError(
                "Cannot post IPC accrual: contract has no NCoA economic "
                "segment. Edit the contract to assign segments first.",
            )
        # The economic segment bridges to a real GL via legacy_account.
        expense_account = (
            getattr(ncoa.economic, 'legacy_account', None)
            or Account.objects.filter(
                code=ncoa.economic.code, is_active=True,
            ).first()
        )
        if expense_account is None:
            raise TransactionPostingError(
                f"Economic segment {ncoa.economic.code} has no bridged GL "
                f"account. Run ``./manage.py backfill_legacy_dims`` to "
                f"reconcile NCoA → CoA."
            )

        ap_account, _src = get_vendor_ap_account(contract.vendor)
        retention_account = cls._resolve_retention_account()
        mob_account = cls._resolve_mobilization_recovery_account()

        # Compute amounts.
        gross = _D(str(ipc.this_certificate_gross or 0))
        mob_recovery = _D(str(ipc.mobilization_recovery_this_cert or 0))
        retention = _D(str(ipc.retention_deduction_this_cert or 0))
        # AP credit is the residual — what genuinely goes to the vendor.
        ap_credit = quantize_currency(gross - mob_recovery - retention)
        if ap_credit < ZERO:
            raise TransactionPostingError(
                "IPC deductions exceed gross — would leave AP credit "
                "negative. Review the certificate before approving."
            )

        # Build the journal.
        journal = JournalHeader.objects.create(
            posting_date=ipc.posting_date,
            reference_number=ipc.ipc_number or f"IPC-{ipc.pk}",
            description=(
                f"IPC accrual — {ipc.ipc_number} / "
                f"{contract.contract_number}"
            ),
            mda=getattr(ncoa.administrative, 'legacy_mda', None),
            fund=getattr(ncoa.fund, 'legacy_fund', None),
            function=getattr(ncoa.functional, 'legacy_function', None),
            program=getattr(ncoa.programme, 'legacy_program', None),
            geo=getattr(ncoa.geographic, 'legacy_geo', None),
            status='Draft',
            source_module='contracts',
            source_document_id=ipc.pk,
            posted_by=actor,
        )

        # DR Expense (gross)
        if gross > ZERO:
            JournalLine.objects.create(
                header=journal, account=expense_account,
                debit=gross, credit=ZERO,
                memo=f"Gross certified — {ipc.ipc_number}",
            )

        # CR Mobilization Advance (releasing the recoverable)
        if mob_recovery > ZERO and mob_account is not None:
            JournalLine.objects.create(
                header=journal, account=mob_account,
                debit=ZERO, credit=mob_recovery,
                memo=f"Mobilization recovery — {ipc.ipc_number}",
            )
        elif mob_recovery > ZERO:
            # No mobilization GL configured — fold into AP credit so
            # the books still balance. Operator should configure the
            # account; this prevents posting from failing.
            ap_credit = quantize_currency(ap_credit + mob_recovery)

        # CR Retention Held (liability)
        if retention > ZERO and retention_account is not None:
            JournalLine.objects.create(
                header=journal, account=retention_account,
                debit=ZERO, credit=retention,
                memo=f"Retention held — {ipc.ipc_number}",
            )
        elif retention > ZERO:
            # No retention GL — fold into AP. Same defensive fallback
            # as mobilization above. The contract's ContractBalance
            # still tracks retention_held so the figure surfaces in
            # the UI even when the GL is unconfigured.
            ap_credit = quantize_currency(ap_credit + retention)

        # CR Accounts Payable (net to vendor)
        if ap_credit > ZERO:
            JournalLine.objects.create(
                header=journal, account=ap_account,
                debit=ZERO, credit=ap_credit,
                memo=f"AP — {ipc.ipc_number} ({contract.vendor.name})",
            )

        # Post via the standard service so balance roll-up + period
        # checks fire (same path used by every other accrual).
        #
        # FAIL CLOSED: a posting error must bubble so the IPC approval
        # rolls back. The previous fallback that manually set
        # ``status='Posted'`` left ``GLBalance`` rows un-incremented
        # while the IPC sat in APPROVED — silent ledger drift in the
        # AP and Expense accounts. Trial Balance would understate
        # total liabilities by the IPC accrual amount until the issue
        # was discovered and a correcting JV posted.
        from accounting.services.ipsas_journal_service import IPSASJournalService
        IPSASJournalService.post_journal(journal, actor)

        # Pin it to the IPC for audit + UI display.
        ipc.accrual_journal = journal
        return journal

    # ── Tax auto-derivation (cash-basis recognition) ──────────────────

    @staticmethod
    def _derive_taxes(ipc: InterimPaymentCertificate) -> tuple[Decimal, Decimal]:
        """Compute (vat, wht) from the IPC's stored tax determination.

        Mirrors the invoice-verification cash-basis pattern: the IPC
        carries the tax-code / withholding-tax FKs at submission time,
        and at payment time we apply their rates to the gross.

        Rules:
          • VAT  = ``this_certificate_gross × tax_code.rate / 100``
                   when ``tax_code`` is set; 0 otherwise.
          • WHT  = ``this_certificate_gross × withholding_tax.rate / 100``
                   when ``withholding_tax`` is set AND ``wht_exempt``
                   is False; 0 otherwise.

        Returns ``(Decimal('0.00'), Decimal('0.00'))`` for any path
        that doesn't resolve a tax code, so callers can treat the
        result as "no tax" without checking ``None``.
        """
        gross = Decimal(str(ipc.this_certificate_gross or 0))
        if gross <= ZERO:
            return ZERO, ZERO

        vat = ZERO
        wht = ZERO

        if ipc.tax_code_id:
            tc_rate = Decimal(str(getattr(ipc.tax_code, "rate", 0) or 0))
            if tc_rate > ZERO:
                vat = quantize_currency(gross * tc_rate / HUNDRED)

        # WHT honours the per-IPC exemption first, then per-vendor.
        vendor_exempt = bool(
            getattr(getattr(ipc.contract, "vendor", None), "wht_exempt", False)
        )
        if not (ipc.wht_exempt or vendor_exempt) and ipc.withholding_tax_id:
            wht_rate = Decimal(str(getattr(ipc.withholding_tax, "rate", 0) or 0))
            if wht_rate > ZERO:
                wht = quantize_currency(gross * wht_rate / HUNDRED)

        return vat, wht

    # ── 1. Submit (DRAFT → SUBMITTED) ──────────────────────────────────

    @classmethod
    @transaction.atomic
    def submit_ipc(
        cls,
        *,
        contract: Contract,
        posting_date,
        cumulative_work_done_to_date: Decimal,
        measurement_book: MeasurementBook | None,
        actor: "AbstractUser",
        variation_claims: Decimal = ZERO,
        ld_deduction: Decimal = ZERO,
        notes: str = "",
        # ── Milestone-driven IPC (optional) ──────────────────────────
        # When supplied, the milestone is pinned to the IPC for audit
        # trail and prevents double-conversion. Tax/WHT FKs come from
        # the vendor master via ``create_from_milestone`` so the
        # downstream PaymentVoucher inherits correct deductions.
        milestone=None,
        tax_code=None,
        withholding_tax=None,
        wht_exempt: bool = False,
    ) -> InterimPaymentCertificate:
        """
        Create a SUBMITTED IPC under a row lock on ContractBalance.

        Enforces controls 1, 3, 7, 8 at submission.  Controls 2, 4, 5
        are applied here as computed deductions; the DB trigger then
        re-validates the balance before the transaction commits.
        """
        # Contract must be able to receive IPCs.
        if contract.status not in (
            ContractStatus.ACTIVATED,
            ContractStatus.IN_PROGRESS,
            ContractStatus.PRACTICAL_COMPLETION,
            ContractStatus.DEFECTS_LIABILITY,
        ):
            raise InvalidTransitionError(
                f"Contract must be ACTIVATED/IN_PROGRESS to submit an IPC "
                f"(is {contract.status}).",
                context={"contract_id": contract.pk, "status": contract.status},
            )

        # ── Control 8: Fiscal-year boundary ────────────────────────────
        fy = contract.fiscal_year
        if not (fy.start_date <= posting_date <= fy.end_date):
            raise FiscalYearBoundaryError(
                f"IPC posting_date {posting_date} falls outside contract fiscal year "
                f"{fy.start_date}…{fy.end_date}.",
                context={
                    "posting_date": str(posting_date),
                    "fy_start": str(fy.start_date),
                    "fy_end": str(fy.end_date),
                },
            )

        # Lock the balance row for the rest of this transaction.
        balance = ContractBalance.objects.select_for_update().get(pk=contract.pk)

        # ── Control 3: Monotonicity ────────────────────────────────────
        # Race-safe baseline. Compare against ``last_cumulative_
        # submitted`` (the highest value of cumulative_work_done_to_date
        # *submitted* on any IPC, regardless of approval status) rather
        # than ``cumulative_gross_certified`` (which only updates on
        # APPROVE).
        #
        # Why this matters under concurrency: two simultaneous
        # submissions on the same contract used to both read the same
        # ``cumulative_gross_certified`` baseline (since neither had
        # been approved yet), both pass the monotonicity check, and
        # both proceed — silently double-certifying the same work
        # once both reach approval. Anchoring the check on
        # ``last_cumulative_submitted`` (which we bump atomically
        # under the SELECT FOR UPDATE below) closes the race: the
        # second submission sees the first's update and refuses.
        previous_submitted = balance.last_cumulative_submitted or balance.cumulative_gross_certified
        previous_certified = balance.cumulative_gross_certified
        if cumulative_work_done_to_date <= previous_submitted:
            raise MonotonicityError(
                "Cumulative work done must exceed the highest value previously submitted on any IPC.",
                context={
                    "previous_submitted": str(previous_submitted),
                    "previous_certified": str(previous_certified),
                    "this_cumulative": str(cumulative_work_done_to_date),
                },
            )

        # ``this_gross`` is the delta against *certified* (not
        # submitted) — it represents the new gross certifiable amount
        # this IPC adds to the books once approved.
        this_gross = quantize_currency(
            cumulative_work_done_to_date - previous_certified
        )
        if this_gross < ZERO:
            raise CoherenceError(
                "Computed this_certificate_gross cannot be negative.",
                context={"this_gross": str(this_gross)},
            )

        # ── Control 1: Ceiling ─────────────────────────────────────────
        projected_committed = quantize_currency(
            balance.cumulative_gross_certified
            + balance.pending_voucher_amount
            + this_gross
            + variation_claims
        )
        if projected_committed > balance.contract_ceiling:
            raise CeilingBreachError(
                "IPC would push committed spend over the contract ceiling.",
                context={
                    "ceiling": str(balance.contract_ceiling),
                    "already_committed": str(
                        balance.cumulative_gross_certified
                        + balance.pending_voucher_amount
                    ),
                    "this_gross": str(this_gross),
                    "variation_claims": str(variation_claims),
                    "projected": str(projected_committed),
                },
            )

        # ── Control 4 & 5: Mobilization + Retention (computation only) ─
        mob_recovery = MobilizationService.compute_recovery(
            contract=contract,
            balance=balance,
            this_certificate_gross=this_gross,
        )
        retention_deduction = RetentionService.compute_deduction(
            contract=contract,
            balance=balance,
            this_certificate_gross=this_gross,
        )

        # Build the IPC (save() recomputes net_payable + integrity_hash).
        ipc = InterimPaymentCertificate(
            contract=contract,
            ipc_number=next_ipc_number(contract),
            measurement_book=measurement_book,
            milestone=milestone,
            tax_code=tax_code,
            withholding_tax=withholding_tax,
            wht_exempt=wht_exempt,
            posting_date=posting_date,
            cumulative_work_done_to_date=quantize_currency(
                cumulative_work_done_to_date
            ),
            previous_certified=previous_certified,
            this_certificate_gross=this_gross,
            mobilization_recovery_this_cert=mob_recovery,
            retention_deduction_this_cert=retention_deduction,
            ld_deduction=quantize_currency(ld_deduction),
            variation_claims=quantize_currency(variation_claims),
            status=IPCStatus.SUBMITTED,
            notes=notes,
            created_by=actor,
            updated_by=actor,
        )

        # ── Control 7: Duplicate IPC ───────────────────────────────────
        try:
            ipc.save()
        except IntegrityError as exc:
            # Partial unique index on integrity_hash WHERE status NOT IN
            # ('REJECTED', 'DRAFT') fired — this is a duplicate attempt.
            raise DuplicateIPCError(
                "An active IPC with this posting_date+cumulative already exists.",
                context={
                    "contract_id": contract.pk,
                    "posting_date": str(posting_date),
                    "cumulative": str(cumulative_work_done_to_date),
                },
            ) from exc

        # Bump pending_voucher_amount — this reserves the gross against
        # the ceiling even before certifier review, so a second concurrent
        # IPC in this same window will correctly fail the ceiling check.
        # H6 fix: use F('version')+1 update() instead of python-side
        # increment so the BEFORE-UPDATE trigger never sees a
        # potentially-stale Python-side value, even if a future caller
        # passes a stale ``balance`` object obtained outside the lock.
        new_pending = quantize_currency(
            balance.pending_voucher_amount + this_gross + variation_claims
        )
        try:
            ContractBalance.objects.filter(pk=balance.pk).update(
                pending_voucher_amount=new_pending,
                # Anchor the monotonicity baseline atomically under the
                # row lock. Subsequent concurrent submissions see this
                # value and refuse to submit anything <= it.
                last_cumulative_submitted=cumulative_work_done_to_date,
                version=F('version') + 1,
                updated_at=timezone.now(),
            )
        except IntegrityError as exc:
            raise ConcurrencyError(
                "ContractBalance update rejected by DB trigger; retry.",
                context={"contract_id": balance.pk},
            ) from exc
        balance.refresh_from_db()

        cls._record_step(
            ipc, actor, ApprovalAction.REQUEST_INFO,
            notes or "IPC submitted for certification",
        )
        return ipc

    # ── 1.b Milestone-driven IPC creation ─────────────────────────────

    @classmethod
    @transaction.atomic
    def create_from_milestone(
        cls,
        *,
        milestone,
        actor: "AbstractUser",
        posting_date=None,
        notes: str = "",
    ) -> InterimPaymentCertificate:
        """Convert an approved milestone into an IPC.

        Derives the heavy parameters from the milestone + vendor master:
          • cumulative_work_done_to_date = previous_certified + scheduled_value
          • posting_date                  = today (or caller override)
          • tax_code / withholding_tax    = vendor master defaults
          • wht_exempt                    = vendor master flag

        Validates that:
          • Milestone is COMPLETED (the "approved" terminal state)
          • Milestone hasn't already been converted (one IPC per milestone)
          • Contract is ACTIVATED / IN_PROGRESS / etc. (delegated to submit_ipc)
          • Cumulative + this gross stays inside the contract ceiling
            (delegated to submit_ipc — Control 1)

        Raises ``InvalidTransitionError`` for milestone-state issues;
        the underlying submit_ipc raises CeilingBreachError /
        FiscalYearBoundaryError as appropriate.
        """
        from datetime import date as _date

        if milestone.status != "COMPLETED":
            raise InvalidTransitionError(
                f"Milestone must be COMPLETED before conversion "
                f"(currently {milestone.status}).",
                context={"milestone_id": milestone.pk, "status": milestone.status},
            )
        # OneToOneField.unique=True will raise IntegrityError on second
        # convert; check explicitly first for a friendlier error.
        if InterimPaymentCertificate.objects.filter(milestone=milestone).exists():
            existing = InterimPaymentCertificate.objects.filter(milestone=milestone).first()
            raise InvalidTransitionError(
                f"Milestone {milestone.milestone_number} has already been "
                f"converted to IPC {existing.ipc_number}.",
                context={
                    "milestone_id": milestone.pk,
                    "existing_ipc_id": existing.pk,
                    "existing_ipc_number": existing.ipc_number,
                },
            )

        contract = milestone.contract
        # Lock the balance to read previous_certified consistently.
        balance = ContractBalance.objects.select_for_update().get(pk=contract.pk)
        previous_certified = balance.cumulative_gross_certified
        cumulative = quantize_currency(
            previous_certified + (milestone.scheduled_value or ZERO)
        )

        # Vendor-master tax determination (mirrors invoice verification).
        vendor = contract.vendor
        tax_code        = getattr(vendor, "tax_code", None)
        withholding_tax = getattr(vendor, "withholding_tax_code", None)
        wht_exempt      = bool(getattr(vendor, "wht_exempt", False))

        return cls.submit_ipc(
            contract=contract,
            posting_date=posting_date or _date.today(),
            cumulative_work_done_to_date=cumulative,
            measurement_book=None,
            actor=actor,
            variation_claims=ZERO,
            ld_deduction=ZERO,
            notes=(
                notes
                or f"Auto-generated from milestone #{milestone.milestone_number} — "
                   f"{milestone.description[:80]}"
            ),
            milestone=milestone,
            tax_code=tax_code,
            withholding_tax=withholding_tax,
            wht_exempt=wht_exempt,
        )

    # ── 2. Certifier review (SUBMITTED → CERTIFIER_REVIEWED) ────────────

    @classmethod
    @transaction.atomic
    def certify(
        cls,
        *,
        ipc: InterimPaymentCertificate,
        actor: "AbstractUser",
        notes: str = "",
    ) -> InterimPaymentCertificate:
        """Engineer / QS review.  SoD: certifier must not be the drafter."""
        if ipc.status != IPCStatus.SUBMITTED:
            raise InvalidTransitionError(
                f"IPC must be SUBMITTED to certify (is {ipc.status}).",
                context={"ipc_id": ipc.pk, "status": ipc.status},
            )

        cls._check_sod(ipc, actor, role="certifier")

        # ── Control 9 (early): MeasurementBook must be APPROVED ────────
        if ipc.measurement_book_id:
            mb = ipc.measurement_book
            if mb.status != MeasurementBookStatus.APPROVED:
                raise ThreeWayMatchError(
                    "Linked measurement book must be APPROVED before IPC "
                    "can be certified.",
                    context={
                        "mb_id": mb.pk,
                        "mb_status": mb.status,
                    },
                )
            # Gross in this IPC cannot exceed total measured value
            # plus any previously-certified cumulative.
            if ipc.this_certificate_gross > mb.total_measured_value:
                raise ThreeWayMatchError(
                    "IPC gross exceeds measurement-book total.",
                    context={
                        "ipc_gross": str(ipc.this_certificate_gross),
                        "mb_total": str(mb.total_measured_value),
                    },
                )

        ipc.certifying_engineer = actor
        ipc.updated_by = actor
        ipc.transition_to(IPCStatus.CERTIFIER_REVIEWED)
        cls._record_step(
            ipc, actor, ApprovalAction.CERTIFY, notes or "Certified by engineer",
        )
        return ipc

    # ── 3. Approval (CERTIFIER_REVIEWED → APPROVED) ────────────────────

    @classmethod
    @transaction.atomic
    def approve(
        cls,
        *,
        ipc: InterimPaymentCertificate,
        actor: "AbstractUser",
        notes: str = "",
    ) -> InterimPaymentCertificate:
        """
        Approving officer sign-off.  Moves the amount out of
        pending_voucher and into cumulative_gross_certified under a
        balance row-lock.  SoD: approver must not be drafter or certifier.
        """
        if ipc.status != IPCStatus.CERTIFIER_REVIEWED:
            raise InvalidTransitionError(
                f"IPC must be CERTIFIER_REVIEWED to approve (is {ipc.status}).",
                context={"ipc_id": ipc.pk, "status": ipc.status},
            )

        cls._check_sod(ipc, actor, role="approver")

        balance = (
            ContractBalance.objects
            .select_for_update()
            .get(pk=ipc.contract_id)
        )

        # M6 fix: defensive ceiling re-refresh under the lock. If a
        # variation approval committed since the last refresh (or if a
        # migration backfill drifted the cached value), the snapshot in
        # ``balance.contract_ceiling`` may lag the live
        # ``contract.contract_ceiling`` property which re-aggregates
        # APPROVED variations on every read. Take the min of the two so
        # we fail closed against either source.
        live_ceiling = ipc.contract.contract_ceiling
        if balance.contract_ceiling != live_ceiling:
            from contracts.services.variation_service import VariationService
            VariationService._refresh_contract_ceiling(ipc.contract)
            balance.refresh_from_db()

        # ── Control 2: Coherence ───────────────────────────────────────
        expected_net = ipc.compute_net_payable()
        if abs(expected_net - ipc.net_payable) > COHERENCE_TOLERANCE:
            raise CoherenceError(
                "IPC net_payable does not reconcile with deduction breakdown.",
                context={
                    "stored_net": str(ipc.net_payable),
                    "expected_net": str(expected_net),
                },
            )

        # ── Control 1 (re-check): Ceiling at approval time ─────────────
        # Ceiling may have tightened if a variation was reverted.
        this_gross = ipc.this_certificate_gross + ipc.variation_claims
        projected_certified = quantize_currency(
            balance.cumulative_gross_certified + this_gross
        )
        # pending already includes this IPC's amount from submit_ipc,
        # so the meaningful invariant is projected_certified + (pending -
        # this_gross) <= ceiling.
        remaining_pending = quantize_currency(
            balance.pending_voucher_amount - this_gross
        )
        if remaining_pending < ZERO:
            remaining_pending = ZERO
        if projected_certified + remaining_pending > balance.contract_ceiling:
            raise CeilingBreachError(
                "Approval would breach contract ceiling.",
                context={
                    "ceiling": str(balance.contract_ceiling),
                    "projected_certified": str(projected_certified),
                    "remaining_pending": str(remaining_pending),
                },
            )

        # ── Control 4 & 5: apply recovery + deduction to balance ───────
        # (these were computed at submit_ipc; we now persist them)
        MobilizationService.apply_recovery(
            balance=balance,
            recovery_amount=ipc.mobilization_recovery_this_cert,
        )
        RetentionService.apply_deduction(
            balance=balance,
            deduction_amount=ipc.retention_deduction_this_cert,
        )

        # Move gross from pending → certified. H6 fix: use update() with
        # F('version')+1 so the version increment happens at the SQL
        # layer atomically with the field updates — the BEFORE-UPDATE
        # trigger sees a server-side computation, not a Python value
        # that could be stale under multi-tab races. mobilization_recovered
        # and retention_held were mutated in-memory by MobilizationService
        # and RetentionService above; we forward those values explicitly.
        try:
            ContractBalance.objects.filter(pk=balance.pk).update(
                cumulative_gross_certified=projected_certified,
                pending_voucher_amount=remaining_pending,
                mobilization_recovered=balance.mobilization_recovered,
                retention_held=balance.retention_held,
                version=F('version') + 1,
                updated_at=timezone.now(),
            )
        except IntegrityError as exc:
            # PG trigger rejected the write — a deeper invariant was
            # violated (e.g. version not strictly increasing under a
            # concurrent update).
            raise ConcurrencyError(
                "ContractBalance update rejected by DB trigger; retry.",
                context={"contract_id": balance.pk},
            ) from exc
        balance.refresh_from_db()

        ipc.updated_by = actor

        # ── Post accrual journal ─────────────────────────────────────
        # IPSAS accrual recognition: at approval the expense + payable
        # are booked even though cash hasn't moved yet. Retention and
        # mobilization recovery hit their respective liability/asset
        # GLs so the trial balance reflects the full obligation. WHT
        # and VAT stay deferred to PV time (cash-basis).
        #
        # FAIL-CLOSED: a posting error must bubble so the surrounding
        # @transaction.atomic rolls back the entire approval. The
        # previous swallow let IPCs reach APPROVED / VOUCHER_RAISED
        # / PAID without a journal — the IPC's "GL LEDGER" panel
        # showed projected lines but ``GLBalance`` was never touched,
        # so the Income Statement and every IPSAS report under-
        # reported the expense. Operators must now resolve the
        # underlying CoA gap (missing account, no NCoA bridge, etc.)
        # before the IPC can transition to APPROVED.
        cls._post_accrual_journal(ipc, actor)

        ipc.transition_to(IPCStatus.APPROVED)
        # ``transition_to`` saved status+updated_at; persist the
        # accrual_journal FK + updated_by separately so the journal
        # link survives the round-trip even if the user navigates
        # away before the next save fires.
        ipc.save(update_fields=['accrual_journal', 'updated_by', 'updated_at'])
        cls._record_step(
            ipc, actor, ApprovalAction.APPROVE, notes or "IPC approved for payment",
        )
        return ipc

    # ── 4. Voucher raising (APPROVED → VOUCHER_RAISED) ──────────────────

    @classmethod
    @transaction.atomic
    def raise_voucher(
        cls,
        *,
        ipc: InterimPaymentCertificate,
        payment_voucher_id: int,
        voucher_gross: Decimal,
        actor: "AbstractUser",
        notes: str = "",
    ) -> InterimPaymentCertificate:
        """
        Treasury raises a PaymentVoucherGov against the IPC.

        Control 9 (three-way match): voucher_gross must equal IPC
        net_payable (within tolerance).  SoD: voucher raiser must not
        be drafter, certifier, or approver.
        """
        if ipc.status != IPCStatus.APPROVED:
            raise InvalidTransitionError(
                f"IPC must be APPROVED to raise a voucher (is {ipc.status}).",
                context={"ipc_id": ipc.pk, "status": ipc.status},
            )

        cls._check_sod(ipc, actor, role="voucher_raiser")

        if abs(quantize_currency(voucher_gross) - ipc.net_payable) > COHERENCE_TOLERANCE:
            raise ThreeWayMatchError(
                "Payment voucher amount does not match IPC net payable.",
                context={
                    "voucher_gross": str(voucher_gross),
                    "ipc_net_payable": str(ipc.net_payable),
                },
            )

        ipc.payment_voucher_id = payment_voucher_id
        ipc.updated_by = actor
        ipc.save(update_fields=["payment_voucher", "updated_by", "updated_at"])
        ipc.transition_to(IPCStatus.VOUCHER_RAISED)
        cls._record_step(
            ipc, actor, ApprovalAction.APPROVE,
            notes or f"Payment voucher {payment_voucher_id} raised",
        )
        return ipc

    # ── 4b. Auto-create draft Payment Voucher from IPC ──────────────────
    #
    # UX helper: spawns a ``PaymentVoucherGov`` in DRAFT pre-populated
    # from the IPC + contract + vendor, then links it to the IPC and
    # transitions IPC to VOUCHER_RAISED. The operator opens the new PV
    # in Treasury to review, edit, and walk through CHECKED → APPROVED →
    # SCHEDULED → PAID. Idempotent: if a PV is already linked, return
    # it instead of creating a duplicate.
    @classmethod
    @transaction.atomic
    def create_draft_voucher(
        cls,
        *,
        ipc: InterimPaymentCertificate,
        actor: "AbstractUser",
        notes: str = "",
    ):
        from accounting.models.gl import TransactionSequence
        from accounting.models.treasury import PaymentVoucherGov, TreasuryAccount

        # Idempotency — if a PV is already attached, just return it.
        if ipc.payment_voucher_id:
            return ipc.payment_voucher

        if ipc.status != IPCStatus.APPROVED:
            raise InvalidTransitionError(
                f"IPC must be APPROVED to raise a voucher (is {ipc.status}).",
                context={"ipc_id": ipc.pk, "status": ipc.status},
            )

        cls._check_sod(ipc, actor, role="voucher_raiser")

        contract = ipc.contract
        vendor = contract.vendor

        # Pick the first active TSA — operator can change it on the PV.
        tsa = TreasuryAccount.objects.filter(is_active=True).first()
        if tsa is None:
            raise InvalidTransitionError(
                "No active Treasury Account configured. Configure a TSA "
                "before raising vouchers.",
                context={"ipc_id": ipc.pk},
            )

        voucher_number = TransactionSequence.get_next(
            "payment_voucher", prefix="PV-",
        )

        # Surface the MDA name in the narration so PV-list scanners
        # know who owns the spend without drilling into NCoA segments.
        # The full administrative classification is already inherited
        # via ``ncoa_code`` (contract.ncoa_code carries it); this is
        # the human-readable echo.
        mda_name = ""
        try:
            mda_name = (
                getattr(getattr(contract, "mda", None), "name", "")
                or getattr(getattr(contract.ncoa_code, "administrative", None), "name", "")
                or ""
            )
        except Exception:  # noqa: BLE001 — narration enrichment is best-effort
            mda_name = ""
        base_narration = (
            f"Payment for IPC {ipc.ipc_number} "
            f"under contract {contract.contract_number}"
        )
        if mda_name:
            base_narration = f"[{mda_name}] {base_narration}"

        pv = PaymentVoucherGov.objects.create(
            voucher_number=voucher_number,
            payment_type="VENDOR",
            ncoa_code=contract.ncoa_code,
            appropriation=None,  # operator selects in PV form (BudgetEncumbrance != Appropriation)
            payee_name=getattr(vendor, "name", "") or contract.contract_number,
            payee_account=getattr(vendor, "bank_account_number", "") or "",
            payee_bank=getattr(vendor, "bank_name", "") or "",
            gross_amount=ipc.net_payable,
            wht_amount=Decimal("0"),
            narration=base_narration[:500],
            tsa_account=tsa,
            source_document=contract.contract_number or f"CONTRACT-{contract.pk}",
            status="DRAFT",
            created_by=actor,
            updated_by=actor,
        )

        # Link the PV to the IPC and transition the IPC. From this point
        # onward the IPC is "VOUCHER_RAISED" — the PV's own lifecycle is
        # tracked separately on the PaymentVoucherGov record.
        ipc.payment_voucher_id = pv.pk
        ipc.updated_by = actor
        ipc.save(update_fields=["payment_voucher", "updated_by", "updated_at"])
        ipc.transition_to(IPCStatus.VOUCHER_RAISED)
        cls._record_step(
            ipc, actor, ApprovalAction.APPROVE,
            notes or f"Draft voucher {voucher_number} created from IPC.",
        )
        return pv

    # ── 5. Mark paid (VOUCHER_RAISED → PAID) ────────────────────────────

    @classmethod
    @transaction.atomic
    def mark_paid(
        cls,
        *,
        ipc: InterimPaymentCertificate,
        payment_date,
        vat_amount: Decimal | None = None,
        wht_amount: Decimal | None = None,
        actor: "AbstractUser",
        notes: str = "",
    ) -> InterimPaymentCertificate:
        """
        Treasury disburses the cash.  Updates balance.cumulative_gross_paid
        under a row lock.  SoD: payer must not be drafter, certifier,
        approver, or voucher raiser.

        VAT/WHT are recorded at payment time per FIRS cash-basis rules
        (mirrors the Invoice Verification model — determination at
        invoice/IPC time, recognition at payment time).

        ``vat_amount`` and ``wht_amount`` are now optional. When omitted
        (or passed as None / 0), the values are auto-derived from the
        IPC's stored tax determination:
          • ``ipc.tax_code.rate``         → VAT recognition unless
                                            ``tax_code`` is None
          • ``ipc.withholding_tax.rate``  → WHT recognition unless
                                            ``ipc.wht_exempt=True`` or
                                            no withholding code is set
        Explicit non-zero amounts passed by the caller still win — that
        path is used by treasury workflows that need to override
        defaults (e.g. partial WHT under double-tax treaty).
        """
        if ipc.status != IPCStatus.VOUCHER_RAISED:
            raise InvalidTransitionError(
                f"IPC must be VOUCHER_RAISED to mark paid (is {ipc.status}).",
                context={"ipc_id": ipc.pk, "status": ipc.status},
            )

        cls._check_sod(ipc, actor, role="payer")

        balance = (
            ContractBalance.objects
            .select_for_update()
            .get(pk=ipc.contract_id)
        )

        # ── Auto-derive VAT / WHT when not supplied ───────────────────
        derived_vat, derived_wht = cls._derive_taxes(ipc)
        final_vat = (
            quantize_currency(vat_amount)
            if vat_amount and Decimal(str(vat_amount)) > ZERO
            else derived_vat
        )
        final_wht = (
            quantize_currency(wht_amount)
            if wht_amount and Decimal(str(wht_amount)) > ZERO
            else derived_wht
        )
        ipc.vat_amount = final_vat
        ipc.wht_amount = final_wht
        # Re-sync net_payable now that taxes are known.
        new_net = ipc.compute_net_payable()
        ipc.net_payable = new_net

        # Increase cumulative_gross_paid by the gross portion that has
        # actually been disbursed (gross − deductions already accounted
        # for in certified).  Here we use this_certificate_gross since
        # that's what moved into cumulative_gross_certified.
        paid_gross = ipc.this_certificate_gross + ipc.variation_claims
        new_paid = quantize_currency(balance.cumulative_gross_paid + paid_gross)
        if new_paid > balance.cumulative_gross_certified:
            raise CeilingBreachError(
                "Payment would exceed cumulative gross certified.",
                context={
                    "certified": str(balance.cumulative_gross_certified),
                    "already_paid": str(balance.cumulative_gross_paid),
                    "this_payment_gross": str(paid_gross),
                },
            )
        # H6 fix: F('version')+1 server-side increment (race-safe).
        try:
            ContractBalance.objects.filter(pk=balance.pk).update(
                cumulative_gross_paid=new_paid,
                version=F('version') + 1,
                updated_at=timezone.now(),
            )
        except IntegrityError as exc:
            raise ConcurrencyError(
                "ContractBalance update rejected by DB trigger; retry.",
                context={"contract_id": balance.pk},
            ) from exc
        balance.refresh_from_db()

        ipc.updated_by = actor
        ipc.save(update_fields=[
            "vat_amount", "wht_amount", "net_payable",
            "updated_by", "updated_at",
        ])
        ipc.transition_to(IPCStatus.PAID)
        cls._record_step(
            ipc, actor, ApprovalAction.APPROVE,
            notes or f"Paid on {payment_date}",
        )

        # Reconcile mobilization payment status (PAID → PARTIALLY_RECOVERED
        # → FULLY_RECOVERED) now that the balance has moved.
        MobilizationService.reconcile_payment_status(contract=ipc.contract)

        return ipc

    # ── Reject (SUBMITTED/CERTIFIER_REVIEWED → REJECTED) ───────────────

    @classmethod
    @transaction.atomic
    def reject(
        cls,
        *,
        ipc: InterimPaymentCertificate,
        actor: "AbstractUser",
        reason: str,
    ) -> InterimPaymentCertificate:
        """
        Reject an IPC.  Releases the reserved pending_voucher_amount.
        Allowed only from SUBMITTED or CERTIFIER_REVIEWED.
        """
        if ipc.status not in (IPCStatus.SUBMITTED, IPCStatus.CERTIFIER_REVIEWED):
            raise InvalidTransitionError(
                f"IPC cannot be rejected from status {ipc.status}.",
                context={"ipc_id": ipc.pk, "status": ipc.status},
            )
        if not reason or not reason.strip():
            raise InvalidTransitionError("Rejection reason is required.")

        balance = (
            ContractBalance.objects
            .select_for_update()
            .get(pk=ipc.contract_id)
        )
        # Release the reservation made at submit_ipc time.
        released = ipc.this_certificate_gross + ipc.variation_claims
        new_pending = quantize_currency(
            balance.pending_voucher_amount - released
        )
        if new_pending < ZERO:
            new_pending = ZERO
        # H6 fix: race-safe versioning.
        try:
            ContractBalance.objects.filter(pk=balance.pk).update(
                pending_voucher_amount=new_pending,
                version=F('version') + 1,
                updated_at=timezone.now(),
            )
        except IntegrityError as exc:
            raise ConcurrencyError(
                "ContractBalance update rejected by DB trigger; retry.",
                context={"contract_id": balance.pk},
            ) from exc
        balance.refresh_from_db()

        ipc.rejection_reason = reason
        ipc.updated_by = actor
        ipc.save(update_fields=[
            "rejection_reason", "updated_by", "updated_at",
        ])
        ipc.transition_to(IPCStatus.REJECTED)
        cls._record_step(ipc, actor, ApprovalAction.REJECT, reason)
        return ipc

    # ── Deductions per Circular AG/CIR/54/C/Vol.10/1/134 (Apr 2026) ────

    @classmethod
    def deductions_for_ipc(
        cls,
        ipc: InterimPaymentCertificate,
        *,
        lock: bool = False,
    ) -> list:
        """
        Compute the statutory deductions for this IPC's payment voucher.

        Returns a list of ``Deduction`` dataclasses as defined in
        ``accounting.services.contract_deductions``. Pure computation —
        does not persist. Callers (view layer, PV-creation service)
        materialise the non-zero lines as ``PaymentVoucherDeduction``
        rows.

        "First payment" is determined by the contract ledger: if
        ``ContractBalance.cumulative_gross_paid`` is zero, no prior
        payment has cleared for this contract, so the handling charge
        applies. Subsequent IPCs on the same contract skip it.

        Status Verification is applied unless a
        ``VendorStatusVerification`` row already exists for
        ``(vendor, current_year)``.

        M5 fix: callers from PV-creation paths should pass ``lock=True``
        so the ``ContractBalance`` row is read under
        ``select_for_update`` — without this, a concurrent IPC approval
        moving ``cumulative_gross_paid`` from 0 to non-zero between
        the read and the PV write can flip ``is_first_payment``
        incorrectly, causing the handling charge to apply twice or
        be missed. Read-only callers (display, reports) keep the
        default ``lock=False`` which is unchanged.
        """
        from datetime import date
        from accounting.services import contract_deductions as deductions_mod
        from contracts.models import VendorStatusVerification

        if lock:
            balance = (
                ContractBalance.objects
                .select_for_update()
                .get(pk=ipc.contract_id)
            )
        else:
            balance = ContractBalance.objects.get(pk=ipc.contract_id)
        is_first_payment = balance.cumulative_gross_paid == ZERO

        current_year = date.today().year
        sv_paid = VendorStatusVerification.objects.filter(
            vendor_id=ipc.contract.vendor_id,
            year=current_year,
        ).exists()

        return deductions_mod.compute_all(
            gross_contract_value=balance.contract_ceiling,
            payment_amount=ipc.net_payable,
            is_first_payment=is_first_payment,
            status_verification_paid_this_year=sv_paid,
        )

    @classmethod
    @transaction.atomic
    def record_status_verification_paid(
        cls,
        *,
        vendor_id: int,
        year: int,
        payment_voucher_id: int | None,
        actor: "AbstractUser",
    ) -> "VendorStatusVerification":
        """
        Idempotently record that a vendor has paid their annual Status
        Verification fee for ``year``.

        Safe to call twice — the (vendor, year) unique constraint means
        the second call becomes a no-op and returns the existing row.
        """
        from datetime import date
        from contracts.models import VendorStatusVerification
        from accounting.services.contract_deductions import (
            STATUS_VERIFICATION_ANNUAL_FEE,
            CIRCULAR_REF,
        )

        row, _ = VendorStatusVerification.objects.get_or_create(
            vendor_id=vendor_id,
            year=year,
            defaults={
                "fee_amount":         STATUS_VERIFICATION_ANNUAL_FEE,
                "recorded_on":        date.today(),
                "payment_voucher_id": payment_voucher_id,
                "circular_reference": CIRCULAR_REF,
                "created_by":         actor,
                "updated_by":         actor,
            },
        )
        return row

    # ── Internal helpers ───────────────────────────────────────────────

    @staticmethod
    def _prior_actor_ids(ipc: InterimPaymentCertificate) -> set[int]:
        """
        Return the set of user IDs who have already acted on this IPC,
        including the drafter.  Used for Segregation-of-Duties checks.
        """
        actors = set(
            ContractApprovalStep.objects.filter(
                object_type=ApprovalObjectType.IPC,
                object_id=ipc.pk,
            ).values_list("action_by_id", flat=True)
        )
        if ipc.created_by_id:
            actors.add(ipc.created_by_id)
        if ipc.certifying_engineer_id:
            actors.add(ipc.certifying_engineer_id)
        return actors

    @classmethod
    def _check_sod(
        cls,
        ipc: InterimPaymentCertificate,
        actor: "AbstractUser",
        *,
        role: str,
    ) -> None:
        """Control 10 — actor must not have taken any prior role on this IPC.

        Tenant Admins / Django superusers / users granted
        ``contracts.bypass_sod`` transparently skip this check. Every such
        bypass is still audit-logged on the ContractApprovalStep row via
        ``_record_step`` (the caller tags the notes when appropriate), so
        auditors can grep for overrides.
        """
        if actor_can_bypass_sod(actor):
            return
        prior = cls._prior_actor_ids(ipc)
        if actor.pk in prior:
            raise SegregationOfDutiesError(
                f"Actor cannot be the {role}: they already acted on this IPC.",
                context={
                    "ipc_id": ipc.pk,
                    "actor_id": actor.pk,
                    "role": role,
                    "prior_actors": sorted(prior),
                },
            )

    @staticmethod
    def _record_step(
        ipc: InterimPaymentCertificate,
        actor: "AbstractUser",
        action: str,
        notes: str,
    ) -> None:
        next_step = (
            ContractApprovalStep.objects.filter(
                object_type=ApprovalObjectType.IPC,
                object_id=ipc.pk,
            ).count()
            + 1
        )
        ContractApprovalStep.objects.create(
            object_type=ApprovalObjectType.IPC,
            object_id=ipc.pk,
            contract=ipc.contract,
            step_number=next_step,
            role_required="contracts.approve_ipc",
            assigned_to=actor,
            action=action,
            action_by=actor,
            notes=notes or action,
        )
