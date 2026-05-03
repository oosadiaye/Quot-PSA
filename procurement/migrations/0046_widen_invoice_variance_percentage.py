"""Widen InvoiceMatching.variance_percentage from (5,2) to (10,2).

A NUMERIC(5,2) caps the value at 999.99. Real-world partial-receipt
scenarios (e.g. invoice value ₦1,075,000 against GRN ₦81,000) yield
variance percentages above 1000% — those must persist so the variance
gate / payment_hold can react to them. Widening to NUMERIC(10,2) lifts
the cap to 99,999,999.99 — comfortably beyond any plausible data.

This is a non-destructive ALTER TYPE — Postgres widens NUMERIC in place
without rewriting the table.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('procurement', '0045_invoicematching_wht_exempt_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='invoicematching',
            name='variance_percentage',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
    ]
