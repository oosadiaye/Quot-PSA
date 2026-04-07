import logging

from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.views import APIView

from django_filters.rest_framework import DjangoFilterBackend
from decimal import Decimal
from django.db.models import Sum, F, Q, Value, DecimalField, Case, When
from django.db.models.functions import Coalesce
from django.db import transaction
from .models import (
    Warehouse, ProductType, ProductCategory, ItemCategory, Item, ItemStock, ItemBatch,
    StockMovement, StockReconciliation, StockReconciliationLine, ReorderAlert,
    ItemSerialNumber, BatchExpiryAlert, InventorySettings
)
from .serializers import (
    WarehouseSerializer, ProductTypeSerializer, ProductCategorySerializer,
    ItemCategorySerializer, ItemSerializer,
    ItemStockSerializer, ItemBatchSerializer, StockMovementSerializer,
    StockReconciliationSerializer, StockReconciliationLineSerializer,
    ReorderAlertSerializer,
    ItemSerialNumberSerializer, BatchExpiryAlertSerializer,
    InventorySettingsSerializer,
)
from accounting.transaction_posting import TransactionPostingService

logger = logging.getLogger('dtsg')


class InventoryPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 500   # raised from 100 — allows product-picker forms to fetch the full catalog in one request


class WarehouseViewSet(viewsets.ModelViewSet):
    queryset = Warehouse.objects.all()
    serializer_class = WarehouseSerializer
    pagination_class = InventoryPagination


class ProductTypeViewSet(viewsets.ModelViewSet):
    queryset = ProductType.objects.all().select_related(
        'inventory_account', 'expense_account', 'revenue_account',
        'clearing_account', 'goods_in_transit_account',   # was missing → N+1 queries
    )
    serializer_class = ProductTypeSerializer
    pagination_class = InventoryPagination
    search_fields = ['name', 'description']


class ProductCategoryViewSet(viewsets.ModelViewSet):
    queryset = ProductCategory.objects.all().select_related('product_type', 'parent')
    serializer_class = ProductCategorySerializer
    pagination_class = InventoryPagination
    search_fields = ['name']
    filterset_fields = ['product_type', 'parent']

    def get_queryset(self):
        queryset = super().get_queryset()
        product_type_id = self.request.query_params.get('product_type')
        if product_type_id:
            queryset = queryset.filter(product_type_id=product_type_id)
        return queryset


class ItemCategoryViewSet(viewsets.ModelViewSet):
    queryset = ItemCategory.objects.all()
    serializer_class = ItemCategorySerializer
    pagination_class = InventoryPagination


