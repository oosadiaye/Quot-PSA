"""Tests for accounting/signals/workflow_dispatch.py.

All tests run without a real database — the receiver logic is isolated
via MagicMock and unittest.mock.patch. Pattern mirrors test_s6_mfa.py.

Because the receiver uses lazy ``from X import Y`` inside the function
body (to avoid circular imports at app startup), we patch at the SOURCE
module path rather than the local name in the receiver module.

Coverage:
  * JournalHeader auto-post fires when signal arrives with the right model_name
  * Auto-post is skipped when header is already 'Posted' (idempotency)
  * Signal for a different model_name is ignored (tight scoping)
  * Reject action is ignored
  * Service failure is logged as WARNING and NOT re-raised
  * None document is silently skipped
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fire_signal(model_name, document, action='approve'):
    """Call the receiver function directly — DB-free, no Django dispatch."""
    from accounting.signals.workflow_dispatch import auto_post_journalheader_on_approval

    auto_post_journalheader_on_approval(
        sender=MagicMock(),
        approval=MagicMock(pk=1),
        model_name=model_name,
        document=document,
        action=action,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestJournalHeaderAutoPost:

    def test_journalheader_auto_post_fires_on_approve(self):
        """Signal with model_name='journalheader' and action='approve' calls
        IPSASJournalService.post_journal once with the header document."""
        header = MagicMock()
        header.status = 'Approved'
        header.pk = 42

        with patch(
            'accounting.services.ipsas_journal_service.IPSASJournalService.post_journal',
        ) as mock_post:
            _fire_signal('journalheader', header)

        mock_post.assert_called_once_with(header, user=None)

    def test_journalheader_skipped_when_already_posted(self):
        """Header whose status is already 'Posted' is silently skipped —
        idempotency guard prevents double-posting."""
        header = MagicMock()
        header.status = 'Posted'
        header.pk = 99

        with patch(
            'accounting.services.ipsas_journal_service.IPSASJournalService.post_journal',
        ) as mock_post:
            _fire_signal('journalheader', header)

        mock_post.assert_not_called()

    def test_journalheader_other_model_name_ignored(self):
        """Signal for a different document type must not invoke the service."""
        document = MagicMock()
        document.status = 'Approved'

        with patch(
            'accounting.services.ipsas_journal_service.IPSASJournalService.post_journal',
        ) as mock_post:
            _fire_signal('vendorinvoice', document)

        mock_post.assert_not_called()

    def test_journalheader_other_action_ignored(self):
        """Reject actions must not trigger auto-post."""
        header = MagicMock()
        header.status = 'Rejected'
        header.pk = 7

        with patch(
            'accounting.services.ipsas_journal_service.IPSASJournalService.post_journal',
        ) as mock_post:
            _fire_signal('journalheader', header, action='reject')

        mock_post.assert_not_called()

    def test_journalheader_failure_logged_not_raised(self):
        """When IPSASJournalService.post_journal raises, the receiver logs a
        WARNING but does NOT re-raise, preserving the approval commit."""
        header = MagicMock()
        header.status = 'Approved'
        header.pk = 55

        boom = ValueError('GL period closed')

        with patch(
            'accounting.services.ipsas_journal_service.IPSASJournalService.post_journal',
            side_effect=boom,
        ), patch(
            'accounting.signals.workflow_dispatch.logger',
        ) as mock_logger, patch(
            'accounting.models.gl.JournalHeader',
        ):
            # Must NOT raise
            _fire_signal('journalheader', header)

        # Warning was logged
        assert mock_logger.warning.called
        log_call_args = mock_logger.warning.call_args[0]
        assert 'JournalHeader' in log_call_args[0]

    def test_journalheader_none_document_ignored(self):
        """None document should be silently skipped."""
        with patch(
            'accounting.services.ipsas_journal_service.IPSASJournalService.post_journal',
        ) as mock_post:
            _fire_signal('journalheader', document=None)

        mock_post.assert_not_called()
