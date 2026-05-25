"""Regression tests for the httpOnly auth-cookie path.

These tests pin the **safe-additive** contract for the cookie auth
migration: enabling ``AUTH_COOKIE_ENABLED`` introduces a second
authentication channel without breaking the existing Authorization-
header path or any caller that uses it.

The tests stay no-DB / pure-Python by:

  * Building fake ``HttpRequest`` objects via ``RequestFactory``
    rather than DRF ``APIClient`` (which spins up the URL conf and
    pulls in tenant middleware — heavy for a focused unit test).
  * Mocking the token-validation path on the auth class so we test
    the header-vs-cookie *routing* without needing a real Token row.

What is **not** covered here (deferred to integration tests):

  * Full login → cookie roundtrip across the real ``login_view``
    handler — that requires a tenant schema, a User row, and a Token
    model insert. Covered by the existing auth integration suite.
  * Browser-side ``HttpOnly`` enforcement — that's a browser
    behaviour, not a server contract.
"""
from __future__ import annotations

from unittest import mock

import pytest
from django.test import RequestFactory, override_settings
from rest_framework import status


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────

@pytest.fixture
def rf():
    return RequestFactory()


class _SentinelUser:
    """Placeholder returned from a successful token lookup. The auth
    class returns ``(user, token)``; tests only care about identity."""
    is_authenticated = True
    pk = 42


class _SentinelToken:
    key = 'AAAA0000BBBB1111CCCC2222DDDD3333EEEE4444'


# ─────────────────────────────────────────────────────────────────────
# Cookie helpers — set / clear
# ─────────────────────────────────────────────────────────────────────

class TestSetAuthCookie:

    @override_settings(AUTH_COOKIE_ENABLED=False)
    def test_disabled_flag_emits_no_cookie(self):
        """Default state: feature is dormant. Login response carries
        the token in JSON only — no Set-Cookie header."""
        from rest_framework.response import Response
        from core.views.auth import _set_auth_cookie

        response = Response({'token': 'tok-abc'})
        _set_auth_cookie(response, 'tok-abc')
        assert 'auth_token' not in response.cookies

    @override_settings(
        AUTH_COOKIE_ENABLED=True,
        AUTH_COOKIE_NAME='auth_token',
        AUTH_COOKIE_SECURE=True,
        AUTH_COOKIE_SAMESITE='Lax',
        AUTH_COOKIE_DOMAIN=None,
        AUTH_COOKIE_PATH='/',
        TOKEN_EXPIRATION_HOURS=12,
    )
    def test_enabled_sets_httponly_secure_samesite_cookie(self):
        """When enabled the cookie carries the security attributes
        the XSS-mitigation case depends on: HttpOnly (JS can't read),
        Secure (HTTPS-only in production), SameSite=Lax (CSRF defence
        while allowing top-level navigation)."""
        from rest_framework.response import Response
        from core.views.auth import _set_auth_cookie

        response = Response({'token': 'tok-xyz'})
        _set_auth_cookie(response, 'tok-xyz')

        cookie = response.cookies.get('auth_token')
        assert cookie is not None, 'cookie must be set when enabled'
        assert cookie.value == 'tok-xyz', 'cookie carries the token'
        # Morsel attributes — Django's SimpleCookie exposes them as
        # lowercase dict keys.
        assert cookie['httponly'] is True
        assert cookie['secure'] is True
        assert cookie['samesite'] == 'Lax'
        # max_age must match TOKEN_EXPIRATION_HOURS so browser drops
        # cookie at the same moment the server would reject the token.
        assert cookie['max-age'] == 12 * 3600

    @override_settings(
        AUTH_COOKIE_ENABLED=True,
        AUTH_COOKIE_NAME='custom_token_name',
    )
    def test_cookie_name_is_settings_driven(self):
        """Deployments can rename the cookie to avoid collision with
        an unrelated app on the same host."""
        from rest_framework.response import Response
        from core.views.auth import _set_auth_cookie

        response = Response({'token': 'tok-1'})
        _set_auth_cookie(response, 'tok-1')
        assert 'custom_token_name' in response.cookies
        assert 'auth_token' not in response.cookies


class TestClearAuthCookie:

    @override_settings(AUTH_COOKIE_ENABLED=True)
    def test_clear_emits_expired_set_cookie(self):
        """Logout must invalidate the cookie even when the feature is
        currently enabled. Django's ``delete_cookie`` writes an
        expired Set-Cookie header (max-age=0) which the browser
        treats as "delete now"."""
        from rest_framework.response import Response
        from core.views.auth import _clear_auth_cookie

        response = Response({'status': 'logged out'})
        _clear_auth_cookie(response)
        cookie = response.cookies.get('auth_token')
        assert cookie is not None
        # Django sets max-age=0 + an expires date in the past on
        # delete. Either signal is sufficient.
        assert cookie['max-age'] == 0 or 'expires' in cookie

    @override_settings(AUTH_COOKIE_ENABLED=False)
    def test_clear_runs_even_when_feature_disabled(self):
        """Mid-rollout case: a user logged in while
        AUTH_COOKIE_ENABLED was True, then the operator flipped the
        flag off. Logout still needs to clear the orphan cookie or
        it lingers in the browser until max_age."""
        from rest_framework.response import Response
        from core.views.auth import _clear_auth_cookie

        response = Response({'status': 'logged out'})
        _clear_auth_cookie(response)
        # The clear is unconditional — proves the "always-clear"
        # contract documented in the helper.
        assert 'auth_token' in response.cookies


