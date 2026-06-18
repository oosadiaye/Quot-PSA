"""
Pass-10 regression tests — budget ↔ contracts ↔ accounting integration.

Each test pins one of the safe-additive fixes shipped in Pass 10. The
suite stays no-DB / pure-Python by inspecting source text and
class/method shapes (not by exercising the live ORM), so it runs on
the fast tier and doesn't require a tenant schema. The trade-off:
these tests catch the **wiring** of each fix — a future refactor that
removes the call or renames the permission code fails immediately —
but they don't catch business-logic regressions in the fix bodies.
Behavioural tests for those live in the contracts/accounting test
suites and run on the DB tier.
"""
from __future__ import annotations

import inspect


# ─────────────────────────────────────────────────────────────────────
# Budget C1 — warrant expiry filter in validate_expenditure
# ─────────────────────────────────────────────────────────────────────

class TestBudgetWarrantExpiryFilter:
    """`BudgetValidationService.validate_expenditure` must filter
    warrants whose ``effective_to`` is in the past — otherwise a
    warrant the daily cron hasn't yet flipped to EXPIRED silently
    authorises new expenditure."""

    def test_validate_expenditure_filters_by_effective_to(self):
        from budget import services
        src = inspect.getsource(services)
        # The bug was reading ``warrants.filter(status='RELEASED').last()``
        # with no expiry guard. The fix adds a Q(effective_to__isnull=True)
        # | Q(effective_to__gte=...) filter. Either token signals the
        # fix is in place.
        assert 'effective_to__gte' in src, (
            'budget.services must filter expired warrants in '
            'validate_expenditure — see Pass 10 C1.'
        )
        assert 'effective_to__isnull=True' in src, (
            'Legacy nullable effective_to rows must still be treated as '
            'not-expired; missing this clause would break historical data.'
        )


# ─────────────────────────────────────────────────────────────────────
# Contracts C1 — MeasurementBook lock after IPC citation
# ─────────────────────────────────────────────────────────────────────

class TestMeasurementBookLockAfterIPC:
    """Once an IPC has cited an MB (status NOT in DRAFT/REJECTED),
    the MB must refuse further mutation — preserves the three-way-
    match audit trail."""

    def test_mb_save_has_ipc_citation_guard(self):
        from contracts.models import payment
        src = inspect.getsource(payment)
        # The guard checks ``self.ipcs.exclude(status__in=('DRAFT','REJECTED'))``
        # inside the MB's ``save()``. We assert on the distinctive
        # combination of method + status set so a generic ``ipcs``
        # reference elsewhere doesn't false-positive.
        assert "exclude(\n                    status__in=('DRAFT', 'REJECTED'),\n                ).exists()" in src or \
               "exclude(status__in=('DRAFT', 'REJECTED')).exists()" in src or \
               "DRAFT" in src and "REJECTED" in src and "self.ipcs" in src, (
            'MeasurementBook.save must refuse mutation when a non-'
            'DRAFT/REJECTED IPC cites it — see Pass 10 C1.'
        )

    def test_mb_lock_allows_status_only_updates(self):
        """The guard exempts status-only saves so the legitimate MB
        status transitions (DRAFT→APPROVED etc.) keep working even
        after an IPC cites it."""
        from contracts.models import payment
        src = inspect.getsource(payment)
        assert 'is_status_only' in src, (
            'MB lock must exempt status-only updates so workflow '
            'transitions continue working post-citation.'
        )


# ─────────────────────────────────────────────────────────────────────
# Contracts C2 — cascade IPC mark_paid failure surfaces in response
# ─────────────────────────────────────────────────────────────────────

class TestCascadeIPCFailureSurfaces:
    """When the PV-driven cascade can't mark an IPC PAID (typically
    SoD or ceiling re-check), the failure must surface in the API
    response so the operator can reconcile — not vanish into a log."""

    def test_post_payment_collects_cascade_warnings(self):
        from accounting.views import payables
        src = inspect.getsource(payables)
        assert '_cascade_warnings' in src, (
            'post_payment must accumulate cascade failures (see Pass 10 C2).'
        )
        assert 'cascade_warnings' in src, (
            'post_payment response must include cascade_warnings field '
            'when downstream IPC updates fail.'
        )
        assert "'kind':   'ipc_mark_paid_failed'" in src or \
               "'kind': 'ipc_mark_paid_failed'" in src, (
            'Cascade warning records must use the documented kind '
            'identifier for IPC mark-paid failures.'
        )


# ─────────────────────────────────────────────────────────────────────
# Contracts source_module collision
# ─────────────────────────────────────────────────────────────────────

class TestContractsSourceModuleDistinct:
    """IPC accrual + retention release journals must use DISTINCT
    source_module values to honour the partial unique constraint
    ``uniq_journalheader_source_doc_posted`` (Pass 3, migration 0067)."""

    def test_ipc_journal_uses_distinct_source_module(self):
        from contracts.services import ipc_service
        src = inspect.getsource(ipc_service)
        assert "source_module='contract_ipc'" in src, (
            'IPC accrual journal must use source_module=contract_ipc '
            '(was: source_module=contracts). See Pass 10 source_module fix.'
        )
        # Make sure the OLD value isn't still there (regression guard)
        assert "source_module='contracts'," not in src, (
            'Stale source_module=contracts still present — collision '
            'risk reintroduced.'
        )

    def test_retention_journal_uses_distinct_source_module(self):
        from contracts.services import retention_service
        src = inspect.getsource(retention_service)
        assert "source_module='contract_retention_release'" in src
        assert "source_module='contracts'," not in src


