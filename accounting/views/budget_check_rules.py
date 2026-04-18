"""CRUD for BudgetCheckRule — tenant-configurable budget-check policy.

Exposes /api/v1/accounting/budget-check-rules/ as a standard DRF
ModelViewSet. Tenant-scoped (lives inside the tenant schema via
django-tenants' routing), so no additional tenant filter is needed.

Permissions: standard RBACPermission gates list / create / update /
delete against the default Django Meta permissions on the model
(view_/add_/change_/delete_budgetcheckrule). Tenant admins get these
by default; other roles must be granted them explicitly.
"""
from rest_framework import viewsets
from accounting.models.budget_check_rules import BudgetCheckRule
from accounting.serializers import BudgetCheckRuleSerializer


class BudgetCheckRuleViewSet(viewsets.ModelViewSet):
    queryset = BudgetCheckRule.objects.all()
    serializer_class = BudgetCheckRuleSerializer
    filterset_fields = ['is_active', 'check_level']

    def get_queryset(self):
        # Return in ascending gl_from order so the UI list looks tidy.
        return BudgetCheckRule.objects.all().order_by('gl_from', '-priority')
