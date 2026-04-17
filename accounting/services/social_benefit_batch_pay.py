"""
IPSAS 42 Social-Benefit batch payment service.

Combines a set of APPROVED ``SocialBenefitClaim`` records into a single
payment journal:

    For each claim C in the batch:
        DR  social_benefit_expense_code         (C.amount)
    CR      bank account (caller-supplied)      (sum of amounts)

Each claim is flipped APPROVED → PAID and stamped with ``paid_at``,
``payment_reference``, and ``journal_entry`` so downstream reporting
can trace bank-statement line → journal line → claim → beneficiary
without joining through a batch table.

Idempotency
-----------
The ``status='APPROVED'`` filter is itself the idempotency guard: a
claim that has already been paid is no longer APPROVED and is silently
excluded from subsequent runs. A caller who re-submits the same
claim_ids after a successful run will receive an empty result
(``claims_paid=0``) rather than a duplicate journal.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as _date
from decimal import Decimal
from typing import Iterable, Optional

from django.db import transaction


@dataclass
class BatchPayResult:
    posting_date: _date
    bank_account_code: str
    journal_id: Optional[int] = None
    journal_reference: str = ''
    claims_paid: int = 0
    claims_skipped: int = 0
    total_paid: Decimal = field(default_factory=lambda: Decimal('0'))
    skipped_details: list[dict] = field(default_factory=list)
    paid_claim_ids: list[int] = field(default_factory=list)


class SocialBenefitBatchPayError(Exception):
    """Raised when the batch-pay run cannot proceed."""


class SocialBenefitBatchPayService:

    @classmethod
    def run_batch(
        cls,
        *,
        bank_account_code: str,
        posting_date: Optional[_date] = None,
        claim_ids: Optional[Iterable[int]] = None,
        payment_reference: str = '',
        user=None,
        dry_run: bool = False,
    ) -> BatchPayResult:
        """Pay all APPROVED claims (or the supplied subset) in one journal.

        Parameters
        ----------
        bank_account_code
            CoA code of the bank/treasury account funding the payment
            (credited). Required — there is no default, because an
            entity may run multiple treasury accounts for different
            welfare programmes.
        posting_date
            Journal posting date. Defaults to today.
        claim_ids
            Optional iterable of SocialBenefitClaim PKs to restrict the
            batch. If ``None``, every APPROVED claim is picked up.
        payment_reference
            Optional shared bank / cheque / mobile-money reference
            stamped onto every paid claim.
        dry_run
            Validate eligibility without writing the journal.
        """
        from django.utils import timezone
        from accounting.models import (
            SocialBenefitClaim, AccountingSettings, Account,
            JournalHeader, JournalLine,
        )

        if posting_date is None:
            posting_date = timezone.now().date()

        if not bank_account_code or not str(bank_account_code).strip():
            raise SocialBenefitBatchPayError(
                'bank_account_code is required.'
            )
        bank_account_code = str(bank_account_code).strip()

        settings_obj = AccountingSettings.objects.first()
        expense_code = _resolve(
            settings_obj, 'social_benefit_expense_code', '25100000',
        )

        expense_account = Account.objects.filter(code=expense_code).first()
        bank_account = Account.objects.filter(code=bank_account_code).first()

        missing = []
        if expense_account is None:
            missing.append(f'social_benefit_expense_code={expense_code!r}')
        if bank_account is None:
            missing.append(f'bank_account_code={bank_account_code!r}')
        if missing:
            raise SocialBenefitBatchPayError(
                'Account(s) not found in the chart of accounts: '
                + '; '.join(missing)
                + '.'
            )

        result = BatchPayResult(
            posting_date=posting_date,
            bank_account_code=bank_account_code,
        )

        # ── Eligibility ─────────────────────────────────────────────
        qs = SocialBenefitClaim.objects.select_related('scheme').filter(
            status='APPROVED',
        )
        if claim_ids is not None:
            claim_ids = list(claim_ids)
            qs = qs.filter(pk__in=claim_ids)

            # Report claim_ids that were supplied but did NOT match
            # APPROVED — these are the skipped ones.
            matched_ids = set(qs.values_list('pk', flat=True))
            for cid in claim_ids:
                if cid not in matched_ids:
                    # Fetch the claim (if it exists) to give a useful
                    # reason in the skipped report.
                    actual = (
                        SocialBenefitClaim.objects
                        .filter(pk=cid)
                        .values('pk', 'claim_reference', 'status')
                        .first()
                    )
                    result.claims_skipped += 1
                    if actual is None:
                        result.skipped_details.append({
                            'claim_id': cid,
                            'reason':   'Claim not found.',
                        })
                    else:
                        result.skipped_details.append({
                            'claim_id':        actual['pk'],
                            'claim_reference': actual['claim_reference'],
                            'status':          actual['status'],
                            'reason':          (
                                f"Claim status is {actual['status']!r}, "
                                f'expected APPROVED.'
                            ),
                        })

        claims = list(qs.order_by('claim_reference'))
        eligible: list = []
        for claim in claims:
            amount = claim.amount or Decimal('0')
            if amount <= 0:
                result.claims_skipped += 1
                result.skipped_details.append({
                    'claim_id':        claim.pk,
                    'claim_reference': claim.claim_reference,
                    'reason':          'Non-positive claim amount.',
                })
                continue
            eligible.append(claim)
            result.total_paid += amount

        if dry_run or not eligible:
            result.claims_paid = len(eligible) if dry_run else 0
            if dry_run:
                result.paid_claim_ids = [c.pk for c in eligible]
            return result

        # ── Post journal + flip claims atomically ──────────────────
        posting_stamp = posting_date.strftime('%Y%m%d')
        reference = f'SB-PAY-{posting_stamp}-{len(eligible):04d}'

        with transaction.atomic():
            header = JournalHeader.objects.create(
                posting_date=posting_date,
                description=(
                    f'IPSAS 42 social-benefit batch payment — '
                    f'{len(eligible)} claim(s), total NGN '
                    f'{result.total_paid:,.2f}.'
                ),
                reference_number=reference,
                status='Draft',
                source_module='social_benefit_batch_pay',
            )

            lines: list[JournalLine] = []
            for claim in eligible:
                memo = (
                    f'Social benefit payment — {claim.claim_reference} '
                    f'({claim.scheme.code}, {claim.beneficiary_name})'
                )
                lines.append(JournalLine(
                    header=header,
                    account=expense_account,
                    debit=claim.amount,
                    credit=Decimal('0'),
                    memo=memo,
                ))
            # Single offsetting credit to the bank account.
            lines.append(JournalLine(
                header=header,
                account=bank_account,
                debit=Decimal('0'),
                credit=result.total_paid,
                memo=(
                    f'Bank disbursement for social-benefit batch '
                    f'{reference} ({len(eligible)} claim(s))'
                ),
            ))
            JournalLine.objects.bulk_create(lines)

            from django.utils import timezone
            now = timezone.now()
            header.status = 'Posted'
            header.posted_at = now
            header.save(update_fields=['status', 'posted_at'])

            # Flip each claim APPROVED → PAID.
            paid_ids: list[int] = []
            for claim in eligible:
                claim.status = 'PAID'
                claim.paid_at = now
                claim.journal_entry = header
                if payment_reference:
                    claim.payment_reference = payment_reference
                elif not claim.payment_reference:
                    claim.payment_reference = reference
                claim.save(update_fields=[
                    'status', 'paid_at', 'journal_entry',
                    'payment_reference', 'updated_at',
                ])
                paid_ids.append(claim.pk)

            result.journal_id = header.pk
            result.journal_reference = header.reference_number
            result.claims_paid = len(eligible)
            result.paid_claim_ids = paid_ids

        return result


def _resolve(settings_obj, attr: str, default: str) -> str:
    if settings_obj is None:
        return default
    val = getattr(settings_obj, attr, None)
    if val is None:
        return default
    stripped = str(val).strip()
    return stripped if stripped else default
