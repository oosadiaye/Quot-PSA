from decimal import Decimal
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action

from django.db.models import Sum
from .models import UnifiedBudget, UnifiedBudgetEncumbrance, UnifiedBudgetVariance, UnifiedBudgetAmendment
from .serializers import BudgetAllocationSerializer, BudgetLineSerializer, BudgetVarianceSerializer
from .logic import check_budget_availability
from accounting.models import JournalHeader, JournalLine


class UnifiedBudgetViewSet(viewsets.ModelViewSet):
    """ViewSet for Unified Budget - supports both Public and Private Sector"""
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


class UnifiedBudgetEncumbranceViewSet(viewsets.ModelViewSet):
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


class UnifiedBudgetVarianceViewSet(viewsets.ReadOnlyModelViewSet):
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
        
        from .serializers import BudgetVarianceSerializer
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


class UnifiedBudgetAmendmentViewSet(viewsets.ModelViewSet):
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
