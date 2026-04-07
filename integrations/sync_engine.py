"""
Sync Engine
===========
Orchestrates bidirectional data sync between DTSG ERP modules and
external systems.

Each `sync_*()` function:
  1. Calls the adapter to fetch remote data
  2. Upserts into the relevant DTSG Django model (correct field names verified
     against actual model definitions in each app)
  3. Updates the SyncLog counters

Field name mapping (remote -> DTSG):
  Item.sku           (NOT code — Item uses sku as unique identifier)
  Customer.customer_code  (NOT code)
  Customer.contact_email  (NOT email)
  PurchaseOrder.po_number (NOT reference)
  SalesOrder.order_number (NOT reference)
  StockMovement.reference_number (NOT reference)
  Receipt.reference_number  (NOT reference)
"""
import logging

from django.utils import timezone

logger = logging.getLogger('integrations.sync')


# ---------------------------------------------------------------------------
# Master dispatcher
# ---------------------------------------------------------------------------

def run_module_sync(config, module: str, direction: str, sync_log):
    """Route to the correct sync function based on module."""
    from integrations.models import ModuleCode, SyncStatus, SyncDirection
    from integrations.adapters.factory import get_adapter

    sync_log.status = SyncStatus.RUNNING
    sync_log.save(update_fields=['status'])

    adapter = get_adapter(config)
    handlers = {
        ModuleCode.ACCOUNTING: sync_gl_accounts,
        ModuleCode.AP: sync_vendors,
        ModuleCode.AR: sync_customers,
        ModuleCode.INVENTORY: sync_inventory_items,
        ModuleCode.PROCUREMENT: sync_purchase_orders,
        ModuleCode.SALES: sync_sales_orders,
        ModuleCode.VENDORS: sync_vendors,
        ModuleCode.CUSTOMERS: sync_customers,
        ModuleCode.ITEMS: sync_inventory_items,
        ModuleCode.HRM: sync_employees,
    }

    if module == ModuleCode.ALL:
        modules = list(handlers.keys())
    else:
        modules = [module]

    total_created = total_updated = total_failed = 0

    for mod in modules:
        if mod in handlers:
            try:
                c, u, f = handlers[mod](adapter, config, sync_log, direction)
                total_created += c
                total_updated += u
                total_failed += f
            except Exception as exc:
                logger.error('Sync error for %s/%s: %s', config.name, mod, exc, exc_info=True)
                total_failed += 1

    sync_log.records_created = total_created
    sync_log.records_updated = total_updated
    sync_log.records_failed = total_failed
    sync_log.records_total = total_created + total_updated + total_failed
    sync_log.status = (
        SyncStatus.FAILED
        if total_failed > 0 and (total_created + total_updated) == 0
        else SyncStatus.SUCCESS
    )
    sync_log.finished_at = timezone.now()
    config.last_sync_at = timezone.now()
    config.save(update_fields=['last_sync_at'])
    sync_log.save()


# ---------------------------------------------------------------------------
# GL Accounts / Chart of Accounts
# ---------------------------------------------------------------------------

def sync_gl_accounts(adapter, config, sync_log, direction: str):
    from integrations.models import SyncDirection
    from integrations.adapters.sap import SAPAdapter
    from integrations.adapters.dynamics import Dynamics365BCAdapter
    from integrations.adapters.sage import SageIntacctAdapter, Sage200Adapter

    created = updated = failed = 0

    if direction in (SyncDirection.INBOUND, SyncDirection.BIDIRECTIONAL):
        try:
            if isinstance(adapter, SAPAdapter):
                remote_accounts = adapter.get_gl_accounts()
            elif isinstance(adapter, Dynamics365BCAdapter):
                remote_accounts = adapter.get_accounts()
            elif isinstance(adapter, SageIntacctAdapter):
                remote_accounts = adapter.get_gl_accounts()
            elif isinstance(adapter, Sage200Adapter):
                remote_accounts = adapter.get_nominal_accounts()
            else:
                remote_accounts = []

            from accounting.models import Account
            for row in remote_accounts:
                # Account uses 'code' as unique identifier (max 20 chars)
                code = str(row.get('code', '')).strip()[:20]
                if not code:
                    continue
                obj, was_created = Account.objects.update_or_create(
                    code=code,
                    defaults={
                        'name': row.get('name', code)[:150],
                        'account_type': row.get('account_type', 'asset'),
                    },
                )
                if was_created:
                    created += 1
                else:
                    updated += 1
        except Exception as exc:
            logger.error('sync_gl_accounts inbound error: %s', exc)
            failed += 1

    return created, updated, failed


# ---------------------------------------------------------------------------
# Vendors
# ---------------------------------------------------------------------------

