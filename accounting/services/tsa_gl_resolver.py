"""
TSA Cash-GL resolver — single source of truth for "which GL Account
should this TSA-driven posting hit on the cash side?"

Why this exists
---------------
Multiple posting paths (payment voucher, revenue collection, opening
balance seed, treasury transfers) used to hardcode the cash GL by
literal NCoA code (``31100100``). That looks fine on paper, but breaks
in three real scenarios:

  • A tenant whose Chart of Accounts uses a different cash code.
  • A tenant with multiple TSAs (Main, Sub, ZBA) where each should hit
    its own GL control account, not the same shared one.
  • Future tenants that follow a state-specific NCoA mapping where
    ``31100100`` simply doesn't exist.

Design
------
Resolution priority (first match wins):

  1. **TSA-specific GL** — ``tsa_account.gl_cash_account`` if the TSA
     was passed in and its FK is populated. This is the canonical
     enterprise choice: every TSA carries its own configured cash GL,
     so postings against TSA #1 hit GL X and postings against TSA #2
     hit GL Y. No collision; clean reconciliation.

  2. **Tenant-configurable default** — ``AccountingSettings
     .default_cash_account_code`` resolved against the COA. Tenants
     can set this in Settings → Accounting; if absent, falls through.

  3. **Last-resort COA scan** — first active Account with
     ``account_type='Asset'`` whose code starts with ``31`` (the NCoA
     cash family prefix). Logs a warning so an operator notices and
     configures a real default.

  4. **Loud failure** — raises ``ImproperlyConfigured`` with a
     message that tells the operator exactly what to do (configure a
     default, or set ``gl_cash_account`` on the TSA).

This module replaces every hardcoded ``Account.objects.filter(code=
'31100100').first()`` lookup. New posting paths should call
``resolve_tsa_cash_gl(...)`` rather than introducing another literal.
"""
from __future__ import annotations

import logging

from django.core.exceptions import ImproperlyConfigured


logger = logging.getLogger(__name__)


def resolve_tsa_cash_gl(*, tsa_account=None, raise_on_missing: bool = True):
    """
    Return the ``Account`` row that this TSA-driven posting should hit
    on the cash side.

    Parameters
    ----------
    tsa_account : TreasuryAccount or None
        Preferred input. If supplied and ``tsa_account.gl_cash_account``
        is set, that is returned immediately.
    raise_on_missing : bool, default True
        If True (and nothing resolves), raises ``ImproperlyConfigured``
        with an actionable message. Set False if the caller wants to
        soft-handle the missing case (e.g. dry-run / preview UI).

    Returns
    -------
    Account or None
        The resolved Account, or None when ``raise_on_missing`` is False
        and no resolution path succeeded.
    """
    from accounting.models import Account

    # ── 1. Per-TSA configured GL ───────────────────────────────────
    if tsa_account is not None:
        gl = getattr(tsa_account, 'gl_cash_account', None)
        if gl is not None:
            return gl
        logger.info(
            'TSA %s has no gl_cash_account configured; falling back to '
            'tenant default.',
            getattr(tsa_account, 'account_number', tsa_account),
        )

    # ── 2. Tenant default from AccountingSettings ─────────────────
    try:
        from accounting.models import AccountingSettings
        settings_obj = AccountingSettings.objects.first()
        default_code = getattr(settings_obj, 'default_cash_account_code', None) if settings_obj else None
    except Exception as exc:  # noqa: BLE001
        logger.warning('AccountingSettings unavailable: %s', exc)
        default_code = None

    if default_code:
        gl = Account.objects.filter(
            code=default_code, is_active=True,
            account_type='Asset',
        ).first()
        if gl:
            return gl
        logger.warning(
            "AccountingSettings.default_cash_account_code=%r does not "
            "match any active Asset account in the COA. Falling back to "
            "first 31* asset account.",
            default_code,
        )

    # ── 3. Last-resort: first active 31* asset account ──────────
    gl = (
        Account.objects
        .filter(is_active=True, account_type='Asset', code__startswith='31')
        .order_by('code')
        .first()
    )
    if gl:
        logger.warning(
            'TSA cash GL resolved by COA-prefix fallback to %s — %s. '
            'Configure AccountingSettings.default_cash_account_code OR '
            'set gl_cash_account on each TSA to silence this warning.',
            gl.code, gl.name,
        )
        return gl

    if raise_on_missing:
        raise ImproperlyConfigured(
            'Cannot resolve TSA cash GL account. None of the resolution '
            'paths succeeded:\n'
            '  1. The TSA has no gl_cash_account configured.\n'
            '  2. AccountingSettings.default_cash_account_code is empty '
            'or points to a missing/inactive account.\n'
            '  3. No Asset account with a 31* code exists in the COA.\n'
            '\nFix one of:\n'
            '  • Settings → Accounting → set default_cash_account_code '
            'to an existing asset code (e.g. 31030205), OR\n'
            '  • Treasury → TSA Accounts → set GL Cash Account on every '
            'TSA, OR\n'
            '  • Add a 31xxxxxx Asset account to the Chart of Accounts.'
        )
    return None
