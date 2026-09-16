"""Put budget's economic indexes and uniqueness back, post-merge.

The companion to ``accounting.0120``. ``budget.0018`` had to drop two
indexes and the active-appropriation uniqueness constraint before it
could drop the old ``economic`` column, and left re-creating them to a
follow-up so their generated names would come from Django rather than a
guess. Django generated the same names, so they land back unchanged.

``uniq_active_appropriation_per_dimension_tuple`` is the one that
matters: it is what stops two ACTIVE appropriations claiming the same
(administrative, economic, fund, fiscal_year) line and double-counting
the authority to spend.
"""
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounting", "0120_retire_economic_segment"),
        ("budget", "0018_economic_segment_to_account"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddIndex(
            model_name="appropriation",
            index=models.Index(
                fields=["administrative", "economic", "fiscal_year"],
                name="budget_appr_adminis_4b73b7_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="revenuebudget",
            index=models.Index(
                fields=["administrative", "economic", "fiscal_year"],
                name="budget_reve_adminis_864c4a_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="appropriation",
            constraint=models.UniqueConstraint(
                condition=models.Q(("status", "ACTIVE")),
                fields=("administrative", "economic", "fund", "fiscal_year"),
                name="uniq_active_appropriation_per_dimension_tuple",
            ),
        ),
    ]
