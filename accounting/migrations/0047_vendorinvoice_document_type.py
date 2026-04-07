# -*- coding: utf-8 -*-
"""Add document_type field to VendorInvoice (Invoice / Credit Memo)."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0046_repair_nullable_columns'),
    ]

    operations = [
        migrations.AddField(
            model_name='vendorinvoice',
            name='document_type',
            field=models.CharField(
                blank=True,
                choices=[('Invoice', 'Invoice'), ('Credit Memo', 'Credit Memo')],
                default='Invoice',
                max_length=20,
            ),
        ),
    ]
