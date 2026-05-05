"""
MFA HTTP endpoints (thin wrappers over ``core.services.mfa.MFAService``).

Endpoints
---------

``POST /api/v1/auth/mfa/enroll/``
    Start (or rotate) an enrollment. Body: empty. Returns
    ``{secret, provisioning_uri, issuer, label}``. The frontend renders
    ``provisioning_uri`` as a QR code with ``qrcode.js``.

``POST /api/v1/auth/mfa/verify-enroll/``
    Confirm the first 6-digit code after scanning the QR. Body:
    ``{"code": "123456"}``. On success returns
    ``{recovery_codes: [...]}`` — THIS IS THE ONLY TIME THE USER SEES
    THE PLAINTEXT CODES.

``POST /api/v1/auth/mfa/verify/``
    Ongoing verification. Body: ``{"code": "123456"}`` or a recovery
    code like ``"5F7K-9HJR"``. Sets ``request.session['mfa_verified'] =
    timestamp`` so downstream views protected by ``RequiresMFA`` can
    proceed. Returns whether a recovery code was consumed and how many
    remain.

``POST /api/v1/auth/mfa/disable/``
    User-initiated disable. Body: ``{"code": "123456"}``. A current
    valid code is required — this prevents an attacker with session
    access from turning off MFA without the user's phone.

``GET /api/v1/auth/mfa/status/``
    Returns ``{is_enrolled, last_verified_at, remaining_recovery_codes,
    is_locked, locked_until}``.
"""
from __future__ import annotations

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status

from core.services.mfa import MFAService, MFAError


class MFAEnrollView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            result = MFAService.start_enrollment(request.user)
        except MFAError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({
            'secret': result.secret,
            'provisioning_uri': result.provisioning_uri,
            'issuer': result.issuer,
            'label': result.label,
        })


class MFAVerifyEnrollView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        code = (request.data.get('code') or '').strip()
        if not code:
            return Response(
                {'error': 'code is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            recovery_codes = MFAService.confirm_enrollment(request.user, code)
        except MFAError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        # Flag the session as MFA-verified so the user doesn't need to
        # re-verify for the rest of this session.
        _mark_session_mfa_verified(request)

        return Response({
            'enrolled': True,
            'recovery_codes': recovery_codes,
            'message': (
                'Store these recovery codes somewhere safe. Each one can '
                'be used exactly once to log in if you lose access to your '
                'authenticator app. They will not be shown again.'
            ),
        })


class MFAVerifyView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        code = (request.data.get('code') or '').strip()
        if not code:
            return Response(
                {'error': 'code is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = MFAService.verify(request.user, code)
        if not result.success:
            return Response(
                {
                    'success': False,
                    'error': result.error,
                    'remaining_recovery_codes': result.remaining_recovery_codes,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        _mark_session_mfa_verified(request)
        return Response({
            'success': True,
            'used_recovery_code': result.used_recovery_code,
            'remaining_recovery_codes': result.remaining_recovery_codes,
        })


class MFADisableView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        code = (request.data.get('code') or '').strip()
        if not code:
            return Response(
                {'error': 'code is required to disable MFA'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            MFAService.disable(request.user, code)
        except MFAError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        # Clear MFA freshness on BOTH the session (legacy path) and
        # every UserSession row owned by this user (token path) so
        # protected views stop accepting until the user re-verifies.
        if hasattr(request, 'session'):
            request.session.pop('mfa_verified_at', None)
        try:
            from core.models import UserSession
            UserSession.objects.filter(user=request.user).update(
                mfa_verified_at=None,
            )
        except Exception:  # noqa: BLE001
            pass
        return Response({'disabled': True})


class MFAStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from core.models import UserMFA
        try:
            mfa = UserMFA.objects.get(user=request.user)
        except UserMFA.DoesNotExist:
            return Response({
                'is_enrolled': False,
                'last_verified_at': None,
                'remaining_recovery_codes': 0,
                'is_locked': False,
                'locked_until': None,
            })
        return Response({
            'is_enrolled': mfa.is_enrolled,
            'last_verified_at': mfa.last_verified_at,
            'remaining_recovery_codes': mfa.unused_recovery_code_count,
            'is_locked': mfa.is_locked,
            'locked_until': mfa.locked_until,
            'session_verified': _session_mfa_is_fresh(request),
        })


# ── Session helpers ────────────────────────────────────────────────────

def _mark_session_mfa_verified(request) -> None:
    """Stamp the current session as MFA-verified.

    The timestamp is used by :class:`RequiresMFA` (see
    ``accounting.permissions``) to enforce a re-verification interval
    on sensitive actions — a stale MFA from 12 hours ago doesn't
    authorise a payment posting.
    """
    from django.utils import timezone
    now = timezone.now()
    # Session stamp (legacy / Django admin path) — kept for
    # backward compatibility.
    if hasattr(request, 'session'):
        request.session['mfa_verified_at'] = now.isoformat()
    # Token-attached stamp — the canonical path under stateless
    # token auth (production frontend). ``RequiresMFA`` reads
    # ``UserSession.mfa_verified_at`` first; falls back to the
    # session stamp only when token auth isn't in use.
    auth = getattr(request, 'auth', None)
    token_key = getattr(auth, 'key', None)
    if token_key:
        try:
            from core.models import UserSession
            UserSession.objects.filter(
                token_key=token_key, is_active=True,
            ).update(mfa_verified_at=now)
        except Exception:  # noqa: BLE001 — best-effort dual-write
            pass


def _session_mfa_is_fresh(request, max_age_minutes: int = 30) -> bool:
    """Whether the session's MFA verification is still fresh."""
    from datetime import datetime
    from django.utils import timezone

    if not hasattr(request, 'session'):
        return False
    stamp = request.session.get('mfa_verified_at')
    if not stamp:
        return False
    try:
        verified_at = datetime.fromisoformat(stamp)
    except (ValueError, TypeError):
        return False

    age = timezone.now() - verified_at
    return age.total_seconds() <= max_age_minutes * 60
