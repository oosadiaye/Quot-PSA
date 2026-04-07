from django.db import migrations, models
import django.core.validators
from decimal import Decimal


class Migration(migrations.Migration):
    """
    Add standard_price and cost_price to Item, and extend valuation_method
    choices to include 'STD' (Standard Cost).

    - standard_price: user-set reference price at product creation.
    - cost_price: computed and persisted after each GRN based on valuation method.
    - STD valuation: cost_price always equals standard_price regardless of purchase prices.
    """

    dependencies = [
        ('inventory', '0017_add_shelf_life_days_to_item'),
    ]

    operations = [
        migrations.AddField(
            model_name='item',
            name='standard_price',
            field=models.DecimalField(
                decimal_places=4,
                default=Decimal('0'),
                help_text='User-defined reference cost set at product creation. Used as cost price for Standard valuation and as an initial baseline for other methods.',
                max_digits=19,
                validators=[django.core.validators.MinValueValidator(Decimal('0'))],
            ),
        ),
        migrations.AddField(
            model_name='item',
            name='cost_price',
            field=models.DecimalField(
                decimal_places=4,
                default=Decimal('0'),
                help_text='Current computed cost price. Updated after each GRN based on the valuation method.',
                max_digits=19,
                validators=[django.core.validators.MinValueValidator(Decimal('0'))],
            ),
        ),
        migrations.AlterField(
            model_name='item',
            name='valuation_method',
            field=models.CharField(
                choices=[
                    ('FIFO', 'FIFO'),
                    ('WA', 'Weighted Average'),
                    ('LIFO', 'LIFO'),
                    ('STD', 'Standard Cost'),
                ],
                default='WA',
                max_length=10,
            ),
        ),
    ]
