"""Relocate GR/IR Clearing & Due-to-Other-Funds from 2-series to 4-series.

Background
----------
Nigerian PSA / NCoA reserves the ``2xxxxxxx`` code range for the Expense
account family and ``4xxxxxxx`` for Liabilities. AccountSerializer
(`accounting/serializers.py:128`) enforces this at write time:

    NIGERIA_COA_SERIES = {
        '1': 'Income',
        '2': 'Expense',
        '3': 'Asset',
        '4': 'Liability',
    }

The legacy ``seed_coa.py`` placed two clearing-style liabilities under
``2060xxxx``:

    20600000 — Due to Other Funds        (Liability)
    20601000 — GR/IR Clearing Account    (Liability)

These passed the seed because the seed creates rows directly via the
ORM (no serializer). But every operator who later tries to create OR
edit either account through the API hits a hard validation rejection:

    "Nigeria CoA violation: account code '20600000' starts with '2'
     — that prefix is reserved for Expense accounts, but the selected
     account type is Liability."

This migration renames the existing rows to NCoA-compliant 4-series
codes:

    20600000 → 41080000   Due to Other Funds        (Liability)
    20601000 → 41090000   GR/IR Clearing Account    (Liability)

The matching seed_coa.py update + DEFAULT_GL_ACCOUNTS settings change
ensure new tenants get the right codes from day one and the
procurement-posting service looks up the right code at runtime.

Why a rename, not a new-row + delete pair
-----------------------------------------
``Account.pk`` (not ``Account.code``) is the FK target on every
JournalLine, BankAccount.gl_account, AccountingSettings FK, and so on.
Renaming the code preserves every existing journal posting and FK
reference; deleting and re-creating would orphan them.

Idempotent
----------
``filter().update()`` is a no-op when the source code doesn't exist,
which is the case for tenants that were provisioned via the NCoA
flow (no seed_coa.py). Tenants that DID run seed_coa.py get the
single-row UPDATE. Re-running the migration after a rollback won't
fail because the target code (41080000 / 41090000) is also empty.
"""
from django.db import migrations


# (old_code, new_code, expected_name_substring_for_safety)
RENAMES = [
    ('20600000', '41080000', 'Due to Other Funds'),
    ('20601000', '41090000', 'GR/IR Clearing'),
]


def relocate_codes(apps, schema_editor):
    Account = apps.get_model('accounting', 'Account')
    for old_code, new_code, name_hint in RENAMES:
        # Skip if the new code already exists (someone already migrated
        # manually or a different tenant has its own NCoA layout where
        # 41080000/41090000 is used for something else — refuse to
        # overwrite it).
        if Account.objects.filter(code=new_code).exists():
            continue
        # Match strictly on (code, name_hint) so we never accidentally
        # rename an unrelated account that happens to share the legacy
        # code in some atypical tenant.
        Account.objects.filter(
            code=old_code, name__icontains=name_hint,
        ).update(code=new_code)


def revert_codes(apps, schema_editor):
    """Rollback to the legacy 2-series codes — for parity with the
    pre-migration shape. Only fires if the new-code rows still carry
    the expected names."""
    Account = apps.get_model('accounting', 'Account')
    for old_code, new_code, name_hint in RENAMES:
        if Account.objects.filter(code=old_code).exists():
            continue
        Account.objects.filter(
            code=new_code, name__icontains=name_hint,
        ).update(code=old_code)


class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0094_default_expense_rule_strict'),
    ]

    operations = [
        migrations.RunPython(relocate_codes, revert_codes),
    ]
