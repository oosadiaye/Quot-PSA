"""Backfill GR/IR Clearing Account for tenants that don't have one yet.

Background
----------
Migration 0095 renamed any pre-existing ``20601000`` row to
``41090000``. But some tenants were provisioned through the NCoA-first
path that never ran ``seed_coa.py``, so they have no GR/IR Clearing
account at all — neither under the legacy code nor the new one. The
first time those tenants try to post a GRN, the procurement-posting
service errors out with:

    "GR/IR Clearing account not found. Configure
     DEFAULT_GL_ACCOUNTS['GOODS_RECEIPT_CLEARING'] in settings and
     ensure a Liability account in the 41xxxxxx series (default code:
     41090000 — GR/IR Clearing Account) exists in the Chart of
     Accounts."

This migration seeds the account on every tenant that lacks it. The
matching change in ``core/management/commands/seed_tenant_defaults.py``
ensures every NEW tenant provisioned after this point gets the
account at signup time without relying on this migration.

Idempotent
----------
``get_or_create`` keyed on ``code='41090000'`` → no-op when the
account already exists (created by 0095 rename, by seed_coa, or by
this migration on a previous run). Safe to re-run.
"""
from django.db import migrations


GRIR_CODE = '41090000'
GRIR_NAME = 'GR/IR Clearing Account'
GRIR_TYPE = 'Liability'


def backfill_grir(apps, schema_editor):
    Account = apps.get_model('accounting', 'Account')
    Account.objects.get_or_create(
        code=GRIR_CODE,
        defaults={
            'name': GRIR_NAME,
            'account_type': GRIR_TYPE,
            'is_active': True,
        },
    )


def remove_grir(apps, schema_editor):
    """Reverse — only delete the row if it has zero journal-line
    references (i.e. nothing has been posted against it yet). This
    avoids breaking historical GL data when rolling back.
    """
    Account = apps.get_model('accounting', 'Account')
    JournalLine = apps.get_model('accounting', 'JournalLine')
    qs = Account.objects.filter(code=GRIR_CODE, name=GRIR_NAME)
    for acc in qs:
        if not JournalLine.objects.filter(account=acc).exists():
            acc.delete()


class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0095_relocate_grir_clearing_to_4_series'),
    ]

    operations = [
        migrations.RunPython(backfill_grir, remove_grir),
    ]
