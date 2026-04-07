from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from django_filters.rest_framework import DjangoFilterBackend
from django.db import transaction
from datetime import datetime, timedelta, date
from django.utils import timezone
from .common import AccountingPagination
from ..models import (
    FiscalPeriod, FiscalYear, PeriodAccess, PeriodCloseCheck, BudgetPeriod,
)
from ..serializers import (
    FiscalPeriodSerializer, FiscalYearSerializer, PeriodAccessSerializer, PeriodCloseCheckSerializer,
)
from core.utils import api_response


class FiscalPeriodViewSet(viewsets.ModelViewSet):
    queryset = FiscalPeriod.objects.all()
    serializer_class = FiscalPeriodSerializer
    filterset_fields = ['fiscal_year', 'period_type', 'status']
    ordering_fields = ['fiscal_year', 'period_number']

    def get_queryset(self):
        queryset = super().get_queryset()
        year = self.request.query_params.get('year')
        if year:
            queryset = queryset.filter(fiscal_year=int(year))
        return queryset

    @action(detail=False, methods=['post'])
    def close_periods(self, request):
        from django.utils import timezone
        close_type = request.data.get('close_type')  # 'daily', 'monthly', 'yearly'
        target_date = request.data.get('target_date')
        close_all_upto = request.data.get('close_all_upto', True)
        reason = request.data.get('reason', '')

        periods_to_close = []
        if close_type == 'daily':
            periods = self.queryset.filter(start_date__lte=target_date, status__in=['Open', 'Locked'])
            if close_all_upto:
                periods = periods.filter(end_date__lte=target_date)
        elif close_type == 'monthly':
            from datetime import datetime
            target = datetime.strptime(target_date, '%Y-%m-%d').date()
            periods = self.queryset.filter(
                fiscal_year=target.year,
                period_number=target.month,
                status__in=['Open', 'Locked']
            )
        elif close_type == 'yearly':
            periods = self.queryset.filter(fiscal_year=int(target_date), status__in=['Open', 'Locked'])
        else:
            return Response({'error': 'Invalid close_type'}, status=status.HTTP_400_BAD_REQUEST)

        for period in periods:
            period.is_closed = True
            period.status = 'Closed'
            period.closed_by = request.user
            period.closed_date = timezone.now()
            period.closed_reason = reason
            period.save()
            periods_to_close.append(period.id)

        return Response({
            'message': f'Closed {len(periods_to_close)} periods',
            'periods': periods_to_close
        })

    @action(detail=True, methods=['post'])
    def close(self, request, pk=None):
        from django.utils import timezone
        period = self.get_object()
        reason = request.data.get('reason', '')
        period.is_closed = True
        period.status = 'Closed'
        period.closed_by = request.user
        period.closed_date = timezone.now()
        period.closed_reason = reason
        period.save()
        return Response(FiscalPeriodSerializer(period).data)

    @action(detail=True, methods=['post'])
    def reopen(self, request, pk=None):
        from django.utils import timezone
        period = self.get_object()
        reason = request.data.get('reason', '')
        period.is_closed = False
        period.status = 'Open'
        period.closed_by = None
        period.closed_date = None
        period.closed_reason = reason
        period.save()
        return Response(FiscalPeriodSerializer(period).data)

    @action(detail=True, methods=['post'])
    def grant_access(self, request, pk=None):
        from django.utils import timezone
        period = self.get_object()
        user_id = request.data.get('user_id')
        access_type = request.data.get('access_type', 'Temporary')
        start_date = request.data.get('start_date')
        end_date = request.data.get('end_date')
        reason = request.data.get('reason', '')

        from django.contrib.auth import get_user_model
        User = get_user_model()

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

        access = PeriodAccess.objects.create(
            period=period,
            user=user,
            access_type=access_type,
            start_date=start_date,
            end_date=end_date,
            granted_by=request.user,
            reason=reason,
            is_active=True
        )

        return Response(PeriodAccessSerializer(access).data)

    @action(detail=True, methods=['get'])
    def access_list(self, request, pk=None):
        period = self.get_object()
        accesses = period.access_grants.all()
        return Response(PeriodAccessSerializer(accesses, many=True).data)


