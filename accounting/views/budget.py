from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Sum, F, Q, OuterRef, Subquery, DecimalField
from django.db.models.functions import Coalesce
from django.db import transaction
from decimal import Decimal
from datetime import datetime, timedelta
import pandas as pd
from core.permissions import IsApprover
from .common import AccountingPagination
from ..models import (
    BudgetPeriod, Budget, BudgetEncumbrance, BudgetAmendment, BudgetTransfer,
    BudgetCheckLog, BudgetForecast, BudgetAnomaly, GLBalance,
)
from ..serializers import (
    BudgetPeriodSerializer, BudgetSerializer, BudgetEncumbranceSerializer,
    BudgetAmendmentSerializer, BudgetTransferSerializer, BudgetCheckLogSerializer,
    BudgetForecastSerializer, BudgetAnomalySerializer,
)


class BudgetPeriodViewSet(viewsets.ModelViewSet):
    queryset = BudgetPeriod.objects.all()
    serializer_class = BudgetPeriodSerializer
    filterset_fields = ['fiscal_year', 'period_type', 'status']

class BudgetViewSet(viewsets.ModelViewSet):
    queryset = Budget.objects.all().select_related('period', 'mda', 'account', 'fund', 'function', 'program', 'geo')
    serializer_class = BudgetSerializer
    filterset_fields = ['period', 'mda', 'account', 'fund', 'function', 'program', 'geo', 'control_level']
    search_fields = ['budget_code', 'notes']

    def get_queryset(self):
        """Annotate encumbered and expended amounts to avoid N+1 queries.

        _encumbered: net active encumbrance (amount − liquidated_amount)
        _expended:   total debit_balance from GLBalance matched by the
                     budget's 5-dimension key + fiscal_year + period_number.
        """
        # Subquery: sum debit_balance from GLBalance for each budget's dimension key
        expended_sq = Subquery(
            GLBalance.objects.filter(
                account=OuterRef('account'),
                fund=OuterRef('fund'),
                function=OuterRef('function'),
                program=OuterRef('program'),
                geo=OuterRef('geo'),
                fiscal_year=OuterRef('period__fiscal_year'),
                period=OuterRef('period__period_number'),
            ).values(
                'account', 'fund', 'function', 'program', 'geo',
            ).annotate(
                total=Sum('debit_balance'),
            ).values('total')[:1],
            output_field=DecimalField(max_digits=19, decimal_places=2),
        )

        return super().get_queryset().annotate(
            _encumbered=Coalesce(
                Sum(
                    F('encumbrances__amount') - F('encumbrances__liquidated_amount'),
                    filter=Q(encumbrances__status__in=['ACTIVE', 'PARTIALLY_LIQUIDATED']),
                ),
                Decimal('0'),
            ),
            _expended=Coalesce(expended_sq, Decimal('0')),
        )

    @action(detail=True, methods=['post'])
    def check_availability(self, request, pk=None):
        """Check budget availability for a transaction"""
        budget = self.get_object()
        amount = Decimal(str(request.data.get('amount', 0)))
        transaction_type = request.data.get('transaction_type', 'JOURNAL')
        transaction_id = request.data.get('transaction_id', 0)

        is_available, message, available = budget.check_availability(amount)

        # Log the check
        BudgetCheckLog.objects.create(
            budget=budget,
            transaction_type=transaction_type,
            transaction_id=transaction_id,
            requested_amount=amount,
            available_amount=available,
            check_result='PASSED' if is_available else ('WARNING' if budget.control_level == 'WARNING' else 'BLOCKED')
        )

        return Response({
            'is_available': is_available,
            'message': message,
            'available_amount': available,
            'requested_amount': amount,
            'control_level': budget.control_level
        })

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Get budget summary for a period"""
        period_id = request.query_params.get('period')
        if not period_id:
            return Response({"error": "period parameter is required"}, status=status.HTTP_400_BAD_REQUEST)

        budgets = self.get_queryset().filter(period_id=period_id)

        agg = budgets.aggregate(
            total_allocated=Coalesce(Sum('allocated_amount'), Decimal('0.00')),
            total_revised=Coalesce(Sum(Coalesce('revised_amount', 'allocated_amount')), Decimal('0.00')),
            total_encumbered=Coalesce(Sum('_encumbered'), Decimal('0.00')),
            total_expended=Coalesce(Sum('_expended'), Decimal('0.00')),
        )
        total_allocated = agg['total_allocated']
        total_revised = agg['total_revised']
        total_encumbered = agg['total_encumbered']
        total_expended = agg['total_expended']

        total_available = total_revised - total_encumbered - total_expended
        utilization_rate = (total_encumbered + total_expended) / total_revised * 100 if total_revised > 0 else 0

        return Response({
            'total_allocated': total_allocated,
            'total_revised': total_revised,
            'total_encumbered': total_encumbered,
            'total_expended': total_expended,
            'total_available': total_available,
            'utilization_rate': round(utilization_rate, 2)
        })

    @action(detail=False, methods=['get'])
    def utilization(self, request):
        """Get budget utilization by account type"""
        period_id = request.query_params.get('period')
        if not period_id:
            return Response({"error": "period parameter is required"}, status=status.HTTP_400_BAD_REQUEST)

        # Group by account type
        utilization_data = []
        account_types = [
            ('PERSONNEL', 'Personnel Costs'),
            ('OVERHEAD', 'Overhead Costs'),
            ('CAPITAL', 'Capital Expenditure'),
            ('RECURRENT', 'Recurrent Expenditure'),
            ('OTHER', 'Other Expenditure')
        ]

        for type_code, type_display in account_types:
            type_budgets = self.get_queryset().filter(period_id=period_id, account__account_type=type_code)

            agg = type_budgets.aggregate(
                total_alloc=Coalesce(Sum(Coalesce('revised_amount', 'allocated_amount')), Decimal('0.00')),
                total_enc=Coalesce(Sum('_encumbered'), Decimal('0.00')),
                total_exp=Coalesce(Sum('_expended'), Decimal('0.00')),
            )
            allocated = agg['total_alloc']
            encumbered = agg['total_enc']
            expended = agg['total_exp']

            used = encumbered + expended
            percent = (used / allocated * 100) if allocated > 0 else 0

            utilization_data.append({
                'account_type': type_code,
                'account_type_display': type_display,
                'allocated': allocated,
                'encumbered': encumbered,
                'expended': expended,
                'utilization_percentage': round(percent, 2)
            })

        return Response(utilization_data)

    @action(detail=False, methods=['get'])
    def alerts(self, request):
        """Get budget alerts for a period"""
        period_id = request.query_params.get('period')
        if not period_id:
            return Response({"error": "period parameter is required"}, status=status.HTTP_400_BAD_REQUEST)

        budgets = self.get_queryset().filter(period_id=period_id)
        alerts = []

        for budget in budgets:
            utilization = budget.utilization_rate
            if utilization >= 95:
                alerts.append({
                    'id': budget.id,
                    'budget_code': budget.budget_code,
                    'account_name': budget.account.name,
                    'mda_name': budget.mda.name,
                    'alert_type': 'CRITICAL',
                    'message': f"Critical: Budget {budget.budget_code} is {utilization}% utilized.",
                    'utilization': round(utilization, 2)
                })
            elif utilization >= 80:
                alerts.append({
                    'id': budget.id,
                    'budget_code': budget.budget_code,
                    'account_name': budget.account.name,
                    'mda_name': budget.mda.name,
                    'alert_type': 'WARNING',
                    'message': f"Warning: Budget {budget.budget_code} is {utilization}% utilized.",
                    'utilization': round(utilization, 2)
                })

        return Response(alerts)

    @action(detail=False, methods=['get'])
    def top_spending(self, request):
        """Get top spending budgets for a period"""
        period_id = request.query_params.get('period')
        limit = int(request.query_params.get('limit', 10))

        if not period_id:
            return Response({"error": "period parameter is required"}, status=status.HTTP_400_BAD_REQUEST)

        budgets = self.get_queryset().filter(period_id=period_id)

        spending_list = []
        for budget in budgets:
            used = budget.expended_amount + budget.encumbered_amount
            spending_list.append({
                'id': budget.id,
                'budget_code': budget.budget_code,
                'account_code': budget.account.code,
                'account_name': budget.account.name,
                'mda_name': budget.mda.name,
                'allocated': budget.revised_amount or budget.allocated_amount,
                'used': used,
                'utilization_percentage': round(budget.utilization_rate, 2)
            })

        # Sort by used amount descending
        spending_list.sort(key=lambda x: x['used'], reverse=True)

        return Response(spending_list[:limit])

    @action(detail=False, methods=['get'])
    def variance_analysis(self, request):
        """Get budget vs actual variance analysis - Optimized with aggregation"""
        from django.db.models import DecimalField

        period_id = request.query_params.get('period')
        if not period_id:
            return Response({"error": "period parameter is required"}, status=status.HTTP_400_BAD_REQUEST)

        # Optimized: Use select_related to reduce queries
        budgets = self.get_queryset().filter(
            period_id=period_id
        ).select_related('account', 'mda', 'fund', 'function', 'program', 'geo')

        # Pre-fetch encumbrance totals in one query
        encumbrance_totals = BudgetEncumbrance.objects.filter(
            budget__period_id=period_id,
            status__in=['ACTIVE', 'PARTIALLY_LIQUIDATED']
        ).values('budget_id').annotate(
            total=Sum(F('amount') - F('liquidated_amount'))
        )
        encumbrance_map = {e['budget_id']: e['total'] or Decimal('0') for e in encumbrance_totals}

        analysis = []
        for budget in budgets:
            allocated = budget.revised_amount if budget.revised_amount else budget.allocated_amount
            encumbered = encumbrance_map.get(budget.id, Decimal('0'))

            # Calculate expended from property (this still has a query but less critical)
            expended = budget.expended_amount
            available = allocated - encumbered - expended
            variance_pct = (available / allocated * 100) if allocated else 0

            analysis.append({
                'id': budget.id,
                'budget_code': budget.budget_code,
                'account': budget.account.code,
                'account_name': budget.account.name,
                'mda': budget.mda.name,
                'allocated': allocated,
                'encumbered': encumbered,
                'expended': expended,
                'available': available,
                'variance': available,
                'variance_percentage': round(variance_pct, 2),
                'utilization_rate': round(((encumbered + expended) / allocated * 100) if allocated else 0, 2)
            })

        return Response(analysis)

    @action(detail=False, methods=['get'])
    def bulk_export(self, request):
        """Export budgets as CSV."""
        import csv
        from django.http import HttpResponse

        budgets = self.filter_queryset(self.get_queryset())
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="budgets_export.csv"'

        writer = csv.writer(response)
        writer.writerow(['Account', 'Period', 'Original Amount', 'Revised Amount', 'Control Level'])
        for b in budgets:
            writer.writerow([
                b.account.code if b.account else '',
                str(b.period) if b.period else '',
                str(b.original_amount) if hasattr(b, 'original_amount') else str(b.allocated_amount),
                str(b.revised_amount),
                b.control_level,
            ])
        return response

    @action(detail=False, methods=['get'], url_path='import-template')
    def import_template(self, request):
        """Download a CSV template for budget imports."""
        import io
        import csv
        from django.http import HttpResponse

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            'mda_id', 'account_id', 'allocated_amount',
            'fund_id', 'function_id', 'program_id', 'geo_id',
            'revised_amount', 'control_level',
        ])
        writer.writerow([1, 101, 500000, '', '', '', '', '', 'HARD_STOP'])
        writer.writerow([2, 102, 300000, 1, 1, 1, 1, 350000, 'WARNING'])

        response = HttpResponse(output.getvalue(), content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="budget_import_template.csv"'
        return response

    @action(detail=False, methods=['post'])
    def bulk_import(self, request):
        """Import budgets from Excel/CSV"""
        file = request.FILES.get('file')
        period_id = request.data.get('period_id')

        if not file or not period_id:
            return Response({"error": "file and period_id are required"}, status=status.HTTP_400_BAD_REQUEST)

        MAX_IMPORT_FILE_SIZE = 5 * 1024 * 1024  # 5MB
        if file.size > MAX_IMPORT_FILE_SIZE:
            return Response({"error": "File too large. Maximum 5MB allowed."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            if file.name.endswith('.xlsx'):
                df = pd.read_excel(file, nrows=10000)
            else:
                df = pd.read_csv(file, nrows=10000)

            created_count = 0
            errors = []

            for index, row in df.iterrows():
                try:
                    Budget.objects.create(
                        period_id=period_id,
                        mda_id=row['mda_id'],
                        account_id=row['account_id'],
                        fund_id=row.get('fund_id'),
                        function_id=row.get('function_id'),
                        program_id=row.get('program_id'),
                        geo_id=row.get('geo_id'),
                        allocated_amount=row['allocated_amount'],
                        revised_amount=row.get('revised_amount', row['allocated_amount']),
                        control_level=row.get('control_level', 'HARD_STOP'),
                        created_by=request.user
                    )
                    created_count += 1
                except Exception as e:
                    errors.append(f"Row {index + 2}: {str(e)}")

            return Response({
                'success': True,
                'created': created_count,
                'errors': errors
            })
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'])
    def predictive_analysis(self, request):
        """AI-powered predictive budget analysis"""
        period_id = request.query_params.get('period')
        if not period_id:
            return Response({"error": "period parameter is required"}, status=status.HTTP_400_BAD_REQUEST)

        budgets = self.get_queryset().filter(period_id=period_id)

        predictions = []
        for budget in budgets:
            days_elapsed = (datetime.now().date() - budget.period.start_date).days
            total_days = (budget.period.end_date - budget.period.start_date).days

            if days_elapsed > 0:
                daily_burn_rate = budget.expended_amount / Decimal(str(days_elapsed))
                projected_total = daily_burn_rate * Decimal(str(total_days))

                allocated = budget.revised_amount if budget.revised_amount else budget.allocated_amount

                if daily_burn_rate > 0:
                    days_to_exhaustion = budget.available_amount / daily_burn_rate
                    exhaustion_date = datetime.now().date() + timedelta(days=int(days_to_exhaustion))
                else:
                    exhaustion_date = None

                predictions.append({
                    'budget_id': budget.id,
                    'budget_code': budget.budget_code,
                    'account': budget.account.code,
                    'mda': budget.mda.name,
                    'current_utilization': round(budget.utilization_rate, 2),
                    'projected_utilization': round((projected_total / allocated * 100), 2) if allocated else 0,
                    'daily_burn_rate': round(daily_burn_rate, 2),
                    'projected_exhaustion_date': exhaustion_date,
                    'risk_level': 'HIGH' if projected_total > allocated else 'MEDIUM' if projected_total > allocated * Decimal('0.9') else 'LOW'
                })

        return Response(predictions)

class BudgetEncumbranceViewSet(viewsets.ModelViewSet):
    queryset = BudgetEncumbrance.objects.all().select_related('budget')
    serializer_class = BudgetEncumbranceSerializer
    filterset_fields = ['budget', 'reference_type', 'status']

class BudgetAmendmentViewSet(viewsets.ModelViewSet):
    queryset = BudgetAmendment.objects.all().select_related('budget', 'requested_by', 'approved_by')
    serializer_class = BudgetAmendmentSerializer
    filterset_fields = ['budget', 'amendment_type', 'status']

    def get_permissions(self):
        if self.action == 'approve':
            return [IsApprover()]
        return super().get_permissions()

    def perform_create(self, serializer):
        serializer.save(requested_by=self.request.user)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        amendment = self.get_object()
        if amendment.status != 'PENDING':
            return Response({"error": "Only pending amendments can be approved"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                budget = amendment.budget
                budget.revised_amount = amendment.new_amount
                budget.save()

                amendment.status = 'APPROVED'
                amendment.approved_by = request.user
                amendment.approved_date = datetime.now().date()
                amendment.save()

            return Response({"status": "Amendment approved and budget updated"})
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

class BudgetTransferViewSet(viewsets.ModelViewSet):
    queryset = BudgetTransfer.objects.all().select_related('from_budget', 'to_budget', 'requested_by', 'approved_by')
    serializer_class = BudgetTransferSerializer
    filterset_fields = ['status']

    def get_permissions(self):
        if self.action == 'approve':
            return [IsApprover()]
        return super().get_permissions()

    def perform_create(self, serializer):
        serializer.save(requested_by=self.request.user)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        transfer = self.get_object()
        if transfer.status != 'PENDING':
            return Response({"error": "Only pending transfers can be approved"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                from_budget = transfer.from_budget
                to_budget = transfer.to_budget

                # Check availability on source
                is_available, message, available = from_budget.check_availability(transfer.amount)
                if not is_available:
                    return Response({"error": f"Source budget insufficient: {message}"}, status=status.HTTP_400_BAD_REQUEST)

                # Execute transfer
                from_budget.revised_amount = (from_budget.revised_amount or from_budget.allocated_amount) - transfer.amount
                to_budget.revised_amount = (to_budget.revised_amount or to_budget.allocated_amount) + transfer.amount

                from_budget.save()
                to_budget.save()

                transfer.status = 'APPROVED'
                transfer.approved_by = request.user
                transfer.save()

            return Response({"status": "Transfer approved and budgets updated"})
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

class BudgetCheckLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = BudgetCheckLog.objects.all().select_related('budget', 'override_by')
    serializer_class = BudgetCheckLogSerializer
    filterset_fields = ['budget', 'check_result', 'transaction_type']

class BudgetForecastViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = BudgetForecast.objects.all().select_related('budget')
    serializer_class = BudgetForecastSerializer
    filterset_fields = ['budget']

class BudgetAnomalyViewSet(viewsets.ModelViewSet):
    queryset = BudgetAnomaly.objects.all().select_related('budget', 'reviewed_by')
    serializer_class = BudgetAnomalySerializer
    filterset_fields = ['budget', 'anomaly_type', 'reviewed']

    @action(detail=True, methods=['post'])
    def mark_reviewed(self, request, pk=None):
        anomaly = self.get_object()
        anomaly.reviewed = True
        anomaly.reviewed_by = request.user
        anomaly.save()
        return Response({"status": "Anomaly marked as reviewed"})
