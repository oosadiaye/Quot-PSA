# Generated manually — adds LeaveRequest to GlobalApprovalSettings.MODULE_CHOICES

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('workflow', '0006_alter_globalapprovalsettings_module'),
    ]

    operations = [
        migrations.AlterField(
            model_name='globalapprovalsettings',
            name='module',
            field=models.CharField(
                choices=[
                    ('PurchaseRequest', 'Purchase Requests'),
                    ('PurchaseOrder', 'Purchase Orders'),
                    ('GoodsReceivedNote', 'Goods Received Notes'),
                    ('InvoiceVerification', 'Invoice Verification (3-Way Match)'),
                    ('PurchaseReturn', 'Purchase Returns'),
                    ('SalesOrder', 'Sales Orders'),
                    ('ProductionOrder', 'Production Orders'),
                    ('QualityInspection', 'Quality Inspections'),
                    ('Budget', 'Budgets'),
                    ('JournalEntry', 'Journal Entries'),
                    ('LeaveRequest', 'Leave Requests'),
                    ('Maintenance', 'Maintenance'),
                ],
                max_length=30,
                unique=True,
            ),
        ),
    ]
