"""Move the GR/IR Clearing **economic segment** out of the expense series.

Migration 0095 relocated GR/IR Clearing and Due-to-Other-Funds from the
2-series to the 4-series in the legacy ``Account`` table, for the reason
it states there: Nigerian PSA / NCoA reserves ``2xxxxxxx`` for Expense
and ``4xxxxxxx`` for Liabilities, and ``AccountSerializer`` enforces it.

It did not cover ``EconomicSegment``, which carries its own parallel
chart for the NCoA six-segment code. So the same liability was still
sitting in the expense series there:

    20100100 — GR/IR Clearing (Goods Received / Invoice Received)
               account_type_code '2', is_control_account False

The visible symptom is on the contract form. Its GL Account dropdown
offers posting-level, non-control accounts in the 2-series — which is
the right rule — and this row satisfies all three, so a clerk could
raise a contract against the GR/IR clearing account instead of an
expenditure line. ``NCoAService.resolve_code`` would not have stopped it
either: it rejects header and control accounts, and this was flagged as
neither.

Two changes, because either alone leaves a hole:

* the code moves to the 4-series (41090000, matching what 0095 gave the
  legacy row) and the type becomes '4', so it no longer looks like an
  expense to anything that reasons from the series;
* ``is_control_account`` becomes True, which is what it has always been
  — a clearing account is not a posting target — and is the flag both
  the form and ``resolve_code`` already honour.

Targeted rather than pattern-matched
------------------------------------
Only the exact code ``20100100`` whose name contains "GR/IR" is touched.
Matching on words like "clearing" or "payable" would be a mistake: real
tenant data contains expenditure lines called "Removal of Illegal
Structures/Slum Clearance", "clearing and sanitation of Street" and
"ENROMENT FEES AND INCIDENTAL COST PAYABLE BY", and hiding those from
the contract form would be a worse bug than the one being fixed.

Safe for the 3-way match
------------------------
Procurement posts to the **legacy** account via
``get_gl_account('GOODS_RECEIPT_CLEARING', 'Liability', 'GR/IR')``,
which resolves ``Account`` 41090000 — a different table and a different
row. Nothing in that pipeline reads this segment.

Renaming, not replacing: ``NCoACode.economic`` is an FK to the segment's
pk and ``NCoACode.full_code`` is a computed property, so composed codes
follow the rename automatically and no journal reference is orphaned —
the same reasoning 0095 gives.
"""
from django.db import migrations

OLD_CODE = "20100100"
NEW_CODE = "41090000"


def relocate(apps, schema_editor):
    EconomicSegment = apps.get_model("accounting", "EconomicSegment")

    seg = (
        EconomicSegment.objects
        .filter(code=OLD_CODE, name__icontains="GR/IR")
        .first()
    )
    if seg is None:
        return                      # tenant never had it, or already moved

    # Someone may have created the 4-series row separately. Renaming onto
    # an occupied code would collide, and merging two charts is not a
    # decision a migration should take silently.
    if EconomicSegment.objects.filter(code=NEW_CODE).exclude(pk=seg.pk).exists():
        seg.is_control_account = True
        seg.save(update_fields=["is_control_account"])
        return

    seg.code = NEW_CODE
    seg.account_type_code = "4"
    seg.is_control_account = True
    seg.save(update_fields=["code", "account_type_code", "is_control_account"])


def restore(apps, schema_editor):
    EconomicSegment = apps.get_model("accounting", "EconomicSegment")
    seg = (
        EconomicSegment.objects
        .filter(code=NEW_CODE, name__icontains="GR/IR")
        .first()
    )
    if seg is None:
        return
    seg.code = OLD_CODE
    seg.account_type_code = "2"
    seg.is_control_account = False
    seg.save(update_fields=["code", "account_type_code", "is_control_account"])


class Migration(migrations.Migration):

    dependencies = [
        ("accounting", "0114_duplicate_payment_guards"),
    ]

    operations = [
        migrations.RunPython(relocate, restore),
    ]