class ItemViewSet(viewsets.ModelViewSet):
    queryset = Item.objects.all().select_related(
        'product_type', 'product_category', 'category',
        'inventory_account', 'expense_account'
    ).prefetch_related('itemstock_set', 'itembatch_set')
    serializer_class = ItemSerializer
    search_fields = ['name', 'sku', 'barcode']
    filterset_fields = ['product_type', 'product_category', 'category', 'is_active', 'valuation_method']
    pagination_class = InventoryPagination

    def get_queryset(self):
        queryset = super().get_queryset()
        if not self.request.query_params.get('include_inactive'):
            queryset = queryset.filter(is_active=True)

        product_type = self.request.query_params.get('product_type')
        if product_type:
            queryset = queryset.filter(product_type_id=product_type)

        return queryset

    @action(detail=True, methods=['get'])
    def stock_by_warehouse(self, request, pk=None):
        item = self.get_object()
        stocks = ItemStock.objects.filter(item=item).select_related('warehouse')
        serializer = ItemStockSerializer(stocks, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def batches(self, request, pk=None):
        item = self.get_object()
        batches = ItemBatch.objects.filter(item=item).select_related('warehouse')
        serializer = ItemBatchSerializer(batches, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def stock_valuation(self, request):
        """Get stock valuation report using DB aggregation"""
        warehouse_id     = request.query_params.get('warehouse')
        product_type_id  = request.query_params.get('product_type')
        category_id      = request.query_params.get('category')

        # Base queryset with DB-level stock aggregation
        stock_filter = Q(itemstock__quantity__gt=0)
        if warehouse_id:
            stock_filter &= Q(itemstock__warehouse_id=warehouse_id)

        items = Item.objects.filter(
            is_active=True
        ).select_related(
            'product_type', 'product_category'
        ).annotate(
            total_stock_qty=Coalesce(
                Sum('itemstock__quantity', filter=stock_filter),
                Value(0), output_field=DecimalField()
            ),
            avg_cost=Case(
                When(total_quantity__gt=0, then=F('total_value') / F('total_quantity')),
                default=Decimal('0'),
                output_field=DecimalField(max_digits=15, decimal_places=4)
            )
        ).filter(total_stock_qty__gt=0)

        if product_type_id:
            items = items.filter(product_type_id=product_type_id)
        if category_id:
            items = items.filter(product_category_id=category_id)

        valuation = []
        total_inventory_value = 0

        for item in items:
            total_qty = item.total_stock_qty
            avg_cost  = item.avg_cost
            total_value = float(total_qty * avg_cost)
            total_inventory_value += total_value

            valuation.append({
                'id':                 item.id,
                'sku':                item.sku,
                'name':               item.name,
                'unit_of_measure':    item.unit_of_measure,
                # IDs for client-side filtering
                'product_type_id':    item.product_type_id,
                'category_id':        item.product_category_id,
                # Display names
                'product_type_name':  item.product_type.name if item.product_type else None,
                'category_name':      item.product_category.name if item.product_category else None,
                'valuation_method':   item.valuation_method,
                'total_quantity':     float(total_qty),
                'average_cost':       float(avg_cost),
                'total_value':        total_value,
                'reorder_point':      float(item.reorder_point),
                'needs_reorder':      item.needs_reorder,
            })

        return Response({
            'items': valuation,
            'summary': {
                'total_items':            len(valuation),
                'total_inventory_value':  total_inventory_value,
            }
        })

    @action(detail=False, methods=['get'])
    def stock_valuation_by_warehouse(self, request):
        """Get stock valuation grouped by warehouse using DB aggregation"""
        warehouse_id = request.query_params.get('warehouse')

        if not warehouse_id:
            return Response({"error": "warehouse parameter required"}, status=status.HTTP_400_BAD_REQUEST)

        items = Item.objects.filter(
            is_active=True
        ).annotate(
            wh_qty=Coalesce(
                Sum('itemstock__quantity', filter=Q(itemstock__warehouse_id=warehouse_id)),
                Value(0), output_field=DecimalField()
            ),
            avg_cost=Case(
                When(total_quantity__gt=0, then=F('total_value') / F('total_quantity')),
                default=Decimal('0'),
                output_field=DecimalField(max_digits=15, decimal_places=4)
            )
        ).filter(wh_qty__gt=0)

        report = []
        total_value = 0

        for item in items:
            qty = float(item.wh_qty)
            avg_cost = float(item.avg_cost)
            value = qty * avg_cost
            total_value += value

            report.append({
                'sku': item.sku,
                'name': item.name,
                'quantity': qty,
                'average_cost': avg_cost,
                'value': value
            })

        return Response({
            'warehouse_id': warehouse_id,
            'items': report,
            'total_value': total_value
        })

    @action(detail=False, methods=['get'])
    def reorder_alerts(self, request):
        """Get items that need reordering using DB query"""
        low_stock = ItemStock.objects.filter(
            item__is_active=True,
            item__reorder_point__gt=0,
            quantity__lte=F('item__reorder_point')
        ).select_related('item', 'warehouse')

        alerts = [{
            'item_id': stock.item.id,
            'sku': stock.item.sku,
            'name': stock.item.name,
            'warehouse': stock.warehouse.name,
            'current_stock': float(stock.quantity),
            'reorder_point': float(stock.item.reorder_point),
            'suggested_quantity': float(stock.item.reorder_quantity or stock.item.reorder_point * 2),
            'shortage': float(stock.item.reorder_point - stock.quantity)
        } for stock in low_stock]

        return Response(alerts)


class ItemStockViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ItemStock.objects.all().select_related('item', 'warehouse')
    serializer_class = ItemStockSerializer
    filterset_fields = ['item', 'warehouse']
    pagination_class = InventoryPagination

    def get_queryset(self):
        return ItemStock.objects.select_related('item', 'warehouse').annotate(
            qty_received=Coalesce(
                Sum(
                    'item__stockmovement__quantity',
                    filter=Q(
                        item__stockmovement__movement_type='IN',
                        item__stockmovement__warehouse_id=F('warehouse_id'),
                    ),
                    output_field=DecimalField(),
                ),
                Value(0),
                output_field=DecimalField(),
            ),
            qty_sold=Coalesce(
                Sum(
                    'item__stockmovement__quantity',
                    filter=Q(
                        item__stockmovement__movement_type='OUT',
                        item__stockmovement__warehouse_id=F('warehouse_id'),
                    ),
                    output_field=DecimalField(),
                ),
                Value(0),
                output_field=DecimalField(),
            ),
        )


class ItemBatchViewSet(viewsets.ModelViewSet):
    queryset = ItemBatch.objects.all().select_related('item', 'warehouse')
    serializer_class = ItemBatchSerializer
    filterset_fields = ['item', 'warehouse']
    pagination_class = InventoryPagination

    @action(detail=True, methods=['post'])
    def split(self, request, pk=None):
        """Split a batch into two batches."""
        from .serializers import BatchSplitSerializer
        serializer = BatchSplitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        batch = self.get_object()
        split_qty = serializer.validated_data['split_quantity']

        if split_qty <= 0 or split_qty >= batch.remaining_quantity:
            return Response(
                {"error": "Split quantity must be greater than 0 and less than remaining quantity"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Generate batch number if not provided
        new_number = serializer.validated_data.get('new_batch_number')
        if not new_number:
            existing_splits = ItemBatch.objects.filter(
                batch_number__startswith=f"{batch.batch_number}-S"
            ).count()
            new_number = f"{batch.batch_number}-S{existing_splits + 1}"

        with transaction.atomic():
            new_batch = ItemBatch.objects.create(
                item=batch.item,
                warehouse=batch.warehouse,
                batch_number=new_number,
                receipt_date=batch.receipt_date,
                expiry_date=batch.expiry_date,
                quantity=split_qty,
                remaining_quantity=split_qty,
                unit_cost=batch.unit_cost,
                reference_number=f"Split from {batch.batch_number}",
            )
            batch.remaining_quantity -= split_qty
            batch.save(update_fields=['remaining_quantity'])

        return Response(ItemBatchSerializer(new_batch).data, status=201)

    @action(detail=True, methods=['post'])
    def transfer(self, request, pk=None):
        """Transfer batch (or partial) to another warehouse."""
        from .serializers import BatchTransferSerializer
        serializer = BatchTransferSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        batch = self.get_object()
        to_warehouse_id = serializer.validated_data['to_warehouse']
        transfer_qty = serializer.validated_data['transfer_quantity']

        if to_warehouse_id == batch.warehouse_id:
            return Response({"error": "Cannot transfer to the same warehouse"}, status=status.HTTP_400_BAD_REQUEST)

        if transfer_qty <= 0 or transfer_qty > batch.remaining_quantity:
            return Response(
                {"error": "Transfer quantity must be > 0 and <= remaining quantity"},
                status=status.HTTP_400_BAD_REQUEST
            )

        from .models import Warehouse, StockMovement

        try:
            to_warehouse = Warehouse.objects.get(pk=to_warehouse_id)
        except Warehouse.DoesNotExist:
            return Response({"error": "Target warehouse not found"}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            source_warehouse = batch.warehouse  # capture before potential reassignment
            # Create transfer stock movement.
            # FIX #9: GL journals posted below (DR GIT / CR Inventory, DR Inventory / CR GIT).
            # DOUBLE-UPDATE FIX: use instance pattern + _skip_stock_update so the
            # post_save signal does NOT also update ItemStock — the explicit F() updates
            # at the end of this block are the single authoritative writes.
            movement = StockMovement(
                item=batch.item,
                warehouse=source_warehouse,
                to_warehouse=to_warehouse,
                movement_type='TRF',
                quantity=transfer_qty,
                unit_price=batch.unit_cost,
                batch=batch,
                cost_method='AVG',
                transfer_status='In Transit',
                reference_number=f"BATCH-TRF-{batch.batch_number}",
                remarks=f"Batch transfer to {to_warehouse.name}",
            )
            movement._skip_stock_update = True   # explicit ItemStock updates below
            movement.save()

            # GL posting: one-step batch transfer — post both dispatch and receive
            # legs so the Goods in Transit clearing account nets to zero.
            try:
                dispatch_journal = TransactionPostingService.post_transfer_dispatch(movement)
                movement.gl_posted = True
                movement.journal_entry = dispatch_journal
                movement.transfer_status = 'Received'
                receive_journal = TransactionPostingService.post_transfer_receive(movement)
                movement.receive_journal_entry = receive_journal
                movement.save(update_fields=[
                    'gl_posted', 'journal_entry', 'transfer_status', 'receive_journal_entry'
                ])
            except Exception as _gl_err:
                logger.error(
                    f"GL posting failed for batch transfer movement {movement.id}: {_gl_err}"
                )

            if transfer_qty == batch.remaining_quantity:
                # Full transfer — move the batch
                batch.warehouse = to_warehouse
                batch.save(update_fields=['warehouse'])
                result_batch = batch
            else:
                # Partial transfer — create new batch at target
                existing_transfers = ItemBatch.objects.filter(
                    batch_number__startswith=f"{batch.batch_number}-T"
                ).count()
                new_number = f"{batch.batch_number}-T{existing_transfers + 1}"

                result_batch = ItemBatch.objects.create(
                    item=batch.item,
                    warehouse=to_warehouse,
                    batch_number=new_number,
                    receipt_date=batch.receipt_date,
                    expiry_date=batch.expiry_date,
                    quantity=transfer_qty,
                    remaining_quantity=transfer_qty,
                    unit_cost=batch.unit_cost,
                    reference_number=f"Transfer from {batch.batch_number}",
                )
                batch.remaining_quantity -= transfer_qty
                batch.save(update_fields=['remaining_quantity'])

            # Update ItemStock for both warehouses atomically (single authoritative write)
            ItemStock.objects.filter(item=batch.item, warehouse=source_warehouse).update(
                quantity=F('quantity') - transfer_qty
            )
            ItemStock.objects.update_or_create(
                item=batch.item, warehouse=to_warehouse,
                defaults={'quantity': Decimal('0')},
            )
            ItemStock.objects.filter(item=batch.item, warehouse=to_warehouse).update(
                quantity=F('quantity') + transfer_qty
            )

            # Recalculate item-level totals (signal skipped this since _skip_stock_update=True)
            batch.item.recalculate_stock_values()

        return Response(ItemBatchSerializer(result_batch).data)


# ─── Inventory Settings ───────────────────────────────────────────────────────

class InventorySettingsView(APIView):
    """Singleton GET / PATCH endpoint for per-tenant inventory configuration."""

    def get(self, request):
        settings = InventorySettings.load()
        return Response(InventorySettingsSerializer(settings).data)

    def patch(self, request):
        settings = InventorySettings.load()
        serializer = InventorySettingsSerializer(settings, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


# ─── Auto-PO helper ───────────────────────────────────────────────────────────

def _maybe_create_auto_po(movement_id):
    """
    Called via transaction.on_commit after a stock movement is committed.

    Checks:
      1. InventorySettings.auto_po_enabled is True
      2. The movement is an outbound type (OUT / ADJ / TRF)
      3. Total stock after the movement is at or below the reorder point
      4. The item has a preferred_vendor with an active status
      5. The item has an expense_account (required for PO line)
      6. No open auto-PO already exists for this item

    If all conditions pass a Draft PO is created and a ReorderAlert is raised.
    """
    try:
        movement = StockMovement.objects.select_related(
            'item__preferred_vendor', 'item__expense_account', 'warehouse'
        ).get(pk=movement_id)
    except StockMovement.DoesNotExist:
        return

    if movement.movement_type not in ('OUT', 'ADJ', 'TRF'):
        return

    inv_settings = InventorySettings.load()
    if not inv_settings.auto_po_enabled:
        return

    item = movement.item

    # Re-read total stock across all warehouses after the movement
    total_qty = ItemStock.objects.filter(item=item).aggregate(
        total=Sum('quantity')
    )['total'] or Decimal('0')

    if total_qty > item.reorder_point:
        return  # Still above reorder point — no action needed

    # Guard: item must have preferred vendor + expense account
    if not item.preferred_vendor_id:
        logger.info(f"Auto-PO skipped for {item.sku}: no preferred_vendor set.")
        return
    if not item.expense_account_id:
        logger.info(f"Auto-PO skipped for {item.sku}: no expense_account set.")
        return
    if not item.preferred_vendor.is_active:
        logger.info(f"Auto-PO skipped for {item.sku}: preferred_vendor is inactive.")
        return

    try:
        from procurement.models import PurchaseOrder, PurchaseOrderLine

        # FIX #38: Idempotency guard — check BOTH the notes marker AND the po_number
        # prefix so that manually editing the notes field cannot re-trigger auto-PO.
        already_open = PurchaseOrderLine.objects.filter(
            item=item,
            po__status__in=('Draft', 'Pending', 'Approved'),
        ).filter(
            Q(po__notes__startswith='[AUTO-PO]') | Q(po__po_number__startswith='APO-')
        ).exists()
        if already_open:
            logger.info(f"Auto-PO skipped for {item.sku}: open auto-PO already exists.")
            return

        reorder_qty = item.reorder_quantity if item.reorder_quantity > 0 else max(item.reorder_point * 2, Decimal('1'))

        from django.utils import timezone
        from django.utils.crypto import get_random_string

        po_number = f"APO-{timezone.now().strftime('%Y%m%d')}-{get_random_string(6, '0123456789')}"

        with transaction.atomic():
            po = PurchaseOrder.objects.create(
                po_number=po_number,
                vendor_id=item.preferred_vendor_id,
                order_date=timezone.now().date(),
                payment_terms='Net_30',
                status='Draft',
                notes=(
                    f'[AUTO-PO] Auto-generated reorder alert.\n'
                    f'Item: {item.sku} — {item.name}\n'
                    f'Current stock: {float(total_qty)} (reorder point: {float(item.reorder_point)})\n'
                    f'Warehouse: {movement.warehouse.name}'
                ),
            )
            PurchaseOrderLine.objects.create(
                po=po,
                item=item,
                item_description=item.name,
                quantity=reorder_qty,
                unit_price=item.cost_price or item.standard_price or Decimal('0'),
                account_id=item.expense_account_id,
            )

        logger.info(
            f"Auto-PO {po_number} created for {item.sku} "
            f"(vendor: {item.preferred_vendor.name}, qty: {reorder_qty})"
        )

        # Raise / update a reorder alert alongside the PO
        ReorderAlert.objects.update_or_create(
            item=item,
            warehouse=movement.warehouse,
            is_sent=False,
            defaults={
                'current_stock': total_qty,
                'reorder_point': item.reorder_point,
                'suggested_quantity': reorder_qty,
            },
        )

    except Exception as exc:
        logger.error(f"Auto-PO creation failed for {item.sku}: {exc}", exc_info=True)


# ─── Stock Movements ──────────────────────────────────────────────────────────

class StockMovementViewSet(viewsets.ModelViewSet):
    queryset = StockMovement.objects.all().select_related('item', 'warehouse', 'batch', 'to_warehouse')
    serializer_class = StockMovementSerializer
    filterset_fields = ['movement_type', 'item', 'warehouse', 'to_warehouse', 'batch']
    search_fields = ['reference_number']
    pagination_class = InventoryPagination
    # Prevent update/delete — corrections should use ADJ movements
    http_method_names = ['get', 'post', 'head', 'options']

    def get_queryset(self):
        qs = super().get_queryset()
        # Allow callers to exclude a specific movement_type (e.g. exclude_type=TRF on the
        # Adjustments page so TRF records never pollute the list or skew pagination counts).
        exclude_type = self.request.query_params.get('exclude_type')
        if exclude_type:
            qs = qs.exclude(movement_type=exclude_type.upper())
        return qs

    def create(self, request, *args, **kwargs):
        """Create stock movement and optionally post to GL"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        post_to_gl = request.data.get('post_to_gl', 'true').lower() == 'true'
        gl_posted = False

        with transaction.atomic():
            movement = serializer.save()

            if post_to_gl:
                try:
                    journal = TransactionPostingService.post_stock_movement(movement)
                    movement.gl_posted = True
                    movement.journal_entry = journal
                    movement.save()
                    gl_posted = True
                except Exception as e:
                    logger.error(f"GL posting failed for movement {movement.id} ({movement.item.sku}): {e}")

            # Schedule auto-PO check after this transaction commits
            movement_id = movement.id
            transaction.on_commit(lambda: _maybe_create_auto_po(movement_id))

        logger.info(
            f"Stock movement created: {movement.movement_type} {movement.quantity} x {movement.item.sku} "
            f"@ warehouse {movement.warehouse.name} (gl_posted={gl_posted})"
        )

        response_data = serializer.data
        if post_to_gl and not gl_posted:
            response_data['gl_warning'] = 'GL posting failed. Use manual post_to_gl action to retry.'

        return Response(response_data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'])
    def transfer(self, request):
        """
        Step 1 of a two-step inter-warehouse transfer.

        Dispatches goods from the source warehouse:
        - Decrements ItemStock at source warehouse immediately.
        - Sets transfer_status = 'In Transit'.
        - Posts GL: DR Goods in Transit / CR Inventory (source warehouse).

        Destination warehouse inventory is NOT updated until /receive/ is called.
        """
        item_id = request.data.get('item')
        from_warehouse_id = request.data.get('from_warehouse')
        to_warehouse_id = request.data.get('to_warehouse')
        quantity = request.data.get('quantity')

        if not all([item_id, from_warehouse_id, to_warehouse_id, quantity]):
            return Response({"error": "item, from_warehouse, to_warehouse, quantity required"},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            item = Item.objects.get(pk=item_id)
        except Item.DoesNotExist:
            return Response({"error": f"Item {item_id} not found"}, status=status.HTTP_404_NOT_FOUND)

        post_to_gl = request.data.get('post_to_gl', 'true').lower() == 'true'
        gl_posted = False

        with transaction.atomic():
            # Validate + lock source warehouse stock (prevents race conditions)
            source_stock = ItemStock.objects.select_for_update().filter(
                item=item, warehouse_id=from_warehouse_id
            ).first()
            if not source_stock or source_stock.quantity < Decimal(str(quantity)):
                available = float(source_stock.quantity) if source_stock else 0
                return Response(
                    {"error": f"Insufficient stock. Available: {available}, Requested: {quantity}"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # DOUBLE-UPDATE FIX: use instance pattern + _skip_stock_update so the
            # post_save signal does NOT apply source -= qty AND dest += qty (the TRF
            # branch in signals.py credits BOTH warehouses immediately, which breaks
            # the two-step flow and double-counts).  The explicit F()-based updates
            # below are the single authoritative stock writes for dispatch.
            movement = StockMovement(
                item=item,
                warehouse_id=from_warehouse_id,
                to_warehouse_id=to_warehouse_id,
                movement_type='TRF',
                quantity=quantity,
                unit_price=item.average_cost,
                transfer_status='In Transit',
                reference_number=request.data.get('reference_number', ''),
                remarks=request.data.get('remarks', 'Stock Transfer'),
            )
            movement._skip_stock_update = True  # suppress signal; explicit updates below
            movement.save()

            # Step 1: ONLY decrement source warehouse.
            # Destination is credited when Warehouse B calls /receive/.
            ItemStock.objects.filter(item=item, warehouse_id=from_warehouse_id).update(
                quantity=F('quantity') - Decimal(str(quantity))
            )
            item.recalculate_stock_values()

            # GL Step 1: DR Goods in Transit / CR Inventory (Warehouse A)
            if post_to_gl:
                try:
                    journal = TransactionPostingService.post_transfer_dispatch(movement)
                    movement.gl_posted = True
                    movement.journal_entry = journal
                    movement.save(update_fields=['gl_posted', 'journal_entry'])
                    gl_posted = True
                except Exception as e:
                    logger.error(f"GL dispatch posting failed for transfer {movement.id}: {e}")

        logger.info(
            f"Transfer dispatched: {item.sku} qty={quantity} "
            f"WH#{from_warehouse_id} → WH#{to_warehouse_id} (In Transit, id={movement.id})"
        )

        response_data = StockMovementSerializer(movement).data
        if post_to_gl and not gl_posted:
            response_data['gl_warning'] = 'GL dispatch posting failed. Goods in Transit not yet recorded.'

        return Response(response_data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def receive(self, request, pk=None):
        """
        Step 2 of a two-step inter-warehouse transfer.

        Destination warehouse (Warehouse B) confirms receipt:
        - Increments ItemStock at destination warehouse.
        - Sets transfer_status = 'Received'.
        - Posts GL: DR Inventory (destination warehouse) / CR Goods in Transit.

        This clears the Goods in Transit clearing account.
        """
        movement = self.get_object()

        if movement.movement_type != 'TRF':
            return Response({"error": "Only TRF-type movements can be received."},
                            status=status.HTTP_400_BAD_REQUEST)
        if movement.transfer_status != 'In Transit':
            return Response(
                {"error": f"Transfer is '{movement.transfer_status}', not 'In Transit'. Cannot receive."},
                status=status.HTTP_400_BAD_REQUEST
            )

        post_to_gl = request.data.get('post_to_gl', 'true').lower() == 'true'
        gl_posted = False

        with transaction.atomic():
            # Credit destination warehouse inventory.
            # NOTE: No new StockMovement is created here — the signal won't fire,
            # so this explicit F()-update is the sole authoritative write for dest.
            ItemStock.objects.update_or_create(
                item=movement.item, warehouse_id=movement.to_warehouse_id,
                defaults={}
            )
            ItemStock.objects.filter(
                item=movement.item, warehouse_id=movement.to_warehouse_id
            ).update(quantity=F('quantity') + movement.quantity)
            movement.item.recalculate_stock_values()

            movement.transfer_status = 'Received'

            # GL Step 2: DR Inventory (Warehouse B) / CR Goods in Transit
            if post_to_gl:
                try:
                    journal = TransactionPostingService.post_transfer_receive(movement)
                    movement.receive_journal_entry = journal
                    gl_posted = True
                except Exception as e:
                    logger.error(f"GL receive posting failed for transfer {movement.id}: {e}")

            movement.save(update_fields=['transfer_status', 'receive_journal_entry'])

        logger.info(
            f"Transfer received: {movement.item.sku} qty={movement.quantity} "
            f"at WH#{movement.to_warehouse_id} (id={movement.id})"
        )

        response_data = StockMovementSerializer(movement).data
        if post_to_gl and not gl_posted:
            response_data['gl_warning'] = 'GL receive posting failed. Goods in Transit not yet cleared.'

        return Response(response_data)

    @action(detail=True, methods=['post'])
    def post_to_gl(self, request, pk=None):
        """Post a stock movement to GL manually"""
        movement = self.get_object()

        if movement.gl_posted:
            return Response({"error": "Movement already posted to GL"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            journal = TransactionPostingService.post_stock_movement(movement)
            movement.gl_posted = True
            movement.journal_entry = journal
            movement.save()
            logger.info(f"Stock movement {movement.id} manually posted to GL: {journal.reference_number}")
            return Response({
                "status": "Stock movement posted to GL",
                "journal_entry_id": journal.id,
                "journal_number": journal.reference_number
            })
        except Exception as e:
            logger.error(f"Manual GL posting failed for movement {movement.id}: {e}")
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class StockReconciliationViewSet(viewsets.ModelViewSet):
    queryset = StockReconciliation.objects.all().select_related('warehouse').prefetch_related('lines')
    serializer_class = StockReconciliationSerializer
    filterset_fields = ['status', 'warehouse', 'reconciliation_type']
    pagination_class = InventoryPagination

    @action(detail=True, methods=['post'])
    def add_line(self, request, pk=None):
        reconciliation = self.get_object()
        if reconciliation.status not in ('Draft', 'In Progress'):
            return Response({"error": "Can only add lines to Draft or In Progress reconciliations"},
                            status=status.HTTP_400_BAD_REQUEST)

        item_id = request.data.get('item')
        physical_qty = request.data.get('physical_quantity')

        if not all([item_id, physical_qty is not None]):
            return Response({"error": "item and physical_quantity required"},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            item = Item.objects.get(pk=item_id)
        except Item.DoesNotExist:
            return Response({"error": f"Item {item_id} not found"}, status=status.HTTP_404_NOT_FOUND)

        stock = ItemStock.objects.filter(item=item, warehouse=reconciliation.warehouse).first()
        sys_qty = stock.quantity if stock else 0

        # Upsert: update existing line if the same item was already added
        existing = StockReconciliationLine.objects.filter(
            reconciliation=reconciliation, item=item
        ).first()
        if existing:
            existing.physical_quantity = physical_qty
            if request.data.get('reason') is not None:
                existing.reason = request.data.get('reason', '')
            existing.save()
            return Response(StockReconciliationLineSerializer(existing).data)

        line = StockReconciliationLine.objects.create(
            reconciliation=reconciliation,
            item=item,
            system_quantity=sys_qty,
            physical_quantity=physical_qty,
            reason=request.data.get('reason', ''),
        )
        return Response(StockReconciliationLineSerializer(line).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def populate_items(self, request, pk=None):
        """Auto-load every item that has stock in this warehouse as reconciliation lines."""
        reconciliation = self.get_object()
        if reconciliation.status not in ('Draft', 'In Progress'):
            return Response(
                {"error": "Can only populate lines on Draft or In Progress reconciliations"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        stocks = ItemStock.objects.filter(
            warehouse=reconciliation.warehouse,
            quantity__gt=0,
        ).select_related('item')

        created = 0

        with transaction.atomic():
            # Use get_or_create so the operation is idempotent and race-condition-safe.
            # Concurrent calls will each attempt a DB-level insert; the second one will
            # find the existing row and skip rather than creating a duplicate.
            for stock in stocks:
                _, was_created = StockReconciliationLine.objects.get_or_create(
                    reconciliation=reconciliation,
                    item=stock.item,
                    defaults={
                        'system_quantity':   stock.quantity,
                        'physical_quantity': stock.quantity,  # default = system qty; user edits to actual count
                    },
                )
                if was_created:
                    created += 1

        return Response({
            "created": created,
            "message": f"{created} item{'s' if created != 1 else ''} loaded into reconciliation.",
        })

    @action(detail=True, methods=['post'])
    def start(self, request, pk=None):
        """Transition a Draft reconciliation to In Progress (counting has begun)."""
        reconciliation = self.get_object()
        if reconciliation.status != 'Draft':
            return Response(
                {"error": "Only Draft reconciliations can be started."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        reconciliation.status = 'In Progress'
        reconciliation.save()
        return Response(self.get_serializer(reconciliation).data)

    @action(detail=True, methods=['post'])
    def update_line(self, request, pk=None):
        """Update physical_quantity and/or reason on an existing reconciliation line."""
        reconciliation = self.get_object()
        if reconciliation.status not in ('Draft', 'In Progress'):
            return Response(
                {"error": "Cannot edit lines on a completed or cancelled reconciliation."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        line_id = request.data.get('line_id')
        if not line_id:
            return Response({"error": "line_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            line = StockReconciliationLine.objects.get(pk=line_id, reconciliation=reconciliation)
        except StockReconciliationLine.DoesNotExist:
            return Response({"error": "Line not found."}, status=status.HTTP_404_NOT_FOUND)

        if 'physical_quantity' in request.data:
            line.physical_quantity = Decimal(str(request.data['physical_quantity']))
        if 'reason' in request.data:
            line.reason = request.data.get('reason', '')
        line.save()
        return Response(StockReconciliationLineSerializer(line).data)

    @action(detail=True, methods=['post'])
    def adjust(self, request, pk=None):
        """Process reconciliation adjustments with stock movements and GL posting"""
        reconciliation = self.get_object()
        # FIX #42: Only allow adjust when counting is actively in progress.
        # Adjusting a Draft (not yet started) reconciliation would skip the
        # review phase and corrupt stock with unvalidated counts.
        if reconciliation.status != 'In Progress':
            return Response(
                {"error": "Reconciliation must be In Progress before adjustments can be applied. "
                          "Use the 'start' action to begin counting first."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            for line in reconciliation.lines.all():
                if not line.is_adjusted and line.variance_quantity != 0:
                    stock, _ = ItemStock.objects.get_or_create(
                        item=line.item,
                        warehouse=reconciliation.warehouse
                    )
                    old_qty = stock.quantity

                    # Explicitly set the stock to the verified physical count.
                    # We use a direct assignment here for precision (physical count is the ground truth).
                    stock.quantity = line.physical_quantity
                    stock.save()

                    # Create an ADJ StockMovement for the audit trail.
                    # Use signed quantity: positive = gain, negative = loss.
                    # The _skip_stock_update flag tells the post_save signal to skip
                    # its own stock update — the explicit save above is the authoritative update.
                    signed_qty = line.variance_quantity  # already signed (physical − system)
                    movement = StockMovement(
                        item=line.item,
                        warehouse=reconciliation.warehouse,
                        movement_type='ADJ',
                        quantity=signed_qty,
                        unit_price=line.item.average_cost or 0,
                        reference_number=reconciliation.reconciliation_number,
                        remarks=f"Reconciliation adjustment: {old_qty} → {line.physical_quantity}"
                    )
                    movement._skip_stock_update = True  # suppress signal double-count
                    movement.save()

                    line.is_adjusted = True
                    line.save()

                    logger.info(
                        f"Reconciliation {reconciliation.reconciliation_number}: "
                        f"{line.item.sku} adjusted {old_qty} → {line.physical_quantity}"
                    )

            # Post GL entries for the reconciliation
            try:
                TransactionPostingService.post_stock_reconciliation(reconciliation)
            except Exception as e:
                logger.error(f"GL posting failed for reconciliation {reconciliation.reconciliation_number}: {e}")

            reconciliation.status = 'Completed'
            reconciliation.save()

        return Response({"status": "Reconciliation completed and stock adjusted"})


class ReorderAlertViewSet(viewsets.ModelViewSet):
    queryset = ReorderAlert.objects.all().select_related('item', 'warehouse')
    serializer_class = ReorderAlertSerializer
    filterset_fields = ['item', 'warehouse', 'is_sent']
    pagination_class = InventoryPagination

    @action(detail=False, methods=['post'])
    def generate_alerts(self, request):
        """Generate reorder alerts for items below reorder point using DB query"""
        low_stock = ItemStock.objects.filter(
            item__is_active=True,
            item__reorder_point__gt=0,
            quantity__lte=F('item__reorder_point')
        ).select_related('item', 'warehouse')[:1000]

        alerts_created = 0
        for stock in low_stock:
            alert, created = ReorderAlert.objects.get_or_create(
                item=stock.item,
                warehouse=stock.warehouse,
                is_sent=False,
                defaults={
                    'current_stock': stock.quantity,
                    'reorder_point': stock.item.reorder_point,
                    'suggested_quantity': stock.item.reorder_quantity or stock.item.reorder_point * 2
                }
            )
            if created:
                alerts_created += 1
        return Response({"alerts_generated": alerts_created})


class ItemSerialNumberViewSet(viewsets.ModelViewSet):
    queryset = ItemSerialNumber.objects.all().select_related('item', 'warehouse', 'batch')
    serializer_class = ItemSerialNumberSerializer
    filterset_fields = ['item', 'status', 'warehouse', 'batch']
    search_fields = ['serial_number', 'item__sku', 'item__name']
    pagination_class = InventoryPagination


class BatchExpiryAlertViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = BatchExpiryAlert.objects.all().select_related('item', 'batch', 'warehouse')
    serializer_class = BatchExpiryAlertSerializer
    filterset_fields = ['item', 'warehouse', 'is_sent', 'is_dismissed']
    pagination_class = InventoryPagination

    @action(detail=False, methods=['post'])
    def generate_expiry_alerts(self, request):
        """Generate batch expiry alerts"""
        from django.conf import settings
        from datetime import timedelta, date

        inv_settings = getattr(settings, 'INVENTORY_SETTINGS', {})
        alert_days = inv_settings.get('EXPIRY_ALERT_DAYS', 30)

        alert_date = date.today() + timedelta(days=alert_days)

        alerts_created = 0
        batches = ItemBatch.objects.filter(
            expiry_date__lte=alert_date,
            expiry_date__gte=date.today(),
            remaining_quantity__gt=0
        ).select_related('item', 'warehouse')[:1000]

        for batch in batches:
            alert, created = BatchExpiryAlert.objects.get_or_create(
                batch=batch,
                defaults={
                    'item': batch.item,
                    'warehouse': batch.warehouse,
                    'expiry_date': batch.expiry_date,
                    'remaining_quantity': batch.remaining_quantity,
                    'alert_date': date.today()
                }
            )
            if created:
                alerts_created += 1

        return Response({"alerts_generated": alerts_created})

    @action(detail=False, methods=['get'])
    def upcoming_expiry(self, request):
        """Get batches expiring soon"""
        from datetime import date, timedelta

        days = int(request.query_params.get('days', 30))
        expiry_date = date.today() + timedelta(days=days)

        batches = ItemBatch.objects.filter(
            expiry_date__lte=expiry_date,
            expiry_date__gte=date.today(),
            remaining_quantity__gt=0
        ).select_related('item', 'warehouse')

        data = []
        for batch in batches:
            days_until_expiry = (batch.expiry_date - date.today()).days
            data.append({
                'id': batch.id,
                'item_sku': batch.item.sku,
                'item_name': batch.item.name,
                'batch_number': batch.batch_number,
                'warehouse': batch.warehouse.name,
                'quantity': float(batch.remaining_quantity),
                'expiry_date': batch.expiry_date,
                'days_until_expiry': days_until_expiry
            })

        return Response(data)
