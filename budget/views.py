from decimal import Decimal
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action

from django.db.models import Sum
from .models import UnifiedBudget, UnifiedBudgetEncumbrance, UnifiedBudgetVariance, UnifiedBudgetAmendment, RevenueBudget
from .serializers import BudgetVarianceSerializer, RevenueBudgetSerializer
from core.mixins import OrganizationFilterMixin


class UnifiedBudgetViewSet(OrganizationFilterMixin, viewsets.ModelViewSet):
    """ViewSet for Unified Budget - supports both Public and Private Sector"""
    org_filter_field = 'mda'
    queryset = UnifiedBudget.objects.all().select_related(
        'mda', 'fund', 'function', 'program', 'geo', 'cost_center', 'account'
    )
    filterset_fields = ['fiscal_year', 'period_type', 'period_number', 'budget_type', 'status', 'mda', 'cost_center']
    search_fields = ['budget_code', 'name', 'description']

    @action(detail=False, methods=['get'])
    def utilization_alerts(self, request):
        """Get budgets exceeding utilization threshold"""
        threshold = request.query_params.get('threshold', 80)
        fiscal_year = request.query_params.get('fiscal_year')

        budgets = UnifiedBudget.objects.filter(
            status='APPROVED'
        ).select_related('mda', 'cost_center', 'account')

        if fiscal_year:
            budgets = budgets.filter(fiscal_year=fiscal_year)

        alerts = []
        for budget in budgets:
            utilization = float(budget.utilization_rate)
            if utilization >= float(threshold):
                alerts.append({
                    'id': budget.id,
                    'budget_code': budget.budget_code,
                    'name': budget.name,
                    'budget_type': budget.budget_type,
                    'mda': budget.mda.name if budget.mda else None,
                    'cost_center': budget.cost_center.name if budget.cost_center else None,
                    'account': budget.account.name if budget.account else None,
                    'allocated_amount': float(budget.allocated_amount),
                    'encumbered_amount': float(budget.encumbered_amount),
                    'actual_expended': float(budget.actual_expended),
                    'available_amount': float(budget.available_amount),
                    'utilization_rate': round(utilization, 2),
                    'threshold': float(threshold),
                    'alert_level': 'Critical' if utilization >= 95 else 'Warning' if utilization >= 80 else 'Info',
                })

        return Response({
            'count': len(alerts),
            'alerts': alerts
        })

    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        budget = self.get_object()
        budget.status = 'APPROVED'
        budget.approved_by = request.user
        from django.utils import timezone
        budget.approved_date = timezone.now()
        budget.save()
        return Response({"status": "Budget activated."})

    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        budget = self.get_object()
        budget.status = 'DRAFT'
        budget.save()
        return Response({"status": "Budget deactivated."})

    @action(detail=True, methods=['post'])
    def close(self, request, pk=None):
        """Close the budget period"""
        budget = self.get_object()
        budget.status = 'CLOSED'
        from django.utils import timezone
        budget.closed_date = timezone.now()
        budget.save()
        return Response({"status": "Budget closed."})

    @action(detail=True, methods=['post'])
    def check_budget(self, request, pk=None):
        """Check if amount is available in this budget"""
        budget = self.get_object()
        amount = request.data.get('amount')

        if not amount:
            return Response({"error": "amount is required"}, status=status.HTTP_400_BAD_REQUEST)

        is_allowed, message, available = budget.check_availability(Decimal(str(amount)))

        return Response({
            "allowed": is_allowed,
            "message": message,
            "available_amount": str(available),
            "allocated_amount": str(budget.allocated_amount),
            "encumbered_amount": str(budget.encumbered_amount),
            "actual_expended": str(budget.actual_expended),
            "utilization_rate": str(budget.utilization_rate)
        })

    @action(detail=True, methods=['get'])
    def summary(self, request, pk=None):
        """Get budget summary with all calculated fields"""
        budget = self.get_object()
        return Response({
            'budget_code': budget.budget_code,
            'name': budget.name,
            'fiscal_year': budget.fiscal_year,
            'period_type': budget.period_type,
            'period_number': budget.period_number,
            'status': budget.status,
            'budget_type': budget.budget_type,
            'original_amount': str(budget.original_amount),
            'revised_amount': str(budget.revised_amount),
            'supplemental_amount': str(budget.supplemental_amount),
            'allocated_amount': str(budget.allocated_amount),
            'encumbered_amount': str(budget.encumbered_amount),
            'actual_expended': str(budget.actual_expended),
            'available_amount': str(budget.available_amount),
            'utilization_rate': str(budget.utilization_rate),
            'variance_amount': str(budget.variance_amount),
            'variance_percent': str(budget.variance_percent),
        })