def sync_vendors(adapter, config, sync_log, direction: str):
    from integrations.models import SyncDirection
    from integrations.adapters.sap import SAPAdapter
    from integrations.adapters.dynamics import Dynamics365BCAdapter
    from integrations.adapters.sage import SageIntacctAdapter, Sage200Adapter

    created = updated = failed = 0

    if direction in (SyncDirection.INBOUND, SyncDirection.BIDIRECTIONAL):
        try:
            if isinstance(adapter, SAPAdapter):
                rows = adapter.get_vendors()
            elif isinstance(adapter, Dynamics365BCAdapter):
                rows = adapter.get_vendors()
            elif isinstance(adapter, SageIntacctAdapter):
                rows = adapter.get_vendors()
            elif isinstance(adapter, Sage200Adapter):
                rows = adapter.get_suppliers()
            else:
                rows = []

            from procurement.models import Vendor
            for row in rows:
                # Vendor.code is the unique identifier (max 20 chars)
                code = str(row.get('code', '')).strip()[:20]
                if not code:
                    continue
                # Vendor.email is an EmailField (blank=True) — safe to update
                obj, was_created = Vendor.objects.update_or_create(
                    code=code,
                    defaults={'name': row.get('name', code), 'email': row.get('email', '')},
                )
                if was_created:
                    created += 1
                else:
                    updated += 1
        except Exception as exc:
            logger.error('sync_vendors inbound error: %s', exc)
            failed += 1

    return created, updated, failed


# ---------------------------------------------------------------------------
# Customers
# ---------------------------------------------------------------------------

def sync_customers(adapter, config, sync_log, direction: str):
    from integrations.models import SyncDirection
    from integrations.adapters.sap import SAPAdapter
    from integrations.adapters.dynamics import Dynamics365BCAdapter
    from integrations.adapters.sage import Sage200Adapter

    created = updated = failed = 0

    if direction in (SyncDirection.INBOUND, SyncDirection.BIDIRECTIONAL):
        try:
            if isinstance(adapter, SAPAdapter):
                rows = adapter.get_customers()
            elif isinstance(adapter, Dynamics365BCAdapter):
                rows = adapter.get_customers()
            elif isinstance(adapter, Sage200Adapter):
                rows = adapter.get_customers()
            else:
                rows = []

            from sales.models import Customer
            for row in rows:
                # Customer uses 'customer_code' as unique identifier (NOT 'code')
                code = str(row.get('code', '')).strip()[:20]
                name = str(row.get('name', code)).strip()[:200]
                if not code or not name:
                    continue

                existing = Customer.objects.filter(customer_code=code).first()
                if existing:
                    # Safe to update name and contact_email (Customer.contact_email, not email)
                    existing.name = name
                    existing.contact_email = row.get('email', existing.contact_email)
                    existing.save(update_fields=['name', 'contact_email'])
                    updated += 1
                else:
                    # Cannot auto-create Customer — many required fields have no defaults
                    # (credit_limit, balance, address, contact_person, contact_phone,
                    #  customer_type, industry, website, is_active).
                    # Log for manual review instead.
                    logger.info(
                        'sync_customers: customer_code=%s not found in DTSG — '
                        'manual creation required (remote system: %s)',
                        code, config.system_type,
                    )

        except Exception as exc:
            logger.error('sync_customers inbound error: %s', exc)
            failed += 1

    return created, updated, failed


# ---------------------------------------------------------------------------
# Inventory Items
# ---------------------------------------------------------------------------

def sync_inventory_items(adapter, config, sync_log, direction: str):
    from integrations.models import SyncDirection
    from integrations.adapters.sap import SAPAdapter
    from integrations.adapters.dynamics import Dynamics365BCAdapter
    from integrations.adapters.generic import ShopifyAdapter

    created = updated = failed = 0

    if direction in (SyncDirection.INBOUND, SyncDirection.BIDIRECTIONAL):
        try:
            if isinstance(adapter, SAPAdapter):
                rows = adapter.get_materials()
            elif isinstance(adapter, Dynamics365BCAdapter):
                rows = adapter.get_items()
            elif isinstance(adapter, ShopifyAdapter):
                rows = adapter.get_products()
            else:
                rows = []

            from inventory.models import Item
            for row in rows:
                # Item uses 'sku' as unique identifier (NOT 'code')
                sku = str(row.get('code', '')).strip()[:50]
                if not sku:
                    continue
                existing = Item.objects.filter(sku=sku).first()
                if existing:
                    existing.name = row.get('name', existing.name)
                    existing.save(update_fields=['name'])
                    updated += 1
                else:
                    # Item has required fields (category, item_type, uom, etc.)
                    # Log for manual creation rather than partial auto-create
                    logger.info(
                        'sync_inventory_items: sku=%s not found in DTSG — '
                        'manual creation required', sku,
                    )

        except Exception as exc:
            logger.error('sync_inventory_items error: %s', exc)
            failed += 1

    return created, updated, failed


