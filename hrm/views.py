import logging

from rest_framework import viewsets, status

logger = logging.getLogger(__name__)
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.filters import SearchFilter, OrderingFilter
from core.permissions import IsApprover
from django.utils import timezone
from django.db.models import Count, Sum, Q
from decimal import Decimal
from datetime import timedelta
from .models import (
    Department, Position, Employee, LeaveType, LeaveRequest, LeaveBalance, Attendance, Holiday,
    JobPost, Candidate, Interview, OnboardingTask, OnboardingProgress,
    SalaryStructure, SalaryComponent, SalaryStructureTemplate, PayrollPeriod, PayrollRun, PayrollLine, PayrollEarning, PayrollDeduction, Payslip,
    PerformanceCycle, PerformanceGoal, PerformanceReview, Competency, Promotion,
    TrainingProgram, TrainingEnrollment, Skill, EmployeeSkill, TrainingPlan,
    Policy, PolicyAcknowledgement, ComplianceRecord, ComplianceTask, AuditLog,
    ExitRequest, ExitInterview, ExitClearance, FinalSettlement, ExperienceCertificate, AssetReturn,
    StatutoryDeductionTemplate, StatutoryDeduction
)
from .serializers import (
    DepartmentSerializer, PositionSerializer, EmployeeSerializer, EmployeeListSerializer,
    LeaveTypeSerializer, LeaveRequestSerializer, LeaveBalanceSerializer, AttendanceSerializer, HolidaySerializer,
    JobPostSerializer, CandidateSerializer, InterviewSerializer, OnboardingTaskSerializer, OnboardingProgressSerializer,
    SalaryStructureSerializer, SalaryComponentSerializer, PayrollPeriodSerializer, PayrollRunSerializer, PayrollLineSerializer, PayslipSerializer,
    PerformanceCycleSerializer, PerformanceGoalSerializer, PerformanceReviewSerializer, CompetencySerializer, PromotionSerializer,
    TrainingProgramSerializer, TrainingEnrollmentSerializer, SkillSerializer, EmployeeSkillSerializer, TrainingPlanSerializer,
    PolicySerializer, PolicyAcknowledgementSerializer, ComplianceRecordSerializer, ComplianceTaskSerializer, AuditLogSerializer,
    ExitRequestSerializer, ExitInterviewSerializer, ExitClearanceSerializer, FinalSettlementSerializer, ExperienceCertificateSerializer, AssetReturnSerializer,
    StatutoryDeductionTemplateSerializer, StatutoryDeductionSerializer
)
class HRMPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100
class DepartmentViewSet(viewsets.ModelViewSet):
    queryset = Department.objects.all()
    serializer_class = DepartmentSerializer
    pagination_class = HRMPagination
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ['name', 'code']
    ordering_fields = ['name', 'code']
class PositionViewSet(viewsets.ModelViewSet):
    queryset = Position.objects.all().select_related('department')
    serializer_class = PositionSerializer
    filterset_fields = ['department', 'grade', 'is_active']
    pagination_class = HRMPagination
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ['title', 'code']
    ordering_fields = ['title', 'grade']
class EmployeeViewSet(viewsets.ModelViewSet):
    queryset = Employee.objects.all().select_related('user', 'department', 'position', 'supervisor')
    serializer_class = EmployeeSerializer
    filterset_fields = ['department', 'status', 'employee_type']
    search_fields = ['employee_number', 'user__first_name', 'user__last_name']
    pagination_class = HRMPagination
    filter_backends = [SearchFilter, OrderingFilter]
    ordering_fields = ['employee_number', 'hire_date']

    def get_serializer_class(self):
        if self.action == 'list':
            return EmployeeListSerializer
        return EmployeeSerializer

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser or user.has_perm('hrm.view_all_employees'):
            return Employee.objects.all().select_related('user', 'department', 'position', 'supervisor')
        return Employee.objects.filter(user=user).select_related('user', 'department', 'position', 'supervisor')

    @action(detail=False, methods=['get'])
    def dashboard(self, request):
        total = Employee.objects.count()
        active = Employee.objects.filter(status='Active').count()
        on_leave = Employee.objects.filter(status='On Leave').count()
        
        by_department = Employee.objects.values('department__id', 'department__name').annotate(count=Count('id'))
        
        by_status = Employee.objects.values('status').annotate(count=Count('id'))
        
        return Response({
            'total_employees': total,
            'active_employees': active,
            'on_leave': on_leave,
            'by_department': list(by_department),
            'by_status': list(by_status)
        })
class LeaveTypeViewSet(viewsets.ModelViewSet):
    queryset = LeaveType.objects.all()
    serializer_class = LeaveTypeSerializer
    pagination_class = HRMPagination
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ['name', 'code']
    ordering_fields = ['name']
