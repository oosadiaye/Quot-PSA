"""Drop EconomicSegment — the economic classifier is the GL account.

The end of the merge that 0118 and 0119 set up. 0118 gave every segment
an ``Account``; 0119 (and ``budget.0018``) repointed all five foreign
keys onto it; the application code has since stopped reading the table.
Nothing references it any more, so it goes.

What is lost with the table
---------------------------
Nothing that was not already derivable:

    account_type_code   == code[0]
    sub_type_code       == code[1]
    account_class_code  == code[2:4]
    sub_class_code      == code[4:6]
    line_item_code      == code[6:8]
    is_posting_level    -> Account.is_postable
    is_control_account  -> Account.is_reconciliation
    normal_balance      implied by the NCoA family (DEBIT for 2/3,
                        CREDIT for 1/4)
    legacy_account      the row itself

This migration is NOT reversible in the sense that matters: running it
backwards recreates an empty table, not the rows. The data it held is
either in ``accounting_account`` already or was a substring of a code.

The two NCoACode indexes
------------------------
0119 removed ``accounting__economi_3e159c_idx`` and
``accounting__economi_73a081_idx`` before it could drop the old
``economic`` column, and deliberately left re-creating them to a
follow-up so the names would come from Django rather than from a guess.
This is that follow-up, and Django generated the same two names — so
the indexes land back exactly where they were.
"""
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounting", "0119_economic_segment_to_account"),
        # budget.0018 is what moves Appropriation.economic and
        # RevenueBudget.economic off this model. Without naming it here
        # the graph lets DeleteModel run first, and replaying the
        # migrations from zero — which is exactly what building the test
        # database does — dies on:
        #
        #   The field budget.Appropriation.economic was declared with a
        #   lazy reference to 'accounting.economicsegment', but app
        #   'accounting' doesn't provide model 'economicsegment'.
        #
        # An incremental migrate never showed it, because by then budget
        # had already moved.
        ("budget", "0018_economic_segment_to_account"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveField(
            model_name="economicsegment",
            name="created_by",
        ),
        migrations.RemoveField(
            model_name="economicsegment",
            name="legacy_account",
        ),
        migrations.RemoveField(
            model_name="economicsegment",
            name="parent",
        ),
        migrations.RemoveField(
            model_name="economicsegment",
            name="updated_by",
        ),
        migrations.AddIndex(
            model_name="ncoacode",
            index=models.Index(
                fields=["economic", "administrative"],
                name="accounting__economi_3e159c_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="ncoacode",
            index=models.Index(
                fields=["economic", "functional"], name="accounting__economi_73a081_idx"
            ),
        ),
        migrations.DeleteModel(
            name="EconomicSegment",
        ),
    ]
