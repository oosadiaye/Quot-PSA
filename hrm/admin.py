from django.contrib import admin
from .models import (
    Department, Position, Employee, LeaveType, LeaveRequest, LeaveBalance, Attendance, Holiday,
    JobPost, Candidate, Interview, OnboardingTask, OnboardingProgress,
    SalaryStructure, SalaryComponent, SalaryStructureTemplate, PayrollPeriod, PayrollRun, PayrollLine,
    PayrollEarning, PayrollDeduction, Payslip,
    PerformanceCycle, PerformanceGoal, PerformanceReview, CompetencyRating, Competency, Promotion,
    TrainingProgram, TrainingEnrollment, Skill, EmployeeSkill, TrainingPlan, TrainingPlanLine,
    Policy, PolicyAcknowledgement, ComplianceRecord, ComplianceTask, AuditLog,
    ExitRequest, ExitInterview, ExitClearance, FinalSettlement, ExperienceCertificate, AssetReturn
)


# =============================================================================
# ORGANIZATION
# =============================================================================

@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'manager', 'parent', 'is_active']
    list_filter = ['is_active']
    search_fields = ['name', 'code']


@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
    list_display = ['title', 'code', 'department', 'grade', 'is_active']
    list_filter = ['grade', 'is_active', 'department']
    search_fields = ['title', 'code']


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ['employee_number', 'user', 'department', 'position', 'employee_type', 'status', 'hire_date']
    list_filter = ['status', 'employee_type', 'department']
    search_fields = ['employee_number', 'user__first_name', 'user__last_name']
    raw_id_fields = ['user', 'supervisor']


# =============================================================================
# LEAVE MANAGEMENT
# =============================================================================

@admin.register(LeaveType)
class LeaveTypeAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'max_days_per_year', 'is_paid', 'requires_approval', 'is_active']
    list_filter = ['is_paid', 'requires_approval', 'is_active']
    search_fields = ['name', 'code']


@admin.register(LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    list_display = ['employee', 'leave_type', 'start_date', 'end_date', 'total_days', 'status']
    list_filter = ['status', 'leave_type']
    search_fields = ['employee__user__first_name', 'employee__user__last_name', 'employee__employee_number']
    raw_id_fields = ['employee', 'approved_by']


@admin.register(LeaveBalance)
class LeaveBalanceAdmin(admin.ModelAdmin):
    list_display = ['employee', 'leave_type', 'year', 'allocated', 'taken', 'balance']
    list_filter = ['year', 'leave_type']
    search_fields = ['employee__user__first_name', 'employee__user__last_name']


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ['employee', 'date', 'status', 'check_in', 'check_out', 'work_hours']
    list_filter = ['status', 'date']
    search_fields = ['employee__user__first_name', 'employee__user__last_name']
    date_hierarchy = 'date'


@admin.register(Holiday)
class HolidayAdmin(admin.ModelAdmin):
    list_display = ['name', 'date', 'is_recurring']
    list_filter = ['is_recurring']
    search_fields = ['name']
    date_hierarchy = 'date'


# =============================================================================
# RECRUITMENT & ONBOARDING
# =============================================================================

class InterviewInline(admin.TabularInline):
    model = Interview
    extra = 0
    fields = ['interviewer', 'scheduled_date', 'interview_type', 'status', 'rating']


@admin.register(JobPost)
class JobPostAdmin(admin.ModelAdmin):
    list_display = ['title', 'department', 'status', 'publish_date', 'close_date']
    list_filter = ['status', 'department']
    search_fields = ['title', 'reference_number']


@admin.register(Candidate)
class CandidateAdmin(admin.ModelAdmin):
    list_display = ['first_name', 'last_name', 'email', 'job_post', 'status']
    list_filter = ['status', 'job_post']
    search_fields = ['first_name', 'last_name', 'email']
    inlines = [InterviewInline]


@admin.register(Interview)
class InterviewAdmin(admin.ModelAdmin):
    list_display = ['candidate', 'interviewer', 'scheduled_date', 'interview_type', 'status', 'rating']
    list_filter = ['status', 'interview_type']
    search_fields = ['candidate__first_name', 'candidate__last_name']
    raw_id_fields = ['candidate']


@admin.register(OnboardingTask)
class OnboardingTaskAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'is_required', 'is_active']
    list_filter = ['category', 'is_required', 'is_active']
    search_fields = ['name']


