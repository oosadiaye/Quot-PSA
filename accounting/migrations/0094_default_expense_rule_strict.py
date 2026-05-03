"""Flip the default expense rule (20000000-29999999) from WARNING to STRICT.

Background
----------
Migration 0092 seeded a single wide WARNING rule covering the entire
NCoA expense classification (Personnel 21x, Goods 22x, Capital 23x,
Subsidies 25x, Grants 26x, Social Benefits 27x, Other Expenses 28x).
WARNING is permissive — postings succeed even when no appropriation
exists, with only an advisory note. The Office of Accountant General
operating policy requires STRICT control on expense postings: no
appropriation, no posting.

This migration replaces the rule's ``check_level`` from WARNING to
STRICT for the same range, and refreshes the description so the
Settings UI shows the new policy stance to operators.

Future tenants
--------------
Newly-provisioned tenants run the migration chain in order:

    0080  → seeds the narrow Personnel STRICT rule (legacy)
    0092  → adds the wide WARNING rule on 20000000–29999999
    0094  → (this) flips that wide rule to STRICT

End state for any tenant — present or future — is the same: a single
wide STRICT rule covering all expense categories. Tenant admins can
still narrow / override / split the rule through Settings → Budget
Check Rules; the seed only sets the floor.

Idempotent
----------
``update_or_create`` keyed on ``(gl_from, gl_to)`` — re-running the
migration after a manual edit in Settings will overwrite the level
back to STRICT. If a tenant explicitly relaxes this in Settings the
choice is recorded in the BudgetCheckRule table and survives normal
operation; this migration only fires when explicitly run again.
"""
from django.db import migrations


WIDE_EXPENSE_RULE = {
    'gl_from': '20000000',
    'gl_to':   '29999999',
    'check_level': 'STRICT',
    # ``description`` field is CharField(max_length=200) — keep
    # under the cap. UI surfaces the full message via the rule list
    # row + tooltip; the long-form rationale lives in this migration's
    # docstring.
    'description': (
        'Expenditure (all economic categories) — STRICT. Posting '
        'requires an active appropriation. Edit in Settings to relax '
        'or split.'
    ),
    'priority': 50,
    'warning_threshold_pct': 80.0,
    'is_active': True,
}


def tighten_default_rule(apps, schema_editor):
    BudgetCheckRule = apps.get_model('accounting', 'BudgetCheckRule')
    BudgetCheckRule.objects.update_or_create(
        gl_from=WIDE_EXPENSE_RULE['gl_from'],
        gl_to=WIDE_EXPENSE_RULE['gl_to'],
        defaults={
            'check_level': WIDE_EXPENSE_RULE['check_level'],
            'description': WIDE_EXPENSE_RULE['description'],
            'priority': WIDE_EXPENSE_RULE['priority'],
            'warning_threshold_pct': WIDE_EXPENSE_RULE['warning_threshold_pct'],
            'is_active': WIDE_EXPENSE_RULE['is_active'],
        },
    )


def relax_to_warning(apps, schema_editor):
    """Reverse: revert to the 0092 WARNING shape so a roll-back
    leaves the rule in the state 0092 produced.
    """
    BudgetCheckRule = apps.get_model('accounting', 'BudgetCheckRule')
    BudgetCheckRule.objects.update_or_create(
        gl_from=WIDE_EXPENSE_RULE['gl_from'],
        gl_to=WIDE_EXPENSE_RULE['gl_to'],
        defaults={
            'check_level': 'WARNING',
            'description': (
                'Expenditure (all economic categories) — advisory only. '
                'Edit in Settings → Budget Check Rules to tighten to STRICT '
                'or to split by sub-range.'
            ),
            'priority': 50,
            'warning_threshold_pct': 80.0,
            'is_active': True,
        },
    )


class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0093_backfill_journal_document_number'),
    ]

    operations = [
        migrations.RunPython(tighten_default_rule, relax_to_warning),
    ]
