"""
Unit tests for workflow/notifications.py

All database access is mocked — tests run in-process with no DB, no tenant
schema, no migrations required. This mirrors the pattern used in
contracts/tests/test_computations.py.

The tests exercise the notification orchestration logic:
  - Correct dispatch based on notification type
  - Respecting GlobalApprovalSettings.send_notifications / notify_requester
  - Graceful handling of missing records
  - Correct priority and category on in-app notifications
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch, call
import pytest


# ---------------------------------------------------------------------------
# Helpers to build cheap mock objects (no DB)
# ---------------------------------------------------------------------------

def _user(pk=1, username='user', first_name='Test', email='u@example.com', is_active=True):
    u = MagicMock()
    u.pk = pk
    u.username = username
    u.first_name = first_name
    u.email = email
    u.is_active = is_active
    u.get_full_name.return_value = f'{first_name} User'
    return u


def _content_type(model='paymentvoucher'):
    ct = MagicMock()
    ct.model = model
    return ct


def _approval(pk=1, title='PV #1', status='Pending', current_step=1, total_steps=2,
              amount=None, requested_by=None, content_type=None):
    a = MagicMock()
    a.pk = pk
    a.title = title
    a.status = status
    a.current_step = current_step
    a.total_steps = total_steps
    a.amount = amount
    a.requested_by = requested_by or _user(pk=10, username='requester')
    a.content_type = content_type or _content_type()
    a.template = None
    return a


def _step(pk=1, step_number=1, group=None, approver=None, status='Pending',
          due_date=None, comment='', approval=None):
    s = MagicMock()
    s.pk = pk
    s.step_number = step_number
    s.approver_group = group
    s.approver = approver
    s.status = status
    s.due_date = due_date
    s.comment = comment
    s.approval = approval or _approval()
    return s


def _group(pk=1, name='Finance Group'):
    g = MagicMock()
    g.pk = pk
    g.name = name
    return g


def _settings_obj(send_notifications=True, notify_requester=True):
    s = MagicMock()
    s.send_notifications = send_notifications
    s.notify_requester = notify_requester
    return s


# ---------------------------------------------------------------------------
# Patch targets
# ---------------------------------------------------------------------------

_MOD = 'workflow.notifications'
_APPROVAL_GET = f'{_MOD}.Approval.objects'
_STEP_GET = f'{_MOD}.ApprovalStep.objects'
_USER_FILTER = f'{_MOD}.User.objects'
_GLOBAL_SETTINGS = f'{_MOD}.GlobalApprovalSettings.objects'
_NOTIF_SEND = f'{_MOD}.Notification.send'
_EMAIL_SUBMITTED = f'{_MOD}.send_approval_submitted_email'
_EMAIL_COMPLETED = f'{_MOD}.send_approval_completed_email'
_EMAIL_REJECTED = f'{_MOD}.send_approval_rejected_email'
_EMAIL_ADVANCED = f'{_MOD}.send_approval_step_advanced_email'
_EMAIL_SLA = f'{_MOD}.send_approval_sla_breach_email'


def _patch_approval_get(approval):
    """Return a context-manager patcher that makes Approval.objects.select_related().get() return approval."""
    m = MagicMock()
    m.select_related.return_value.get.return_value = approval
    return patch(_APPROVAL_GET, m)


def _patch_step_get(step):
    m = MagicMock()
    m.select_related.return_value.get.return_value = step
    return patch(_STEP_GET, m)


def _patch_no_settings():
    """GlobalApprovalSettings.objects.filter().first() returns None → no restriction."""
    m = MagicMock()
    m.filter.return_value.first.return_value = None
    return patch(_GLOBAL_SETTINGS, m)


def _patch_with_settings(settings_mock):
    m = MagicMock()
    m.filter.return_value.first.return_value = settings_mock
    return patch(_GLOBAL_SETTINGS, m)


def _patch_step_qs(approval_mock, step):
    """Make approval.steps.filter().select_related().first() return step."""
    qs = MagicMock()
    qs.select_related.return_value.first.return_value = step
    approval_mock.steps.filter.return_value = qs
    return approval_mock


def _patch_approver_users(users):
    m = MagicMock()
    m.filter.return_value = users
    return patch(_USER_FILTER, m)


# ===========================================================================
# Tests: notify_approval_submitted
# ===========================================================================

class TestNotifyApprovalSubmitted:

    def _run(self, approval, step, approver_users, settings=None):
        """Wire all mocks and call notify_approval_submitted."""
        from workflow.notifications import notify_approval_submitted

        group = _group()
        group.effective_user_ids.return_value = {u.pk for u in approver_users}
        step.approver_group = group

        _patch_step_qs(approval, step)

        with _patch_approval_get(approval), \
             (_patch_with_settings(settings) if settings else _patch_no_settings()), \
             _patch_approver_users(approver_users), \
             patch(_EMAIL_SUBMITTED, return_value=True) as mock_email, \
             patch(_NOTIF_SEND) as mock_notif:
            notify_approval_submitted(approval.pk)
            return mock_email, mock_notif

    def test_sends_email_and_in_app_to_step1_approvers(self):
        approver = _user(pk=5)
        approval = _approval()
        step = _step(step_number=1, approval=approval)

        mock_email, mock_notif = self._run(approval, step, [approver])

        mock_email.assert_called_once()
        assert mock_email.call_args[0][0] == approver  # first positional = user
        mock_notif.assert_called_once()
        call_kwargs = mock_notif.call_args[1]
        assert call_kwargs['category'] == 'APPROVAL'
        assert call_kwargs['priority'] == 'NORMAL'

    def test_respects_send_notifications_false(self):
        settings = _settings_obj(send_notifications=False)
        approver = _user()
        approval = _approval()
        step = _step(approval=approval)

        mock_email, mock_notif = self._run(approval, step, [approver], settings)

        mock_email.assert_not_called()
        mock_notif.assert_not_called()

    def test_does_nothing_when_approval_not_found(self):
        from workflow.notifications import notify_approval_submitted

        m = MagicMock()
        m.select_related.return_value.get.side_effect = Exception('DoesNotExist')

        with patch('workflow.notifications.Approval') as mock_approval_class:
            mock_approval_class.DoesNotExist = Exception
            mock_approval_class.objects.select_related.return_value.get.side_effect = \
                mock_approval_class.DoesNotExist
            with patch(_NOTIF_SEND) as mock_notif, patch(_EMAIL_SUBMITTED) as mock_email:
                notify_approval_submitted(99999)
                mock_email.assert_not_called()
                mock_notif.assert_not_called()

    def test_no_recipients_when_step_has_no_group(self):
        approver = _user()
        approval = _approval()
        step = _step(step_number=1, approval=approval)
        step.approver_group = None  # no group

        _patch_step_qs(approval, step)

        with _patch_approval_get(approval), _patch_no_settings(), \
             _patch_approver_users([]), \
             patch(_EMAIL_SUBMITTED, return_value=True) as mock_email, \
             patch(_NOTIF_SEND) as mock_notif:
            from workflow.notifications import notify_approval_submitted
            notify_approval_submitted(approval.pk)

        mock_email.assert_not_called()
        mock_notif.assert_not_called()


# ===========================================================================
# Tests: notify_approval_step_advanced
# ===========================================================================

class TestNotifyApprovalStepAdvanced:

    def _run(self, approval, step, approver_users, new_step, settings=None):
        from workflow.notifications import notify_approval_step_advanced

        group = _group()
        group.effective_user_ids.return_value = {u.pk for u in approver_users}
        step.approver_group = group

        _patch_step_qs(approval, step)

        with _patch_approval_get(approval), \
             (_patch_with_settings(settings) if settings else _patch_no_settings()), \
             _patch_approver_users(approver_users), \
             patch(_EMAIL_ADVANCED, return_value=True) as mock_email, \
             patch(_NOTIF_SEND) as mock_notif:
            notify_approval_step_advanced(approval.pk, new_step)
            return mock_email, mock_notif

    def test_notifies_next_step_group(self):
        approver = _user(pk=7)
        approval = _approval(total_steps=3)
        step = _step(step_number=2, approval=approval)

        mock_email, mock_notif = self._run(approval, step, [approver], new_step=2)

        mock_email.assert_called_once()
        assert mock_email.call_args[0][0] == approver
        assert 'Step 2' in mock_notif.call_args[1]['message']

    def test_silent_when_notifications_off(self):
        settings = _settings_obj(send_notifications=False)
        mock_email, mock_notif = self._run(
            _approval(), _step(), [_user()], new_step=2, settings=settings
        )
        mock_email.assert_not_called()
        mock_notif.assert_not_called()


# ===========================================================================
# Tests: notify_approval_completed
# ===========================================================================

class TestNotifyApprovalCompleted:

    def _run(self, approval, settings=None):
        from workflow.notifications import notify_approval_completed
        with _patch_approval_get(approval), \
             (_patch_with_settings(settings) if settings else _patch_no_settings()), \
             patch(_EMAIL_COMPLETED, return_value=True) as mock_email, \
             patch(_NOTIF_SEND) as mock_notif:
            notify_approval_completed(approval.pk)
            return mock_email, mock_notif

    def test_notifies_requester(self):
        requester = _user(pk=3, username='req')
        approval = _approval(requested_by=requester, status='Approved')

        mock_email, mock_notif = self._run(approval)

        mock_email.assert_called_once()
        assert mock_email.call_args[0][0] == requester
        assert mock_notif.call_args[1]['priority'] == 'NORMAL'

    def test_respects_notify_requester_false(self):
        settings = _settings_obj(notify_requester=False)
        mock_email, mock_notif = self._run(_approval(status='Approved'), settings)
        mock_email.assert_not_called()
        mock_notif.assert_not_called()

    def test_silent_when_no_requester(self):
        approval = _approval(status='Approved')
        approval.requested_by = None

        mock_email, mock_notif = self._run(approval)
        mock_email.assert_not_called()
        mock_notif.assert_not_called()

    def test_in_app_notification_has_approval_title(self):
        requester = _user(pk=4)
        approval = _approval(title='Invoice #99', requested_by=requester, status='Approved')

        _, mock_notif = self._run(approval)

        assert 'Invoice #99' in mock_notif.call_args[1]['title']


# ===========================================================================
# Tests: notify_approval_rejected
# ===========================================================================

class TestNotifyApprovalRejected:

    def _run(self, approval, rej_step, settings=None):
        from workflow.notifications import notify_approval_rejected

        qs = MagicMock()
        qs.select_related.return_value.first.return_value = rej_step
        approval.steps.filter.return_value = qs

        with _patch_approval_get(approval), \
             (_patch_with_settings(settings) if settings else _patch_no_settings()), \
             patch(_EMAIL_REJECTED, return_value=True) as mock_email, \
             patch(_NOTIF_SEND) as mock_notif:
            notify_approval_rejected(approval.pk, rejecting_step_number=1)
            return mock_email, mock_notif

    def test_notifies_requester_with_rejection_details(self):
        requester = _user(pk=5)
        rejector_user = _user(pk=6, username='rejector', first_name='Jane')
        rej_step = _step(step_number=1, approver=rejector_user, status='Rejected',
                         comment='No budget.')
        approval = _approval(requested_by=requester, status='Rejected')

        mock_email, mock_notif = self._run(approval, rej_step)

        mock_email.assert_called_once()
        call_args = mock_email.call_args[0]
        assert call_args[0] == requester        # user
        assert call_args[2] == 1               # step_number

        notif_kwargs = mock_notif.call_args[1]
        assert notif_kwargs['priority'] == 'HIGH'

    def test_silent_when_notify_requester_off(self):
        settings = _settings_obj(notify_requester=False)
        rej_step = _step()
        mock_email, mock_notif = self._run(_approval(status='Rejected'), rej_step, settings)
        mock_email.assert_not_called()
        mock_notif.assert_not_called()


# ===========================================================================
# Tests: notify_approval_cancelled
# ===========================================================================

class TestNotifyApprovalCancelled:

    def _run(self, approval, settings=None):
        from workflow.notifications import notify_approval_cancelled
        with _patch_approval_get(approval), \
             (_patch_with_settings(settings) if settings else _patch_no_settings()), \
             patch(_NOTIF_SEND) as mock_notif:
            notify_approval_cancelled(approval.pk)
            return mock_notif

    def test_sends_in_app_only_with_low_priority(self):
        requester = _user(pk=7)
        approval = _approval(requested_by=requester, status='Cancelled')

        mock_notif = self._run(approval)

        mock_notif.assert_called_once()
        assert mock_notif.call_args[1]['priority'] == 'LOW'
        assert 'cancelled' in mock_notif.call_args[1]['title'].lower()

    def test_silent_when_notify_requester_off(self):
        settings = _settings_obj(notify_requester=False)
        mock_notif = self._run(_approval(status='Cancelled'), settings)
        mock_notif.assert_not_called()


# ===========================================================================
# Tests: notify_approval_sla_breach
# ===========================================================================

class TestNotifyApprovalSLABreach:

    def _run(self, step, approver_users, settings=None):
        from workflow.notifications import notify_approval_sla_breach

        group = _group()
        group.effective_user_ids.return_value = {u.pk for u in approver_users}
        step.approver_group = group
        step.approval.steps = MagicMock()

        with _patch_step_get(step), \
             (_patch_with_settings(settings) if settings else _patch_no_settings()), \
             _patch_approver_users(approver_users), \
             patch(_EMAIL_SLA, return_value=True) as mock_email, \
             patch(_NOTIF_SEND) as mock_notif:
            notify_approval_sla_breach(step.pk)
            return mock_email, mock_notif

    def test_notifies_approvers_with_urgent_priority(self):
        approver = _user(pk=9)
        approval = _approval()
        # due_date is in the past — mock timezone inside the function's local scope
        due = MagicMock()
        step = _step(step_number=1, due_date=due, approval=approval)

        fake_delta = MagicMock()
        fake_delta.total_seconds.return_value = 6 * 3600
        fake_now = MagicMock()
        fake_now.__sub__ = MagicMock(return_value=fake_delta)

        with patch('django.utils.timezone.now', return_value=fake_now):
            mock_email, mock_notif = self._run(step, [approver])

        mock_email.assert_called_once()
        mock_notif.assert_called_once()
        assert mock_notif.call_args[1]['priority'] == 'URGENT'

    def test_delay_hours_zero_when_no_due_date(self):
        step = _step(due_date=None)

        mock_email, mock_notif = self._run(step, [_user()])

        # delay_hours passed to email should be 0
        assert mock_email.call_args[0][2] == 0

    def test_silent_when_notifications_disabled(self):
        settings = _settings_obj(send_notifications=False)
        step = _step()
        mock_email, mock_notif = self._run(step, [_user()], settings)
        mock_email.assert_not_called()
        mock_notif.assert_not_called()

    def test_does_nothing_for_nonexistent_step(self):
        from workflow.notifications import notify_approval_sla_breach

        with patch('workflow.notifications.ApprovalStep') as mock_step_class:
            mock_step_class.DoesNotExist = Exception
            mock_step_class.objects.select_related.return_value.get.side_effect = \
                mock_step_class.DoesNotExist
            with patch(_NOTIF_SEND) as mock_notif, patch(_EMAIL_SLA) as mock_email:
                notify_approval_sla_breach(99999)
                mock_email.assert_not_called()
                mock_notif.assert_not_called()


# ===========================================================================
# Tests: email convenience functions (unit, no DB)
# ===========================================================================

class TestEmailConvenienceFunctions:
    """Smoke-test each convenience function delegates to send_localized_email."""

    def _user(self):
        u = MagicMock()
        u.first_name = 'Test'
        u.username = 'testuser'
        u.email = 'test@example.com'
        return u

    def _approval(self):
        a = MagicMock()
        a.title = 'Invoice #1'
        a.amount = None
        a.requested_by = self._user()
        a.requested_by.get_full_name.return_value = 'Test User'
        return a

    @patch('core.localized_emails.send_localized_email', return_value=True)
    def test_send_approval_submitted_email_delegates(self, mock_send):
        from core.localized_emails import send_approval_submitted_email
        send_approval_submitted_email(self._user(), self._approval(), 'Vendor Invoice', 'http://x/')
        mock_send.assert_called_once()
        assert mock_send.call_args[0][0] == 'approval_submitted'

    @patch('core.localized_emails.send_localized_email', return_value=True)
    def test_send_approval_completed_email_delegates(self, mock_send):
        from core.localized_emails import send_approval_completed_email
        send_approval_completed_email(self._user(), self._approval(), 'http://x/')
        assert mock_send.call_args[0][0] == 'approval_completed'

    @patch('core.localized_emails.send_localized_email', return_value=True)
    def test_send_approval_rejected_email_delegates(self, mock_send):
        from core.localized_emails import send_approval_rejected_email
        send_approval_rejected_email(
            self._user(), self._approval(), 2, 'Jane Doe', 'No budget.', 'http://x/'
        )
        assert mock_send.call_args[0][0] == 'approval_rejected'

    @patch('core.localized_emails.send_localized_email', return_value=True)
    def test_send_approval_step_advanced_email_delegates(self, mock_send):
        from core.localized_emails import send_approval_step_advanced_email
        send_approval_step_advanced_email(
            self._user(), self._approval(), 'Purchase Order', 'http://x/'
        )
        assert mock_send.call_args[0][0] == 'approval_step_advanced'

    @patch('core.localized_emails.send_localized_email', return_value=True)
    def test_send_approval_sla_breach_email_delegates(self, mock_send):
        from core.localized_emails import send_approval_sla_breach_email
        send_approval_sla_breach_email(self._user(), self._approval(), 8, 'http://x/')
        assert mock_send.call_args[0][0] == 'approval_sla_breach'


# ===========================================================================
# Tests: tasks.enqueue_approval_notification
# ===========================================================================

class TestEnqueueApprovalNotification:
    """Verifies the task wrapper schedules via transaction.on_commit."""

    def test_registers_on_commit_callback(self):
        from workflow.tasks import enqueue_approval_notification

        with patch('django.db.transaction.on_commit') as mock_on_commit:
            enqueue_approval_notification('submitted', 42)
            mock_on_commit.assert_called_once()

    def test_callback_calls_send_approval_notification(self):
        import workflow.tasks as tasks_mod
        from workflow.tasks import enqueue_approval_notification

        captured = []

        def fake_on_commit(fn):
            captured.append(fn)

        with patch('django.db.transaction.on_commit', side_effect=fake_on_commit), \
             patch('workflow.tasks._HAS_CELERY', False), \
             patch('workflow.tasks.send_approval_notification') as mock_task:
            enqueue_approval_notification('completed', 10)

            assert len(captured) == 1
            captured[0]()  # execute the on_commit callback
            mock_task.assert_called_once_with('completed', 10)
