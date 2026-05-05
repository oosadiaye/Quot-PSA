import os

from rest_framework import viewsets, status
from rest_framework.decorators import api_view, permission_classes, parser_classes as parser_classes_decorator, action
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.decorators import authentication_classes as authentication_classes_decorator
from superadmin.views import IsSuperAdminUser
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from django.utils import timezone
from datetime import timedelta

ALLOWED_EXTENSIONS = {'.pdf', '.jpg', '.jpeg', '.png', '.doc', '.docx', '.xlsx'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

# Magic-byte signatures for the allowed file types. We sniff the
# first ~8 bytes of every upload and reject when they don't match an
# expected file class. This catches the rename-attack (renaming a
# .exe to .pdf) that pure extension validation lets through.
#
# Office 2007+ formats (docx / xlsx) ARE zip files, so they share the
# 'PK\x03\x04' magic with any other zip. That's acceptable here —
# the size + extension gate constrains the misuse window.
_MAGIC_SIGNATURES = {
    '.pdf':  [b'%PDF-'],
    '.jpg':  [b'\xff\xd8\xff'],
    '.jpeg': [b'\xff\xd8\xff'],
    '.png':  [b'\x89PNG\r\n\x1a\n'],
    '.doc':  [b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'],   # OLE compound
    '.docx': [b'PK\x03\x04'],                          # zip
    '.xlsx': [b'PK\x03\x04'],                          # zip
}


def _file_signature_matches(uploaded_file, ext: str) -> bool:
    """Read the first 16 bytes and check against the expected magic
    bytes for ``ext``. Resets the file pointer afterwards so the
    later ``.save()`` still writes the full content.
    """
    sigs = _MAGIC_SIGNATURES.get(ext.lower())
    if not sigs:
        # Unknown extension — caller should have rejected before us.
        return False
    head = uploaded_file.read(16)
    uploaded_file.seek(0)
    return any(head.startswith(s) for s in sigs)
from django_tenants.utils import schema_context
from .models import Client, TenantModule, TenantSubscription, SubscriptionPlan, AVAILABLE_MODULES, TenantPayment, UserTenantRole, Role, get_tenant_settings
# Per-tenant schema models (live in each tenant's own PostgreSQL schema)
from core.models import TenantModule as PerTenantModule, Role as PerTenantRole
from .serializers import (
    TenantSerializer, TenantModuleSerializer,
    SubscriptionPlanSerializer, SubscriptionPlanListSerializer,
    TenantSubscriptionSerializer, AssignPlanSerializer,
    TenantPaymentSerializer, TenantPaymentCreateSerializer, PaymentApprovalSerializer,
    UserTenantRoleSerializer, RoleSerializer,
)


class TenantViewSet(viewsets.ReadOnlyModelViewSet):
    """API endpoint for viewing tenants (read-only for superadmin).

    DEPRECATED: The frontend uses /api/v1/superadmin/tenants instead.
    Kept for potential programmatic/API consumers. Canonical CRUD is in
    superadmin.views.tenant_list / tenant_detail.
    """
    queryset = Client.objects.exclude(schema_name='public').prefetch_related('domains')
    serializer_class = TenantSerializer
    permission_classes = [IsSuperAdminUser]


class UserTenantRoleViewSet(viewsets.ModelViewSet):
    """Manage user-tenant role assignments (superadmin only)."""
    queryset = UserTenantRole.objects.select_related('user', 'tenant').all()
    serializer_class = UserTenantRoleSerializer
    permission_classes = [IsSuperAdminUser]
    filterset_fields = ['tenant', 'user', 'role', 'is_active']
    search_fields = ['user__username', 'tenant__name']


class RoleViewSet(viewsets.ModelViewSet):
    """
    API endpoint for managing per-tenant roles.

    Roles now live in each tenant's own PostgreSQL schema (core.Role).
    All write operations and queries require a ``tenant_id`` query param
    so the view can switch to the correct schema context.
    """
    # Provide a safe default queryset so DRF router introspection works;
    # actual data is fetched inside schema_context in list/retrieve/etc.
    queryset = PerTenantRole.objects.none()
    serializer_class = RoleSerializer
    permission_classes = [IsSuperAdminUser]
    search_fields = ['name', 'code']

    def _get_tenant(self, tenant_id):
        try:
            return Client.objects.get(pk=tenant_id)
        except Client.DoesNotExist:
            return None

    def list(self, request, *args, **kwargs):
        tenant_id = request.query_params.get('tenant_id')
        if not tenant_id:
            return Response({'error': 'tenant_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        tenant = self._get_tenant(tenant_id)
        if not tenant:
            return Response({'error': 'Tenant not found'}, status=status.HTTP_404_NOT_FOUND)

        module = request.query_params.get('module')
        role_type = request.query_params.get('role_type')
        is_active = request.query_params.get('is_active')

        with schema_context(tenant.schema_name):
            qs = PerTenantRole.objects.all()
            if module:
                qs = qs.filter(module=module)
            if role_type:
                qs = qs.filter(role_type=role_type)
            if is_active is not None:
                qs = qs.filter(is_active=is_active.lower() == 'true')
            data = list(qs.values())
        return Response(data)

    def create(self, request, *args, **kwargs):
        tenant_id = request.data.get('tenant_id')
        if not tenant_id:
            return Response({'error': 'tenant_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        tenant = self._get_tenant(tenant_id)
        if not tenant:
            return Response({'error': 'Tenant not found'}, status=status.HTTP_404_NOT_FOUND)

        role_data = {k: v for k, v in request.data.items() if k != 'tenant_id'}
        with schema_context(tenant.schema_name):
            serializer = RoleSerializer(data=role_data)
            if serializer.is_valid():
                role = PerTenantRole.objects.create(**serializer.validated_data)
                return Response(
                    RoleSerializer(role).data, status=status.HTTP_201_CREATED
                )
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def retrieve(self, request, pk=None, *args, **kwargs):
        tenant_id = request.query_params.get('tenant_id')
        if not tenant_id:
            return Response({'error': 'tenant_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        tenant = self._get_tenant(tenant_id)
        if not tenant:
            return Response({'error': 'Tenant not found'}, status=status.HTTP_404_NOT_FOUND)

        with schema_context(tenant.schema_name):
            try:
                role = PerTenantRole.objects.get(pk=pk)
                return Response(RoleSerializer(role).data)
            except PerTenantRole.DoesNotExist:
                return Response({'error': 'Role not found'}, status=status.HTTP_404_NOT_FOUND)

    def update(self, request, pk=None, *args, **kwargs):
        tenant_id = request.data.get('tenant_id') or request.query_params.get('tenant_id')
        if not tenant_id:
            return Response({'error': 'tenant_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        tenant = self._get_tenant(tenant_id)
        if not tenant:
            return Response({'error': 'Tenant not found'}, status=status.HTTP_404_NOT_FOUND)

        with schema_context(tenant.schema_name):
            try:
                role = PerTenantRole.objects.get(pk=pk)
            except PerTenantRole.DoesNotExist:
                return Response({'error': 'Role not found'}, status=status.HTTP_404_NOT_FOUND)
            role_data = {k: v for k, v in request.data.items() if k != 'tenant_id'}
            serializer = RoleSerializer(role, data=role_data, partial=kwargs.get('partial', False))
            if serializer.is_valid():
                for attr, value in serializer.validated_data.items():
                    setattr(role, attr, value)
                role.save()
                return Response(RoleSerializer(role).data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def partial_update(self, request, pk=None, *args, **kwargs):
        kwargs['partial'] = True
        return self.update(request, pk, *args, **kwargs)

    def destroy(self, request, pk=None, *args, **kwargs):
        tenant_id = request.query_params.get('tenant_id')
        if not tenant_id:
            return Response({'error': 'tenant_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        tenant = self._get_tenant(tenant_id)
        if not tenant:
            return Response({'error': 'Tenant not found'}, status=status.HTTP_404_NOT_FOUND)

        with schema_context(tenant.schema_name):
            try:
                PerTenantRole.objects.get(pk=pk).delete()
                return Response(status=status.HTTP_204_NO_CONTENT)
            except PerTenantRole.DoesNotExist:
                return Response({'error': 'Role not found'}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=False, methods=['post'])
    def seed_defaults(self, request):
        """Seed default roles into a tenant's own schema."""
        tenant_id = request.data.get('tenant_id')
        if not tenant_id:
            return Response({'error': 'tenant_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        tenant = self._get_tenant(tenant_id)
        if not tenant:
            return Response({'error': 'Tenant not found'}, status=status.HTTP_404_NOT_FOUND)

        from tenants.management.commands.seed_default_roles import seed_tenant_default_roles
        roles_created, groups_created = seed_tenant_default_roles(tenant)
        return Response({
            'status': f'{roles_created} roles and {groups_created} groups seeded for {tenant.name}',
            'roles_created': roles_created,
            'groups_created': groups_created,
        })


class TenantModuleViewSet(viewsets.ModelViewSet):
    """
    API endpoint for managing per-tenant module feature toggles.

    Modules now live in each tenant's own PostgreSQL schema (core.TenantModule).
    All operations require a ``tenant_id`` query param / request body so the
    view can switch to the correct schema context.

    The canonical UI endpoint is /api/v1/superadmin/tenants/<id>/modules —
    this viewset is kept for programmatic / API consumers.
    """
    queryset = PerTenantModule.objects.none()
    serializer_class = TenantModuleSerializer
    permission_classes = [IsSuperAdminUser]

    def _get_tenant(self, tenant_id):
        try:
            return Client.objects.get(pk=tenant_id)
        except Client.DoesNotExist:
            return None

    def list(self, request, *args, **kwargs):
        tenant_id = request.query_params.get('tenant_id')
        if not tenant_id:
            return Response({'error': 'tenant_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        tenant = self._get_tenant(tenant_id)
        if not tenant:
            return Response({'error': 'Tenant not found'}, status=status.HTTP_404_NOT_FOUND)

        with schema_context(tenant.schema_name):
            data = list(PerTenantModule.objects.values())
        return Response(data)

    def create(self, request, *args, **kwargs):
        tenant_id = request.data.get('tenant_id')
        modules_data = request.data.get('modules', [])
        if not tenant_id:
            return Response({'error': 'tenant_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        tenant = self._get_tenant(tenant_id)
        if not tenant:
            return Response({'error': 'Tenant not found'}, status=status.HTTP_404_NOT_FOUND)

        results = []
        with schema_context(tenant.schema_name):
            for mod in modules_data:
                obj, _ = PerTenantModule.objects.update_or_create(
                    module_name=mod.get('module_name'),
                    defaults={
                        'module_title': mod.get('module_title', ''),
                        'description': mod.get('description', ''),
                        'is_active': mod.get('is_active', True),
                    },
                )
                results.append({'module_name': obj.module_name, 'is_active': obj.is_active})
        return Response(results, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'])
    def bulk_update(self, request):
        tenant_id = request.data.get('tenant_id')
        modules = request.data.get('modules', {})
        if not tenant_id:
            return Response({'error': 'tenant_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        tenant = self._get_tenant(tenant_id)
        if not tenant:
            return Response({'error': 'Tenant not found'}, status=status.HTTP_404_NOT_FOUND)

        updated = []
        with schema_context(tenant.schema_name):
            for module_name, is_active in modules.items():
                title, desc = '', ''
                for key, t, d in AVAILABLE_MODULES:
                    if key == module_name:
                        title, desc = t, d
                        break
                obj, _ = PerTenantModule.objects.update_or_create(
                    module_name=module_name,
                    defaults={'is_active': is_active, 'module_title': title, 'description': desc},
                )
                updated.append({'module_name': obj.module_name, 'is_active': obj.is_active})
        return Response(updated)
    
    @action(detail=False, methods=['post'])
    def toggle(self, request, pk=None):
        """Toggle a module by name for a specific tenant."""
        tenant_id = request.data.get('tenant_id')
        module_name = request.data.get('module_name')
        if not tenant_id or not module_name:
            return Response({'error': 'tenant_id and module_name are required'}, status=status.HTTP_400_BAD_REQUEST)
        tenant = self._get_tenant(tenant_id)
        if not tenant:
            return Response({'error': 'Tenant not found'}, status=status.HTTP_404_NOT_FOUND)

        with schema_context(tenant.schema_name):
            try:
                module = PerTenantModule.objects.get(module_name=module_name)
                module.is_active = not module.is_active
                module.save()
                return Response({
                    'status': 'Module activated' if module.is_active else 'Module deactivated',
                    'module_name': module.module_name,
                    'is_active': module.is_active,
                })
            except PerTenantModule.DoesNotExist:
                return Response({'error': 'Module not found'}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=False, methods=['post'])
    def activate(self, request, pk=None):
        """Activate a module for a specific tenant."""
        tenant_id = request.data.get('tenant_id')
        module_name = request.data.get('module_name')
        if not tenant_id or not module_name:
            return Response({'error': 'tenant_id and module_name are required'}, status=status.HTTP_400_BAD_REQUEST)
        tenant = self._get_tenant(tenant_id)
        if not tenant:
            return Response({'error': 'Tenant not found'}, status=status.HTTP_404_NOT_FOUND)

        with schema_context(tenant.schema_name):
            obj, _ = PerTenantModule.objects.update_or_create(
                module_name=module_name,
                defaults={'is_active': True},
            )
        return Response({'status': 'Module activated', 'module_name': module_name, 'is_active': True})

    @action(detail=False, methods=['post'])
    def deactivate(self, request, pk=None):
        """Deactivate a module for a specific tenant."""
        tenant_id = request.data.get('tenant_id')
        module_name = request.data.get('module_name')
        if not tenant_id or not module_name:
            return Response({'error': 'tenant_id and module_name are required'}, status=status.HTTP_400_BAD_REQUEST)
        tenant = self._get_tenant(tenant_id)
        if not tenant:
            return Response({'error': 'Tenant not found'}, status=status.HTTP_404_NOT_FOUND)

        with schema_context(tenant.schema_name):
            PerTenantModule.objects.filter(module_name=module_name).update(is_active=False)
        return Response({'status': 'Module deactivated', 'module_name': module_name, 'is_active': False
        })
    
    @action(detail=False, methods=['post'])
    def initialize_modules(self, request):
        """Initialize all available modules for a tenant with default settings.

        Writes to ``PerTenantModule`` (the new per-schema model) so the
        rest of this viewset's CRUD actions (which already read/write
        PerTenantModule) see the same source of truth. The legacy
        public-schema ``TenantModule`` model is kept around only until
        the deprecation cleanup migration drops it.
        """
        from django_tenants.utils import schema_context
        tenant_id = request.data.get('tenant_id')
        if not tenant_id:
            return Response({'error': 'tenant_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            tenant = Client.objects.get(pk=tenant_id)
        except Client.DoesNotExist:
            return Response({'error': 'Tenant not found'}, status=status.HTTP_404_NOT_FOUND)

        created_modules = []
        with schema_context(tenant.schema_name):
            for mod_name, mod_title, mod_desc in AVAILABLE_MODULES:
                module, _created = PerTenantModule.objects.update_or_create(
                    module_name=mod_name,
                    defaults={
                        'module_title': mod_title,
                        'description': mod_desc,
                        'is_active': True,
                    },
                )
                created_modules.append(module)

            serializer = self.get_serializer(created_modules, many=True)
            return Response({
                'status': 'Modules initialized',
                'modules': serializer.data,
            }, status=status.HTTP_201_CREATED)


class SubscriptionPlanViewSet(viewsets.ModelViewSet):
    """API endpoint for managing subscription plans.

    DEPRECATED: The frontend uses /api/v1/superadmin/plans instead.
    Kept for the create_default_plans action and programmatic access.
    """
    queryset = SubscriptionPlan.objects.all()
    permission_classes = [IsSuperAdminUser]
    
    def get_serializer_class(self):
        if self.action == 'list':
            return SubscriptionPlanListSerializer
        return SubscriptionPlanSerializer
    
    @action(detail=False, methods=['post'])
    def create_default_plans(self, request):
        """Create default subscription plans with comprehensive features"""

        # ── Feature templates per plan ────────────────────────────────
        free_features = [
            {'category': 'Core', 'name': 'Chart of Accounts', 'included': True},
            {'category': 'Core', 'name': 'Journal Entries', 'included': True, 'limit': '50/month'},
            {'category': 'Core', 'name': 'Budget Allocations', 'included': True, 'limit': '5 budgets'},
            {'category': 'Core', 'name': 'Financial Reports', 'included': True, 'limit': 'Basic only'},
            {'category': 'Users & Access', 'name': 'User Accounts', 'included': True, 'limit': '3 users'},
            {'category': 'Users & Access', 'name': 'Role-Based Access', 'included': False},
            {'category': 'Users & Access', 'name': 'Audit Trail', 'included': False},
            {'category': 'Storage & Data', 'name': 'Cloud Storage', 'included': True, 'limit': '1 GB'},
            {'category': 'Storage & Data', 'name': 'Data Export (CSV)', 'included': True},
            {'category': 'Storage & Data', 'name': 'Automated Backups', 'included': False},
            {'category': 'Modules', 'name': 'Accounting', 'included': True},
            {'category': 'Modules', 'name': 'Budget Management', 'included': True},
            {'category': 'Modules', 'name': 'Procurement', 'included': False},
            {'category': 'Modules', 'name': 'Inventory', 'included': False},
            {'category': 'Modules', 'name': 'Sales & CRM', 'included': False},
            {'category': 'Modules', 'name': 'Human Resources', 'included': False},
            {'category': 'Modules', 'name': 'Service Management', 'included': False},
            {'category': 'Modules', 'name': 'Workflow & Approvals', 'included': False},
            {'category': 'Modules', 'name': 'Production', 'included': False},
            {'category': 'Modules', 'name': 'Quality Management', 'included': False},
            {'category': 'Support', 'name': 'Email Support', 'included': True, 'limit': 'Community'},
            {'category': 'Support', 'name': 'Priority Support', 'included': False},
            {'category': 'Support', 'name': 'Dedicated Account Manager', 'included': False},
            {'category': 'Integrations', 'name': 'API Access', 'included': False},
            {'category': 'Integrations', 'name': 'Webhooks', 'included': False},
            {'category': 'Integrations', 'name': 'Custom SMTP', 'included': False},
        ]

        basic_features = [
            {'category': 'Core', 'name': 'Chart of Accounts', 'included': True},
            {'category': 'Core', 'name': 'Journal Entries', 'included': True, 'limit': '500/month'},
            {'category': 'Core', 'name': 'Budget Allocations', 'included': True, 'limit': '20 budgets'},
            {'category': 'Core', 'name': 'Financial Reports', 'included': True},
            {'category': 'Core', 'name': 'Multi-Currency', 'included': True, 'limit': '3 currencies'},
            {'category': 'Core', 'name': 'AP/AR Management', 'included': True},
            {'category': 'Users & Access', 'name': 'User Accounts', 'included': True, 'limit': '10 users'},
            {'category': 'Users & Access', 'name': 'Role-Based Access', 'included': True},
            {'category': 'Users & Access', 'name': 'Audit Trail', 'included': True, 'limit': '90 days'},
            {'category': 'Storage & Data', 'name': 'Cloud Storage', 'included': True, 'limit': '10 GB'},
            {'category': 'Storage & Data', 'name': 'Data Export (CSV)', 'included': True},
            {'category': 'Storage & Data', 'name': 'Automated Backups', 'included': True, 'limit': 'Weekly'},
            {'category': 'Modules', 'name': 'Accounting', 'included': True},
            {'category': 'Modules', 'name': 'Budget Management', 'included': True},
            {'category': 'Modules', 'name': 'Procurement', 'included': True},
            {'category': 'Modules', 'name': 'Inventory', 'included': True},
            {'category': 'Modules', 'name': 'Sales & CRM', 'included': False},
            {'category': 'Modules', 'name': 'Human Resources', 'included': False},
            {'category': 'Modules', 'name': 'Service Management', 'included': False},
            {'category': 'Modules', 'name': 'Workflow & Approvals', 'included': False},
            {'category': 'Modules', 'name': 'Production', 'included': False},
            {'category': 'Modules', 'name': 'Quality Management', 'included': False},
            {'category': 'Support', 'name': 'Email Support', 'included': True},
            {'category': 'Support', 'name': 'Priority Support', 'included': False},
            {'category': 'Support', 'name': 'Dedicated Account Manager', 'included': False},
            {'category': 'Integrations', 'name': 'API Access', 'included': True, 'limit': '1,000 req/day'},
            {'category': 'Integrations', 'name': 'Webhooks', 'included': False},
            {'category': 'Integrations', 'name': 'Custom SMTP', 'included': False},
        ]

        standard_features = [
            {'category': 'Core', 'name': 'Chart of Accounts', 'included': True},
            {'category': 'Core', 'name': 'Journal Entries', 'included': True, 'limit': 'Unlimited'},
            {'category': 'Core', 'name': 'Budget Allocations', 'included': True, 'limit': 'Unlimited'},
            {'category': 'Core', 'name': 'Financial Reports', 'included': True},
            {'category': 'Core', 'name': 'Multi-Currency', 'included': True, 'limit': 'Unlimited'},
            {'category': 'Core', 'name': 'AP/AR Management', 'included': True},
            {'category': 'Core', 'name': 'Fixed Asset Management', 'included': True},
            {'category': 'Core', 'name': 'Bank Reconciliation', 'included': True},
            {'category': 'Users & Access', 'name': 'User Accounts', 'included': True, 'limit': '50 users'},
            {'category': 'Users & Access', 'name': 'Role-Based Access', 'included': True},
            {'category': 'Users & Access', 'name': 'Audit Trail', 'included': True, 'limit': '1 year'},
            {'category': 'Users & Access', 'name': 'Two-Factor Auth', 'included': True},
            {'category': 'Storage & Data', 'name': 'Cloud Storage', 'included': True, 'limit': '50 GB'},
            {'category': 'Storage & Data', 'name': 'Data Export (CSV)', 'included': True},
            {'category': 'Storage & Data', 'name': 'Automated Backups', 'included': True, 'limit': 'Daily'},
            {'category': 'Storage & Data', 'name': 'Data Import Tools', 'included': True},
            {'category': 'Modules', 'name': 'Accounting', 'included': True},
            {'category': 'Modules', 'name': 'Budget Management', 'included': True},
            {'category': 'Modules', 'name': 'Procurement', 'included': True},
            {'category': 'Modules', 'name': 'Inventory', 'included': True},
            {'category': 'Modules', 'name': 'Sales & CRM', 'included': True},
            {'category': 'Modules', 'name': 'Human Resources', 'included': True},
            {'category': 'Modules', 'name': 'Service Management', 'included': False},
            {'category': 'Modules', 'name': 'Workflow & Approvals', 'included': False},
            {'category': 'Modules', 'name': 'Production', 'included': False},
            {'category': 'Modules', 'name': 'Quality Management', 'included': False},
            {'category': 'Support', 'name': 'Email Support', 'included': True},
            {'category': 'Support', 'name': 'Priority Support', 'included': True},
            {'category': 'Support', 'name': 'Dedicated Account Manager', 'included': False},
            {'category': 'Integrations', 'name': 'API Access', 'included': True, 'limit': '10,000 req/day'},
            {'category': 'Integrations', 'name': 'Webhooks', 'included': True},
            {'category': 'Integrations', 'name': 'Custom SMTP', 'included': True},
        ]

        enterprise_features = [
            {'category': 'Core', 'name': 'Chart of Accounts', 'included': True},
            {'category': 'Core', 'name': 'Journal Entries', 'included': True, 'limit': 'Unlimited'},
            {'category': 'Core', 'name': 'Budget Allocations', 'included': True, 'limit': 'Unlimited'},
            {'category': 'Core', 'name': 'Financial Reports', 'included': True},
            {'category': 'Core', 'name': 'Multi-Currency', 'included': True, 'limit': 'Unlimited'},
            {'category': 'Core', 'name': 'AP/AR Management', 'included': True},
            {'category': 'Core', 'name': 'Fixed Asset Management', 'included': True},
            {'category': 'Core', 'name': 'Bank Reconciliation', 'included': True},
            {'category': 'Core', 'name': 'Multi-Dimensional Accounting', 'included': True},
            {'category': 'Users & Access', 'name': 'User Accounts', 'included': True, 'limit': 'Unlimited'},
            {'category': 'Users & Access', 'name': 'Role-Based Access', 'included': True},
            {'category': 'Users & Access', 'name': 'Audit Trail', 'included': True, 'limit': 'Unlimited'},
            {'category': 'Users & Access', 'name': 'Two-Factor Auth', 'included': True},
            {'category': 'Users & Access', 'name': 'SSO Integration', 'included': True},
            {'category': 'Users & Access', 'name': 'IP Whitelisting', 'included': True},
            {'category': 'Storage & Data', 'name': 'Cloud Storage', 'included': True, 'limit': '1 TB'},
            {'category': 'Storage & Data', 'name': 'Data Export (CSV)', 'included': True},
            {'category': 'Storage & Data', 'name': 'Automated Backups', 'included': True, 'limit': 'Real-time'},
            {'category': 'Storage & Data', 'name': 'Data Import Tools', 'included': True},
            {'category': 'Storage & Data', 'name': 'Custom Reports Builder', 'included': True},
            {'category': 'Modules', 'name': 'Accounting', 'included': True},
            {'category': 'Modules', 'name': 'Budget Management', 'included': True},
            {'category': 'Modules', 'name': 'Procurement', 'included': True},
            {'category': 'Modules', 'name': 'Inventory', 'included': True},
            {'category': 'Modules', 'name': 'Sales & CRM', 'included': True},
            {'category': 'Modules', 'name': 'Human Resources', 'included': True},
            {'category': 'Modules', 'name': 'Service Management', 'included': True},
            {'category': 'Modules', 'name': 'Workflow & Approvals', 'included': True},
            {'category': 'Modules', 'name': 'Production', 'included': True},
            {'category': 'Modules', 'name': 'Quality Management', 'included': True},
            {'category': 'Support', 'name': 'Email Support', 'included': True},
            {'category': 'Support', 'name': 'Priority Support', 'included': True, 'limit': '24/7'},
            {'category': 'Support', 'name': 'Dedicated Account Manager', 'included': True},
            {'category': 'Support', 'name': 'On-site Training', 'included': True},
            {'category': 'Support', 'name': 'SLA Guarantee', 'included': True, 'limit': '99.9% uptime'},
            {'category': 'Integrations', 'name': 'API Access', 'included': True, 'limit': 'Unlimited'},
            {'category': 'Integrations', 'name': 'Webhooks', 'included': True},
            {'category': 'Integrations', 'name': 'Custom SMTP', 'included': True},
            {'category': 'Integrations', 'name': 'Custom Integrations', 'included': True},
            {'category': 'Integrations', 'name': 'White-Label Branding', 'included': True},
        ]

        default_plans = [
            {
                'name': 'Free Trial',
                'plan_type': 'free',
                'description': 'Explore QUOT ERP with core accounting and budget modules. Perfect for evaluation.',
                'price': 0,
                'billing_cycle': 'monthly',
                'max_users': 3,
                'max_storage_gb': 1,
                'allowed_modules': ['accounting', 'budget'],
                'features': free_features,
                'is_active': True,
                'is_featured': False,
                'trial_days': 14
            },
            {
                'name': 'Basic',
                'plan_type': 'basic',
                'description': 'Essential IFMIS for small MDAs with accounting, budget, and procurement.',
                'price': 50000,
                'billing_cycle': 'monthly',
                'max_users': 10,
                'max_storage_gb': 10,
                'allowed_modules': ['accounting', 'budget', 'procurement', 'dimensions'],
                'features': basic_features,
                'is_active': True,
                'is_featured': False,
                'trial_days': 0
            },
            {
                'name': 'Standard',
                'plan_type': 'standard',
                'description': 'Complete IFMIS with Treasury, Revenue, HR, and advanced financial management.',
                'price': 150000,
                'billing_cycle': 'monthly',
                'max_users': 50,
                'max_storage_gb': 50,
                'allowed_modules': ['accounting', 'budget', 'treasury', 'revenue', 'procurement', 'inventory', 'hrm', 'workflow', 'dimensions'],
                'features': standard_features,
                'is_active': True,
                'is_featured': True,
                'trial_days': 0
            },
            {
                'name': 'Enterprise',
                'plan_type': 'enterprise',
                'description': 'Full IFMIS with all modules, unlimited users, IPSAS reporting, and priority support.',
                'price': 500000,
                'billing_cycle': 'yearly',
                'max_users': 999999,
                'max_storage_gb': 1000,
                'allowed_modules': [m[0] for m in AVAILABLE_MODULES],
                'features': enterprise_features,
                'is_active': True,
                'is_featured': False,
                'trial_days': 0
            },
        ]
        
        created = []
        for plan_data in default_plans:
            plan, created_flag = SubscriptionPlan.objects.update_or_create(
                name=plan_data['name'],
                defaults=plan_data
            )
            created.append(plan)
        
        serializer = self.get_serializer(created, many=True)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class TenantSubscriptionViewSet(viewsets.ModelViewSet):
    """API endpoint for managing tenant subscriptions.

    DEPRECATED: The frontend uses /api/v1/superadmin/tenants/<id>/change-plan instead.
    Kept for assign_plan, cancel, suspend, reactivate actions and programmatic access.
    """
    queryset = TenantSubscription.objects.all().select_related('tenant', 'plan')
    serializer_class = TenantSubscriptionSerializer
    permission_classes = [IsSuperAdminUser]
    
    def get_queryset(self):
        queryset = super().get_queryset()
        tenant_id = self.request.query_params.get('tenant_id')
        if tenant_id:
            queryset = queryset.filter(tenant_id=tenant_id)
        return queryset
    
    @action(detail=False, methods=['post'])
    def assign_plan(self, request):
        """Assign a plan to a tenant"""
        serializer = AssignPlanSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        tenant_id = serializer.validated_data['tenant_id']
        plan_id = serializer.validated_data['plan_id']
        
        try:
            tenant = Client.objects.get(pk=tenant_id)
        except Client.DoesNotExist:
            return Response({'error': 'Tenant not found'}, status=status.HTTP_404_NOT_FOUND)
        
        try:
            plan = SubscriptionPlan.objects.get(pk=plan_id)
        except SubscriptionPlan.DoesNotExist:
            return Response({'error': 'Plan not found'}, status=status.HTTP_404_NOT_FOUND)
        
        # Calculate subscription dates
        start_date = serializer.validated_data.get('start_date', timezone.now().date())
        billing_days = {'monthly': 30, 'quarterly': 90, 'yearly': 365}
        duration = billing_days.get(plan.billing_cycle, 30)
        end_date = serializer.validated_data.get('end_date', start_date + timedelta(days=duration))
        
        subscription, created = TenantSubscription.objects.update_or_create(
            tenant=tenant,
            defaults={
                'plan': plan,
                'status': 'active',
                'start_date': start_date,
                'end_date': end_date,
                'auto_renew': serializer.validated_data.get('auto_renew', True),
                'notes': serializer.validated_data.get('notes', '')
            }
        )
        
        # Auto-enable modules based on plan (deactivate unlisted, activate listed)
        allowed = set(plan.allowed_modules or [])
        # Deactivate modules not in the new plan
        TenantModule.objects.filter(tenant=tenant).exclude(
            module_name__in=allowed
        ).update(is_active=False)
        # Enable/create modules in the new plan
        for module_name in allowed:
            module_title = {k: t for k, t, _d in AVAILABLE_MODULES}.get(module_name, module_name)
            TenantModule.objects.update_or_create(
                tenant=tenant,
                module_name=module_name,
                defaults={
                    'module_title': module_title,
                    'description': f'Included in {plan.name} plan',
                    'is_active': True,
                },
            )
        
        result_serializer = self.get_serializer(subscription)
        return Response(result_serializer.data)
    
    @action(detail=False, methods=['post'])
    def cancel_subscription(self, request):
        """Cancel a tenant's subscription"""
        tenant_id = request.data.get('tenant_id')
        
        if not tenant_id:
            return Response({'error': 'tenant_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            subscription = TenantSubscription.objects.get(tenant_id=tenant_id)
            subscription.status = 'cancelled'
            subscription.auto_renew = False
            subscription.save()
            return Response({'status': 'Subscription cancelled successfully'})
        except TenantSubscription.DoesNotExist:
            return Response({'error': 'Subscription not found'}, status=status.HTTP_404_NOT_FOUND)
    
    @action(detail=False, methods=['post'])
    def suspend_subscription(self, request):
        """Suspend a tenant's subscription"""
        tenant_id = request.data.get('tenant_id')
        
        if not tenant_id:
            return Response({'error': 'tenant_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            subscription = TenantSubscription.objects.get(tenant_id=tenant_id)
            subscription.status = 'suspended'
            subscription.save()
            return Response({'status': 'Subscription suspended successfully'})
        except TenantSubscription.DoesNotExist:
            return Response({'error': 'Subscription not found'}, status=status.HTTP_404_NOT_FOUND)
    
    @action(detail=False, methods=['post'])
    def reactivate_subscription(self, request):
        """Reactivate a suspended subscription"""
        tenant_id = request.data.get('tenant_id')
        
        if not tenant_id:
            return Response({'error': 'tenant_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            subscription = TenantSubscription.objects.get(tenant_id=tenant_id)
            subscription.status = 'active'
            subscription.save()
            return Response({'status': 'Subscription reactivated successfully'})
        except TenantSubscription.DoesNotExist:
            return Response({'error': 'Subscription not found'}, status=status.HTTP_404_NOT_FOUND)


@api_view(['GET'])
@permission_classes([IsSuperAdminUser])
def available_modules(request):
    """Get list of all available modules"""
    modules = [{'name': m[0], 'title': m[1], 'description': m[2]} for m in AVAILABLE_MODULES]
    return Response({'modules': modules})


@api_view(['GET'])
@permission_classes([IsSuperAdminUser])
def tenant_modules(request):
    """Get all module configurations for a tenant"""
    tenant_id = request.query_params.get('tenant_id')
    
    if not tenant_id:
        return Response({'error': 'tenant_id is required'}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        tenant = Client.objects.get(pk=tenant_id)
    except Client.DoesNotExist:
        return Response({'error': 'Tenant not found'}, status=status.HTTP_404_NOT_FOUND)
    
    existing = {m.module_name: m for m in tenant.modules.all()}
    
    result = []
    for mod_name, mod_title, mod_desc in AVAILABLE_MODULES:
        if mod_name in existing:
            tm = existing[mod_name]
            result.append({
                'id': tm.id,
                'module_name': tm.module_name,
                'module_title': tm.module_title,
                'description': tm.description,
                'is_active': tm.is_active,
                'configured': True
            })
        else:
            result.append({
                'id': None,
                'module_name': mod_name,
                'module_title': mod_title,
                'description': mod_desc,
                'is_active': False,
                'configured': False
            })
    
    return Response(result)


class TenantPaymentViewSet(viewsets.ModelViewSet):
    """API endpoint for managing tenant payments.

    DEPRECATED for superadmin use: The frontend uses /api/v1/superadmin/payments instead.
    Still used by tenant-facing payment upload (receipt submission by tenants).
    """
    queryset = TenantPayment.objects.all().select_related('tenant', 'subscription', 'approved_by')
    serializer_class = TenantPaymentSerializer
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        # Restrict mutating actions (update / partial_update / destroy
        # / approve / reject) to platform superusers. Tenant operators
        # may create receipts (uploading their own bank slip) and
        # read their own tenant's payments — nothing more.
        # Previously every action allowed any authenticated user; a
        # tenant-A admin who shared a user account across tenants
        # could see and mutate tenant-B's payment records via the
        # upload_receipt and other mutating endpoints.
        if self.action in ('list', 'retrieve', 'create'):
            return [IsAuthenticated()]
        # All write actions on existing rows are platform-admin only.
        from rest_framework.permissions import BasePermission

        class _IsSuper(BasePermission):
            def has_permission(self, request, view):
                return bool(request.user and request.user.is_superuser)
        return [IsAuthenticated(), _IsSuper()]

    def get_queryset(self):
        queryset = super().get_queryset()
        tenant_id = self.request.query_params.get('tenant_id')
        status_filter = self.request.query_params.get('status')

        if tenant_id:
            queryset = queryset.filter(tenant_id=tenant_id)
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        # Non-admin users can only see their tenant's payments
        if not self.request.user.is_superuser:
            user_tenants = UserTenantRole.objects.filter(
                user=self.request.user, is_active=True
            ).values_list('tenant_id', flat=True)
            queryset = queryset.filter(tenant_id__in=user_tenants)

        return queryset
    
    def create(self, request, *args, **kwargs):
        """Tenant uploads payment receipt"""
        serializer = TenantPaymentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Get tenant from request (usually from user's session)
        tenant_id = request.data.get('tenant_id')
        
        if not tenant_id:
            # Try to get from user's tenant roles
            user_role = UserTenantRole.objects.filter(
                user=request.user, is_active=True
            ).first()
            if user_role:
                tenant_id = user_role.tenant_id
        
        if not tenant_id:
            return Response({'error': 'tenant_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            tenant = Client.objects.get(pk=tenant_id)
        except Client.DoesNotExist:
            return Response({'error': 'Tenant not found'}, status=status.HTTP_404_NOT_FOUND)
        
        # Check for duplicate transaction reference
        if TenantPayment.objects.filter(transaction_reference=serializer.validated_data['transaction_reference']).exists():
            return Response({'error': 'Transaction reference already exists'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Get subscription
        subscription = None
        try:
            subscription = tenant.subscription
        except TenantSubscription.DoesNotExist:
            pass
        
        payment = TenantPayment.objects.create(
            tenant=tenant,
            subscription=subscription,
            amount=serializer.validated_data['amount'],
            currency=serializer.validated_data.get('currency', 'NGN'),
            payment_method=serializer.validated_data['payment_method'],
            bank_name=serializer.validated_data['bank_name'],
            account_number=serializer.validated_data['account_number'],
            transaction_reference=serializer.validated_data['transaction_reference'],
            payment_date=serializer.validated_data['payment_date'],
            status='pending'
        )
        
        # Handle receipt upload
        if 'receipt' in request.FILES:
            uploaded_file = request.FILES['receipt']
            ext = os.path.splitext(uploaded_file.name)[1].lower()
            if ext not in ALLOWED_EXTENSIONS:
                return Response({'error': f'File type {ext} not allowed'}, status=status.HTTP_400_BAD_REQUEST)
            # Magic-byte check defeats rename attacks (.exe -> .pdf).
            if not _file_signature_matches(uploaded_file, ext):
                return Response(
                    {'error': f'Uploaded file content does not match the {ext} format.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if uploaded_file.size > MAX_FILE_SIZE:
                return Response({'error': 'File size exceeds 10MB limit'}, status=status.HTTP_400_BAD_REQUEST)
            payment.receipt_document = uploaded_file
            payment.receipt_filename = uploaded_file.name
            payment.save()
        
        result_serializer = TenantPaymentSerializer(payment)
        return Response(result_serializer.data, status=status.HTTP_201_CREATED)
    
    @action(detail=False, methods=['post'])
    def upload_receipt(self, request):
        """Upload payment receipt for an existing payment"""
        payment_id = request.data.get('payment_id')

        if not payment_id:
            return Response({'error': 'payment_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            payment = TenantPayment.objects.get(pk=payment_id)
        except TenantPayment.DoesNotExist:
            return Response({'error': 'Payment not found'}, status=status.HTTP_404_NOT_FOUND)

        # Verify tenant ownership for non-superusers
        if not request.user.is_superuser:
            user_tenants = UserTenantRole.objects.filter(
                user=request.user, is_active=True
            ).values_list('tenant_id', flat=True)
            if payment.tenant_id not in list(user_tenants):
                return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)

        if 'receipt' in request.FILES:
            uploaded_file = request.FILES['receipt']
            ext = os.path.splitext(uploaded_file.name)[1].lower()
            if ext not in ALLOWED_EXTENSIONS:
                return Response({'error': f'File type {ext} not allowed'}, status=status.HTTP_400_BAD_REQUEST)
            # Magic-byte check defeats rename attacks (.exe -> .pdf).
            if not _file_signature_matches(uploaded_file, ext):
                return Response(
                    {'error': f'Uploaded file content does not match the {ext} format.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if uploaded_file.size > MAX_FILE_SIZE:
                return Response({'error': 'File size exceeds 10MB limit'}, status=status.HTTP_400_BAD_REQUEST)
            payment.receipt_document = uploaded_file
            payment.receipt_filename = uploaded_file.name
            payment.save()

            return Response({
                'status': 'Receipt uploaded successfully',
                'filename': payment.receipt_filename
            })
        
        return Response({'error': 'No receipt file provided'}, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['post'])
    def approve_payment(self, request):
        """Approve or reject a payment (superadmin only)"""
        if not request.user.is_superuser:
            return Response({'error': 'Only super admins can approve payments'}, status=status.HTTP_403_FORBIDDEN)
        
        serializer = PaymentApprovalSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        payment_id = serializer.validated_data['payment_id']
        action = serializer.validated_data['action']
        notes = serializer.validated_data.get('notes', '')
        
        try:
            payment = TenantPayment.objects.get(pk=payment_id)
        except TenantPayment.DoesNotExist:
            return Response({'error': 'Payment not found'}, status=status.HTTP_404_NOT_FOUND)
        
        if payment.status != 'pending':
            return Response({'error': f'Payment is already {payment.status}'}, status=status.HTTP_400_BAD_REQUEST)

        # Cross-tenant integrity check: a payment row carries both
        # ``tenant`` and ``subscription`` FKs — they MUST point to the
        # same tenant. Without this guard a misconfigured payment
        # (e.g. created via API with a swapped subscription_id) could
        # extend tenant B's subscription on the strength of tenant
        # A's bank receipt.
        if payment.subscription_id and payment.subscription.tenant_id != payment.tenant_id:
            return Response(
                {
                    'error': (
                        f'Payment integrity error: payment.tenant_id '
                        f'({payment.tenant_id}) does not match '
                        f'subscription.tenant_id '
                        f'({payment.subscription.tenant_id}). '
                        f'Cannot approve.'
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if action == 'approve':
            payment.status = 'approved'
            payment.approved_by = request.user
            payment.approved_date = timezone.now()
            payment.approval_notes = notes
            payment.save()

            # Update subscription if exists
            if payment.subscription:
                payment.subscription.status = 'active'
                payment.subscription.last_payment_date = payment.payment_date
                if payment.subscription.end_date and payment.subscription.end_date < timezone.now().date():
                    # Extend subscription
                    billing_days = {'monthly': 30, 'quarterly': 90, 'yearly': 365}
                    days = billing_days.get(payment.subscription.plan.billing_cycle, 30) if payment.subscription.plan else 30
                    payment.subscription.end_date = timezone.now().date() + timedelta(days=days)
                payment.subscription.save()
            
            return Response({
                'status': 'Payment approved',
                'payment_id': payment.id,
                'amount': str(payment.amount)
            })
        else:
            payment.status = 'rejected'
            payment.approval_notes = notes
            payment.save()
            
            return Response({
                'status': 'Payment rejected',
                'payment_id': payment.id
            })
    
    @action(detail=False, methods=['post'])
    def process_payment(self, request):
        """Mark payment as processed (superadmin only)"""
        if not request.user.is_superuser:
            return Response({'error': 'Only super admins can process payments'}, status=status.HTTP_403_FORBIDDEN)
        
        payment_id = request.data.get('payment_id')
        
        try:
            payment = TenantPayment.objects.get(pk=payment_id)
        except TenantPayment.DoesNotExist:
            return Response({'error': 'Payment not found'}, status=status.HTTP_404_NOT_FOUND)
        
        if payment.status != 'approved':
            return Response({'error': 'Only approved payments can be processed'}, status=status.HTTP_400_BAD_REQUEST)
        
        payment.status = 'processed'
        payment.notes = request.data.get('notes', '')
        payment.save()
        
        return Response({
            'status': 'Payment processed',
            'payment_id': payment.id
        })


@api_view(['GET'])
@permission_classes([IsSuperAdminUser])
def pending_payments_list(request):
    """Get list of pending payments for approval"""
    payments = TenantPayment.objects.filter(
        status='pending'
    ).select_related('tenant', 'subscription').order_by('-payment_date')
    
    return Response(TenantPaymentSerializer(payments, many=True).data)

def _user_has_tenant_access(user, tenant) -> bool:
    """True if the user is a superuser or holds an active
    UserTenantRole on the given tenant. Used to gate tenant-scoped
    APIs so a stray X-Tenant-Domain header from a user without a
    role on that tenant can't read or mutate that tenant's settings.
    """
    if user is None or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    if tenant is None:
        return False
    return UserTenantRole.objects.filter(
        user=user, tenant=tenant, is_active=True,
    ).exists()


@api_view(['GET', 'PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def tenant_settings_api(request):
    """Get or update tenant-level settings (timezone, locale, fiscal year, etc.)."""
    tenant = getattr(request, 'tenant', None)
    if not tenant:
        return Response({'error': 'No tenant context'}, status=400)

    # Reject requests where the authenticated user has no role on the
    # tenant resolved by middleware (X-Tenant-Domain header). The
    # middleware sets ``request.tenant`` from the header alone — it
    # doesn't verify the user actually belongs to that tenant. Without
    # this gate any authenticated user could read or mutate any
    # tenant's settings just by changing the header.
    if not _user_has_tenant_access(request.user, tenant):
        return Response(
            {'error': 'You do not have access to this tenant.'},
            status=403,
        )

    if request.method == 'GET':
        sub = getattr(tenant, 'subscription', None)
        modules = get_tenant_settings(tenant)
        return Response({
            'tenant_id': tenant.id,
            'tenant_name': tenant.name,
            'schema_name': tenant.schema_name,
            'plan': sub.plan.name if sub and sub.plan else None,
            'status': sub.status if sub else 'no_subscription',
            'start_date': sub.start_date if sub else None,
            'end_date': sub.end_date if sub else None,
            'modules': modules,
        })

    # PUT/PATCH - update tenant name (only for admin roles)
    if 'name' in request.data:
        tenant.name = request.data['name']
        tenant.save(update_fields=['name'])

    return Response({'status': 'updated'})


@api_view(['GET', 'PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def tenant_company_api(request):
    """Get or update tenant company information."""
    tenant = getattr(request, 'tenant', None)
    if not tenant:
        return Response({})

    # Same gate as tenant_settings_api / tenant_branding_api: an
    # authenticated user with no UserTenantRole on this tenant cannot
    # read or mutate its company info.
    if not _user_has_tenant_access(request.user, tenant):
        return Response(
            {'error': 'You do not have access to this tenant.'},
            status=403,
        )

    if request.method == 'GET':
        return Response({
            'name': tenant.name,
            'schema_name': tenant.schema_name,
            'created_on': tenant.created_on,
            'domains': list(tenant.domains.values_list('domain', flat=True)),
        })

    # PUT/PATCH - update company name
    if 'name' in request.data:
        tenant.name = request.data['name']
        tenant.save(update_fields=['name'])
    return Response({'name': tenant.name})


@api_view(['GET'])
@authentication_classes_decorator([])
@permission_classes([AllowAny])
def tenant_public_branding_api(request):
    """Public endpoint — returns tenant name and logo for the login page.

    No authentication required. The tenant is resolved by django-tenants
    middleware from the request hostname. Only exposes name, tagline, and
    logo — no sensitive data.
    """
    tenant = getattr(request, 'tenant', None)
    if not tenant or getattr(tenant, 'schema_name', 'public') == 'public':
        return Response({'name': 'QUOT ERP', 'tagline': '', 'logo': None})

    return Response({
        'name': tenant.name,
        'tagline': tenant.tagline,
        'logo': request.build_absolute_uri(tenant.logo.url) if tenant.logo else None,
    })


@api_view(['GET', 'PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
@parser_classes_decorator([MultiPartParser, FormParser])
def tenant_branding_api(request):
    """Get or update tenant branding and contact information."""
    tenant = getattr(request, 'tenant', None)
    if not tenant:
        return Response({'error': 'No tenant context'}, status=400)

    # Same gate as tenant_settings_api: an authenticated user with no
    # UserTenantRole on this tenant cannot view or mutate its branding.
    if not _user_has_tenant_access(request.user, tenant):
        return Response(
            {'error': 'You do not have access to this tenant.'},
            status=403,
        )

    if request.method == 'GET':
        return Response({
            'name': tenant.name,
            'tagline': tenant.tagline,
            'logo': request.build_absolute_uri(tenant.logo.url) if tenant.logo else None,
            'address': tenant.address,
            'city': tenant.city,
            'state': tenant.state,
            'country': tenant.country,
            'postal_code': tenant.postal_code,
            'phone': tenant.phone,
            'email': tenant.email,
            'website': tenant.website,
        })

    # PUT/PATCH — update branding fields
    data = request.data
    update_fields = []
    text_fields = [
        'name', 'tagline', 'address', 'city', 'state',
        'country', 'postal_code', 'phone', 'email', 'website',
    ]
    for field in text_fields:
        if field in data:
            setattr(tenant, field, data[field])
            update_fields.append(field)

    # Handle logo file upload
    if 'logo' in request.FILES:
        # Delete old logo file if it exists
        if tenant.logo:
            tenant.logo.delete(save=False)
        tenant.logo = request.FILES['logo']
        update_fields.append('logo')
    elif data.get('logo') == '' or data.get('remove_logo') == 'true':
        # Explicit removal
        if tenant.logo:
            tenant.logo.delete(save=False)
        tenant.logo = None
        update_fields.append('logo')

    if update_fields:
        tenant.save(update_fields=update_fields)

    return Response({
        'name': tenant.name,
        'tagline': tenant.tagline,
        'logo': request.build_absolute_uri(tenant.logo.url) if tenant.logo else None,
        'address': tenant.address,
        'city': tenant.city,
        'state': tenant.state,
        'country': tenant.country,
        'postal_code': tenant.postal_code,
        'phone': tenant.phone,
        'email': tenant.email,
        'website': tenant.website,
    })


@api_view(['GET', 'PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def tenant_email_api(request):
    """Get or update tenant email/SMTP settings.

    SMTP credentials are high-value — an attacker who could mutate
    them could redirect tenant outbound mail through their own server
    and harvest password resets / receipts. Gate behind the same
    UserTenantRole check used on the rest of the tenant-config APIs.
    """
    tenant = getattr(request, 'tenant', None)
    if not tenant:
        return Response({'provider': 'smtp'})

    if not _user_has_tenant_access(request.user, tenant):
        return Response(
            {'error': 'You do not have access to this tenant.'},
            status=403,
        )

    from superadmin.models import TenantSMTPConfig

    if request.method == 'GET':
        try:
            smtp = TenantSMTPConfig.objects.get(tenant=tenant)
            return Response({
                'provider': 'smtp',
                'smtp_host': smtp.smtp_host,
                'smtp_port': smtp.smtp_port,
                'smtp_username': smtp.smtp_username,
                'smtp_use_tls': smtp.smtp_use_tls,
                'smtp_use_ssl': smtp.smtp_use_ssl,
                'smtp_from_email': smtp.smtp_from_email,
                'smtp_from_name': smtp.smtp_from_name,
                'reply_to_email': smtp.reply_to_email,
                'is_active': smtp.is_active,
                'is_verified': smtp.is_verified,
            })
        except TenantSMTPConfig.DoesNotExist:
            return Response({'provider': 'smtp', 'configured': False})

    # PUT/PATCH - update SMTP settings
    data = request.data
    smtp, _ = TenantSMTPConfig.objects.update_or_create(
        tenant=tenant,
        defaults={
            'smtp_host': data.get('smtp_host', ''),
            'smtp_port': data.get('smtp_port', 587),
            'smtp_username': data.get('smtp_username', ''),
            'smtp_password': data.get('smtp_password', ''),
            'smtp_use_tls': data.get('smtp_use_tls', True),
            'smtp_use_ssl': data.get('smtp_use_ssl', False),
            'smtp_from_email': data.get('smtp_from_email', ''),
            'smtp_from_name': data.get('smtp_from_name', ''),
            'reply_to_email': data.get('reply_to_email', ''),
        },
    )
    return Response({'status': 'updated'})


@api_view(['GET'])  # was ['GET', 'PUT', 'PATCH'] — implementation is read-only.
@permission_classes([IsAuthenticated])
def tenant_payment_methods_api(request):
    """Get accepted payment methods for the tenant's subscription payments.

    The list is currently a static catalogue (no DB write), so PUT/PATCH
    were dead verbs that mis-suggested a settings endpoint. Restricted
    to GET to keep the contract honest.
    """
    return Response([
        {'method': 'bank_transfer', 'label': 'Bank Transfer', 'enabled': True},
        {'method': 'bank_deposit', 'label': 'Bank Deposit', 'enabled': True},
        {'method': 'mobile_money', 'label': 'Mobile Money', 'enabled': True},
        {'method': 'cheque', 'label': 'Cheque', 'enabled': True},
    ])

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def tenant_modules_api(request):
    """Get enabled modules for the current tenant"""
    if hasattr(request, 'tenant') and request.tenant and request.tenant.schema_name != 'public':
        # Tenant request is already routed into the tenant's own schema context —
        # query PerTenantModule directly (no schema_context switch needed).
        configured = {m.module_name: m.is_active for m in PerTenantModule.objects.all()}
        # Pad with False for any module not yet in the tenant's table
        all_modules = {key: configured.get(key, False) for key, _, _ in AVAILABLE_MODULES}
        return Response({
            "enabled_modules": all_modules,
            "dimensions_enabled": all_modules.get('dimensions', False),
        })
    return Response({"enabled_modules": {}, "dimensions_enabled": False})


# ─── Government Configuration (Quot PSE) ────────────────────────────

# NBS state code -> (state_name, zone_code) lookup
_NBS_STATES = {
    '01': ('Abia', '4'), '02': ('Adamawa', '2'), '03': ('Akwa Ibom', '5'),
    '04': ('Anambra', '4'), '05': ('Bauchi', '2'), '06': ('Bayelsa', '5'),
    '07': ('Benue', '1'), '08': ('Borno', '2'), '09': ('Cross River', '5'),
    '10': ('Delta', '5'), '11': ('Ebonyi', '4'), '12': ('Edo', '5'),
    '13': ('Enugu', '4'), '14': ('Jigawa', '3'), '15': ('Kogi', '1'),
    '16': ('Kaduna', '3'), '17': ('Kano', '3'), '18': ('Kwara', '1'),
    '19': ('Katsina', '3'), '20': ('Kebbi', '3'), '21': ('Ekiti', '6'),
    '22': ('Nasarawa', '1'), '23': ('Lagos', '6'), '25': ('Niger', '1'),
    '26': ('Ogun', '6'), '27': ('Imo', '4'), '28': ('Ondo', '6'),
    '29': ('Osun', '6'), '30': ('Oyo', '6'), '31': ('Sokoto', '3'),
    '32': ('Rivers', '5'), '33': ('Taraba', '2'), '35': ('Yobe', '2'),
    '36': ('Zamfara', '3'), '37': ('FCT Abuja', '1'),
}


def _is_tenant_admin(user, tenant) -> bool:
    """True if the user holds an ``admin`` (or ``senior_manager``) role
    on the given tenant. Used to gate destructive tenant-wide actions
    (configure_government, isolation_mode, etc.) without forcing the
    operator to be a platform-level superuser."""
    if user is None or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    if tenant is None:
        return False
    return UserTenantRole.objects.filter(
        user=user, tenant=tenant, is_active=True,
        role__in=('admin', 'senior_manager'),
    ).exists()


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def configure_government(request):
    """
    GET: Returns current government configuration + list of available states.
    POST: Configure the tenant's government tier, state, and LGA.
          Triggers NCoA seeding for the selected state/tier.

    POST is restricted to tenant admins (or superusers). The endpoint
    re-seeds the entire Chart of Accounts for the tenant — letting any
    authenticated user trigger this would let any tenant member wipe
    and rebuild the live ledger.
    """
    tenant = getattr(request, 'tenant', None)
    if not tenant:
        return Response({'error': 'No tenant context'}, status=400)

    # Authorisation gate for the destructive POST path.
    if request.method == 'POST':
        if not (request.user.is_superuser or _is_tenant_admin(request.user, tenant)):
            return Response(
                {'error': (
                    'configure_government is restricted to tenant administrators. '
                    'It re-seeds the Chart of Accounts and other tenant defaults; '
                    'unauthorised use would corrupt your live ledger.'
                )},
                status=403,
            )

    if request.method == 'GET':
        states = [
            {'code': code, 'name': name, 'zone': zone}
            for code, (name, zone) in sorted(_NBS_STATES.items())
        ]
        return Response({
            'current': {
                'government_tier': tenant.government_tier,
                'state_nbs_code': tenant.state_nbs_code,
                'state_name': tenant.state_name,
                'lga_code': tenant.lga_code,
                'lga_name': tenant.lga_name,
                'is_configured': bool(tenant.government_tier and tenant.state_nbs_code),
            },
            'available_states': states,
            'tiers': [
                {'value': 'STATE', 'label': 'State Government'},
                {'value': 'LGA', 'label': 'Local Government Area'},
            ],
        })

    # POST — configure government
    tier = request.data.get('government_tier', '')
    state_code = request.data.get('state_nbs_code', '')
    lga_code = request.data.get('lga_code', '')
    lga_name = request.data.get('lga_name', '')

    if tier not in ('STATE', 'LGA'):
        return Response({'error': 'government_tier must be STATE or LGA'}, status=400)
    if not state_code or state_code not in _NBS_STATES:
        return Response({'error': f'Invalid state_nbs_code: {state_code}'}, status=400)
    if tier == 'LGA' and not lga_code:
        return Response({'error': 'lga_code is required for LGA tier'}, status=400)

    state_name = _NBS_STATES[state_code][0]

    # Update Client record
    tenant.government_tier = tier
    tenant.state_nbs_code = state_code
    tenant.state_name = state_name
    tenant.lga_code = lga_code
    tenant.lga_name = lga_name
    tenant.business_category = 'government'
    tenant.save(update_fields=[
        'government_tier', 'state_nbs_code', 'state_name',
        'lga_code', 'lga_name', 'business_category',
    ])

    # Trigger NCoA seeding in the tenant's schema
    from django.core.management import call_command
    from django.db import connection as db_connection
    try:
        db_connection.set_tenant(tenant)
        call_command('seed_ncoa_economic')
        call_command('seed_ncoa', '--segment', 'functional')
        call_command('seed_ncoa', '--segment', 'fund')
        call_command('seed_ncoa', '--segment', 'geo')
        call_command('seed_ncoa', '--segment', 'administrative')
        call_command('seed_ncoa', '--segment', 'programme')
        try:
            call_command('seed_ncoa_lgas', '--state-code', state_code)
        except Exception:
            pass  # LGA data may not be available for all states
        call_command('seed_ncoa_state_mdas', '--tier', tier)
        call_command('seed_procurement_thresholds')
        call_command('seed_nigeria_payroll')
        call_command('seed_revenue_heads')
        call_command('seed_ncoa_as_coa')
        call_command('seed_ncoa_as_dimensions')

        seeded = True
    except Exception as e:
        seeded = False
        # Log the full exception server-side; return only the safe
        # operator-facing message to the client. ``str(exc)`` can leak
        # SQL fragments / file paths / library version hints in 500s
        # — never the right thing to return to a partially-trusted
        # caller. Operators get the exception in logs; clients get a
        # bounded message + a correlation-friendly tier/state
        # echo so they can re-try with corrected inputs.
        import logging as _logging
        _logging.getLogger(__name__).exception(
            'configure_government seed failed for tier=%s state=%s',
            tier, state_name,
        )
        return Response({
            'status': 'configured_with_errors',
            'error': (
                'Government setup partially failed during seeding. '
                'The tenant is configured but Chart-of-Accounts seeding '
                'did not complete. Contact your platform administrator '
                'to inspect the logs.'
            ),
            'government_tier': tier,
            'state_name': state_name,
        }, status=500)

    return Response({
        'status': 'configured',
        'government_tier': tier,
        'state_name': state_name,
        'state_nbs_code': state_code,
        'lga_code': lga_code,
        'lga_name': lga_name,
        'seeded': seeded,
    })


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def isolation_mode(request):
    """
    GET: Returns current MDA isolation mode.
    POST: Toggle between UNIFIED and SEPARATED. Restricted to tenant
          administrators — flipping from SEPARATED to UNIFIED exposes
          every MDA's transactions to every user in the tenant
          immediately, so it is a tenant-wide privacy event.
    """
    from django_tenants.utils import schema_context
    with schema_context('public'):
        tenant = Client.objects.get(pk=request.tenant.pk)

    if request.method == 'GET':
        return Response({
            'mda_isolation_mode': tenant.mda_isolation_mode,
        })

    # Authorisation gate for the privacy-event POST path.
    if not (request.user.is_superuser or _is_tenant_admin(request.user, tenant)):
        return Response(
            {'error': (
                'isolation_mode is restricted to tenant administrators. '
                'Switching MDA isolation affects which users can see which '
                'MDA records — only an admin should make that change.'
            )},
            status=403,
        )

    mode = request.data.get('mda_isolation_mode', '')
    if mode not in ('UNIFIED', 'SEPARATED'):
        return Response(
            {'error': 'mda_isolation_mode must be UNIFIED or SEPARATED'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    with schema_context('public'):
        tenant.mda_isolation_mode = mode
        tenant.save(update_fields=['mda_isolation_mode'])

    return Response({
        'mda_isolation_mode': tenant.mda_isolation_mode,
        'message': f'Isolation mode set to {mode}',
    })
