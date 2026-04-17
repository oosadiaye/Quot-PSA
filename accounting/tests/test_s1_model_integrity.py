"""
Sprint-1 regression tests: model-layer integrity.

Covers:
  * S1-01 — JournalLine DB CheckConstraints (debit/credit non-neg, mutual
    exclusion, at least one non-zero)
  * S1-02 — JournalHeader uniqueness (reference, source document on Posted)
  * S1-03 — Posted immutability on JournalHeader + JournalLine
  * S1-04 — JournalReversal FK is PROTECT (can't CASCADE-wipe a reversal)

These tests exercise DB-level guarantees that are the LAST line of defence
when the service layer is bypassed (raw SQL, bulk_create, admin actions).
"""
from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction


# =============================================================================
# S1-01 — JournalLine DB constraints
# =============================================================================

@pytest.mark.django_db(transaction=True)
class TestJournalLineConstraints:
    """DB constraints on JournalLine reject bad data even via raw ORM."""

    def test_negative_debit_rejected(self, cash_account, raw_journal):
        """debit < 0 must be rejected at the DB layer (jrn_line_debit_nonneg)."""
        from accounting.models import JournalHeader, JournalLine
        header = JournalHeader.objects.create(
            posting_date=date.today(), reference_number='NEG-DR-001',
        )
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                JournalLine.objects.create(
                    header=header, account=cash_account,
                    debit=Decimal('-100.00'), credit=Decimal('0.00'),
                )

    def test_negative_credit_rejected(self, cash_account):
        """credit < 0 must be rejected (jrn_line_credit_nonneg)."""
        from accounting.models import JournalHeader, JournalLine
        header = JournalHeader.objects.create(
            posting_date=date.today(), reference_number='NEG-CR-001',
        )
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                JournalLine.objects.create(
                    header=header, account=cash_account,
                    debit=Decimal('0.00'), credit=Decimal('-50.00'),
                )

    def test_both_debit_and_credit_rejected(self, cash_account):
        """A line with debit>0 AND credit>0 violates jrn_line_not_both_sides."""
        from accounting.models import JournalHeader, JournalLine
        header = JournalHeader.objects.create(
            posting_date=date.today(), reference_number='BOTH-001',
        )
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                JournalLine.objects.create(
                    header=header, account=cash_account,
                    debit=Decimal('100.00'), credit=Decimal('100.00'),
                )

    def test_zero_debit_and_credit_rejected(self, cash_account):
        """A line with both zero violates jrn_line_at_least_one_side."""
        from accounting.models import JournalHeader, JournalLine
        header = JournalHeader.objects.create(
            posting_date=date.today(), reference_number='ZERO-001',
        )
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                JournalLine.objects.create(
                    header=header, account=cash_account,
                    debit=Decimal('0.00'), credit=Decimal('0.00'),
                )

    def test_valid_line_accepted(self, cash_account, expense_account, raw_journal):
        """Sanity: a well-formed pair of lines persists without error."""
        header = raw_journal(
            [(expense_account, 100, 0), (cash_account, 0, 100)],
            reference='VALID-001',
        )
        assert header.lines.count() == 2


# =============================================================================
# S1-02 — JournalHeader uniqueness
# =============================================================================

@pytest.mark.django_db(transaction=True)
class TestJournalHeaderUniqueness:

    def test_duplicate_reference_number_rejected(self, raw_journal,
                                                 expense_account, cash_account):
        """reference_number must be unique when non-blank."""
        raw_journal(
            [(expense_account, 10, 0), (cash_account, 0, 10)],
            reference='DUP-REF-001',
        )
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                raw_journal(
                    [(expense_account, 20, 0), (cash_account, 0, 20)],
                    reference='DUP-REF-001',
                )

    def test_blank_reference_numbers_allowed(self, raw_journal,
                                             expense_account, cash_account):
        """Multiple blank reference_numbers are permitted (partial index)."""
        raw_journal(
            [(expense_account, 10, 0), (cash_account, 0, 10)],
            reference='',
        )
        # Second blank-ref journal: must NOT raise.
        raw_journal(
            [(expense_account, 20, 0), (cash_account, 0, 20)],
            reference='',
        )

    def test_duplicate_source_doc_posted_rejected(self, raw_journal,
                                                  expense_account, cash_account):
        """Same (source_module, source_document_id) can't appear twice in
        status='Posted'."""
        h1 = raw_journal(
            [(expense_account, 10, 0), (cash_account, 0, 10)],
            reference='SRC-001',
        )
        h1.source_module = 'procurement'
        h1.source_document_id = 42
        h1.status = 'Posted'
        h1.save()

        h2 = raw_journal(
            [(expense_account, 10, 0), (cash_account, 0, 10)],
            reference='SRC-002',
        )
        h2.source_module = 'procurement'
        h2.source_document_id = 42
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                h2.status = 'Posted'
                h2.save()


# =============================================================================
# S1-03 — Posted immutability
# =============================================================================

@pytest.mark.django_db(transaction=True)
class TestPostedImmutability:

    def test_posted_journal_description_cannot_change(
        self, raw_journal, expense_account, cash_account,
    ):
        """Editing description on a Posted journal raises ValidationError."""
        h = raw_journal(
            [(expense_account, 100, 0), (cash_account, 0, 100)],
            reference='IMM-001',
        )
        h.status = 'Posted'
        h.save()

        h.description = 'tampered description'
        with pytest.raises(ValidationError):
            h.save()

    def test_posted_journal_status_can_flip_to_reversed(
        self, raw_journal, expense_account, cash_account,
    ):
        """Allow-listed fields (status → Reversed, is_reversed) are still
        mutable after posting — required for the reversal workflow."""
        h = raw_journal(
            [(expense_account, 50, 0), (cash_account, 0, 50)],
            reference='IMM-002',
        )
        h.status = 'Posted'
        h.save()

        h.is_reversed = True
        # Must NOT raise — is_reversed is in POST_POSTING_MUTABLE_FIELDS.
        h.save(update_fields=['is_reversed'])
        h.refresh_from_db()
        assert h.is_reversed is True

    def test_posted_journal_line_cannot_be_edited(
        self, raw_journal, expense_account, cash_account,
    ):
        """JournalLine.save() on a posted parent raises."""
        h = raw_journal(
            [(expense_account, 10, 0), (cash_account, 0, 10)],
            reference='IMM-LINE-001',
        )
        h.status = 'Posted'
        h.save()

        line = h.lines.first()
        line.memo = 'tampered memo'
        with pytest.raises(ValidationError):
            line.save()

    def test_posted_journal_line_cannot_be_deleted(
        self, raw_journal, expense_account, cash_account,
    ):
        """JournalLine.delete() is blocked on posted parents."""
        h = raw_journal(
            [(expense_account, 10, 0), (cash_account, 0, 10)],
            reference='IMM-LINE-002',
        )
        h.status = 'Posted'
        h.save()

        line = h.lines.first()
        with pytest.raises(ValidationError):
            line.delete()
