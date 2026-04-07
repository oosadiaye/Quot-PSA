from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0012_fix_assetdepreciationschedule'),
    ]

    operations = [
        migrations.CreateModel(
            name='AccountingSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('account_code_digits', models.IntegerField(choices=[(4, '4'), (5, '5'), (6, '6'), (7, '7'), (8, '8'), (9, '9'), (10, '10')], default=8)),
                ('is_digit_enforcement_active', models.BooleanField(default=False)),
            ],
            options={
                'verbose_name': 'Accounting Settings',
                'verbose_name_plural': 'Accounting Settings',
            },
        ),
    ]
