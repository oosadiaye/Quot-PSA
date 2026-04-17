from decimal import Decimal
from django.db import models
from django.contrib.auth.models import User
from core.models import AuditBaseModel


# =============================================================================
# CORE HR MODELS
# =============================================================================

class Department(AuditBaseModel):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20, unique=True)
    parent = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='sub_departments')
    manager = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='managed_departments')
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    
    cost_center = models.ForeignKey(
        'accounting.CostCenter', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='departments'
    )

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Position(AuditBaseModel):
    GRADE_CHOICES = [
        ('Entry', 'Entry Level'),
        ('Mid', 'Mid Level'),
        ('Senior', 'Senior Level'),
        ('Manager', 'Manager'),
        ('Director', 'Director'),
        ('Executive', 'Executive'),
    ]
    
    title = models.CharField(max_length=100)
    code = models.CharField(max_length=20)
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name='positions')
    grade = models.CharField(max_length=20, choices=GRADE_CHOICES)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ['code', 'department']

    def __str__(self):
        return f"{self.title} - {self.department.name}"


class Employee(AuditBaseModel):
    GENDER_CHOICES = [
        ('Male', 'Male'),
        ('Female', 'Female'),
        ('Other', 'Other'),
    ]
    
    MARITAL_CHOICES = [
        ('Single', 'Single'),
        ('Married', 'Married'),
        ('Divorced', 'Divorced'),
        ('Widowed', 'Widowed'),
    ]
    
    STATUS_CHOICES = [
        ('Active', 'Active'),
        ('Probation', 'Probation'),
        ('On Leave', 'On Leave'),
        ('Terminated', 'Terminated'),
        ('Retired', 'Retired'),
    ]

    EMPLOYMENT_TYPE_CHOICES = [
        ('Permanent', 'Permanent'),
        ('Contract', 'Contract'),
        ('Intern', 'Intern'),
        ('Part-time', 'Part-time'),
        ('Freelance', 'Freelance'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='employee')
    employee_number = models.CharField(max_length=50, unique=True)
    
    personal_info = models.JSONField(default=dict, blank=True)
    
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name='employees')
    position = models.ForeignKey(Position, on_delete=models.PROTECT, related_name='employees')
    supervisor = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='subordinates')
    
    employee_type = models.CharField(max_length=20, choices=EMPLOYMENT_TYPE_CHOICES, default='Permanent')
    
    hire_date = models.DateField()
    confirmation_date = models.DateField(null=True, blank=True)
    contract_start_date = models.DateField(null=True, blank=True)
    contract_end_date = models.DateField(null=True, blank=True)
    termination_date = models.DateField(null=True, blank=True)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Active')
    
    base_salary = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    salary_structure = models.ForeignKey(
        'SalaryStructure', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='employees'
    )
    hourly_rate = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    
    bank_name = models.CharField(max_length=100, blank=True)
    bank_account = models.CharField(max_length=50, blank=True)
    bank_routing = models.CharField(max_length=20, blank=True)
    
    # HR-M5: Statutory ID Fields
    tax_identification_number = models.CharField(
        max_length=50, blank=True,
        help_text="Tax ID / TIN"
    )
    social_security_number = models.CharField(
        max_length=50, blank=True,
        help_text="SSN / Social Security Number"
    )
    national_id_number = models.CharField(
        max_length=50, blank=True,
        help_text="National ID Card Number"
    )
    passport_number = models.CharField(
        max_length=50, blank=True,
        help_text="Passport Number"
    )
    passport_expiry = models.DateField(null=True, blank=True)
    pension_number = models.CharField(
        max_length=50, blank=True,
        help_text="Pension Membership Number"
    )
    health_insurance_number = models.CharField(
        max_length=50, blank=True,
        help_text="NHIS / Health Insurance Number"
    )
    
    emergency_contact_name = models.CharField(max_length=100, blank=True)
    emergency_contact_phone = models.CharField(max_length=20, blank=True)
    emergency_contact_relation = models.CharField(max_length=50, blank=True)

    class Meta:
        ordering = ['employee_number']

    def __str__(self):
        return f"{self.employee_number} - {self.user.get_full_name()}"


# =============================================================================
# LEAVE MANAGEMENT
# =============================================================================

class LeaveType(AuditBaseModel):
    name = models.CharField(max_length=50)
    code = models.CharField(max_length=20, unique=True)
    description = models.TextField(blank=True)
    max_days_per_year = models.PositiveIntegerField(default=0)
    is_paid = models.BooleanField(default=True)
    requires_approval = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class LeaveRequest(AuditBaseModel):
    STATUS_CHOICES = [
        ('Draft', 'Draft'),
        ('Pending', 'Pending'),
        ('Approved', 'Approved'),
        ('Rejected', 'Rejected'),
        ('Cancelled', 'Cancelled'),
    ]
    
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='leave_requests')
    leave_type = models.ForeignKey(LeaveType, on_delete=models.CASCADE)
    
    start_date = models.DateField()
    end_date = models.DateField()
    total_days = models.DecimalField(max_digits=5, decimal_places=2, editable=False)
    
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Draft')
    
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_leaves')
    approved_date = models.DateTimeField(null=True, blank=True)
    comments = models.TextField(blank=True)

    class Meta:
        permissions = [
            ('approve_leaverequest', 'Can approve leave requests'),
        ]

    def save(self, *args, **kwargs):
        if self.start_date and self.end_date:
            from datetime import timedelta
            days = (self.end_date - self.start_date).days + 1
            self.total_days = days
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.employee} - {self.leave_type} ({self.start_date} to {self.end_date})"


class LeaveBalance(AuditBaseModel):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='leave_balances')
    leave_type = models.ForeignKey(LeaveType, on_delete=models.CASCADE)
    year = models.PositiveIntegerField()
    
    allocated = models.PositiveIntegerField(default=0)
    taken = models.PositiveIntegerField(default=0)
    balance = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ['employee', 'leave_type', 'year']

    def __str__(self):
        return f"{self.employee} - {self.leave_type} ({self.year}): {self.balance}"


# =============================================================================
# ATTENDANCE
# =============================================================================

