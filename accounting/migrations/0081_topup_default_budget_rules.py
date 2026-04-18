"""Top up the default BudgetCheckRule set on tenants that migrated
through 0080 before the 3 extra ranges were added (Revenue / Assets /
Liabilities). Safe to apply anywhere — uses get_or_create.
"""
from django.db import migrations


EXTRA_DEFAULTS = [
    {
        'gl_from': '10000000', 'gl_to': '19999999',
        'check_level': 'NONE',
        'description': 'Revenue — no budget gating (statistical vs. RevenueBudget targets)',
        'priority': 10,
    },
    {
        'gl_from': '30000000', 'gl_to': '39999999',
        'check_level': 'WARNING',
        'description': 'Assets — warning-only; admin may raise to strict',
        'priority': 20,
    },
    {
        'gl_from': '40000000', 'gl_to': '49999999',
        'check_level': 'WARNING',
        'description': 'Liabilities — warning-only',
        'priority': 20,
    },
]


def topup(apps, schema_editor):
    BudgetCheckRule = apps.get_model('accounting', 'BudgetCheckRule')
    for rule in EXTRA_DEFAULTS:
        BudgetCheckRule.objects.get_or_create(
            gl_from=rule['gl_from'], gl_to=rule['gl_to'],
            defaults={
                'check_level': rule['check_level'],
                'description': rule['description'],
                'priority': rule['priority'],
            },
        )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [('accounting', '0080_budgetcheckrule')]
    operations = [migrations.RunPython(topup, noop_reverse)]
