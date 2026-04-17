"""
Sprint-6 regression tests: MFA service + RequiresMFA permission.

All tests run without touching the database by mocking ``UserMFA``
lookups and patching ``pyotp``'s verify. This keeps MFA regression
coverage in the fast smoke tier alongside the permission tests.

Coverage:
  * TOTP code format normalisation (strips whitespace/dashes)
  * 6-digit path vs recovery-code path dispatch
  * Lockout after MAX_FAILED_ATTEMPTS
  * Recovery-code single-use enforcement
  * RequiresMFA: superuser bypass, bypass_mfa permission, enrolled
    requirement, session-freshness TTL
"""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.utils import timezone


# =============================================================================
# RequiresMFA permission class
# =============================================================================

class TestRequiresMFA:

    def setup_method(self):
        from accounting.permissions import RequiresMFA
        self.perm = RequiresMFA()

    def _request(self, user, session=None):
        req = MagicMock(user=user)
        req.session = session or {}
        return req

    def test_unauthenticated_denied(self):
        user = MagicMock(is_authenticated=False)
        assert self.perm.has_permission(self._request(user), view=None) is False

    def test_superuser_bypasses_mfa(self):
        user = MagicMock(is_authenticated=True, is_superuser=True)
        # Even with no MFA enrollment, superuser passes.
        with patch('accounting.permissions._user_is_mfa_enrolled', return_value=False):
            assert self.perm.has_permission(self._request(user), view=None) is True

    def test_bypass_mfa_permission_allowed(self):
        user = MagicMock(is_authenticated=True, is_superuser=False)
        user.has_perm.side_effect = lambda p: p == 'core.bypass_mfa'
        with patch('accounting.permissions._user_is_mfa_enrolled', return_value=False):
            assert self.perm.has_permission(self._request(user), view=None) is True

    def test_not_enrolled_denied(self):
        """Users who haven't enrolled MFA cannot access sensitive views."""
        user = MagicMock(is_authenticated=True, is_superuser=False)
        user.has_perm.return_value = False
        with patch('accounting.permissions._user_is_mfa_enrolled', return_value=False):
            assert self.perm.has_permission(self._request(user), view=None) is False

    def test_enrolled_but_session_not_verified_denied(self):
        """Enrolled users still need a fresh session verification."""
        user = MagicMock(is_authenticated=True, is_superuser=False)
        user.has_perm.return_value = False
        with patch('accounting.permissions._user_is_mfa_enrolled', return_value=True):
            # Empty session — no mfa_verified_at.
            assert self.perm.has_permission(self._request(user), view=None) is False

    def test_enrolled_with_fresh_verification_allowed(self):
        user = MagicMock(is_authenticated=True, is_superuser=False)
        user.has_perm.return_value = False
        fresh_stamp = timezone.now().isoformat()
        with patch('accounting.permissions._user_is_mfa_enrolled', return_value=True):
            assert self.perm.has_permission(
                self._request(user, session={'mfa_verified_at': fresh_stamp}),
                view=None,
            ) is True

    def test_stale_session_verification_denied(self):
        """Verification older than TTL (30 min default) is rejected."""
        user = MagicMock(is_authenticated=True, is_superuser=False)
        user.has_perm.return_value = False
        stale_stamp = (timezone.now() - timedelta(hours=2)).isoformat()
        with patch('accounting.permissions._user_is_mfa_enrolled', return_value=True):
            assert self.perm.has_permission(
                self._request(user, session={'mfa_verified_at': stale_stamp}),
                view=None,
            ) is False


# =============================================================================
# MFAService — TOTP + recovery-code logic (mocked UserMFA)
# =============================================================================

