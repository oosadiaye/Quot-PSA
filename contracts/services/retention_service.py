"""
RetentionService
================
Handles deduction of retention on each IPC and its release at:
  • Practical Completion  — 50 % of held retention
  • Final Completion      — remaining 50 %
"""
from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from contracts.models import (
    Contract,
    ContractApprovalStep,
    ContractBalance,
    ContractStatus,
    RetentionRelease,
    RetentionReleaseStatus,
    RetentionReleaseType,
    ApprovalAction,
    ApprovalObjectType,
)
from contracts.services.exceptions import (
    InvalidTransitionError,
    RetentionCapError,
    SegregationOfDutiesError,
)
from contracts.services.sod import actor_can_bypass_sod
from core.models import quantize_currency

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser


User = get_user_model()
ZERO    = Decimal("0.00")
HALF    = Decimal("0.50")
HUNDRED = Decimal("100")


class RetentionService:

    # ── Deduction on each IPC (deprecated — upfront model in use) ─────

    @staticmethod
    def compute_deduction(
        *,
        contract: Contract,
        balance: ContractBalance,
        this_certificate_gross: Decimal,
    ) -> Decimal:
        """
        Returns ZERO — retention is no longer deducted per IPC.

        This system uses the LUMP-SUM / UPFRONT retention model:
        the full retention reserve (``contract.retention_reserve`` =
        original_sum × retention_rate / 100) is held back from the
        contract ceiling at activation. ``balance.retention_held`` is
        seeded with this value in
        :meth:`ContractActivationService.activate`, and IPCs cannot
        push committed spend over the reduced ceiling.

        The function is kept as a stub (rather than removed) so the
        existing IPC submission code in
        :meth:`IPCService._submit_ipc` doesn't need a structural change
        — it can keep calling this helper and writing the result onto
        ``IPC.retention_deduction_this_cert``. The field stays in the
        model for backward compat on historical IPCs created under the
        old per-IPC formula; new IPCs simply write 0.

        See :attr:`Contract.retention_reserve` for the new model.
        """
        return ZERO

    @staticmethod
    def apply_deduction(
        *,
        balance: ContractBalance,
        deduction_amount: Decimal,
    ) -> None:
        if deduction_amount < ZERO:
            raise RetentionCapError(
                "Retention deduction cannot be negative.",
                context={"amount": str(deduction_amount)},
            )
        balance.retention_held = quantize_currency(balance.retention_held + deduction_amount)

    # ── Release at completion ──────────────────────────────────────────

    @classmethod
    @transaction.atomic
    def create_release(
        cls,
        *,
        contract: Contract,
        release_type: str,
        actor: "AbstractUser",
    ) -> RetentionRelease:
        """
        Create a PENDING RetentionRelease at Practical or Final completion.
        The actual payment is raised via PaymentVoucher; mark_paid() is
        called by the treasury workflow when disbursed.
        """
        # Status gate
        if release_type == RetentionReleaseType.PRACTICAL_COMPLETION:
            required_status = ContractStatus.PRACTICAL_COMPLETION
        elif release_type == RetentionReleaseType.FINAL_COMPLETION:
            required_status = ContractStatus.FINAL_COMPLETION
        else:
            raise InvalidTransitionError(
                f"Unknown release_type: {release_type}",
            )

        if contract.status != required_status:
            raise InvalidTransitionError(
                f"Contract must be in {required_status} to release "
                f"{release_type} retention (is {contract.status}).",
                context={"contract_id": contract.pk, "status": contract.status},
            )

        # ── SoD: contract creator cannot create the release ─────────
        # Without this gate, the user who drafted the contract could
        # also create the retention release for that contract — the
        # release amount can be 50%+ of held retention, real money.
        # The existing ``approve`` and ``mark_paid`` methods get their
        # own SoD checks below.
        if (
            contract.created_by_id
            and contract.created_by_id == getattr(actor, 'pk', None)
            and not actor_can_bypass_sod(actor)
        ):
            raise InvalidTransitionError(
                "Segregation of duties: the user who drafted the contract "
                "cannot also create its retention release. Have a different "
                "officer raise the release.",
                context={
                    "contract_id": contract.pk,
                    "contract_drafter_id": contract.created_by_id,
                    "actor_id": getattr(actor, 'pk', None),
                },
            )

        # Uniqueness at DB level too (unique_together), but friendlier error here
        if contract.retention_releases.filter(release_type=release_type).exists():
            raise InvalidTransitionError(
                f"A {release_type} release already exists for this contract.",
            )

        # ── No-open-IPCs guard ───────────────────────────────────────
        # Both PRACTICAL_COMPLETION and FINAL_COMPLETION releases must
        # only fire AFTER every IPC has been approved or rejected. If
        # an IPC is still in DRAFT / SUBMITTED / CERTIFIER_REVIEWED,
        # additional retention will be deducted on it later — releasing
        # 50 % of the *currently-held* amount now permanently traps the
        # difference because ``unique_together(contract, release_type)``
        # blocks a second release of the same type.
        from contracts.models import (
            InterimPaymentCertificate,
            IPCStatus,
        )
        OPEN_IPC_STATUSES = (
            IPCStatus.DRAFT,
            IPCStatus.SUBMITTED,
            IPCStatus.CERTIFIER_REVIEWED,
        )
        if InterimPaymentCertificate.objects.filter(
            contract=contract, status__in=OPEN_IPC_STATUSES,
        ).exists():
            raise InvalidTransitionError(
                "Cannot release retention while open IPCs exist on the "
                "contract. Approve or reject every Draft / Submitted / "
                "Certifier-Reviewed IPC before raising a retention release "
                "— otherwise additional retention deducted later would be "
                "permanently trapped (unique_together blocks a second "
                "release of the same type).",
                context={
                    "contract_id": contract.pk,
                    "release_type": release_type,
                    "open_ipc_count": InterimPaymentCertificate.objects.filter(
                        contract=contract, status__in=OPEN_IPC_STATUSES,
                    ).count(),
                },
            )

        # Lock balance, compute amount
        balance = ContractBalance.objects.select_for_update().get(pk=contract.pk)
        remaining = balance.retention_held - balance.retention_released
        if remaining <= ZERO:
            raise RetentionCapError(
                "No retention remaining to release.",
                context={"held": str(balance.retention_held), "released": str(balance.retention_released)},
            )

        # Compute 50 % of original held at practical, remainder at final
        if release_type == RetentionReleaseType.PRACTICAL_COMPLETION:
            amount = quantize_currency(balance.retention_held * HALF)
            # But don't exceed what's still held
            amount = min(amount, remaining)
        else:  # FINAL_COMPLETION
            amount = remaining

        release = RetentionRelease.objects.create(
            contract=contract,
            release_type=release_type,
            amount=amount,
            status=RetentionReleaseStatus.PENDING,
            created_by=actor,
            updated_by=actor,
        )
        cls._record_step(release, actor, ApprovalAction.REQUEST_INFO, "Release created")
        return release

    @classmethod
    @transaction.atomic
    def approve(
        cls,
        *,
        release: RetentionRelease,
        actor: "AbstractUser",
        notes: str = "",
    ) -> RetentionRelease:
        if release.status != RetentionReleaseStatus.PENDING:
            raise InvalidTransitionError(
                f"Release must be PENDING to approve (is {release.status})."
            )
        if release.created_by_id == actor.pk and not actor_can_bypass_sod(actor):
            raise SegregationOfDutiesError(
                "Approver cannot be the same user who created the release.",
            )

        # Post the GL accrual journal BEFORE flipping status, so a
        # posting failure rolls the whole approval back atomically (the
        # @transaction.atomic decorator covers both). Mirrors the IPC
        # accrual-on-approve pattern in ``IPCService._post_accrual_journal``.
        # Audit fix C1: without this, Retention-Held liability never
        # cleared on the trial balance and AP-Contractor was never
        # recognised when the contractor was paid via PV.
        journal = cls._post_release_accrual_journal(release, actor)

        release.status       = RetentionReleaseStatus.APPROVED
        release.approved_by  = actor
        release.updated_by   = actor
        release.accrual_journal = journal
        release.save(update_fields=[
            "status", "approved_by", "updated_by", "updated_at",
            "accrual_journal",
        ])
        cls._record_step(release, actor, ApprovalAction.APPROVE, notes)
        return release

    # ── GL accrual journal posting on approve ────────────────────────
    # Layered account resolver mirrors IPCService — we share the same
    # retention liability GL slot so the credit at IPC accrual and the
    # debit at retention release land on the same row in GLBalance.

    @staticmethod
    def _resolve_retention_account():
        """Layered ladder for the Retention-Held GL account.

        Order (mirrors IPCService._resolve_retention_account so credit
        and debit hit the same GL row):
          1. Account.reconciliation_type='retention_held' (CoA-portable)
          2. Settings DEFAULT_GL_ACCOUNTS['RETENTION_HELD']
          3. Liability account whose code starts with '41' AND name
             matches /retention|deposit|holdback/i
        """
        from accounting.models import Account
        recon = Account.objects.filter(
            reconciliation_type='retention_held', is_active=True,
        ).first()
        if recon:
            return recon

        from django.conf import settings as dj_settings
        code = (
            getattr(dj_settings, 'DEFAULT_GL_ACCOUNTS', {}) or {}
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

    @classmethod
    def _post_release_accrual_journal(
        cls,
        release: RetentionRelease,
        actor,
    ):
        """Post the IPSAS journal recognising the retention release.

            DR  Retention Held (liability)        release.amount
            CR  Accounts Payable (vendor recon)   release.amount

        Idempotent: returns the existing journal if one is already
        linked. Posted via ``IPSASJournalService.post_journal`` so the
        chokepoint (assert_balanced + invalidate_period_reports +
        GLBalance roll-up) fires.
        """
        from accounting.models import JournalHeader, JournalLine
        from accounting.services.procurement_posting import get_vendor_ap_account
        from accounting.services.base_posting import TransactionPostingError
        from accounting.services.ipsas_journal_service import IPSASJournalService

        if release.accrual_journal_id:
            return release.accrual_journal

        contract = release.contract
        amount = quantize_currency(release.amount)
        if amount <= ZERO:
            raise InvalidTransitionError(
                "Cannot post retention-release journal for zero or negative amount.",
                context={"amount": str(amount)},
            )

        retention_account = cls._resolve_retention_account()
        if retention_account is None:
            raise TransactionPostingError(
                "Cannot post retention release accrual: no Retention-Held GL "
                "account found. Configure an Account with "
                "reconciliation_type='retention_held' OR set "
                "DEFAULT_GL_ACCOUNTS['RETENTION_HELD'] OR ensure a Liability "
                "account exists matching code 41* AND name "
                "/retention|holdback|security.deposit/i."
            )

        ap_account, _src = get_vendor_ap_account(contract.vendor)

        # Build the journal — copy contract MDA/fund/etc dimensions so
        # the GL roll-up lands on the same MDA bucket as the IPC accrual
        # that originally credited Retention-Held.
        ncoa = contract.ncoa_code
        # Posting date for the **accrual** journal = moment of
        # approval, not the future cash settlement date. The
        # previous expression read ``release.payment_date or
        # timezone.now().date()`` — but ``payment_date`` is ONLY
        # set later inside ``mark_paid``, so at this code path it
        # was always None and the fallback to ``now()`` always
        # fired. That was misleading (the ``or`` clause read like
        # it offered a choice but never could). The IPSAS-correct
        # date for the accrual is the moment the release was
        # approved, captured in ``updated_at`` by approve()'s save
        # just before this method runs.
        accrual_date = (
            release.updated_at.date()
            if release.updated_at
            else timezone.now().date()
        )
        journal = JournalHeader.objects.create(
            posting_date=accrual_date,
            reference_number=f"RR-{release.pk}-{release.release_type}",
            description=(
                f"Retention release ({release.get_release_type_display()}) "
                f"— {contract.contract_number}"
            ),
            mda=getattr(getattr(ncoa, 'administrative', None), 'legacy_mda', None) if ncoa else None,
            fund=getattr(getattr(ncoa, 'fund', None), 'legacy_fund', None) if ncoa else None,
            function=getattr(getattr(ncoa, 'functional', None), 'legacy_function', None) if ncoa else None,
            program=getattr(getattr(ncoa, 'programme', None), 'legacy_program', None) if ncoa else None,
            geo=getattr(getattr(ncoa, 'geographic', None), 'legacy_geo', None) if ncoa else None,
            status='Draft',
            # Distinct ``source_module`` per contracts-app document
            # type — see ipc_service.py for the rationale (partial
            # unique constraint on (source_module, source_document_id)
            # for Posted journals).
            source_module='contract_retention_release',
            source_document_id=release.pk,
            posted_by=actor,
        )

        # DR Retention-Held — clears the liability previously raised
        # at IPC accrual.
        JournalLine.objects.create(
            header=journal, account=retention_account,
            debit=amount, credit=ZERO,
            memo=f"Retention release {release.get_release_type_display()} — "
                 f"{contract.contract_number}",
        )

        # CR Accounts Payable — recognises the contractor receivable
        # before cash settles via PV.
        JournalLine.objects.create(
            header=journal, account=ap_account,
            debit=ZERO, credit=amount,
            memo=f"AP — retention release {contract.contract_number} "
                 f"({contract.vendor.name})",
        )

        IPSASJournalService.post_journal(journal, actor)
        return journal

    @classmethod
    @transaction.atomic
    def mark_paid(
        cls,
        *,
        release: RetentionRelease,
        payment_voucher_id: int,
        payment_date,
        actor: "AbstractUser",
    ) -> RetentionRelease:
        if release.status != RetentionReleaseStatus.APPROVED:
            raise InvalidTransitionError(
                f"Release must be APPROVED to mark paid (is {release.status})."
            )

        # ── SoD: approver cannot also mark paid ─────────────────────
        # Retention release is the final cash-out moment for the
        # contract; the canonical SoD invariant is "the user who
        # approved the release cannot also disburse it". The release
        # carries the approver in ``updated_by`` after approve()
        # commits (line 246 sets it). Also block the creator from
        # marking paid for symmetry with the broader policy.
        prior_actor_ids = {
            release.created_by_id,
            release.updated_by_id,  # last-set in approve()
        }
        if (
            getattr(actor, 'pk', None) in prior_actor_ids
            and not actor_can_bypass_sod(actor)
        ):
            raise InvalidTransitionError(
                "Segregation of duties: the user who created or approved "
                "the retention release cannot also mark it paid. Have a "
                "different treasury officer perform the disbursement.",
                context={
                    "release_id": release.pk,
                    "prior_actor_ids": [aid for aid in prior_actor_ids if aid],
                    "actor_id": getattr(actor, 'pk', None),
                },
            )

        balance = ContractBalance.objects.select_for_update().get(pk=release.contract_id)
        new_released = quantize_currency(balance.retention_released + release.amount)
        if new_released > balance.retention_held:
            raise RetentionCapError(
                "Release would exceed retention held.",
                context={
                    "held":          str(balance.retention_held),
                    "already_released": str(balance.retention_released),
                    "this_release":  str(release.amount),
                },
            )
        # H6 fix: F('version')+1 server-side increment — race-safe.
        from django.db import IntegrityError
        try:
            ContractBalance.objects.filter(pk=balance.pk).update(
                retention_released=new_released,
                version=F('version') + 1,
                updated_at=timezone.now(),
            )
        except IntegrityError as exc:
            raise InvalidTransitionError(
                "ContractBalance update rejected by DB trigger; retry.",
                context={"contract_id": balance.pk},
            ) from exc
        balance.refresh_from_db()

        release.status             = RetentionReleaseStatus.PAID
        release.payment_voucher_id = payment_voucher_id
        release.payment_date       = payment_date
        release.updated_by         = actor
        release.save(update_fields=[
            "status", "payment_voucher", "payment_date", "updated_by", "updated_at",
        ])
        return release

    # ── Internal ───────────────────────────────────────────────────────

    @staticmethod
    def _record_step(
        release: RetentionRelease,
        actor: "AbstractUser",
        action: str,
        notes: str,
    ) -> None:
        next_step = (
            ContractApprovalStep.objects.filter(
                object_type=ApprovalObjectType.RETENTION,
                object_id=release.pk,
            ).count()
            + 1
        )
        ContractApprovalStep.objects.create(
            object_type=ApprovalObjectType.RETENTION,
            object_id=release.pk,
            contract=release.contract,
            step_number=next_step,
            role_required="contracts.approve_retention_release",
            assigned_to=actor,
            action=action,
            action_by=actor,
            notes=notes or action,
        )