@admin.register(OnboardingProgress)
class OnboardingProgressAdmin(admin.ModelAdmin):
    list_display = ['employee', 'task', 'status', 'due_date', 'completed_date']
    list_filter = ['status']
    search_fields = ['employee__user__first_name', 'employee__user__last_name']
    raw_id_fields = ['employee']


# =============================================================================
# PAYROLL
# =============================================================================

class SalaryStructureTemplateInline(admin.TabularInline):
    model = SalaryStructureTemplate
    extra = 1
    fields = ['component', 'is_active']


@admin.register(SalaryStructure)
class SalaryStructureAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'is_active']
    list_filter = ['is_active']
    search_fields = ['name', 'code']
    inlines = [SalaryStructureTemplateInline]


@admin.register(SalaryComponent)
class SalaryComponentAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'component_type', 'calculation_type', 'value', 'percentage_of_basic', 'is_taxable', 'is_pensionable', 'is_active']
    list_filter = ['component_type', 'calculation_type', 'is_taxable', 'is_pensionable', 'is_active']
    search_fields = ['name', 'code']


@admin.register(PayrollPeriod)
class PayrollPeriodAdmin(admin.ModelAdmin):
    list_display = ['period_type', 'start_date', 'end_date', 'payment_date', 'status', 'is_active']
    list_filter = ['period_type', 'status', 'is_active']
    date_hierarchy = 'start_date'


class PayrollLineInline(admin.TabularInline):
    model = PayrollLine
    extra = 0
    fields = ['employee', 'basic_salary', 'gross_salary', 'total_deductions', 'net_salary', 'working_days', 'days_worked']
    readonly_fields = ['employee', 'basic_salary', 'gross_salary', 'total_deductions', 'net_salary']
    show_change_link = True


@admin.register(PayrollRun)
class PayrollRunAdmin(admin.ModelAdmin):
    list_display = ['run_number', 'period', 'status', 'total_gross', 'total_deductions', 'total_net', 'processed_by', 'approved_by']
    list_filter = ['status', 'period']
    search_fields = ['run_number']
    raw_id_fields = ['processed_by', 'approved_by']
    inlines = [PayrollLineInline]


class PayrollEarningInline(admin.TabularInline):
    model = PayrollEarning
    extra = 0
    fields = ['component', 'amount']


class PayrollDeductionInline(admin.TabularInline):
    model = PayrollDeduction
    extra = 0
    fields = ['component', 'amount']


@admin.register(PayrollLine)
class PayrollLineAdmin(admin.ModelAdmin):
    list_display = ['payroll_run', 'employee', 'basic_salary', 'gross_salary', 'total_deductions', 'net_salary', 'tax_deduction', 'pension_deduction']
    list_filter = ['payroll_run']
    search_fields = ['employee__user__first_name', 'employee__user__last_name', 'employee__employee_number']
    raw_id_fields = ['employee']
    inlines = [PayrollEarningInline, PayrollDeductionInline]


@admin.register(Payslip)
class PayslipAdmin(admin.ModelAdmin):
    list_display = ['payroll_line', 'status']
    list_filter = ['status']


# =============================================================================
# PERFORMANCE
# =============================================================================

class PerformanceGoalInline(admin.TabularInline):
    model = PerformanceGoal
    extra = 0
    fields = ['employee', 'title', 'weight', 'status']


class CompetencyRatingInline(admin.TabularInline):
    model = CompetencyRating
    extra = 0
    fields = ['competency', 'rating', 'comments']