class Attendance(AuditBaseModel):
    ATTENDANCE_STATUS = [
        ('Present', 'Present'),
        ('Absent', 'Absent'),
        ('Late', 'Late'),
        ('On Leave', 'On Leave'),
        ('Holiday', 'Holiday'),
    ]
    
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='attendances')
    date = models.DateField()
    
    status = models.CharField(max_length=20, choices=ATTENDANCE_STATUS)
    check_in = models.DateTimeField(null=True, blank=True)
    check_out = models.DateTimeField(null=True, blank=True)
    work_hours = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    
    notes = models.TextField(blank=True)

    class Meta:
        unique_together = ['employee', 'date']
        ordering = ['-date']

    def __str__(self):
        return f"{self.employee} - {self.date} ({self.status})"


class Holiday(AuditBaseModel):
    name = models.CharField(max_length=100)
    date = models.DateField()
    is_recurring = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['date']
    
    def __str__(self):
        return f"{self.name} - {self.date}"


# =============================================================================
# RECRUITMENT & ONBOARDING
# =============================================================================

class JobPost(AuditBaseModel):
    STATUS_CHOICES = [
        ('Draft', 'Draft'),
        ('Published', 'Published'),
        ('Closed', 'Closed'),
        ('On Hold', 'On Hold'),
    ]
    
    title = models.CharField(max_length=200)
    code = models.CharField(max_length=20, unique=True)
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True)
    position = models.ForeignKey(Position, on_delete=models.SET_NULL, null=True, blank=True)
    
    description = models.TextField()
    requirements = models.TextField()
    responsibilities = models.TextField()
    
    job_type = models.CharField(max_length=50, choices=Employee.EMPLOYMENT_TYPE_CHOICES, default='Permanent')
    location = models.CharField(max_length=200, blank=True)
    remote_type = models.CharField(max_length=20, choices=[
        ('Onsite', 'Onsite'),
        ('Remote', 'Remote'),
        ('Hybrid', 'Hybrid'),
    ], default='Onsite')
    
    salary_min = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    salary_max = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    salary_currency = models.CharField(max_length=3, default='USD')
    
    vacancies = models.PositiveIntegerField(default=1)
    experience_required = models.PositiveIntegerField(default=0, help_text="Years of experience")
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Draft')
    publish_date = models.DateField(null=True, blank=True)
    close_date = models.DateField(null=True, blank=True)
    
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.title} ({self.code})"


class Candidate(AuditBaseModel):
    GENDER_CHOICES = Employee.GENDER_CHOICES
    
    STATUS_CHOICES = [
        ('Applied', 'Applied'),
        ('Screening', 'Screening'),
        ('Interview', 'Interview'),
        ('Assessment', 'Assessment'),
        ('Offer', 'Offer'),
        ('Rejected', 'Rejected'),
        ('Hired', 'Hired'),
        ('Withdrawn', 'Withdrawn'),
    ]
    
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField()
    phone = models.CharField(max_length=20)
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, blank=True)
    
    job_post = models.ForeignKey(JobPost, on_delete=models.CASCADE, related_name='candidates')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Applied')
    
    resume = models.FileField(upload_to='recruitment/resumes/', null=True, blank=True)
    cover_letter = models.TextField(blank=True)
    
    current_company = models.CharField(max_length=200, blank=True)
    current_position = models.CharField(max_length=100, blank=True)
    years_of_experience = models.PositiveIntegerField(default=0)
    
    source = models.CharField(max_length=50, choices=[
        ('Website', 'Website'),
        ('Referral', 'Referral'),
        ('LinkedIn', 'LinkedIn'),
        ('Job Fair', 'Job Fair'),
        ('Agency', 'Agency'),
        ('Other', 'Other'),
    ], default='Website')
    
    applied_date = models.DateField(auto_now_add=True)
    
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name} - {self.job_post.title}"


class Interview(AuditBaseModel):
    STATUS_CHOICES = [
        ('Scheduled', 'Scheduled'),
        ('Completed', 'Completed'),
        ('Cancelled', 'Cancelled'),
        ('No Show', 'No Show'),
    ]
    
    RESULT_CHOICES = [
        ('Pending', 'Pending'),
        ('Pass', 'Pass'),
        ('Fail', 'Fail'),
        ('Deferred', 'Deferred'),
    ]
    
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name='interviews')
    interviewer = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='interviews_conducted')
    
    interview_round = models.PositiveIntegerField(default=1)
    interview_type = models.CharField(max_length=20, choices=[
        ('Phone', 'Phone'),
        ('Video', 'Video'),
        ('In-Person', 'In-Person'),
        ('Technical', 'Technical'),
        ('HR', 'HR'),
        ('Final', 'Final'),
    ], default='Video')
    
    scheduled_date = models.DateTimeField()
    duration_minutes = models.PositiveIntegerField(default=60)
    location = models.CharField(max_length=200, blank=True)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Scheduled')
    result = models.CharField(max_length=20, choices=RESULT_CHOICES, default='Pending')
    
    questions = models.TextField(blank=True)
    answers = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    rating = models.PositiveIntegerField(null=True, blank=True, help_text="1-5 rating")

    def __str__(self):
        return f"{self.candidate} - Round {self.interview_round}"


class OnboardingTask(AuditBaseModel):
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('In Progress', 'In Progress'),
        ('Completed', 'Completed'),
        ('Skipped', 'Skipped'),
    ]
    
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=50, choices=[
        ('Documentation', 'Documentation'),
        ('IT Setup', 'IT Setup'),
        ('Training', 'Training'),
        ('Compliance', 'Compliance'),
        ('Introduction', 'Introduction'),
        ('Other', 'Other'),
    ])
    sequence = models.PositiveIntegerField(default=1)
    due_days = models.PositiveIntegerField(default=7, help_text="Due within days of start")
    
    is_required = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['sequence']

    def __str__(self):
        return self.name


class OnboardingProgress(AuditBaseModel):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='onboarding_progress')
    task = models.ForeignKey(OnboardingTask, on_delete=models.CASCADE)
    
    due_date = models.DateField()
    completed_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=OnboardingTask.STATUS_CHOICES, default='Pending')
    
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='onboarding_tasks')
    notes = models.TextField(blank=True)

    class Meta:
        unique_together = ['employee', 'task']

    def __str__(self):
        return f"{self.employee} - {self.task.name}"


# =============================================================================
# PAYROLL MANAGEMENT
# =============================================================================

