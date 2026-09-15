"""Move stray economic segments onto NCoA family digits.

0116 finished the ``Account`` chart. ``EconomicSegment`` carries its own
parallel chart for the six-segment NCoA code and had one row left over:

    50000000  "Expenditure (Group)"  account_type_code '2'

Two problems in one row. NCoA defines four families — 1 Revenue,
2 Expenditure, 3 Assets, 4 Liabilities and Net Assets — and there is no
fifth, so the code belongs in no family at all. And despite being named
"(Group)" it carried ``is_posting_level=True``, which is what decides
whether a segment can be posted to and whether it appears in the contract
GL Account picker. A group is a heading; postings belong on its children.

Both are corrected: the code moves into the family its own
``account_type_code`` already claims, and the row is marked as the group
it says it is.

Targeted, not pattern-matched
-----------------------------
Only rows whose code sits outside 1-4 are considered, and each is placed
using the family its ``account_type_code`` already declares — so this
reads the data's own statement about itself rather than guessing from the
name. 0115 explains at length why name matching is unsafe here: real
tenant data contains expenditure lines called "Slum Clearance" and
"... PAYABLE BY".
"""
from django.db import migrations

FAMILIES = {"1", "2", "3", "4"}


def _allocate(preferred: str, family: str, taken: set) -> str:
    """First free code at or after ``preferred``, inside ``family``."""
    if preferred not in taken:
        return preferred
    start, width = int(preferred), len(preferred)
    ceiling = (int(family) + 1) * 10 ** (width - 1)
    for step in (100, 1):
        candidate = start + step
        while candidate < ceiling:
            code = str(candidate).zfill(width)
            if code not in taken:
                return code
            candidate += step
    raise RuntimeError(f"no free code in the {family}-series for {preferred}")


def forwards(apps, schema_editor):
    EconomicSegment = apps.get_model("accounting", "EconomicSegment")

    segments = list(EconomicSegment.objects.all())
    strays = [
        s for s in segments
        if s.code and s.code[0].isdigit() and s.code[0] not in FAMILIES
    ]
    if not strays:
        return

    stray_pks = {s.pk for s in strays}
    taken = {s.code for s in segments if s.code and s.pk not in stray_pks}

    plan = []
    for seg in sorted(strays, key=lambda s: s.code):
        family = str(seg.account_type_code or "").strip()
        if family not in FAMILIES:
            continue                      # nothing reliable to place it by
        target = _allocate(family + seg.code[1:], family, taken)
        taken.add(target)
        plan.append((seg.pk, target, "(group)" in (seg.name or "").lower()))

    # Park first, then place — the unique index is immediate and a target
    # may be held by another stray that has not moved yet.
    for pk, _, _ in plan:
        EconomicSegment.objects.filter(pk=pk).update(code=f"~s{pk}")

    for pk, target, is_group in plan:
        fields = {"code": target}
        if is_group:
            # Named "(Group)" but flagged postable. The flag is what keeps
            # a heading out of the GL picker and out of resolve_code.
            fields["is_posting_level"] = False
        EconomicSegment.objects.filter(pk=pk).update(**fields)


class Migration(migrations.Migration):
    """Forward only, for the same reason as 0116 — the target chosen
    depends on what was free at the time, so an exact inverse cannot be
    reconstructed from the result."""

    dependencies = [
        ("accounting", "0116_ncoa_series_compliance"),
    ]

    operations = [
        migrations.RunPython(forwards),
    ]
