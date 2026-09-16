"""Record a clerk's decision to save a contract that looked like a duplicate.

``makemigrations`` also wanted to bundle an ``AlterField`` on
``mobilizationpayment.status`` here. That change belongs to PR #5, which
ships it as its own ``0012_alter_mobilizationpayment_status`` — the model
and the migration history have been out of step on ``main`` for a while
and that PR is the fix. Carrying it here as well would land the same
alteration twice under two migrations both numbered 0012 and both
depending on 0011, which is a branched graph Django refuses to run
without a merge migration.

So it is deliberately left out. ``makemigrations --check`` therefore still
reports the drift on this branch, exactly as it did before this commit.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("contracts", "0011_contract_retention_cap_percent"),
    ]

    operations = [
        migrations.AddField(
            model_name="contract",
            name="duplicate_ack_ids",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="Contracts flagged as possible duplicates and accepted anyway.",
            ),
        ),
        migrations.AddField(
            model_name="contract",
            name="duplicate_ack_reason",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Why this was saved despite resembling an existing contract.",
            ),
        ),
    ]