class SalaryStructure(AuditBaseModel):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class TaxBracket(AuditBaseModel):
    """HR-H1: Tax brackets for automatic tax calculation"""
    name = models.CharField(max_length=100)
    min_income = models.DecimalField(max_digits=12, decimal_places=2, help_text="Minimum income for this bracket")
    max_income = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, help_text="Maximum income (null = no limit)")
    rate = models.DecimalField(max_digits=5, decimal_places=2, help_text="Tax rate as percentage (e.g., 25.00 for 25%)")
    fixed_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0, help_text="Fixed amount to add to calculated tax")
    effective_date = models.DateField(help_text="Date this bracket becomes effective")
    end_date = models.DateField(null=True, blank=True, help_text="Date this bracket expires")
    is_active = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['min_income']
    
    def __str__(self):
        return f"{self.name}: {self.min_income} - {self.max_income or '∞'} @ {self.rate}%"


class TaxConfiguration(AuditBaseModel):
    """HR-H1: Tax configuration settings"""
    name = models.CharField(max_length=100)
    tax_year = models.PositiveIntegerField(unique=True)
    basic_exemption = models.DecimalField(max_digits=12, decimal_places=2, default=0, help_text="Annual income exemption")
    standard_deduction = models.DecimalField(max_digits=12, decimal_places=2, default=0, help_text="Standard deduction amount")
    social_security_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    social_security_cap = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    pension_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    pension_cap = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    
    def __str__(self):
        return f"Tax Config {self.tax_year}"


class SalaryComponent(AuditBaseModel):
    COMPONENT_TYPE = [
        ('Earning', 'Earning'),
        ('Deduction', 'Deduction'),
    ]
    
    CALCULATION_TYPE = [
        ('Fixed', 'Fixed Amount'),
        ('Percentage', 'Percentage of Basic'),
        ('Variable', 'Variable'),
    ]
    
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20)
    component_type = models.CharField(max_length=20, choices=COMPONENT_TYPE)
    calculation_type = models.CharField(max_length=20, choices=CALCULATION_TYPE, default='Fixed')
    
    value = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    percentage_of_basic = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, help_text="Used if calculation_type is Percentage")
    
    is_taxable = models.BooleanField(default=False)
    is_pensionable = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ['code']

    def __str__(self):
        return f"{self.name} ({self.get_component_type_display()})"


class SalaryStructureTemplate(models.Model):
    salary_structure = models.ForeignKey(SalaryStructure, on_delete=models.CASCADE, related_name='components')
    component = models.ForeignKey(SalaryComponent, on_delete=models.CASCADE)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ['salary_structure', 'component']


class PayrollPeriod(AuditBaseModel):
    STATUS_CHOICES = [
        ('Draft', 'Draft'),
        ('Open', 'Open'),
        ('Closed', 'Closed'),
        ('Processed', 'Processed'),
    ]
    
    period_type = models.CharField(max_length=20, choices=[
        ('Monthly', 'Monthly'),
        ('Bi-Weekly', 'Bi-Weekly'),
        ('Weekly', 'Weekly'),
    ], default='Monthly')
    
    start_date = models.DateField()
    end_date = models.DateField()
    payment_date = models.DateField()
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Draft')
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-start_date']
        unique_together = ['period_type', 'start_date']

    def __str__(self):
        return f"{self.period_type} - {self.start_date} to {self.end_date}"


class PayrollRun(AuditBaseModel):
    STATUS_CHOICES = [
        ('Draft', 'Draft'),
        ('In Progress', 'In Progress'),
        ('Approved', 'Approved'),
        ('Paid', 'Paid'),
        ('Cancelled', 'Cancelled'),
    ]
    
    period = models.ForeignKey(PayrollPeriod, on_delete=models.CASCADE, related_name='payroll_runs')
    
    run_number = models.CharField(max_length=20, unique=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Draft')
    
    total_gross = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_deductions = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_net = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    
    processed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='payrolls_processed')
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='payrolls_approved')
    approved_date = models.DateTimeField(null=True, blank=True)
    
    journal_entry = models.ForeignKey('accounting.JournalHeader', on_delete=models.SET_NULL, null=True, blank=True, related_name='payroll_runs')
    notes = models.TextField(blank=True)

    # ── GL Account Overrides ───────────────────────────────────────────────────
    # When set, the payroll posting service uses these accounts instead of the
    # global DEFAULT_GL_ACCOUNTS fallback.  Useful for per-department or
    # per-entity GL segregation (e.g. different payroll expense cost centres).
    payroll_expense_account = models.ForeignKey(
        'accounting.Account',
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name='payroll_runs_as_expense',
        help_text="Override GL account for Salary/Wage Expense. Falls back to DEFAULT_GL_ACCOUNTS['SALARY_EXPENSE'].",
    )
    payroll_liability_account = models.ForeignKey(
        'accounting.Account',
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name='payroll_runs_as_liability',
        help_text="Override GL account for Net Pay Liability. Falls back to DEFAULT_GL_ACCOUNTS['PAYROLL_LIABILITY'].",
    )
    pension_account = models.ForeignKey(
        'accounting.Account',
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name='payroll_runs_as_pension',
        help_text="Override GL account for Pension Payable. Falls back to DEFAULT_GL_ACCOUNTS['PENSION_PAYABLE'].",
    )

    class Meta:
        permissions = [
            ('process_payrollrun', 'Can process payroll runs'),
            ('approve_payrollrun', 'Can approve payroll runs'),
        ]

    def __str__(self):
        return f"Payroll {self.run_number} - {self.period}"


class PayrollLine(AuditBaseModel):
    payroll_run = models.ForeignKey(PayrollRun, on_delete=models.CASCADE, related_name='lines')
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='payroll_lines')
    
    basic_salary = models.DecimalField(max_digits=12, decimal_places=2)
    gross_salary = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_earnings = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_deductions = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    net_salary = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    working_days = models.PositiveIntegerField(default=0)
    days_worked = models.PositiveIntegerField(default=0)
    overtime_hours = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    overtime_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    tax_deduction = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    pension_deduction = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    other_deductions = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    bank_name = models.CharField(max_length=100, blank=True)
    bank_account = models.CharField(max_length=50, blank=True)
    
    notes = models.TextField(blank=True)

    class Meta:
        unique_together = ['payroll_run', 'employee']

    def __str__(self):
        return f"{self.employee} - {self.net_salary}"


