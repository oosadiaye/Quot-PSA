"""Make the out-of-the-box budget control a STRICT hard stop.

Background
----------
Migration 0092 seeded the wide expenditure rule (20000000–29999999) at
WARNING level, so by default an operator could post an unbudgeted or
over-budget expense and only see an advisory banner. For a public-sector
system this violates the statutory control "no appropriation, no
expenditure" (IPSAS 24 / Constitution §81).

What this migration does
------------------------
Flips the *seed* wide expenditure rule to STRICT. To avoid overriding a
tenant's deliberate policy choice, it only changes rules that still carry
the seed description written by 0092 (i.e. the tenant has not customised
it via Settings -> Budget Check Rules). Tenant-edited rules are left
untouched.

This is idempotent and safe to re-run.
"""
from django.db import migrations


WIDE_EXPENSE_RULE = {'gl_from': '20000000', 'gl_to': '29999999'}


def enforce_strict_default(apps, schema_editor):
    BudgetCheckRule = apps.get_model('accounting', 'BudgetCheckRule')
    qs = BudgetCheckRule.objects.filter(
        gl_from=WIDE_EXPENSE_RULE['gl_from'],
        gl_to=WIDE_EXPENSE_RULE['gl_to'],
    )
    for rule in qs:
        desc = rule.description or ''
        # Only flip rules that still match the 0092 seed wording.
        if 'advisory only' in desc or 'Edit in Settings' in desc:
            rule.check_level = 'STRICT'
            rule.description = (
                'Expenditure (all economic categories) — STRICT. '
                'Posting is blocked when the appropriation slot is '
                'exhausted. Edit in Settings -> Budget Check Rules to '
                'relax per tenant.'
            )
            rule.save()


def reverse_enforce_strict_default(apps, schema_editor):
    BudgetCheckRule = apps.get_model('accounting', 'BudgetCheckRule')
    BudgetCheckRule.objects.filter(
        gl_from=WIDE_EXPENSE_RULE['gl_from'],
        gl_to=WIDE_EXPENSE_RULE['gl_to'],
    ).update(
        check_level='WARNING',
        description=(
            'Expenditure (all economic categories) — advisory only. '
            'Edit in Settings -> Budget Check Rules to tighten to '
            'STRICT or to split by sub-range.'
        ),
    )


class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0109_paymentbatch_paymentbatchline_and_more'),
    ]

    operations = [
        migrations.RunPython(
            enforce_strict_default, reverse_enforce_strict_default
        ),
    ]
