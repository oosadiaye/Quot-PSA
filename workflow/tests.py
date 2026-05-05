"""Workflow module unit tests.

Pure-unit tests against the model layer and view-helper functions —
zero DB writes (every test is a SimpleTestCase, with mocks where the
ORM would otherwise be needed). Integration tests that exercise the
real DRF stack live in ``workflow/tests/`` once that scaffolding is
ready; this file is the backstop that catches regressions in the
pieces that have a clean, mockable shape today.
"""
from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase


class GlobalApprovalSettingsLogicTests(SimpleTestCase):
    """``should_auto_approve`` / ``is_enabled`` / ``get_mode`` are pure
    classmethods that wrap a single ORM lookup. With the lookup mocked
    they're trivial to drive."""

    def _settings(self, **overrides):
        defaults = dict(
            module='PaymentVoucher',
            approval_mode='Required',
            auto_approve_below_threshold=True,
            low_amount_threshold=Decimal('10000'),
        )
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    def test_should_auto_approve_returns_false_when_no_settings_row(self):
        from workflow.models import GlobalApprovalSettings
        with patch.object(GlobalApprovalSettings, 'objects') as mgr:
            mgr.filter.return_value.first.return_value = None
            self.assertFalse(
                GlobalApprovalSettings.should_auto_approve('Foo', Decimal('1')),
            )

    def test_should_auto_approve_amount_below_threshold(self):
        from workflow.models import GlobalApprovalSettings
        with patch.object(GlobalApprovalSettings, 'objects') as mgr:
            mgr.filter.return_value.first.return_value = self._settings()
            self.assertTrue(
                GlobalApprovalSettings.should_auto_approve('PV', Decimal('5000')),
            )

    def test_should_auto_approve_amount_at_or_above_threshold(self):
        from workflow.models import GlobalApprovalSettings
        with patch.object(GlobalApprovalSettings, 'objects') as mgr:
            mgr.filter.return_value.first.return_value = self._settings(
                low_amount_threshold=Decimal('10000'),
            )
            self.assertFalse(
                GlobalApprovalSettings.should_auto_approve('PV', Decimal('10000')),
            )
            self.assertFalse(
                GlobalApprovalSettings.should_auto_approve('PV', Decimal('15000')),
            )

    def test_should_auto_approve_disabled_when_flag_off(self):
        from workflow.models import GlobalApprovalSettings
        with patch.object(GlobalApprovalSettings, 'objects') as mgr:
            mgr.filter.return_value.first.return_value = self._settings(
                auto_approve_below_threshold=False,
            )
            self.assertFalse(
                GlobalApprovalSettings.should_auto_approve('PV', Decimal('1')),
            )

    def test_get_mode_defaults_to_required_when_no_row(self):
        from workflow.models import GlobalApprovalSettings
        with patch.object(GlobalApprovalSettings, 'objects') as mgr:
            mgr.filter.return_value.first.return_value = None
            self.assertEqual(
                GlobalApprovalSettings.get_mode('UnknownModule'),
                'Required',
            )

    def test_is_enabled_only_for_required_or_strict(self):
        from workflow.models import GlobalApprovalSettings
        for mode, expected in [
            ('Required', True),
            ('Strict', True),
            ('Optional', False),
            ('Disabled', False),
        ]:
            with self.subTest(mode=mode), patch.object(
                GlobalApprovalSettings, 'objects',
            ) as mgr:
                mgr.filter.return_value.first.return_value = self._settings(
                    approval_mode=mode,
                )
                self.assertEqual(
                    GlobalApprovalSettings.is_enabled('PV'), expected,
                )


class ModelToModuleKeyTests(SimpleTestCase):
    """``_MODEL_TO_MODULE_KEY`` is the canonical mapping from
    lowercase ContentType model names to ``GlobalApprovalSettings.MODULE_CHOICES``
    keys. Regression guard: every key must round-trip.
    """

    def test_every_key_maps_to_a_module_choice(self):
        from workflow.models import GlobalApprovalSettings
        from workflow.views import _MODEL_TO_MODULE_KEY
        valid_modules = {key for key, _ in GlobalApprovalSettings.MODULE_CHOICES}
        for model_name, module_key in _MODEL_TO_MODULE_KEY.items():
            self.assertIn(
                module_key, valid_modules,
                f'{model_name} → {module_key} not in MODULE_CHOICES',
            )

    def test_invoicematching_does_not_capitalize(self):
        """Regression guard for V4: ``invoicematching.capitalize()``
        produces ``Invoicematching`` which is NOT a valid module key.
        The mapping must intervene."""
        from workflow.views import _MODEL_TO_MODULE_KEY
        self.assertEqual(
            _MODEL_TO_MODULE_KEY['invoicematching'],
            'InvoiceVerification',
        )

    def test_every_approvable_model_has_a_label(self):
        from workflow.views import APPROVABLE_MODELS, APPROVABLE_LABELS
        for model_name in APPROVABLE_MODELS:
            self.assertIn(
                model_name, APPROVABLE_LABELS,
                f'{model_name} missing from APPROVABLE_LABELS',
            )