class PayrollEarning(models.Model):
    payroll_line = models.ForeignKey(PayrollLine, on_delete=models.CASCADE, related_name='earnings')
    component = models.ForeignKey(SalaryComponent, on_delete=models.PROTECT)
    amount = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.component.name}: {self.amount}"


class PayrollDeduction(models.Model):
    payroll_line = models.ForeignKey(PayrollLine, on_delete=models.CASCADE, related_name='deductions')
    component = models.ForeignKey(SalaryComponent, on_delete=models.PROTECT)
    amount = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.component.name}: {self.amount}"


class StatutoryDeductionTemplate(AuditBaseModel):
    """HR-M6: Deduction templates for statutory filings (NHIS, GETFL, etc.)"""
    DEDUCTION_TYPE_CHOICES = [
        ('NHIS', 'National Health Insurance'),
        ('GETFL', 'GETFL/Trade Union'),
        ('Tier1', 'Tier 1 Pension'),
        ('Tier2', 'Tier 2 Pension'),
        ('Income_Tax', 'Income Tax'),
        ('Other', 'Other'),
    ]
    
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20, unique=True)
    deduction_type = models.CharField(max_length=20, choices=DEDUCTION_TYPE_CHOICES)
    
    rate = models.DecimalField(
        max_digits=6, decimal_places=4, default=0,
        help_text="Percentage rate (e.g., 0.025 for 2.5%)"
    )
    fixed_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text="Fixed amount to deduct (used instead of rate if set)"
    )
    
    employer_rate = models.DecimalField(
        max_digits=6, decimal_places=4, default=0,
        help_text="Employer contribution rate"
    )
    employer_fixed = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text="Employer fixed contribution"
    )
    
    is_mandatory = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    
    gl_account = models.ForeignKey(
        'accounting.Account', on_delete=models.PROTECT, null=True, blank=True,
        related_name='statutory_deduction_templates'
    )
    
    applies_to_employment_types = models.JSONField(
        default=list, blank=True,
        help_text="List of employment types this applies to (e.g., ['Permanent', 'Contract'])"
    )
    
    minimum_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text="Minimum deduction amount"
    )
    maximum_amount = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="Maximum deduction amount (cap)"
    )
    
    class Meta:
        ordering = ['deduction_type', 'name']
    
    def __str__(self):
        return f"{self.name} ({self.deduction_type})"
    
    def calculate_deduction(self, gross_salary):
        """Calculate deduction amount based on gross salary."""
        if self.fixed_amount > 0:
            return self.fixed_amount
        
        amount = gross_salary * self.rate
        
        if self.minimum_amount > 0 and amount < self.minimum_amount:
            amount = self.minimum_amount
        
        if self.maximum_amount and amount > self.maximum_amount:
            amount = self.maximum_amount
        
        return amount


class StatutoryDeduction(AuditBaseModel):
    """Records of statutory deductions applied to payroll lines."""
    payroll_line = models.ForeignKey(
        PayrollLine, on_delete=models.CASCADE, related_name='statutory_deductions'
    )
    template = models.ForeignKey(
        StatutoryDeductionTemplate, on_delete=models.PROTECT,
        related_name='deductions'
    )
    employee_amount = models.DecimalField(max_digits=12, decimal_places=2)
    employer_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    is_employer_contribution = models.BooleanField(default=True)
    
    class Meta:
        unique_together = ['payroll_line', 'template']
    
    def __str__(self):
        return f"{self.template.name}: {self.employee_amount}"


class Payslip(AuditBaseModel):
    STATUS_CHOICES = [
        ('Generated', 'Generated'),
        ('Sent', 'Sent'),
        ('Viewed', 'Viewed'),
    ]
    
    payroll_line = models.OneToOneField(PayrollLine, on_delete=models.CASCADE, related_name='payslip')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Generated')
    
    generated_date = models.DateTimeField(auto_now_add=True)
    sent_date = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Payslip - {self.payroll_line.employee}"


# =============================================================================
# PERFORMANCE MANAGEMENT
# =============================================================================

class PerformanceCycle(AuditBaseModel):
    STATUS_CHOICES = [
        ('Draft', 'Draft'),
        ('Active', 'Active'),
        ('Closed', 'Closed'),
    ]
    
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=20, unique=True)
    
    start_date = models.DateField()
    end_date = models.DateField()
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Draft')
    
    self_review_enabled = models.BooleanField(default=True)
    peer_review_enabled = models.BooleanField(default=False)
    manager_review_enabled = models.BooleanField(default=True)
    
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class PerformanceGoal(AuditBaseModel):
    STATUS_CHOICES = [
        ('Draft', 'Draft'),
        ('Active', 'Active'),
        ('Completed', 'Completed'),
        ('Cancelled', 'Cancelled'),
    ]
    
    GOAL_TYPE = [
        ('Individual', 'Individual'),
        ('Team', 'Team'),
        ('Department', 'Department'),
        ('Organizational', 'Organizational'),
    ]
    
    title = models.CharField(max_length=200)
    description = models.TextField()
    
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='performance_goals')
    cycle = models.ForeignKey(PerformanceCycle, on_delete=models.SET_NULL, null=True, blank=True, related_name='goals')
    
    goal_type = models.CharField(max_length=20, choices=GOAL_TYPE, default='Individual')
    
    start_date = models.DateField()
    target_date = models.DateField()
    completion_date = models.DateField(null=True, blank=True)
    
    progress = models.PositiveIntegerField(default=0, help_text="0-100%")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Draft')
    
    weight = models.DecimalField(max_digits=5, decimal_places=2, default=10, help_text="Weight in performance calculation")
    
    key_results = models.JSONField(default=list, help_text="List of key results")
    
    def __str__(self):
        return f"{self.employee} - {self.title}"


