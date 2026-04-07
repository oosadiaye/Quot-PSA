import logging

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, authentication_classes, throttle_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.throttling import AnonRateThrottle
from rest_framework.authtoken.models import Token
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from django_tenants.utils import schema_context

from core.serializers import UserSerializer

logger = logging.getLogger('dtsg')
security_logger = logging.getLogger('security')


class LoginRateThrottle(AnonRateThrottle):
    scope = 'login'


class SignupRateThrottle(AnonRateThrottle):
    scope = 'signup'


def _get_user_tenants(user):
    """Return serializable list of tenants accessible by this user."""
    from tenants.models import UserTenantRole, Domain
    if user.is_superuser:
        # Superusers can access every tenant
        from tenants.models import Client
        tenants = Client.objects.prefetch_related('domains').all()
        return [
            {
                'id': t.id,
                'name': t.name,
                # SEC: schema_name removed from login API response to avoid leaking internal DB identifiers
                'domain': t.domains.filter(is_primary=True).values_list('domain', flat=True).first(),
                'role': 'admin',
            }
            for t in tenants
        ]
    roles = (
        UserTenantRole.objects
        .filter(user=user, is_active=True)
        .select_related('tenant')
        .prefetch_related('tenant__domains')
    )
    return [
        {
            'id': r.tenant.id,
            'name': r.tenant.name,
            # SEC: schema_name removed from login API response
            'domain': r.tenant.domains.filter(is_primary=True).values_list('domain', flat=True).first(),
            'role': r.role,
        }
        for r in roles
    ]


