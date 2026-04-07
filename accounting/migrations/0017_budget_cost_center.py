from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0016_enhance_asset_category'),
    ]

    operations = [
        migrations.AddField(
            model_name='budget',
            name='cost_center',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='budgets',
                to='accounting.costcenter',
            ),
        ),
    ]
