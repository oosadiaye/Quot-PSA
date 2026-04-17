from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from decimal import Decimal
from django.utils import timezone
from ..models import (
    RecurringJournal, RecurringJournalRun,
    Accrual, Deferral,
    PeriodStatus, YearEndClosing, RetainedEarnings, CurrencyRevaluation,
    Currency,
)
from ..serializers import (
    RecurringJournalSerializer, RecurringJournalRunSerializer,
    AccrualSerializer, DeferralSerializer,
    PeriodStatusSerializer, YearEndClosingSerializer, RetainedEarningsSerializer,
    CurrencyRevaluationSerializer,
)


class RecurringJournalViewSet(viewsets.ModelViewSet):
    queryset = RecurringJournal.objects.all().prefetch_related('lines')
    serializer_class = RecurringJournalSerializer
    filterset_fields = ['frequency', 'is_active']
    search_fields = ['name', 'code']

    @action(detail=False, methods=['get'])
    def default_dates(self, request):
        """Get default posting and reversal dates"""
        from accounting.utils import get_default_posting_and_reversal_dates
        return Response(get_default_posting_and_reversal_dates())

    @action(detail=False, methods=['post'])
    def generate(self, request):
        """Generate journals from recurring templates"""
        from ..advanced_services import RecurringJournalService
        result = RecurringJournalService.generate_journals()
        return Response(result)

    @action(detail=True, methods=['post'])
    def generate_now(self, request, pk=None):
        """Generate a single journal from template immediately"""
        from ..advanced_services import RecurringJournalService
        template = self.get_object()

        try:
            journal = RecurringJournalService.generate_single_journal(template, request.user)
            return Response({
                'status': 'success',
                'journal_id': journal.id,
                'journal_number': journal.reference_number
            })
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def generate_once(self, request, pk=None):
        """Generate a single journal from template"""
        from ..advanced_services import RecurringJournalService
        template = self.get_object()

        today = timezone.now().date()
        result = RecurringJournalService.generate_journals()

        if template.code in result.get('generated', []):
            return Response({'status': 'Journal generated successfully'})
        elif result.get('errors'):
            return Response({'error': result['errors']}, status=status.HTTP_400_BAD_REQUEST)

        return Response({'status': 'No journals generated'})


class RecurringJournalRunViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = RecurringJournalRun.objects.all().select_related('recurring_journal', 'journal')
    serializer_class = RecurringJournalRunSerializer
    filterset_fields = ['recurring_journal', 'status']