class TestMFAServiceVerify:
    """Verify() dispatch + lockout + recovery-code consumption."""

    def _mfa_stub(self, **overrides):
        """Build a MagicMock that looks like a UserMFA row."""
        defaults = dict(
            is_enrolled=True,
            secret='JBSWY3DPEHPK3PXP',  # well-known test secret
            recovery_codes=[],
            failed_attempts=0,
            locked_until=None,
            is_locked=False,
            unused_recovery_code_count=0,
        )
        defaults.update(overrides)
        stub = MagicMock(**defaults)
        # is_locked is a property on the real model — emulate.
        if 'is_locked' not in overrides:
            stub.is_locked = (
                defaults['locked_until'] is not None
                and defaults['locked_until'] > timezone.now()
            )
        return stub

    def test_totp_success_resets_failure_counter(self):
        from core.services.mfa import MFAService
        mfa = self._mfa_stub(failed_attempts=3)
        with patch('core.models.UserMFA.objects.get', return_value=mfa), \
             patch.object(MFAService, '_verify_totp', return_value=True):
            result = MFAService.verify(user=MagicMock(), code='123456')
        assert result.success is True
        assert result.used_recovery_code is False
        # mark_success should have been called, resetting failure counter.
        assert mfa.failed_attempts == 0
        assert mfa.locked_until is None

    def test_totp_wrong_code_increments_failures(self):
        from core.services.mfa import MFAService
        mfa = self._mfa_stub(failed_attempts=0)
        with patch('core.models.UserMFA.objects.get', return_value=mfa), \
             patch.object(MFAService, '_verify_totp', return_value=False):
            result = MFAService.verify(user=MagicMock(), code='000000')
        assert result.success is False
        assert mfa.failed_attempts == 1

    def test_lockout_after_max_failures(self):
        from core.services.mfa import MFAService
        from core.models import UserMFA
        # Just below threshold — one more failure triggers lockout.
        mfa = self._mfa_stub(
            failed_attempts=UserMFA.MAX_FAILED_ATTEMPTS - 1,
        )
        with patch('core.models.UserMFA.objects.get', return_value=mfa), \
             patch.object(MFAService, '_verify_totp', return_value=False):
            result = MFAService.verify(user=MagicMock(), code='000000')
        assert result.success is False
        assert mfa.locked_until is not None
        assert mfa.locked_until > timezone.now()

    def test_locked_row_rejects_even_valid_code(self):
        """An account in cooldown refuses even a correct code."""
        from core.services.mfa import MFAService
        mfa = self._mfa_stub(
            locked_until=timezone.now() + timedelta(minutes=10),
            is_locked=True,
        )
        with patch('core.models.UserMFA.objects.get', return_value=mfa), \
             patch.object(MFAService, '_verify_totp', return_value=True):
            result = MFAService.verify(user=MagicMock(), code='123456')
        assert result.success is False
        assert 'Locked' in (result.error or '')

    def test_recovery_code_format_normalized(self):
        """Whitespace and dashes are stripped before comparison.

        Patches ``core.services.mfa.transaction.atomic`` with a no-op
        context manager so this test stays in the smoke tier (no DB).
        The real atomic block on the recovery-code path is verified in
        the DB-tier integration tests.
        """
        from contextlib import contextmanager
        from core.services.mfa import MFAService
        from django.contrib.auth.hashers import make_password

        @contextmanager
        def _noop_atomic(*args, **kwargs):
            yield

        recovery_plaintext = '5F7K9HJR'
        mfa = self._mfa_stub(
            recovery_codes=[
                {'hash': make_password(recovery_plaintext), 'used_at': None},
            ],
            unused_recovery_code_count=1,
        )
        with patch('core.models.UserMFA.objects.get', return_value=mfa), \
             patch.object(MFAService, '_verify_totp', return_value=False), \
             patch('core.services.mfa.transaction.atomic', _noop_atomic):
            result = MFAService.verify(user=MagicMock(), code='5f7k-9hjr'.upper())
        assert result.success is True
        assert result.used_recovery_code is True
        # Used_at should now be populated on that code entry.
        assert mfa.recovery_codes[0]['used_at'] is not None

    def test_used_recovery_code_cannot_be_reused(self):
        """A recovery code with used_at set is rejected on subsequent use."""
        from core.services.mfa import MFAService
        from django.contrib.auth.hashers import make_password

        plaintext = 'ABCDEFGH'
        mfa = self._mfa_stub(
            recovery_codes=[
                {'hash': make_password(plaintext),
                 'used_at': timezone.now().isoformat()},
            ],
            unused_recovery_code_count=0,
        )
        with patch('core.models.UserMFA.objects.get', return_value=mfa), \
             patch.object(MFAService, '_verify_totp', return_value=False):
            result = MFAService.verify(user=MagicMock(), code=plaintext)
        assert result.success is False

    def test_not_enrolled_user_rejected(self):
        from core.services.mfa import MFAService
        mfa = self._mfa_stub(is_enrolled=False)
        with patch('core.models.UserMFA.objects.get', return_value=mfa):
            result = MFAService.verify(user=MagicMock(), code='123456')
        assert result.success is False
        assert 'not been confirmed' in (result.error or '') or 'not enrolled' in (result.error or '').lower()


# =============================================================================
# MFAService — recovery code generation format
# =============================================================================

def test_recovery_code_format():
    from core.services.mfa import MFAService
    code = MFAService._generate_recovery_code()
    assert len(code) == 9           # 8 chars + 1 dash
    assert code[4] == '-'
    # Only uppercase letters/digits from the unambiguous alphabet.
    for ch in code.replace('-', ''):
        assert ch in 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'


def test_recovery_codes_are_unique_over_many_generations():
    """Sanity check: 1000 codes from a 40-bit alphabet should not collide."""
    from core.services.mfa import MFAService
    codes = {MFAService._generate_recovery_code() for _ in range(1000)}
    assert len(codes) == 1000
