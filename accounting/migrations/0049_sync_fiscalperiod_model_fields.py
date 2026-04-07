"""
Sync migration: FiscalPeriod model fields were stripped from models.py at some
point but the DB columns created by migration 0008 remained (created_at,
updated_at, name, is_adjustment_period, created_by_id, updated_by_id).

Because those columns already exist in the tenant DB we use
SeparateDatabaseAndState:
  - database_operations: RunSQL with IF NOT EXISTS guards (safe no-op if
    columns are already present, ensures they exist if somehow absent)
  - state_operations: AddField declarations that only update Django's
    internal migration state — no DDL is issued for these

This brings the ORM back in sync so bulk_create / INSERT includes all fields
and the NOT NULL constraint on created_at is satisfied.
"""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('accounting', '0048_customerinvoice_document_type'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            # ── DB side: safe ADD COLUMN IF NOT EXISTS (no-op when columns exist) ──
            database_operations=[
                migrations.RunSQL(
                    sql="""
                        ALTER TABLE accounting_fiscalperiod
                            ADD COLUMN IF NOT EXISTS created_at
                                timestamptz NOT NULL DEFAULT now();
                        ALTER TABLE accounting_fiscalperiod
                            ADD COLUMN IF NOT EXISTS updated_at
                                timestamptz NOT NULL DEFAULT now();
                        ALTER TABLE accounting_fiscalperiod
                            ADD COLUMN IF NOT EXISTS name
                                varchar(100) NOT NULL DEFAULT '';
                        ALTER TABLE accounting_fiscalperiod
                            ADD COLUMN IF NOT EXISTS is_adjustment_period
                                boolean NOT NULL DEFAULT false;
                        ALTER TABLE accounting_fiscalperiod
                            ADD COLUMN IF NOT EXISTS created_by_id
                                integer NULL
                                REFERENCES auth_user(id)
                                DEFERRABLE INITIALLY DEFERRED;
                        ALTER TABLE accounting_fiscalperiod
                            ADD COLUMN IF NOT EXISTS updated_by_id
                                integer NULL
                                REFERENCES auth_user(id)
                                DEFERRABLE INITIALLY DEFERRED;
                    """,
                    reverse_sql=migrations.RunSQL.noop,
                ),
            ],
            # ── State side: teach Django's ORM about these fields (no DDL) ──
            state_operations=[
                migrations.AddField(
                    model_name='fiscalperiod',
                    name='created_at',
                    field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now),
                    preserve_default=False,
                ),
                migrations.AddField(
                    model_name='fiscalperiod',
                    name='updated_at',
                    field=models.DateTimeField(auto_now=True),
                ),
                migrations.AddField(
                    model_name='fiscalperiod',
                    name='name',
                    field=models.CharField(blank=True, default='', max_length=100),
                ),
                migrations.AddField(
                    model_name='fiscalperiod',
                    name='is_adjustment_period',
                    field=models.BooleanField(default=False),
                ),
                migrations.AddField(
                    model_name='fiscalperiod',
                    name='created_by',
                    field=models.ForeignKey(
                        blank=True, null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='fiscal_periods_created',
                        db_column='created_by_id',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                migrations.AddField(
                    model_name='fiscalperiod',
                    name='updated_by',
                    field=models.ForeignKey(
                        blank=True, null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='fiscal_periods_updated',
                        db_column='updated_by_id',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
    ]
