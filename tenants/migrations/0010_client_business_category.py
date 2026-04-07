from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tenants', '0009_add_module_pricing'),
    ]

    operations = [
        migrations.AddField(
            model_name='client',
            name='business_category',
            field=models.CharField(
                blank=True,
                choices=[
                    ('agriculture', 'Agriculture & Farming'),
                    ('manufacturing', 'Manufacturing'),
                    ('construction', 'Construction'),
                    ('trading', 'Trading & Distribution'),
                    ('healthcare', 'Healthcare'),
                    ('education', 'Education'),
                    ('technology', 'Technology / IT Services'),
                    ('hospitality', 'Hospitality / Food & Beverage'),
                    ('mining', 'Mining & Extractive Industries'),
                    ('logistics', 'Transportation & Logistics'),
                    ('real_estate', 'Real Estate & Property'),
                    ('nonprofit', 'Non-Profit / NGO'),
                    ('government', 'Government / Public Sector'),
                    ('retail', 'Retail'),
                    ('energy', 'Energy & Utilities'),
                    ('other', 'General / Other'),
                ],
                default='other',
                help_text='Industry category — drives default CoA, BOM templates, and module config',
                max_length=50,
            ),
        ),
    ]
