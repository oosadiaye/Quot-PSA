"""The report of one dimension: spend by value over posted journals, with the untagged remainder shown, and a drill-down
from a parent value to its children."""
from decimal import Decimal

import pytest

from accounting.models import Account, JournalHeader, JournalLine
from dimensions import services

pytestmark = pytest.mark.django_db(transaction=True)   # posting runs the ledger's balance trigger


def _posted_line(amount, tags, account_type='Expense', status='Posted'):
    acct, _ = Account.objects.get_or_create(
        code='29990002' if account_type == 'Expense' else '19990002',
        defaults=dict(name=f'Dim test {account_type}', account_type=account_type, is_active=True))
    header = JournalHeader.objects.create(description='dim report', status='Draft')
    line = JournalLine.objects.create(header=header, account=acct, debit=amount, credit=0)
    if tags:
        services.set_tags('journal_line', line.pk, tags)
    offset, _ = Account.objects.get_or_create(
        code='19990003', defaults=dict(name='Dim test offset', account_type='Asset', is_active=True))
    JournalLine.objects.create(header=header, account=offset, debit=0, credit=amount)    # a posted journal must balance
    JournalHeader.all_objects.filter(pk=header.pk).update(status=status)
    return line


def _by_code(report):
    return {row['code']: row for row in report['rows']}


def test_spend_by_ward_counts_only_posted_expense_lines_and_shows_the_untagged(zone_ward):
    base = {k: Decimal(v['debit']) for k, v in _by_code(services.dimension_report('ward')).items()}
    _posted_line(100, {'ward': 'W1'})
    _posted_line(40, {'ward': 'W1'})
    _posted_line(70, {'ward': 'W2'})
    _posted_line(999, {'ward': 'W2'}, status='Draft')            # not posted: never counted
    _posted_line(500, {'ward': 'W2'}, account_type='Asset')       # not an expense: never counted
    _posted_line(25, None)                                       # untagged
    rows = _by_code(services.dimension_report('ward'))
    assert Decimal(rows['W1']['debit']) - base.get('W1', 0) == 140
    assert Decimal(rows['W2']['debit']) - base.get('W2', 0) == 70
    assert Decimal(rows['(untagged)']['debit']) - base.get('(untagged)', 0) == 25


def test_drill_down_from_a_zone_to_its_wards(zone_ward):
    _posted_line(60, {'zone': 'Z1', 'ward': 'W1'})
    _posted_line(30, {'zone': 'Z2', 'ward': 'W2'})
    rows = _by_code(services.dimension_report('ward', parent_value='Z1'))
    assert 'W1' in rows and 'W2' not in rows
    assert '(untagged)' not in rows                              # a drill-down lists only that parent's children


def test_a_reversed_journal_and_its_reversal_cancel_out(zone_ward):
    from accounting.models import JournalReversal
    base = _by_code(services.dimension_report('ward')).get('W1', {}).get('debit', '0')
    original = _posted_line(100, {'ward': 'W1'})
    reversal = _posted_line(100, None)                         # the reversing journal's lines carry no tags
    JournalHeader.all_objects.filter(pk=original.header_id).update(is_reversed=True)
    JournalReversal.objects.create(original_journal=original.header, reversal_journal=reversal.header)
    after = _by_code(services.dimension_report('ward'))
    assert Decimal(after['W1']['debit']) == Decimal(base)      # the spend that was reversed is no longer spend