@admin.register(PerformanceCycle)
class PerformanceCycleAdmin(admin.ModelAdmin):
    list_display = ['name', 'start_date', 'end_date', 'status']
    list_filter = ['status']
    search_fields = ['name']
    inlines = [PerformanceGoalInline]


@admin.register(PerformanceGoal)
class PerformanceGoalAdmin(admin.ModelAdmin):
    list_display = ['title', 'employee', 'cycle', 'weight', 'status']
    list_filter = ['status', 'cycle']
    search_fields = ['title', 'employee__user__first_name']
    raw_id_fields = ['employee']


@admin.register(PerformanceReview)
class PerformanceReviewAdmin(admin.ModelAdmin):
    list_display = ['employee', 'cycle', 'reviewer', 'rating', 'status']
    list_filter = ['status', 'cycle', 'rating']
    search_fields = ['employee__user__first_name', 'employee__user__last_name']
    raw_id_fields = ['employee', 'reviewer']
    inlines = [CompetencyRatingInline]


@admin.register(Competency)
class CompetencyAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'is_active']
    list_filter = ['category', 'is_active']
    search_fields = ['name']


@admin.register(Promotion)
class PromotionAdmin(admin.ModelAdmin):
    list_display = ['employee', 'from_position', 'to_position', 'effective_date', 'status']
    list_filter = ['status']
    search_fields = ['employee__user__first_name', 'employee__user__last_name']
    raw_id_fields = ['employee']


# =============================================================================
# TRAINING
# =============================================================================

class TrainingEnrollmentInline(admin.TabularInline):
    model = TrainingEnrollment
    extra = 0
    fields = ['employee', 'status', 'completion_date', 'score']
    raw_id_fields = ['employee']


class TrainingPlanLineInline(admin.TabularInline):
    model = TrainingPlanLine
    extra = 0
    fields = ['program', 'sequence', 'due_date', 'completed']


@admin.register(TrainingProgram)
class TrainingProgramAdmin(admin.ModelAdmin):
    list_display = ['name', 'program_type', 'department', 'start_date', 'end_date', 'max_participants', 'is_active']
    list_filter = ['program_type', 'is_active', 'department']
    search_fields = ['name']
    inlines = [TrainingEnrollmentInline]


@admin.register(TrainingEnrollment)
class TrainingEnrollmentAdmin(admin.ModelAdmin):
    list_display = ['employee', 'program', 'status', 'completion_date', 'score']
    list_filter = ['status', 'program']
    search_fields = ['employee__user__first_name', 'employee__user__last_name']
    raw_id_fields = ['employee']


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'is_active']
    list_filter = ['category', 'is_active']
    search_fields = ['name']


@admin.register(EmployeeSkill)
class EmployeeSkillAdmin(admin.ModelAdmin):
    list_display = ['employee', 'skill', 'proficiency_level']
    list_filter = ['proficiency_level', 'skill']
    search_fields = ['employee__user__first_name', 'employee__user__last_name']
    raw_id_fields = ['employee']


@admin.register(TrainingPlan)
class TrainingPlanAdmin(admin.ModelAdmin):
    list_display = ['name', 'employee', 'start_date', 'end_date', 'status']
    list_filter = ['status', 'is_active']
    search_fields = ['name', 'employee__user__first_name', 'employee__user__last_name']
    raw_id_fields = ['employee']
    inlines = [TrainingPlanLineInline]


# =============================================================================
# COMPLIANCE & POLICIES
# =============================================================================

class PolicyAcknowledgementInline(admin.TabularInline):
    model = PolicyAcknowledgement
    extra = 0
    fields = ['employee', 'status', 'acknowledged_date']
    raw_id_fields = ['employee']


class ComplianceTaskInline(admin.TabularInline):
    model = ComplianceTask
    extra = 0
    fields = ['title', 'assigned_to', 'due_date', 'status']
    raw_id_fields = ['assigned_to']