class LeaveRequestViewSet(viewsets.ModelViewSet):
    queryset = LeaveRequest.objects.all().select_related('employee__user', 'leave_type', 'approved_by')
    serializer_class = LeaveRequestSerializer
    filterset_fields = ['status', 'leave_type', 'employee']
    pagination_class = HRMPagination
    filter_backends = [SearchFilter, OrderingFilter]
    ordering_fields = ['-start_date']

    def get_permissions(self):
        if self.action == 'approve':
            return [IsApprover()]
        return super().get_permissions()

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser or user.has_perm('hrm.view_all_leave_requests'):
            return LeaveRequest.objects.all().select_related('employee__user', 'leave_type', 'approved_by')
        return LeaveRequest.objects.filter(employee__user=user).select_related('employee__user', 'leave_type', 'approved_by')

    @action(detail=True, methods=['post'])
    def submit_for_approval(self, request, pk=None):
        """Submit Leave Request for approval through the centralized workflow engine."""
        from workflow.views import auto_route_approval
        leave = self.get_object()
        if leave.status not in ['Draft', 'Rejected']:
            return Response(
                {"error": "Only Draft or Rejected leave requests can be submitted."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = auto_route_approval(
            leave, 'leaverequest', request,
            title=f"Leave: {leave.employee} - {leave.leave_type} ({leave.start_date} to {leave.end_date})",
            amount=None,  # Leave requests don't have monetary amounts
        )

        if result.get('auto_approved'):
            leave.status = 'Approved'
            msg = "Leave request auto-approved."
        else:
            leave.status = 'Pending'
            msg = "Leave request submitted for approval."

        leave.save()
        return Response({"status": msg, "approval_id": result.get('approval_id')})

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        leave_request = self.get_object()
        if leave_request.status != 'Pending':
            return Response({'error': 'Only pending requests can be approved'}, status=status.HTTP_400_BAD_REQUEST)
        
        if leave_request.employee.user == request.user:
            return Response({'error': 'You cannot approve your own leave request'}, status=status.HTTP_400_BAD_REQUEST)
        
        leave_request.status = 'Approved'
        leave_request.approved_by = request.user
        leave_request.approved_date = timezone.now()
        leave_request.save()
        
        return Response(LeaveRequestSerializer(leave_request).data)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        leave_request = self.get_object()
        if leave_request.status != 'Pending':
            return Response({'error': 'Only pending requests can be rejected'}, status=status.HTTP_400_BAD_REQUEST)
        
        leave_request.status = 'Rejected'
        leave_request.approved_by = request.user
        leave_request.comments = request.data.get('comment', '')
        leave_request.save()
        
        return Response(LeaveRequestSerializer(leave_request).data)

    @action(detail=False, methods=['get'])
    def pending_count(self, request):
        count = LeaveRequest.objects.filter(status='Pending').count()
        return Response({'count': count})
class LeaveBalanceViewSet(viewsets.ModelViewSet):
    queryset = LeaveBalance.objects.all().select_related('employee__user', 'leave_type')
    serializer_class = LeaveBalanceSerializer
    filterset_fields = ['employee', 'leave_type', 'year']
    pagination_class = HRMPagination
    filter_backends = [SearchFilter, OrderingFilter]
    ordering_fields = ['-year', 'leave_type__name']

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser or user.has_perm('hrm.view_all_leave_balances'):
            return LeaveBalance.objects.all().select_related('employee__user', 'leave_type')
        return LeaveBalance.objects.filter(employee__user=user).select_related('employee__user', 'leave_type')
class AttendanceViewSet(viewsets.ModelViewSet):
    queryset = Attendance.objects.all().select_related('employee__user')
    serializer_class = AttendanceSerializer
    filterset_fields = ['employee', 'date', 'status']
    pagination_class = HRMPagination
    filter_backends = [SearchFilter, OrderingFilter]
    ordering_fields = ['-date']

    @action(detail=False, methods=['post'])
    def bulk_mark(self, request):
        employee_ids = request.data.get('employee_ids', [])
        date = request.data.get('date', timezone.now().date())
        attendance_status = request.data.get('status', 'Present')
        
        existing = Attendance.objects.filter(employee_id__in=employee_ids, date=date).values_list('employee_id', flat=True)
        new_employee_ids = [eid for eid in employee_ids if eid not in existing]
        
        new_attendances = [
            Attendance(employee_id=emp_id, date=date, status=attendance_status)
            for emp_id in new_employee_ids
        ]
        
        Attendance.objects.bulk_create(new_attendances)
        
        return Response({
            'created': len(new_attendances),
            'existing': len(existing)
        })

    @action(detail=False, methods=['get'])
    def today_summary(self, request):
        today = timezone.now().date()
        summary = Attendance.objects.filter(date=today).values('status').annotate(count=Count('id'))
        return Response({'date': today, 'summary': list(summary)})
# =============================================================================
# HOLIDAY VIEWS
# =============================================================================

class HolidayViewSet(viewsets.ModelViewSet):
    queryset = Holiday.objects.all()
    serializer_class = HolidaySerializer
    pagination_class = HRMPagination
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ['name']
    ordering_fields = ['date']

    @action(detail=False, methods=['get'])
    def upcoming(self, request):
        today = timezone.now().date()
        holidays = Holiday.objects.filter(date__gte=today, is_active=True).order_by('date')[:10]
        return Response(HolidaySerializer(holidays, many=True).data)
# =============================================================================
# RECRUITMENT & ONBOARDING VIEWS
# =============================================================================

class JobPostViewSet(viewsets.ModelViewSet):
    queryset = JobPost.objects.all().select_related('department')
    serializer_class = JobPostSerializer
    filterset_fields = ['department', 'status', 'job_type', 'is_active']
    pagination_class = HRMPagination
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ['title', 'code', 'description']
    ordering_fields = ['title', 'created_at']

    @action(detail=False, methods=['get'])
    def dashboard(self, request):
        total = JobPost.objects.count()
        active = JobPost.objects.filter(status='Published', is_active=True).count()
        by_department = JobPost.objects.values('department__name').annotate(count=Count('id'))
        return Response({
            'total_posts': total,
            'active_posts': active,
            'by_department': list(by_department)
        })
class CandidateViewSet(viewsets.ModelViewSet):
    queryset = Candidate.objects.all().select_related('job_post__department')
    serializer_class = CandidateSerializer
    filterset_fields = ['job_post', 'status', 'source']
    pagination_class = HRMPagination
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ['first_name', 'last_name', 'email']
    ordering_fields = ['applied_date']

    @action(detail=False, methods=['get'])
    def funnel(self, request):
        funnel = Candidate.objects.values('status').annotate(count=Count('id'))
        return Response({'funnel': list(funnel)})
class InterviewViewSet(viewsets.ModelViewSet):
    queryset = Interview.objects.all().select_related('candidate__job_post', 'interviewer')
    serializer_class = InterviewSerializer
    filterset_fields = ['candidate', 'status', 'result']
    pagination_class = HRMPagination
    filter_backends = [SearchFilter, OrderingFilter]
    ordering_fields = ['scheduled_date']

    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        interview = self.get_object()
        interview.status = 'Completed'
        interview.result = request.data.get('result', 'Pending')
        interview.notes = request.data.get('notes', '')
        interview.rating = request.data.get('rating')
        interview.save()
        
        if interview.result in ['Pass', 'Fail']:
            candidate = interview.candidate
            if interview.result == 'Pass' and candidate.status == 'Interview':
                candidate.status = 'Assessment' if interview.interview_round < 3 else 'Offer'
            elif interview.result == 'Fail':
                candidate.status = 'Rejected'
            candidate.save()
        
        return Response(InterviewSerializer(interview).data)
class OnboardingTaskViewSet(viewsets.ModelViewSet):
    queryset = OnboardingTask.objects.all()
    serializer_class = OnboardingTaskSerializer
    filterset_fields = ['category', 'is_required', 'is_active']
    pagination_class = HRMPagination
class OnboardingProgressViewSet(viewsets.ModelViewSet):
    queryset = OnboardingProgress.objects.all().select_related('employee__user', 'task', 'assigned_to')
    serializer_class = OnboardingProgressSerializer
    filterset_fields = ['employee', 'status', 'task__category']
    pagination_class = HRMPagination

    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        progress = self.get_object()
        progress.status = 'Completed'
        progress.completed_date = timezone.now().date()
        progress.notes = request.data.get('notes', '')
        progress.save()
        return Response(OnboardingProgressSerializer(progress).data)
# =============================================================================
# PAYROLL VIEWS
# =============================================================================

class SalaryStructureViewSet(viewsets.ModelViewSet):
    queryset = SalaryStructure.objects.all()
    serializer_class = SalaryStructureSerializer
    pagination_class = HRMPagination
class SalaryComponentViewSet(viewsets.ModelViewSet):
    queryset = SalaryComponent.objects.all()
    serializer_class = SalaryComponentSerializer
    filterset_fields = ['component_type', 'is_active']
    pagination_class = HRMPagination
class PayrollPeriodViewSet(viewsets.ModelViewSet):
    queryset = PayrollPeriod.objects.all()
    serializer_class = PayrollPeriodSerializer
    filterset_fields = ['period_type', 'status']
    pagination_class = HRMPagination
    filter_backends = [OrderingFilter]
    ordering_fields = ['-start_date']
class PayrollRunViewSet(viewsets.ModelViewSet):
    queryset = PayrollRun.objects.all().select_related('period', 'processed_by', 'approved_by')
    serializer_class = PayrollRunSerializer
    filterset_fields = ['period', 'status']
    pagination_class = HRMPagination

    def get_permissions(self):
        if self.action == 'process':
            return [IsApprover('process')]
        if self.action == 'approve':
            return [IsApprover()]
        return super().get_permissions()

    @action(detail=True, methods=['post'])
    def process(self, request, pk=None):
        payroll_run = self.get_object()

        if payroll_run.status != 'Draft':
            return Response({'error': 'Payroll run already processed'}, status=status.HTTP_400_BAD_REQUEST)

        period = payroll_run.period

        # Calculate working days from period dates (exclude weekends)
        working_days = 0
        current = period.start_date
        while current <= period.end_date:
            if current.weekday() < 5:  # Mon-Fri
                working_days += 1
            current += timedelta(days=1)

        employees = Employee.objects.filter(status='Active').select_related('salary_structure')
        statutory_templates = list(StatutoryDeductionTemplate.objects.filter(is_active=True))
        payroll_lines = []
        earning_records = []
        deduction_records = []

        for employee in employees:
            basic = employee.base_salary or Decimal('0')
            total_earnings = basic
            total_deductions_amt = Decimal('0')
            tax_deduction = Decimal('0')
            pension_deduction = Decimal('0')
            other_deductions = Decimal('0')

            # Collect component amounts to create PayrollEarning/Deduction after bulk_create
            emp_earnings = []
            emp_deductions = []

            # Apply salary structure components if assigned
            if employee.salary_structure:
                templates = SalaryStructureTemplate.objects.filter(
                    salary_structure=employee.salary_structure,
                    is_active=True
                ).select_related('component')

                for template in templates:
                    comp = template.component
                    if not comp.is_active:
                        continue

                    # Calculate component amount
                    if comp.calculation_type == 'Percentage' and comp.percentage_of_basic:
                        amount = basic * comp.percentage_of_basic / Decimal('100')
                    elif comp.calculation_type == 'Fixed':
                        amount = comp.value or Decimal('0')
                    else:  # Variable — use component value as default
                        amount = comp.value or Decimal('0')

                    if amount <= 0:
                        continue

                    if comp.component_type == 'Earning':
                        total_earnings += amount
                        emp_earnings.append((comp, amount))
                    elif comp.component_type == 'Deduction':
                        total_deductions_amt += amount
                        if comp.is_taxable:
                            tax_deduction += amount
                        elif comp.is_pensionable:
                            pension_deduction += amount
                        else:
                            other_deductions += amount
                        emp_deductions.append((comp, amount))

            gross = total_earnings

            # Apply statutory deductions (NHIS, GETFL, Tier 1/2 Pension, Income Tax, etc.)
            statutory_deduction_records = []
            for tmpl in statutory_templates:
                applies_to = tmpl.applies_to_employment_types
                if applies_to and employee.employee_type not in applies_to:
                    continue

                employee_amount = tmpl.calculate_deduction(gross)
                if tmpl.employer_fixed and tmpl.employer_fixed > 0:
                    employer_amount = tmpl.employer_fixed
                elif tmpl.employer_rate and tmpl.employer_rate > 0:
                    employer_amount = gross * tmpl.employer_rate
                else:
                    employer_amount = Decimal('0')

                if employee_amount > 0 or employer_amount > 0:
                    total_deductions_amt += employee_amount
                    if tmpl.deduction_type in ('Tier1', 'Tier2'):
                        pension_deduction += employee_amount
                    elif tmpl.deduction_type == 'Income_Tax':
                        tax_deduction += employee_amount
                    else:
                        other_deductions += employee_amount
                    statutory_deduction_records.append((tmpl, employee_amount, employer_amount))

            net = gross - total_deductions_amt

            line = PayrollLine(
                payroll_run=payroll_run,
                employee=employee,
                basic_salary=basic,
                gross_salary=gross,
                total_earnings=total_earnings,
                total_deductions=total_deductions_amt,
                net_salary=net,
                tax_deduction=tax_deduction,
                pension_deduction=pension_deduction,
                other_deductions=other_deductions,
                working_days=working_days,
                days_worked=working_days,
                bank_name=employee.bank_name or '',
                bank_account=employee.bank_account or ''
            )
            payroll_lines.append((line, emp_earnings, emp_deductions, statutory_deduction_records))

        # Bulk create payroll lines
        PayrollLine.objects.bulk_create(pl for pl, _, _, _ in payroll_lines)

        # Reload lines to get IDs for earning/deduction records
        created_lines = {
            line.employee_id: line
            for line in payroll_run.lines.all()
        }

        statutory_records = []
        for line, emp_earnings, emp_deductions, emp_statutory in payroll_lines:
            saved_line = created_lines.get(line.employee_id)
            if not saved_line:
                continue
            for comp, amount in emp_earnings:
                earning_records.append(PayrollEarning(
                    payroll_line=saved_line, component=comp, amount=amount
                ))
            for comp, amount in emp_deductions:
                deduction_records.append(PayrollDeduction(
                    payroll_line=saved_line, component=comp, amount=amount
                ))
            for tmpl, emp_amount, employer_amount in emp_statutory:
                statutory_records.append(StatutoryDeduction(
                    payroll_line=saved_line,
                    template=tmpl,
                    employee_amount=emp_amount,
                    employer_amount=employer_amount,
                    is_employer_contribution=(employer_amount > 0)
                ))

        if earning_records:
            PayrollEarning.objects.bulk_create(earning_records)
        if deduction_records:
            PayrollDeduction.objects.bulk_create(deduction_records)
        if statutory_records:
            StatutoryDeduction.objects.bulk_create(statutory_records)

        # Aggregate totals
        totals = payroll_run.lines.aggregate(
            total_gross=Sum('gross_salary'),
            total_deductions=Sum('total_deductions'),
            total_net=Sum('net_salary')
        )

        payroll_run.total_gross = totals['total_gross'] or 0
        payroll_run.total_deductions = totals['total_deductions'] or 0
        payroll_run.total_net = totals['total_net'] or 0
        payroll_run.status = 'In Progress'
        payroll_run.processed_by = request.user
        payroll_run.save()

        return Response(PayrollRunSerializer(payroll_run).data)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        payroll_run = self.get_object()

        if payroll_run.status != 'In Progress':
            return Response({'error': 'Payroll must be processed first'}, status=status.HTTP_400_BAD_REQUEST)

        from django.db import transaction as db_transaction

        with db_transaction.atomic():
            payroll_run.status = 'Approved'
            payroll_run.approved_by = request.user
            payroll_run.approved_date = timezone.now()
            payroll_run.save()

            for line in payroll_run.lines.all():
                Payslip.objects.get_or_create(payroll_line=line)

            # Auto-post payroll accrual to GL on approval.
            # Creates:  DR Salary Expense / CR Payroll Liability
            # The liability is cleared later by the mark_paid action.
            #
            # IMPORTANT — rollback semantics:
            # Catching an exception and returning a Response prevents it from
            # propagating out of `with transaction.atomic()`, so the DB commits
            # despite the failure.  That would leave payroll_run.status = Approved
            # without a matching GL journal.  We explicitly flag the transaction
            # for rollback so BOTH sides stay consistent: either fully posted
            # or fully pending.
            try:
                from accounting.services.payroll_posting import PayrollPostingService
                journal = PayrollPostingService.post_payroll_run(payroll_run)
                if journal:
                    payroll_run.journal_entry = journal
                    payroll_run.save(update_fields=['journal_entry'])
            except Exception as e:
                import logging
                from django.db import transaction as _txn
                _txn.set_rollback(True)
                logger = logging.getLogger(__name__)
                logger.error("payroll GL posting failed for run %s: %s", payroll_run.run_number, e)
                return Response(
                    {'error': f'Payroll approval rolled back — GL posting failed: {str(e)}'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

        return Response(PayrollRunSerializer(payroll_run).data)

    @action(detail=True, methods=['post'])
    def mark_paid(self, request, pk=None):
        payroll_run = self.get_object()

        if payroll_run.status != 'Approved':
            return Response({'error': 'Payroll must be approved first'}, status=status.HTTP_400_BAD_REQUEST)

        # Clear payroll liability: Dr Payroll Liability / Cr Bank
        # GL posting must succeed atomically before the run advances to 'Paid'.
        from django.db import transaction as db_transaction
        from accounting.models import JournalHeader, JournalLine
        from accounting.transaction_posting import get_gl_account, TransactionPostingService

        payroll_liability = get_gl_account('PAYROLL_LIABILITY', 'Liability', 'Payroll')
        bank_account      = get_gl_account('BANK_ACCOUNT', 'Asset', 'Bank')
        if not bank_account:
            bank_account = get_gl_account('CASH_ACCOUNT', 'Asset', 'Cash')

        if not payroll_liability:
            return Response(
                {'error': 'Payroll Liability GL account not found. '
                          'Configure PAYROLL_LIABILITY in DEFAULT_GL_ACCOUNTS.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not bank_account:
            return Response(
                {'error': 'Bank/Cash GL account not found. '
                          'Configure BANK_ACCOUNT or CASH_ACCOUNT in DEFAULT_GL_ACCOUNTS.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        total_net = Decimal(str(payroll_run.total_net or 0))
        try:
            with db_transaction.atomic():
                if total_net > 0:
                    journal = JournalHeader.objects.create(
                        reference_number=f"PAY-{payroll_run.run_number or payroll_run.id}",
                        description=f"Payroll Payment: {payroll_run.run_number}",
                        posting_date=timezone.now().date(),
                        status='Posted'
                    )
                    JournalLine.objects.create(
                        header=journal,
                        account=payroll_liability,
                        debit=total_net,
                        credit=Decimal('0.00'),
                        memo="Clear Salary Payable"
                    )
                    JournalLine.objects.create(
                        header=journal,
                        account=bank_account,
                        debit=Decimal('0.00'),
                        credit=total_net,
                        memo="Bank payment for payroll"
                    )
                    # Validate balance before updating GL — prevents unbalanced journal
                    # from corrupting GL balances (matches the invariant in transaction_posting.py)
                    TransactionPostingService._validate_journal_balanced(journal)
                    TransactionPostingService._update_gl_balances(journal)

                payroll_run.status = 'Paid'
                payroll_run.save(update_fields=['status'])

        except Exception as e:
            logger.error(f"GL posting failed for payroll run {payroll_run.pk}: {e}", exc_info=True)
            return Response({'error': f'GL posting failed: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

        return Response(PayrollRunSerializer(payroll_run).data)

    @action(detail=True, methods=['post'])
    def post_to_gl(self, request, pk=None):
        """Post payroll run to General Ledger"""
        from accounting.transaction_posting import TransactionPostingService
        
        payroll_run = self.get_object()
        
        if payroll_run.status != 'Approved':
            return Response({'error': 'Payroll must be approved before posting to GL'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            journal = TransactionPostingService.post_payroll_run(payroll_run)
            payroll_run.journal_entry = journal
            payroll_run.save(update_fields=['journal_entry'])
            return Response({
                'status': 'Posted to GL',
                'journal_number': journal.reference_number,
                'journal_id': journal.id
            })
        except Exception as e:
            logger.error("Failed to post payroll run %s to GL: %s", payroll_run.pk, e)
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def reverse(self, request, pk=None):
        """HR-L1: Create month-end reversal entries for payroll"""
        from accounting.transaction_posting import TransactionPostingService
        
        payroll_run = self.get_object()
        
        if payroll_run.status not in ['Paid', 'Approved']:
            return Response({'error': 'Payroll must be paid or approved to create reversal'}, status=status.HTTP_400_BAD_REQUEST)
        
        if not payroll_run.journal_entry_id:
            return Response({'error': 'Payroll has not been posted to GL yet'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            reversal_journal = TransactionPostingService.reverse_payroll_journal(
                payroll_run.journal_entry,
                payroll_run.period.end_date,
                request.data.get('reason', 'Month-end reversal')
            )
            
            return Response({
                'status': 'Reversal posted',
                'original_journal': payroll_run.journal_entry.reference_number,
                'reversal_journal_number': reversal_journal.reference_number,
                'reversal_journal_id': reversal_journal.id
            })
        except Exception as e:
            logger.error("Failed to reverse payroll run %s: %s", payroll_run.pk, e)
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class PayrollLineViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = PayrollLine.objects.all().select_related('employee__user', 'payroll_run__period')
    serializer_class = PayrollLineSerializer
    filterset_fields = ['payroll_run', 'employee']
    pagination_class = HRMPagination
class PayslipViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Payslip.objects.all().select_related('payroll_line__employee__user', 'payroll_line__payroll_run__period')
    serializer_class = PayslipSerializer
    pagination_class = HRMPagination

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser:
            return Payslip.objects.all()
        try:
            employee = user.employee
            return Payslip.objects.filter(payroll_line__employee=employee)
        except Employee.DoesNotExist:
            return Payslip.objects.none()


class StatutoryDeductionTemplateViewSet(viewsets.ModelViewSet):
    queryset = StatutoryDeductionTemplate.objects.all()
    serializer_class = StatutoryDeductionTemplateSerializer
    filterset_fields = ['deduction_type', 'is_active', 'is_mandatory']
    pagination_class = HRMPagination


class StatutoryDeductionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = StatutoryDeduction.objects.all().select_related('payroll_line__employee__user', 'template')
    serializer_class = StatutoryDeductionSerializer
    filterset_fields = ['payroll_line', 'template']
    pagination_class = HRMPagination

# =============================================================================
# PERFORMANCE MANAGEMENT VIEWS
# =============================================================================

class PerformanceCycleViewSet(viewsets.ModelViewSet):
    queryset = PerformanceCycle.objects.all()
    serializer_class = PerformanceCycleSerializer
    filterset_fields = ['status', 'is_active']
    pagination_class = HRMPagination

    @action(detail=False, methods=['get'])
    def current(self, request):
        cycle = PerformanceCycle.objects.filter(status='Active').first()
        if not cycle:
            return Response({'error': 'No active cycle'}, status=status.HTTP_404_NOT_FOUND)
        return Response(PerformanceCycleSerializer(cycle).data)
class PerformanceGoalViewSet(viewsets.ModelViewSet):
    queryset = PerformanceGoal.objects.all().select_related('employee__user', 'cycle')
    serializer_class = PerformanceGoalSerializer
    filterset_fields = ['employee', 'cycle', 'status', 'goal_type']
    pagination_class = HRMPagination
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ['title', 'description']
    ordering_fields = ['target_date']

    @action(detail=True, methods=['post'])
    def update_progress(self, request, pk=None):
        goal = self.get_object()
        goal.progress = request.data.get('progress', goal.progress)
        
        if goal.progress >= 100:
            goal.status = 'Completed'
            goal.completion_date = timezone.now().date()
        
        goal.save()
        return Response(PerformanceGoalSerializer(goal).data)
class PerformanceReviewViewSet(viewsets.ModelViewSet):
    queryset = PerformanceReview.objects.all().select_related('employee__user', 'cycle', 'reviewer')
    serializer_class = PerformanceReviewSerializer
    filterset_fields = ['employee', 'cycle', 'review_type', 'status']
    pagination_class = HRMPagination
    filter_backends = [SearchFilter, OrderingFilter]
    ordering_fields = ['submitted_date']

    @action(detail=True, methods=['post'])
    def submit(self, request, pk=None):
        review = self.get_object()
        
        if review.status == 'Completed':
            return Response({'error': 'Review already submitted'}, status=status.HTTP_400_BAD_REQUEST)
        
        review.rating = request.data.get('rating')
        review.rating_category = request.data.get('rating_category')
        review.strengths = request.data.get('strengths', '')
        review.areas_for_improvement = request.data.get('areas_for_improvement', '')
        review.comments = request.data.get('comments', '')
        review.status = 'Completed'
        review.submitted_date = timezone.now()
        review.save()
        
        return Response(PerformanceReviewSerializer(review).data)
class CompetencyViewSet(viewsets.ModelViewSet):
    queryset = Competency.objects.all()
    serializer_class = CompetencySerializer
    filterset_fields = ['category', 'is_active']
    pagination_class = HRMPagination
class PromotionViewSet(viewsets.ModelViewSet):
    queryset = Promotion.objects.all().select_related('employee__user', 'from_position', 'to_position', 'approved_by')
    serializer_class = PromotionSerializer
    filterset_fields = ['employee', 'status']
    pagination_class = HRMPagination
    filter_backends = [SearchFilter, OrderingFilter]
    ordering_fields = ['effective_date']

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        promotion = self.get_object()
        
        if promotion.status != 'Pending':
            return Response({'error': 'Promotion already processed'}, status=status.HTTP_400_BAD_REQUEST)
        
        promotion.status = 'Approved'
        promotion.approved_by = request.user
        promotion.approved_date = timezone.now()
        promotion.save()
        
        return Response(PromotionSerializer(promotion).data)

    @action(detail=True, methods=['post'])
    def implement(self, request, pk=None):
        promotion = self.get_object()
        
        if promotion.status != 'Approved':
            return Response({'error': 'Promotion must be approved first'}, status=status.HTTP_400_BAD_REQUEST)
        
        employee = promotion.employee
        employee.position = promotion.to_position
        employee.base_salary = promotion.to_salary
        employee.save()
        
        promotion.status = 'Implemented'
        promotion.save()
        
        return Response(PromotionSerializer(promotion).data)
# =============================================================================
# TRAINING & DEVELOPMENT VIEWS
# =============================================================================

class TrainingProgramViewSet(viewsets.ModelViewSet):
    queryset = TrainingProgram.objects.all().select_related('department')
    serializer_class = TrainingProgramSerializer
    filterset_fields = ['program_type', 'delivery_method', 'status', 'is_active']
    pagination_class = HRMPagination
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ['name', 'code', 'description']
    ordering_fields = ['start_date']

    @action(detail=False, methods=['get'])
    def available(self, request):
        today = timezone.now().date()
        programs = TrainingProgram.objects.filter(
            status='Active',
            is_active=True,
            registration_deadline__gte=today
        )
        return Response(TrainingProgramSerializer(programs, many=True).data)
class TrainingEnrollmentViewSet(viewsets.ModelViewSet):
    queryset = TrainingEnrollment.objects.all().select_related('employee__user', 'program')
    serializer_class = TrainingEnrollmentSerializer
    filterset_fields = ['employee', 'program', 'status']
    pagination_class = HRMPagination

    @action(detail=True, methods=['post'])
    def mark_attended(self, request, pk=None):
        enrollment = self.get_object()
        enrollment.status = 'Attended'
        enrollment.attendance_date = timezone.now().date()
        enrollment.save()
        return Response(TrainingEnrollmentSerializer(enrollment).data)

    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        enrollment = self.get_object()
        enrollment.status = 'Completed'
        enrollment.completion_date = timezone.now().date()
        enrollment.score = request.data.get('score')
        enrollment.passed = request.data.get('passed', True)
        enrollment.save()
        return Response(TrainingEnrollmentSerializer(enrollment).data)
class SkillViewSet(viewsets.ModelViewSet):
    queryset = Skill.objects.all()
    serializer_class = SkillSerializer
    filterset_fields = ['category', 'is_active']
    pagination_class = HRMPagination
    filter_backends = [SearchFilter]
    search_fields = ['name', 'code']
class EmployeeSkillViewSet(viewsets.ModelViewSet):
    queryset = EmployeeSkill.objects.all().select_related('employee__user', 'skill')
    serializer_class = EmployeeSkillSerializer
    filterset_fields = ['employee', 'skill', 'proficiency_level']
    pagination_class = HRMPagination

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser:
            return EmployeeSkill.objects.all()
        try:
            employee = user.employee
            return EmployeeSkill.objects.filter(employee=employee)
        except Employee.DoesNotExist:
            return EmployeeSkill.objects.none()
class TrainingPlanViewSet(viewsets.ModelViewSet):
    queryset = TrainingPlan.objects.all().select_related('employee__user')
    serializer_class = TrainingPlanSerializer
    filterset_fields = ['employee', 'status']
    pagination_class = HRMPagination
# =============================================================================
# COMPLIANCE & POLICY VIEWS
# =============================================================================

class PolicyViewSet(viewsets.ModelViewSet):
    queryset = Policy.objects.all()
    serializer_class = PolicySerializer
    filterset_fields = ['category', 'status', 'is_active']
    pagination_class = HRMPagination
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ['title', 'code', 'description']
    ordering_fields = ['title', 'effective_date']

    @action(detail=True, methods=['post'])
    def acknowledge(self, request, pk=None):
        policy = self.get_object()
        employee = request.user.employee
        
        acknowledgement, created = PolicyAcknowledgement.objects.get_or_create(
            employee=employee,
            policy=policy,
            defaults={'status': 'Acknowledged', 'acknowledged_date': timezone.now()}
        )
        
        if not created:
            acknowledgement.status = 'Acknowledged'
            acknowledgement.acknowledged_date = timezone.now()
            acknowledgement.save()
        
        return Response(PolicyAcknowledgementSerializer(acknowledgement).data)
class PolicyAcknowledgementViewSet(viewsets.ModelViewSet):
    queryset = PolicyAcknowledgement.objects.all().select_related('employee__user', 'policy')
    serializer_class = PolicyAcknowledgementSerializer
    filterset_fields = ['employee', 'policy', 'status']
    pagination_class = HRMPagination

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser:
            return PolicyAcknowledgement.objects.all()
        try:
            employee = user.employee
            return PolicyAcknowledgement.objects.filter(employee=employee)
        except Employee.DoesNotExist:
            return PolicyAcknowledgement.objects.none()
class ComplianceRecordViewSet(viewsets.ModelViewSet):
    queryset = ComplianceRecord.objects.all().select_related('assigned_to')
    serializer_class = ComplianceRecordSerializer
    filterset_fields = ['compliance_type', 'status']
    pagination_class = HRMPagination
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ['title', 'code', 'description']
    ordering_fields = ['effective_date']
class ComplianceTaskViewSet(viewsets.ModelViewSet):
    queryset = ComplianceTask.objects.all().select_related('compliance_record', 'assigned_to')
    serializer_class = ComplianceTaskSerializer
    filterset_fields = ['compliance_record', 'assigned_to', 'status']
    pagination_class = HRMPagination

    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        task = self.get_object()
        task.status = 'Completed'
        task.completed_date = timezone.now().date()
        task.evidence = request.data.get('evidence', '')
        task.save()
        return Response(ComplianceTaskSerializer(task).data)
class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AuditLog.objects.all().select_related('user')
    serializer_class = AuditLogSerializer
    filterset_fields = ['user', 'action_type', 'module']
    pagination_class = HRMPagination
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ['object_repr', 'user__username']
    ordering_fields = ['-timestamp']
# =============================================================================
# EXIT & OFFBOARDING VIEWS
# =============================================================================

class ExitRequestViewSet(viewsets.ModelViewSet):
    queryset = ExitRequest.objects.all().select_related('employee__user', 'approved_by')
    serializer_class = ExitRequestSerializer
    filterset_fields = ['employee', 'exit_type', 'status']
    pagination_class = HRMPagination
    filter_backends = [SearchFilter, OrderingFilter]
    ordering_fields = ['requested_date']

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        exit_request = self.get_object()
        
        if exit_request.status != 'Pending':
            return Response({'error': 'Only pending requests can be approved'}, status=status.HTTP_400_BAD_REQUEST)
        
        exit_request.status = 'Approved'
        exit_request.approved_by = request.user
        exit_request.approved_date = timezone.now()
        exit_request.save()
        
        return Response(ExitRequestSerializer(exit_request).data)

    @action(detail=True, methods=['post'])
    def process(self, request, pk=None):
        exit_request = self.get_object()
        
        if exit_request.status != 'Approved':
            return Response({'error': 'Exit request must be approved first'}, status=status.HTTP_400_BAD_REQUEST)
        
        employee = exit_request.employee
        employee.status = 'Terminated'
        employee.termination_date = exit_request.last_working_date
        employee.save()
        
        exit_request.status = 'Processed'
        exit_request.save()
        
        return Response(ExitRequestSerializer(exit_request).data)
class ExitInterviewViewSet(viewsets.ModelViewSet):
    queryset = ExitInterview.objects.all().select_related('exit_request__employee__user', 'interviewer')
    serializer_class = ExitInterviewSerializer
    filterset_fields = ['exit_request', 'status']
    pagination_class = HRMPagination

    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        interview = self.get_object()
        interview.status = 'Completed'
        interview.completed_date = timezone.now()
        interview.save()
        return Response(ExitInterviewSerializer(interview).data)
class ExitClearanceViewSet(viewsets.ModelViewSet):
    queryset = ExitClearance.objects.all().select_related('exit_request__employee__user', 'completed_by')
    serializer_class = ExitClearanceSerializer
    filterset_fields = ['exit_request', 'category', 'status']
    pagination_class = HRMPagination

    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        clearance = self.get_object()
        clearance.status = 'Completed'
        clearance.completed_by = request.user
        clearance.completed_date = timezone.now()
        clearance.remarks = request.data.get('remarks', '')
        clearance.save()
        return Response(ExitClearanceSerializer(clearance).data)
class FinalSettlementViewSet(viewsets.ModelViewSet):
    queryset = FinalSettlement.objects.all().select_related('exit_request__employee__user', 'calculated_by', 'approved_by')
    serializer_class = FinalSettlementSerializer
    filterset_fields = ['exit_request', 'status']
    pagination_class = HRMPagination

    @action(detail=True, methods=['post'])
    def calculate(self, request, pk=None):
        settlement = self.get_object()
        settlement.calculate()
        settlement.save()
        return Response(FinalSettlementSerializer(settlement).data)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        settlement = self.get_object()
        
        if settlement.status != 'Calculated':
            return Response({'error': 'Settlement must be calculated first'}, status=status.HTTP_400_BAD_REQUEST)
        
        settlement.status = 'Approved'
        settlement.approved_by = request.user
        settlement.approved_date = timezone.now()
        settlement.save()
        
        return Response(FinalSettlementSerializer(settlement).data)

    @action(detail=True, methods=['post'])
    def mark_paid(self, request, pk=None):
        settlement = self.get_object()
        
        if settlement.status != 'Approved':
            return Response({'error': 'Settlement must be approved first'}, status=status.HTTP_400_BAD_REQUEST)
        
        settlement.status = 'Paid'
        settlement.payment_date = request.data.get('payment_date')
        settlement.payment_reference = request.data.get('payment_reference', '')
        settlement.save()
        
        return Response(FinalSettlementSerializer(settlement).data)
class ExperienceCertificateViewSet(viewsets.ModelViewSet):
    queryset = ExperienceCertificate.objects.all()
    serializer_class = ExperienceCertificateSerializer
    filterset_fields = ['exit_request']
    pagination_class = HRMPagination
class AssetReturnViewSet(viewsets.ModelViewSet):
    queryset = AssetReturn.objects.all().select_related('exit_request__employee__user', 'verified_by')
    serializer_class = AssetReturnSerializer
    filterset_fields = ['exit_request', 'status']
    pagination_class = HRMPagination

    @action(detail=True, methods=['post'])
    def mark_returned(self, request, pk=None):
        asset = self.get_object()
        asset.status = request.data.get('status', 'Returned')
        asset.return_actual_date = timezone.now().date()
        asset.condition = request.data.get('condition', '')
        asset.remarks = request.data.get('remarks', '')
        asset.verified_by = request.user
        asset.save()
        return Response(AssetReturnSerializer(asset).data)
# =============================================================================
# HR DASHBOARD & REPORTS
# =============================================================================

class HRDashboardViewSet(viewsets.ViewSet):

    def list(self, request):
        from django.db.models import Q
        
        total_employees = Employee.objects.count()
        active_employees = Employee.objects.filter(status='Active').count()
        on_leave = Employee.objects.filter(status='On Leave').count()
        terminated = Employee.objects.filter(status='Terminated').count()
        
        probation = Employee.objects.filter(status='Probation').count()
        
        by_department = Employee.objects.values('department__name').annotate(
            total=Count('id'),
            active=Count('id', filter=Q(status='Active'))
        )
        
        by_status = Employee.objects.values('status').annotate(count=Count('id'))
        
        pending_leaves = LeaveRequest.objects.filter(status='Pending').count()
        pending_interviews = Interview.objects.filter(status='Scheduled').count()
        open_jobs = JobPost.objects.filter(status='Published').count()
        
        attendance_today = Attendance.objects.filter(date=timezone.now().date()).values('status').annotate(count=Count('id'))
        
        return Response({
            'headcount': {
                'total': total_employees,
                'active': active_employees,
                'on_leave': on_leave,
                'terminated': terminated,
                'probation': probation,
            },
            'by_department': list(by_department),
            'by_status': list(by_status),
            'pending': {
                'leaves': pending_leaves,
                'interviews': pending_interviews,
                'jobs': open_jobs,
            },
            'attendance_today': list(attendance_today),
        })
class HRReportsViewSet(viewsets.ViewSet):

    @action(detail=False, methods=['get'])
    def attendance_report(self, request):
        from datetime import timedelta
        from django.db.models.functions import TruncDate
        
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        
        if not start_date:
            start_date = timezone.now().date() - timedelta(days=30)
        if not end_date:
            end_date = timezone.now().date()
        
        attendances = Attendance.objects.filter(
            date__gte=start_date,
            date__lte=end_date
        ).values('date', 'status').annotate(count=Count('id'))
        
        return Response({
            'period': {'start': start_date, 'end': end_date},
            'data': list(attendances)
        })

    @action(detail=False, methods=['get'])
    def payroll_summary(self, request):
        period_id = request.query_params.get('period')
        
        if not period_id:
            return Response({'error': 'period required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            period = PayrollPeriod.objects.get(pk=period_id)
        except PayrollPeriod.DoesNotExist:
            return Response({'error': 'Period not found'}, status=status.HTTP_404_NOT_FOUND)
        
        runs = PayrollRun.objects.filter(period=period, status__in=['Approved', 'Paid'])
        
        total_gross = runs.aggregate(total=Sum('total_gross'))['total'] or 0
        total_deductions = runs.aggregate(total=Sum('total_deductions'))['total'] or 0
        total_net = runs.aggregate(total=Sum('total_net'))['total'] or 0
        
        employee_count = runs.aggregate(count=Count('lines', distinct=True))['count'] or 0
        
        return Response({
            'period': PayrollPeriodSerializer(period).data,
            'employee_count': employee_count,
            'total_gross': total_gross,
            'total_deductions': total_deductions,
            'total_net': total_net,
        })

    @action(detail=False, methods=['get'])
    def compliance_status(self, request):
        records = ComplianceRecord.objects.all()
        
        by_status = records.values('status').annotate(count=Count('id'))
        by_type = records.values('compliance_type').annotate(count=Count('id'))
        
        expiring = records.filter(
            expiry_date__lte=timezone.now().date() + timedelta(days=30),
            expiry_date__gte=timezone.now().date()
        )
        
        return Response({
            'by_status': list(by_status),
            'by_type': list(by_type),
            'expiring_soon': ComplianceRecordSerializer(expiring, many=True).data
        })

    @action(detail=False, methods=['get'])
    def attrition_report(self, request):
        from datetime import timedelta
        
        months = int(request.query_params.get('months', 12))
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=months * 30)
        
        terminations = Employee.objects.filter(
            status='Terminated',
            termination_date__gte=start_date,
            termination_date__lte=end_date
        ).values('termination_date__month').annotate(count=Count('id'))
        
        hires = Employee.objects.filter(
            hire_date__gte=start_date,
            hire_date__lte=end_date
        ).values('hire_date__month').annotate(count=Count('id'))
        
        avg_headcount = Employee.objects.filter(
            hire_date__lte=end_date
        ).exclude(
            Q(status='Terminated') & Q(termination_date__lte=start_date)
        ).count()
        
        attrition_rate = 0
        if avg_headcount > 0:
            attrition_rate = (terminations.aggregate(total=Sum('count'))['total'] or 0) / avg_headcount * 100
        
        return Response({
            'period': {'start': start_date, 'end': end_date},
            'terminations': list(terminations),
            'hires': list(hires),
            'avg_headcount': avg_headcount,
            'attrition_rate': round(attrition_rate, 2)
        })
