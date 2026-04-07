"""
Integration Signals
===================
Listens to DTSG model save events and dispatches outbound webhooks.
Covers all major business events across modules.
"""
import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from .webhook_dispatcher import dispatch_event

logger = logging.getLogger('integrations.signals')


# ---------------------------------------------------------------------------
# Sales
# ---------------------------------------------------------------------------

def _safe_dispatch(event_type, module, payload_fn, instance):
    """Dispatch without crashing the calling transaction."""
    try:
        dispatch_event(event_type, module=module, payload=payload_fn(instance))
    except Exception as exc:
        logger.error('webhook dispatch error (%s): %s', event_type, exc)


try:
    from sales.models import SalesOrder

    @receiver(post_save, sender=SalesOrder)
    def on_sales_order_save(sender, instance, created, **kwargs):
        event = 'sales_order.created' if created else 'sales_order.updated'
        _safe_dispatch(event, 'sales', lambda o: {
            'id': o.pk,
            'reference': getattr(o, 'reference', ''),
            'status': getattr(o, 'status', ''),
            'customer': str(getattr(o, 'customer_id', '')),
        }, instance)

except ImportError as exc:
    logger.warning(
        "integrations: optional module unavailable, signal not registered "
        "(sales.SalesOrder): %s", exc,
    )

try:
    from sales.models import DeliveryNote

    @receiver(post_save, sender=DeliveryNote)
    def on_delivery_note_save(sender, instance, created, **kwargs):
        if getattr(instance, 'status', '') == 'posted':
            _safe_dispatch('delivery.posted', 'sales', lambda o: {
                'id': o.pk,
                'reference': getattr(o, 'reference', ''),
                'sales_order': str(getattr(o, 'sales_order_id', '')),
            }, instance)

except ImportError as exc:
    logger.warning(
        "integrations: optional module unavailable, signal not registered "
        "(sales.DeliveryNote): %s", exc,
    )


# ---------------------------------------------------------------------------
# Procurement
# ---------------------------------------------------------------------------

try:
    from procurement.models import PurchaseOrder

    @receiver(post_save, sender=PurchaseOrder)
    def on_purchase_order_save(sender, instance, created, **kwargs):
        event = 'purchase_order.created' if created else 'purchase_order.updated'
        if getattr(instance, 'status', '') == 'Approved':
            event = 'purchase_order.approved'
        _safe_dispatch(event, 'procurement', lambda o: {
            'id': o.pk,
            'po_number': getattr(o, 'po_number', ''),
            'vendor': str(getattr(o, 'vendor_id', '')),
            'status': getattr(o, 'status', ''),
        }, instance)

except ImportError as exc:
    logger.warning(
        "integrations: optional module unavailable, signal not registered "
        "(procurement.PurchaseOrder): %s", exc,
    )

try:
    from procurement.models import GoodsReceivedNote

    @receiver(post_save, sender=GoodsReceivedNote)
    def on_grn_save(sender, instance, created, **kwargs):
        if getattr(instance, 'status', '') == 'Posted':
            _safe_dispatch('grn.posted', 'procurement', lambda o: {
                'id': o.pk,
                'reference': getattr(o, 'grn_number', ''),
                'purchase_order': str(getattr(o, 'purchase_order_id', '')),
            }, instance)

except ImportError as exc:
    logger.warning(
        "integrations: optional module unavailable, signal not registered "
        "(procurement.GoodsReceivedNote): %s", exc,
    )


# ---------------------------------------------------------------------------
# Accounting
# ---------------------------------------------------------------------------

try:
    from accounting.models import JournalHeader

    @receiver(post_save, sender=JournalHeader)
    def on_journal_save(sender, instance, created, **kwargs):
        if getattr(instance, 'status', '') == 'Posted':
            _safe_dispatch('journal.posted', 'accounting', lambda o: {
                'id': o.pk,
                'reference': getattr(o, 'reference_number', ''),
                'date': str(getattr(o, 'posting_date', '')),
                'amount': str(getattr(o, 'total_debit', '')),
            }, instance)

except ImportError as exc:
    logger.warning(
        "integrations: optional module unavailable, signal not registered "
        "(accounting.JournalHeader): %s", exc,
    )

try:
    from accounting.models import Payment

    @receiver(post_save, sender=Payment)
    def on_payment_save(sender, instance, created, **kwargs):
        if getattr(instance, 'status', '') == 'Posted':
            _safe_dispatch('payment.posted', 'accounting', lambda o: {
                'id': o.pk,
                'reference': getattr(o, 'payment_number', ''),
                'amount': str(getattr(o, 'total_amount', '')),
            }, instance)

except ImportError as exc:
    logger.warning(
        "integrations: optional module unavailable, signal not registered "
        "(accounting.Payment): %s", exc,
    )


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------

try:
    from inventory.models import StockMovement

    @receiver(post_save, sender=StockMovement)
    def on_stock_movement_save(sender, instance, created, **kwargs):
        if created:
            _safe_dispatch('stock_movement.created', 'inventory', lambda o: {
                'id': o.pk,
                'item': str(getattr(o, 'item_id', '')),
                'quantity': str(getattr(o, 'quantity', '')),
                'movement_type': getattr(o, 'movement_type', ''),
            }, instance)

except ImportError as exc:
    logger.warning(
        "integrations: optional module unavailable, signal not registered "
        "(inventory.StockMovement): %s", exc,
    )


# ---------------------------------------------------------------------------
# HRM
# ---------------------------------------------------------------------------

try:
    from hrm.models import Employee

    @receiver(post_save, sender=Employee)
    def on_employee_save(sender, instance, created, **kwargs):
        event = 'employee.created' if created else 'employee.updated'
        _safe_dispatch(event, 'hrm', lambda o: {
            'id': o.pk,
            'employee_number': getattr(o, 'employee_number', ''),
            'full_name': f'{getattr(o, "first_name", "")} {getattr(o, "last_name", "")}'.strip(),
            'department': str(getattr(o, 'department_id', '')),
        }, instance)

except ImportError as exc:
    logger.warning(
        "integrations: optional module unavailable, signal not registered "
        "(hrm.Employee): %s", exc,
    )

try:
    from hrm.models import PayrollRun

    @receiver(post_save, sender=PayrollRun)
    def on_payroll_run_save(sender, instance, created, **kwargs):
        if getattr(instance, 'status', '') == 'paid':
            _safe_dispatch('payroll.posted', 'hrm', lambda o: {
                'id': o.pk,
                'period': str(getattr(o, 'period_id', '')),
                'total': str(getattr(o, 'total_net', '')),
            }, instance)

except ImportError as exc:
    logger.warning(
        "integrations: optional module unavailable, signal not registered "
        "(hrm.PayrollRun): %s", exc,
    )


# ---------------------------------------------------------------------------
# Production
# ---------------------------------------------------------------------------

try:
    from production.models import ProductionOrder

    @receiver(post_save, sender=ProductionOrder)
    def on_production_order_save(sender, instance, created, **kwargs):
        if created:
            _safe_dispatch('production_order.created', 'production', lambda o: {
                'id': o.pk,
                'reference': getattr(o, 'order_number', ''),
                'status': getattr(o, 'status', ''),
            }, instance)
        elif getattr(instance, 'status', '') == 'completed':
            _safe_dispatch('production_order.completed', 'production', lambda o: {
                'id': o.pk,
                'reference': getattr(o, 'order_number', ''),
            }, instance)

except ImportError as exc:
    logger.warning(
        "integrations: optional module unavailable, signal not registered "
        "(production.ProductionOrder): %s", exc,
    )
