"""Tests for budget/signals.py — warrant auto-release receiver.

All tests run without a real database — warrant objects are MagicMocks
and the DB layer is patched out. Pattern mirrors accounting/tests/test_s6_mfa.py.

Because the receiver uses a lazy ``from budget.models import Warrant`` inside
the function body, we patch at the SOURCE module path.

Coverage:
  * Warrant auto-release fires when model_name='warrant' and action='approve'
  * Already-released warrant is skipped (idempotency, pre-lock check)
  * Already-released warrant is skipped (idempotency, under-lock check)
  * Expired warrant is skipped
  * Signal for a different model_name is a no-op
  * Reject action is a no-op
  * None document is silently skipped
  * Service failure causes the handler to re-raise (rolls back approval)
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