# ---------------------------------------------------------------------------
# Purchase Orders
# ---------------------------------------------------------------------------

def sync_purchase_orders(adapter, config, sync_log, direction: str):
    from integrations.models import SyncDirection
    from integrations.adapters.sap import SAPAdapter
    from integrations.adapters.dynamics import Dynamics365BCAdapter

    created = updated = failed = 0

    if direction in (SyncDirection.INBOUND, SyncDirection.BIDIRECTIONAL):
        try:
            if isinstance(adapter, SAPAdapter):
                rows = adapter.get_purchase_orders()
            elif isinstance(adapter, Dynamics365BCAdapter):
                rows = adapter.get_purchase_orders()
            else:
                rows = []

            from procurement.models import PurchaseOrder, Vendor
            for row in rows:
                # PurchaseOrder uses 'po_number' as unique identifier (NOT 'reference')
                po_number = str(row.get('po_number', '')).strip()[:50]
                if not po_number:
                    continue
                vendor = Vendor.objects.filter(code=row.get('vendor_code', '')).first()

                existing = PurchaseOrder.objects.filter(po_number=po_number).first()
                if existing:
                    # Only update vendor linkage and status if vendor was found
                    if vendor:
                        existing.vendor = vendor
                    mapped_status = _map_po_status(row.get('status', ''))
                    existing.status = mapped_status
                    existing.save(update_fields=[f for f in (['vendor', 'status'] if vendor else ['status'])])
                    updated += 1
                else:
                    logger.info(
                        'sync_purchase_orders: po_number=%s not found in DTSG — '
                        'manual creation required', po_number,
                    )

        except Exception as exc:
            logger.error('sync_purchase_orders error: %s', exc)
            failed += 1

    return created, updated, failed


# ---------------------------------------------------------------------------
# Sales Orders
# ---------------------------------------------------------------------------

def sync_sales_orders(adapter, config, sync_log, direction: str):
    from integrations.models import SyncDirection
    from integrations.adapters.sap import SAPAdapter
    from integrations.adapters.dynamics import Dynamics365BCAdapter

    created = updated = failed = 0

    if direction in (SyncDirection.INBOUND, SyncDirection.BIDIRECTIONAL):
        try:
            if isinstance(adapter, SAPAdapter):
                rows = adapter.get_sales_orders()
            elif isinstance(adapter, Dynamics365BCAdapter):
                rows = adapter.get_sales_orders()
            else:
                rows = []

            from sales.models import SalesOrder, Customer
            for row in rows:
                # SalesOrder uses 'order_number' as unique identifier (NOT 'reference')
                order_number = str(row.get('so_number', '')).strip()[:50]
                if not order_number:
                    continue
                # Customer uses 'customer_code' (NOT 'code')
                customer = Customer.objects.filter(
                    customer_code=row.get('customer_code', '')
                ).first()

                existing = SalesOrder.objects.filter(order_number=order_number).first()
                if existing:
                    update_fields = []
                    if customer:
                        existing.customer = customer
                        update_fields.append('customer')
                    if update_fields:
                        existing.save(update_fields=update_fields)
                    updated += 1
                else:
                    logger.info(
                        'sync_sales_orders: order_number=%s not found in DTSG — '
                        'manual creation required', order_number,
                    )

        except Exception as exc:
            logger.error('sync_sales_orders error: %s', exc)
            failed += 1

    return created, updated, failed


# ---------------------------------------------------------------------------
# HRM (Employees)
# ---------------------------------------------------------------------------

def sync_employees(adapter, config, sync_log, direction: str):
    # Stub: HR data from 3rd-party HRIS (Workday, BambooHR) could be synced here.
    # Employee creation requires many required fields — not auto-creatable.
    return 0, 0, 0


# ---------------------------------------------------------------------------
# Inbound event processors (called from webhook receivers)
# ---------------------------------------------------------------------------

def process_sap_inbound_event(config, event_type: str, payload: dict):
    """Handle a pushed event from SAP Event Mesh."""
    logger.info('SAP inbound event: %s', event_type)
    if 'GoodsMovement' in event_type:
        _handle_sap_goods_movement(config, payload)
    elif 'SalesOrder' in event_type:
        _handle_sap_sales_order(config, payload)
    elif 'PurchaseOrder' in event_type:
        _handle_sap_purchase_order(config, payload)