class PerformanceReview(AuditBaseModel):
    STATUS_CHOICES = [
        ('Draft', 'Draft'),
        ('Self Review', 'Self Review'),
        ('Manager Review', 'Manager Review'),
        ('Calibration', 'Calibration'),
        ('Completed', 'Completed'),
    ]
    
    REVIEW_TYPE = [
        ('Self', 'Self Review'),
        ('Manager', 'Manager Review'),
        ('Peer', 'Peer Review'),
        ('360', '360 Degree'),
    ]
    
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='performance_reviews')
    cycle = models.ForeignKey(PerformanceCycle, on_delete=models.CASCADE, related_name='reviews')
    
    review_type = models.CharField(max_length=20, choices=REVIEW_TYPE)
    reviewer = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviews_conducted')
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Draft')
    
    rating = models.DecimalField(max_digits=3, decimal_places=2, null=True, blank=True, help_text="1-5 rating")
    rating_category = models.CharField(max_length=20, choices=[
        ('1', '1 - Unsatisfactory'),
        ('2', '2 - Needs Improvement'),
        ('3', '3 - Meets Expectations'),
        ('4', '4 - Exceeds Expectations'),
        ('5', '5 - Outstanding'),
    ], blank=True)
    
    strengths = models.TextField(blank=True)
    areas_for_improvement = models.TextField(blank=True)
    comments = models.TextField(blank=True)
    
    goals_achieved = models.PositiveIntegerField(default=0)
    goals_total = models.PositiveIntegerField(default=0)
    
    submitted_date = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.employee} - {self.cycle.name} - {self.review_type}"


class Competency(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=50, choices=[
        ('Technical', 'Technical'),
        ('Leadership', 'Leadership'),
        ('Communication', 'Communication'),
        ('Problem Solving', 'Problem Solving'),
        ('Teamwork', 'Teamwork'),
        ('Other', 'Other'),
    ])
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class CompetencyRating(models.Model):
    review = models.ForeignKey(PerformanceReview, on_delete=models.CASCADE, related_name='competency_ratings')
    competency = models.ForeignKey(Competency, on_delete=models.CASCADE)
    rating = models.PositiveIntegerField(help_text="1-5 rating")
    comments = models.TextField(blank=True)

    class Meta:
        unique_together = ['review', 'competency']


class Promotion(AuditBaseModel):
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Approved', 'Approved'),
        ('Rejected', 'Rejected'),
        ('Implemented', 'Implemented'),
    ]
    
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='promotions')
    
    from_position = models.ForeignKey(Position, on_delete=models.SET_NULL, null=True, related_name='promotions_from')
    to_position = models.ForeignKey(Position, on_delete=models.SET_NULL, null=True, related_name='promotions_to')
    
    from_salary = models.DecimalField(max_digits=12, decimal_places=2)
    to_salary = models.DecimalField(max_digits=12, decimal_places=2)
    
    effective_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    
    reason = models.TextField()
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='promotions_approved')
    approved_date = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.employee} - {self.from_position} to {self.to_position}"


# =============================================================================
# TRAINING & DEVELOPMENT
# =============================================================================

class TrainingProgram(AuditBaseModel):
    STATUS_CHOICES = [
        ('Draft', 'Draft'),
        ('Active', 'Active'),
        ('Completed', 'Completed'),
        ('Cancelled', 'Cancelled'),
    ]
    
    DELIVERY_METHOD = [
        ('In-Person', 'In-Person'),
        ('Online', 'Online'),
        ('Hybrid', 'Hybrid'),
    ]
    
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=20, unique=True)
    description = models.TextField()
    
    program_type = models.CharField(max_length=50, choices=[
        ('Technical', 'Technical'),
        ('Soft Skills', 'Soft Skills'),
        ('Compliance', 'Compliance'),
        ('Leadership', 'Leadership'),
        ('Product', 'Product'),
        ('Safety', 'Safety'),
        ('Other', 'Other'),
    ])
    
    delivery_method = models.CharField(max_length=20, choices=DELIVERY_METHOD, default='In-Person')
    
    duration_hours = models.PositiveIntegerField(default=0)
    max_participants = models.PositiveIntegerField(default=0)
    
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    registration_deadline = models.DateField(null=True, blank=True)
    
    trainer_name = models.CharField(max_length=200, blank=True)
    trainer_contact = models.CharField(max_length=200, blank=True)
    location = models.CharField(max_length=200, blank=True)
    
    cost_per_participant = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    objectives = models.TextField(blank=True)
    prerequisites = models.TextField(blank=True)
    materials = models.TextField(blank=True)
    
    certificate_enabled = models.BooleanField(default=False)
    certificate_template = models.CharField(max_length=200, blank=True)
    
    department = models.ForeignKey(
        Department, on_delete=models.SET_NULL, null=True, blank=True, related_name='training_programs'
    )

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Draft')
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class TrainingEnrollment(AuditBaseModel):
    STATUS_CHOICES = [
        ('Registered', 'Registered'),
        ('Attended', 'Attended'),
        ('Completed', 'Completed'),
        ('Failed', 'Failed'),
        ('Cancelled', 'Cancelled'),
        ('No Show', 'No Show'),
    ]
    
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='training_enrollments')
    program = models.ForeignKey(TrainingProgram, on_delete=models.CASCADE, related_name='enrollments')
    
    registration_date = models.DateField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Registered')
    
    attendance_date = models.DateField(null=True, blank=True)
    completion_date = models.DateField(null=True, blank=True)
    
    score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, help_text="Assessment score")
    passed = models.BooleanField(default=False)
    
    feedback = models.TextField(blank=True)
    certificate_issued = models.BooleanField(default=False)
    certificate_number = models.CharField(max_length=50, blank=True)

    class Meta:
        unique_together = ['employee', 'program']

    def __str__(self):
        return f"{self.employee} - {self.program.name}"


class Skill(AuditBaseModel):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20, unique=True)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=50)
    
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class EmployeeSkill(AuditBaseModel):
    PROFICIENCY_LEVEL = [
        ('1', 'Beginner'),
        ('2', 'Elementary'),
        ('3', 'Intermediate'),
        ('4', 'Advanced'),
        ('5', 'Expert'),
    ]
    
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='skills')
    skill = models.ForeignKey(Skill, on_delete=models.CASCADE)
    
    proficiency_level = models.CharField(max_length=20, choices=PROFICIENCY_LEVEL)
    years_experience = models.PositiveIntegerField(default=0)
    
    certified = models.BooleanField(default=False)
    certification_date = models.DateField(null=True, blank=True)
    certification_expiry = models.DateField(null=True, blank=True)
    
    notes = models.TextField(blank=True)

    class Meta:
        unique_together = ['employee', 'skill']

    def __str__(self):
        return f"{self.employee} - {self.skill.name}"


