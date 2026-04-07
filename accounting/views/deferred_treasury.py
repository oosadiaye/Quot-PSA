from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from django_filters.rest_framework import DjangoFilterBackend
import pandas as pd
from .common import AccountingPagination
from ..models import (
    DeferredRevenue, DeferredExpense,
    Lease, LeasePayment,
    TreasuryForecast, Investment, Loan, LoanRepayment,
    ExchangeRateHistory, ForeignCurrencyRevaluation,
    Currency,
)
from ..serializers import (
    DeferredRevenueSerializer, DeferredExpenseSerializer,
    LeaseSerializer, LeasePaymentSerializer,
    TreasuryForecastSerializer, InvestmentSerializer, LoanSerializer, LoanRepaymentSerializer,
    ExchangeRateHistorySerializer, ForeignCurrencyRevaluationSerializer,
)


class DeferredRevenueViewSet(viewsets.ModelViewSet):
    queryset = DeferredRevenue.objects.all().select_related('customer', 'revenue_account', 'unearned_revenue_account')
    serializer_class = DeferredRevenueSerializer
    filterset_fields = ['customer', 'is_fully_recognized']


class DeferredExpenseViewSet(viewsets.ModelViewSet):
    queryset = DeferredExpense.objects.all().select_related('vendor', 'expense_account', 'prepaid_account')
    serializer_class = DeferredExpenseSerializer
    filterset_fields = ['vendor', 'is_fully_recognized']


class LeaseViewSet(viewsets.ModelViewSet):
    queryset = Lease.objects.all().select_related('lessor', 'right_of_use_asset', 'lease_liability_account')
    serializer_class = LeaseSerializer
    filterset_fields = ['lease_type', 'status']


class LeasePaymentViewSet(viewsets.ModelViewSet):
    queryset = LeasePayment.objects.all().select_related('lease')
    serializer_class = LeasePaymentSerializer
    filterset_fields = ['lease', 'status']


class TreasuryForecastViewSet(viewsets.ModelViewSet):
    queryset = TreasuryForecast.objects.all()
    serializer_class = TreasuryForecastSerializer


class InvestmentViewSet(viewsets.ModelViewSet):
    queryset = Investment.objects.all().select_related('bank_account')
    serializer_class = InvestmentSerializer
    filterset_fields = ['investment_type', 'status']


class LoanViewSet(viewsets.ModelViewSet):
    queryset = Loan.objects.all().select_related('lender', 'loan_account', 'interest_expense_account')
    serializer_class = LoanSerializer
    filterset_fields = ['loan_type', 'status']


class LoanRepaymentViewSet(viewsets.ModelViewSet):
    queryset = LoanRepayment.objects.all().select_related('loan')
    serializer_class = LoanRepaymentSerializer
    filterset_fields = ['loan', 'status']


class ExchangeRateHistoryViewSet(viewsets.ModelViewSet):
    queryset = ExchangeRateHistory.objects.all().select_related('from_currency', 'to_currency')
    serializer_class = ExchangeRateHistorySerializer
    filterset_fields = ['from_currency', 'to_currency']

    @action(detail=False, methods=['get'], url_path='import-template')
    def import_template(self, request):
        """Download a CSV template for exchange rate imports."""
        import io, csv
        from django.http import HttpResponse

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['from_currency_code', 'to_currency_code', 'rate_date', 'exchange_rate'])
        writer.writerow(['USD', 'EUR', '2026-01-01', '0.920000'])
        writer.writerow(['USD', 'GBP', '2026-01-01', '0.790000'])
        writer.writerow(['EUR', 'GBP', '2026-01-01', '0.858700'])

        response = HttpResponse(output.getvalue(), content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="exchange_rate_import_template.csv"'
        return response

    @action(detail=False, methods=['post'], url_path='bulk-import')
    def bulk_import(self, request):
        """Import exchange rates from CSV/Excel file."""
        file = request.FILES.get('file')
        if not file:
            return Response({"error": "A CSV or Excel file is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            if file.name.endswith('.xlsx'):
                df = pd.read_excel(file)
            else:
                df = pd.read_csv(file)
        except Exception as e:
            return Response({"error": f"Failed to parse file: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

        df.columns = df.columns.str.strip().str.lower()
        required = {'from_currency_code', 'to_currency_code', 'rate_date', 'exchange_rate'}
        missing = required - set(df.columns)
        if missing:
            return Response({"error": f"Missing required columns: {', '.join(missing)}"}, status=status.HTTP_400_BAD_REQUEST)

        # Build currency code->id lookup
        currency_map = {c.code.upper(): c for c in Currency.objects.all()}

        created_count = 0
        updated_count = 0
        errors = []

        for index, row in df.iterrows():
            row_num = index + 2
            try:
                from_code = str(row['from_currency_code']).strip().upper()
                to_code = str(row['to_currency_code']).strip().upper()
                rate_date = str(row['rate_date']).strip()
                rate_val = float(row['exchange_rate'])

                if from_code not in currency_map:
                    errors.append(f"Row {row_num}: Unknown currency code '{from_code}'.")
                    continue
                if to_code not in currency_map:
                    errors.append(f"Row {row_num}: Unknown currency code '{to_code}'.")
                    continue
                if from_code == to_code:
                    errors.append(f"Row {row_num}: From and To currency cannot be the same.")
                    continue

                from_obj = currency_map[from_code]
                to_obj = currency_map[to_code]

                existing = ExchangeRateHistory.objects.filter(
                    from_currency=from_obj, to_currency=to_obj, rate_date=rate_date,
                ).first()
                if existing:
                    existing.exchange_rate = rate_val
                    existing.save()
                    updated_count += 1
                else:
                    ExchangeRateHistory.objects.create(
                        from_currency=from_obj, to_currency=to_obj,
                        rate_date=rate_date, exchange_rate=rate_val,
                    )
                    created_count += 1

            except Exception as e:
                errors.append(f"Row {row_num}: {str(e)}")

        return Response({
            "success": True,
            "created": created_count,
            "updated": updated_count,
            "errors": errors,
        })

    @action(detail=False, methods=['get'], url_path='export')
    def export_data(self, request):
        """Export exchange rates as CSV."""
        import io, csv
        from django.http import HttpResponse

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['from_currency_code', 'to_currency_code', 'rate_date', 'exchange_rate'])

        for r in self.get_queryset():
            writer.writerow([r.from_currency.code, r.to_currency.code, str(r.rate_date), str(r.exchange_rate)])

        response = HttpResponse(output.getvalue(), content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="exchange_rates_export.csv"'
        return response


class ForeignCurrencyRevaluationViewSet(viewsets.ModelViewSet):
    queryset = ForeignCurrencyRevaluation.objects.all().select_related('period', 'base_currency', 'gain_account', 'loss_account')
    serializer_class = ForeignCurrencyRevaluationSerializer
    filterset_fields = ['period', 'status']
