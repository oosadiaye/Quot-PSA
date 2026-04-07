from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    DepartmentViewSet, PositionViewSet, EmployeeViewSet,
    LeaveTypeViewSet, LeaveRequestViewSet, LeaveBalanceViewSet, AttendanceViewSet, HolidayViewSet,
    JobPostViewSet, CandidateViewSet, InterviewViewSet, OnboardingTaskViewSet, OnboardingProgressViewSet,
    SalaryStructureViewSet, SalaryComponentViewSet, PayrollPeriodViewSet, PayrollRunViewSet, PayrollLineViewSet, PayslipViewSet,
    PerformanceCycleViewSet, PerformanceGoalViewSet, PerformanceReviewViewSet, CompetencyViewSet, PromotionViewSet,
    TrainingProgramViewSet, TrainingEnrollmentViewSet, SkillViewSet, EmployeeSkillViewSet, TrainingPlanViewSet,
    PolicyViewSet, PolicyAcknowledgementViewSet, ComplianceRecordViewSet, ComplianceTaskViewSet, AuditLogViewSet,
    ExitRequestViewSet, ExitInterviewViewSet, ExitClearanceViewSet, FinalSettlementViewSet, ExperienceCertificateViewSet, AssetReturnViewSet,
    HRDashboardViewSet, HRReportsViewSet,
    StatutoryDeductionTemplateViewSet, StatutoryDeductionViewSet
)

router = DefaultRouter()
router.register(r'departments', DepartmentViewSet)
router.register(r'positions', PositionViewSet)
router.register(r'employees', EmployeeViewSet)
router.register(r'leave-types', LeaveTypeViewSet)
router.register(r'leave-requests', LeaveRequestViewSet)
router.register(r'leave-balances', LeaveBalanceViewSet)
router.register(r'attendances', AttendanceViewSet)
router.register(r'holidays', HolidayViewSet)

# Recruitment & Onboarding
router.register(r'job-posts', JobPostViewSet)
router.register(r'candidates', CandidateViewSet)
router.register(r'interviews', InterviewViewSet)
router.register(r'onboarding-tasks', OnboardingTaskViewSet)
router.register(r'onboarding-progress', OnboardingProgressViewSet)

# Payroll
router.register(r'salary-structures', SalaryStructureViewSet)
router.register(r'salary-components', SalaryComponentViewSet)
router.register(r'payroll-periods', PayrollPeriodViewSet)
router.register(r'payroll-runs', PayrollRunViewSet)
router.register(r'payroll-lines', PayrollLineViewSet)
router.register(r'payslips', PayslipViewSet)

# Performance Management
router.register(r'performance-cycles', PerformanceCycleViewSet)
router.register(r'performance-goals', PerformanceGoalViewSet)
router.register(r'performance-reviews', PerformanceReviewViewSet)
router.register(r'competencies', CompetencyViewSet)
router.register(r'promotions', PromotionViewSet)

# Training & Development
router.register(r'training-programs', TrainingProgramViewSet)
router.register(r'training-enrollments', TrainingEnrollmentViewSet)
router.register(r'skills', SkillViewSet)
router.register(r'employee-skills', EmployeeSkillViewSet)
router.register(r'training-plans', TrainingPlanViewSet)

# Compliance & Policy
router.register(r'policies', PolicyViewSet)
router.register(r'policy-acknowledgements', PolicyAcknowledgementViewSet)
router.register(r'compliance-records', ComplianceRecordViewSet)
router.register(r'compliance-tasks', ComplianceTaskViewSet)
router.register(r'audit-logs', AuditLogViewSet)

# Exit & Offboarding
router.register(r'exit-requests', ExitRequestViewSet)
router.register(r'exit-interviews', ExitInterviewViewSet)
router.register(r'exit-clearances', ExitClearanceViewSet)
router.register(r'final-settlements', FinalSettlementViewSet)
router.register(r'experience-certificates', ExperienceCertificateViewSet)
router.register(r'asset-returns', AssetReturnViewSet)

# Statutory Deductions
router.register(r'statutory-templates', StatutoryDeductionTemplateViewSet)
router.register(r'statutory-deductions', StatutoryDeductionViewSet)

# Dashboard & Reports
router.register(r'dashboard', HRDashboardViewSet, basename='hr-dashboard')
router.register(r'reports', HRReportsViewSet, basename='hr-reports')

urlpatterns = [
    path('', include(router.urls)),
]
