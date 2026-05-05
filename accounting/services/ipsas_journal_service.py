"""
IPSAS Journal Posting Service
=============================
Enforces IPSAS accrual accounting and NCoA compliance for all journal entries.

Works against the ACTUAL model schema:
  - JournalHeader: reference_number, description, posting_date, status (Draft/Posted/etc)
  - JournalLine: header (FK), account (FK to Account), debit, credit, memo
  - TransactionAuditLog: transaction_type, transaction_id, action, user, old_values, new_values

Key guarantees:
1. SUM(DR) = SUM(CR) — enforced before posting
2. Only posting-level accounts allowed (when using NCoA EconomicSegment)
3. No posting to control accounts
4. Immutable once posted (must reverse to correct)
5. Complete audit trail for every status change
"""

from decimal import Decimal
from django.db import transaction
from django.utils import timezone


class JournalPostingError(Exception):
    """Raised when a journal entry fails validation or posting."""
    pass


class IPSASJournalService:
    """
    Central service for all journal posting operations.
    Every financial transaction in the system ultimately creates
    and posts a journal through this service.

    All field references match the actual model schema in accounting/models/gl.py:
      JournalHeader: reference_number, description, status choices = Draft/Pending/Posted/etc
      JournalLine: header (FK), account (FK), debit, credit, memo
    """

    # Status values matching JournalHeader.status choices (title-cased)
    STATUS_DRAFT = 'Draft'
    STATUS_PENDING = 'Pending'
    STATUS_APPROVED = 'Approved'
    STATUS_POSTED = 'Posted'
    STATUS_REJECTED = 'Rejected'

    POSTABLE_STATUSES = (STATUS_DRAFT, STATUS_PENDING, STATUS_APPROVED)

    @staticmethod
    def validate_journal(journal) -> list[str]:
        """
        Validates a journal entry against IPSAS and NCoA rules.
        Returns list of validation errors (empty list = valid).

        Validates against:
        - JournalHeader.lines (related_name='lines' on JournalLine.header FK)
        - JournalLine fields: debit, credit, account, memo
        """
        errors: list[str] = []
        lines = journal.lines.all()
        line_count = lines.count()

        # 1. Minimum 2 lines for double-entry
        if line_count < 2:
            errors.append("Journal must have at least 2 lines (double-entry).")
            return errors  # No point validating balances on empty/single-line journal

        # 2. Balance check — ABSOLUTE REQUIREMENT
        total_dr = Decimal('0')
        total_cr = Decimal('0')
        for idx, line in enumerate(lines, start=1):
            dr = line.debit or Decimal('0')
            cr = line.credit or Decimal('0')
            total_dr += dr
            total_cr += cr

            # 3. No line with both DR and CR > 0
            if dr > 0 and cr > 0:
                errors.append(
                    f"Line {idx}: Cannot have both debit "
                    f"(NGN {dr:,.2f}) and credit (NGN {cr:,.2f})."
                )
            if dr < 0 or cr < 0:
                errors.append(f"Line {idx}: Negative amounts not allowed.")
            if dr == 0 and cr == 0:
                errors.append(f"Line {idx}: Line has zero amount.")

            # 4. NCoA validation — if line has NCoA code, validate economic segment
            if hasattr(line, 'ncoa_code') and line.ncoa_code:
                eco = line.ncoa_code.economic
                if not eco.is_posting_level:
                    errors.append(
                        f"Line {idx}: Account {eco.code} ({eco.name}) "
                        f"is not a posting-level account."
                    )
                if eco.is_control_account:
                    errors.append(
                        f"Line {idx}: Cannot post directly to "
                        f"control account {eco.code} ({eco.name})."
                    )

        if total_dr != total_cr:
            errors.append(
                f"Journal is not balanced. "
                f"Total Debit: NGN {total_dr:,.2f}, Total Credit: NGN {total_cr:,.2f}, "
                f"Difference: NGN {abs(total_dr - total_cr):,.2f}"
            )

        return errors

    @staticmethod
    @transaction.atomic
    def post_journal(journal, user):
        """
        Full validation + posting pipeline.
        Raises JournalPostingError on any failure.

        Args:
            journal: JournalHeader instance
            user: User performing the posting
        Returns:
            The posted JournalHeader instance
        """
        from accounting.models.audit import TransactionAuditLog

        # 1. Validate
        errors = IPSASJournalService.validate_journal(journal)
        if errors:
            raise JournalPostingError(
                "Journal validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
            )

        # 2. Check journal is in correct status
        if journal.status not in IPSASJournalService.POSTABLE_STATUSES:
            raise JournalPostingError(
                f"Cannot post journal with status '{journal.status}'. "
                f"Only Draft, Pending, or Approved journals can be posted."
            )

        # 3. Auto-populate legacy dimension FKs from NCoA bridges
        #    This ensures GLBalance (which uses legacy FKs) stays in sync
        IPSASJournalService._sync_legacy_dimensions(journal)

        # 4. Post the journal
        old_status = journal.status
        journal.status = IPSASJournalService.STATUS_POSTED
        journal.posted_by = user
        journal.posted_at = timezone.now()
        journal.save(update_fields=['status', 'posted_by', 'posted_at', 'updated_at'])

        # 4. Update GL balances
        IPSASJournalService._update_gl_balances(journal)

        # 5. Audit log — using actual TransactionAuditLog field names
        lines = journal.lines.all()
        total_dr = sum((line.debit or Decimal('0')) for line in lines)
        total_cr = sum((line.credit or Decimal('0')) for line in lines)
        TransactionAuditLog.objects.create(
            transaction_type='JE',
            transaction_id=journal.pk,
            action='POST',
            user=user,
            username=user.username if user else '',
            old_values={'status': old_status},
            new_values={
                'status': IPSASJournalService.STATUS_POSTED,
                'total_debit': str(total_dr),
                'total_credit': str(total_cr),
                'line_count': lines.count(),
            },
            description=f"Posted journal {journal.reference_number}",
            reference_number=journal.reference_number or '',
        )

        return journal

    @staticmethod
    @transaction.atomic
    def reverse_journal(journal, user, reason: str):
        """
        Reverse a posted journal entry (IPSAS does not allow deletion).
        Creates a new JournalHeader with inverted DR/CR lines.

        Uses actual field names:
          JournalHeader: reference_number, description, posting_date, status
          JournalLine: header (FK), account, debit, credit, memo
        """
        from accounting.models.audit import TransactionAuditLog
        from accounting.models.gl import JournalHeader, JournalLine

        if journal.status != IPSASJournalService.STATUS_POSTED:
            raise JournalPostingError(
                f"Only Posted journals can be reversed. "
                f"Current status: {journal.status}"
            )

        if not reason:
            raise JournalPostingError("Reversal reason is required.")

        # Create reversal journal header
        reversal = JournalHeader(
            reference_number=f"REV-{journal.reference_number}",
            description=f"Reversal of {journal.reference_number}: {reason}",
            posting_date=timezone.now().date(),
            status=IPSASJournalService.STATUS_DRAFT,
            source_module='reversal',
            source_document_id=journal.pk,
            # Carry over dimensional FKs from original header
            mda=journal.mda,
            fund=journal.fund,
            function=journal.function,
            program=journal.program,
            geo=journal.geo,
        )
        reversal.save()

        # Create reversed lines (swap DR/CR)
        for line in journal.lines.all():
            JournalLine.objects.create(
                header=reversal,         # FK field is 'header', not 'journal'
                account=line.account,    # FK to Account
                debit=line.credit,       # Swap: original credit becomes debit
                credit=line.debit,       # Swap: original debit becomes credit
                memo=f"Reversal: {line.memo}",
            )

        # Post the reversal
        IPSASJournalService.post_journal(reversal, user)

        # Mark original as reversed
        journal.is_reversed = True
        journal.save(update_fields=['is_reversed', 'updated_at'])

        # Create reversal audit record via JournalReversal model
        from accounting.models.gl import JournalReversal
        JournalReversal.objects.create(
            original_journal=journal,
            reversal_journal=reversal,
            reversal_type='Reverse',
            reason=reason,
            reversed_by=user,
        )

        # Audit log
        TransactionAuditLog.objects.create(
            transaction_type='REV',
            transaction_id=journal.pk,
            action='REVERSE',
            user=user,
            username=user.username if user else '',
            old_values={'is_reversed': False},
            new_values={
                'is_reversed': True,
                'reason': reason,
                'reversal_reference': reversal.reference_number,
            },
            description=f"Reversed journal {journal.reference_number}",
            reference_number=journal.reference_number or '',
        )

        return reversal

    @staticmethod
    def _update_gl_balances(journal):
        """
        Update GL account balances after posting.
        Uses the existing GLBalance model with its actual field names.

        GLBalance has: account, fund, function, program, geo,
                       debit_balance, credit_balance, fiscal_year, period

        Raises ``TransactionPostingError`` (via assert_balanced) if the
        journal violates double-entry — same chokepoint as
        ``update_gl_from_journal`` and
        ``BasePostingService._update_gl_balances`` so every posting
        path goes through the same invariant.
        """
        from accounting.models.balances import GLBalance
        from accounting.services.base_posting import BasePostingService
        from django.db.models import F

        # Mandatory double-entry assertion.
        BasePostingService.assert_balanced(journal)

        # Extract fiscal year and period from posting date
        fiscal_year = journal.posting_date.year
        period = journal.posting_date.month

        for line in journal.lines.select_related('account').all():
            account = line.account
            if account is None:
                continue

            # Get dimensional context from the journal header
            header = journal
            # S3-05 — carry the MDA dimension onto each GLBalance bucket
            # so per-MDA Trial Balance / Balance Sheet filters include
            # accrual postings made via this service (IPC accruals,
            # IPSAS-spec'd journals). Without this the
            # ``unique_together`` (which includes ``mda``) routes these
            # postings to a ``mda=None`` ghost row that no per-MDA
            # filter ever surfaces. We use the journal header's MDA as
            # the single source — the legacy per-line ``cost_center``
            # override has been removed from this project.
            line_mda = header.mda

            # Get or create GL balance record (must include fiscal_year + period
            # AND mda to satisfy GLBalance unique_together constraint)
            balance, _ = GLBalance.objects.get_or_create(
                account=account,
                fund=header.fund,
                function=header.function,
                program=header.program,
                geo=header.geo,
                mda=line_mda,
                fiscal_year=fiscal_year,
                period=period,
                defaults={
                    'debit_balance': Decimal('0'),
                    'credit_balance': Decimal('0'),
                },
            )

            # Atomic increment using F() to avoid race conditions
            GLBalance.objects.filter(pk=balance.pk).update(
                debit_balance=F('debit_balance') + (line.debit or Decimal('0')),
                credit_balance=F('credit_balance') + (line.credit or Decimal('0')),
            )

        # Bust the IPSAS report cache so every Financial Position /
        # Financial Performance / Cash Flow / Changes in Net Assets /
        # Notes / Budget Performance / Revenue Performance / Functional
        # / Programme / Geographic / Fund Performance report drops its
        # cached entry and recomputes on next read.
        try:
            from accounting.services.report_cache import invalidate_period_reports
            invalidate_period_reports(fiscal_year=fiscal_year)
        except Exception:  # noqa: BLE001 — cache invalidation is best-effort
            pass

    @staticmethod
    def _sync_legacy_dimensions(journal):
        """
        Auto-populate legacy dimension FKs on JournalHeader from NCoA bridges.
        This ensures GLBalance (which uses legacy Fund/Function/Program/Geo FKs)
        stays in sync when transactions use the NCoA code path.
        """
        ncoa_line = journal.lines.filter(ncoa_code__isnull=False).first()
        if not ncoa_line or not ncoa_line.ncoa_code:
            return

        ncoa = ncoa_line.ncoa_code
        updated_fields = []

        # Fund bridge
        if ncoa.fund and hasattr(ncoa.fund, 'legacy_fund') and ncoa.fund.legacy_fund:
            if not journal.fund:
                journal.fund = ncoa.fund.legacy_fund
                updated_fields.append('fund')

        # Function bridge
        if ncoa.functional and hasattr(ncoa.functional, 'legacy_function') and ncoa.functional.legacy_function:
            if not journal.function:
                journal.function = ncoa.functional.legacy_function
                updated_fields.append('function')

        # Program bridge
        if ncoa.programme and hasattr(ncoa.programme, 'legacy_program') and ncoa.programme.legacy_program:
            if not journal.program:
                journal.program = ncoa.programme.legacy_program
                updated_fields.append('program')

        # Geo bridge
        if ncoa.geographic and hasattr(ncoa.geographic, 'legacy_geo') and ncoa.geographic.legacy_geo:
            if not journal.geo:
                journal.geo = ncoa.geographic.legacy_geo
                updated_fields.append('geo')

        # MDA bridge
        if ncoa.administrative and hasattr(ncoa.administrative, 'legacy_mda') and ncoa.administrative.legacy_mda:
            if not journal.mda:
                journal.mda = ncoa.administrative.legacy_mda
                updated_fields.append('mda')

        if updated_fields:
            updated_fields.append('updated_at')
            journal.save(update_fields=updated_fields)
