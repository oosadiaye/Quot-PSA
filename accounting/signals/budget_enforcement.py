"""Centralised BudgetCheckRule enforcement + expenditure roll-up.

Every ``JournalHeader`` save is intercepted here so that ANY code path
which transitions a journal to ``status='Posted'`` — whether via the
UI ViewSet, a payroll run, depreciation batch, year-end close, bank
reconciliation, or a management command — goes through the same two
gates:

  1. ``pre_save``: run ``check_policy`` for every line. If any line's
     GL falls under a STRICT BudgetCheckRule and either has no matching
     Appropriation or would exceed it, block the transition to Posted
     with a ``ValidationError``.
  2. ``post_save``: refresh denormalised totals on every Appropriation
     touched by the newly-posted journal so
     ``Appropriation.cached_total_expended`` stays current.

Callers that have already performed the policy check (the journal
ViewSet's ``_post_to_gl`` method) set the ``_budget_checked = True``
sentinel on the header instance to suppress the duplicate pre-save
evaluation. Likewise for ``_totals_refreshed = True``. The signal is
a safety net — it must never break a legitimate posting path that has
already validated itself.
"""
from __future__ import annotations

import logging
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


def _is_transitioning_to_posted(instance) -> bool:
    """Detect a status transition to 'Posted' on this save."""
    if instance.status != 'Posted':
        return False
    if not instance.pk:
        # Brand-new row created already as Posted — legitimate (bulk imports)
        return True
    try:
        prior = type(instance).all_objects.get(pk=instance.pk)
    except type(instance).DoesNotExist:
        return True
    return prior.status != 'Posted'


@receiver(pre_save, sender=None, dispatch_uid='budget_enforcement_pre_save_journal')
def enforce_budget_on_journal_post(sender, instance, **kwargs):
    """Block Posted transitions when STRICT rules are violated.

    Runs for every JournalHeader save. Only evaluates when the journal
    is crossing into 'Posted' status. Honors the ``_budget_checked``
    sentinel from the ViewSet so users see the structured error shape
    (``budget_violations`` key) rather than a generic ValidationError.
    """
    from accounting.models.gl import JournalHeader
    if sender is not JournalHeader:
        return
    if getattr(instance, '_budget_checked', False):
        return
    if not _is_transitioning_to_posted(instance):
        return
    # skip_budget_check sentinel honored for legacy flows (e.g. reversals)
    if getattr(instance, '_skip_budget_check', False):
        return

    # A row being INSERTED with status='Posted' (common pattern from
    # procurement / payroll services: JournalHeader.objects.create(
    # status='Posted', ...)) has no pk yet at pre_save time, which
    # means the reverse-FK manager ``instance.lines`` would raise
    # ``ValueError('JournalHeader instance needs to have a primary
    # key value before this relationship can be used.')``.
    #
    # Skip the pre-save check in that case — the lines haven't been
    # attached yet, so there's nothing to validate. Budget enforcement
    # for those flows is the caller's responsibility (e.g. procurement
    # runs ``check_policy`` / warrant checks inline before creating the
    # journal, so setting ``_budget_checked = True`` on the instance
    # is the correct way to acknowledge that). The post-save signal
    # still fires (with pk now set), so ``refresh_totals`` runs once
    # lines have been created.
    if instance.pk is None:
        return

    from accounting.services.budget_check_rules import (
        check_policy, find_matching_appropriation, resolve_rule_for_account,
    )
    from budget.services import _is_warrant_enforced
    from accounting.budget_logic import (
        check_warrant_availability,
        is_warrant_pre_payment_enforced,
    )

    # Statutory charges (Constitution §81(2)): debt service, judges'
    # salaries, pensions-in-payment carry standing warrants and so
    # skip the quarterly-warrant gate. The annual-appropriation gate
    # (check_policy) still runs.
    STATUTORY_SOURCES = {
        'debt_service', 'pension_payroll', 'pensions',
        'judicial_salary', 'statutory_charge', 'cfs',
    }

    fiscal_year = instance.posting_date.year if instance.posting_date else None
    source_module = (instance.source_module or '')
    # Two flags — ``warrant_mode_on`` is the legacy tenant-level
    # toggle (off for tenants that don't use warrants at all).
    # ``pre_payment_warrant`` is the new stage flag — when False, the
    # journal posts without warrant interrogation (the ceiling
    # enforces at payment time only, per PFM control design).
    warrant_mode_on = _is_warrant_enforced() and is_warrant_pre_payment_enforced()
    violations = []
    for line in instance.lines.all():
        amt = (line.debit or Decimal('0')) + (line.credit or Decimal('0'))
        if amt <= 0:
            continue
        # Budget consumption is a DEBIT-side concept: a debit on an
        # expense-coded GL consumes appropriation; a credit on the
        # same GL is a reversal / release and SHOULD NOT be gated by
        # the appropriation requirement. Skipping credits here means
        # legitimate correcting journals (e.g. reversing an over-
        # posted expense) succeed even when no appropriation matches
        # the line's GL — which is the correct behaviour, since the
        # entry is reducing recorded spend, not increasing it.
        if not (line.debit and line.debit > 0):
            continue
        rule = resolve_rule_for_account(line.account.code)
        if rule is None and not (
            line.account.account_type == 'Expense'
            and line.debit and line.debit > 0
        ):
            continue
        appropriation = find_matching_appropriation(
            mda=instance.mda, fund=instance.fund,
            account=line.account, fiscal_year=fiscal_year,
        )
        result = check_policy(
            account_code=line.account.code, appropriation=appropriation,
            requested_amount=line.debit or Decimal('0'),
            transaction_label='journal',
            account_name=line.account.name,
        )
        if result.blocked:
            violations.append(
                f"[{line.account.code} {line.account.name}] {result.reason}"
            )
            continue

        # ── Warrant / AIE gate (PFM Act 2007 + Fin Reg §§ 400–417) ──
        # Mirrors the ViewSet-level check so every code path — payroll
        # posting, depreciation run, year-end close, bank rec, etc. —
        # honours the quarterly warrant ceiling. Statutory sources
        # bypass because they carry standing warrants.
        if (
            warrant_mode_on
            and result.level == 'STRICT'
            and appropriation is not None
            and line.account.account_type == 'Expense'
            and line.debit and line.debit > 0
            and source_module not in STATUTORY_SOURCES
        ):
            warrant_ok, warrant_msg, _info = check_warrant_availability(
                dimensions={'mda': instance.mda, 'fund': instance.fund},
                account=line.account,
                amount=line.debit,
            )
            if not warrant_ok:
                violations.append(
                    f"[{line.account.code} {line.account.name}] {warrant_msg}"
                )

    if violations:
        raise ValidationError(
            'Budget check failed — cannot post journal: ' + '; '.join(violations)
        )


