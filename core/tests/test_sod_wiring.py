"""
SoD wiring tests — proves the four critical action paths are guarded.

These tests intentionally stay no-DB / pure-Python so they run on the
fast tier. They verify the **wiring** (imports + handler contract) not
the evaluator's matching logic — that is already covered by
``test_s23_roles_and_sod.py``.

Three things are checked:

1. ``enforce_action`` is imported by every wired view (text-search
   the source). This catches accidental removal during refactors.
2. ``core.drf_exception_handler.project_exception_handler`` is the
   registered ``EXCEPTION_HANDLER`` in REST_FRAMEWORK settings.
3. The handler returns a 403 with the structured ``violations``
   payload when given a synthetic ``SoDViolation``.
"""
from __future__ import annotations

import inspect


class TestEnforceActionImports:
    """Each wired view must reference enforce_action by name.

    A grep on the file source is the cheapest reliable signal — the
    actual function is imported lazily inside the action handler so we
    can't introspect via the module namespace.
    """

    def _source_of(self, dotted_view_path: str) -> str:
        """Return the source text of the module hosting the wired view."""
        module_path, _ = dotted_view_path.rsplit('.', 1)
        import importlib
        mod = importlib.import_module(module_path)
        return inspect.getsource(mod)

    def test_pr_approve_uses_enforce_action(self):
        src = self._source_of('procurement.views.PurchaseRequestViewSet')
        assert "enforce_action" in src, (
            "procurement.views must call enforce_action on PR approve"
        )
        assert "'procurement.pr.approve'" in src, (
            "Wiring must reference the seeded permission code"
        )

    def test_po_approve_uses_enforce_action(self):
        src = self._source_of('procurement.views.PurchaseOrderViewSet')
        assert "'procurement.po.approve'" in src, (
            "Wiring must reference the seeded PO-approve permission code"
        )

    def test_journal_post_uses_enforce_action(self):
        src = self._source_of('accounting.views.core_gl.JournalHeaderViewSet')
        assert "enforce_action" in src, (
            "core_gl must call enforce_action on post_journal"
        )
        assert "'accounting.journal.post'" in src, (
            "Wiring must reference the seeded journal-post permission code"
        )

    def test_pv_mark_paid_uses_enforce_action(self):
        # PaymentVoucherViewSet hosts mark_paid in treasury_revenue.
        from accounting.views import treasury_revenue
        src = inspect.getsource(treasury_revenue)
        assert "enforce_action" in src, (
            "treasury_revenue must call enforce_action on mark_paid"
        )
        assert "'treasury.voucher.pay'" in src, (
            "Wiring must reference the seeded PV-pay permission code"
        )


class TestExceptionHandlerWired:
    """``EXCEPTION_HANDLER`` must point at our handler."""

    def test_settings_registers_custom_handler(self):
        from django.conf import settings
        rest = getattr(settings, 'REST_FRAMEWORK', {})
        assert rest.get('EXCEPTION_HANDLER') == (
            'core.drf_exception_handler.project_exception_handler'
        ), (
            "REST_FRAMEWORK['EXCEPTION_HANDLER'] must point at the "
            "project handler so SoDViolation lands as a structured 403"
        )

    def test_handler_translates_sod_violation_to_403(self):
        """The handler returns 403 + the violations payload that the
        React UI reads to render one banner per blocking rule.
        """
        from core.drf_exception_handler import project_exception_handler
        from core.services.sod_evaluator import SoDViolation, Violation

        synthetic = Violation(
            rule_id=42,
            rule_code='sod.test.case',
            rule_name='Test rule',
            scope='same_document',
            severity='block',
            permission_a_code='module.thing.create',
            permission_a_label='Create thing',
            permission_b_code='module.thing.approve',
            permission_b_label='Approve thing',
            reason='Creator cannot approve',
        )
        response = project_exception_handler(
            SoDViolation([synthetic]),
            {'request': None},
        )
        assert response is not None, "Handler must not fall through for SoDViolation"
        assert response.status_code == 403
        body = response.data
        assert body['detail']
        assert body['error']
        assert isinstance(body['violations'], list)
        assert len(body['violations']) == 1
        v = body['violations'][0]
        assert v['rule_id'] == 42
        assert v['rule_code'] == 'sod.test.case'
        assert v['severity'] == 'block'
        assert v['permission_a']['code'] == 'module.thing.create'
        assert v['permission_b']['code'] == 'module.thing.approve'
        assert v['reason'] == 'Creator cannot approve'

    def test_handler_falls_through_for_other_exceptions(self):
        """Anything that isn't a SoDViolation must reach the DRF
        default handler — we don't want to swallow ValidationError /
        Http404 / PermissionDenied accidentally.
        """
        from core.drf_exception_handler import project_exception_handler
        from rest_framework.exceptions import ValidationError

        # DRF default handler returns a Response for known DRF exceptions.
        response = project_exception_handler(
            ValidationError("bad"),
            {'request': None, 'view': None},
        )
        assert response is not None
        assert response.status_code == 400


class TestSafeAdditiveContract:
    """The evaluator returns an empty violation list when no rule
    matches the action's permission code. That is the property that
    makes wiring ``enforce_action`` safe to ship without seeding any
    SoD rules: tenants see zero behaviour change until they configure
    rules in the admin UI.
    """

    def test_check_action_returns_empty_when_no_rules_match(self, monkeypatch):
        """Patch SoDRule.objects.filter to return an empty QuerySet
        so we test the early-out path without touching the DB.
        """
        from core.services import sod_evaluator

        class _FakeQS:
            def filter(self, *a, **kw):
                return self
            def select_related(self, *a, **kw):
                return self
            def __iter__(self):
                return iter([])

        class _FakeManager:
            objects = _FakeQS()

        monkeypatch.setattr(
            sod_evaluator,
            'actor_can_bypass',
            lambda _user: False,
        )
        # Patch the lazy SoDRule import inside check_action by
        # injecting a fake into core.models. The function does a
        # ``from core.models import SoDRule`` at call time.
        import core.models as core_models
        monkeypatch.setattr(core_models, 'SoDRule', _FakeManager, raising=False)

        # A plain object stands in for the document.
        class _Doc:
            pk = 1
            created_by_id = 999

        class _User:
            pk = 1
            is_authenticated = True
            is_superuser = False
            is_staff = False
            def has_perm(self, _perm):
                return False

        violations = sod_evaluator.check_action(
            _User(), 'module.thing.approve', _Doc(),
        )
        assert violations == [], (
            "With no matching rule, evaluator must return empty list — "
            "this is the safe-additive guarantee that lets us wire "
            "enforce_action without a behaviour change"
        )