class FiscalYearViewSet(viewsets.ModelViewSet):
    queryset = FiscalYear.objects.all()
    serializer_class = FiscalYearSerializer
    filterset_fields = ['year', 'status', 'period_type']
    ordering_fields = ['year']

    @action(detail=False, methods=['post'])
    def create_year(self, request):
        year = request.data.get('year')
        name = request.data.get('name')
        start_date = request.data.get('start_date')
        end_date = request.data.get('end_date')
        period_type = request.data.get('period_type', 'Monthly')

        if FiscalYear.objects.filter(year=year).exists():
            return Response({'error': f'Fiscal year {year} already exists'}, status=status.HTTP_400_BAD_REQUEST)

        from datetime import date, timedelta

        with transaction.atomic():
            fiscal_year = FiscalYear.objects.create(
                year=year,
                name=name,
                start_date=start_date,
                end_date=end_date,
                period_type=period_type,
                status='Open'
            )

            periods = []
            if period_type == 'Daily':
                current_date = start_date if isinstance(start_date, date) else datetime.strptime(str(start_date), '%Y-%m-%d').date()
                end_dt = end_date if isinstance(end_date, date) else datetime.strptime(str(end_date), '%Y-%m-%d').date()
                period_num = 1
                while current_date <= end_dt:
                    periods.append(FiscalPeriod(
                        fiscal_year=year,
                        period_number=period_num,
                        period_type='Daily',
                        start_date=current_date,
                        end_date=current_date,
                        status='Open'
                    ))
                    current_date += timedelta(days=1)
                    period_num += 1
            elif period_type == 'Monthly':
                start = datetime.strptime(str(start_date), '%Y-%m-%d').date() if not isinstance(start_date, date) else start_date
                end = datetime.strptime(str(end_date), '%Y-%m-%d').date() if not isinstance(end_date, date) else end_date
                period_num = 1
                current_year = start.year
                current_month = start.month
                while (current_year, current_month) <= (end.year, end.month):
                    month_start = date(current_year, current_month, 1)
                    if current_month == 12:
                        month_end = date(current_year + 1, 1, 1) - timedelta(days=1)
                    else:
                        month_end = date(current_year, current_month + 1, 1) - timedelta(days=1)
                    periods.append(FiscalPeriod(
                        fiscal_year=year,
                        period_number=period_num,
                        period_type='Monthly',
                        start_date=month_start,
                        end_date=month_end,
                        status='Open'
                    ))
                    period_num += 1
                    if current_month == 12:
                        current_month = 1
                        current_year += 1
                    else:
                        current_month += 1
            else:
                periods.append(FiscalPeriod(
                    fiscal_year=year,
                    period_number=1,
                    period_type='Yearly',
                    start_date=start_date,
                    end_date=end_date,
                    status='Open'
                ))

            if periods:
                FiscalPeriod.objects.bulk_create(periods)

            # ── Auto-create matching BudgetPeriod records ─────────────────────
            # This makes budget periods immediately available in Budget Management
            # without any extra manual step.
            if period_type == 'Monthly':
                budget_periods = []
                start_dt = start_date if isinstance(start_date, date) else datetime.strptime(str(start_date), '%Y-%m-%d').date()
                end_dt = end_date if isinstance(end_date, date) else datetime.strptime(str(end_date), '%Y-%m-%d').date()
                cur_year = start_dt.year
                cur_month = start_dt.month
                p_num = 1
                while (cur_year, cur_month) <= (end_dt.year, end_dt.month):
                    m_start = date(cur_year, cur_month, 1)
                    if cur_month == 12:
                        m_end = date(cur_year + 1, 1, 1) - timedelta(days=1)
                    else:
                        m_end = date(cur_year, cur_month + 1, 1) - timedelta(days=1)
                    budget_periods.append(BudgetPeriod(
                        fiscal_year=year,
                        period_type='MONTHLY',
                        period_number=p_num,
                        start_date=m_start,
                        end_date=m_end,
                        status='OPEN',
                        allow_postings=True,
                        allow_adjustments=True,
                    ))
                    p_num += 1
                    if cur_month == 12:
                        cur_month = 1
                        cur_year += 1
                    else:
                        cur_month += 1
                if budget_periods:
                    BudgetPeriod.objects.bulk_create(budget_periods, ignore_conflicts=True)

        return Response(FiscalYearSerializer(fiscal_year).data)

    @action(detail=True, methods=['post'])
    def set_active(self, request, pk=None):
        fiscal_year = self.get_object()
        FiscalYear.objects.filter(is_active=True).update(is_active=False)
        fiscal_year.is_active = True
        fiscal_year.save()
        return Response(FiscalYearSerializer(fiscal_year).data)

    @action(detail=True, methods=['post'])
    def close_year(self, request, pk=None):
        from django.utils import timezone
        fiscal_year = self.get_object()
        reason = request.data.get('reason', '')
        fiscal_year.status = 'Closed'
        fiscal_year.closed_by = request.user
        fiscal_year.closed_date = timezone.now()
        fiscal_year.save()

        fiscal_year.periods.update(status='Closed', is_closed=True)
        return Response(FiscalYearSerializer(fiscal_year).data)


