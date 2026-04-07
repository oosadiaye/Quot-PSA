from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tenants', '0005_add_language_preference'),
    ]

    operations = [
        migrations.AddField(
            model_name='subscriptionplan',
            name='features',
            field=models.JSONField(blank=True, default=list, help_text='List of feature dicts: [{category, name, included, limit}]'),
        ),
    ]
