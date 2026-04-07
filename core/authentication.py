from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.utils import timezone
from django_tenants.utils import schema_context
from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import AuthenticationFailed

User = get_user_model()


class PublicSchemaBackend(ModelBackend):
    """Authentication backend that always queries the public schema.

    This ensures that ``authenticate()`` checks the single, centralized
    ``auth_user`` table in the public schema regardless of which tenant
    schema is currently active.  Combined with moving
    ``django.contrib.auth`` and ``rest_framework.authtoken`` to
    ``SHARED_APPS`` only, this gives us one user pool and one token pool
    for all tenants.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        with schema_context('public'):
            return super().authenticate(
                request, username=username, password=password, **kwargs
            )

    def get_user(self, user_id):
        with schema_context('public'):
            return super().get_user(user_id)


class ExpiringTokenAuthentication(TokenAuthentication):
    """Token authentication with expiration support and session tracking.

    Tokens are stored in the public schema, so we wrap the lookup
    in ``schema_context('public')`` to ensure the query always hits
    the correct table.

    Also checks that the token's corresponding UserSession has not been
    revoked, and updates `last_activity` on each authenticated request.
    """

    def authenticate_credentials(self, key):
        with schema_context('public'):
            model = self.get_model()
            try:
                token = model.objects.select_related('user').get(key=key)
            except model.DoesNotExist:
                raise AuthenticationFailed('Invalid token.')

            if not token.user.is_active:
                raise AuthenticationFailed('User inactive or deleted.')

            expiration_hours = getattr(settings, 'TOKEN_EXPIRATION_HOURS', 24)
            if token.created < timezone.now() - timedelta(hours=expiration_hours):
                token.delete()
                raise AuthenticationFailed('Token has expired.')

            # Check if session has been revoked
            from .models import UserSession
            session = UserSession.objects.filter(token_key=key).first()
            if session and not session.is_active:
                token.delete()
                raise AuthenticationFailed('Session has been revoked.')

            # Update last activity timestamp (throttle to avoid DB spam)
            if session:
                age = (timezone.now() - session.last_activity).total_seconds()
                if age > 60:  # Update at most once per minute
                    session.save(update_fields=['last_activity'])

            return (token.user, token)