@admin.register(Policy)
class PolicyAdmin(admin.ModelAdmin):
    list_display = ['title', 'category', 'effective_date', 'version', 'is_active']
    list_filter = ['category', 'is_active']
    search_fields = ['title']
    inlines = [PolicyAcknowledgementInline]


@admin.register(PolicyAcknowledgement)
class PolicyAcknowledgementAdmin(admin.ModelAdmin):
    list_display = ['policy', 'employee', 'status', 'acknowledged_date']
    list_filter = ['status', 'policy']
    search_fields = ['employee__user__first_name', 'employee__user__last_name']
    raw_id_fields = ['employee']


@admin.register(ComplianceRecord)
class ComplianceRecordAdmin(admin.ModelAdmin):
    list_display = ['title', 'code', 'compliance_type', 'status', 'effective_date', 'next_audit_date']
    list_filter = ['status', 'compliance_type']
    search_fields = ['title', 'code']
    inlines = [ComplianceTaskInline]


@admin.register(ComplianceTask)
class ComplianceTaskAdmin(admin.ModelAdmin):
    list_display = ['title', 'compliance_record', 'assigned_to', 'due_date', 'status']
    list_filter = ['status']
    search_fields = ['title']
    raw_id_fields = ['assigned_to']


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ['action_type', 'module', 'object_repr', 'user', 'timestamp']
    list_filter = ['action_type', 'module']
    search_fields = ['module', 'object_repr']
    readonly_fields = ['action_type', 'module', 'object_id', 'object_repr', 'user', 'timestamp', 'changes', 'ip_address']
    date_hierarchy = 'timestamp'


# =============================================================================
# EXIT MANAGEMENT
# =============================================================================

class ExitInterviewInline(admin.StackedInline):
    model = ExitInterview
    extra = 0


class ExitClearanceInline(admin.TabularInline):
    model = ExitClearance
    extra = 0
    fields = ['category', 'department', 'status', 'assigned_to', 'completed_by', 'completed_date']
    raw_id_fields = ['assigned_to', 'completed_by']


class AssetReturnInline(admin.TabularInline):
    model = AssetReturn
    extra = 0
    fields = ['asset_name', 'asset_tag', 'status', 'return_actual_date']


@admin.register(ExitRequest)
class ExitRequestAdmin(admin.ModelAdmin):
    list_display = ['employee', 'exit_type', 'requested_date', 'last_working_date', 'status']
    list_filter = ['status', 'exit_type']
    search_fields = ['employee__user__first_name', 'employee__user__last_name']
    raw_id_fields = ['employee', 'approved_by']
    inlines = [ExitInterviewInline, ExitClearanceInline, AssetReturnInline]


@admin.register(ExitInterview)
class ExitInterviewAdmin(admin.ModelAdmin):
    list_display = ['exit_request', 'interviewer', 'scheduled_date', 'status', 'satisfaction_rating']
    list_filter = ['status']
    raw_id_fields = ['interviewer']


@admin.register(ExitClearance)
class ExitClearanceAdmin(admin.ModelAdmin):
    list_display = ['exit_request', 'category', 'department', 'status', 'completed_by', 'completed_date']
    list_filter = ['status', 'category']
    raw_id_fields = ['assigned_to', 'completed_by']


@admin.register(FinalSettlement)
class FinalSettlementAdmin(admin.ModelAdmin):
    list_display = ['exit_request', 'total_payable', 'total_deductions', 'status', 'payment_date']
    list_filter = ['status']


@admin.register(ExperienceCertificate)
class ExperienceCertificateAdmin(admin.ModelAdmin):
    list_display = ['exit_request', 'certificate_number', 'employee_name', 'issue_date', 'conduct', 'is_issued']
    list_filter = ['conduct', 'is_issued']
    search_fields = ['certificate_number', 'employee_name']


@admin.register(AssetReturn)
class AssetReturnAdmin(admin.ModelAdmin):
    list_display = ['exit_request', 'asset_name', 'asset_tag', 'status', 'return_actual_date']
    list_filter = ['status']
