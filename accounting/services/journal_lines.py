"""Validation for the raw journal-line payload, before any arithmetic.

Why this module exists
----------------------
``JournalViewSet.create`` used to parse ``Decimal(str(line['debit']))``
straight off the request body and then call
``JournalLine.objects.create(...)``. That ordering produced HTTP 500s for
every kind of bad input, via three separate mechanisms:

* ``decimal.InvalidOperation`` — a non-numeric amount blew up in the
  balance calculation before anything was validated.
* ``Account.DoesNotExist`` — an unknown ``account`` id failed on insert.
* ``IntegrityError`` — the S1-01 CheckConstraints (``jrn_line_debit_nonneg``,
  ``jrn_line_not_both_sides``, ``jrn_line_at_least_one_side``) rejected the
  row at the database layer.

``JournalLine.clean()`` already expresses the same double-entry rules with
readable messages, but ``objects.create()`` does not call ``full_clean()``,
so it never ran. Rather than sprinkle ``full_clean()`` calls around, this
module validates the payload up front and hands back parsed ``Decimal``
values the caller can safely sum.

Keeping it out of the view (and out of DRF) means it is testable without a
database or an HTTP request — see ``test_journal_line_validation.py``.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

from django.core.exceptions import ValidationError

MIN_LINES = 2


def _parse_amount(raw: Any, line_number: int, side: str) -> Decimal:
    """Parse one side of a line, or raise a message naming the line."""
    if raw is None or raw == '':
        return Decimal('0')
    try:
        return Decimal(str(raw))
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError(
            f'Line {line_number}: {side} must be numeric — got {raw!r}.'
        )


def validate_journal_lines(lines_data: Any) -> list[dict]:
    """Validate the raw ``lines`` payload and return cleaned line dicts.

    Raises ``django.core.exceptions.ValidationError`` naming the offending
    line. Returns a list of dicts with ``account``/``debit``/``credit``/
    ``memo``, amounts already coerced to ``Decimal``.

    Account *existence* is not checked here — that needs a database and is
    handled by the caller, which already has the queryset in hand.
    """
    if not isinstance(lines_data, (list, tuple)):
        raise ValidationError(
            'lines must be a list of journal lines.'
        )

    if len(lines_data) < MIN_LINES:
        # H-2: a zero-line journal used to pass the balance check (0 == 0)
        # and persist as a line-less GL record.
        raise ValidationError(
            f'A journal needs at least two lines (got {len(lines_data)}). '
            f'Double entry requires a debit and a matching credit.'
        )

    cleaned: list[dict] = []
    for index, line in enumerate(lines_data, start=1):
        if not isinstance(line, dict):
            raise ValidationError(f'Line {index}: expected an object.')

        account = line.get('account')
        if account in (None, ''):
            raise ValidationError(f'Line {index}: account is required.')

        debit = _parse_amount(line.get('debit'), index, 'debit')
        credit = _parse_amount(line.get('credit'), index, 'credit')

        # Mirrors JournalLine.clean() and the S1-01 DB constraints, but in
        # Python so the operator gets a 400 with a readable message.
        if debit < 0 or credit < 0:
            raise ValidationError(
                f'Line {index}: amounts cannot be negative '
                f'(debit {debit}, credit {credit}).'
            )
        if debit > 0 and credit > 0:
            raise ValidationError(
                f'Line {index}: a journal line cannot have both debit and '
                f'credit amounts.'
            )
        if debit == 0 and credit == 0:
            raise ValidationError(
                f'Line {index}: a journal line must have either a debit or '
                f'credit amount.'
            )

        cleaned.append({
            'account': account,
            'debit': debit,
            'credit': credit,
            'memo': line.get('memo', '') or '',
            'asset': line.get('asset'),
        })

    return cleaned


def journal_totals(cleaned_lines: Iterable[dict]) -> tuple[Decimal, Decimal]:
    """Sum the debit and credit sides of already-validated lines."""
    total_debit = Decimal('0')
    total_credit = Decimal('0')
    for line in cleaned_lines:
        total_debit += line['debit']
        total_credit += line['credit']
    return total_debit, total_credit


def assert_accounts_exist(cleaned_lines: list[dict]) -> None:
    """Reject unknown or non-postable accounts with a 400-able message.

    Separated from ``validate_journal_lines`` because it needs the DB; kept
    here so the whole line-validation story lives in one place.
    """
    from accounting.models import Account

    wanted = {line['account'] for line in cleaned_lines}
    found = {
        pk: (code, name, postable)
        for pk, code, name, postable in Account.objects.filter(
            pk__in=wanted
        ).values_list('id', 'code', 'name', 'is_postable')
    }

    missing = sorted(w for w in wanted if w not in found)
    if missing:
        raise ValidationError(
            f'Unknown account id(s): {missing}. Pick accounts from the '
            f'chart of accounts.'
        )

    for index, line in enumerate(cleaned_lines, start=1):
        code, name, postable = found[line['account']]
        if not postable:
            raise ValidationError(
                f'Line {index}: account {code} ({name}) is a header / group '
                f'account and cannot be posted to directly. Pick one of its '
                f'leaf descendants instead.'
            )