def _get_client_ip(request):
    """Extract client IP from request, respecting X-Forwarded-For."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', 'unknown')


@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
@throttle_classes([LoginRateThrottle])
def login_view(request):
    """Centralized login with account lockout protection.

    Accepts either a username or email address in the ``username`` field so
    that tenants can sign in with whichever identifier they prefer.  When the
    value looks like an email address (contains ``@``) we look up the
    corresponding Django user and fall back to the plain username path if no
    match is found (authenticate() will then return None gracefully).

    Returns the auth token **and** the list of tenants accessible by
    the user so the frontend can offer a tenant-selection step.
    """
    from core.models import LoginAttempt, UserSession

    identifier = (request.data.get('username') or '').strip()
    password = request.data.get('password')
    client_ip = _get_client_ip(request)
    user_agent = request.META.get('HTTP_USER_AGENT', '')

    if not identifier or not password:
        return Response(
            {'error': 'Username and password required'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Resolve email → username so authenticate() (which only accepts username)
    # works correctly regardless of which identifier the user supplied.
    username = identifier
    if '@' in identifier:
        with schema_context('public'):
            try:
                email_user = User.objects.get(email__iexact=identifier)
                username = email_user.username
            except User.DoesNotExist:
                pass  # keep identifier; authenticate() will return None → 401

    # Check account lockout BEFORE authenticating
    with schema_context('public'):
        if LoginAttempt.is_locked_out(username):
            remaining = LoginAttempt.remaining_lockout_seconds(username)
            security_logger.warning(
                'Locked-out login attempt user=%s ip=%s remaining=%ds',
                username, client_ip, remaining,
            )
            return Response(
                {
                    'error': 'Account temporarily locked due to too many failed attempts.',
                    'retry_after_seconds': remaining,
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

    # authenticate() uses PublicSchemaBackend → always hits public schema
    user = authenticate(request, username=username, password=password)

    if user is None:
        with schema_context('public'):
            LoginAttempt.record_attempt(username, client_ip, user_agent, success=False)
        security_logger.warning(
            'Failed login attempt user=%s ip=%s', username, client_ip,
        )
        return Response(
            {'error': 'Invalid credentials'},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    if not user.is_active:
        with schema_context('public'):
            LoginAttempt.record_attempt(username, client_ip, user_agent, success=False)
        security_logger.warning(
            'Login attempt on disabled account user=%s ip=%s',
            username, client_ip,
        )
        return Response(
            {'error': 'User account is disabled'},
            status=status.HTTP_403_FORBIDDEN,
        )

    # Successful login — record and clear lockout history
    with schema_context('public'):
        LoginAttempt.record_attempt(username, client_ip, user_agent, success=True)
        LoginAttempt.clear_failures(username)

    login(request, user)

    # Create a fresh token for each login session
    with schema_context('public'):
        Token.objects.filter(user=user).delete()
        token = Token.objects.create(user=user)

    # Track session
    with schema_context('public'):
        UserSession.create_for_token(user, token.key, client_ip, user_agent)

    tenants = _get_user_tenants(user)

    security_logger.info(
        'Login successful user_id=%s ip=%s tenants=%d',
        user.pk, client_ip, len(tenants),
    )

    # Check email verification status
    email_verified = True
    try:
        from core.models import EmailVerification
        with schema_context('public'):
            ev = EmailVerification.objects.filter(user=user).first()
            if ev and not ev.is_verified:
                email_verified = False
    except Exception as exc:
        logger.warning(
            "login: could not check email verification status for user %s: %s",
            getattr(user, 'pk', '?'), exc,
        )

    return Response({
        'user': UserSerializer(user).data,
        'token': token.key,
        'tenants': tenants,
        'email_verified': email_verified,
    })


@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
@throttle_classes([LoginRateThrottle])
def jwt_login_view(request):
    """JWT-based login with access and refresh tokens.

    Returns JWT access token (15 min) and refresh token (24h) along with
    user info and accessible tenants.
    """
    from rest_framework_simplejwt.tokens import RefreshToken
    from core.models import LoginAttempt, UserSession

    username = request.data.get('username')
    password = request.data.get('password')
    client_ip = _get_client_ip(request)
    user_agent = request.META.get('HTTP_USER_AGENT', '')

    if not username or not password:
        return Response(
            {'error': 'Username and password required'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    with schema_context('public'):
        if LoginAttempt.is_locked_out(username):
            remaining = LoginAttempt.remaining_lockout_seconds(username)
            security_logger.warning(
                'Locked-out login attempt user=%s ip=%s remaining=%ds',
                username, client_ip, remaining,
            )
            return Response(
                {
                    'error': 'Account temporarily locked due to too many failed attempts.',
                    'retry_after_seconds': remaining,
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

    user = authenticate(request, username=username, password=password)

    if user is None:
        with schema_context('public'):
            LoginAttempt.record_attempt(username, client_ip, user_agent, success=False)
        security_logger.warning(
            'Failed login attempt user=%s ip=%s', username, client_ip,
        )
        return Response(
            {'error': 'Invalid credentials'},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    if not user.is_active:
        with schema_context('public'):
            LoginAttempt.record_attempt(username, client_ip, user_agent, success=False)
        security_logger.warning(
            'Login attempt on disabled account user=%s ip=%s',
            username, client_ip,
        )
        return Response(
            {'error': 'User account is disabled'},
            status=status.HTTP_403_FORBIDDEN,
        )

    with schema_context('public'):
        LoginAttempt.record_attempt(username, client_ip, user_agent, success=True)
        LoginAttempt.clear_failures(username)

    login(request, user)

    with schema_context('public'):
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        refresh_token = str(refresh)

        UserSession.create_for_token(user, access_token[:40], client_ip, user_agent)

    tenants = _get_user_tenants(user)

    security_logger.info(
        'JWT Login successful user_id=%s ip=%s tenants=%d',
        user.pk, client_ip, len(tenants),
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
            "jwt_login: could not check email verification status for user %s: %s",
            getattr(user, 'pk', '?'), exc,
        )

    return Response({
        'user': UserSerializer(user).data,
        'access': access_token,
        'refresh': refresh_token,
        'tenants': tenants,
        'email_verified': email_verified,
    })


@api_view(['POST'])
def logout_view(request):
    """Logout — deletes the auth token and marks session inactive."""
    from core.models import UserSession
    if request.user.is_authenticated:
        with schema_context('public'):
            try:
                token = request.user.auth_token
                UserSession.objects.filter(token_key=token.key).update(is_active=False)
                token.delete()
            except Token.DoesNotExist:
                pass
        logout(request)
    return Response({'status': 'logged out successfully'})


# Keep old name as alias for backward compatibility (urls.py uses logout_view)
logout = logout_view


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def select_tenant(request):
    """Select a tenant to work with after login.

    Validates that the user has access to the requested tenant and
    returns the tenant domain for the frontend to store and send as
    ``X-Tenant-Domain`` in subsequent requests.
    """
    from tenants.models import UserTenantRole, Client

    tenant_id = request.data.get('tenant_id')
    if not tenant_id:
        return Response(
            {'error': 'tenant_id is required'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        tenant = Client.objects.prefetch_related('domains').get(pk=tenant_id)
    except Client.DoesNotExist:
        return Response(
            {'error': 'Tenant not found'},
            status=status.HTTP_404_NOT_FOUND,
        )

    # Superusers can access any tenant
    if not request.user.is_superuser:
        has_access = UserTenantRole.objects.filter(
            user=request.user, tenant=tenant, is_active=True
        ).exists()
        if not has_access:
            security_logger.warning(
                'Unauthorized tenant access attempt user_id=%s tenant_id=%s',
                request.user.pk, tenant_id,
            )
            return Response(
                {'error': 'You do not have access to this tenant'},
                status=status.HTTP_403_FORBIDDEN,
            )

    domain = tenant.domains.filter(is_primary=True).first()
    domain_value = domain.domain if domain else tenant.schema_name

    security_logger.info(
        'Tenant selected user_id=%s tenant=%s', request.user.pk, tenant.name,
    )

    # Include role and permissions for the selected tenant
    # SEC: schema_name removed from API response to avoid leaking internal DB identifiers
    response_data = {
        'tenant_id': tenant.id,
        'tenant_name': tenant.name,
        'domain': domain_value,
    }

    if request.user.is_superuser:
        response_data['role'] = 'admin'
        response_data['permissions'] = ['__all__']
    else:
        try:
            utr = UserTenantRole.objects.prefetch_related('groups').get(
                user=request.user, tenant=tenant, is_active=True
            )
            response_data['role'] = utr.role
            if utr.role == 'admin':
                response_data['permissions'] = ['__all__']
            else:
                response_data['permissions'] = sorted(
                    p.split('.')[-1] for p in utr.get_all_permissions()
                )
        except UserTenantRole.DoesNotExist:
            response_data['role'] = None
            response_data['permissions'] = []

    # Check if tenant setup wizard is needed (admin only, first login)
    role = response_data.get('role')
    if role == 'admin':
        try:
            from django_tenants.utils import schema_context as sc
            with sc(tenant.schema_name):
                from core.models import TenantSetupProfile
                profile = TenantSetupProfile.objects.first()
                response_data['setup_required'] = not profile or not profile.setup_completed
        except Exception:
            response_data['setup_required'] = False
    else:
        response_data['setup_required'] = False

    return Response(response_data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_tenants(request):
    """List all tenants the authenticated user can access."""
    return Response({'tenants': _get_user_tenants(request.user)})


# ── Password Reset (self-service) ──────────────────────────────────────

class PasswordResetRateThrottle(AnonRateThrottle):
    rate = '3/hour'


@api_view(['POST'])
@permission_classes([AllowAny])
@authentication_classes([])
@throttle_classes([PasswordResetRateThrottle])
def forgot_password(request):
    """Send a password reset email. Always returns 200 to prevent user enumeration."""
    email = request.data.get('email', '').strip().lower()
    if email:
        with schema_context('public'):
            try:
                user = User.objects.get(email__iexact=email, is_active=True)
                uid = urlsafe_base64_encode(force_bytes(user.pk))
                token = default_token_generator.make_token(user)
                frontend_url = settings.FRONTEND_URL
                reset_link = f"{frontend_url}/reset-password?uid={uid}&token={token}"
                send_mail(
                    subject='DTSG ERP — Password Reset',
                    message=f'Click the link to reset your password:\n\n{reset_link}\n\nThis link expires in 3 days. If you did not request this, ignore this email.',
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[user.email],
                    fail_silently=True,
                )
                logger.info('Password reset email sent to user_id=%s', user.pk)
            except User.DoesNotExist:
                pass  # Silent — prevent enumeration
    return Response({'status': 'If an account with that email exists, a reset link has been sent.'})


@api_view(['POST'])
@permission_classes([AllowAny])
@authentication_classes([])
def reset_password_confirm(request):
    """Validate token and set a new password."""
    uid = request.data.get('uid', '')
    token = request.data.get('token', '')
    new_password = request.data.get('new_password', '')
    new_password_confirm = request.data.get('new_password_confirm', '')

    if not all([uid, token, new_password, new_password_confirm]):
        return Response({'error': 'All fields are required.'}, status=status.HTTP_400_BAD_REQUEST)

    if new_password != new_password_confirm:
        return Response({'error': "Passwords don't match."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        user_id = urlsafe_base64_decode(uid).decode()
        with schema_context('public'):
            user = User.objects.get(pk=user_id)
    except (ValueError, TypeError, User.DoesNotExist):
        return Response({'error': 'Invalid reset link.'}, status=status.HTTP_400_BAD_REQUEST)

    if not default_token_generator.check_token(user, token):
        return Response({'error': 'Reset link has expired or is invalid.'}, status=status.HTTP_400_BAD_REQUEST)

    from django.contrib.auth.password_validation import validate_password
    from django.core.exceptions import ValidationError
    from core.models import PasswordHistory, UserSession
    try:
        validate_password(new_password, user)
    except ValidationError as e:
        return Response({'error': ' '.join(e.messages)}, status=status.HTTP_400_BAD_REQUEST)

    # Check password history
    with schema_context('public'):
        if PasswordHistory.is_password_reused(user, new_password):
            return Response(
                {'error': f'Cannot reuse any of your last {PasswordHistory.HISTORY_DEPTH} passwords.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        PasswordHistory.record_password(user)

    with schema_context('public'):
        user.set_password(new_password)
        user.save()
        Token.objects.filter(user=user).delete()  # Invalidate existing sessions
        UserSession.objects.filter(user=user).update(is_active=False)

    logger.info('Password reset completed for user_id=%s', user.pk)
    return Response({'status': 'Password has been reset successfully.'})


# ── Email Verification ─────────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([AllowAny])
@authentication_classes([])
def verify_email(request):
    """Verify a user's email address using the token sent after registration."""
    from core.models import EmailVerification

    token = request.data.get('token', '')
    if not token:
        return Response({'error': 'Token is required.'}, status=status.HTTP_400_BAD_REQUEST)

    with schema_context('public'):
        try:
            ev = EmailVerification.objects.select_related('user').get(token=token)
        except EmailVerification.DoesNotExist:
            return Response({'error': 'Invalid verification token.'}, status=status.HTTP_400_BAD_REQUEST)

        if ev.is_verified:
            return Response({'status': 'Email already verified.'})

        if ev.is_expired:
            return Response(
                {'error': 'Verification link has expired. Please request a new one.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ev.verify()
        security_logger.info('Email verified user_id=%s', ev.user.pk)

    return Response({'status': 'Email verified successfully.'})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def resend_verification_email(request):
    """Resend the email verification link for the authenticated user."""
    from core.models import EmailVerification

    with schema_context('public'):
        ev = EmailVerification.create_for_user(request.user)
        frontend_url = settings.FRONTEND_URL
        verify_link = f"{frontend_url}/verify-email?token={ev.token}"

        try:
            send_mail(
                subject='DTSG ERP — Verify Your Email',
                message=(
                    f"Hi {request.user.first_name or request.user.username},\n\n"
                    f"Please verify your email address by clicking this link:\n\n"
                    f"{verify_link}\n\n"
                    f"This link expires in 72 hours."
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[request.user.email],
                fail_silently=True,
            )
        except Exception:
            logger.warning('Failed to resend verification email to user_id=%s', request.user.pk)

    return Response({'status': 'Verification email sent.'})


# ── Session Management ─────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def active_sessions(request):
    """List all active sessions for the authenticated user."""
    from core.models import UserSession

    with schema_context('public'):
        sessions = UserSession.objects.filter(
            user=request.user, is_active=True,
        ).values('id', 'ip_address', 'user_agent', 'created_at', 'last_activity', 'token_key')

    current_token = getattr(request.auth, 'key', None)
    result = []
    for s in sessions:
        result.append({
            'id': s['id'],
            'ip_address': s['ip_address'],
            'user_agent': s['user_agent'],
            'created_at': s['created_at'],
            'last_activity': s['last_activity'],
            'is_current': s['token_key'] == current_token,
        })

    return Response({'sessions': result, 'count': len(result)})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def revoke_session(request):
    """Revoke a specific session by ID."""
    from core.models import UserSession

    session_id = request.data.get('session_id')
    if not session_id:
        return Response({'error': 'session_id is required.'}, status=status.HTTP_400_BAD_REQUEST)

    with schema_context('public'):
        try:
            session = UserSession.objects.get(
                id=session_id, user=request.user, is_active=True,
            )
        except UserSession.DoesNotExist:
            return Response({'error': 'Session not found.'}, status=status.HTTP_404_NOT_FOUND)

        # Don't allow revoking current session via this endpoint (use logout)
        current_token = getattr(request.auth, 'key', None)
        if session.token_key == current_token:
            return Response(
                {'error': 'Cannot revoke current session. Use logout instead.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        session.is_active = False
        session.save(update_fields=['is_active'])
        Token.objects.filter(key=session.token_key).delete()

    security_logger.info(
        'Session revoked user_id=%s session_id=%s', request.user.pk, session_id,
    )
    return Response({'status': 'Session revoked.'})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def revoke_all_sessions(request):
    """Revoke all sessions except the current one."""
    from core.models import UserSession

    current_token = getattr(request.auth, 'key', None)
    with schema_context('public'):
        UserSession.revoke_all(request.user, exclude_token_key=current_token)

    security_logger.info('All other sessions revoked user_id=%s', request.user.pk)
    return Response({'status': 'All other sessions have been revoked.'})


# ── Login Activity ──────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def login_history(request):
    """Return recent login attempts for the authenticated user."""
    from core.models import LoginAttempt

    try:
        limit = min(int(request.query_params.get('limit', 20)), 100)
    except (ValueError, TypeError):
        limit = 20
    with schema_context('public'):
        attempts = LoginAttempt.objects.filter(
            username=request.user.username,
        ).order_by('-attempted_at')[:limit]

    result = [
        {
            'ip_address': a.ip_address,
            'user_agent': a.user_agent,
            'attempted_at': a.attempted_at,
            'was_successful': a.was_successful,
        }
        for a in attempts
    ]
    return Response({'login_history': result, 'count': len(result)})
