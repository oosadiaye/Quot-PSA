import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0015_accountingsettings_default_currencies'),
    ]

    operations = [
        # is_active flag — skipped: already added in 0008_product_type_category CreateModel

        # GL account FKs
        migrations.AddField(
            model_name='assetcategory',
            name='cost_account',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='category_cost_accounts',
                to='accounting.account',
            ),
        ),
        migrations.AddField(
            model_name='assetcategory',
            name='accumulated_depreciation_account',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='category_accum_depr_accounts',
                to='accounting.account',
            ),
        ),
        migrations.AddField(
            model_name='assetcategory',
            name='depreciation_expense_account',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='category_depr_expense_accounts',
                to='accounting.account',
            ),
        ),

        # Rename depreciation_override → depreciation_method (field was named differently in 0008)
        migrations.RenameField(
            model_name='assetcategory',
            old_name='depreciation_override',
            new_name='depreciation_method',
        ),
        # Now alter to set default and updated choices
        migrations.AlterField(
            model_name='assetcategory',
            name='depreciation_method',
            field=models.CharField(
                choices=[
                    ('Straight-Line', 'Straight-Line'),
                    ('Declining Balance', 'Declining Balance'),
                    ('Double Declining Balance', 'Double Declining Balance'),
                    ('Sum of Years Digits', 'Sum of Years Digits'),
                    ('Units of Production', 'Units of Production'),
                ],
                default='Straight-Line',
                max_length=30,
            ),
        ),

        # Rename useful_life_override → default_life_years
        migrations.RenameField(
            model_name='assetcategory',
            old_name='useful_life_override',
            new_name='default_life_years',
        ),
        migrations.AlterField(
            model_name='assetcategory',
            name='default_life_years',
            field=models.IntegerField(default=5),
        ),

        # Remove fields that are no longer in the model
        migrations.RemoveField(
            model_name='assetcategory',
            name='default_location',
        ),
        migrations.RemoveField(
            model_name='assetcategory',
            name='default_warranty_months',
        ),

        # Residual value fields
        migrations.AddField(
            model_name='assetcategory',
            name='residual_value_type',
            field=models.CharField(
                choices=[
                    ('percentage', 'Percentage of Cost'),
                    ('amount', 'Fixed Amount'),
                ],
                default='percentage',
                max_length=15,
            ),
        ),
        migrations.AddField(
            model_name='assetcategory',
            name='residual_value',
            field=models.DecimalField(
                decimal_places=4, default=0, max_digits=15,
            ),
        ),

        # Change asset_class from CASCADE to SET_NULL
        migrations.AlterField(
            model_name='assetcategory',
            name='asset_class',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to='accounting.assetclass',
            ),
        ),

        # Make code unique
        migrations.AlterField(
            model_name='assetcategory',
            name='code',
            field=models.CharField(max_length=20, unique=True),
        ),

        # Remove unique_together (replaced by unique on code field above)
        migrations.AlterUniqueTogether(
            name='assetcategory',
            unique_together=set(),
        ),
    ]
