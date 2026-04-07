"""
Integrations Minimum Viable Test Suite
=========================================
Covers: signals module imports cleanly; _safe_dispatch error-handling;
webhook dispatcher interface.

These tests use SimpleTestCase (no DB) because integration signals are
stateless event dispatchers and should not require a tenant schema.

Run with:
    python manage.py test integrations --verbosity=2
"""
from unittest.mock import patch, MagicMock, call
from django.test import SimpleTestCase


class SignalModuleImportTests(SimpleTestCase):
    """The signals module should be importable without crashing."""

    def test_signals_module_imports(self):
        """Importing signals does not raise ImportError or NameError."""
        try:
            import integrations.signals  # noqa: F401
        except Exception as exc:
            self.fail(f"integrations.signals import raised {type(exc).__name__}: {exc}")


class SafeDispatchTests(SimpleTestCase):
    """_safe_dispatch swallows webhook errors and logs them."""

    def _get_safe_dispatch(self):
        from integrations.signals import _safe_dispatch
        return _safe_dispatch

    def test_safe_dispatch_calls_dispatch_event(self):
        with patch('integrations.signals.dispatch_event') as mock_dispatch:
            _safe_dispatch = self._get_safe_dispatch()
            instance = MagicMock()
            instance.pk = 42
            _safe_dispatch('test.event', 'module', lambda o: {'id': o.pk}, instance)
        mock_dispatch.assert_called_once_with(
            'test.event', module='module', payload={'id': 42},
        )

    def test_safe_dispatch_does_not_raise_on_webhook_error(self):
        """A failing dispatch_event must not propagate exceptions."""
        with patch('integrations.signals.dispatch_event', side_effect=Exception('network error')):
            _safe_dispatch = self._get_safe_dispatch()
            # Should not raise
            try:
                _safe_dispatch('fail.event', 'module', lambda o: {}, MagicMock())
            except Exception as exc:
                self.fail(f"_safe_dispatch propagated exception: {exc}")

    def test_safe_dispatch_logs_error_on_webhook_failure(self):
        """A dispatch error is logged at ERROR level, not silently swallowed."""
        with patch('integrations.signals.dispatch_event', side_effect=RuntimeError('boom')):
            with patch('integrations.signals.logger') as mock_logger:
                _safe_dispatch = self._get_safe_dispatch()
                _safe_dispatch('err.event', 'module', lambda o: {}, MagicMock())
        mock_logger.error.assert_called_once()
        args = mock_logger.error.call_args[0]
        self.assertIn('err.event', args[1])


class WebhookDispatcherImportTests(SimpleTestCase):
    """The webhook_dispatcher module should be importable."""

    def test_webhook_dispatcher_imports(self):
        try:
            from integrations import webhook_dispatcher  # noqa: F401
        except Exception as exc:
            self.fail(f"integrations.webhook_dispatcher import raised {type(exc).__name__}: {exc}")

    def test_dispatch_event_function_exists(self):
        from integrations.webhook_dispatcher import dispatch_event
        self.assertTrue(callable(dispatch_event))
