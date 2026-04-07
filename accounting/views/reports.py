from rest_framework import viewsets, status
from rest_framework.response import Response
from core.utils import api_response


class BalanceSheetViewSet(viewsets.ViewSet):

    def create(self, request):
        """Generate Balance Sheet report"""
        from ..reports import FinancialReportService
        from datetime import datetime

        start_date = request.data.get('start_date')
        end_date = request.data.get('end_date')

        if not start_date or not end_date:
            return api_response(error='start_date and end_date are required', status=status.HTTP_400_BAD_REQUEST)

        try:
            start = datetime.strptime(start_date, '%Y-%m-%d').date()
            end = datetime.strptime(end_date, '%Y-%m-%d').date()
        except ValueError:
            return api_response(error='Invalid date format. Use YYYY-MM-DD', status=status.HTTP_400_BAD_REQUEST)

        try:
            report = FinancialReportService.generate_balance_sheet(start, end)
            return api_response(data=report)
        except Exception as e:
            return api_response(error=str(e), status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class IncomeStatementViewSet(viewsets.ViewSet):

    def create(self, request):
        """Generate Income Statement report"""
        from ..reports import FinancialReportService
        from datetime import datetime

        start_date = request.data.get('start_date')
        end_date = request.data.get('end_date')

        if not start_date or not end_date:
            return api_response(error='start_date and end_date are required', status=status.HTTP_400_BAD_REQUEST)

        try:
            start = datetime.strptime(start_date, '%Y-%m-%d').date()
            end = datetime.strptime(end_date, '%Y-%m-%d').date()
        except ValueError:
            return api_response(error='Invalid date format. Use YYYY-MM-DD', status=status.HTTP_400_BAD_REQUEST)

        try:
            report = FinancialReportService.generate_income_statement(start, end)
            return api_response(data=report)
        except Exception as e:
            return api_response(error=str(e), status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CashFlowStatementViewSet(viewsets.ViewSet):

    def create(self, request):
        """Generate Cash Flow Statement report"""
        from ..reports import FinancialReportService
        from datetime import datetime

        start_date = request.data.get('start_date')
        end_date = request.data.get('end_date')
        method = request.data.get('method', 'direct')

        if not start_date or not end_date:
            return api_response(error='start_date and end_date are required', status=status.HTTP_400_BAD_REQUEST)

        try:
            start = datetime.strptime(start_date, '%Y-%m-%d').date()
            end = datetime.strptime(end_date, '%Y-%m-%d').date()
        except ValueError:
            return api_response(error='Invalid date format. Use YYYY-MM-DD', status=status.HTTP_400_BAD_REQUEST)

        try:
            if method == 'indirect':
                report = FinancialReportService.generate_cash_flow_indirect(start, end)
            else:
                report = FinancialReportService.generate_cash_flow_direct(start, end)
            return api_response(data=report)
        except Exception as e:
            return api_response(error=str(e), status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class BudgetVsActualViewSet(viewsets.ViewSet):

    def create(self, request):
        """Generate Budget vs Actual report"""
        from ..reports import BudgetReportService

        budget_period_id = request.data.get('budget_period_id')
        fund_id = request.data.get('fund_id')
        mda_id = request.data.get('mda_id')

        if not budget_period_id:
            return Response({'error': 'budget_period_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            report = BudgetReportService.generate_budget_vs_actual(
                budget_period_id=budget_period_id,
                fund_id=fund_id,
                mda_id=mda_id
            )
            return Response(report)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class BudgetPerformanceViewSet(viewsets.ViewSet):

    def create(self, request):
        """Generate Budget Performance report"""
        from ..reports import BudgetReportService

        fiscal_year = request.data.get('fiscal_year')
        fund_id = request.data.get('fund_id')

        if not fiscal_year:
            return Response({'error': 'fiscal_year is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            report = BudgetReportService.generate_budget_performance(
                fiscal_year=int(fiscal_year),
                fund_id=fund_id
            )
            return Response(report)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CostCenterReportViewSet(viewsets.ViewSet):

    def create(self, request):
        """Generate Cost Center report"""
        from ..reports import CostCenterReportService
        from datetime import datetime

        start_date = request.data.get('start_date')
        end_date = request.data.get('end_date')
        cost_center_id = request.data.get('cost_center_id')

        if not start_date or not end_date:
            return Response({'error': 'start_date and end_date are required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            start = datetime.strptime(start_date, '%Y-%m-%d').date()
            end = datetime.strptime(end_date, '%Y-%m-%d').date()
        except ValueError:
            return Response({'error': 'Invalid date format. Use YYYY-MM-DD'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            report = CostCenterReportService.generate_cost_center_report(
                start_date=start,
                end_date=end,
                cost_center_id=cost_center_id
            )
            return Response(report)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class IFRSComparisonViewSet(viewsets.ViewSet):

    def create(self, request):
        """Generate IFRS Comparison report"""
        from ..reports import IFRSReportService
        from datetime import datetime

        start_date = request.data.get('start_date')
        end_date = request.data.get('end_date')
        fiscal_year = request.data.get('fiscal_year')

        if not start_date or not end_date or not fiscal_year:
            return Response({'error': 'start_date, end_date, and fiscal_year are required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            start = datetime.strptime(start_date, '%Y-%m-%d').date()
            end = datetime.strptime(end_date, '%Y-%m-%d').date()
            year = int(fiscal_year)
        except ValueError:
            return Response({'error': 'Invalid date format. Use YYYY-MM-DD'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            report = IFRSReportService.generate_ifrs_comparison_report(
                start_date=start,
                end_date=end,
                fiscal_year=year
            )
            return Response(report)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class GeneralLedgerViewSet(viewsets.ViewSet):

    def create(self, request):
        """Generate General Ledger report"""
        from ..reports import GeneralLedgerReportService
        from datetime import datetime

        start_date = request.data.get('start_date')
        end_date = request.data.get('end_date')
        account_code = request.data.get('account_code')

        if not start_date or not end_date:
            return Response({'error': 'start_date and end_date are required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            start = datetime.strptime(start_date, '%Y-%m-%d').date()
            end = datetime.strptime(end_date, '%Y-%m-%d').date()
        except ValueError:
            return Response({'error': 'Invalid date format. Use YYYY-MM-DD'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            report = GeneralLedgerReportService.generate_general_ledger(
                start_date=start,
                end_date=end,
                account_code=account_code
            )
            return Response(report)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class TrialBalanceViewSet(viewsets.ViewSet):

    def create(self, request):
        """Generate Trial Balance report"""
        from ..reports import TrialBalanceReportService
        from datetime import datetime

        end_date = request.data.get('end_date')
        start_date = request.data.get('start_date', '1900-01-01')

        if not end_date:
            return api_response(error='end_date is required', status=status.HTTP_400_BAD_REQUEST)

        try:
            start = datetime.strptime(start_date, '%Y-%m-%d').date()
            end = datetime.strptime(end_date, '%Y-%m-%d').date()
        except ValueError:
            return api_response(error='Invalid date format. Use YYYY-MM-DD', status=status.HTTP_400_BAD_REQUEST)

        try:
            report = TrialBalanceReportService.generate_trial_balance(start, end)
            return api_response(data=report)
        except Exception as e:
            return api_response(error=str(e), status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class InventoryStockValuationViewSet(viewsets.ViewSet):

    def create(self, request):
        """Generate Inventory Stock Valuation report"""
        from ..reports import InventoryReportService

        warehouse_id = request.data.get('warehouse_id')

        try:
            report = InventoryReportService.generate_stock_valuation(warehouse_id)
            return Response(report)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class InventoryLowStockViewSet(viewsets.ViewSet):

    def list(self, request):
        """Generate Low Stock Alert report"""
        from ..reports import InventoryReportService

        try:
            report = InventoryReportService.generate_low_stock_report()
            return Response(report)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class InventoryMovementViewSet(viewsets.ViewSet):

    def create(self, request):
        """Generate Stock Movement report"""
        from ..reports import InventoryReportService
        from datetime import datetime

        start_date = request.data.get('start_date')
        end_date = request.data.get('end_date')

        if not start_date or not end_date:
            return Response({'error': 'start_date and end_date are required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            start = datetime.strptime(start_date, '%Y-%m-%d').date()
            end = datetime.strptime(end_date, '%Y-%m-%d').date()
        except ValueError:
            return Response({'error': 'Invalid date format. Use YYYY-MM-DD'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            report = InventoryReportService.generate_stock_movement(start, end)
            return Response(report)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class HRHeadcountViewSet(viewsets.ViewSet):

    def list(self, request):
        """Generate Headcount Report"""
        from ..reports import HRReportService

        try:
            report = HRReportService.generate_headcount_report()
            return Response(report)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class HRPayrollSummaryViewSet(viewsets.ViewSet):

    def create(self, request):
        """Generate Payroll Summary Report"""
        from ..reports import HRReportService

        month = request.data.get('month')
        year = request.data.get('year')

        if not month or not year:
            return Response({'error': 'month and year are required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            report = HRReportService.generate_payroll_summary(int(month), int(year))
            return Response(report)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class SalesSummaryViewSet(viewsets.ViewSet):

    def create(self, request):
        """Generate Sales Summary Report"""
        from ..reports import SalesReportService
        from datetime import datetime

        start_date = request.data.get('start_date')
        end_date = request.data.get('end_date')

        if not start_date or not end_date:
            return Response({'error': 'start_date and end_date are required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            start = datetime.strptime(start_date, '%Y-%m-%d').date()
            end = datetime.strptime(end_date, '%Y-%m-%d').date()
        except ValueError:
            return Response({'error': 'Invalid date format. Use YYYY-MM-DD'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            report = SalesReportService.generate_sales_summary(start, end)
            return Response(report)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class SalesCustomersViewSet(viewsets.ViewSet):

    def list(self, request):
        """Generate Customers Report"""
        from ..reports import SalesReportService

        try:
            report = SalesReportService.generate_customers_report()
            return Response(report)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ProcurementSummaryViewSet(viewsets.ViewSet):

    def create(self, request):
        """Generate Purchase Summary Report"""
        from ..reports import ProcurementReportService
        from datetime import datetime

        start_date = request.data.get('start_date')
        end_date = request.data.get('end_date')

        if not start_date or not end_date:
            return Response({'error': 'start_date and end_date are required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            start = datetime.strptime(start_date, '%Y-%m-%d').date()
            end = datetime.strptime(end_date, '%Y-%m-%d').date()
        except ValueError:
            return Response({'error': 'Invalid date format. Use YYYY-MM-DD'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            report = ProcurementReportService.generate_purchase_summary(start, end)
            return Response(report)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ProcurementVendorsViewSet(viewsets.ViewSet):

    def list(self, request):
        """Generate Vendors Report"""
        from ..reports import ProcurementReportService

        try:
            report = ProcurementReportService.generate_vendors_report()
            return Response(report)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ProductionSummaryViewSet(viewsets.ViewSet):

    def create(self, request):
        """Generate Production Summary Report"""
        from ..reports import ProductionReportService
        from datetime import datetime

        start_date = request.data.get('start_date')
        end_date = request.data.get('end_date')

        if not start_date or not end_date:
            return Response({'error': 'start_date and end_date are required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            start = datetime.strptime(start_date, '%Y-%m-%d').date()
            end = datetime.strptime(end_date, '%Y-%m-%d').date()
        except ValueError:
            return Response({'error': 'Invalid date format. Use YYYY-MM-DD'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            report = ProductionReportService.generate_production_summary(start, end)
            return Response(report)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ProductionMaterialConsumptionViewSet(viewsets.ViewSet):

    def create(self, request):
        """Generate Material Consumption Report"""
        from ..reports import ProductionReportService
        from datetime import datetime

        start_date = request.data.get('start_date')
        end_date = request.data.get('end_date')

        if not start_date or not end_date:
            return Response({'error': 'start_date and end_date are required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            start = datetime.strptime(start_date, '%Y-%m-%d').date()
            end = datetime.strptime(end_date, '%Y-%m-%d').date()
        except ValueError:
            return Response({'error': 'Invalid date format. Use YYYY-MM-DD'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            report = ProductionReportService.generate_material_consumption(start, end)
            return Response(report)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ProductionCostReportViewSet(viewsets.ViewSet):

    def create(self, request):
        """Generate Production Cost & Profitability Report"""
        from ..reports import ProductionReportService
        from datetime import datetime

        start_date = request.data.get('start_date')
        end_date = request.data.get('end_date')

        if not start_date or not end_date:
            return Response({'error': 'start_date and end_date are required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            start = datetime.strptime(start_date, '%Y-%m-%d').date()
            end = datetime.strptime(end_date, '%Y-%m-%d').date()
        except ValueError:
            return Response({'error': 'Invalid date format. Use YYYY-MM-DD'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            report = ProductionReportService.generate_production_cost_report(start, end)
            return Response(report)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ProductProfitabilityViewSet(viewsets.ViewSet):

    def create(self, request):
        """Generate Product Profitability Analysis Report"""
        from ..reports import ProductionReportService
        from datetime import datetime

        start_date = request.data.get('start_date')
        end_date = request.data.get('end_date')

        if not start_date or not end_date:
            return Response({'error': 'start_date and end_date are required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            start = datetime.strptime(start_date, '%Y-%m-%d').date()
            end = datetime.strptime(end_date, '%Y-%m-%d').date()
        except ValueError:
            return Response({'error': 'Invalid date format. Use YYYY-MM-DD'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            report = ProductionReportService.generate_product_profitability(start, end)
            return Response(report)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
