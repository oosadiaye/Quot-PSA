import logging

from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login
from django_tenants.utils import schema_context
from rest_framework.authtoken.models import Token

from core.serializers import UserSerializer

logger = logging.getLogger('dtsg')
security_logger = logging.getLogger('security')


def _get_client_ip(request):
    """Extract client IP from request, respecting X-Forwarded-For."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', 'unknown')


class AuthService:
    @staticmethod
    def authenticate_user(identifier, password, request=None):
        """Resolve identifier (username or email), check lockout, authenticate.

        Returns a tuple of (user, token, error_response_data, http_status).
        On success error_response_data is None and http_status is None.
        On failure user and token are None.
        """
        from .models import LoginAttempt, UserSession  # noqa: F401 — imported at call-site
        # Note: models are accessed via the caller context; kept here for clarity.

        from rest_framework import status as drf_status

        client_ip = _get_client_ip(request) if request else 'unknown'
        user_agent = request.META.get('HTTP_USER_AGENT', '') if request else ''

        # Resolve email → username
        username = identifier
        if '@' in identifier:
            with schema_context('public'):
                try:
                    email_user = User.objects.get(email__iexact=identifier)
                    username = email_user.username
                except User.DoesNotExist:
                    pass

        # Check account lockout BEFORE authenticating
        from core.models import LoginAttempt
        with schema_context('public'):
            if LoginAttempt.is_locked_out(username):
                remaining = LoginAttempt.remaining_lockout_seconds(username)
                security_logger.warning(
                    'Locked-out login attempt user=%s ip=%s remaining=%ds',
                    username, client_ip, remaining,
                )
                return None, None, {
                    'error': 'Account temporarily locked due to too many failed attempts.',
                    'retry_after_seconds': remaining,
                }, drf_status.HTTP_429_TOO_MANY_REQUESTS

        user = authenticate(request, username=username, password=password)

        if user is None:
            with schema_context('public'):
                LoginAttempt.record_attempt(username, client_ip, user_agent, success=False)
            security_logger.warning(
                'Failed login attempt user=%s ip=%s', username, client_ip,
            )
            return None, None, {'error': 'Invalid credentials'}, drf_status.HTTP_401_UNAUTHORIZED

        if not user.is_active:
            with schema_context('public'):
                LoginAttempt.record_attempt(username, client_ip, user_agent, success=False)
            security_logger.warning(
                'Login attempt on disabled account user=%s ip=%s',
                username, client_ip,
            )
            return None, None, {'error': 'User account is disabled'}, drf_status.HTTP_403_FORBIDDEN

        # Successful login — record and clear lockout history
        with schema_context('public'):
            LoginAttempt.record_attempt(username, client_ip, user_agent, success=True)
            LoginAttempt.clear_failures(username)

        if request:
            login(request, user)

        # Create a fresh token for each login session
        from core.models import UserSession
        with schema_context('public'):
            Token.objects.filter(user=user).delete()
            token = Token.objects.create(user=user)

        # Track session
        with schema_context('public'):
            UserSession.create_for_token(user, token.key, client_ip, user_agent)

        return user, token, None, None

    @staticmethod
    def build_login_response(user, token):
        """Build the standard login response payload."""
        from core.views.auth import _get_user_tenants

        tenants = _get_user_tenants(user)

        security_logger.info(
            'Login successful user_id=%s tenants=%d',
            user.pk, len(tenants),
        )

        email_verified = True
        try:
            from core.models import EmailVerification
            with schema_context('public'):
                ev = EmailVerification.objects.filter(user=user).first()
                if ev and not ev.is_verified:
                    email_verified = False
        except Exception as exc:
            logger.warning(
                "auth_service: could not check email verification status for user %s: %s",
                getattr(user, 'pk', '?'), exc,
            )

        return {
            'user': UserSerializer(user).data,
            'token': token.key,
            'tenants': tenants,
            'email_verified': email_verified,
        }
