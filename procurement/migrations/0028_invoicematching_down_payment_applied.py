from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('procurement', '0027_down_payment_request'),
    ]

    operations = [
        migrations.AddField(
            model_name='invoicematching',
            name='down_payment_applied',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text='Amount of down payment / advance deducted from this invoice.',
                max_digits=15,
            ),
        ),
    ]