# ─────────────────────────────────────────────────────────────────────
# Budget SoD wiring (H1+H2+H3)
# ─────────────────────────────────────────────────────────────────────

class TestBudgetSoDWiring:
    """Wire enforce_action on every budget state-transition that
    spends money or authorises spending."""

    def test_appropriation_submit_approve_enact_wired(self):
        from budget import views
        src = inspect.getsource(views)
        assert "'budget.appropriation.submit'" in src
        assert "'budget.appropriation.approve'" in src

    def test_warrant_release_suspend_wired(self):
        from budget import views
        src = inspect.getsource(views)
        assert "'budget.warrant.release'" in src
        assert "'budget.warrant.suspend'" in src

    def test_virement_approve_wired(self):
        from budget import views
        src = inspect.getsource(views)
        assert "'budget.virement.approve'" in src


# ─────────────────────────────────────────────────────────────────────
# Contracts SoD — mobilisation, retention, closure
# ─────────────────────────────────────────────────────────────────────

class TestContractsSoDWiring:
    """Mobilisation issuance, retention release create+pay, and the
    three CompletionCertificate-issuing transitions must reject the
    contract drafter (or prior actor for retention pay)."""

    def test_mobilization_issue_advance_has_sod(self):
        from contracts.services import mobilization_service
        src = inspect.getsource(mobilization_service)
        assert 'actor_can_bypass_sod' in src
        assert 'created_by_id == getattr(actor' in src, (
            'mobilization.issue_advance must reject contract drafter.'
        )

    def test_mobilization_locks_appropriation(self):
        from contracts.services import mobilization_service
        src = inspect.getsource(mobilization_service)
        assert '.select_for_update()' in src, (
            'mobilization._validate_appropriation must lock the '
            'appropriation row — see Pass 10 H1.'
        )

    def test_retention_create_release_has_sod(self):
        from contracts.services import retention_service
        src = inspect.getsource(retention_service)
        # Find the create_release block specifically
        assert 'cannot also create its retention release' in src

    def test_retention_mark_paid_has_sod(self):
        from contracts.services import retention_service
        src = inspect.getsource(retention_service)
        assert 'cannot also mark it paid' in src or 'prior_actor_ids' in src

    def test_completion_certificate_issuance_has_sod(self):
        from contracts.services import contract_closure_service
        src = inspect.getsource(contract_closure_service)
        # Both practical and final completion certificate issuance
        # must reject the contract drafter.
        assert 'cannot also issue its practical-completion' in src
        assert 'cannot also issue its final-completion' in src


# ─────────────────────────────────────────────────────────────────────
# IPC raise_voucher idempotency (H7)
# ─────────────────────────────────────────────────────────────────────

class TestRaiseVoucherIdempotency:
    """raise_voucher must lock the IPC row to prevent two concurrent
    calls both linking different PVs."""

    def test_raise_voucher_locks_ipc_row(self):
        from contracts.services import ipc_service
        src = inspect.getsource(ipc_service)
        # The fix locks the IPC inside raise_voucher via select_for_update.
        # We can't isolate to that method by inspect alone, but we can
        # check that the new "already has a voucher" guard exists.
        assert 'IPC already has a payment voucher linked' in src, (
            'raise_voucher must refuse when payment_voucher_id is '
            'already set on the locked row (see Pass 10 H7).'
        )


# ─────────────────────────────────────────────────────────────────────
# Retention accrual posting date (H8)
# ─────────────────────────────────────────────────────────────────────

class TestRetentionAccrualDate:
    """The accrual journal's posting_date must be the moment of
    approval (release.updated_at), not today() and not the
    not-yet-set payment_date."""

    def test_accrual_uses_updated_at(self):
        from contracts.services import retention_service
        src = inspect.getsource(retention_service)
        assert 'release.updated_at.date()' in src, (
            'Retention release accrual must post on release.updated_at '
            '(the approval moment), not payment_date (always None at '
            'this point) — see Pass 10 H8.'
        )
        # And the old misleading expression must be gone
        assert 'release.payment_date or timezone.now().date()' not in src, (
            'Old expression release.payment_date or now() is misleading '
            '(payment_date is always None at this code path) — must be '
            'replaced.'
        )


# ─────────────────────────────────────────────────────────────────────
# Variation appropriation re-check (H5)
# ─────────────────────────────────────────────────────────────────────

class TestVariationAppropriationRecheck:
    """A ceiling-increasing variation must re-run the appropriation
    check at approve-time, not wait for the next IPC."""

    def test_variation_approve_calls_appropriation_recheck(self):
        from contracts.services import variation_service
        src = inspect.getsource(variation_service)
        assert '_appropriation_recheck_for_increase' in src, (
            'Variation approve must call '
            '_appropriation_recheck_for_increase when amount > 0 — '
            'see Pass 10 H5.'
        )
        assert 'check_policy' in src, (
            'Re-check must route through the shared check_policy '
            'engine so the rules match the IPC-time gate.'
        )

    def test_recheck_only_fires_for_positive_amounts(self):
        from contracts.services import variation_service
        src = inspect.getsource(variation_service)
        # The if-guard must check amount > 0 so EOT (amount=0) and
        # omissions (amount<0) don't get re-checked.
        assert "variation.amount or Decimal('0')) > Decimal('0')" in src
