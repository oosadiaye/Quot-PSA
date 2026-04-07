import logging
import time

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.utils import timezone
from django.db import connection

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
        "name": "DTSG ERP API",
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
    """Returns cross-module KPI counts for the tenant dashboard."""
    from django.apps import apps

    stats = {}

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
        from django.db.models import F
        stats['low_stock_alerts'] = ItemStock.objects.filter(
            item__is_active=True,
            item__reorder_point__isnull=False,
            quantity__lte=F('item__reorder_point'),
        ).values('item').distinct().count()
    except (LookupError, Exception):
        stats['low_stock_alerts'] = 0

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