class TrainingPlan(AuditBaseModel):
    STATUS_CHOICES = [
        ('Draft', 'Draft'),
        ('Active', 'Active'),
        ('Completed', 'Completed'),
    ]
    
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='training_plans')
    
    start_date = models.DateField()
    end_date = models.DateField()
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Draft')
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} - {self.employee}"


class TrainingPlanLine(models.Model):
    training_plan = models.ForeignKey(TrainingPlan, on_delete=models.CASCADE, related_name='lines')
    program = models.ForeignKey(TrainingProgram, on_delete=models.CASCADE)
    sequence = models.PositiveIntegerField(default=1)
    due_date = models.DateField(null=True, blank=True)
    completed = models.BooleanField(default=False)

    class Meta:
        ordering = ['sequence']


# =============================================================================
# COMPLIANCE & POLICY MANAGEMENT
# =============================================================================

class Policy(AuditBaseModel):
    STATUS_CHOICES = [
        ('Draft', 'Draft'),
        ('Active', 'Active'),
        ('Under Review', 'Under Review'),
        ('Expired', 'Expired'),
        ('Archived', 'Archived'),
    ]
    
    CATEGORY_CHOICES = [
        ('HR', 'Human Resources'),
        ('IT', 'Information Technology'),
        ('Finance', 'Finance'),
        ('Operations', 'Operations'),
        ('Legal', 'Legal'),
        ('Safety', 'Safety'),
        ('Ethics', 'Ethics'),
        ('Other', 'Other'),
    ]
    
    title = models.CharField(max_length=200)
    code = models.CharField(max_length=20, unique=True)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES)
    version = models.CharField(max_length=20, default='1.0')
    
    description = models.TextField()
    content = models.TextField()
    
    effective_date = models.DateField()
    expiry_date = models.DateField(null=True, blank=True)
    
    requires_acknowledgement = models.BooleanField(default=True)
    acknowledgment_deadline_days = models.PositiveIntegerField(default=30)
    
    applies_to_all = models.BooleanField(default=False)
    departments = models.ManyToManyField('Department', blank=True, related_name='policies')
    positions = models.ManyToManyField('Position', blank=True, related_name='policies')
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Draft')
    is_active = models.BooleanField(default=True)
    
    attachment = models.FileField(upload_to='policies/attachments/', null=True, blank=True)

    def __str__(self):
        return f"{self.title} (v{self.version})"


class PolicyAcknowledgement(AuditBaseModel):
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Acknowledged', 'Acknowledged'),
        ('Declined', 'Declined'),
    ]
    
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='policy_acknowledgements')
    policy = models.ForeignKey(Policy, on_delete=models.CASCADE, related_name='acknowledgements')
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    acknowledged_date = models.DateTimeField(null=True, blank=True)
    
    comments = models.TextField(blank=True)
    
    class Meta:
        unique_together = ['employee', 'policy']


class ComplianceRecord(AuditBaseModel):
    COMPLIANCE_TYPE = [
        ('Regulatory', 'Regulatory'),
        ('Legal', 'Legal'),
        ('Internal', 'Internal'),
        ('Industry Standard', 'Industry Standard'),
        ('Certification', 'Certification'),
    ]
    
    STATUS_CHOICES = [
        ('Compliant', 'Compliant'),
        ('Non-Compliant', 'Non-Compliant'),
        ('In Progress', 'In Progress'),
        ('Pending Review', 'Pending Review'),
        ('Expired', 'Expired'),
    ]
    
    title = models.CharField(max_length=200)
    code = models.CharField(max_length=20, unique=True)
    compliance_type = models.CharField(max_length=50, choices=COMPLIANCE_TYPE)
    
    description = models.TextField()
    
    effective_date = models.DateField()
    expiry_date = models.DateField(null=True, blank=True)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending Review')
    
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='compliance_records')
    
    requirements = models.JSONField(default=list, help_text="List of compliance requirements")
    evidence = models.JSONField(default=list, help_text="Evidence documents/links")
    
    last_audit_date = models.DateField(null=True, blank=True)
    next_audit_date = models.DateField(null=True, blank=True)
    
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.title} - {self.get_status_display()}"


class ComplianceTask(AuditBaseModel):
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('In Progress', 'In Progress'),
        ('Completed', 'Completed'),
        ('Overdue', 'Overdue'),
    ]
    
    compliance_record = models.ForeignKey(ComplianceRecord, on_delete=models.CASCADE, related_name='tasks')
    
    title = models.CharField(max_length=200)
    description = models.TextField()
    
    due_date = models.DateField()
    completed_date = models.DateField(null=True, blank=True)
    
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='compliance_tasks')
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    
    evidence = models.TextField(blank=True)

    def __str__(self):
        return f"{self.compliance_record.title} - {self.title}"


class AuditLog(AuditBaseModel):
    ACTION_TYPES = [
        ('Create', 'Create'),
        ('Read', 'Read'),
        ('Update', 'Update'),
        ('Delete', 'Delete'),
        ('Login', 'Login'),
        ('Logout', 'Logout'),
        ('Export', 'Export'),
        ('Print', 'Print'),
        ('Other', 'Other'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='audit_logs')
    
    action_type = models.CharField(max_length=20, choices=ACTION_TYPES)
    module = models.CharField(max_length=50)
    
    object_id = models.PositiveIntegerField(null=True, blank=True)
    object_repr = models.CharField(max_length=200, blank=True)
    
    changes = models.JSONField(default=dict, help_text="Field changes in JSON format")
    
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user', '-timestamp']),
            models.Index(fields=['module', '-timestamp']),
        ]

    def __str__(self):
        return f"{self.user} - {self.action_type} - {self.module}"


# =============================================================================
# EXIT & OFFBOARDING
# =============================================================================

