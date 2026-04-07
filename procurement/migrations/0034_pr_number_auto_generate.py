from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Allow request_number to be blank so save() can auto-generate it
    in the format PR-YYYY-NNNNN (matching GRN-YYYY-NNNNN convention).
    """

    dependencies = [
        ('procurement', '0033_add_batch_expiry_to_grn_line'),
    ]

    operations = [
        migrations.AlterField(
            model_name='purchaserequest',
            name='request_number',
            field=models.CharField(blank=True, max_length=50, unique=True),
        ),
    ]
