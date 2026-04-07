from rest_framework import serializers
from django.utils import timezone
from datetime import timedelta
from .models import (
    Department, Position, Employee, LeaveType, LeaveRequest, LeaveBalance, Attendance, Holiday,
    JobPost, Candidate, Interview, OnboardingTask, OnboardingProgress,
    SalaryStructure, SalaryComponent, PayrollPeriod, PayrollRun, PayrollLine, PayrollEarning, PayrollDeduction, Payslip,
    PerformanceCycle, PerformanceGoal, PerformanceReview, Competency, CompetencyRating, Promotion,
    TrainingProgram, TrainingEnrollment, Skill, EmployeeSkill, TrainingPlan, TrainingPlanLine,
    Policy, PolicyAcknowledgement, ComplianceRecord, ComplianceTask, AuditLog,
    ExitRequest, ExitInterview, ExitClearance, FinalSettlement, ExperienceCertificate, AssetReturn,
    StatutoryDeductionTemplate, StatutoryDeduction
)


# =============================================================================
# CORE HR SERIALIZERS
# =============================================================================

class DepartmentSerializer(serializers.ModelSerializer):
    manager_name = serializers.ReadOnlyField(source='manager.username')
    sub_department_count = serializers.SerializerMethodField()

    class Meta:
        model = Department
        fields = ['id', 'name', 'code', 'parent', 'manager', 'manager_name', 'description', 'is_active', 'sub_department_count', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_sub_department_count(self, obj):
        return obj.sub_departments.count()


class PositionSerializer(serializers.ModelSerializer):
    department_name = serializers.ReadOnlyField(source='department.name')
    employee_count = serializers.SerializerMethodField()

    class Meta:
        model = Position
        fields = ['id', 'title', 'code', 'department', 'department_name', 'grade', 'description', 'is_active', 'employee_count', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_employee_count(self, obj):
        return obj.employees.count()


class EmployeeSerializer(serializers.ModelSerializer):
    user_name = serializers.ReadOnlyField(source='user.username')
    department_name = serializers.ReadOnlyField(source='department.name')
    position_title = serializers.ReadOnlyField(source='position.title')
    supervisor_name = serializers.SerializerMethodField()
    salary_structure_name = serializers.ReadOnlyField(source='salary_structure.name')

    class Meta:
        model = Employee
        fields = [
            'id', 'user', 'user_name', 'employee_number', 'employee_type',
            'department', 'department_name', 'position', 'position_title',
            'supervisor', 'supervisor_name', 'hire_date', 'confirmation_date',
            'contract_start_date', 'contract_end_date', 'termination_date',
            'status', 'base_salary', 'salary_structure', 'salary_structure_name',
            'hourly_rate', 'bank_name', 'bank_account',
            'bank_routing', 'emergency_contact_name', 'emergency_contact_phone',
            'emergency_contact_relation', 'personal_info', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'employee_number', 'created_at', 'updated_at']

    def get_supervisor_name(self, obj):
        if obj.supervisor:
            return obj.supervisor.user.get_full_name()
        return None

    def validate(self, data):
        if data.get('contract_end_date') and data.get('contract_start_date'):
            if data['contract_end_date'] < data['contract_start_date']:
                raise serializers.ValidationError("Contract end date must be after start date")
        if data.get('termination_date') and data.get('hire_date'):
            if data['termination_date'] < data['hire_date']:
                raise serializers.ValidationError("Termination date must be after hire date")
        return data

    def create(self, validated_data):
        employee = super().create(validated_data)

        onboarding_tasks = OnboardingTask.objects.filter(is_active=True).order_by('sequence')
        hire_date = employee.hire_date
        assigned_to = employee.supervisor.user if employee.supervisor else None

        OnboardingProgress.objects.bulk_create([
            OnboardingProgress(
                employee=employee,
                task=task,
                due_date=hire_date + timedelta(days=task.due_days),
                status='Pending',
                assigned_to=assigned_to,
            )
            for task in onboarding_tasks
        ])

        return employee


class EmployeeListSerializer(EmployeeSerializer):
    """Serializer for list views that masks PII fields"""
    class Meta(EmployeeSerializer.Meta):
        fields = [f for f in EmployeeSerializer.Meta.fields if f not in (
            'social_security_number', 'national_id_number', 'tax_identification_number',
            'bank_account', 'base_salary', 'hourly_rate'
        )]


# =============================================================================
# LEAVE MANAGEMENT SERIALIZERS
# =============================================================================

class LeaveTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeaveType
        fields = [
            'id', 'name', 'code', 'description', 'max_days_per_year',
            'is_paid', 'requires_approval', 'is_active',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']


class LeaveRequestSerializer(serializers.ModelSerializer):
    employee_name = serializers.ReadOnlyField(source='employee.user.get_full_name')
    leave_type_name = serializers.ReadOnlyField(source='leave_type.name')
    approved_by_name = serializers.SerializerMethodField()

    class Meta:
        model = LeaveRequest
        fields = [
            'id', 'employee', 'employee_name', 'leave_type', 'leave_type_name',
            'start_date', 'end_date', 'total_days', 'reason', 'status',
            'approved_by', 'approved_by_name', 'approved_date', 'comments',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'total_days', 'status', 'approved_by', 'approved_date', 'created_at', 'updated_at']

    def get_approved_by_name(self, obj):
        if obj.approved_by:
            return obj.approved_by.username
        return None

    def validate(self, data):
        if data.get('start_date') and data.get('end_date'):
            if data['end_date'] < data['start_date']:
                raise serializers.ValidationError("End date must be after start date")

            employee = data.get('employee')
            leave_type = data.get('leave_type')
            start_date = data['start_date']
            end_date = data['end_date']

            if employee and leave_type:
                overlapping = LeaveRequest.objects.filter(
                    employee=employee,
                    leave_type=leave_type,
                    status__in=['Pending', 'Approved'],
                    start_date__lte=end_date,
                    end_date__gte=start_date
                )
                if self.instance:
                    overlapping = overlapping.exclude(pk=self.instance.pk)
                if overlapping.exists():
                    raise serializers.ValidationError("You already have a leave request for these dates")

        return data


class LeaveBalanceSerializer(serializers.ModelSerializer):
    employee_name = serializers.ReadOnlyField(source='employee.user.get_full_name')
    leave_type_name = serializers.ReadOnlyField(source='leave_type.name')
    available = serializers.SerializerMethodField()

    class Meta:
        model = LeaveBalance
        fields = ['id', 'employee', 'employee_name', 'leave_type', 'leave_type_name', 'year', 'allocated', 'taken', 'balance', 'available', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_available(self, obj):
        return obj.allocated - obj.taken


# =============================================================================
# ATTENDANCE SERIALIZERS
# =============================================================================

class AttendanceSerializer(serializers.ModelSerializer):
    employee_name = serializers.ReadOnlyField(source='employee.user.get_full_name')
    work_hours_display = serializers.SerializerMethodField()

    class Meta:
        model = Attendance
        fields = ['id', 'employee', 'employee_name', 'date', 'status', 'check_in', 'check_out', 'work_hours', 'work_hours_display', 'notes', 'created_at', 'updated_at']
        read_only_fields = ['id', 'work_hours', 'created_at', 'updated_at']

    def get_work_hours_display(self, obj):
        if obj.check_in and obj.check_out:
            duration = obj.check_out - obj.check_in
            hours = duration.total_seconds() / 3600
            return round(hours, 2)
        return 0

    def validate(self, data):
        if data.get('check_in') and data.get('check_out'):
            if data['check_out'] <= data['check_in']:
                raise serializers.ValidationError("Check-out must be after check-in")
        return data


class HolidaySerializer(serializers.ModelSerializer):
    class Meta:
        model = Holiday
        fields = [
            'id', 'name', 'date', 'is_recurring', 'is_active',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']


# =============================================================================
# RECRUITMENT & ONBOARDING SERIALIZERS
# =============================================================================

class JobPostSerializer(serializers.ModelSerializer):
    department_name = serializers.ReadOnlyField(source='department.name')
    candidate_count = serializers.SerializerMethodField()

    class Meta:
        model = JobPost
        fields = [
            'id', 'title', 'code', 'department', 'department_name', 'position',
            'description', 'requirements', 'responsibilities', 'job_type',
            'location', 'remote_type', 'salary_min', 'salary_max',
            'salary_currency', 'vacancies', 'experience_required', 'status',
            'publish_date', 'close_date', 'is_active', 'candidate_count',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']

    def get_candidate_count(self, obj):
        return obj.candidates.count()


class CandidateSerializer(serializers.ModelSerializer):
    job_title = serializers.ReadOnlyField(source='job_post.title')
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = Candidate
        fields = [
            'id', 'first_name', 'last_name', 'full_name', 'email', 'phone',
            'gender', 'job_post', 'job_title', 'status', 'resume',
            'cover_letter', 'current_company', 'current_position',
            'years_of_experience', 'source', 'applied_date', 'notes',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'applied_date', 'created_at', 'updated_at', 'created_by', 'updated_by']

    def get_full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}"


class InterviewSerializer(serializers.ModelSerializer):
    candidate_name = serializers.SerializerMethodField()
    interviewer_name = serializers.ReadOnlyField(source='interviewer.username')

    class Meta:
        model = Interview
        fields = [
            'id', 'candidate', 'candidate_name', 'interviewer',
            'interviewer_name', 'interview_round', 'interview_type',
            'scheduled_date', 'duration_minutes', 'location', 'status',
            'result', 'questions', 'answers', 'notes', 'rating',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']

    def get_candidate_name(self, obj):
        return f"{obj.candidate.first_name} {obj.candidate.last_name}"


class OnboardingTaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = OnboardingTask
        fields = [
            'id', 'name', 'description', 'category', 'sequence', 'due_days',
            'is_required', 'is_active',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']


class OnboardingProgressSerializer(serializers.ModelSerializer):
    task_name = serializers.ReadOnlyField(source='task.name')
    employee_name = serializers.ReadOnlyField(source='employee.user.get_full_name')
    assigned_to_name = serializers.ReadOnlyField(source='assigned_to.username')

    class Meta:
        model = OnboardingProgress
        fields = [
            'id', 'employee', 'employee_name', 'task', 'task_name',
            'due_date', 'completed_date', 'status', 'assigned_to',
            'assigned_to_name', 'notes',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']


# =============================================================================
# PAYROLL SERIALIZERS
# =============================================================================

class SalaryStructureSerializer(serializers.ModelSerializer):
    class Meta:
        model = SalaryStructure
        fields = [
            'id', 'name', 'code', 'description', 'is_active',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']


class SalaryComponentSerializer(serializers.ModelSerializer):
    type_display = serializers.ReadOnlyField(source='get_component_type_display')

    class Meta:
        model = SalaryComponent
        fields = [
            'id', 'name', 'code', 'component_type', 'type_display',
            'calculation_type', 'value', 'percentage_of_basic',
            'is_taxable', 'is_pensionable', 'is_active',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']


class PayrollPeriodSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayrollPeriod
        fields = [
            'id', 'period_type', 'start_date', 'end_date', 'payment_date',
            'status', 'is_active',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']


class PayrollEarningSerializer(serializers.ModelSerializer):
    component_name = serializers.ReadOnlyField(source='component.name')

    class Meta:
        model = PayrollEarning
        fields = ['id', 'payroll_line', 'component', 'component_name', 'amount']
        read_only_fields = ['id']


class PayrollDeductionSerializer(serializers.ModelSerializer):
    component_name = serializers.ReadOnlyField(source='component.name')

    class Meta:
        model = PayrollDeduction
        fields = ['id', 'payroll_line', 'component', 'component_name', 'amount']
        read_only_fields = ['id']


class PayrollLineSerializer(serializers.ModelSerializer):
    employee_name = serializers.ReadOnlyField(source='employee.user.get_full_name')
    earnings = PayrollEarningSerializer(many=True, read_only=True)
    deductions = PayrollDeductionSerializer(many=True, read_only=True)

    class Meta:
        model = PayrollLine
        fields = [
            'id', 'payroll_run', 'employee', 'employee_name', 'basic_salary',
            'gross_salary', 'total_earnings', 'total_deductions', 'net_salary',
            'working_days', 'days_worked', 'overtime_hours', 'overtime_amount',
            'tax_deduction', 'pension_deduction', 'other_deductions',
            'bank_name', 'bank_account', 'notes', 'earnings', 'deductions',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']


class PayrollRunSerializer(serializers.ModelSerializer):
    period_name = serializers.SerializerMethodField()
    lines = PayrollLineSerializer(many=True, read_only=True)
    processed_by_name = serializers.ReadOnlyField(source='processed_by.username')
    approved_by_name = serializers.ReadOnlyField(source='approved_by.username')

    class Meta:
        model = PayrollRun
        fields = [
            'id', 'period', 'period_name', 'run_number', 'status',
            'total_gross', 'total_deductions', 'total_net',
            'processed_by', 'processed_by_name', 'approved_by',
            'approved_by_name', 'approved_date', 'notes', 'lines',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']

    def get_period_name(self, obj):
        return f"{obj.period.period_type} - {obj.period.start_date} to {obj.period.end_date}"


class PayslipSerializer(serializers.ModelSerializer):
    employee_name = serializers.ReadOnlyField(source='payroll_line.employee.user.get_full_name')
    period = serializers.SerializerMethodField()

    class Meta:
        model = Payslip
        fields = [
            'id', 'payroll_line', 'employee_name', 'status',
            'generated_date', 'sent_date', 'period',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'generated_date', 'created_at', 'updated_at', 'created_by', 'updated_by']

    def get_period(self, obj):
        return f"{obj.payroll_line.payroll_run.period.start_date} - {obj.payroll_line.payroll_run.period.end_date}"


# =============================================================================
# PERFORMANCE MANAGEMENT SERIALIZERS
# =============================================================================

class PerformanceCycleSerializer(serializers.ModelSerializer):
    class Meta:
        model = PerformanceCycle
        fields = [
            'id', 'name', 'code', 'start_date', 'end_date', 'status',
            'self_review_enabled', 'peer_review_enabled',
            'manager_review_enabled', 'is_active',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']


class PerformanceGoalSerializer(serializers.ModelSerializer):
    employee_name = serializers.ReadOnlyField(source='employee.user.get_full_name')

    class Meta:
        model = PerformanceGoal
        fields = [
            'id', 'title', 'description', 'employee', 'employee_name',
            'cycle', 'goal_type', 'start_date', 'target_date',
            'completion_date', 'progress', 'status', 'weight', 'key_results',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']


class CompetencyRatingSerializer(serializers.ModelSerializer):
    competency_name = serializers.ReadOnlyField(source='competency.name')

    class Meta:
        model = CompetencyRating
        fields = ['id', 'review', 'competency', 'competency_name', 'rating', 'comments']
        read_only_fields = ['id']


class PerformanceReviewSerializer(serializers.ModelSerializer):
    employee_name = serializers.ReadOnlyField(source='employee.user.get_full_name')
    reviewer_name = serializers.ReadOnlyField(source='reviewer.username')
    competency_ratings = CompetencyRatingSerializer(many=True, read_only=True)

    class Meta:
        model = PerformanceReview
        fields = [
            'id', 'employee', 'employee_name', 'cycle', 'review_type',
            'reviewer', 'reviewer_name', 'status', 'rating', 'rating_category',
            'strengths', 'areas_for_improvement', 'comments',
            'goals_achieved', 'goals_total', 'submitted_date',
            'competency_ratings',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']


class CompetencySerializer(serializers.ModelSerializer):
    class Meta:
        model = Competency
        fields = ['id', 'name', 'description', 'category', 'is_active']
        read_only_fields = ['id']


class PromotionSerializer(serializers.ModelSerializer):
    employee_name = serializers.ReadOnlyField(source='employee.user.get_full_name')
    from_position_title = serializers.ReadOnlyField(source='from_position.title')
    to_position_title = serializers.ReadOnlyField(source='to_position.title')
    approved_by_name = serializers.ReadOnlyField(source='approved_by.username')

    class Meta:
        model = Promotion
        fields = [
            'id', 'employee', 'employee_name', 'from_position',
            'from_position_title', 'to_position', 'to_position_title',
            'from_salary', 'to_salary', 'effective_date', 'status',
            'reason', 'approved_by', 'approved_by_name', 'approved_date',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']


# =============================================================================
# TRAINING & DEVELOPMENT SERIALIZERS
# =============================================================================

class TrainingProgramSerializer(serializers.ModelSerializer):
    department_name = serializers.ReadOnlyField(source='department.name')
    enrollment_count = serializers.SerializerMethodField()

    class Meta:
        model = TrainingProgram
        fields = [
            'id', 'name', 'code', 'description', 'program_type',
            'delivery_method', 'duration_hours', 'max_participants',
            'start_date', 'end_date', 'registration_deadline',
            'trainer_name', 'trainer_contact', 'location',
            'cost_per_participant', 'objectives', 'prerequisites',
            'materials', 'certificate_enabled', 'certificate_template',
            'department', 'status', 'is_active', 'department_name', 'enrollment_count',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']

    def get_enrollment_count(self, obj):
        return obj.enrollments.count()


class TrainingEnrollmentSerializer(serializers.ModelSerializer):
    employee_name = serializers.ReadOnlyField(source='employee.user.get_full_name')
    program_name = serializers.ReadOnlyField(source='program.name')

    class Meta:
        model = TrainingEnrollment
        fields = [
            'id', 'employee', 'employee_name', 'program', 'program_name',
            'registration_date', 'status', 'attendance_date', 'completion_date',
            'score', 'passed', 'feedback', 'certificate_issued',
            'certificate_number',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'registration_date', 'created_at', 'updated_at', 'created_by', 'updated_by']


class SkillSerializer(serializers.ModelSerializer):
    class Meta:
        model = Skill
        fields = [
            'id', 'name', 'code', 'description', 'category', 'is_active',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']


class EmployeeSkillSerializer(serializers.ModelSerializer):
    employee_name = serializers.ReadOnlyField(source='employee.user.get_full_name')
    skill_name = serializers.ReadOnlyField(source='skill.name')
    proficiency_display = serializers.SerializerMethodField()

    class Meta:
        model = EmployeeSkill
        fields = [
            'id', 'employee', 'employee_name', 'skill', 'skill_name',
            'proficiency_level', 'proficiency_display', 'years_experience',
            'certified', 'certification_date', 'certification_expiry', 'notes',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']

    def get_proficiency_display(self, obj):
        return obj.get_proficiency_level_display()


class TrainingPlanLineSerializer(serializers.ModelSerializer):
    program_name = serializers.ReadOnlyField(source='program.name')

    class Meta:
        model = TrainingPlanLine
        fields = [
            'id', 'training_plan', 'program', 'program_name',
            'sequence', 'due_date', 'completed',
        ]
        read_only_fields = ['id']


class TrainingPlanSerializer(serializers.ModelSerializer):
    employee_name = serializers.ReadOnlyField(source='employee.user.get_full_name')
    lines = TrainingPlanLineSerializer(many=True, read_only=True)

    class Meta:
        model = TrainingPlan
        fields = [
            'id', 'name', 'description', 'employee', 'employee_name',
            'start_date', 'end_date', 'status', 'is_active', 'lines',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']


# =============================================================================
# COMPLIANCE & POLICY SERIALIZERS
# =============================================================================

class PolicySerializer(serializers.ModelSerializer):
    department_names = serializers.SerializerMethodField()
    acknowledgment_count = serializers.SerializerMethodField()

    class Meta:
        model = Policy
        fields = [
            'id', 'title', 'code', 'category', 'version', 'description',
            'content', 'effective_date', 'expiry_date',
            'requires_acknowledgement', 'acknowledgment_deadline_days',
            'applies_to_all', 'departments', 'department_names', 'positions',
            'status', 'is_active', 'attachment', 'acknowledgment_count',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']

    def get_department_names(self, obj):
        return [d.name for d in obj.departments.all()]

    def get_acknowledgment_count(self, obj):
        return obj.acknowledgements.filter(status='Acknowledged').count()


class PolicyAcknowledgementSerializer(serializers.ModelSerializer):
    employee_name = serializers.ReadOnlyField(source='employee.user.get_full_name')
    policy_title = serializers.ReadOnlyField(source='policy.title')

    class Meta:
        model = PolicyAcknowledgement
        fields = [
            'id', 'employee', 'employee_name', 'policy', 'policy_title',
            'status', 'acknowledged_date', 'comments',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']


class ComplianceRecordSerializer(serializers.ModelSerializer):
    assigned_to_name = serializers.ReadOnlyField(source='assigned_to.username')
    task_count = serializers.SerializerMethodField()

    class Meta:
        model = ComplianceRecord
        fields = [
            'id', 'title', 'code', 'compliance_type', 'description',
            'effective_date', 'expiry_date', 'status', 'assigned_to',
            'assigned_to_name', 'requirements', 'evidence',
            'last_audit_date', 'next_audit_date', 'notes', 'task_count',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']

    def get_task_count(self, obj):
        return obj.tasks.count()


class ComplianceTaskSerializer(serializers.ModelSerializer):
    assigned_to_name = serializers.ReadOnlyField(source='assigned_to.username')

    class Meta:
        model = ComplianceTask
        fields = [
            'id', 'compliance_record', 'title', 'description', 'due_date',
            'completed_date', 'assigned_to', 'assigned_to_name', 'status',
            'evidence',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']


class AuditLogSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = [
            'id', 'user', 'user_name', 'action_type', 'module',
            'object_id', 'object_repr', 'changes', 'ip_address',
            'user_agent', 'timestamp',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'timestamp', 'created_at', 'updated_at', 'created_by', 'updated_by']

    def get_user_name(self, obj):
        return obj.user.username if obj.user else 'System'


# =============================================================================
# EXIT & OFFBOARDING SERIALIZERS
# =============================================================================

class ExitRequestSerializer(serializers.ModelSerializer):
    employee_name = serializers.ReadOnlyField(source='employee.user.get_full_name')
    approved_by_name = serializers.ReadOnlyField(source='approved_by.username')

    class Meta:
        model = ExitRequest
        fields = [
            'id', 'employee', 'employee_name', 'exit_type', 'requested_date',
            'last_working_date', 'reason', 'status', 'approved_by',
            'approved_by_name', 'approved_date', 'manager_comments',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']


class ExitInterviewSerializer(serializers.ModelSerializer):
    employee_name = serializers.SerializerMethodField()
    interviewer_name = serializers.ReadOnlyField(source='interviewer.username')

    class Meta:
        model = ExitInterview
        fields = [
            'id', 'exit_request', 'employee_name', 'interviewer',
            'interviewer_name', 'scheduled_date', 'completed_date', 'status',
            'reason_for_leaving', 'satisfaction_rating', 'feedback_questions',
            'overall_feedback', 'would_recommend', 'exit_interviewer_notes',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']

    def get_employee_name(self, obj):
        return obj.exit_request.employee.user.get_full_name()


class ExitClearanceSerializer(serializers.ModelSerializer):
    exit_employee_name = serializers.SerializerMethodField()
    completed_by_name = serializers.ReadOnlyField(source='completed_by.username')

    class Meta:
        model = ExitClearance
        fields = [
            'id', 'exit_request', 'exit_employee_name', 'category',
            'department', 'status', 'checklist_items', 'completed_items',
            'assigned_to', 'completed_by', 'completed_by_name',
            'completed_date', 'remarks',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']

    def get_exit_employee_name(self, obj):
        return obj.exit_request.employee.user.get_full_name()


class StatutoryDeductionTemplateSerializer(serializers.ModelSerializer):
    gl_account_name = serializers.ReadOnlyField(source='gl_account.name', allow_null=True)
    
    class Meta:
        model = StatutoryDeductionTemplate
        fields = [
            'id', 'name', 'code', 'deduction_type',
            'rate', 'fixed_amount', 'employer_rate', 'employer_fixed',
            'is_mandatory', 'is_active',
            'gl_account', 'gl_account_name',
            'applies_to_employment_types',
            'minimum_amount', 'maximum_amount',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class StatutoryDeductionSerializer(serializers.ModelSerializer):
    template_name = serializers.ReadOnlyField(source='template.name')
    template_type = serializers.ReadOnlyField(source='template.deduction_type')
    
    class Meta:
        model = StatutoryDeduction
        fields = [
            'id', 'payroll_line', 'template', 'template_name', 'template_type',
            'employee_amount', 'employer_amount', 'is_employer_contribution',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class FinalSettlementSerializer(serializers.ModelSerializer):
    employee_name = serializers.SerializerMethodField()
    calculated_by_name = serializers.ReadOnlyField(source='calculated_by.username')
    approved_by_name = serializers.ReadOnlyField(source='approved_by.username')

    class Meta:
        model = FinalSettlement
        fields = [
            'id', 'exit_request', 'employee_name', 'basic_salary',
            'pending_salary_days', 'pending_salary_amount',
            'leave_balance_days', 'leave_encashment_rate',
            'leave_encashment_amount', 'notice_period_deduction',
            'advances_deduction', 'other_deductions', 'bonus_amount',
            'gratuity_amount', 'other_benefits', 'total_deductions',
            'total_payable', 'status', 'payment_date', 'payment_reference',
            'calculated_by', 'calculated_by_name', 'calculated_date',
            'approved_by', 'approved_by_name', 'approved_date', 'notes',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'calculated_date', 'created_at', 'updated_at', 'created_by', 'updated_by']

    def get_employee_name(self, obj):
        return obj.exit_request.employee.user.get_full_name()


class ExperienceCertificateSerializer(serializers.ModelSerializer):
    employee_name = serializers.SerializerMethodField()

    class Meta:
        model = ExperienceCertificate
        fields = [
            'id', 'exit_request', 'certificate_number', 'issue_date',
            'employee_name', 'father_name', 'designation', 'department',
            'joining_date', 'relieving_date', 'total_experience_years',
            'conduct', 'reason_for_leaving', 'is_issued', 'issued_date',
            'template_content', 'digital_signature',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']

    def get_employee_name(self, obj):
        return obj.exit_request.employee.user.get_full_name()


class AssetReturnSerializer(serializers.ModelSerializer):
    employee_name = serializers.SerializerMethodField()
    verified_by_name = serializers.ReadOnlyField(source='verified_by.username')

    class Meta:
        model = AssetReturn
        fields = [
            'id', 'exit_request', 'employee_name', 'asset_name',
            'asset_description', 'asset_tag', 'assigned_date',
            'return_due_date', 'return_actual_date', 'status',
            'condition', 'remarks', 'verified_by', 'verified_by_name',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']

    def get_employee_name(self, obj):
        return obj.exit_request.employee.user.get_full_name()
