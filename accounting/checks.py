"""Accounting app system checks.

These checks run at startup (``python manage.py check``) and as part of
``runserver`` / ``migrate`` to surface data-integrity drift before it
becomes a posting-time bug.

Currently registered:

* ``check_header_accounts_are_non_postable`` (M10 follow-up) — surfaces
  any ``Account`` row that has children but is still ``is_postable=True``.
  Migration ``0101_account_is_postable_header_flag`` backfilled this at
  upgrade time, but tenants can legitimately add new header accounts
  after upgrade, and a manual SQL fix-up or an admin save with the
  wrong toggle could leave a header postable. The check warns rather
  than errors because the model-level ``Account.clean()`` and
  ``JournalLine.clean()`` guards still prevent posting; the warning
  alerts the operator that the chart of accounts has drifted from the
  SAP-style header/leaf convention so they can fix it before the
  next bulk import.
"""
from __future__ import annotations

from django.core.checks import Warning as DjangoWarning, register, Tags


@register(Tags.database)
def check_header_accounts_are_non_postable(app_configs, **kwargs):
    """Warn if any Account with children has ``is_postable=True``.

    Skipped silently when the schema hasn't migrated yet (e.g. running
    ``makemigrations`` on a fresh DB) — checking before the column
    exists would mask the real makemigrations output.
    """
    warnings = []
    try:
        from accounting.models.gl import Account
        from django.db.utils import ProgrammingError, OperationalError

        # ``parent_id`` is a self-FK — accounts that show up as a
        # ``parent_id`` somewhere are headers by definition.
        try:
            parent_ids = (
                Account.objects.exclude(parent_id__isnull=True)
                .values_list('parent_id', flat=True)
                .distinct()
            )
            offenders = list(
                Account.objects.filter(pk__in=parent_ids, is_postable=True)
                .values_list('code', 'name')[:20]
            )
        except (ProgrammingError, OperationalError):
            # DB not migrated yet (or table not created in a unit-test
            # context). Skip — the check will run cleanly post-migrate.
            return warnings
    except Exception:  # noqa: BLE001 — system checks must never crash startup
        return warnings

    if offenders:
        sample = ", ".join(f"{code} ({name})" for code, name in offenders[:5])
        warnings.append(
            DjangoWarning(
                f"{len(offenders)} header account(s) are still marked "
                f"is_postable=True. Sample: {sample}. Header accounts "
                f"should be is_postable=False so journal lines, AP "
                f"invoices, and payment vouchers cannot target them "
                f"directly. Run a one-off fix-up: "
                f"`Account.objects.filter(children__isnull=False)"
                f".update(is_postable=False)`.",
                id='accounting.W001',
            )
        )
    return warnings