@receiver(post_save, sender=None, dispatch_uid='budget_enforcement_post_save_journal')
def refresh_appropriation_totals_after_post(sender, instance, created, **kwargs):
    """Roll up expenditure to every Appropriation touched by a Posted JV."""
    from accounting.models.gl import JournalHeader
    if sender is not JournalHeader:
        return
    if instance.status != 'Posted':
        return
    if getattr(instance, '_totals_refreshed', False):
        return

    try:
        from accounting.services.appropriation_totals import refresh_totals
        from accounting.services.budget_check_rules import find_matching_appropriation
        from budget.models import Appropriation
        fiscal_year = instance.posting_date.year if instance.posting_date else None
        touched = set()
        for line in instance.lines.all():
            amt = (line.debit or Decimal('0')) + (line.credit or Decimal('0'))
            if amt <= 0:
                continue
            appr = find_matching_appropriation(
                mda=instance.mda, fund=instance.fund,
                account=line.account, fiscal_year=fiscal_year,
            )
            if appr is not None:
                touched.add(appr.pk)
        for a in Appropriation.objects.filter(pk__in=touched):
            refresh_totals(a)
        # Mark so re-save events don't re-run the aggregate
        instance._totals_refreshed = True
    except Exception as exc:
        # Reporting-cache failures must NEVER break the posting path,
        # but they MUST be loud — the appropriation cache is what every
        # budget execution report and dashboard reads. If this silently
        # fails, every budget number on the system is stale. Log at
        # ``error`` level (not just ``exception``) so monitoring picks
        # it up; the posting itself still succeeds.
        logger.error(
            'CRITICAL: Appropriation totals refresh failed after journal '
            'post (journal_id=%s document=%s): %s. Run '
            '`./manage.py resync_appropriation_totals` to recover.',
            getattr(instance, 'pk', None),
            getattr(instance, 'document_number', None),
            exc, exc_info=True,
        )


def _connect_signals():
    """Connect signals with concrete sender. Called from apps.ready()."""
    from accounting.models.gl import JournalHeader
    pre_save.connect(
        enforce_budget_on_journal_post,
        sender=JournalHeader,
        dispatch_uid='budget_enforcement_pre_save_journal',
    )
    post_save.connect(
        refresh_appropriation_totals_after_post,
        sender=JournalHeader,
        dispatch_uid='budget_enforcement_post_save_journal',
    )
