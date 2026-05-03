"""
Collapse IPC period_from / period_to into a single posting_date.

Rationale: Engineers sign off on the measurement book once and post the
IPC on that date. A two-date window added UX friction without giving
the accrual engine anything it couldn't compute from posting_date +
contract.fiscal_year. The dedup hash is rebuilt on the new shape in a
data migration below so existing integrity checks still fire.
"""
from __future__ import annotations

import hashlib

from django.db import migrations, models


def _rebuild_hashes(apps, schema_editor):
    """Recompute integrity_hash for every IPC against the new shape."""
    IPC = apps.get_model("contracts", "InterimPaymentCertificate")
    for ipc in IPC.objects.all().only(
        "id", "contract_id", "posting_date", "cumulative_work_done_to_date",
    ):
        raw = "|".join([
            str(ipc.contract_id),
            str(ipc.posting_date),
            str(ipc.cumulative_work_done_to_date),
        ])
        ipc.integrity_hash = hashlib.sha256(raw.encode()).hexdigest()
        ipc.save(update_fields=["integrity_hash"])


def _noop_reverse(apps, schema_editor):
    """Reversal would need the old period_from/period_to back — out of scope."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("contracts", "0003_vendor_status_verification"),
    ]

    operations = [
        # 1. Add posting_date as nullable so existing rows don't blow up.
        migrations.AddField(
            model_name="interimpaymentcertificate",
            name="posting_date",
            field=models.DateField(null=True),
        ),
        # 2. Backfill: copy period_from → posting_date for any existing rows.
        migrations.RunSQL(
            sql=(
                "UPDATE contracts_interimpaymentcertificate "
                "SET posting_date = period_from "
                "WHERE posting_date IS NULL AND period_from IS NOT NULL;"
            ),
            reverse_sql=migrations.RunSQL.noop,
        ),
        # 3. Flip posting_date to NOT NULL now that every row has a value.
        migrations.AlterField(
            model_name="interimpaymentcertificate",
            name="posting_date",
            field=models.DateField(),
        ),
        # 4. Drop the old period fields.
        migrations.RemoveField(
            model_name="interimpaymentcertificate",
            name="period_from",
        ),
        migrations.RemoveField(
            model_name="interimpaymentcertificate",
            name="period_to",
        ),
        # 5. Re-order on posting_date to match the new Meta.ordering.
        migrations.AlterModelOptions(
            name="interimpaymentcertificate",
            options={"ordering": ["contract", "posting_date"]},
        ),
        # 6. Rebuild integrity_hash against (contract_id, posting_date, cumulative).
        migrations.RunPython(_rebuild_hashes, _noop_reverse),
    ]
