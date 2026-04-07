"""
Migration for accounting audit fixes:
- C1: Remove unique=True from JournalLine.document_number
- H1: Remove null=True from JournalLine.account (set orphan nulls to a default first)
- H2: Remove null=True from JournalLine.header (delete orphan null rows first)
- H3: Add MinValueValidator on financial DecimalFields
- L3: Add unique=True to ProfitCenter.code
"""

from decimal import Decimal
from django.core.validators import MinValueValidator
from django.db import migrations, models
import django.db.models.deletion


def fix_null_journal_lines(apps, schema_editor):
    """Delete JournalLines with null header (orphans), and set null account to first account."""
    JournalLine = apps.get_model('accounting', 'JournalLine')
    Account = apps.get_model('accounting', 'Account')

    # Delete orphan lines with no header
    JournalLine.objects.filter(header__isnull=True).delete()

    # Fix lines with no account — set to the first available account
    null_account_lines = JournalLine.objects.filter(account__isnull=True)
    if null_account_lines.exists():
        default_account = Account.objects.first()
        if default_account:
            null_account_lines.update(account=default_account)
        else:
            # No accounts exist — delete the orphan lines
            null_account_lines.delete()


def fix_duplicate_profit_center_codes(apps, schema_editor):
    """Resolve duplicate ProfitCenter codes before adding unique constraint."""
    ProfitCenter = apps.get_model('accounting', 'ProfitCenter')
    from django.db.models import Count
    dupes = (
        ProfitCenter.objects.values('code')
        .annotate(cnt=Count('id'))
        .filter(cnt__gt=1)
    )
    for dupe in dupes:
        pcs = ProfitCenter.objects.filter(code=dupe['code']).order_by('id')
        for i, pc in enumerate(pcs):
            if i > 0:  # Keep the first, rename the rest
                pc.code = f"{pc.code}_{pc.id}"
                pc.save(update_fields=['code'])


class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0036_accountingsettings_account_number_series'),
    ]

    operations = [
        # C1: Remove unique constraint from JournalLine.document_number
        migrations.AlterField(
            model_name='journalline',
            name='document_number',
            field=models.CharField(blank=True, db_index=True, max_length=50, null=True),
        ),

        # Fix data before making fields non-nullable
        migrations.RunPython(fix_null_journal_lines, migrations.RunPython.noop),

        # H2: Make JournalLine.header non-nullable
        migrations.AlterField(
            model_name='journalline',
            name='header',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='lines',
                to='accounting.journalheader',
            ),
        ),

        # H1: Make JournalLine.account non-nullable
        migrations.AlterField(
            model_name='journalline',
            name='account',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                to='accounting.account',
            ),
        ),

        # H3: Add validators on financial fields
        migrations.AlterField(
            model_name='journalline',
            name='debit',
            field=models.DecimalField(
                decimal_places=2, default=0, max_digits=15,
                validators=[MinValueValidator(Decimal('0.00'))],
            ),
        ),
        migrations.AlterField(
            model_name='journalline',
            name='credit',
            field=models.DecimalField(
                decimal_places=2, default=0, max_digits=15,
                validators=[MinValueValidator(Decimal('0.00'))],
            ),
        ),

        # Fix duplicate profit center codes before adding unique
        migrations.RunPython(fix_duplicate_profit_center_codes, migrations.RunPython.noop),

        # L3: Add unique=True to ProfitCenter.code (idempotent — skip if already exists)
        migrations.RunSQL(
            sql="""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint
                        WHERE conname = 'accounting_profitcenter_code_key'
                    ) THEN
                        ALTER TABLE accounting_profitcenter
                        ADD CONSTRAINT accounting_profitcenter_code_key UNIQUE (code);
                    END IF;
                END $$;
            """,
            reverse_sql="ALTER TABLE accounting_profitcenter DROP CONSTRAINT IF EXISTS accounting_profitcenter_code_key;",
            state_operations=[
                migrations.AlterField(
                    model_name='profitcenter',
                    name='code',
                    field=models.CharField(default='', max_length=20, unique=True),
                ),
            ],
        ),
    ]
