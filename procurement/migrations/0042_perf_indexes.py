"""P6-T1 — performance indexes for Appropriation totals queries.

``ProcurementBudgetLink`` is scanned every time an Appropriation card
loads its totals. See ``docs/PERFORMANCE_AUDIT.md``.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('procurement', '0041_alter_goodsreceivednote_warehouse_helptext'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='procurementbudgetlink',
            index=models.Index(
                fields=['appropriation', 'status'],
                name='cmt_appr_status_idx',
            ),
        ),
    ]
