"""Widen the default budget-check rule range and relax to WARNING.

Background
----------
Migration 0080 shipped a STRICT default rule covering only the Personnel
range (21000000–21999999). On tenants whose admins later widened that
rule's range — e.g. to 21000000–22999999 — the original "Personnel
Costs" description stayed in place, producing misleading errors like
``Strict budget control is active for GL 22020309 (Personnel Costs)``
when posting an invoice for Uniforms (a Goods & Services code, not
Personnel). The check itself was technically correct given the rule
data, but the rule data made no sense.

What this migration does
------------------------
Replaces the narrow STRICT Personnel rule with a SINGLE wide rule
covering the entire NCoA expense classification (20000000–29999999) at
WARNING level. Operators get an advisory flag if the appropriation
slot is missing or near-utilised, but posting is not blocked.

Tenant admins can still edit, narrow, disable, or duplicate this rule
through Settings → Budget Check Rules (see
``frontend/src/features/settings/BudgetCheckRulesSettings.tsx``). The
rule is data, not code — the Settings UI is the canonical place to
adjust enforcement policy per tenant. This migration just fixes the
out-of-the-box seed so new tenants don't inherit a too-narrow strict
rule, and existing tenants get aligned.

Idempotent
----------
The migration is safe to re-run: ``get_or_create`` for the new wide
rule, and the cleanup only removes rules whose ``(gl_from, gl_to)``
match the legacy seed's narrow Personnel range AND were never
edited by the tenant (description still contains the legacy
"Personnel Costs" string). User-customised rules are preserved.
"""
from django.db import migrations


WIDE_EXPENSE_RULE = {
    'gl_from': '20000000',
    'gl_to':   '29999999',
    'check_level': 'WARNING',
    'description': (
        'Expenditure (all economic categories) — advisory only. '
        'Edit in Settings → Budget Check Rules to tighten to STRICT '
        'or to split by sub-range.'
    ),
    'priority': 50,
    'warning_threshold_pct': 80.0,
    'is_active': True,
}

LEGACY_PERSONNEL_RULE_BOUNDS = ('21000000', '21999999')
LEGACY_PERSONNEL_DESC_FRAGMENT = 'Personnel Costs'


def widen_default_rule(apps, schema_editor):
    BudgetCheckRule = apps.get_model('accounting', 'BudgetCheckRule')

    # Remove the legacy narrow Personnel STRICT rule, but ONLY if it
    # still carries the seed description — preserves any tenant-edited
    # rule that happens to share the same range bounds.
    BudgetCheckRule.objects.filter(
        gl_from=LEGACY_PERSONNEL_RULE_BOUNDS[0],
        gl_to=LEGACY_PERSONNEL_RULE_BOUNDS[1],
        description__icontains=LEGACY_PERSONNEL_DESC_FRAGMENT,
    ).delete()

    # Seed (or update) the wide WARNING rule. ``update_or_create`` keyed
    # on (gl_from, gl_to) makes this idempotent and lets us refresh the
    # description / level if the rule already exists with stale fields.
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


def reverse_widen_default_rule(apps, schema_editor):
    """Reverse: remove the wide rule and restore the narrow Personnel
    STRICT rule. Mirrors the original 0080 seed shape.
    """
    BudgetCheckRule = apps.get_model('accounting', 'BudgetCheckRule')
    BudgetCheckRule.objects.filter(
        gl_from=WIDE_EXPENSE_RULE['gl_from'],
        gl_to=WIDE_EXPENSE_RULE['gl_to'],
    ).delete()
    BudgetCheckRule.objects.get_or_create(
        gl_from='21000000', gl_to='21999999',
        defaults={
            'check_level': 'STRICT',
            'description': 'Personnel Costs — salaries, allowances, pension contributions',
            'priority': 100,
        },
    )


class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0091_accountingsettings_vendor_registration_revenue_account'),
    ]

    operations = [
        migrations.RunPython(widen_default_rule, reverse_widen_default_rule),
    ]
