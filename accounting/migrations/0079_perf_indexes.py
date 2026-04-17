"""P6-T1 — performance indexes on hot query paths.

See ``docs/PERFORMANCE_AUDIT.md`` for EXPLAIN evidence.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0078_accountingsettings_defined_benefit_obligation_code_and_more'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='journalline',
            index=models.Index(
                fields=['header', 'account'],
                name='jrn_line_header_account_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='journalline',
            index=models.Index(
                fields=['header', 'ncoa_code'],
                name='jrn_line_header_ncoa_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='journalline',
            index=models.Index(
                fields=['header', 'cost_center'],
                name='jrn_line_header_cc_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='vendorinvoice',
            index=models.Index(
                fields=['status', 'invoice_date'],
                name='vi_status_date_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='customerinvoice',
            index=models.Index(
                fields=['status', 'invoice_date'],
                name='ci_status_date_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='reportsnapshot',
            index=models.Index(
                fields=['report_type', 'fiscal_year', 'period', '-generated_at'],
                name='rpt_snap_lookup_idx',
            ),
        ),
    ]
