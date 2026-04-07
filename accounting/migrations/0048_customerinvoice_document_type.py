from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0047_vendorinvoice_document_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='customerinvoice',
            name='document_type',
            field=models.CharField(
                blank=True,
                choices=[('Invoice', 'Invoice'), ('Credit Memo', 'Credit Memo')],
                default='Invoice',
                max_length=20,
            ),
        ),
    ]
