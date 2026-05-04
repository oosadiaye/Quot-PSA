"""Add per-tenant ``require_warrant_before_payment`` toggle.

Lets each tenant decide whether the payment-stage warrant ceiling check
is enforced or bypassed. Defaults to True (safe / GIFMIS-compliant).
The Accounting Settings UI surfaces this as a single toggle.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0097_vendor_advance_special_gl'),
    ]

    operations = [
        migrations.AddField(
            model_name='accountingsettings',
            name='require_warrant_before_payment',
            field=models.BooleanField(
                default=True,
                help_text=(
                    'When True, outgoing Payments are blocked when the '
                    'released warrant balance for the relevant MDA + Fund + '
                    'Account would not cover the payment amount. When False, '
                    'payments post without the warrant ceiling check — useful '
                    'for tenants not yet operating on warrant-based cash '
                    'control. Pre-payment stages (commitment, invoice) are '
                    'governed separately by the WARRANT_ENFORCEMENT_STAGE '
                    'system setting.'
                ),
            ),
        ),
    ]
