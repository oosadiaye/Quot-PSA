"""Backfill the Gateway Settlement Clearing account on existing tenants.

Background
----------
E-payment (gateway) disbursements post to a parking liability —
``GATEWAY_SETTLEMENT_CLEARING`` (code 41090001) — instead of crediting
Bank directly, because the cash has not left the account until the PSP
settlement webhook confirms it. ``_clearing_account()`` in
``accounting/services/gateway_disbursement.py`` resolves this account
via ``get_gl_account("GATEWAY_SETTLEMENT_CLEARING", "Liability",
"Gateway Clearing")`` and RAISES if it is missing, so a tenant that
turns on the e-payment toggle without the account would fail at post
time.

Tenants provisioned before e-payment existed have no such account.
This migration seeds it on every tenant that lacks it. The matching
change in ``core/management/commands/seed_tenant_defaults.py`` (and the
``seed_coa.py`` list) ensures every NEW tenant gets it at signup
without relying on this migration.

Idempotent
----------
``get_or_create`` keyed on ``code='41090001'`` → no-op when the account
already exists (from seed_coa, seed_tenant_defaults, or a previous run
of this migration). Safe to re-run.
"""
from django.db import migrations


GW_CODE = '41090001'
GW_NAME = 'Gateway Settlement Clearing'
GW_TYPE = 'Liability'


def backfill_gateway_clearing(apps, schema_editor):
    Account = apps.get_model('accounting', 'Account')
    Account.objects.get_or_create(
        code=GW_CODE,
        defaults={
            'name': GW_NAME,
            'account_type': GW_TYPE,
            'is_active': True,
        },
    )


def remove_gateway_clearing(apps, schema_editor):
    """Reverse — only delete the row if nothing has been posted against
    it yet (zero journal-line references), to avoid breaking historical
    GL data on a rollback.
    """
    Account = apps.get_model('accounting', 'Account')
    JournalLine = apps.get_model('accounting', 'JournalLine')
    for acc in Account.objects.filter(code=GW_CODE, name=GW_NAME):
        if not JournalLine.objects.filter(account=acc).exists():
            acc.delete()


class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0142_alter_paymentvouchergov_options'),
    ]

    operations = [
        migrations.RunPython(backfill_gateway_clearing, remove_gateway_clearing),
    ]