class ExitRequest(AuditBaseModel):
    STATUS_CHOICES = [
        ('Draft', 'Draft'),
        ('Pending', 'Pending'),
        ('Approved', 'Approved'),
        ('Rejected', 'Rejected'),
        ('Processed', 'Processed'),
        ('Cancelled', 'Cancelled'),
    ]
    
    EXIT_TYPE = [
        ('Resignation', 'Resignation'),
        ('Termination', 'Termination'),
        ('Retirement', 'Retirement'),
        ('End of Contract', 'End of Contract'),
        ('Layoff', 'Layoff'),
        ('Other', 'Other'),
    ]
    
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='exit_requests')
    
    exit_type = models.CharField(max_length=20, choices=EXIT_TYPE)
    
    requested_date = models.DateField(help_text="Date employee requested to leave")
    last_working_date = models.DateField()
    
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Draft')
    
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='exit_approved')
    approved_date = models.DateTimeField(null=True, blank=True)
    
    manager_comments = models.TextField(blank=True)

    def __str__(self):
        return f"{self.employee} - {self.exit_type}"


class ExitInterview(AuditBaseModel):
    STATUS_CHOICES = [
        ('Scheduled', 'Scheduled'),
        ('Completed', 'Completed'),
        ('Cancelled', 'Cancelled'),
        ('No Show', 'No Show'),
    ]
    
    exit_request = models.ForeignKey(ExitRequest, on_delete=models.CASCADE, related_name='interviews')
    
    interviewer = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='exit_interviews_conducted')
    
    scheduled_date = models.DateTimeField()
    completed_date = models.DateTimeField(null=True, blank=True)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Scheduled')
    
    # Interview feedback
    reason_for_leaving = models.TextField(blank=True)
    satisfaction_rating = models.PositiveIntegerField(null=True, blank=True, help_text="1-10 rating")
    
    feedback_questions = models.JSONField(default=list, help_text="Custom feedback questions and answers")
    
    overall_feedback = models.TextField(blank=True)
    
    would_recommend = models.BooleanField(null=True, blank=True, help_text="Would recommend company")
    
    exit_interviewer_notes = models.TextField(blank=True)

    def __str__(self):
        return f"Exit Interview - {self.exit_request.employee}"


class ExitClearance(AuditBaseModel):
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('In Progress', 'In Progress'),
        ('Completed', 'Completed'),
        ('Waived', 'Waived'),
    ]
    
    CATEGORY_CHOICES = [
        ('IT', 'IT & Systems'),
        ('Finance', 'Finance & Accounts'),
        ('HR', 'HR & Documents'),
        ('Operations', 'Operations & Assets'),
        ('Legal', 'Legal'),
        ('Security', 'Security'),
    ]
    
    exit_request = models.ForeignKey(ExitRequest, on_delete=models.CASCADE, related_name='clearances')
    
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES)
    department = models.ForeignKey('Department', on_delete=models.SET_NULL, null=True)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    
    checklist_items = models.JSONField(default=list, help_text="List of clearance items")
    completed_items = models.JSONField(default=list)
    
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='clearances_assigned')
    
    completed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='clearances_completed')
    completed_date = models.DateTimeField(null=True, blank=True)
    
    remarks = models.TextField(blank=True)

    class Meta:
        unique_together = ['exit_request', 'category']

    def __str__(self):
        return f"{self.exit_request.employee} - {self.category}"


class FinalSettlement(AuditBaseModel):
    STATUS_CHOICES = [
        ('Calculated', 'Calculated'),
        ('Approved', 'Approved'),
        ('Paid', 'Paid'),
        ('Disputed', 'Disputed'),
    ]
    
    exit_request = models.OneToOneField(ExitRequest, on_delete=models.CASCADE, related_name='settlement')
    
    # Salary & Benefits
    basic_salary = models.DecimalField(max_digits=12, decimal_places=2)
    pending_salary_days = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    pending_salary_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Leave encashment
    leave_balance_days = models.PositiveIntegerField(default=0)
    leave_encashment_rate = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    leave_encashment_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Deductions
    notice_period_deduction = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    advances_deduction = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    other_deductions = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Benefits
    bonus_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    gratuity_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    other_benefits = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Totals
    total_deductions = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_payable = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Calculated')
    
    payment_date = models.DateField(null=True, blank=True)
    payment_reference = models.CharField(max_length=50, blank=True)
    
    calculated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='settlements_calculated')
    calculated_date = models.DateTimeField(auto_now_add=True)
    
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='settlements_approved')
    approved_date = models.DateTimeField(null=True, blank=True)
    
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"Settlement - {self.exit_request.employee}"

    def calculate(self):
        self.total_deductions = (
            self.notice_period_deduction + 
            self.advances_deduction + 
            self.other_deductions
        )
        gross = (
            self.pending_salary_amount + 
            self.leave_encashment_amount + 
            self.bonus_amount + 
            self.gratuity_amount + 
            self.other_benefits
        )
        self.total_payable = gross - self.total_deductions
        return self


class ExperienceCertificate(AuditBaseModel):
    exit_request = models.OneToOneField(ExitRequest, on_delete=models.CASCADE, related_name='experience_certificate')
    
    certificate_number = models.CharField(max_length=50, unique=True)
    issue_date = models.DateField()
    
    # Certificate content
    employee_name = models.CharField(max_length=200)
    father_name = models.CharField(max_length=100, blank=True)
    designation = models.CharField(max_length=100)
    department = models.CharField(max_length=100)
    
    joining_date = models.DateField()
    relieving_date = models.DateField()
    total_experience_years = models.DecimalField(max_digits=4, decimal_places=2)
    
    conduct = models.CharField(max_length=50, choices=[
        ('Excellent', 'Excellent'),
        ('Very Good', 'Very Good'),
        ('Good', 'Good'),
        ('Satisfactory', 'Satisfactory'),
    ], default='Good')
    
    reason_for_leaving = models.TextField(blank=True)
    
    is_issued = models.BooleanField(default=False)
    issued_date = models.DateTimeField(null=True, blank=True)
    
    template_content = models.TextField(blank=True)
    
    digital_signature = models.ImageField(upload_to='certificates/signatures/', null=True, blank=True)

    def __str__(self):
        return f"Experience Certificate - {self.employee_name}"


class AssetReturn(AuditBaseModel):
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Returned', 'Returned'),
        ('Damaged', 'Damaged'),
        ('Lost', 'Lost'),
    ]
    
    exit_request = models.ForeignKey(ExitRequest, on_delete=models.CASCADE, related_name='asset_returns')
    
    asset_name = models.CharField(max_length=200)
    asset_description = models.TextField(blank=True)
    asset_tag = models.CharField(max_length=50, blank=True)
    
    assigned_date = models.DateField(null=True, blank=True)
    
    return_due_date = models.DateField()
    return_actual_date = models.DateField(null=True, blank=True)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    
    condition = models.TextField(blank=True)
    remarks = models.TextField(blank=True)
    
    verified_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assets_verified')

    def __str__(self):
        return f"{self.asset_name} - {self.exit_request.employee}"