class AccrualViewSet(viewsets.ModelViewSet):
    queryset = Accrual.objects.all().select_related('account', 'counterpart_account', 'period', 'journal_entry')
    serializer_class = AccrualSerializer
    filterset_fields = ['accrual_type', 'is_reversed', 'is_posted', 'period']

    @action(detail=False, methods=['get'])
    def default_dates(self, request):
        """Get default posting and reversal dates"""
        from accounting.utils import get_default_posting_and_reversal_dates
        return Response(get_default_posting_and_reversal_dates())

    @action(detail=True, methods=['post'])
    def post(self, request, pk=None):
        """Post an accrual to create a journal entry"""
        from ..advanced_services import AccrualDeferralService
        accrual = self.get_object()

        try:
            journal = AccrualDeferralService.post_accrual(accrual, request.user)
            return Response({
                'status': 'success',
                'journal_id': journal.id,
                'journal_number': journal.reference_number
            })
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def reverse(self, request, pk=None):
        """Reverse an accrual"""
        from ..advanced_services import AccrualDeferralService
        accrual = self.get_object()

        try:
            journal = AccrualDeferralService.reverse_accrual(accrual, request.user)
            return Response({
                'status': 'success',
                'journal_id': journal.id,
                'journal_number': journal.reference_number
            })
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'])
    def reverse_all(self, request):
        """Reverse all due accruals for a period"""
        from ..advanced_services import AccrualDeferralService
        from ..models import BudgetPeriod

        period_id = request.data.get('period_id')
        if not period_id:
            return Response({'error': 'period_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            period = BudgetPeriod.objects.get(pk=period_id)
            count = AccrualDeferralService.reverse_accruals(period)
            return Response({'status': f'{count} accruals reversed'})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class DeferralViewSet(viewsets.ModelViewSet):
    queryset = Deferral.objects.all().select_related('account', 'counterpart_account')
    serializer_class = DeferralSerializer
    filterset_fields = ['deferral_type', 'is_active', 'is_fully_recognized']

    @action(detail=True, methods=['post'])
    def recognize(self, request, pk=None):
        """Recognize the next period for a single deferral."""
        from ..advanced_services import AccrualDeferralService
        deferral = self.get_object()
        try:
            journal = AccrualDeferralService.recognize_deferral(deferral, request.user)
            return Response({
                'status': 'success',
                'journal_id': journal.id,
                'journal_number': journal.reference_number,
            })
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'])
    def recognize_all(self, request):
        """Recognize deferrals for a period"""
        from ..advanced_services import AccrualDeferralService
        from ..models import BudgetPeriod

        period_id = request.data.get('period_id')
        if not period_id:
            return Response({'error': 'period_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            period = BudgetPeriod.objects.get(pk=period_id)
            count = AccrualDeferralService.recognize_deferrals(period)
            return Response({'status': f'{count} deferrals recognized'})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class PeriodStatusViewSet(viewsets.ModelViewSet):
    queryset = PeriodStatus.objects.all().select_related('period', 'closed_by')
    serializer_class = PeriodStatusSerializer
    filterset_fields = ['status']

    @action(detail=True, methods=['post'])
    def close_period(self, request, pk=None):
        """Close a period"""
        from ..advanced_services import PeriodClosingService
        status_obj = self.get_object()

        try:
            result = PeriodClosingService.close_period(status_obj.period, request.user)
            return Response(PeriodStatusSerializer(result).data)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def open_period(self, request, pk=None):
        """Reopen a period"""
        from ..advanced_services import PeriodClosingService
        status_obj = self.get_object()

        try:
            result = PeriodClosingService.open_period(status_obj.period, request.user)
            return Response(PeriodStatusSerializer(result).data)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def lock_period(self, request, pk=None):
        """Lock a period"""
        from ..advanced_services import PeriodClosingService
        status_obj = self.get_object()

        reason = request.data.get('reason', 'Manual lock')

        try:
            result = PeriodClosingService.lock_period(status_obj.period, request.user, reason)
            return Response(PeriodStatusSerializer(result).data)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class YearEndClosingViewSet(viewsets.ModelViewSet):
    queryset = YearEndClosing.objects.all().select_related('closing_journal', 'opening_journal', 'closed_by')
    serializer_class = YearEndClosingSerializer
    filterset_fields = ['fiscal_year', 'status']

    @action(detail=False, methods=['post'])
    def close_year(self, request):
        """Close a fiscal year"""
        from ..advanced_services import YearEndClosingService

        fiscal_year = request.data.get('fiscal_year')
        if not fiscal_year:
            return Response({'error': 'fiscal_year is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            result = YearEndClosingService.close_year(int(fiscal_year), request.user)
            return Response(YearEndClosingSerializer(result).data)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class RetainedEarningsViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = RetainedEarnings.objects.all()
    serializer_class = RetainedEarningsSerializer
    filterset_fields = ['fiscal_year']


class CurrencyRevaluationViewSet(viewsets.ModelViewSet):
    queryset = CurrencyRevaluation.objects.all().select_related('currency', 'journal_entry')
    serializer_class = CurrencyRevaluationSerializer
    filterset_fields = ['currency', 'status']

    @action(detail=False, methods=['post'])
    def revaluate(self, request):
        """Perform currency revaluation"""
        from ..advanced_services import CurrencyRevaluationService

        currency_id = request.data.get('currency_id')
        exchange_rate = request.data.get('exchange_rate')

        if not currency_id or not exchange_rate:
            return Response({'error': 'currency_id and exchange_rate are required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            currency = Currency.objects.get(pk=currency_id)
            result = CurrencyRevaluationService.revaluate(
                currency,
                Decimal(str(exchange_rate)),
                timezone.now().date(),
                request.user
            )
            return Response(CurrencyRevaluationSerializer(result).data)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
