"""Tests for budget/signals.py — workflow-dispatch receivers.

All tests run without a real database — document objects are MagicMocks
and the DB layer is patched out. Pattern mirrors accounting/tests/test_s6_mfa.py.

Because each receiver uses a lazy import inside the function body, we patch
at the SOURCE module path (e.g. ``budget.models.Warrant``).

Coverage:
  Warrant receiver
  * Warrant auto-release fires when model_name='warrant' and action='approve'
  * Already-released warrant is skipped (idempotency, pre-lock check)
  * Already-released warrant is skipped (idempotency, under-lock check)
  * Expired warrant is skipped
  * Signal for a different model_name is a no-op
  * Reject action is a no-op
  * None document is silently skipped
  * Service failure causes the handler to re-raise (rolls back approval)

  AppropriationVirement receiver
  * Fires on approve + model_name='appropriationvirement'
  * Skipped when status already 'APPLIED' (pre-lock)
  * Skipped when status already 'APPLIED' (under-lock)
  * Other model_name is ignored
  * Service failure re-raises

  RevenueBudget receiver
  * Fires on approve + model_name='revenuebudget'
  * Skipped when status already 'ACTIVE' (pre-lock)
  * Other model_name is ignored
  * Save failure re-raises

  Appropriation receiver
  * Fires on approve + model_name='appropriation'
  * Skipped when status already 'ACTIVE' (pre-lock)
  * Other model_name is ignored
  * full_clean() failure re-raises (NCoA bridge missing)
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_warrant(status='Approved', pk=1):
    w = MagicMock()
    w.status = status
    w.pk = pk
    return w


def _fire_signal(model_name, document, action='approve'):
    """Call the receiver function directly — DB-free, no Django dispatch."""
    from budget.signals import auto_release_warrant_on_approval

    auto_release_warrant_on_approval(
        sender=MagicMock(),
        approval=MagicMock(pk=999),
        model_name=model_name,
        document=document,
        action=action,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestWarrantAutoRelease:

    def test_warrant_auto_release_fires_on_approve(self):
        """Warrant with status='Approved' (workflow generic) is transitioned
        to 'RELEASED' when signal fires with model_name='warrant'."""
        warrant_doc = _make_warrant(status='Approved')

        # The receiver does select_for_update().get() → return a fresh mock
        locked_warrant = MagicMock()
        locked_warrant.status = 'Approved'  # status under lock

        with patch('budget.models.Warrant') as mock_warrant_cls:
            mock_warrant_cls.objects.select_for_update.return_value \
                .get.return_value = locked_warrant

            _fire_signal('warrant', warrant_doc)

        # Warrant was saved with 'RELEASED'
        assert locked_warrant.status == 'RELEASED'
        locked_warrant.save.assert_called_once_with(
            update_fields=['status', 'updated_at']
        )

    def test_warrant_skipped_when_already_released(self):
        """Warrant already in 'RELEASED' state is silently skipped (pre-lock)."""
        warrant_doc = _make_warrant(status='RELEASED')

        with patch('budget.models.Warrant') as mock_warrant_cls:
            _fire_signal('warrant', warrant_doc)

        # select_for_update should never be called — early return
        mock_warrant_cls.objects.select_for_update.assert_not_called()

    def test_warrant_skipped_when_expired(self):
        """Warrant in 'EXPIRED' state is silently skipped (pre-lock)."""
        warrant_doc = _make_warrant(status='EXPIRED')

        with patch('budget.models.Warrant') as mock_warrant_cls:
            _fire_signal('warrant', warrant_doc)

        mock_warrant_cls.objects.select_for_update.assert_not_called()

    def test_warrant_other_model_name_ignored(self):
        """Signal for a different model_name must not touch any Warrant."""
        doc = MagicMock()
        doc.status = 'Approved'

        with patch('budget.models.Warrant') as mock_warrant_cls:
            _fire_signal('paymentvouchergov', doc)

        mock_warrant_cls.objects.select_for_update.assert_not_called()

    def test_warrant_other_action_ignored(self):
        """Reject action must not release the warrant."""
        warrant_doc = _make_warrant(status='Approved')

        with patch('budget.models.Warrant') as mock_warrant_cls:
            _fire_signal('warrant', warrant_doc, action='reject')

        mock_warrant_cls.objects.select_for_update.assert_not_called()

    def test_warrant_failure_reraises(self):
        """When save() raises, the handler re-raises so the approval's
        transaction.atomic() rolls back and no half-released warrant
        corrupts Appropriation.total_warrants_released."""
        warrant_doc = _make_warrant(status='Approved')

        boom = RuntimeError('DB constraint violated')
        locked_warrant = MagicMock()
        locked_warrant.status = 'Approved'
        locked_warrant.save.side_effect = boom

        with patch('budget.models.Warrant') as mock_warrant_cls:
            mock_warrant_cls.objects.select_for_update.return_value \
                .get.return_value = locked_warrant

            with pytest.raises(RuntimeError, match='DB constraint violated'):
                _fire_signal('warrant', warrant_doc)

    def test_warrant_none_document_ignored(self):
        """None document should be silently skipped."""
        with patch('budget.models.Warrant') as mock_warrant_cls:
            _fire_signal('warrant', document=None)

        mock_warrant_cls.objects.select_for_update.assert_not_called()

    def test_warrant_already_released_under_lock_skipped(self):
        """If the warrant is found to be already RELEASED after acquiring
        the row lock (race condition), the handler exits without saving."""
        warrant_doc = _make_warrant(status='Approved')

        # Another process released it between the initial status check and lock
        locked_warrant = MagicMock()
        locked_warrant.status = 'RELEASED'

        with patch('budget.models.Warrant') as mock_warrant_cls:
            mock_warrant_cls.objects.select_for_update.return_value \
                .get.return_value = locked_warrant

            _fire_signal('warrant', warrant_doc)

        locked_warrant.save.assert_not_called()


# ---------------------------------------------------------------------------
# AppropriationVirement receiver helpers + tests
# ---------------------------------------------------------------------------

def _make_virement_doc(status='SUBMITTED', pk=10):
    v = MagicMock()
    v.status = status
    v.pk = pk
    return v


def _fire_virement_signal(model_name, document, action='approve'):
    from budget.signals import auto_apply_virement_on_approval
    auto_apply_virement_on_approval(
        sender=MagicMock(),
        approval=MagicMock(pk=888, approved_by=None, created_by=None),
        model_name=model_name,
        document=document,
        action=action,
    )


class TestVirementAutoApply:

    def test_virement_fires_on_approve(self):
        """approve_and_apply_virement is called when model_name='appropriationvirement'."""
        doc = _make_virement_doc(status='SUBMITTED')

        locked_virement = MagicMock()
        locked_virement.status = 'SUBMITTED'

        with patch('budget.models.AppropriationVirement') as mock_cls, \
             patch('budget.services_virement.approve_and_apply_virement') as mock_apply:
            mock_cls.objects.select_for_update.return_value.get.return_value = locked_virement

            _fire_virement_signal('appropriationvirement', doc)

        mock_apply.assert_called_once_with(locked_virement, user=None)

    def test_virement_skipped_when_already_applied_pre_lock(self):
        """Virement already 'APPLIED' is skipped before acquiring the row lock."""
        doc = _make_virement_doc(status='APPLIED')

        with patch('budget.models.AppropriationVirement') as mock_cls, \
             patch('budget.services_virement.approve_and_apply_virement') as mock_apply:

            _fire_virement_signal('appropriationvirement', doc)

        mock_cls.objects.select_for_update.assert_not_called()
        mock_apply.assert_not_called()

    def test_virement_skipped_when_already_applied_under_lock(self):
        """Virement found 'APPLIED' under lock (race condition) exits without calling service."""
        doc = _make_virement_doc(status='SUBMITTED')

        locked_virement = MagicMock()
        locked_virement.status = 'APPLIED'

        with patch('budget.models.AppropriationVirement') as mock_cls, \
             patch('budget.services_virement.approve_and_apply_virement') as mock_apply:
            mock_cls.objects.select_for_update.return_value.get.return_value = locked_virement

            _fire_virement_signal('appropriationvirement', doc)

        mock_apply.assert_not_called()

    def test_virement_other_model_name_ignored(self):
        """Signal for a different model_name must not call the virement service."""
        doc = _make_virement_doc(status='SUBMITTED')

        with patch('budget.models.AppropriationVirement') as mock_cls, \
             patch('budget.services_virement.approve_and_apply_virement') as mock_apply:

            _fire_virement_signal('warrant', doc)

        mock_cls.objects.select_for_update.assert_not_called()
        mock_apply.assert_not_called()

    def test_virement_failure_reraises(self):
        """Service failure re-raises so the workflow transaction rolls back."""
        doc = _make_virement_doc(status='SUBMITTED')

        locked_virement = MagicMock()
        locked_virement.status = 'SUBMITTED'

        boom = RuntimeError('source balance over-drawn')

        with patch('budget.models.AppropriationVirement') as mock_cls, \
             patch('budget.services_virement.approve_and_apply_virement') as mock_apply:
            mock_cls.objects.select_for_update.return_value.get.return_value = locked_virement
            mock_apply.side_effect = boom

            with pytest.raises(RuntimeError, match='source balance over-drawn'):
                _fire_virement_signal('appropriationvirement', doc)


# ---------------------------------------------------------------------------
# RevenueBudget receiver helpers + tests
# ---------------------------------------------------------------------------

def _make_revenue_budget_doc(status='DRAFT', pk=20):
    rb = MagicMock()
    rb.status = status
    rb.pk = pk
    return rb


def _fire_revenue_budget_signal(model_name, document, action='approve'):
    from budget.signals import auto_activate_revenue_budget_on_approval
    auto_activate_revenue_budget_on_approval(
        sender=MagicMock(),
        approval=MagicMock(pk=777),
        model_name=model_name,
        document=document,
        action=action,
    )


class TestRevenueBudgetAutoActivate:

    def test_revenue_budget_fires_on_approve(self):
        """RevenueBudget status is flipped to 'ACTIVE' on approve signal."""
        doc = _make_revenue_budget_doc(status='DRAFT')

        locked_rb = MagicMock()
        locked_rb.status = 'DRAFT'

        with patch('budget.models.RevenueBudget') as mock_cls:
            mock_cls.objects.select_for_update.return_value.get.return_value = locked_rb

            _fire_revenue_budget_signal('revenuebudget', doc)

        assert locked_rb.status == 'ACTIVE'
        locked_rb.save.assert_called_once_with(update_fields=['status', 'updated_at'])

    def test_revenue_budget_skipped_when_already_active(self):
        """RevenueBudget already 'ACTIVE' is skipped before acquiring the row lock."""
        doc = _make_revenue_budget_doc(status='ACTIVE')

        with patch('budget.models.RevenueBudget') as mock_cls:
            _fire_revenue_budget_signal('revenuebudget', doc)

        mock_cls.objects.select_for_update.assert_not_called()

    def test_revenue_budget_other_model_name_ignored(self):
        """Signal for a different model_name must not touch RevenueBudget."""
        doc = _make_revenue_budget_doc(status='DRAFT')

        with patch('budget.models.RevenueBudget') as mock_cls:
            _fire_revenue_budget_signal('appropriation', doc)

        mock_cls.objects.select_for_update.assert_not_called()

    def test_revenue_budget_failure_reraises(self):
        """Save failure re-raises so the workflow transaction rolls back."""
        doc = _make_revenue_budget_doc(status='DRAFT')

        locked_rb = MagicMock()
        locked_rb.status = 'DRAFT'
        locked_rb.save.side_effect = RuntimeError('DB write failed')

        with patch('budget.models.RevenueBudget') as mock_cls:
            mock_cls.objects.select_for_update.return_value.get.return_value = locked_rb

            with pytest.raises(RuntimeError, match='DB write failed'):
                _fire_revenue_budget_signal('revenuebudget', doc)


# ---------------------------------------------------------------------------
# Appropriation receiver helpers + tests
# ---------------------------------------------------------------------------

def _make_appropriation_doc(status='APPROVED', pk=30):
    a = MagicMock()
    a.status = status
    a.pk = pk
    return a


def _fire_appropriation_signal(model_name, document, action='approve'):
    from budget.signals import auto_activate_appropriation_on_approval
    auto_activate_appropriation_on_approval(
        sender=MagicMock(),
        approval=MagicMock(pk=666),
        model_name=model_name,
        document=document,
        action=action,
    )


class TestAppropriationAutoActivate:

    def test_appropriation_fires_on_approve(self):
        """Appropriation status is set to 'ACTIVE' and saved after full_clean()."""
        doc = _make_appropriation_doc(status='APPROVED')

        locked_app = MagicMock()
        locked_app.status = 'APPROVED'

        with patch('budget.models.Appropriation') as mock_cls:
            mock_cls.objects.select_for_update.return_value.get.return_value = locked_app

            _fire_appropriation_signal('appropriation', doc)

        assert locked_app.status == 'ACTIVE'
        locked_app.full_clean.assert_called_once()
        locked_app.save.assert_called_once_with(update_fields=['status', 'updated_at'])

    def test_appropriation_skipped_when_already_active(self):
        """Appropriation already 'ACTIVE' is skipped before acquiring the row lock."""
        doc = _make_appropriation_doc(status='ACTIVE')

        with patch('budget.models.Appropriation') as mock_cls:
            _fire_appropriation_signal('appropriation', doc)

        mock_cls.objects.select_for_update.assert_not_called()

    def test_appropriation_other_model_name_ignored(self):
        """Signal for a different model_name must not touch Appropriation."""
        doc = _make_appropriation_doc(status='APPROVED')

        with patch('budget.models.Appropriation') as mock_cls:
            _fire_appropriation_signal('revenuebudget', doc)

        mock_cls.objects.select_for_update.assert_not_called()

    def test_appropriation_full_clean_failure_reraises(self):
        """ValidationError from full_clean() (missing NCoA bridge) re-raises,
        rolling back the approval so the operator can fix bridges first."""
        from django.core.exceptions import ValidationError

        doc = _make_appropriation_doc(status='APPROVED')

        locked_app = MagicMock()
        locked_app.status = 'APPROVED'
        locked_app.full_clean.side_effect = ValidationError(
            {'status': 'administrative segment has no legacy_mda bridge'}
        )

        with patch('budget.models.Appropriation') as mock_cls:
            mock_cls.objects.select_for_update.return_value.get.return_value = locked_app

            with pytest.raises(ValidationError):
                _fire_appropriation_signal('appropriation', doc)

        # save must NOT have been called — the exception fired before it
        locked_app.save.assert_not_called()
