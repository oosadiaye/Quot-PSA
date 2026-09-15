"""Repoint budget's economic classifier from EconomicSegment to Account.

The companion to ``accounting.0119``. The NCoA economic segment and the
GL account are one classifier in public-sector accounting; ``Account`` is
the survivor and the duplicate table is retired.

    Appropriation.economic
    RevenueBudget.economic

Same reasoning as 0119: a plain ``AlterField`` on ``to=`` would keep the
existing integers and read them as Account primary keys, quietly pointing
every appropriation at an unrelated account. The values are copied
through ``EconomicSegment.legacy_account`` instead — the bridge the sync
service already maintained, completed by ``accounting.0118``.

``Appropriation`` gains from this beyond tidiness. It used to reach the
GL through ``economic.legacy_account_id`` and refused to save when that
hop was missing; the hop is now the field itself.

The index and the uniqueness constraint that name ``economic`` come off
before the column is dropped. The index is left to a follow-up so its
generated name comes from Django rather than a guess.
"""
from django.db import migrations, models
import django.db.models.deletion


def copy_forward(apps, schema_editor):
    Appropriation = apps.get_model("budget", "Appropriation")
    RevenueBudget = apps.get_model("budget", "RevenueBudget")
    EconomicSegment = apps.get_model("accounting", "EconomicSegment")

    bridge = dict(EconomicSegment.objects.values_list("pk", "legacy_account_id"))

    def remap(model):
        for pk, old_id in model.objects.values_list("pk", "economic_id"):
            if old_id is None:
                continue
            account_id = bridge.get(old_id)
            if account_id is None:
                raise RuntimeError(
                    f"{model.__name__} {pk} references economic segment {old_id}, "
                    f"which has no legacy_account; run accounting.0118 first."
                )
            model.objects.filter(pk=pk).update(economic_acct_id=account_id)

    remap(Appropriation)
    remap(RevenueBudget)


class Migration(migrations.Migration):

    dependencies = [
        ("budget", "0017_alter_warrant_status"),
        # The copy reads EconomicSegment.legacy_account, which 0118 fills.
        ("accounting", "0119_economic_segment_to_account"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="appropriation",
            name="uniq_active_appropriation_per_dimension_tuple",
        ),
        migrations.RemoveIndex(
            model_name="appropriation", name="budget_appr_adminis_4b73b7_idx",
        ),
        migrations.RemoveIndex(
            model_name="revenuebudget", name="budget_reve_adminis_864c4a_idx",
        ),

        migrations.AddField(
            model_name="appropriation",
            name="economic_acct",
            field=models.ForeignKey(
                null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name="appropriations_tmp", to="accounting.account",
            ),
        ),
        migrations.AddField(
            model_name="revenuebudget",
            name="economic_acct",
            field=models.ForeignKey(
                null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name="revenue_budgets_tmp", to="accounting.account",
            ),
        ),

        migrations.RunPython(copy_forward, migrations.RunPython.noop),

        migrations.RemoveField(model_name="appropriation", name="economic"),
        migrations.RemoveField(model_name="revenuebudget", name="economic"),

        migrations.RenameField(
            model_name="appropriation", old_name="economic_acct", new_name="economic",
        ),
        migrations.RenameField(
            model_name="revenuebudget", old_name="economic_acct", new_name="economic",
        ),

        migrations.AlterField(
            model_name="appropriation",
            name="economic",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="appropriations", to="accounting.account",
            ),
        ),
        migrations.AlterField(
            model_name="revenuebudget",
            name="economic",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="revenue_budgets", to="accounting.account",
                help_text="NCoA revenue account (GL account, 1-series Revenue)",
            ),
        ),
    ]
