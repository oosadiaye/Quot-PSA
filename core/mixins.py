"""
Organization-aware ViewSet mixins — Quot PSE

Provides automatic queryset filtering by the active organization
when the tenant is in SEPARATED MDA isolation mode.
"""
from rest_framework.permissions import BasePermission, SAFE_METHODS


class OrganizationFilterMixin:
    """
    Auto-filters ViewSet querysets by the active organization.

    In UNIFIED mode: no filtering — all records returned.
    In SEPARATED mode:
    - MDA org: filter to own data via ``org_filter_field`` or
      ``org_filter_admin_field``
    - Oversight org (Budget/Finance/Audit): no filter (cross-MDA read)
    - No org selected: empty queryset (safety net)

    Subclass attributes:
    - ``org_filter_field``       — FK field name to ``accounting.MDA``
                                   (e.g. 'mda')
    - ``org_filter_admin_field`` — FK field name to
                                   ``accounting.AdministrativeSegment``
                                   (e.g. 'administrative', 'collecting_mda')

    If both are None, no filtering is applied (for reference/config data).
    """

    org_filter_field: str | None = None
    org_filter_admin_field: str | None = None

    def get_queryset(self):
        qs = super().get_queryset()
        request = getattr(self, 'request', None)
        if not request:
            return qs

        # UNIFIED mode → no filtering
        if getattr(request, 'mda_isolation_mode', 'UNIFIED') != 'SEPARATED':
            return qs

        org = getattr(request, 'organization', None)
        if not org:
            # No org in SEPARATED mode = see nothing (safety net)
            return qs.none()

        # Oversight orgs see everything
        if org.has_cross_mda_read:
            return qs

        # Standard MDA → filter to own data
        if self.org_filter_admin_field and org.administrative_segment_id:
            return qs.filter(**{
                f'{self.org_filter_admin_field}_id': org.administrative_segment_id,
            })
        elif self.org_filter_field and org.legacy_mda_id:
            return qs.filter(**{
                f'{self.org_filter_field}_id': org.legacy_mda_id,
            })

        return qs


class OrganizationPermission(BasePermission):
    """
    DRF permission enforcing org_role write restrictions.

    Works alongside module-level ``core.Role`` permission checks:
    - AUDIT_AUTHORITY → read-only (safe methods only)
    - BUDGET_AUTHORITY → can write only to budget module
    - FINANCE_AUTHORITY → can write to finance/treasury, view-only budget
    - MDA → normal module permissions apply
    """

    # Modules the BUDGET_AUTHORITY can write to
    BUDGET_WRITE_MODULES = {'budget', 'workflow'}

    # Modules the FINANCE_AUTHORITY can write to
    FINANCE_WRITE_MODULES = {
        'accounting', 'treasury', 'revenue', 'hrm', 'workflow',
    }

    def has_permission(self, request, view) -> bool:
        org = getattr(request, 'organization', None)
        if not org:
            return True  # UNIFIED mode or no org context

        # Audit authority = strictly read-only
        if org.org_role == 'AUDIT_AUTHORITY':
            return request.method in SAFE_METHODS

        # Get module name from view (if declared)
        module = getattr(view, 'module_name', None)
        if not module:
            return True  # No module declared = no restriction

        # Budget authority can only write to budget modules
        if org.org_role == 'BUDGET_AUTHORITY':
            if request.method not in SAFE_METHODS:
                return module in self.BUDGET_WRITE_MODULES

        # Finance authority can only write to finance modules
        if org.org_role == 'FINANCE_AUTHORITY':
            if request.method not in SAFE_METHODS:
                return module in self.FINANCE_WRITE_MODULES

        return True
