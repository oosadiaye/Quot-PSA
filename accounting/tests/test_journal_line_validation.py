"""Journal line payload validation — QA findings H-1 and H-2.

Background
----------
``JournalViewSet.create`` computed ``Decimal(str(line['debit']))`` on the
raw request body *before* any line-level validation, then handed the
values straight to ``JournalLine.objects.create``. Two consequences:

H-1  Malformed input crashed with HTTP 500 instead of 400. Three distinct
     mechanisms produced it — a ``decimal.InvalidOperation`` from parsing,
     a ``DoesNotExist`` from an unknown account FK, and ``IntegrityError``
     from the S1-01 DB CheckConstraints. ``JournalLine.clean()`` already
     encodes the same rules with readable messages, but
     ``objects.create()`` never calls ``full_clean()``, so it never ran.

H-2  A journal with ``lines: []`` passed the balance check (0 == 0) and
     was persisted as a line-less GL record.

These tests are pure — they call the validator directly, so they need no
database and no HTTP layer.
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError


@pytest.mark.unit
class TestLineCountRule:
    """H-2 — a journal must have at least two lines."""

    def test_rejects_empty_line_list(self):
        from accounting.services.journal_lines import validate_journal_lines
        with pytest.raises(ValidationError) as exc:
            validate_journal_lines([])
        assert 'at least two lines' in str(exc.value)

    def test_rejects_single_line(self):
        from accounting.services.journal_lines import validate_journal_lines
        with pytest.raises(ValidationError):
            validate_journal_lines([{'account': 1, 'debit': 100, 'credit': 0}])

    def test_rejects_non_list_payload(self):
        from accounting.services.journal_lines import validate_journal_lines
        with pytest.raises(ValidationError):
            validate_journal_lines('not-a-list')


@pytest.mark.unit
class TestAmountParsing:
    """H-1 — the decimal.InvalidOperation path."""

    def test_rejects_non_numeric_debit_naming_the_line(self):
        from accounting.services.journal_lines import validate_journal_lines
        with pytest.raises(ValidationError) as exc:
            validate_journal_lines([
                {'account': 1, 'debit': 'abc', 'credit': 0},
                {'account': 2, 'debit': 0, 'credit': 'abc'},
            ])
        message = str(exc.value)
        assert 'Line 1' in message
        assert 'numeric' in message.lower()

    def test_rejects_non_numeric_credit(self):
        from accounting.services.journal_lines import validate_journal_lines
        with pytest.raises(ValidationError):
            validate_journal_lines([
                {'account': 1, 'debit': 100, 'credit': 0},
                {'account': 2, 'debit': 0, 'credit': 'oops'},
            ])

    def test_treats_missing_amount_as_zero(self):
        """A line may omit the side it doesn't use."""
        from accounting.services.journal_lines import validate_journal_lines
        cleaned = validate_journal_lines([
            {'account': 1, 'debit': 100},
            {'account': 2, 'credit': 100},
        ])
        assert cleaned[0]['debit'] == Decimal('100')
        assert cleaned[0]['credit'] == Decimal('0')

    def test_treats_none_amount_as_zero(self):
        from accounting.services.journal_lines import validate_journal_lines
        cleaned = validate_journal_lines([
            {'account': 1, 'debit': 100, 'credit': None},
            {'account': 2, 'debit': None, 'credit': 100},
        ])
        assert cleaned[1]['debit'] == Decimal('0')


@pytest.mark.unit
class TestDoubleEntryRules:
    """H-1 — the three S1-01 CheckConstraint paths, caught in Python."""

    def test_rejects_negative_debit(self):
        from accounting.services.journal_lines import validate_journal_lines
        with pytest.raises(ValidationError) as exc:
            validate_journal_lines([
                {'account': 1, 'debit': -100, 'credit': 0},
                {'account': 2, 'debit': 0, 'credit': -100},
            ])
        assert 'negative' in str(exc.value).lower()

    def test_rejects_both_debit_and_credit_on_one_line(self):
        from accounting.services.journal_lines import validate_journal_lines
        with pytest.raises(ValidationError) as exc:
            validate_journal_lines([
                {'account': 1, 'debit': 50, 'credit': 50},
                {'account': 2, 'debit': 50, 'credit': 50},
            ])
        assert 'both' in str(exc.value).lower()

    def test_rejects_line_with_neither_debit_nor_credit(self):
        from accounting.services.journal_lines import validate_journal_lines
        with pytest.raises(ValidationError) as exc:
            validate_journal_lines([
                {'account': 1, 'debit': 0, 'credit': 0},
                {'account': 2, 'debit': 0, 'credit': 0},
            ])
        assert 'either a debit or credit' in str(exc.value).lower()

    def test_rejects_missing_account(self):
        from accounting.services.journal_lines import validate_journal_lines
        with pytest.raises(ValidationError) as exc:
            validate_journal_lines([
                {'debit': 100, 'credit': 0},
                {'account': 2, 'debit': 0, 'credit': 100},
            ])
        assert 'account' in str(exc.value).lower()


@pytest.mark.unit
class TestHappyPath:

    def test_returns_cleaned_decimals_in_order(self):
        from accounting.services.journal_lines import validate_journal_lines
        cleaned = validate_journal_lines([
            {'account': 7, 'debit': '100.50', 'credit': 0, 'memo': 'a'},
            {'account': 9, 'debit': 0, 'credit': '100.50', 'memo': 'b'},
        ])
        assert [c['account'] for c in cleaned] == [7, 9]
        assert cleaned[0]['debit'] == Decimal('100.50')
        assert cleaned[1]['credit'] == Decimal('100.50')
        assert cleaned[0]['memo'] == 'a'

    def test_totals_helper_sums_cleaned_lines(self):
        from accounting.services.journal_lines import (
            journal_totals, validate_journal_lines,
        )
        cleaned = validate_journal_lines([
            {'account': 1, 'debit': '60.25', 'credit': 0},
            {'account': 2, 'debit': '39.75', 'credit': 0},
            {'account': 3, 'debit': 0, 'credit': '100.00'},
        ])
        debit, credit = journal_totals(cleaned)
        assert debit == Decimal('100.00')
        assert credit == Decimal('100.00')
