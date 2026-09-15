"""Finish 0121: the remaining NCoA group roots become headers too.

0121 flagged NCoA group roots (8 digits ending in six zeros) as header
accounts but skipped any that already carried journal lines, because
doing so would have stranded those journals — ``post_journal`` applied
the header guard to reversals as well, so an account re-classified after
a posting could never be unwound.

That gap is now closed: a reversal is exempt from the classification
gates, since its lines are copied from an original whose account choice
was legal when it was made. See
``accounting/tests/test_reversal_survives_reclassification.py``.

With reversibility preserved there is no reason to leave a group root
postable. ``20000000 Expenditure`` is not a line an MDA spends against
under NCoA, whatever has been posted to it, and leaving it selectable in
the contract GL picker is the same fault as the GR/IR clearing account
that migration 0115 dealt with.

Existing journal lines are not touched. Those postings happened and IPSAS
keeps them; the flag governs what may be posted from here on.
"""
from django.db import migrations


def forwards(apps, schema_editor):
    Account = apps.get_model('accounting', 'Account')

    flagged = []
    for account in Account.objects.filter(is_postable=True):
        code = account.code or ''
        if len(code) == 8 and code.isdigit() and code.endswith('000000'):
            account.is_postable = False
            account.save(update_fields=['is_postable'])
            flagged.append(code)

    if flagged:
        print(f'  Flagged {len(flagged)} remaining NCoA group account(s) as '
              f'headers: ' + ', '.join(sorted(flagged)))


class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0121_ncoa_group_accounts_are_headers'),
    ]

    operations = [
        # No reverse, for the same reason as 0121: the previous value was
        # the field default rather than a deliberate setting, so restoring
        # it would re-introduce the fault rather than undo a change.
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
