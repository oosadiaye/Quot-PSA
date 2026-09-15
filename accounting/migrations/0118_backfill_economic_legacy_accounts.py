"""Give every economic segment an Account, ready for the merge.

In public-sector accounting the NCoA economic segment *is* the chart of
accounts: the same codes, the same names, the same hierarchy, kept in two
tables. ``seed_ncoa_as_coa`` exists only to copy one into the other, and
``EconomicSegment.legacy_account`` is already a foreign key to the
matching ``Account`` — the duplication is acknowledged in the schema.

The plan is to keep ``Account`` and drop ``EconomicSegment``, repointing
everything that referenced a segment at the account it already mirrors.
That repoint can be a straight copy of ``legacy_account``, but only if
every segment has one. Across the tenants here 1,527 of 1,528 do; this
closes the remainder so the repoint cannot silently null a reference.

The account is built with the same rules ``seed_ncoa_as_coa`` applies, so
a backfilled row is indistinguishable from a seeded one:

  * account_type from account_type_code (1 Income, 2 Expense, 3 Asset,
    4 Liability), with 43xxxxxx mapping to Equity because NCoA's fourth
    family is "Liabilities and Net Assets";
  * parent taken from the segment's own parent chain where that parent
    already has an account.
"""
from django.db import migrations

NCOA_TO_LEGACY_TYPE = {
    "1": "Income",
    "2": "Expense",
    "3": "Asset",
    "4": "Liability",
}
EQUITY_PREFIXES = ("43",)


def _legacy_type(segment) -> str:
    code = (segment.code or "").strip()
    if code.startswith(EQUITY_PREFIXES):
        return "Equity"
    return NCOA_TO_LEGACY_TYPE.get(str(segment.account_type_code or ""), "Expense")


def forwards(apps, schema_editor):
    EconomicSegment = apps.get_model("accounting", "EconomicSegment")
    Account = apps.get_model("accounting", "Account")

    pending = list(EconomicSegment.objects.filter(legacy_account__isnull=True))
    if not pending:
        return

    accounts_by_code = {a.code: a for a in Account.objects.all()}
    accounts_by_name = {}
    for account in Account.objects.all():
        accounts_by_name.setdefault((account.name or "").strip().lower(), account)

    for segment in pending:
        # Prefer an existing account: code first, then name. Name matters
        # because a code can drift — 0116 renumbered accounts onto their
        # NCoA family without moving the segments that mirror them, so a
        # segment may still carry the pre-0116 number.
        account = accounts_by_code.get(segment.code)
        if account is None:
            account = accounts_by_name.get((segment.name or "").strip().lower())

        if account is None:
            parent = None
            if segment.parent_id:
                parent_segment = EconomicSegment.objects.filter(pk=segment.parent_id).first()
                if parent_segment:
                    parent = (
                        accounts_by_code.get(parent_segment.code)
                        or (parent_segment.legacy_account if parent_segment.legacy_account_id else None)
                    )
            account = Account.objects.create(
                code=segment.code,
                name=segment.name,
                account_type=_legacy_type(segment),
                is_active=segment.is_active,
                parent=parent,
            )
            accounts_by_code[account.code] = account
            accounts_by_name.setdefault((account.name or "").strip().lower(), account)

        segment.legacy_account = account
        segment.save(update_fields=["legacy_account"])


class Migration(migrations.Migration):

    dependencies = [
        ("accounting", "0117_ncoa_segment_series_compliance"),
    ]

    operations = [
        # Additive only: creates accounts that were missing and links
        # segments to them. Nothing is removed, so it needs no reverse.
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
