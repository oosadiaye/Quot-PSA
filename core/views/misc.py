import logging
import time

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.utils import timezone

logger = logging.getLogger('dtsg')


MENU_STRUCTURE = {
    "dashboard": {
        "title": "Dashboard",
        "icon": "dashboard",
        "url": "/dashboard"
    },
    "modules": [
        {
            "name": "accounting",
            "title": "Accounting",
            "icon": "account_balance",
            "url": "/accounting",
            "submenu": [
                {"title": "Chart of Accounts", "url": "/accounting/accounts"},
                {"title": "Journals", "url": "/accounting/journals"},
                {"title": "Funds", "url": "/accounting/funds"},
                {"title": "Functions", "url": "/accounting/functions"},
                {"title": "Programs", "url": "/accounting/programs"},
                {"title": "Geos", "url": "/accounting/geos"},
                {"title": "Currencies", "url": "/accounting/currencies"},
                {"title": "Vendor Invoices", "url": "/accounting/vendor-invoices"},
                {"title": "Payments", "url": "/accounting/payments"},
                {"title": "Customer Invoices", "url": "/accounting/customer-invoices"},
                {"title": "Receipts", "url": "/accounting/receipts"},
                {"title": "Fixed Assets", "url": "/accounting/fixed-assets"},
                {"title": "GL Balances", "url": "/accounting/gl-balances"},
            ]
        },
        {
            "name": "budget",
            "title": "Budget",
            "icon": "budget",
            "url": "/budget",
            "submenu": [
                {"title": "Budget Allocations", "url": "/budget/allocations"},
                {"title": "Budget Lines", "url": "/budget/lines"},
                {"title": "Variance Analysis", "url": "/budget/variances"},
            ]
        },
        {
            "name": "procurement",
            "title": "Procurement",
            "icon": "shopping_cart",
            "url": "/procurement",
            "submenu": [
                {"title": "Vendors", "url": "/procurement/vendors"},
                {"title": "Purchase Requests", "url": "/procurement/requests"},
                {"title": "Purchase Orders", "url": "/procurement/orders"},
                {"title": "Goods Received Notes", "url": "/procurement/grns"},
                {"title": "Invoice Matching", "url": "/procurement/invoice-matching"},
            ]
        },
        {
            "name": "inventory",
            "title": "Inventory",
            "icon": "inventory",
            "url": "/inventory",
            "submenu": [
                {"title": "Warehouses", "url": "/inventory/warehouses"},
                {"title": "Item Categories", "url": "/inventory/categories"},
                {"title": "Items", "url": "/inventory/items"},
                {"title": "Stock by Warehouse", "url": "/inventory/stocks"},
                {"title": "Batches/Lots", "url": "/inventory/batches"},
                {"title": "Stock Movements", "url": "/inventory/movements"},
                {"title": "Stock Valuation", "url": "/inventory/valuation"},
                {"title": "Stock Transfers", "url": "/inventory/transfers"},
                {"title": "Reconciliations", "url": "/inventory/reconciliations"},
                {"title": "Reorder Alerts", "url": "/inventory/reorder-alerts"},
            ]
        },
        {
            "name": "sales",
            "title": "Sales",
            "icon": "point_of_sale",
            "url": "/sales",
            "submenu": [
                {"title": "Customers", "url": "/sales/customers"},
                {"title": "Leads", "url": "/sales/leads"},
                {"title": "Opportunities", "url": "/sales/opportunities"},
                {"title": "Quotations", "url": "/sales/quotations"},
                {"title": "Sales Orders", "url": "/sales/orders"},
            ]
        },
        {
            "name": "service",
            "title": "Service",
            "icon": "build",
            "url": "/service",
            "submenu": [
                {"title": "Service Assets", "url": "/service/assets"},
                {"title": "Technicians", "url": "/service/technicians"},
                {"title": "Service Tickets", "url": "/service/tickets"},
                {"title": "Maintenance Schedules", "url": "/service/schedules"},
                {"title": "Work Orders", "url": "/service/work-orders"},
                {"title": "Citizen Requests", "url": "/service/citizen-requests"},
                {"title": "Service Metrics", "url": "/service/metrics"},
            ]
        },
        {
            "name": "workflow",
            "title": "Workflow",
            "icon": "account_tree",
            "url": "/workflow",
            "submenu": [
                {"title": "Workflow Definitions", "url": "/workflow/definitions"},
                {"title": "Workflow Instances", "url": "/workflow/instances"},
            ]
        },
        {
            "name": "hrm",
            "title": "Human Resources",
            "icon": "people",
            "url": "/hrm",
            "submenu": [
                {"title": "Employees", "url": "/hrm/employees"},
                {"title": "Departments", "url": "/hrm/departments"},
                {"title": "Positions", "url": "/hrm/positions"},
                {"title": "Leave Requests", "url": "/hrm/leave-requests"},
                {"title": "Attendance", "url": "/hrm/attendances"},
                {"title": "Holidays", "url": "/hrm/holidays"},
                {"title": "Job Posts", "url": "/hrm/job-posts"},
                {"title": "Candidates", "url": "/hrm/candidates"},
                {"title": "Payroll", "url": "/hrm/payroll-runs"},
                {"title": "Payslips", "url": "/hrm/payslips"},
                {"title": "Performance", "url": "/hrm/performance-cycles"},
                {"title": "Training", "url": "/hrm/training-programs"},
                {"title": "Skills", "url": "/hrm/skills"},
                {"title": "Policies", "url": "/hrm/policies"},
                {"title": "Compliance", "url": "/hrm/compliance-records"},
                {"title": "Exit Requests", "url": "/hrm/exit-requests"},
                {"title": "Reports", "url": "/hrm/reports"},
            ]
        },
        {
            "name": "core",
            "title": "User Management",
            "icon": "people",
            "url": "/core",
            "submenu": [
                {"title": "Users", "url": "/core/users"},
            ]
        },
    ]
}