class UnifiedBudgetEncumbranceViewSet(OrganizationFilterMixin, viewsets.ModelViewSet):
    org_filter_field = 'budget__mda'
    """ViewSet for Budget Encumbrances"""
    queryset = UnifiedBudgetEncumbrance.objects.all().select_related('budget')
    filterset_fields = ['budget', 'reference_type', 'status']
    search_fields = ['reference_number', 'description']

    @action(detail=True, methods=['post'])
    def liquidate(self, request, pk=None):
        """Liquidate (reduce) an encumbrance"""
        encumbrance = self.get_object()
        amount = request.data.get('amount')

        if not amount:
            return Response({"error": "amount is required"}, status=status.HTTP_400_BAD_REQUEST)

        encumbrance.liquidate(Decimal(str(amount)))
        return Response({"status": "Encumbrance liquidated.", "remaining": str(encumbrance.remaining_amount)})

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel an encumbrance"""
        encumbrance = self.get_object()
        reason = request.data.get('reason', 'Manual cancellation')
        encumbrance.cancel(reason)
        return Response({"status": "Encumbrance cancelled."})


class UnifiedBudgetVarianceViewSet(OrganizationFilterMixin, viewsets.ReadOnlyModelViewSet):
    org_filter_field = 'budget__mda'
    """ViewSet for Budget Variance Analysis"""
    queryset = UnifiedBudgetVariance.objects.all().select_related('budget')
    filterset_fields = ['budget', 'fiscal_year', 'period_type', 'period_number', 'variance_type']

    @action(detail=False, methods=['post'])
    def calculate(self, request):
        """Calculate variance for a given period"""
        budget_id = request.data.get('budget_id')
        period_number = request.data.get('period_number')
        period_type = request.data.get('period_type', 'MONTHLY')

        if not budget_id or not period_number:
            return Response({"error": "budget_id and period_number are required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            budget = UnifiedBudget.objects.get(pk=budget_id)
        except UnifiedBudget.DoesNotExist:
            return Response({"error": "Budget not found"}, status=status.HTTP_404_NOT_FOUND)

        variance = UnifiedBudgetVariance.calculate_for_period(budget, int(period_number), period_type)

        return Response(BudgetVarianceSerializer(variance).data)

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Get variance summary"""
        budget_id = request.query_params.get('budget_id')

        variances = UnifiedBudgetVariance.objects.all()
        if budget_id:
            variances = variances.filter(budget_id=budget_id)

        total_budget = variances.aggregate(Sum('ytd_budget'))['ytd_budget__sum'] or 0
        total_actual = variances.aggregate(Sum('ytd_actual'))['ytd_actual__sum'] or 0
        total_variance = total_budget - total_actual

        return Response({
            'total_ytd_budget': float(total_budget),
            'total_ytd_actual': float(total_actual),
            'total_variance': float(total_variance),
            'variance_percent': float((total_variance / total_budget * 100) if total_budget > 0 else 0)
        })


class UnifiedBudgetAmendmentViewSet(OrganizationFilterMixin, viewsets.ModelViewSet):
    org_filter_field = 'budget__mda'
    """ViewSet for Budget Amendments"""
    queryset = UnifiedBudgetAmendment.objects.all().select_related('budget', 'from_budget', 'to_budget')
    filterset_fields = ['budget', 'amendment_type', 'status']
    search_fields = ['amendment_number', 'reason']

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """Approve a budget amendment"""
        amendment = self.get_object()
        amendment.approve(request.user)
        return Response({"status": "Amendment approved.", "new_amount": str(amendment.new_amount)})

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """Reject a budget amendment"""
        amendment = self.get_object()
        reason = request.data.get('reason', 'No reason provided')
        amendment.reject(request.user, reason)
        return Response({"status": "Amendment rejected."})


# Legacy aliases for backward compatibility
BudgetAllocationViewSet = UnifiedBudgetViewSet
BudgetLineViewSet = UnifiedBudgetEncumbranceViewSet
BudgetVarianceViewSet = UnifiedBudgetVarianceViewSet


