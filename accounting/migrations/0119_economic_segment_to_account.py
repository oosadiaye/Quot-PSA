"""Repoint the economic classifier from EconomicSegment to Account.

In public-sector accounting the NCoA economic segment and the chart of
accounts are one classifier: same codes, same names, same hierarchy. They
were kept in two tables held level by ``coa_to_ncoa_sync`` and a signal.
``Account`` is the survivor. The other five NCoA segments keep their own
models, because administrative, functional, programme, fund and
geographic classify things the GL does not.

Three fields move here; ``budget`` moves its two in its own migration:

    NCoACode.economic
    TreasuryAccount.ncoa_cash_code
    RevenueHead.economic_segment

Why not a plain AlterField
--------------------------
Changing ``to=`` would leave the existing integers in place and
reinterpret them as Account primary keys. A segment's pk is not its
account's pk, so every row would silently point at an unrelated account —
the worst kind of migration, because nothing fails.

Instead a new column is added, populated from
``EconomicSegment.legacy_account`` (the bridge the sync service has been
maintaining all along, and which 0118 completed so no row is unmapped),
and then swapped into place.

NCoACode's unique_together and two of its indexes name ``economic``, so
they come off before the column is dropped; uniqueness is restored here
and the indexes by the follow-up migration.
"""
from django.db import migrations, models
import django.db.models.deletion


def copy_forward(apps, schema_editor):
    """Populate the new columns from the segment's own account bridge."""
    NCoACode = apps.get_model("accounting", "NCoACode")
    TreasuryAccount = apps.get_model("accounting", "TreasuryAccount")
    RevenueHead = apps.get_model("accounting", "RevenueHead")
    EconomicSegment = apps.get_model("accounting", "EconomicSegment")

    bridge = dict(
        EconomicSegment.objects.values_list("pk", "legacy_account_id")
    )

    def remap(model, old_field, new_field):
        for pk, old_id in model.objects.values_list("pk", old_field):
            if old_id is None:
                continue
            account_id = bridge.get(old_id)
            if account_id is None:
                # 0118 guarantees every segment has an account. Refuse
                # rather than write a null into a column that is about to
                # become NOT NULL — a broken reference discovered here is
                # cheap, and discovered in a ledger is not.
                raise RuntimeError(
                    f"{model.__name__}.{old_field}={old_id} points at an economic "
                    f"segment with no legacy_account; run 0118 first."
                )
            model.objects.filter(pk=pk).update(**{new_field: account_id})

    remap(NCoACode, "economic_id", "economic_acct_id")
    remap(TreasuryAccount, "ncoa_cash_code_id", "ncoa_cash_code_acct_id")
    remap(RevenueHead, "economic_segment_id", "economic_segment_acct_id")


class Migration(migrations.Migration):

    dependencies = [
        ("accounting", "0118_backfill_economic_legacy_accounts"),
    ]

    operations = [
        # ── Take the constraints that name `economic` off first ────────
        migrations.AlterUniqueTogether(name="ncoacode", unique_together=set()),
        # Two indexes name `economic` and must come off before the column
        # can be dropped. A follow-up migration puts them back, so their
        # generated names come from Django rather than from a guess.
        migrations.RemoveIndex(model_name="ncoacode", name="accounting__economi_3e159c_idx"),
        migrations.RemoveIndex(model_name="ncoacode", name="accounting__economi_73a081_idx"),

        # ── Add the replacement columns ────────────────────────────────
        migrations.AddField(
            model_name="ncoacode",
            name="economic_acct",
            field=models.ForeignKey(
                null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name="ncoa_codes_tmp", to="accounting.account",
            ),
        ),
        migrations.AddField(
            model_name="treasuryaccount",
            name="ncoa_cash_code_acct",
            field=models.ForeignKey(
                null=True, blank=True, on_delete=django.db.models.deletion.PROTECT,
                related_name="tsa_cash_accounts_tmp", to="accounting.account",
            ),
        ),
        migrations.AddField(
            model_name="revenuehead",
            name="economic_segment_acct",
            field=models.ForeignKey(
                null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name="revenue_heads_tmp", to="accounting.account",
            ),
        ),

        migrations.RunPython(copy_forward, migrations.RunPython.noop),

        # ── Drop the old columns and take the new names ────────────────
        migrations.RemoveField(model_name="ncoacode", name="economic"),
        migrations.RemoveField(model_name="treasuryaccount", name="ncoa_cash_code"),
        migrations.RemoveField(model_name="revenuehead", name="economic_segment"),

        migrations.RenameField(
            model_name="ncoacode", old_name="economic_acct", new_name="economic",
        ),
        migrations.RenameField(
            model_name="treasuryaccount",
            old_name="ncoa_cash_code_acct", new_name="ncoa_cash_code",
        ),
        migrations.RenameField(
            model_name="revenuehead",
            old_name="economic_segment_acct", new_name="economic_segment",
        ),

        # ── Settle each field on its final definition ──────────────────
        migrations.AlterField(
            model_name="ncoacode",
            name="economic",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="ncoa_codes", to="accounting.account",
            ),
        ),
        migrations.AlterField(
            model_name="treasuryaccount",
            name="ncoa_cash_code",
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="tsa_cash_accounts", to="accounting.account",
                help_text=(
                    "NCoA Economic Segment classification for this TSA's cash "
                    "position (e.g. '31030205 — Cash Transfer / JAAC Direct "
                    "Allocation'). Used by IPSAS Cash Flow Statement to group "
                    "treasury accounts by economic classification."
                ),
            ),
        ),
        migrations.AlterField(
            model_name="revenuehead",
            name="economic_segment",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="revenue_heads", to="accounting.account",
                help_text="NCoA economic code (GL account) for this revenue type",
            ),
        ),

        # ── Put the uniqueness back ────────────────────────────────────
        # Indexes are left to the follow-up migration so their generated
        # names come from Django rather than from me guessing hashes.
        migrations.AlterUniqueTogether(
            name="ncoacode",
            unique_together={
                ("administrative", "economic", "functional",
                 "programme", "fund", "geographic")
            },
        ),
    ]
