"""NCoA family and sub-family roots are headers, not posting accounts.

Surfaced by the EconomicSegment merge rather than caused by it. The
contract GL picker used to read the mirror table's ``is_posting_level``;
it now reads the GL's own ``is_postable``, and on several tenants the two
disagreed. The mirror said "header", the GL said "postable", and with the
mirror gone the group accounts started appearing in a picker that had
never offered them.

The GL's flag is the wrong one. In NCoA an 8-digit code ending in six
zeros is a structural roll-up level:

    X0000000   family root      e.g. 20000000 Expenditure
    XY000000   sub-family root  e.g. 21000000 Personnel Costs

Neither is a line an MDA can spend against. They aggregate their
children, which is exactly what ``is_postable=False`` means. The rows
predate the flag: ``seed_ncoa_as_coa`` created them without setting it,
so they took the field default of True.

Only accounts with NO journal lines are changed
-----------------------------------------------
A group account that already carries postings is evidence the tenant
treats it as a posting account, whatever its code shape says. Flipping
the flag under an account in active use would reject the next reversal
of a journal that posted to it perfectly legally yesterday. Those rows
are left alone and listed in the migration output so an operator can
decide; silently re-classifying an account somebody is posting to is not
this migration's call to make.
"""
from django.db import migrations


def _group_roots(Account):
    """Active, postable accounts whose code is an 8-digit NCoA group root."""
    return [
        a for a in Account.objects.filter(is_postable=True)
        if len(a.code) == 8 and a.code.isdigit() and a.code.endswith('000000')
    ]


def forwards(apps, schema_editor):
    Account = apps.get_model('accounting', 'Account')
    JournalLine = apps.get_model('accounting', 'JournalLine')

    flagged, in_use = [], []
    for account in _group_roots(Account):
        if JournalLine.objects.filter(account_id=account.pk).exists():
            in_use.append(account.code)
            continue
        account.is_postable = False
        account.save(update_fields=['is_postable'])
        flagged.append(account.code)

    if flagged:
        print(f'  Flagged {len(flagged)} NCoA group account(s) as headers: '
              + ', '.join(sorted(flagged)))
    if in_use:
        print(f'  Left {len(in_use)} group account(s) postable because they '
              f'already carry journal lines: ' + ', '.join(sorted(in_use)))


class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0120_retire_economic_segment'),
    ]

    operations = [
        # No reverse: the pre-migration value was the field default, not a
        # deliberate setting, so "restoring" it would re-introduce the bug
        # rather than undo a change. An operator who genuinely wants one of
        # these postable can toggle it on the Chart of Accounts screen.
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