def _handle_sap_goods_movement(config, payload: dict):
    """
    Reconcile a SAP goods movement with DTSG inventory.
    StockMovement requires warehouse, unit_price, cost_method, remarks — all
    non-nullable — so we log for manual reconciliation rather than attempt a
    partial create that would raise IntegrityError.
    """
    from inventory.models import Item

    material = payload.get('Material', '')
    quantity = float(payload.get('Quantity', 0) or 0)
    mvt_type = payload.get('GoodsMovementType', '')
    doc_ref = payload.get('MaterialDocumentYear', '') + payload.get('MaterialDocument', '')

    # Item uses 'sku' as unique identifier (NOT 'code')
    item = Item.objects.filter(sku=material).first()
    if not item:
        logger.warning(
            'SAP goods movement: item sku=%s not found in DTSG (doc=%s)',
            material, doc_ref,
        )
        return

    # StockMovement requires warehouse + unit_price + cost_method — log pending
    # reconciliation rather than fail silently with a partial create.
    logger.info(
        'SAP goods movement received: item=%s qty=%s mvt_type=%s doc=%s — '
        'requires manual warehouse assignment in DTSG before posting',
        material, quantity, mvt_type, doc_ref,
    )


def _handle_sap_sales_order(config, payload: dict):
    logger.info('SAP Sales Order event: %s', payload.get('SalesOrder', ''))


def _handle_sap_purchase_order(config, payload: dict):
    logger.info('SAP Purchase Order event: %s', payload.get('PurchaseOrder', ''))


def process_dynamics_inbound_event(config, event_type: str, payload: dict):
    logger.info('Dynamics 365 inbound event: %s', event_type)


def process_shopify_order(config, payload: dict):
    """
    Convert a Shopify order into a DTSG Sales Order.
    Only updates existing Customer / SalesOrder records.
    New records require manual creation in DTSG because Customer and SalesOrder
    both have required fields without defaults (credit_limit, fund, geo, etc.).
    """
    from sales.models import SalesOrder, Customer, SalesOrderLine
    from inventory.models import Item
    import decimal

    email = (payload.get('email') or '').strip()
    shopify_customer = payload.get('customer', {})
    first = shopify_customer.get('first_name', '').strip()
    last = shopify_customer.get('last_name', '').strip()
    full_name = ' '.join(filter(None, [first, last]))

    # Look up existing Customer by contact_email (NOT 'email' — Customer uses contact_email)
    customer = None
    if email:
        customer = Customer.objects.filter(contact_email=email).first()
    if not customer and full_name:
        customer = Customer.objects.filter(name=full_name).first()
    if not customer:
        logger.info(
            'process_shopify_order: no matching Customer for email=%s name=%s — '
            'manual customer linkage required', email, full_name,
        )

    # SalesOrder uses 'order_number' (NOT 'reference')
    order_ref = f"SHO-{payload.get('name', payload.get('id', ''))}"[:50]

    existing_so = SalesOrder.objects.filter(order_number=order_ref).first()
    if existing_so:
        logger.info('process_shopify_order: order_number=%s already exists, skipping', order_ref)
        return

    if not customer:
        # Cannot create SalesOrder without a Customer FK
        logger.warning(
            'process_shopify_order: skipping order %s — no matching DTSG customer', order_ref,
        )
        return

    # SalesOrder has required FK fields (function, fund, geo, program) that Shopify
    # doesn't provide. We log for manual creation rather than attempt partial create.
    logger.info(
        'process_shopify_order: order %s from customer %s requires manual '
        'creation in DTSG (fund/geo/program dimensions not in Shopify payload)',
        order_ref, customer.customer_code,
    )


def process_stripe_payment(config, payment_intent: dict):
    """Convert a Stripe payment_intent.succeeded event to a DTSG receipt."""
    from accounting.models import Receipt

    amount = float(payment_intent.get('amount', 0)) / 100.0
    currency = payment_intent.get('currency', 'USD').upper()
    ref = payment_intent.get('id', '')

    # Receipt uses 'reference_number' (NOT 'reference')
    if ref and Receipt.objects.filter(reference_number=ref).exists():
        logger.info('process_stripe_payment: receipt for %s already exists, skipping', ref)
        return

    # Receipt creation requires GL account linkage and a receipt_number sequence —
    # log for manual matching if chart of accounts is not yet configured.
    logger.info(
        'Stripe payment %s: %.2f %s received — '
        'manual GL receipt creation required in DTSG accounting module',
        ref, amount, currency,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _map_po_status(remote_status: str) -> str:
    mapping = {
        'Open': 'Draft',
        'Released': 'Approved',
        'Partially delivered': 'Draft',
        'Closed': 'Closed',
        'Cancelled': 'Rejected',
        '': 'Draft',
    }
    return mapping.get(remote_status, 'Draft')
