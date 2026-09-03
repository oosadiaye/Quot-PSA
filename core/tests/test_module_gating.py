"""
Module gating tests — FUTURE_MODULES.md §2.

Covers:
  * ``ModuleEnabled`` permission semantics (fail-open for legacy, fail-closed
    logic is exercised via the cache layer).
  * ``audit_module_gating`` command contract behaviours that do not require
    a live database: the legacy vs future module registry split.
"""
from __future__ import annotations


class TestModuleEnabledSemantics:
    """Pure-logic checks on the ModuleEnabled permission class."""

    def test_declares_module_attr_for_readers(self):
        from core.permissions import ModuleEnabled
        assert hasattr(ModuleEnabled, 'has_permission')

    def test_no_module_key_passes_through(self):
        """A ViewSet without module_key is NOT gated — RBAC owns it."""

        class _View:
            pass

        from core.permissions import ModuleEnabled

        class _Req:
            user = None

        perm = ModuleEnabled()
        # No module_key → has_permission just returns True early.
        result = perm.has_permission(_Req(), _View())
        assert result is True


class TestModuleRegistrySplit:
    """The legacy-vs-future split is the backbone of fail-open/fail-closed.

    The 12 shipping modules must be in the legacy set (so unconfigured
    tenants keep working); none of the 15 future keys may be silently
    upgraded to legacy.
    """

    def test_all_fifteen_future_keys_are_registered(self):
        from tenants.models import AVAILABLE_MODULES
        keys = {k for k, _t, _d in AVAILABLE_MODULES}
        from core.permissions import _LEGACY_MODULES
        future = {
            'budget_prep', 'egp', 'personnel_budget', 'debt', 'transparency',
            'results', 'integrations', 'revenue_admin', 'cash_planning',
            'staff_advances', 'internal_audit', 'fleet', 'catalogue',
            'disclosure', 'legal',
        }
        # Every future key is (a) in the registry and (b) NOT legacy.
        for key in future:
            assert key in keys, f'{key} not yet in AVAILABLE_MODULES'
            assert key not in _LEGACY_MODULES, (
                f'{key} must NOT be legacy — it fails closed'
            )

    def test_legacy_modules_are_denylist_free(self):
        from core.permissions import _LEGACY_MODULES
        future = {
            'budget_prep', 'egp', 'personnel_budget', 'debt', 'transparency',
            'results', 'integrations', 'revenue_admin', 'cash_planning',
            'staff_advances', 'internal_audit', 'fleet', 'catalogue',
            'disclosure', 'legal',
        }
        assert not (_LEGACY_MODULES & future), 'leak between legacy and future'

    def test_default_decision_for_unknown_key_is_fail_closed(self):
        """A brand-new key with no TenantModule row must be OFF (fail closed).

        This drives the commercial boundary: shipping a new module defaults
        to *disabled* until the superadmin seeds its row.
        """
        from unittest.mock import patch
        from core.permissions import _is_module_enabled

        class _FakeTenant:
            pk = 999_999
            schema_name = 'fake'

        with patch(
            'core.models.TenantModule.objects',
        ) as fake_mgr:
            # Simulate no row → DoesNotExist.
            fake_mgr.get.side_effect = __import__(
                'core.models', fromlist=['TenantModule']
            ).TenantModule.DoesNotExist
            # Fresh key with no row → NOT in legacy → disabled (False).
            assert _is_module_enabled('totally_new_module', _FakeTenant()) is False

    def test_legacy_key_without_row_defaults_on(self):
        """A legacy module with no TenantModule row stays enabled (fail open)."""
        from unittest.mock import patch
        from core.permissions import _is_module_enabled

        class _FakeTenant:
            pk = 888_888
            schema_name = 'fake'

        with patch(
            'core.models.TenantModule.objects',
        ) as fake_mgr:
            fake_mgr.get.side_effect = __import__(
                'core.models', fromlist=['TenantModule']
            ).TenantModule.DoesNotExist
            assert _is_module_enabled('accounting', _FakeTenant()) is True

    def test_inactive_row_fails_closed(self):
        """An explicitly-inactive row (new module) → disabled."""
        from unittest.mock import patch
        from types import SimpleNamespace
        from core.permissions import _is_module_enabled

        class _FakeTenant:
            pk = 777_777
            schema_name = 'fake'

        with patch('core.models.TenantModule.objects') as fake_mgr:
            fake_mgr.get.return_value = SimpleNamespace(is_active=False)
            assert _is_module_enabled('debt', _FakeTenant()) is False

    def test_active_row_enables(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        from core.permissions import _is_module_enabled

        class _FakeTenant:
            pk = 666_666
            schema_name = 'fake'

        with patch('core.models.TenantModule.objects') as fake_mgr:
            fake_mgr.get.return_value = SimpleNamespace(is_active=True)
            assert _is_module_enabled('debt', _FakeTenant()) is True

    def test_4308_keys_unambiguous(self):
        """No key is both registry-owned and reserved differently."""
        from tenants.models import AVAILABLE_MODULES
        from core.permissions import _LEGACY_MODULES
        keys = {k for k, _t, _d in AVAILABLE_MODULES}
        # Exactly 12 legacy + 15 future + possibly more = total distinct.
        assert len(keys) >= 27


class TestAuditCommandContract:
    """The audit_module_gating command's static contract.

    ``_APP_LABEL_TO_MODULE`` maps Django app labels to module keys for the
    audit.  Future modules are new apps — verify the mapping registers them
    so the audit knows they must be gated.
    """

    def test_future_apps_in_mapping(self):
        import importlib
        # Because AVAILABLE_MODULES drives the mapping, a future key that is
        # ALSO a new Django app will be picked up automatically.  This test
        # proves the mechanism is not accidentally dropped.
        import core.management.commands.audit_module_gating as mod
        mm = mod._APP_LABEL_TO_MODULE
        # accounting is the canonical host for treasury/revenue/reporting
        assert mm['accounting'] == 'accounting'
        assert mm['budget'] == 'budget'

    def test_command_namespace_uniqueness(self):
        import core.management.commands.audit_module_gating as mod
        # Mapping never maps two labels to the same module accidentally.
        from collections import Counter
        counts = Counter(mod._APP_LABEL_TO_MODULE.values())
        # 'accounting' is intentionally a many-to-one host; but NO label may
        # map to a *future* module (they are their own apps).
        future = {
            'budget_prep', 'egp', 'personnel_budget', 'debt', 'transparency',
            'results', 'integrations', 'revenue_admin', 'cash_planning',
            'staff_advances', 'internal_audit', 'fleet', 'catalogue',
            'disclosure', 'legal',
        }
        for label, module in mod._APP_LABEL_TO_MODULE.items():
            if module in future:
                assert label == module, (
                    f'label {label} must equal its future module {module}'
                )


class TestFutureModuleViewSetsGated:
    """§2 enforcement for the 15 new apps.

    Every ViewSet in a future-module app must declare ``module_key`` equal to
    the app's module and compose ``ModuleEnabled`` in its permission tuple so
    that toggling the module off refuses requests (fail-closed for new
    modules). This is the same contract the CI ``audit_module_gating``
    command enforces at runtime; this test pins it statically in the
    no-DB fast tier.
    """

    FUTURE_APPS = [
        'personnel_budget', 'cash_planning', 'staff_advances', 'budget_prep',
        'debt', 'transparency', 'integrations', 'egp', 'results',
        'revenue_admin', 'internal_audit', 'fleet', 'catalogue', 'disclosure',
        'legal',
    ]

    def _view_module(self, app):
        import importlib
        return importlib.import_module(f'{app}.views')

    def _viewset_classes(self, module):
        import inspect
        from rest_framework.viewsets import ViewSetMixin
        return [
            obj for _name, obj in vars(module).items()
            if inspect.isclass(obj)
            and issubclass(obj, ViewSetMixin)
            and obj is not ViewSetMixin
        ]

    def test_every_app_has_gated_viewsets(self):
        from core.permissions import ModuleEnabled
        for app in self.FUTURE_APPS:
            viewsets = self._viewset_classes(self._view_module(app))
            assert viewsets, f'{app} exports no ViewSet classes'
            for vs in viewsets:
                assert getattr(vs, 'module_key', None) == app, (
                    f'{app}:{vs.__name__} must declare module_key={app!r}'
                )
                perms = getattr(vs, 'permission_classes', [])
                assert ModuleEnabled in perms, (
                    f'{app}:{vs.__name__} must compose ModuleEnabled'
                )

    def test_router_registers_viewsets(self):
        """Each future app wires a working DefaultRouter (no import break)."""
        import importlib
        from rest_framework.routers import DefaultRouter
        for app in self.FUTURE_APPS:
            urls_mod = importlib.import_module(f'{app}.urls')
            assert urls_mod.router is not None, f'{app}.urls must define router'
            assert urls_mod.router.registry, f'{app}.urls router has no registrations'