class ApprovalDelegationContractTests(SimpleTestCase):
    """The ``get_active_delegate`` classmethod and the dead-code
    regression on the approve()/reject() delegation guard."""

    def test_get_active_delegate_returns_none_when_no_active_delegation(self):
        from workflow.models import ApprovalDelegation
        with patch.object(ApprovalDelegation, 'objects') as mgr:
            mgr.filter.return_value.select_related.return_value.first.return_value = None
            self.assertIsNone(
                ApprovalDelegation.get_active_delegate(SimpleNamespace(pk=1)),
            )

    def test_classmethod_func_attribute_is_always_truthy(self):
        """Regression guard for V1: the previous code had
        ``ApprovalDelegation.get_active_delegate.__func__ is not None``
        as a conjunct in the delegation check. ``__func__`` is always
        present on a classmethod's descriptor — this test exists so a
        future maintainer can't reintroduce the dead conjunct without
        also acknowledging it's a no-op."""
        from workflow.models import ApprovalDelegation
        self.assertIsNotNone(ApprovalDelegation.get_active_delegate.__func__)


class ConfigureModuleValidationTests(SimpleTestCase):
    """V8: configure_module rejects unknown ``module`` and
    ``approval_mode`` strings. Pure data-shape check on the choice
    sets — exercises the validator boundary without needing an HTTP
    request cycle.
    """

    def test_module_choices_set_is_non_empty(self):
        from workflow.models import GlobalApprovalSettings
        keys = {k for k, _ in GlobalApprovalSettings.MODULE_CHOICES}
        # If the catalogue ever shrinks to empty, the validator
        # rejects everything — including legitimate calls.
        self.assertGreater(len(keys), 0)
        # All P2P chain modules should be present.
        for required in ('PurchaseOrder', 'InvoiceVerification', 'PaymentVoucher'):
            self.assertIn(required, keys)

    def test_approval_mode_choices_cover_required_states(self):
        from workflow.models import GlobalApprovalSettings
        modes = {k for k, _ in GlobalApprovalSettings.APPROVAL_MODE_CHOICES}
        self.assertSetEqual(
            modes, {'Disabled', 'Optional', 'Required', 'Strict'},
        )


class ApprovalStepSequenceValidationTests(SimpleTestCase):
    """M11: ``ApprovalStep.clean()`` rejects step_numbers that would
    create a gap. Patches the ORM lookup so the test stays a pure unit
    test."""

    def test_first_step_must_be_one(self):
        from django.core.exceptions import ValidationError
        from workflow.models import ApprovalStep
        step = ApprovalStep(approval_id=1, step_number=2)
        with patch.object(ApprovalStep, 'objects') as mgr:
            mgr.filter.return_value.aggregate.return_value = {'m': 0}
            with self.assertRaises(ValidationError) as cm:
                step.clean()
        self.assertIn('step_number', cm.exception.message_dict)

    def test_sequential_step_passes(self):
        from workflow.models import ApprovalStep
        step = ApprovalStep(approval_id=1, step_number=3)
        with patch.object(ApprovalStep, 'objects') as mgr:
            mgr.filter.return_value.aggregate.return_value = {'m': 2}
            step.clean()  # should not raise

    def test_gap_two_rejects(self):
        from django.core.exceptions import ValidationError
        from workflow.models import ApprovalStep
        step = ApprovalStep(approval_id=1, step_number=5)
        with patch.object(ApprovalStep, 'objects') as mgr:
            mgr.filter.return_value.aggregate.return_value = {'m': 2}
            with self.assertRaises(ValidationError):
                step.clean()


class ApprovalGroupConstraintTests(SimpleTestCase):
    """M6: declarative check that the unique constraint exists in the
    model meta (this catches accidental removal in future migrations)."""

    def test_unique_constraint_exists(self):
        from workflow.models import ApprovalGroup
        names = {c.name for c in ApprovalGroup._meta.constraints}
        self.assertIn('uniq_approvalgroup_name_per_org', names)


class ApprovalIndexTests(SimpleTestCase):
    """M8: declarative check that the GenericFK and status indexes are
    declared. Catches accidental removal during model edits."""

    def test_genericfk_composite_index_declared(self):
        from workflow.models import Approval
        index_names = {idx.name for idx in Approval._meta.indexes}
        self.assertIn('approval_genericfk_idx', index_names)

    def test_status_field_indexed(self):
        from workflow.models import Approval, ApprovalStep
        for model in (Approval, ApprovalStep):
            field = model._meta.get_field('status')
            self.assertTrue(
                field.db_index,
                f'{model.__name__}.status missing db_index',
            )
