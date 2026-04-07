from django.contrib import admin
from .models import (
    UnifiedBudget, UnifiedBudgetEncumbrance, 
    UnifiedBudgetVariance, UnifiedBudgetAmendment
)

@admin.register(UnifiedBudget)
class UnifiedBudgetAdmin(admin.ModelAdmin):
    list_display = ['budget_code', 'name', 'fiscal_year', 'period_type', 'period_number', 'budget_type', 'status', 'original_amount', 'allocated_amount', 'utilization_rate']
    list_filter = ['fiscal_year', 'period_type', 'budget_type', 'status', 'mda', 'cost_center']
    search_fields = ['budget_code', 'name', 'description']
    readonly_fields = ['created_at', 'updated_at', 'utilization_rate', 'encumbered_amount', 'actual_expended', 'available_amount', 'variance_amount']
    fieldsets = (
        ('Basic Info', {
            'fields': ('budget_code', 'name', 'description', 'budget_type', 'status')
        }),
        ('Period', {
            'fields': ('fiscal_year', 'period_type', 'period_number')
        }),
        ('Dimensions (Public Sector)', {
            'fields': ('mda', 'fund', 'function', 'program', 'geo'),
            'classes': ('collapse',),
            'description': 'Leave empty for private sector budgets'
        }),
        ('Dimensions (Private Sector)', {
            'fields': ('cost_center',),
            'classes': ('collapse',)
        }),
        ('Account', {
            'fields': ('account',)
        }),
        ('Amounts', {
            'fields': ('original_amount', 'revised_amount', 'supplemental_amount', 'allocated_amount')
        }),
        ('Control', {
            'fields': ('control_level', 'enable_encumbrance', 'allow_over_expenditure', 'over_expenditure_limit_percent')
        }),
        ('Tracking', {
            'fields': ('approved_by', 'approved_date', 'closed_date', 'created_by', 'created_at', 'updated_at')
        }),
        ('Calculated', {
            'fields': ('encumbered_amount', 'actual_expended', 'available_amount', 'utilization_rate', 'variance_amount'),
            'classes': ('collapse',)
        }),
    )

@admin.register(UnifiedBudgetEncumbrance)
class UnifiedBudgetEncumbranceAdmin(admin.ModelAdmin):
    list_display = ['reference_type', 'reference_id', 'reference_number', 'budget', 'encumbrance_date', 'amount', 'liquidated_amount', 'remaining_amount', 'status']
    list_filter = ['reference_type', 'status', 'encumbrance_date']
    search_fields = ['reference_number', 'description']

@admin.register(UnifiedBudgetVariance)
class UnifiedBudgetVarianceAdmin(admin.ModelAdmin):
    list_display = ['budget', 'fiscal_year', 'period_type', 'period_number', 'variance_type', 'period_budget', 'period_actual', 'period_variance', 'period_variance_percent']
    list_filter = ['fiscal_year', 'period_type', 'period_number', 'variance_type']

@admin.register(UnifiedBudgetAmendment)
class UnifiedBudgetAmendmentAdmin(admin.ModelAdmin):
    list_display = ['amendment_number', 'amendment_type', 'budget', 'original_amount', 'new_amount', 'change_amount', 'status', 'requested_by', 'approved_by']
    list_filter = ['amendment_type', 'status', 'amendment_number']
    search_fields = ['amendment_number', 'reason']
    readonly_fields = ['created_at', 'approved_date']
