"""
Multi-factor authentication service (TOTP).

Orchestrates enrollment, verification, recovery-code generation, and
lockout logic. All the business rules live here; the API views are
thin wrappers that handle (de)serialization and HTTP status codes.

Industry-standard TOTP parameters:
  * 30-second window (RFC 6238 default)
  * 6-digit codes
  * SHA-1 HMAC (universally supported by authenticator apps)

Why SHA-1? Google Authenticator, Microsoft Authenticator, FreeOTP and
the Apple/1Password variants all support SHA-1 out of the box. SHA-256
is supported by some apps but rejected by others — sticking with SHA-1
maximises compatibility without meaningfully weakening the protocol.
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Optional

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.utils import timezone


# Recovery code format: 8 alphanumeric chars (e.g. "5F7K-9HJR"), uppercase,
# unambiguous alphabet (no 0/O/I/1). 40-bit entropy per code is plenty
# for a single-use backup.
_RECOVERY_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
_RECOVERY_CODE_LEN = 8


@dataclass(frozen=True)
class EnrollmentResult:
    """Return type for :func:`start_enrollment`."""
    secret: str
    provisioning_uri: str
    issuer: str
    label: str


@dataclass(frozen=True)
class VerificationResult:
    """Return type for :func:`verify`."""
    success: bool
    used_recovery_code: bool
    remaining_recovery_codes: int
    error: Optional[str] = None


class MFAError(Exception):
    """Raised for any MFA-flow error that a view should translate to 400."""


class MFAService:
    """TOTP enrollment + verification + recovery-code handling."""

    # ── Enrollment ──────────────────────────────────────────────────────

    @classmethod
    def start_enrollment(cls, user) -> EnrollmentResult:
        """Generate or rotate a TOTP secret for ``user``.

        Called from ``POST /auth/mfa/enroll/``. If the user has never
        enrolled, creates the UserMFA row. If they have a pending but
        not-yet-verified enrollment, rotates the secret (previous QR
        becomes invalid). If they are fully enrolled, refuses — the
        disable flow must be used first.
        """
        import pyotp
        from core.models import UserMFA

        mfa, _ = UserMFA.objects.get_or_create(user=user)

        if mfa.is_enrolled:
            raise MFAError(
                'MFA is already enrolled for this user. Disable it first '
                'via the /auth/mfa/disable/ endpoint (requires current code).'
            )

        mfa.secret = pyotp.random_base32()
        mfa.failed_attempts = 0
        mfa.locked_until = None
        mfa.save(update_fields=['secret', 'failed_attempts', 'locked_until'])

        issuer = cls._issuer()
        label = user.email or user.username
        uri = pyotp.totp.TOTP(
            mfa.secret,
            digits=UserMFA.TOTP_DIGITS,
            interval=UserMFA.TOTP_INTERVAL_SECONDS,
        ).provisioning_uri(name=label, issuer_name=issuer)

        return EnrollmentResult(
            secret=mfa.secret,
            provisioning_uri=uri,
            issuer=issuer,
            label=label,
        )

    @classmethod
    def confirm_enrollment(cls, user, code: str) -> list[str]:
        """Verify the first TOTP code and finalise enrollment.

        Returns the plaintext recovery codes — THIS IS THE ONLY TIME
        THE USER SEES THEM. They're stored hashed. Losing them means
        account recovery requires an admin reset.
        """
        from core.models import UserMFA
        try:
            mfa = UserMFA.objects.get(user=user)
        except UserMFA.DoesNotExist:
            raise MFAError('No enrollment in progress. Call /auth/mfa/enroll/ first.')

        if mfa.is_enrolled:
            raise MFAError('MFA is already enrolled.')

        if not mfa.secret:
            raise MFAError('No secret on file — re-run /auth/mfa/enroll/.')

        if not cls._verify_totp(mfa.secret, code):
            mfa.failed_attempts += 1
            mfa.save(update_fields=['failed_attempts'])
            raise MFAError('The verification code is incorrect or expired.')

        plaintext_codes = [cls._generate_recovery_code() for _ in range(
            UserMFA.RECOVERY_CODE_COUNT,
        )]

        with transaction.atomic():
            mfa.is_enrolled = True
            mfa.enrolled_at = timezone.now()
            mfa.last_verified_at = timezone.now()
            mfa.failed_attempts = 0
            mfa.locked_until = None
            mfa.recovery_codes = [
                {'hash': make_password(code_), 'used_at': None}
                for code_ in plaintext_codes
            ]
            mfa.save()

        return plaintext_codes

    # ── Verification (ongoing) ──────────────────────────────────────────

    @classmethod
    def verify(cls, user, code: str) -> VerificationResult:
        """Verify a TOTP code OR a recovery code for an enrolled user.

        Called during login (after password auth) and before any
        sensitive action (journal post, PV approval, warrant release,
        year-end close).

        Rate-limiting: after ``MAX_FAILED_ATTEMPTS`` wrong codes the row
        is locked for ``LOCKOUT_DURATION_MINUTES``. Correct verification
        resets the counter.
        """
        from core.models import UserMFA
        try:
            mfa = UserMFA.objects.get(user=user)
        except UserMFA.DoesNotExist:
            return VerificationResult(
                success=False, used_recovery_code=False,
                remaining_recovery_codes=0,
                error='MFA is not enrolled for this user.',
            )

        if not mfa.is_enrolled:
            return VerificationResult(
                success=False, used_recovery_code=False,
                remaining_recovery_codes=0,
                error='MFA enrollment has not been confirmed.',
            )

        if mfa.is_locked:
            return VerificationResult(
                success=False, used_recovery_code=False,
                remaining_recovery_codes=mfa.unused_recovery_code_count,
                error=(
                    f'Too many failed attempts. Locked until '
                    f'{mfa.locked_until.isoformat()}.'
                ),
            )

        normalized = (code or '').strip().replace(' ', '').replace('-', '')

        # Try TOTP first (6 digits). If the code isn't 6 digits, skip
        # straight to recovery-code path.
        if len(normalized) == UserMFA.TOTP_DIGITS and normalized.isdigit():
            if cls._verify_totp(mfa.secret, normalized):
                cls._mark_success(mfa)
                return VerificationResult(
                    success=True, used_recovery_code=False,
                    remaining_recovery_codes=mfa.unused_recovery_code_count,
                )

        # Recovery code path: check against each unused hash.
        for i, entry in enumerate(mfa.recovery_codes or []):
            if entry.get('used_at'):
                continue
            if check_password(normalized, entry['hash']):
                # Consume this recovery code.
                with transaction.atomic():
                    entry['used_at'] = timezone.now().isoformat()
                    mfa.recovery_codes[i] = entry
                    cls._mark_success(mfa, save_fields=None)
                    mfa.save()
                return VerificationResult(
                    success=True, used_recovery_code=True,
                    remaining_recovery_codes=mfa.unused_recovery_code_count,
                )

        # No match — bump failure counter, lock if exceeded.
        cls._mark_failure(mfa)
        return VerificationResult(
            success=False, used_recovery_code=False,
            remaining_recovery_codes=mfa.unused_recovery_code_count,
            error='The verification code is incorrect or expired.',
        )

    # ── Disable / reset ─────────────────────────────────────────────────

    @classmethod
    def disable(cls, user, current_code: str) -> None:
        """Disable MFA for a user. Requires a valid current code — an
        admin reset path is provided separately for lost-device cases.
        """
        from core.models import UserMFA
        try:
            mfa = UserMFA.objects.get(user=user, is_enrolled=True)
        except UserMFA.DoesNotExist:
            raise MFAError('MFA is not enrolled for this user.')

        result = cls.verify(user, current_code)
        if not result.success:
            raise MFAError(result.error or 'Invalid verification code.')

        mfa.is_enrolled = False
        mfa.secret = ''
        mfa.recovery_codes = []
        mfa.failed_attempts = 0
        mfa.locked_until = None
        mfa.save()

    @classmethod
    def admin_reset(cls, user, admin_user) -> None:
        """Admin-initiated MFA wipe (e.g. lost device). Should be gated
        by the caller to an admin/superuser; this helper does NOT
        re-check permissions — it's a pure data mutation to be invoked
        from a view that has already authorised the reset.
        """
        from core.models import UserMFA
        try:
            mfa = UserMFA.objects.get(user=user)
        except UserMFA.DoesNotExist:
            return
        mfa.is_enrolled = False
        mfa.secret = ''
        mfa.recovery_codes = []
        mfa.failed_attempts = 0
        mfa.locked_until = None
        mfa.save()

    # ── Helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _verify_totp(secret: str, code: str) -> bool:
        """Verify a 6-digit TOTP code against ``secret``.

        ``valid_window=1`` allows codes from the adjacent 30-s window
        on each side — handles small clock-drift between the user's
        phone and the server. This is the pyotp default.
        """
        import pyotp
        if not secret or not code:
            return False
        totp = pyotp.TOTP(secret)
        return totp.verify(code, valid_window=1)

    @staticmethod
    def _generate_recovery_code() -> str:
        """Generate a formatted recovery code ``XXXX-XXXX``."""
        raw = ''.join(
            secrets.choice(_RECOVERY_ALPHABET) for _ in range(_RECOVERY_CODE_LEN)
        )
        return f'{raw[:4]}-{raw[4:]}'

    @classmethod
    def _mark_success(cls, mfa, save_fields=('last_verified_at', 'failed_attempts', 'locked_until')):
        mfa.last_verified_at = timezone.now()
        mfa.failed_attempts = 0
        mfa.locked_until = None
        if save_fields is not None:
            mfa.save(update_fields=list(save_fields))

    @classmethod
    def _mark_failure(cls, mfa):
        from core.models import UserMFA
        mfa.failed_attempts += 1
        if mfa.failed_attempts >= UserMFA.MAX_FAILED_ATTEMPTS:
            mfa.locked_until = timezone.now() + timezone.timedelta(
                minutes=UserMFA.LOCKOUT_DURATION_MINUTES,
            )
        mfa.save(update_fields=['failed_attempts', 'locked_until'])

    @staticmethod
    def _issuer() -> str:
        """The issuer string that appears in the authenticator app."""
        # Use a tenant-specific issuer where available so a user with
        # multiple state-government logins sees distinct entries in
        # their authenticator app.
        issuer = getattr(settings, 'MFA_ISSUER_NAME', None) or 'Quot PSE'
        return issuer
