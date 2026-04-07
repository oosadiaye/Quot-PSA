import logging

from django.contrib.auth.models import User, Group
from django_tenants.utils import schema_context

logger = logging.getLogger('dtsg')


class UserProvisioningService:
    @staticmethod
    def check_subscription_limit(tenant):
        """Check whether the tenant has reached its max_users limit.

        Returns None if within limits, or an error string if the limit is reached.
        """
        from tenants.models import UserTenantRole, TenantSubscription

        with schema_context('public'):
            try:
                sub = TenantSubscription.objects.select_related('plan').get(tenant=tenant)
                if sub.plan and sub.plan.max_users:
                    current_users = UserTenantRole.objects.filter(
                        tenant=tenant, is_active=True
                    ).count()
                    if current_users >= sub.plan.max_users:
                        return (
                            f'User limit reached ({sub.plan.max_users} users). '
                            f'Upgrade your plan to add more users.'
                        )
            except TenantSubscription.DoesNotExist:
                pass  # No subscription — allow creation

        return None

    @staticmethod
    def provision_user(tenant, user_data, role, group_ids=None, link_employee=False):
        """Create a Django user, assign them to the tenant, optionally create an HRM employee.

        Returns the created UserTenantRole instance.
        """
        from tenants.models import UserTenantRole

        with schema_context('public'):
            user = User.objects.create_user(
                username=user_data['username'],
                email=user_data['email'],
                password=user_data['password'],
                first_name=user_data.get('first_name', ''),
                last_name=user_data.get('last_name', ''),
            )

        # Create tenant role
        utr = UserTenantRole.objects.create(
            user=user, tenant=tenant,
            role=role, is_active=True,
        )

        # Assign groups
        if group_ids:
            groups = Group.objects.filter(id__in=group_ids)
            utr.groups.set(groups)
        else:
            UserProvisioningService._auto_assign_groups(utr)

        # Optionally link HRM employee
        if link_employee:
            UserProvisioningService._create_employee(user, tenant)

        return utr

    @staticmethod
    def assign_role(user, tenant, role, group_ids=None):
        """Change a user's role for a given tenant and optionally reassign groups.

        Returns the updated UserTenantRole instance.
        """
        from tenants.models import UserTenantRole
        from core.permissions import invalidate_permission_cache

        utr = UserTenantRole.objects.get(user=user, tenant=tenant)
        utr.role = role
        utr.save()

        if group_ids:
            groups = Group.objects.filter(id__in=group_ids)
            utr.groups.set(groups)
        else:
            UserProvisioningService._auto_assign_groups(utr)

        invalidate_permission_cache(utr.user_id, utr.tenant_id)
        return utr

    # ── Private helpers ────────────────────────────────────────────────

    @staticmethod
    def _auto_assign_groups(utr):
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
                    "user_provisioning: Django Group '%s' not found; "
                    "user %s will not be assigned a role group",
                    group_name, getattr(utr, 'pk', '?'),
                )

    @staticmethod
    def _create_employee(user, tenant):
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
                "user_provisioning: could not create HRM Employee for user %s "
                "(HRM module may not be migrated yet): %s",
                getattr(user, 'pk', '?'), exc,
            )