@api_view(['GET'])
def menu_api(request):
    """Returns the complete menu structure for the sidebar"""
    return Response(MENU_STRUCTURE)


@api_view(['GET'])
@permission_classes([AllowAny])
@authentication_classes([])
def health_check(request):
    """Health check endpoint for load balancers and monitoring"""
    health = {'status': 'healthy', 'timestamp': timezone.now().isoformat()}
    try:
        from django.db import connection
        start = time.monotonic()
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
        health['database'] = 'ok'
        health['db_response_ms'] = round((time.monotonic() - start) * 1000, 2)
    except Exception:
        health['status'] = 'degraded'
        health['database'] = 'error'
    return Response(health, status=status.HTTP_200_OK if health['status'] == 'healthy' else status.HTTP_503_SERVICE_UNAVAILABLE)


@api_view(['GET'])
def api_root(request):
    """Returns all available API endpoints"""
    return Response({
        "name": "QUOT ERP API",
        "version": "1.0.0",
        "description": "Enterprise Resource Planning System",
        "endpoints": {
            "accounting": "/api/accounting/",
            "budget": "/api/budget/",
            "procurement": "/api/procurement/",
            "inventory": "/api/inventory/",
            "sales": "/api/sales/",
            "service": "/api/service/",
            "workflow": "/api/workflow/",
            "hrm": "/api/hrm/",
            "core": "/api/core/",
        },
        "menu": "/api/menu/",
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dashboard_stats(request):
    """Returns cross-module KPI counts and analytics for the tenant dashboard."""
    from django.apps import apps
    from django.db.models import Sum, Count, F, Q
    from django.db.models.functions import TruncMonth, Coalesce
    from decimal import Decimal
    import datetime

    stats = {}
    today = timezone.now().date()
    current_month_start = today.replace(day=1)
    # Previous month
    if current_month_start.month == 1:
        prev_month_start = current_month_start.replace(year=current_month_start.year - 1, month=12)
    else:
        prev_month_start = current_month_start.replace(month=current_month_start.month - 1)
    prev_month_end = current_month_start - datetime.timedelta(days=1)
    # 6 months ago for trend charts
    six_months_ago = (current_month_start - datetime.timedelta(days=180)).replace(day=1)

    def _safe_float(val):
        """Convert Decimal/None to float for JSON serialization."""
        if val is None:
            return 0.0
        return float(val)

    # ── KPI Cards ─────────────────────────────────────────────

    # Pending approvals (workflow module)
    try:
        WorkflowInstance = apps.get_model('workflow', 'WorkflowInstance')
        stats['pending_approvals'] = WorkflowInstance.objects.filter(
            status__in=['pending', 'in_review']
        ).count()
    except LookupError:
        stats['pending_approvals'] = 0

    # Active work orders (service module)
    try:
        WorkOrder = apps.get_model('service', 'WorkOrder')
        stats['active_work_orders'] = WorkOrder.objects.filter(
            status__in=['open', 'in_progress']
        ).count()
    except LookupError:
        stats['active_work_orders'] = 0

    # Open requisitions (procurement module)
    try:
        PurchaseRequisition = apps.get_model('procurement', 'PurchaseRequisition')
        stats['open_requisitions'] = PurchaseRequisition.objects.filter(
            status__in=['draft', 'submitted', 'approved']
        ).count()
    except LookupError:
        stats['open_requisitions'] = 0

    # Low stock alerts (inventory module)
    try:
        ItemStock = apps.get_model('inventory', 'ItemStock')
        stats['low_stock_alerts'] = ItemStock.objects.filter(
            item__is_active=True,
            item__reorder_point__isnull=False,
            quantity__lte=F('item__reorder_point'),
        ).values('item').distinct().count()
    except (LookupError, Exception):
        stats['low_stock_alerts'] = 0

    # ── Revenue & Expenses (from GL Journal Lines) ────────────
    # Revenue = credit balances on 4xxxx accounts (income)
    # Expenses = debit balances on 5xxxx-9xxxx accounts (expense)
    try:
        JournalLine = apps.get_model('accounting', 'JournalLine')
        JournalHeader = apps.get_model('accounting', 'JournalHeader')

        posted_lines = JournalLine.objects.filter(
            journal__status='Posted',
        )

        # Current month revenue (credits on 4x accounts)
        revenue_mtd = posted_lines.filter(
            journal__posting_date__gte=current_month_start,
            journal__posting_date__lte=today,
            account__code__startswith='4',
        ).aggregate(total=Coalesce(Sum('credit'), Decimal('0')) - Coalesce(Sum('debit'), Decimal('0')))['total']

        # Previous month revenue
        revenue_prev = posted_lines.filter(
            journal__posting_date__gte=prev_month_start,
            journal__posting_date__lte=prev_month_end,
            account__code__startswith='4',
        ).aggregate(total=Coalesce(Sum('credit'), Decimal('0')) - Coalesce(Sum('debit'), Decimal('0')))['total']

        # Current month expenses (debits on 5x-9x accounts)
        expense_mtd = posted_lines.filter(
            journal__posting_date__gte=current_month_start,
            journal__posting_date__lte=today,
        ).filter(
            Q(account__code__startswith='5') | Q(account__code__startswith='6') |
            Q(account__code__startswith='7') | Q(account__code__startswith='8') |
            Q(account__code__startswith='9')
        ).aggregate(total=Coalesce(Sum('debit'), Decimal('0')) - Coalesce(Sum('credit'), Decimal('0')))['total']

        expense_prev = posted_lines.filter(
            journal__posting_date__gte=prev_month_start,
            journal__posting_date__lte=prev_month_end,
        ).filter(
            Q(account__code__startswith='5') | Q(account__code__startswith='6') |
            Q(account__code__startswith='7') | Q(account__code__startswith='8') |
            Q(account__code__startswith='9')
        ).aggregate(total=Coalesce(Sum('debit'), Decimal('0')) - Coalesce(Sum('credit'), Decimal('0')))['total']

        stats['revenue_mtd'] = _safe_float(revenue_mtd)
        stats['revenue_prev'] = _safe_float(revenue_prev)
        stats['expenses_mtd'] = _safe_float(expense_mtd)
        stats['expenses_prev'] = _safe_float(expense_prev)
        stats['net_income_mtd'] = _safe_float(revenue_mtd) - _safe_float(expense_mtd)

        # ── Monthly Revenue & Expense trend (last 6 months) ──
        monthly_revenue = (
            posted_lines
            .filter(journal__posting_date__gte=six_months_ago, account__code__startswith='4')
            .annotate(month=TruncMonth('journal__posting_date'))
            .values('month')
            .annotate(
                revenue=Coalesce(Sum('credit'), Decimal('0')) - Coalesce(Sum('debit'), Decimal('0')),
            )
            .order_by('month')
        )
        monthly_expense = (
            posted_lines
            .filter(journal__posting_date__gte=six_months_ago)
            .filter(
                Q(account__code__startswith='5') | Q(account__code__startswith='6') |
                Q(account__code__startswith='7') | Q(account__code__startswith='8') |
                Q(account__code__startswith='9')
            )
            .annotate(month=TruncMonth('journal__posting_date'))
            .values('month')
            .annotate(
                expense=Coalesce(Sum('debit'), Decimal('0')) - Coalesce(Sum('credit'), Decimal('0')),
            )
            .order_by('month')
        )

        # Merge into single list
        rev_map = {r['month'].strftime('%Y-%m'): _safe_float(r['revenue']) for r in monthly_revenue}
        exp_map = {e['month'].strftime('%Y-%m'): _safe_float(e['expense']) for e in monthly_expense}
        all_months = sorted(set(list(rev_map.keys()) + list(exp_map.keys())))
        # If no data, generate last 6 month keys anyway
        if not all_months:
            all_months = []
            m = six_months_ago
            while m <= current_month_start:
                all_months.append(m.strftime('%Y-%m'))
                if m.month == 12:
                    m = m.replace(year=m.year + 1, month=1)
                else:
                    m = m.replace(month=m.month + 1)

        stats['monthly_trend'] = [
            {
                'month': mk,
                'revenue': rev_map.get(mk, 0),
                'expenses': exp_map.get(mk, 0),
                'net': rev_map.get(mk, 0) - exp_map.get(mk, 0),
            }
            for mk in all_months
        ]

    except (LookupError, Exception) as e:
        logger.warning('Dashboard GL stats failed: %s', e)
        stats['revenue_mtd'] = 0
        stats['revenue_prev'] = 0
        stats['expenses_mtd'] = 0
        stats['expenses_prev'] = 0
        stats['net_income_mtd'] = 0
        stats['monthly_trend'] = []

    # ── Accounts Receivable ───────────────────────────────────
    try:
        CustomerInvoice = apps.get_model('accounting', 'CustomerInvoice')
        ar_data = CustomerInvoice.objects.filter(
            status__in=['Sent', 'Partially Paid', 'Overdue']
        ).aggregate(
            total_outstanding=Coalesce(Sum(F('total_amount') - F('received_amount')), Decimal('0')),
            overdue_count=Count('id', filter=Q(status='Overdue')),
            overdue_amount=Coalesce(
                Sum(F('total_amount') - F('received_amount'), filter=Q(status='Overdue')),
                Decimal('0')
            ),
        )
        stats['ar_outstanding'] = _safe_float(ar_data['total_outstanding'])
        stats['ar_overdue_count'] = ar_data['overdue_count']
        stats['ar_overdue_amount'] = _safe_float(ar_data['overdue_amount'])
    except (LookupError, Exception):
        stats['ar_outstanding'] = 0
        stats['ar_overdue_count'] = 0
        stats['ar_overdue_amount'] = 0

    # ── Accounts Payable ──────────────────────────────────────
    try:
        VendorInvoice = apps.get_model('accounting', 'VendorInvoice')
        ap_data = VendorInvoice.objects.exclude(
            status__in=['Paid', 'Void', 'Draft']
        ).aggregate(
            total_outstanding=Coalesce(Sum('balance_due'), Decimal('0')),
            total_count=Count('id'),
        )
        stats['ap_outstanding'] = _safe_float(ap_data['total_outstanding'])
        stats['ap_count'] = ap_data['total_count']
    except (LookupError, Exception):
        stats['ap_outstanding'] = 0
        stats['ap_count'] = 0

    # ── Cash Flow (Payments & Receipts this month) ────────────
    try:
        Payment = apps.get_model('accounting', 'Payment')
        Receipt = apps.get_model('accounting', 'Receipt')

        cash_in = Receipt.objects.filter(
            status='Posted',
            receipt_date__gte=current_month_start,
            receipt_date__lte=today,
        ).aggregate(total=Coalesce(Sum('total_amount'), Decimal('0')))['total']

        cash_out = Payment.objects.filter(
            status='Posted',
            payment_date__gte=current_month_start,
            payment_date__lte=today,
        ).aggregate(total=Coalesce(Sum('total_amount'), Decimal('0')))['total']

        stats['cash_in_mtd'] = _safe_float(cash_in)
        stats['cash_out_mtd'] = _safe_float(cash_out)
        stats['net_cash_flow'] = _safe_float(cash_in) - _safe_float(cash_out)
    except (LookupError, Exception):
        stats['cash_in_mtd'] = 0
        stats['cash_out_mtd'] = 0
        stats['net_cash_flow'] = 0

    # ── Sales stats ───────────────────────────────────────────
    try:
        SalesOrder = apps.get_model('sales', 'SalesOrder')
        sales_mtd = SalesOrder.objects.filter(
            status__in=['Approved', 'Posted', 'Closed'],
            order_date__gte=current_month_start,
            order_date__lte=today,
        ).aggregate(total=Coalesce(Sum('tax_amount'), Decimal('0')))
        # tax_amount is often used for total; try to get actual total
        # SalesOrder.total_amount is a property, so we sum line totals
        SalesOrderLine = apps.get_model('sales', 'SalesOrderLine')
        sales_total = SalesOrderLine.objects.filter(
            sales_order__status__in=['Approved', 'Posted', 'Closed'],
            sales_order__order_date__gte=current_month_start,
            sales_order__order_date__lte=today,
        ).aggregate(
            total=Coalesce(Sum(F('quantity') * F('unit_price')), Decimal('0'))
        )['total']
        stats['sales_mtd'] = _safe_float(sales_total)
        stats['sales_order_count'] = SalesOrder.objects.filter(
            order_date__gte=current_month_start, order_date__lte=today,
        ).count()
    except (LookupError, Exception):
        stats['sales_mtd'] = 0
        stats['sales_order_count'] = 0

    # ── Procurement spend ─────────────────────────────────────
    try:
        PurchaseOrder = apps.get_model('procurement', 'PurchaseOrder')
        PurchaseOrderLine = apps.get_model('procurement', 'PurchaseOrderLine')
        po_total = PurchaseOrderLine.objects.filter(
            purchase_order__status__in=['Approved', 'Posted', 'Closed'],
            purchase_order__order_date__gte=current_month_start,
            purchase_order__order_date__lte=today,
        ).aggregate(
            total=Coalesce(Sum(F('quantity') * F('unit_price')), Decimal('0'))
        )['total']
        stats['procurement_mtd'] = _safe_float(po_total)
    except (LookupError, Exception):
        stats['procurement_mtd'] = 0

    # ── Budget utilization ────────────────────────────────────
    try:
        BudgetLine = apps.get_model('budget', 'BudgetLine')
        budget_data = BudgetLine.objects.filter(
            budget__status='Approved',
        ).aggregate(
            total_allocated=Coalesce(Sum('amount_allocated'), Decimal('0')),
            total_consumed=Coalesce(Sum('amount_consumed'), Decimal('0')),
            total_reserved=Coalesce(Sum('amount_reserved'), Decimal('0')),
        )
        allocated = _safe_float(budget_data['total_allocated'])
        consumed = _safe_float(budget_data['total_consumed'])
        reserved = _safe_float(budget_data['total_reserved'])
        stats['budget_allocated'] = allocated
        stats['budget_consumed'] = consumed
        stats['budget_reserved'] = reserved
        stats['budget_available'] = allocated - consumed - reserved
        stats['budget_utilization'] = round((consumed / allocated * 100), 1) if allocated > 0 else 0
    except (LookupError, Exception):
        stats['budget_allocated'] = 0
        stats['budget_consumed'] = 0
        stats['budget_reserved'] = 0
        stats['budget_available'] = 0
        stats['budget_utilization'] = 0

    # ── Employee headcount ────────────────────────────────────
    try:
        Employee = apps.get_model('hrm', 'Employee')
        stats['active_employees'] = Employee.objects.filter(status='Active').count()
        stats['total_employees'] = Employee.objects.exclude(status='Terminated').count()
    except (LookupError, Exception):
        stats['active_employees'] = 0
        stats['total_employees'] = 0

    # ── Production analytics ────────────────────────────────────
    try:
        ProductionOrder = apps.get_model('production', 'ProductionOrder')
        prod_qs = ProductionOrder.objects.all()
        stats['production_in_progress'] = prod_qs.filter(status__in=['In Progress', 'in_progress']).count()
        stats['production_planned'] = prod_qs.filter(status__in=['Planned', 'planned', 'Draft', 'draft']).count()
        stats['production_completed_mtd'] = prod_qs.filter(
            status__in=['Completed', 'completed', 'Closed', 'closed'],
            updated_at__gte=current_month_start,
        ).count()
        stats['production_total'] = prod_qs.exclude(
            status__in=['Cancelled', 'cancelled']
        ).count()
    except (LookupError, Exception):
        stats['production_in_progress'] = 0
        stats['production_planned'] = 0
        stats['production_completed_mtd'] = 0
        stats['production_total'] = 0

    # ── Quality analytics ─────────────────────────────────────
    try:
        QualityInspection = apps.get_model('quality', 'QualityInspection')
        qi_qs = QualityInspection.objects.all()
        stats['quality_pending'] = qi_qs.filter(status__in=['Pending', 'pending', 'In Progress', 'in_progress']).count()
        stats['quality_passed_mtd'] = qi_qs.filter(
            status__in=['Passed', 'passed', 'Accepted', 'accepted'],
            updated_at__gte=current_month_start,
        ).count()
        stats['quality_failed_mtd'] = qi_qs.filter(
            status__in=['Failed', 'failed', 'Rejected', 'rejected'],
            updated_at__gte=current_month_start,
        ).count()
    except (LookupError, Exception):
        stats['quality_pending'] = 0
        stats['quality_passed_mtd'] = 0
        stats['quality_failed_mtd'] = 0

    try:
        NonConformance = apps.get_model('quality', 'NonConformance')
        stats['open_ncr'] = NonConformance.objects.filter(
            status__in=['Open', 'open', 'In Progress', 'in_progress']
        ).count()
    except (LookupError, Exception):
        stats['open_ncr'] = 0

    # ── Inventory analytics ───────────────────────────────────
    try:
        Item = apps.get_model('inventory', 'Item')
        stats['total_items'] = Item.objects.filter(is_active=True).count()
        ItemStock = apps.get_model('inventory', 'ItemStock')
        stock_agg = ItemStock.objects.aggregate(
            total_value=Coalesce(Sum('quantity'), Decimal('0')),
        )
        stats['total_stock_qty'] = _safe_float(stock_agg['total_value'])
        # Stock value from Item.total_value
        item_value = Item.objects.filter(is_active=True).aggregate(
            total=Coalesce(Sum('total_value'), Decimal('0'))
        )['total']
        stats['inventory_value'] = _safe_float(item_value)
    except (LookupError, Exception):
        stats['total_items'] = 0
        stats['total_stock_qty'] = 0
        stats['inventory_value'] = 0

    # Stock movements this month
    try:
        StockMovement = apps.get_model('inventory', 'StockMovement')
        movements_mtd = StockMovement.objects.filter(
            created_at__gte=current_month_start,
        )
        stats['stock_movements_in'] = movements_mtd.filter(movement_type='IN').count()
        stats['stock_movements_out'] = movements_mtd.filter(movement_type='OUT').count()
    except (LookupError, Exception):
        stats['stock_movements_in'] = 0
        stats['stock_movements_out'] = 0

    # ── Service analytics ─────────────────────────────────────
    try:
        ServiceTicket = apps.get_model('service', 'ServiceTicket')
        st_qs = ServiceTicket.objects.all()
        stats['tickets_open'] = st_qs.filter(status__in=['Open', 'open', 'New', 'new']).count()
        stats['tickets_in_progress'] = st_qs.filter(status__in=['In Progress', 'in_progress']).count()
        stats['tickets_resolved_mtd'] = st_qs.filter(
            status__in=['Resolved', 'resolved', 'Closed', 'closed'],
            updated_at__gte=current_month_start,
        ).count()
    except (LookupError, Exception):
        stats['tickets_open'] = 0
        stats['tickets_in_progress'] = 0
        stats['tickets_resolved_mtd'] = 0

    # ── Fixed Assets summary ──────────────────────────────────
    try:
        FixedAsset = apps.get_model('accounting', 'FixedAsset')
        fa_qs = FixedAsset.objects.filter(status__in=['Active', 'active', 'In Use', 'in_use'])
        stats['fixed_assets_count'] = fa_qs.count()
        stats['fixed_assets_value'] = _safe_float(
            fa_qs.aggregate(total=Coalesce(Sum('acquisition_cost'), Decimal('0')))['total']
        )
        stats['fixed_assets_nbv'] = _safe_float(
            fa_qs.aggregate(total=Coalesce(Sum('net_book_value'), Decimal('0')))['total']
        )
    except (LookupError, Exception):
        stats['fixed_assets_count'] = 0
        stats['fixed_assets_value'] = 0
        stats['fixed_assets_nbv'] = 0

    # ── Recent transactions (last 10 posted journals) ─────────
    try:
        JournalHeader = apps.get_model('accounting', 'JournalHeader')
        recent = JournalHeader.objects.filter(
            status='Posted',
        ).order_by('-posting_date', '-id')[:10]
        stats['recent_transactions'] = [
            {
                'id': j.id,
                'reference': j.reference_number,
                'date': j.posting_date.isoformat() if j.posting_date else '',
                'description': j.description[:80] if j.description else '',
                'source': getattr(j, 'source_module', '') or '',
                'amount': _safe_float(
                    j.lines.aggregate(total=Coalesce(Sum('debit'), Decimal('0')))['total']
                ),
            }
            for j in recent
        ]
    except (LookupError, Exception):
        stats['recent_transactions'] = []

    return Response(stats)


@api_view(['GET'])
def module_list(request):
    """Returns all available modules with their endpoints"""
    modules = [
        {
            "name": "accounting",
            "title": "Accounting",
            "description": "Financial management, journals, AP/AR, fixed assets",
            "icon": "account_balance",
            "endpoints": [
                {"name": "Funds", "url": "/api/accounting/funds/"},
                {"name": "Functions", "url": "/api/accounting/functions/"},
                {"name": "Programs", "url": "/api/accounting/programs/"},
                {"name": "Geos", "url": "/api/accounting/geos/"},
                {"name": "Accounts", "url": "/api/accounting/accounts/"},
                {"name": "Journals", "url": "/api/accounting/journals/"},
                {"name": "Currencies", "url": "/api/accounting/currencies/"},
                {"name": "Vendor Invoices", "url": "/api/accounting/vendor-invoices/"},
                {"name": "Payments", "url": "/api/accounting/payments/"},
                {"name": "Customer Invoices", "url": "/api/accounting/customer-invoices/"},
                {"name": "Receipts", "url": "/api/accounting/receipts/"},
                {"name": "Fixed Assets", "url": "/api/accounting/fixed-assets/"},
                {"name": "GL Balances", "url": "/api/accounting/gl-balances/"},
            ]
        },
        {
            "name": "budget",
            "title": "Budget",
            "description": "Budget allocation, BAC, variance analysis",
            "icon": "budget",
            "endpoints": [
                {"name": "Allocations", "url": "/api/budget/allocations/"},
                {"name": "Lines", "url": "/api/budget/lines/"},
                {"name": "Variances", "url": "/api/budget/variances/"},
            ]
        },
        {
            "name": "procurement",
            "title": "Procurement",
            "description": "Vendors, PR, PO, GRN, 3-Way Matching",
            "icon": "shopping_cart",
            "endpoints": [
                {"name": "Vendors", "url": "/api/procurement/vendors/"},
                {"name": "Purchase Requests", "url": "/api/procurement/requests/"},
                {"name": "Purchase Orders", "url": "/api/procurement/orders/"},
                {"name": "GRNs", "url": "/api/procurement/grns/"},
                {"name": "Invoice Matching", "url": "/api/procurement/invoice-matching/"},
            ]
        },
        {
            "name": "inventory",
            "title": "Inventory",
            "description": "Warehouses, items, batches, stock valuation",
            "icon": "inventory",
            "endpoints": [
                {"name": "Warehouses", "url": "/api/inventory/warehouses/"},
                {"name": "Categories", "url": "/api/inventory/categories/"},
                {"name": "Items", "url": "/api/inventory/items/"},
                {"name": "Stock", "url": "/api/inventory/stocks/"},
                {"name": "Batches", "url": "/api/inventory/batches/"},
                {"name": "Movements", "url": "/api/inventory/movements/"},
                {"name": "Reconciliations", "url": "/api/inventory/reconciliations/"},
                {"name": "Reorder Alerts", "url": "/api/inventory/reorder-alerts/"},
            ]
        },
        {
            "name": "sales",
            "title": "Sales",
            "description": "CRM, quotations, orders, invoicing",
            "icon": "point_of_sale",
            "endpoints": [
                {"name": "Customers", "url": "/api/sales/customers/"},
                {"name": "Leads", "url": "/api/sales/leads/"},
                {"name": "Opportunities", "url": "/api/sales/opportunities/"},
                {"name": "Quotations", "url": "/api/sales/quotations/"},
                {"name": "Orders", "url": "/api/sales/orders/"},
            ]
        },
        {
            "name": "service",
            "title": "Service",
            "description": "Helpdesk, tickets, maintenance, technicians",
            "icon": "build",
            "endpoints": [
                {"name": "Assets", "url": "/api/service/assets/"},
                {"name": "Technicians", "url": "/api/service/technicians/"},
                {"name": "Tickets", "url": "/api/service/tickets/"},
                {"name": "Schedules", "url": "/api/service/schedules/"},
            ]
        },
        {
            "name": "workflow",
            "title": "Workflow",
            "description": "Workflow definitions and instances",
            "icon": "account_tree",
            "endpoints": [
                {"name": "Definitions", "url": "/api/workflow/definitions/"},
                {"name": "Instances", "url": "/api/workflow/instances/"},
            ]
        },
    ]
    return Response({"modules": modules})
