from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    """
    Make PurchaseRequestLine.account optional (null=True, blank=True).

    GL accounts are derived from the item's product type/category and are not
    required at the PR stage. They are resolved during PO creation and posting.
    """

    dependencies = [
        ('accounting', '0001_initial'),
        ('procurement', '0034_pr_number_auto_generate'),
    ]

    operations = [
        migrations.AlterField(
            model_name='purchaserequestline',
            name='account',
            field=models.ForeignKey(
                blank=True,
                help_text='GL account derived from the item product type. Left blank on PR; resolved at PO/GRN stage.',
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to='accounting.account',
            ),
        ),
    ]