# ─── Government Appropriation & Warrant (Quot PSE Phase 3) ───────────

from .models import Appropriation, Warrant
from .serializers import (
    AppropriationSerializer, WarrantSerializer, BudgetValidationRequestSerializer,
)
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter


class AppropriationViewSet(OrganizationFilterMixin, viewsets.ModelViewSet):
    org_filter_admin_field = 'administrative'
    """Legislative budget appropriation — the legal authority to spend."""
    serializer_class = AppropriationSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status', 'appropriation_type', 'fiscal_year', 'administrative', 'fund']
    search_fields = ['administrative__name', 'economic__name', 'description']
    ordering_fields = ['amount_approved', 'created_at']
    ordering = ['-created_at']

    def get_queryset(self):
        return Appropriation.objects.select_related(
            'fiscal_year', 'administrative', 'economic',
            'functional', 'programme', 'fund',
        )

    @action(detail=True, methods=['post'])
    def submit(self, request, pk=None):
        """Submit a draft appropriation for review."""
        appro = self.get_object()
        if appro.status != 'DRAFT':
            return Response(
                {'error': f'Only DRAFT appropriations can be submitted. Current: "{appro.status}"'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        appro.status = 'SUBMITTED'
        appro.save(update_fields=['status', 'updated_at'])
        return Response(AppropriationSerializer(appro).data)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """Approve a submitted appropriation."""
        appro = self.get_object()
        if appro.status != 'SUBMITTED':
            return Response(
                {'error': f'Only SUBMITTED appropriations can be approved. Current: "{appro.status}"'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        appro.status = 'APPROVED'
        appro.save(update_fields=['status', 'updated_at'])
        return Response(AppropriationSerializer(appro).data)

    @action(detail=True, methods=['post'])
    def enact(self, request, pk=None):
        """Enact an approved appropriation — makes it ACTIVE for spending."""
        appro = self.get_object()
        if appro.status not in ('APPROVED', 'SUBMITTED'):
            return Response(
                {'error': f'Only APPROVED appropriations can be enacted. Current: "{appro.status}"'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        appro.status = 'ACTIVE'
        from django.utils import timezone
        appro.enactment_date = appro.enactment_date or timezone.now().date()
        appro.save(update_fields=['status', 'enactment_date', 'updated_at'])
        return Response(AppropriationSerializer(appro).data)

    @action(detail=True, methods=['post'])
    def close(self, request, pk=None):
        """Close an active appropriation at fiscal year end."""
        appro = self.get_object()
        if appro.status != 'ACTIVE':
            return Response(
                {'error': f'Only ACTIVE appropriations can be closed. Current: "{appro.status}"'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        appro.status = 'CLOSED'
        appro.save(update_fields=['status', 'updated_at'])
        return Response(AppropriationSerializer(appro).data)

    @action(detail=True, methods=['get'])
    def execution(self, request, pk=None):
        """Budget execution details for this appropriation."""
        appro = self.get_object()
        return Response({
            'appropriation_id': appro.pk,
            'mda': appro.administrative.name,
            'account': appro.economic.name,
            'amount_approved': str(appro.amount_approved),
            'total_warrants': str(appro.total_warrants_released),
            'total_committed': str(appro.total_committed),
            'total_expended': str(appro.total_expended),
            'available_balance': str(appro.available_balance),
            'execution_rate': appro.execution_rate,
        })

    @action(detail=False, methods=['get'], url_path='lookup')
    def lookup_by_dimensions(self, request):
        """Lookup an active appropriation by the 3 control pillars.

        Used by the PO form to preview budget availability before commitment.
        Query params: mda (legacy MDA pk), account (legacy Account pk), fund (legacy Fund pk).
        Returns matching appropriation + execution stats, or 404 if none.
        """
        from accounting.models.ncoa import AdministrativeSegment, EconomicSegment, FundSegment

        mda_id = request.query_params.get('mda')
        account_id = request.query_params.get('account')
        fund_id = request.query_params.get('fund')
        if not (mda_id and fund_id):
            return Response(
                {'error': 'mda and fund query parameters are required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Bridge legacy FK ids → NCoA segments via the legacy_* bridges
        try:
            admin_seg = AdministrativeSegment.objects.filter(legacy_mda_id=mda_id).first()
            fund_seg = FundSegment.objects.filter(legacy_fund_id=fund_id).first()
            econ_seg = (
                EconomicSegment.objects.filter(legacy_account_id=account_id).first()
                if account_id else None
            )
        except Exception:
            admin_seg = fund_seg = econ_seg = None

        if not admin_seg or not fund_seg:
            return Response(
                {'error': 'No NCoA segment found for given MDA/Fund',
                 'hint': 'Ensure NCoA segments are seeded and bridged to legacy models.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        qs = Appropriation.objects.filter(
            administrative=admin_seg, fund=fund_seg, status='ACTIVE',
        )
        if econ_seg:
            qs = qs.filter(economic=econ_seg)

        appro = qs.select_related('administrative', 'economic', 'fund').first()
        if not appro:
            return Response(
                {'found': False,
                 'error': f'No ACTIVE appropriation for MDA:{admin_seg.code} / Fund:{fund_seg.code}'
                           + (f' / Economic:{econ_seg.code}' if econ_seg else ''),
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response({
            'found': True,
            'appropriation_id': appro.pk,
            'mda': appro.administrative.name,
            'account': appro.economic.name,
            'fund': appro.fund.name,
            'amount_approved': str(appro.amount_approved),
            'total_warrants': str(appro.total_warrants_released),
            'total_committed': str(appro.total_committed),
            'total_expended': str(appro.total_expended),
            'available_balance': str(appro.available_balance),
            'execution_rate': appro.execution_rate,
        })


class WarrantViewSet(OrganizationFilterMixin, viewsets.ModelViewSet):
    org_filter_admin_field = 'appropriation__administrative'
    """Quarterly cash release (warrant) against enacted appropriation."""
    serializer_class = WarrantSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['status', 'quarter', 'appropriation']
    ordering = ['appropriation', 'quarter']

    def get_permissions(self):
        # S7-01 — Warrant release converts enacted appropriation into
        # actually-spendable cash authority. The action that creates the
        # downstream liability surface MUST be MFA-gated. Suspension
        # and cancellation are similarly sensitive.
        from accounting.permissions import RequiresMFA
        if self.action in ('release', 'suspend', 'cancel', 'revoke'):
            return [IsAuthenticated(), RequiresMFA()]
        return super().get_permissions()

    def get_queryset(self):
        return Warrant.objects.select_related(
            'appropriation__administrative', 'appropriation__economic',
        )

    @action(detail=True, methods=['post'])
    def release(self, request, pk=None):
        """Release a pending warrant (AIE) and notify MDA accountant + AG."""
        warrant = self.get_object()
        if warrant.status != 'PENDING':
            return Response(
                {'error': f'Only PENDING warrants can be released. Current: "{warrant.status}"'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        warrant.status = 'RELEASED'
        warrant.save(update_fields=['status', 'updated_at'])

        # ── Notify MDA accountant + AG on warrant release ──────
        self._notify_warrant_released(warrant, request.user)

        return Response(WarrantSerializer(warrant).data)

    @action(detail=True, methods=['post'])
    def suspend(self, request, pk=None):
        """Suspend a released warrant."""
        warrant = self.get_object()
        if warrant.status != 'RELEASED':
            return Response(
                {'error': f'Only RELEASED warrants can be suspended. Current: "{warrant.status}"'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        warrant.status = 'SUSPENDED'
        warrant.save(update_fields=['status', 'updated_at'])
        return Response(WarrantSerializer(warrant).data)

    def _notify_warrant_released(self, warrant, released_by):
        """Send notifications to MDA accountant and AG office on warrant release."""
        from core.models import Notification, UserOrganization

        mda = warrant.appropriation.administrative
        amount = warrant.amount_released
        quarter = warrant.quarter
        fy = warrant.appropriation.fiscal_year

        title = f"Warrant Released — Q{quarter} {fy}"
        message = (
            f"AIE (Authority to Incur Expenditure) released for "
            f"{mda.name}.\n\n"
            f"Quarter: Q{quarter}\n"
            f"Amount: NGN {amount:,.2f}\n"
            f"Appropriation: {warrant.appropriation.economic.name}\n"
            f"Released by: {released_by.get_full_name() or released_by.username}"
        )
        action_url = '/budget/warrants'

        # 1. Notify all users assigned to this MDA
        mda_users = UserOrganization.objects.filter(
            organization__administrative_segment=mda,
            organization__org_role='MDA',
            is_active=True,
        ).select_related('user').values_list('user', flat=True)

        # 2. Notify all users in AG office (FINANCE_AUTHORITY)
        ag_users = UserOrganization.objects.filter(
            organization__org_role='FINANCE_AUTHORITY',
            is_active=True,
        ).select_related('user').values_list('user', flat=True)

        # Combine and deduplicate
        from django.contrib.auth.models import User
        all_user_ids = set(list(mda_users) + list(ag_users))
        # Exclude the person who released it (they already know)
        all_user_ids.discard(released_by.pk)

        if all_user_ids:
            users = User.objects.filter(pk__in=all_user_ids)
            Notification.send(
                users=users,
                category='WARRANT',
                title=title,
                message=message,
                action_url=action_url,
                priority='HIGH',
                related_model='Warrant',
                related_id=warrant.pk,
            )


class BudgetExecutionView(APIView):
    """Budget execution summary + pre-expenditure validation endpoint."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Budget execution summary across all active appropriations.

        When the caller sets ``?format=xlsx|pdf|html`` the response is
        rendered and streamed as a download (routed via
        ``serve_report``). Plain JSON callers continue to get a flat
        list of rows (back-compat with GenericListPage-style consumers).
        """
        from decimal import Decimal
        from accounting.views.reporting_helpers import serve_report

        qs = Appropriation.objects.filter(status='ACTIVE')
        fiscal_year = request.query_params.get('fiscal_year')
        if fiscal_year:
            qs = qs.filter(fiscal_year_id=fiscal_year)

        rows = []
        total_approved = Decimal('0')
        total_committed = Decimal('0')
        total_expended = Decimal('0')
        total_available = Decimal('0')
        for appro in qs.select_related('administrative', 'economic', 'fund')[:100]:
            rows.append({
                'id': appro.pk,
                'mda': appro.administrative.name,
                'account': appro.economic.name,
                'fund': appro.fund.name,
                'approved': str(appro.amount_approved),
                'committed': str(appro.total_committed),
                'expended': str(appro.total_expended),
                'available': str(appro.available_balance),
                'execution_pct': appro.execution_rate,
            })
            total_approved += appro.amount_approved or Decimal('0')
            total_committed += appro.total_committed or Decimal('0')
            total_expended += appro.total_expended or Decimal('0')
            total_available += appro.available_balance or Decimal('0')

        fmt = (request.query_params.get('format') or 'json').strip().lower()
        if fmt in ('xlsx', 'excel', 'pdf', 'html'):
            overall_exec = (
                float(total_expended / total_approved * 100)
                if total_approved > 0 else 0.0
            )
            payload = {
                'title':       'Budget Execution Report',
                'fiscal_year': int(fiscal_year) if fiscal_year else None,
                'currency':    'NGN',
                'rows':        rows,
                'totals': {
                    'total_approved':   total_approved,
                    'total_committed':  total_committed,
                    'total_expended':   total_expended,
                    'total_available':  total_available,
                    'overall_execution_pct': overall_exec,
                },
            }
            return serve_report(
                request, payload,
                filename_stem=f'budget-execution-{fiscal_year or "all"}',
                report_type='budget.execution',
                fiscal_year=int(fiscal_year) if fiscal_year else 0,
                period=0,
            )

        # Default JSON: preserve the flat-list shape existing clients depend on.
        return Response(rows)

    def post(self, request):
        """Pre-expenditure budget validation (hard-stop check)."""
        ser = BudgetValidationRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        from budget.services import BudgetValidationService, BudgetExceededError
        try:
            result = BudgetValidationService.validate_expenditure(**ser.validated_data)
            return Response(result)
        except BudgetExceededError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class CommitmentReportView(APIView):
    """Budget commitment/encumbrance report — shows PO commitments against appropriations."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from procurement.models import ProcurementBudgetLink
        from django.db.models import Sum
        from accounting.views.reporting_helpers import serve_report

        qs = ProcurementBudgetLink.objects.select_related(
            'purchase_order', 'appropriation__administrative', 'appropriation__economic',
        ).order_by('-committed_at')

        status_filter = request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)

        items = []
        for link in qs[:100]:
            items.append({
                'id': link.id,
                'purchase_order': str(link.purchase_order),
                'mda': link.appropriation.administrative.name if link.appropriation else '',
                'account': link.appropriation.economic.name if link.appropriation else '',
                'committed_amount': str(link.committed_amount),
                'status': link.status,
                'committed_at': link.committed_at.isoformat() if link.committed_at else None,
                'appropriation_balance': str(link.appropriation.available_balance) if link.appropriation else '0',
            })

        totals = qs.aggregate(total_committed=Sum('committed_amount'))
        total_committed = totals['total_committed'] or 0
        count = qs.count()

        fmt = (request.query_params.get('format') or 'json').strip().lower()
        if fmt in ('xlsx', 'excel', 'pdf', 'html'):
            payload = {
                'title':       'Budget Commitment Report',
                'currency':    'NGN',
                'items':       items,
                'totals': {
                    'total_committed': total_committed,
                    'count':           count,
                },
            }
            return serve_report(
                request, payload,
                filename_stem='commitment-report',
                report_type='budget.commitment',
                fiscal_year=0,
                period=0,
            )

        return Response({
            'items': items,
            'total_committed': str(total_committed),
            'count': count,
        })


class RevenueBudgetViewSet(OrganizationFilterMixin, viewsets.ModelViewSet):
    """Revenue budget targets — statistical (no enforcement).

    Tracks estimated vs actual IGR/FAAC collections per MDA per account.
    """
    org_filter_admin_field = 'administrative'
    serializer_class = RevenueBudgetSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['fiscal_year', 'status', 'administrative']
    ordering = ['fiscal_year', 'administrative', 'economic']

    def get_queryset(self):
        return RevenueBudget.objects.select_related(
            'administrative', 'economic', 'fund', 'fiscal_year',
        )

    @action(detail=False, methods=['get'], url_path='import-template')
    def import_template(self, request):
        """CSV template for bulk revenue budget import."""
        import io
        import csv
        from django.http import HttpResponse

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            'fiscal_year', 'administrative_code', 'economic_code', 'fund_code',
            'estimated_amount', 'jan', 'feb', 'mar', 'apr', 'may', 'jun',
            'jul', 'aug', 'sep', 'oct', 'nov', 'dec', 'description',
        ])
        writer.writerow([
            '2026', '011300000000', '11100100', '08000',
            '500000000', '', '', '', '', '', '',
            '', '', '', '', '', '', 'PAYE from SIRS',
        ])
        writer.writerow([
            '2026', '010600000000', '12100100', '08000',
            '120000000', '10000000', '10000000', '10000000', '10000000',
            '10000000', '10000000', '10000000', '10000000', '10000000',
            '10000000', '10000000', '10000000', 'Fees and fines',
        ])

        response = HttpResponse(output.getvalue(), content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="revenue_budget_template.csv"'
        return response

    @action(detail=False, methods=['post'], url_path='bulk-import')
    def bulk_import(self, request):
        """Bulk import revenue budget targets from CSV/Excel."""
        import pandas as pd
        from accounting.models.advanced import FiscalYear
        from accounting.models.ncoa import AdministrativeSegment, EconomicSegment, FundSegment

        file = request.FILES.get('file')
        if not file:
            return Response({'error': 'CSV or Excel file required'}, status=status.HTTP_400_BAD_REQUEST)
        if file.size > 5 * 1024 * 1024:
            return Response({'error': 'Max 5MB'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            df = pd.read_excel(file, nrows=10000) if file.name.endswith('.xlsx') else pd.read_csv(file, nrows=10000)
        except Exception as e:
            return Response({'error': f'Parse error: {e}'}, status=status.HTTP_400_BAD_REQUEST)

        df.columns = df.columns.str.strip().str.lower()
        required = {'fiscal_year', 'administrative_code', 'economic_code', 'fund_code', 'estimated_amount'}
        missing = required - set(df.columns)
        if missing:
            return Response({'error': f'Missing columns: {", ".join(missing)}'}, status=status.HTTP_400_BAD_REQUEST)

        month_cols = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec']
        created, skipped, errors = 0, 0, []

        for idx, row in df.iterrows():
            row_num = idx + 2
            try:
                fy = FiscalYear.objects.filter(year=int(row['fiscal_year'])).first()
                admin = AdministrativeSegment.objects.filter(code=str(row['administrative_code']).strip()).first()
                econ = EconomicSegment.objects.filter(code=str(row['economic_code']).strip()).first()
                fund = FundSegment.objects.filter(code=str(row['fund_code']).strip()).first()

                if not fy:
                    errors.append(f'Row {row_num}: Fiscal year {row["fiscal_year"]} not found')
                    continue
                if not admin:
                    errors.append(f'Row {row_num}: Admin code {row["administrative_code"]} not found')
                    continue
                if not econ:
                    errors.append(f'Row {row_num}: Economic code {row["economic_code"]} not found')
                    continue
                if not fund:
                    errors.append(f'Row {row_num}: Fund code {row["fund_code"]} not found')
                    continue

                amt = float(row['estimated_amount'])
                if amt <= 0:
                    errors.append(f'Row {row_num}: Invalid amount')
                    continue

                # Check duplicate
                if RevenueBudget.objects.filter(
                    fiscal_year=fy, administrative=admin, economic=econ, fund=fund,
                ).exists():
                    skipped += 1
                    continue

                # Build monthly spread if any month columns have values
                spread = {}
                for i, col in enumerate(month_cols):
                    if col in df.columns:
                        val = row.get(col)
                        if pd.notna(val) and float(val) > 0:
                            spread[str(i + 1)] = float(val)

                desc = str(row.get('description', '')).strip() if pd.notna(row.get('description')) else ''

                RevenueBudget.objects.create(
                    fiscal_year=fy, administrative=admin, economic=econ, fund=fund,
                    estimated_amount=amt,
                    monthly_spread=spread if spread else None,
                    status='ACTIVE',
                    description=desc,
                )
                created += 1
            except Exception as e:
                errors.append(f'Row {row_num}: {e}')

        return Response({
            'success': True, 'created': created, 'updated': 0, 'skipped': skipped, 'errors': errors,
        })

    @action(detail=False, methods=['post'], url_path='copy-from-prior-year')
    def copy_from_prior_year(self, request):
        """Copy prior year's actual revenue as budget targets for a new year.

        Reads GL credit balances for revenue accounts (type 1) from the prior
        fiscal year and creates DRAFT revenue budget records for the target year.
        """
        from accounting.models.advanced import FiscalYear

        target_year_id = request.data.get('target_fiscal_year_id')
        if not target_year_id:
            return Response({'error': 'target_fiscal_year_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        target_fy = FiscalYear.objects.filter(pk=target_year_id).first()
        if not target_fy:
            return Response({'error': 'Target fiscal year not found'}, status=status.HTTP_400_BAD_REQUEST)

        # Find the prior year
        prior_fy = FiscalYear.objects.filter(year=target_fy.year - 1).first()
        if not prior_fy:
            return Response(
                {'error': f'No fiscal year found for {target_fy.year - 1}. Cannot copy prior year actuals.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Get all existing revenue budgets for this target year (to avoid duplicates)
        existing = set(
            RevenueBudget.objects.filter(fiscal_year=target_fy)
            .values_list('administrative_id', 'economic_id', 'fund_id')
        )

        # Get prior year revenue actuals from appropriations that had revenue accounts
        # Or from GL balances for revenue accounts (type 1)
        from accounting.models.ncoa import EconomicSegment

        revenue_segments = EconomicSegment.objects.filter(
            account_type_code='1', is_active=True,
        )

        created = 0
        skipped = 0

        # Look at prior year's existing revenue budgets and use their actuals
        prior_budgets = RevenueBudget.objects.filter(
            fiscal_year=prior_fy, status__in=['ACTIVE', 'CLOSED'],
        ).select_related('administrative', 'economic', 'fund')

        for pb in prior_budgets:
            key = (pb.administrative_id, pb.economic_id, pb.fund_id)
            if key in existing:
                skipped += 1
                continue

            # Use actual collected if > 0, otherwise use the prior target
            actual = pb.actual_collected
            target = actual if actual > 0 else pb.estimated_amount

            RevenueBudget.objects.create(
                fiscal_year=target_fy,
                administrative=pb.administrative,
                economic=pb.economic,
                fund=pb.fund,
                estimated_amount=target,
                status='DRAFT',
                description=f'Copied from FY{prior_fy.year} — prior actual: NGN {actual:,.2f}',
            )
            created += 1

        return Response({
            'success': True,
            'created': created,
            'skipped': skipped,
            'source_year': prior_fy.year,
            'target_year': target_fy.year,
            'message': f'{created} revenue targets created from FY{prior_fy.year} actuals as DRAFT',
        })
