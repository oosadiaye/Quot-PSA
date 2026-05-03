"""
Chart of Accounts → NCoA Economic Segment mirror.

Two entry points:

1. ``sync_all_accounts_to_economic_segments()`` — one-time backfill that walks
   every ``Account`` and creates/updates a matching ``EconomicSegment``.
   Idempotent: re-running only adds/refreshes; never duplicates.

2. ``mirror_account_to_economic_segment(instance)`` — single-row mirror used by
   the ``post_save`` signal on ``Account``. After the signal is wired (see
   ``accounting.signals.coa_to_ncoa``), every CoA create / update — whether
   from the COA form, the bulk-import endpoint, the Django admin, or a
   shell — automatically writes the NCoA layer in the same transaction.

The mapping is mechanical:

  Account.code            -> EconomicSegment.code           (1:1)
  Account.name            -> EconomicSegment.name           (1:1)
  Account.account_type    -> EconomicSegment.account_type_code via 5→4 bucket
                             collapse (Income=1, Expense=2, Asset=3,
                             Liability=4, Equity=4 — NCoA's 4xxxxxxx covers
                             "Liabilities and Net Assets" so Equity lives there)
  Account.code[0]         -> override the family digit when it's '1'-'4',
                             since the project's NIGERIA_COA_SERIES rule says
                             the first digit IS the canonical family marker
  family digit            -> EconomicSegment.normal_balance
                               1 (Revenue)    -> CREDIT
                               2 (Expenditure) -> DEBIT
                               3 (Assets)     -> DEBIT
                               4 (Liab/Equity) -> CREDIT
  Account.is_active       -> EconomicSegment.is_active
  Account.id              -> EconomicSegment.legacy_account (FK)

Posting-level: every legacy CoA account is treated as a posting-level NCoA
segment by default (is_posting_level=True). Header / control accounts in the
NCoA hierarchy that don't correspond to a legacy CoA row are left untouched.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from accounting.models.gl import Account
from accounting.models.ncoa import EconomicSegment

if TYPE_CHECKING:
    from accounting.models.gl import Account as AccountType


# ── 5-bucket → 4-bucket family map ───────────────────────────────────────
# Used only when the account code's first digit isn't 1-4 (i.e. legacy
# accounts that don't follow NIGERIA_COA_SERIES). When the code starts
# with a valid family digit, that digit is the source of truth.
_FAMILY_FROM_TYPE = {
    'Income':    '1',
    'Expense':   '2',
    'Asset':     '3',
    'Liability': '4',
    'Equity':    '4',
}

# Family digit → NCoA normal balance.
_NORMAL_BALANCE = {
    '1': 'CREDIT',  # Revenue / Income
    '2': 'DEBIT',   # Expenditure / Expense
    '3': 'DEBIT',   # Assets
    '4': 'CREDIT',  # Liabilities and Net Assets / Equity
}


def _derive_family_digit(account: 'AccountType') -> str:
    """First digit of code if it's 1-4, else fall back to account_type map."""
    code = (account.code or '').strip()
    if code and code[0] in ('1', '2', '3', '4'):
        return code[0]
    return _FAMILY_FROM_TYPE.get(account.account_type, '3')  # default Asset


def _build_defaults(account: 'AccountType') -> dict:
    """Translate an Account row into the EconomicSegment fields it should mirror."""
    family = _derive_family_digit(account)
    return {
        'name':              (account.name or '')[:200],
        'account_type_code': family,
        'normal_balance':    _NORMAL_BALANCE[family],
        'is_active':         account.is_active,
        'is_posting_level':  True,
        'legacy_account_id': account.id,
        # Preserve legacy_account_type (used by some IPSAS reports that read
        # the older 5-bucket label rather than NCoA's 4-bucket).
        'legacy_account_type': account.account_type or '',
    }


def mirror_account_to_economic_segment(account: 'AccountType') -> tuple[EconomicSegment, bool]:
    """Idempotent single-row upsert. Returns (segment, created)."""
    code = (account.code or '').strip()
    if not code:
        # Defensive: an Account without a code can't be mirrored. The Account
        # model itself has ``code`` non-nullable so this should never happen,
        # but skip rather than crash if a future migration loosens the field.
        return None, False  # type: ignore[return-value]
    if len(code) > 20:
        # EconomicSegment.code is max_length=20 (matches Account.code). Skip
        # if somehow the upstream slipped through a longer code.
        return None, False  # type: ignore[return-value]

    defaults = _build_defaults(account)
    # update_or_create on the unique ``code`` field — the right shape for
    # both create-on-first-save and update-on-rename.
    obj, created = EconomicSegment.objects.update_or_create(
        code=code, defaults=defaults,
    )
    return obj, created


def sync_all_accounts_to_economic_segments() -> dict:
    """One-time backfill. Returns counts + skipped codes."""
    created_count = 0
    updated_count = 0
    skipped: list[dict] = []

    for account in Account.objects.all():
        code = (account.code or '').strip()
        if not code:
            skipped.append({'id': account.id, 'reason': 'blank code'})
            continue
        if len(code) > 20:
            skipped.append({'id': account.id, 'code': code, 'reason': f'code longer than 20 chars ({len(code)})'})
            continue
        _, created = mirror_account_to_economic_segment(account)
        if created:
            created_count += 1
        else:
            updated_count += 1

    return {
        'created':  created_count,
        'updated':  updated_count,
        'skipped':  len(skipped),
        'skipped_details': skipped,
        'total':    created_count + updated_count + len(skipped),
    }