# =============================================================================
# PENSION & STATUTORY DEDUCTIONS — Nigeria CPS Compliance
# =============================================================================

class PensionFundAdministrator(models.Model):
    """
    PENCOM-registered Pension Fund Administrator (PFA) registry.
    Employees select a PFA and provide their RSA PIN.
    Employer remits pension contributions to the employee's PFA monthly.
    """
    name         = models.CharField(max_length=200)
    pfa_code     = models.CharField(
        max_length=10, unique=True,
        help_text="PENCOM registration code",
    )
    bank_name    = models.CharField(max_length=100)
    bank_account = models.CharField(max_length=20)
    sort_code    = models.CharField(max_length=10, blank=True, default='')
    is_active    = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Pension Fund Administrator (PFA)'
        verbose_name_plural = 'Pension Fund Administrators (PFAs)'

    def __str__(self):
        return f"{self.pfa_code} - {self.name}"


class EmployeePensionProfile(models.Model):
    """
    Employee's contributory pension scheme details.
    Per the Pension Reform Act 2014:
    - Employee contributes minimum 8% of (basic + housing + transport)
    - Employer contributes minimum 10% of (basic + housing + transport)
    """
    employee      = models.OneToOneField(
        Employee, on_delete=models.PROTECT, related_name='pension_profile',
    )
    rsa_pin       = models.CharField(
        max_length=20, unique=True,
        help_text="Retirement Savings Account PIN (from PENCOM)",
    )
    pfa           = models.ForeignKey(
        PensionFundAdministrator, on_delete=models.PROTECT,
        related_name='employees',
    )
    enrollment_date = models.DateField()
    is_active     = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Employee Pension Profile'
        verbose_name_plural = 'Employee Pension Profiles'

    def __str__(self):
        return f"{self.employee} - RSA: {self.rsa_pin}"


class PensionConfiguration(models.Model):
    """
    State-level Contributory Pension Scheme (CPS) configuration.
    Per Pension Reform Act 2014 (as amended):
    - Minimum employer: 10% of (basic + housing + transport)
    - Minimum employee: 8% of (basic + housing + transport)
    - Remittance to PFA within 7 working days after payroll
    """
    employer_rate           = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('10.00'),
        help_text="Employer contribution rate (minimum 10%)",
    )
    employee_rate           = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('8.00'),
        help_text="Employee contribution rate (minimum 8%)",
    )
    qualifying_components   = models.JSONField(
        default=list,
        help_text='Salary components for pension base, e.g. ["basic", "housing", "transport"]',
    )
    remittance_deadline_days = models.IntegerField(
        default=7,
        help_text="Days after payroll to remit to PFA (7 working days per PRA 2014)",
    )
    effective_date          = models.DateField()
    is_current              = models.BooleanField(default=True)

    class Meta:
        ordering = ['-effective_date']
        verbose_name = 'Pension Configuration'
        verbose_name_plural = 'Pension Configurations'

    def __str__(self):
        return f"CPS: Employer {self.employer_rate}% + Employee {self.employee_rate}% (from {self.effective_date})"


class PensionRemittance(models.Model):
    """
    Monthly pension contribution remittance to PFA.
    Grouped by PFA for batch remittance via TSA.
    """
    STATUS_CHOICES = [
        ('PENDING',    'Pending'),
        ('INITIATED',  'Remittance Initiated'),
        ('REMITTED',   'Remitted'),
        ('FAILED',     'Failed'),
    ]

    payroll_run      = models.ForeignKey(
        PayrollRun, on_delete=models.PROTECT,
        related_name='pension_remittances',
    )
    pfa              = models.ForeignKey(
        PensionFundAdministrator, on_delete=models.PROTECT,
        related_name='remittances',
    )
    employee_count   = models.IntegerField()
    employer_amount  = models.DecimalField(max_digits=20, decimal_places=2)
    employee_amount  = models.DecimalField(max_digits=20, decimal_places=2)
    total_amount     = models.DecimalField(max_digits=20, decimal_places=2)
    remittance_date  = models.DateField(null=True, blank=True)
    payment_voucher  = models.ForeignKey(
        'accounting.PaymentVoucherGov', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='pension_remittances',
    )
    status           = models.CharField(
        max_length=15, choices=STATUS_CHOICES, default='PENDING',
    )
    created_at       = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Pension Remittance'
        verbose_name_plural = 'Pension Remittances'
        unique_together = ['payroll_run', 'pfa']

    def __str__(self):
        return f"Pension to {self.pfa.name} - NGN {self.total_amount:,.2f}"

    def save(self, *args, **kwargs):
        self.total_amount = self.employer_amount + self.employee_amount
        super().save(*args, **kwargs)


class NigeriaTaxBracket(models.Model):
    """
    Nigeria PAYE Tax Brackets per the Personal Income Tax Act (PITAM).
    Updated per Finance Act amendments.

    Current brackets (Finance Act 2020):
      First  NGN 300,000  ->  7%
      Next   NGN 300,000  ->  11%
      Next   NGN 500,000  ->  15%
      Next   NGN 500,000  ->  19%
      Next   NGN 1,600,000 -> 21%
      Above  NGN 3,200,000 -> 24%

    Plus: 1% minimum tax if PAYE < 1% of gross income.
    """
    lower_bound  = models.DecimalField(max_digits=15, decimal_places=2)
    upper_bound  = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True,
        help_text="Null = unlimited (highest bracket)",
    )
    rate         = models.DecimalField(
        max_digits=5, decimal_places=2,
        help_text="Tax rate as percentage",
    )
    effective_date = models.DateField()
    is_current   = models.BooleanField(default=True)

    class Meta:
        ordering = ['lower_bound']
        verbose_name = 'Nigeria PAYE Tax Bracket'
        verbose_name_plural = 'Nigeria PAYE Tax Brackets'

    def __str__(self):
        upper = f"NGN {self.upper_bound:,.2f}" if self.upper_bound else "Above"
        return f"NGN {self.lower_bound:,.2f} - {upper} @ {self.rate}%"
