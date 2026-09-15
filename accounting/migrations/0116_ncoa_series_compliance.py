"""Bring every account code onto its NCoA family digit.

    1xxxxxxx Revenue
    2xxxxxxx Expenditure
    3xxxxxxx Assets
    4xxxxxxx Liabilities and Net Assets

Migration 0095 did this for two clearing liabilities; 0115 did it for the
GR/IR economic segment. This finishes the chart.

Where the non-compliance came from
----------------------------------
Tenant provisioning seeds via ``seed_ncoa_as_coa`` and produces a
compliant chart — the tenant created through that path carries 1,148
accounts with no violations. The offenders are older tenants seeded from
``seed_coa.py``, a generic commercial chart on the completely different
1-Asset / 2-Liability / 5-Expense convention. So these are not typos;
they are a different numbering scheme that has to be moved wholesale:

    Cash and Bank           Asset     at 1xxxxxxx  -> 3xxxxxxx
    Accounts Payable        Liability at 2xxxxxxx  -> 4xxxxxxx
    Purchase Expense        Expense   at 5xxxxxxx  -> 2xxxxxxx
    Accumulated Surplus     Equity    at 3xxxxxxx  -> 4xxxxxxx

Renaming, not replacing
-----------------------
``Account.pk`` is the FK target on JournalLine, BankAccount.gl_account,
AccountingSettings and the rest, so renaming ``code`` preserves every
posting and reference. 0095 chose the same approach for the same reason.
Accounts carrying journal history are moved, never deactivated.

Two-phase, because the unique index is immediate
------------------------------------------------
Many of the collisions are only about order: 20100000 is occupied by
Accounts Payable, and freed the moment Accounts Payable moves to
40100000, at which point Purchase Expense can take it. Resolving that by
sorting is fragile — a cycle has no valid order at all. Instead every
mover is parked on a temporary code first and then placed, so no
intermediate state can violate the index.

Allocation
----------
Preferred target is the family digit plus the existing last seven digits,
which keeps codes recognisable. When that is already held by an account
that is staying put, the next free slot in the same family is taken in
steps of 100 so the result still reads like a chart code rather than a
sequence number.
"""
from django.db import migrations

FAMILY_OF_TYPE = {
    "Income": "1",
    "Expense": "2",
    "Asset": "3",
    "Liability": "4",
    "Equity": "4",          # NCoA: "Liabilities and Net Assets"
}
PRIMARY_OF_FAMILY = {"1": "Income", "2": "Expense", "3": "Asset", "4": "Liability"}
ALSO_ALLOWED = {"4": {"Equity"}}


def _is_compliant(code: str, account_type: str) -> bool:
    if not code or not code[0].isdigit():
        return True                       # nothing to judge
    primary = PRIMARY_OF_FAMILY.get(code[0])
    if primary is None:
        return False                      # 5-9 are outside the NCoA families
    return primary == account_type or account_type in ALSO_ALLOWED.get(code[0], set())


#: Within the fourth family, liabilities and net assets occupy different
#: bands. Every equity account already in these charts sits at 43xxxxxx —
#: Net Assets / Equity, Accumulated Fund, Statutory Reserve — and
#: ``accumulated_fund_account_code`` points into it. Moving an equity
#: account by family digit alone would drop it into 401xxxxx, the
#: payables band: 4-series and therefore compliant, but a chart an
#: auditor would question. So equity keeps the family *and* the band.
NET_ASSETS_BAND = "43"


def _preferred_code(code: str, account_type: str, family: str) -> str:
    if account_type == "Equity":
        return NET_ASSETS_BAND + code[2:]
    return family + code[1:]


def _allocate(preferred: str, family: str, taken: set) -> str:
    """First free code at or after ``preferred``, inside ``family``."""
    if preferred not in taken:
        return preferred
    try:
        start = int(preferred)
    except ValueError:
        start = int(family + "0" * (len(preferred) - 1))
    width = len(preferred)
    # Steps of 100 keep the shape of a chart code; fall back to 1 only if
    # a whole band is somehow full.
    for step in (100, 1):
        candidate = start + step
        ceiling = (int(family) + 1) * 10 ** (width - 1)
        while candidate < ceiling:
            code = str(candidate).zfill(width)
            if code not in taken:
                return code
            candidate += step
    raise RuntimeError(f"no free code in the {family}-series for {preferred}")


def forwards(apps, schema_editor):
    Account = apps.get_model("accounting", "Account")

    accounts = list(Account.objects.all())
    movers = [
        a for a in accounts
        if a.code and a.code[0].isdigit() and not _is_compliant(a.code, a.account_type)
    ]
    if not movers:
        return

    moving_pks = {a.pk for a in movers}
    # Codes held by accounts that are NOT moving stay occupied throughout.
    taken = {a.code for a in accounts if a.code and a.pk not in moving_pks}

    plan = []
    # Deterministic order so a given chart always produces the same result.
    for account in sorted(movers, key=lambda a: a.code):
        family = FAMILY_OF_TYPE.get(account.account_type)
        if not family:
            continue                       # unknown type: leave it alone
        target = _allocate(
            _preferred_code(account.code, account.account_type, family), family, taken,
        )
        taken.add(target)
        plan.append((account.pk, account.code, target))

    # Phase 1 — park every mover somewhere no real code can collide with.
    for pk, old, _ in plan:
        Account.objects.filter(pk=pk).update(code=f"~m{pk}")

    # Phase 2 — place them.
    for pk, old, new in plan:
        Account.objects.filter(pk=pk).update(code=new)


class Migration(migrations.Migration):
    """Forward only.

    No reverse is supplied, so Django raises IrreversibleError if anyone
    tries to unapply this. That is deliberate: which target each account
    received depends on what was free at the time, and an exact inverse
    cannot be reconstructed from the result alone. Restore from a backup
    to undo — silently guessing the old numbers would be worse than
    refusing to guess.
    """

    dependencies = [
        ("accounting", "0115_relocate_grir_economic_segment"),
    ]

    operations = [
        migrations.RunPython(forwards),
    ]
