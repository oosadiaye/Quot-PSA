"""
Add SAP-style ``is_postable`` flag to ``Account``.

Default ``True`` so existing rows continue to behave as posting accounts.
The data migration immediately following the schema change inspects the
parent/child hierarchy: any account that already has at least one child
is a header by definition (its role is to roll up the children's
balances) and gets ``is_postable=False``. Leaf accounts are left
unchanged at the default ``True``.

This pattern mirrors SAP's "Block for Posting" / "Group account"
distinction: parent accounts aggregate, leaves carry the actual
debits/credits. Post-migration, journal lines, AP invoices, and payment
vouchers can no longer target a header account directly — they must use
one of its leaf descendants.

Reverse: ``RunPython.noop`` because rolling back this distinction would
require knowing which accounts were *manually* converted to headers
after the migration vs. backfilled here. Schema reversal (``RemoveField``)
is enough to restore the pre-migration shape.
"""

from django.db import migrations, models


def backfill_is_postable_for_existing_parents(apps, schema_editor):
    """Set ``is_postable=False`` on every account that has children."""
    Account = apps.get_model('accounting', 'Account')
    # Single round-trip: collect distinct parent_ids in active accounts,
    # then update those rows. Counts both active and inactive children
    # as evidence the account is a header — once an account has been
    # used as a parent, posting to it directly is unsafe regardless of
    # whether the children are currently active.
    parent_ids = (
        Account.objects.exclude(parent__isnull=True)
        .values_list('parent_id', flat=True)
        .distinct()
    )
    parent_ids = [pid for pid in parent_ids if pid is not None]
    if parent_ids:
        Account.objects.filter(pk__in=parent_ids).update(is_postable=False)


class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0100_treasuryaccount_uniq_main_tsa_per_mda_active'),
    ]

    operations = [
        migrations.AddField(
            model_name='account',
            name='is_postable',
            field=models.BooleanField(
                db_index=True,
                default=True,
                help_text=(
                    'When False, this account is a header / group account: it '
                    'aggregates the balances of its children but cannot be the '
                    'target of any journal line. Operators must post to a leaf '
                    'descendant. Mirrors SAP\'s "Block for Posting" flag. The '
                    'data migration sets this False for any account that has '
                    'child accounts at upgrade time.'
                ),
            ),
        ),
        migrations.RunPython(
            backfill_is_postable_for_existing_parents,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
