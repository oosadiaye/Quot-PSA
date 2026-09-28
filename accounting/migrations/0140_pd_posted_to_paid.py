"""Grandfather existing directly-posted Payment Documents.

Before the Payment Proposal change a PaymentDocument posted its own journal and
its terminal status was "Posted". The proposal lifecycle renames that terminal
to "Paid" (the document is paid once its Outgoing Payment posts). Existing
"Posted" documents already carry a journal and moved cash, so map them to
"Paid". Idempotent and reversible.
"""
from django.db import migrations


def posted_to_paid(apps, schema_editor):
    PaymentDocument = apps.get_model("accounting", "PaymentDocument")
    PaymentDocument.objects.filter(status="Posted").update(status="Paid")


def paid_to_posted(apps, schema_editor):
    PaymentDocument = apps.get_model("accounting", "PaymentDocument")
    PaymentDocument.objects.filter(status="Paid").update(status="Posted")


class Migration(migrations.Migration):
    dependencies = [("accounting", "0139_alter_paymentdocument_status")]
    operations = [migrations.RunPython(posted_to_paid, paid_to_posted)]
