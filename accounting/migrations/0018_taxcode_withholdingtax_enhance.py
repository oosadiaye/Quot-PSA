import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0017_budget_cost_center'),
    ]

    operations = [
        # ── Enhance WithholdingTax ──────────────────────────────────────
        # NOTE: code, name, withholding_account already exist in 0008_product_type_category
        # (WithholdingTax was created there with all these fields). Removed duplicate AddField ops.

        # ── Create TaxCode table ────────────────────────────────────────
        migrations.CreateModel(
            name='TaxCode',
            fields=[
                ('id', models.AutoField(
                    auto_created=True, primary_key=True,
                    serialize=False, verbose_name='ID',
                )),
                ('code', models.CharField(
                    db_index=True, max_length=20, unique=True,
                )),
                ('name', models.CharField(max_length=150)),
                ('tax_type', models.CharField(
                    choices=[
                        ('vat', 'VAT'),
                        ('sales_tax', 'Sales Tax'),
                        ('service_tax', 'Service Tax'),
                        ('excise_duty', 'Excise Duty'),
                        ('customs_duty', 'Customs Duty'),
                    ],
                    db_index=True, max_length=20,
                )),
                ('direction', models.CharField(
                    choices=[
                        ('purchase', 'Purchase (Input)'),
                        ('sales', 'Sales (Output)'),
                        ('both', 'Both'),
                    ],
                    db_index=True, max_length=10,
                )),
                ('rate', models.DecimalField(
                    decimal_places=4, max_digits=8,
                )),
                ('tax_account', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='tax_codes',
                    to='accounting.account',
                )),
                ('is_active', models.BooleanField(
                    db_index=True, default=True,
                )),
                ('description', models.TextField(blank=True)),
            ],
            options={
                'ordering': ['code'],
            },
        ),
    ]