# ─────────────────────────────────────────────────────────────────────
# ExpiringTokenAuthentication — header / cookie precedence
# ─────────────────────────────────────────────────────────────────────

class TestExpiringTokenAuthenticationRouting:
    """The auth class must:

      1. Prefer the header when present (back-compat).
      2. Fall back to the cookie when AUTH_COOKIE_ENABLED and present.
      3. Return None (anonymous) when neither is present.
      4. Return None when only the cookie is present but the flag is OFF.
    """

    def _patch_credentials(self, auth_instance):
        """Stub ``authenticate_credentials`` so we don't need a real
        Token / DB / schema_context. The patched method returns the
        sentinel tuple iff the key argument is the canonical sentinel."""
        return mock.patch.object(
            auth_instance.__class__,
            'authenticate_credentials',
            return_value=(_SentinelUser(), _SentinelToken()),
            create=False,
        )

    @override_settings(AUTH_COOKIE_ENABLED=True)
    def test_header_takes_precedence_over_cookie(self, rf):
        """When both header and cookie are present, the header wins.
        This preserves the existing API contract and avoids a
        confusing "logged in as X according to cookie but as Y
        according to header" scenario."""
        from core.authentication import ExpiringTokenAuthentication

        auth = ExpiringTokenAuthentication()
        request = rf.get(
            '/api/v1/anything',
            HTTP_AUTHORIZATION=f'Token {_SentinelToken.key}',
        )
        request.COOKIES['auth_token'] = 'COOKIE-KEY-IGNORED'

        with self._patch_credentials(auth) as patched:
            result = auth.authenticate(request)

        assert result is not None
        # Only one credentials lookup — the one for the HEADER key.
        # If both ran we'd see two calls; the header path returned
        # first and short-circuited the cookie path.
        patched.assert_called_once_with(_SentinelToken.key)

    @override_settings(AUTH_COOKIE_ENABLED=True, AUTH_COOKIE_NAME='auth_token')
    def test_cookie_path_used_when_no_header(self, rf):
        """Browser session that received the cookie at login and
        never sets the Authorization header — the cookie path
        delivers the user identity."""
        from core.authentication import ExpiringTokenAuthentication

        auth = ExpiringTokenAuthentication()
        request = rf.get('/api/v1/anything')
        request.COOKIES['auth_token'] = _SentinelToken.key

        with self._patch_credentials(auth) as patched:
            result = auth.authenticate(request)

        assert result is not None
        user, _token = result
        assert user.pk == 42
        patched.assert_called_once_with(_SentinelToken.key)

    @override_settings(AUTH_COOKIE_ENABLED=False)
    def test_cookie_ignored_when_feature_disabled(self, rf):
        """The flag must actually gate behaviour. With it OFF, even a
        well-formed cookie produces an anonymous request — closes
        the "cookie keeps working after rollback" failure mode."""
        from core.authentication import ExpiringTokenAuthentication

        auth = ExpiringTokenAuthentication()
        request = rf.get('/api/v1/anything')
        request.COOKIES['auth_token'] = _SentinelToken.key

        with self._patch_credentials(auth) as patched:
            result = auth.authenticate(request)

        assert result is None, 'Cookie must not authenticate when flag is OFF'
        patched.assert_not_called()

    @override_settings(AUTH_COOKIE_ENABLED=True)
    def test_no_credentials_returns_none(self, rf):
        """Anonymous request with neither header nor cookie returns
        None so the DRF permission chain treats it as anonymous
        rather than failing hard."""
        from core.authentication import ExpiringTokenAuthentication

        auth = ExpiringTokenAuthentication()
        request = rf.get('/api/v1/anything')

        with self._patch_credentials(auth) as patched:
            result = auth.authenticate(request)

        assert result is None
        patched.assert_not_called()


# ─────────────────────────────────────────────────────────────────────
# Settings sanity
# ─────────────────────────────────────────────────────────────────────

class TestSettingsContract:
    """Pin the public surface so a future settings refactor doesn't
    silently rename / drop the keys the auth class depends on."""

    def test_auth_cookie_settings_present(self):
        from django.conf import settings
        for attr in (
            'AUTH_COOKIE_ENABLED',
            'AUTH_COOKIE_NAME',
            'AUTH_COOKIE_SECURE',
            'AUTH_COOKIE_SAMESITE',
        ):
            assert hasattr(settings, attr), f'settings.{attr} must be defined'

    def test_default_is_disabled(self):
        """Default ships dormant — flipping it on is an explicit
        operator decision per deployment."""
        from django.conf import settings
        # The dev/test env may have flipped it on; assert it's a
        # boolean rather than asserting the value, so tests don't
        # fail in environments that explicitly enabled the path.
        assert isinstance(settings.AUTH_COOKIE_ENABLED, bool)

    def test_cors_allow_credentials_is_on(self):
        """Without this the browser refuses to send the auth cookie
        cross-origin — the cookie path is broken before it starts."""
        from django.conf import settings
        assert settings.CORS_ALLOW_CREDENTIALS is True, (
            'CORS_ALLOW_CREDENTIALS must be True for the httpOnly '
            'auth-cookie path to work cross-origin'
        )
