from django.contrib import admin
from .models import (
    WorkflowDefinition, WorkflowStep, WorkflowInstance, WorkflowLog,
    ApprovalGroup, ApprovalTemplate, ApprovalTemplateStep,
    Approval, ApprovalStep, ApprovalLog,
)

class WorkflowStepInline(admin.TabularInline):
    model = WorkflowStep
    extra = 1
    ordering = ['sequence']

@admin.register(WorkflowDefinition)
class WorkflowDefinitionAdmin(admin.ModelAdmin):
    list_display = ['name', 'target_model', 'is_active', 'created_at']
    list_filter = ['is_active']
    search_fields = ['name']
    inlines = [WorkflowStepInline]

@admin.register(WorkflowStep)
class WorkflowStepAdmin(admin.ModelAdmin):
    list_display = ['workflow', 'name', 'sequence', 'approver_role']
    list_filter = ['workflow']
    ordering = ['workflow', 'sequence']

@admin.register(WorkflowInstance)
class WorkflowInstanceAdmin(admin.ModelAdmin):
    list_display = ['workflow', 'status', 'current_step', 'content_object']
    list_filter = ['status', 'workflow']
    search_fields = ['workflow__name']

@admin.register(WorkflowLog)
class WorkflowLogAdmin(admin.ModelAdmin):
    list_display = ['instance', 'step', 'action', 'created_at']
    list_filter = ['action']
    ordering = ['-created_at']


# --- Approval System Admin ---

@admin.register(ApprovalGroup)
class ApprovalGroupAdmin(admin.ModelAdmin):
    list_display = ['name', 'min_amount', 'max_amount', 'is_active', 'created_at']
    list_filter = ['is_active']
    search_fields = ['name']
    filter_horizontal = ['members']


class ApprovalTemplateStepInline(admin.TabularInline):
    model = ApprovalTemplateStep
    extra = 1
    ordering = ['sequence']


@admin.register(ApprovalTemplate)
class ApprovalTemplateAdmin(admin.ModelAdmin):
    list_display = ['name', 'content_type', 'approval_type', 'is_active', 'created_at']
    list_filter = ['approval_type', 'is_active']
    search_fields = ['name']
    inlines = [ApprovalTemplateStepInline]


class ApprovalStepInline(admin.TabularInline):
    model = ApprovalStep
    extra = 0
    readonly_fields = ['acted_at']
    ordering = ['step_number']


@admin.register(Approval)
class ApprovalAdmin(admin.ModelAdmin):
    list_display = ['title', 'content_type', 'status', 'current_step', 'total_steps', 'requested_by', 'created_at']
    list_filter = ['status', 'content_type']
    search_fields = ['title']
    inlines = [ApprovalStepInline]


@admin.register(ApprovalLog)
class ApprovalLogAdmin(admin.ModelAdmin):
    list_display = ['approval', 'action', 'user', 'created_at']
    list_filter = ['action']
    search_fields = ['approval__title']
    ordering = ['-created_at']
