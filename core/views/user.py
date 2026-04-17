import logging

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.authtoken.models import Token
from django.contrib.auth.models import User
from django.db import connection
from django_tenants.utils import schema_context

from core.serializers import UserSerializer, UserCreateSerializer, ChangePasswordSerializer
from core.views.auth import SignupRateThrottle, _get_user_tenants

logger = logging.getLogger('dtsg')
security_logger = logging.getLogger('security')


class UserViewSet(viewsets.ReadOnlyModelViewSet):
    """API endpoint that allows users to be viewed."""
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['is_superuser', 'is_active']
    search_fields = ['username', 'email', 'first_name', 'last_name']

    def get_queryset(self):
        queryset = super().get_queryset()
        if not self.request.user.is_superuser:
            queryset = queryset.filter(is_active=True)
        return queryset

    @action(detail=False, methods=['get'])
    def me(self, request):
        serializer = self.get_serializer(request.user)
        data = serializer.data
        data['tenants'] = _get_user_tenants(request.user)

        # Include tenant-scoped role and permissions if in a tenant context
        tenant = getattr(connection, 'tenant', None)
        if tenant and tenant.schema_name != 'public':
            from tenants.models import UserTenantRole
            try:
                utr = UserTenantRole.objects.prefetch_related('groups').get(
                    user=request.user, tenant=tenant, is_active=True
                )
                data['tenant_role'] = utr.role
                data['tenant_role_display'] = utr.get_role_display()
                data['tenant_groups'] = list(utr.groups.values_list('name', flat=True))
                if utr.role == 'admin':
                    data['tenant_permissions'] = ['__all__']
                else:
                    data['tenant_permissions'] = sorted(
                        p.split('.')[-1] for p in utr.get_all_permissions()
                    )
            except UserTenantRole.DoesNotExist:
                data['tenant_role'] = None
                data['tenant_permissions'] = []

        return Response(data)

    @action(detail=False, methods=['patch'])
    def update_profile(self, request):
        """Allow the authenticated user to update their own name and email."""
        user = request.user
        allowed = {'first_name', 'last_name', 'email'}
        data = {k: v for k, v in request.data.items() if k in allowed}

        if not data:
            return Response(
                {'error': 'No updatable fields provided. Allowed: first_name, last_name, email.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if 'email' in data:
            email = data['email'].strip().lower()
            # Enforce uniqueness (case-insensitive), excluding the current user
            with schema_context('public'):
                if User.objects.filter(email__iexact=email).exclude(pk=user.pk).exists():
                    return Response(
                        {'error': 'That email address is already associated with another account.'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            data['email'] = email

        with schema_context('public'):
            for field, value in data.items():
                setattr(user, field, value)
            user.save(update_fields=list(data.keys()))

        security_logger.info('Profile updated user_id=%s fields=%s', user.pk, list(data.keys()))
        return Response(UserSerializer(user).data)

    @action(detail=False, methods=['post'])
    def change_password(self, request):
        from core.models import PasswordHistory, UserSession
        serializer = ChangePasswordSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            new_password = serializer.validated_data['new_password']

            # Check password history
            with schema_context('public'):
                if PasswordHistory.is_password_reused(request.user, new_password):
                    return Response(
                        {'error': f'Cannot reuse any of your last {PasswordHistory.HISTORY_DEPTH} passwords.'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                # Record current password before changing
                PasswordHistory.record_password(request.user)

            with schema_context('public'):
                request.user.set_password(new_password)
                request.user.save()

            # Invalidate all other sessions (keep current)
            current_token = getattr(request.auth, 'key', None)
            with schema_context('public'):
                UserSession.revoke_all(request.user, exclude_token_key=current_token)

            security_logger.info('Password changed user_id=%s', request.user.pk)
            return Response({'status': 'password changed successfully'})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(
        detail=False, methods=['post'],
        throttle_classes=[SignupRateThrottle],
        permission_classes=[AllowAny],
        authentication_classes=[],
    )
    def register(self, request):
        from core.models import EmailVerification, PasswordHistory
        with schema_context('public'):
            serializer = UserCreateSerializer(data=request.data)
            if serializer.is_valid():
                user = serializer.save()
                token, created = Token.objects.get_or_create(user=user)

                # Record initial password in history
                PasswordHistory.record_password(user)

                # ── Auto-assign to tenant ──────────────────────────────
                # Resolve tenant from the domain sent by the frontend
                # (window.location.hostname in the request body) or fall back
                # to the X-Tenant-Domain header if present.
                tenant_assigned = False
                tenant_domain_str = (
                    request.data.get('tenant_domain')
                    or request.META.get('HTTP_X_TENANT_DOMAIN')
                )
                if tenant_domain_str:
                    try:
                        from tenants.models import Domain, UserTenantRole
                        domain_obj = Domain.objects.select_related('tenant').filter(
                            domain=tenant_domain_str
                        ).first()
                        if domain_obj and domain_obj.tenant.schema_name != 'public':
                            UserTenantRole.objects.get_or_create(
                                user=user,
                                tenant=domain_obj.tenant,
                                defaults={'role': 'admin', 'is_active': True},
                            )
                            tenant_assigned = True
                            logger.info(
                                'Auto-assigned user_id=%s to tenant=%s on registration',
                                user.pk, domain_obj.tenant.schema_name,
                            )
                    except Exception as exc:
                        # Non-fatal — user is created, admin can assign manually
                        logger.warning(
                            'Failed to auto-assign user_id=%s to tenant domain=%s: %s',
                            user.pk, tenant_domain_str, exc,
                        )

                # Create email verification token and send
                ev = EmailVerification.create_for_user(user)
                self._send_verification_email(user, ev.token)

                return Response({
                    'user': UserSerializer(user).data,
                    'token': token.key,
                    'email_verified': False,
                    'tenant_assigned': tenant_assigned,
                    'message': 'Account created. Please check your email to verify your address.',
                }, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def _send_verification_email(self, user, token):
        """Send email verification link."""
        from core.services.notification_service import NotificationService
        NotificationService.send_verification_email(user, token)