class PeriodAccessViewSet(viewsets.ModelViewSet):
    queryset = PeriodAccess.objects.all()
    serializer_class = PeriodAccessSerializer
    filterset_fields = ['period', 'user', 'access_type', 'is_active']

    @action(detail=True, methods=['post'])
    def revoke(self, request, pk=None):
        access = self.get_object()
        access.is_active = False
        access.save()
        return Response(PeriodAccessSerializer(access).data)


class PeriodCloseCheckViewSet(viewsets.ModelViewSet):
    queryset = PeriodCloseCheck.objects.all().select_related('period', 'checked_by')
    serializer_class = PeriodCloseCheckSerializer
    filterset_fields = ['period', 'check_category', 'is_passed']


class PeriodCloseChecklistView(viewsets.ViewSet):
    """
    Period-close pre-flight checklist.

    GET /api/accounting/period-close/checklist/?fiscal_period_id=<id>

    Returns live counts of items that must be resolved before a period can be
    safely closed:
      - unposted_journals       : Draft/Pending journals in the period
      - open_grn_without_invoice: GRNs with no matched vendor invoice
      - unreconciled_payments   : Posted payments not yet reconciled
      - unreconciled_receipts   : Posted receipts not yet reconciled
      - pending_approvals       : Journal entries in Pending/Approved-but-not-Posted state

    All counts = 0 means the period is clear to close.
    """

    def list(self, request):
        from ..models import JournalHeader, BankReconciliation
        from django.db.models import Q

        fiscal_period_id = request.query_params.get('fiscal_period_id')
        period_obj = None
        if fiscal_period_id:
            period_obj = FiscalPeriod.objects.filter(pk=fiscal_period_id).first()

        # Base date range for filtering
        start_date = period_obj.start_date if period_obj else None
        end_date = period_obj.end_date if period_obj else None

        # 1. Unposted journal entries (Draft or Pending) within the period
        je_qs = JournalHeader.objects.filter(status__in=['Draft', 'Pending'])
        if start_date and end_date:
            je_qs = je_qs.filter(posting_date__gte=start_date, posting_date__lte=end_date)
        unposted_journals = je_qs.count()

        # 2. Open GRNs without a matched vendor invoice
        try:
            from procurement.models import GoodsReceivedNote
            grn_qs = GoodsReceivedNote.objects.filter(status='Posted')
            if start_date and end_date:
                grn_qs = grn_qs.filter(received_date__gte=start_date, received_date__lte=end_date)
            # GRNs that have no vendor invoice linked via purchase_order
            open_grns = grn_qs.filter(
                purchase_order__vendor_invoices__isnull=True
            ).distinct().count()
        except Exception:
            open_grns = 0

        # 3. Unreconciled payments
        try:
            from accounting.models import Payment, Receipt
            pay_qs = Payment.objects.filter(status='Posted', is_reconciled=False)
            if start_date and end_date:
                pay_qs = pay_qs.filter(payment_date__gte=start_date, payment_date__lte=end_date)
            unreconciled_payments = pay_qs.count()

            rec_qs = Receipt.objects.filter(status='Posted', is_reconciled=False)
            if start_date and end_date:
                rec_qs = rec_qs.filter(receipt_date__gte=start_date, receipt_date__lte=end_date)
            unreconciled_receipts = rec_qs.count()
        except Exception:
            unreconciled_payments = 0
            unreconciled_receipts = 0

        # 4. Pending approval workflows (journals in 'Pending' state)
        pending_approvals = JournalHeader.objects.filter(status='Pending').count()
        if start_date and end_date:
            pending_approvals = JournalHeader.objects.filter(
                status='Pending',
                posting_date__gte=start_date,
                posting_date__lte=end_date,
            ).count()

        checklist = {
            'fiscal_period': fiscal_period_id,
            'period_name': str(period_obj) if period_obj else None,
            'is_clear_to_close': (
                unposted_journals == 0
                and open_grns == 0
                and unreconciled_payments == 0
                and unreconciled_receipts == 0
                and pending_approvals == 0
            ),
            'items': {
                'unposted_journals': unposted_journals,
                'open_grn_without_invoice': open_grns,
                'unreconciled_payments': unreconciled_payments,
                'unreconciled_receipts': unreconciled_receipts,
                'pending_approvals': pending_approvals,
            }
        }
        return api_response(data=checklist)
