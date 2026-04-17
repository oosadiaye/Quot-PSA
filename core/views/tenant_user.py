import logging

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from django.contrib.auth.models import User, Group
from django.db import connection, models
from django_tenants.utils import schema_context

from core.serializers import (
    TenantUserSerializer, TenantUserCreateSerializer,
    TenantUserUpdateSerializer, RoleAssignmentSerializer,
)
from core.permissions import IsTenantAdmin, invalidate_permission_cache

logger = logging.getLogger('dtsg')
security_logger = logging.getLogger('security')


class TenantUserViewSet(viewsets.ViewSet):
    """Manage users within the current tenant.

    Only accessible to tenant admins and senior managers.
    Operates on UserTenantRole records for the current tenant.
    """
    permission_classes = [IsTenantAdmin]

    def _get_tenant(self):
        return getattr(connection, 'tenant', None)

    def _get_utr_queryset(self):
        from tenants.models import UserTenantRole
        tenant = self._get_tenant()
        if not tenant or tenant.schema_name == 'public':
            return UserTenantRole.objects.none()
        return (
            UserTenantRole.objects
            .filter(tenant=tenant)
            .select_related('user')
            .prefetch_related('groups')
        )

    def list(self, request):
        """List all users in the current tenant."""
        utrs = self._get_utr_queryset()

        # Optional filters
        role = request.query_params.get('role')
        if role:
            utrs = utrs.filter(role=role)
        search = request.query_params.get('search')
        if search:
            utrs = utrs.filter(
                models.Q(user__username__icontains=search) |
                models.Q(user__first_name__icontains=search) |
                models.Q(user__last_name__icontains=search) |
                models.Q(user__email__icontains=search)
            )
        is_active = request.query_params.get('is_active')
        if is_active is not None:
            utrs = utrs.filter(is_active=is_active.lower() == 'true')

        serializer = TenantUserSerializer(utrs, many=True)
        return Response(serializer.data)

    def retrieve(self, request, pk=None):
        """Get a specific tenant user by UserTenantRole ID."""
        try:
            utr = self._get_utr_queryset().get(pk=pk)
        except Exception:
            return Response({'error': 'User not found in this tenant'}, status=status.HTTP_404_NOT_FOUND)
        serializer = TenantUserSerializer(utr)
        return Response(serializer.data)

    def create(self, request):
        """Create a new user and assign them to the current tenant."""
        from tenants.models import UserTenantRole, TenantSubscription

        serializer = TenantUserCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        tenant = self._get_tenant()
        if not tenant or tenant.schema_name == 'public':
            return Response({'error': 'No tenant context'}, status=status.HTTP_400_BAD_REQUEST)

        # Enforce max_users limit from subscription plan
        with schema_context('public'):
            try:
                sub = TenantSubscription.objects.select_related('plan').get(tenant=tenant)
                if sub.plan and sub.plan.max_users:
                    current_users = UserTenantRole.objects.filter(
                        tenant=tenant, is_active=True
                    ).count()
                    if current_users >= sub.plan.max_users:
                        return Response(
                            {'error': f'User limit reached ({sub.plan.max_users} users). Upgrade your plan to add more users.'},
                            status=status.HTTP_403_FORBIDDEN,
                        )
            except TenantSubscription.DoesNotExist:
                pass  # No subscription — allow creation

        with schema_context('public'):
            user = User.objects.create_user(
                username=data['username'].lower(),
                email=data['email'],
                password=data['password'],
                first_name=data.get('first_name', ''),
                last_name=data.get('last_name', ''),
            )

        # Create tenant role
        utr = UserTenantRole.objects.create(
            user=user, tenant=tenant,
            role=data['role'], is_active=True,
        )

        # Assign groups
        group_ids = data.get('group_ids', [])
        if group_ids:
            groups = Group.objects.filter(id__in=group_ids)
            utr.groups.set(groups)
        else:
            self._auto_assign_groups(utr)

        # Optionally link HRM employee
        if data.get('link_employee'):
            self._create_employee(user, tenant)

        result = TenantUserSerializer(utr).data
        return Response(result, status=status.HTTP_201_CREATED)

    def update(self, request, pk=None):
        """Update a tenant user's profile and role."""
        from tenants.models import UserTenantRole

        try:
            utr = self._get_utr_queryset().get(pk=pk)
        except UserTenantRole.DoesNotExist:
            return Response({'error': 'User not found in this tenant'}, status=status.HTTP_404_NOT_FOUND)

        serializer = TenantUserUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # Update user fields
        user = utr.user
        if 'email' in data:
            user.email = data['email']
        if 'first_name' in data:
            user.first_name = data['first_name']
        if 'last_name' in data:
            user.last_name = data['last_name']

        with schema_context('public'):
            user.save()

        # Update tenant role
        if 'is_active' in data:
            utr.is_active = data['is_active']
        if 'role' in data:
            utr.role = data['role']
        utr.save()

        # Update groups if provided
        if 'group_ids' in data:
            groups = Group.objects.filter(id__in=data['group_ids'])
            utr.groups.set(groups)

        invalidate_permission_cache(user.pk, utr.tenant_id)
        return Response(TenantUserSerializer(utr).data)

    def destroy(self, request, pk=None):
        """Deactivate a user's access to this tenant (soft delete)."""
        from tenants.models import UserTenantRole

        try:
            utr = self._get_utr_queryset().get(pk=pk)
        except UserTenantRole.DoesNotExist:
            return Response({'error': 'User not found in this tenant'}, status=status.HTTP_404_NOT_FOUND)

        utr.is_active = False
        utr.save()
        invalidate_permission_cache(utr.user_id, utr.tenant_id)
        return Response({'status': 'User access deactivated'})

    @action(detail=True, methods=['post'])
    def assign_role(self, request, pk=None):
        """Change a user's role and groups for this tenant."""
        from tenants.models import UserTenantRole

        try:
            utr = self._get_utr_queryset().get(pk=pk)
        except UserTenantRole.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

        serializer = RoleAssignmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        utr.role = data['role']
        utr.save()

        group_ids = data.get('group_ids', [])
        if group_ids:
            groups = Group.objects.filter(id__in=group_ids)
            utr.groups.set(groups)
        else:
            self._auto_assign_groups(utr)

        invalidate_permission_cache(utr.user_id, utr.tenant_id)
        return Response(TenantUserSerializer(utr).data)

    @action(detail=True, methods=['post'])
    def reset_password(self, request, pk=None):
        """Admin reset of a user's password with validation."""
        from tenants.models import UserTenantRole
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError as DjangoValidationError
        from core.models import PasswordHistory, UserSession

        try:
            utr = self._get_utr_queryset().get(pk=pk)
        except UserTenantRole.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

        new_password = request.data.get('new_password')
        if not new_password:
            return Response({'error': 'new_password is required'}, status=status.HTTP_400_BAD_REQUEST)

        # Validate password strength
        try:
            validate_password(new_password, utr.user)
        except DjangoValidationError as e:
            return Response({'error': ' '.join(e.messages)}, status=status.HTTP_400_BAD_REQUEST)

        with schema_context('public'):
            # Record current password before changing
            PasswordHistory.record_password(utr.user)
            utr.user.set_password(new_password)
            utr.user.save()
            # Invalidate all sessions for this user
            Token.objects.filter(user=utr.user).delete()
            UserSession.objects.filter(user=utr.user).update(is_active=False)

        security_logger.info(
            'Admin password reset user_id=%s by admin_id=%s',
            utr.user.pk, request.user.pk,
        )
        return Response({'status': 'Password reset successfully'})

    @action(detail=False, methods=['get'])
    def available_groups(self, request):
        """List available Django Groups for assignment."""
        groups = Group.objects.all().values('id', 'name')
        return Response(list(groups))

    @action(detail=True, methods=['get'])
    def effective_permissions(self, request, pk=None):
        """Show the resolved permissions for a user in this tenant."""
        from tenants.models import UserTenantRole

        try:
            utr = self._get_utr_queryset().get(pk=pk)
        except UserTenantRole.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

        if utr.role == 'admin':
            perms = ['__all__ (tenant admin — full access)']
        else:
            perms = sorted(utr.get_all_permissions())

        return Response({
            'user': utr.user.username,
            'role': utr.role,
            'role_display': utr.get_role_display(),
            'groups': list(utr.groups.values_list('name', flat=True)),
            'permissions': perms,
            'total_permissions': len(perms),
        })

    def _auto_assign_groups(self, utr):
        """Automatically assign the default group matching the user's role."""
        role_group_map = {
            'senior_manager': 'Senior Manager',
            'manager': 'Mid-Level Manager',
            'user': 'User',
            'viewer': 'Viewer',
        }
        group_name = role_group_map.get(utr.role)
        if group_name:
            try:
                group = Group.objects.get(name=group_name)
                utr.groups.set([group])
            except Group.DoesNotExist:
                logger.warning(
                    "tenant_user: Django Group '%s' not found; "
                    "user %s will not be assigned a role group",
                    group_name, getattr(utr, 'pk', '?'),
                )

    def _create_employee(self, user, tenant):
        """Create an HRM Employee record linked to the user."""
        try:
            with schema_context(tenant.schema_name):
                from hrm.models import Employee
                if not Employee.objects.filter(user=user).exists():
                    Employee.objects.create(
                        user=user,
                        employee_number=f"EMP-{user.pk:04d}",
                        first_name=user.first_name or user.username,
                        last_name=user.last_name or '',
                        email=user.email,
                        status='Active',
                    )
        except Exception as exc:
            logger.warning(
                "tenant_user: could not create HRM Employee for user %s "
                "(HRM module may not be migrated yet): %s",
                getattr(user, 'pk', '?'), exc,
            )
