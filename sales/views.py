import logging
from decimal import Decimal

from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from core.permissions import IsApprover, RBACPermission

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Prefetch, Sum, Value, DecimalField
from django.db.models.functions import Coalesce
from django.utils import timezone
from .models import Customer, CustomerCategory, Lead, Opportunity, Quotation, SalesOrder, SalesOrderLine, DeliveryNote, DeliveryNoteLine, SalesReturn, CreditNote
from .serializers import CustomerSerializer, CustomerCategorySerializer, LeadSerializer, OpportunitySerializer, QuotationSerializer, SalesOrderSerializer, DeliveryNoteSerializer, SalesReturnSerializer, CreditNoteSerializer
from accounting.transaction_posting import TransactionPostingService

logger = logging.getLogger('dtsg')


class SalesPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 50


class CustomerCategoryViewSet(viewsets.ModelViewSet):
    queryset = CustomerCategory.objects.select_related('accounts_receivable_account').all()
    serializer_class = CustomerCategorySerializer
    permission_classes = [RBACPermission]
    search_fields = ['name', 'code']
    pagination_class = SalesPagination



class CustomerViewSet(viewsets.ModelViewSet):
    queryset = Customer.objects.select_related(
        'category',
        'category__accounts_receivable_account',
        'accounts_receivable_account',
    ).all()
    serializer_class = CustomerSerializer
    permission_classes = [RBACPermission]
    search_fields = ['name', 'customer_code']
    filterset_fields = ['industry', 'category']
    pagination_class = SalesPagination

    def _sync_gl(self, instance):
        """Sync AR account from the customer's category."""
        cat = instance.category
        if cat and cat.accounts_receivable_account_id:
            instance.accounts_receivable_account_id = cat.accounts_receivable_account_id
            instance.save(update_fields=['accounts_receivable_account'])

    def perform_create(self, serializer):
        instance = serializer.save()
        self._sync_gl(instance)

    def perform_update(self, serializer):
        instance = serializer.save()
        self._sync_gl(instance)


class LeadViewSet(viewsets.ModelViewSet):
    queryset = Lead.objects.select_related('converted_to_customer').all()
    serializer_class = LeadSerializer
    permission_classes = [RBACPermission]
    filterset_fields = ['status', 'source']
    search_fields = ['name', 'company', 'email']
    pagination_class = SalesPagination


class OpportunityViewSet(viewsets.ModelViewSet):
    queryset = Opportunity.objects.select_related('customer', 'lead').all()
    serializer_class = OpportunitySerializer
    permission_classes = [RBACPermission]
    filterset_fields = ['stage', 'customer']
    search_fields = ['name', 'customer__name']
    pagination_class = SalesPagination

    @action(detail=False, methods=['get'])
    def forecast(self, request):
        """Calculate weighted sales forecast from opportunities"""
        stage_filter = request.query_params.get('stage')
        
        opportunities = self.queryset.filter(
            stage__in=['Prospecting', 'Qualification', 'Proposal', 'Negotiation']
        )
        
        if stage_filter:
            opportunities = opportunities.filter(stage=stage_filter)
        
        # Fetch once — group in Python to avoid one DB query per stage
        all_ops = list(opportunities)
        stage_groups: dict = {s: [] for s in ['Prospecting', 'Qualification', 'Proposal', 'Negotiation']}
        for op in all_ops:
            if op.stage in stage_groups:
                stage_groups[op.stage].append(op)

        total_value = sum(op.expected_value for op in all_ops)
        weighted_forecast = sum(
            op.expected_value * op.probability / 100
            for op in all_ops
        )

        stage_breakdown = {}
        for stage, ops in stage_groups.items():
            stage_breakdown[stage] = {
                'count': len(ops),
                'total_value': float(sum(op.expected_value for op in ops)),
                'weighted_value': float(sum(
                    op.expected_value * op.probability / 100
                    for op in ops
                )),
            }

        return Response({
            'total_opportunities': len(all_ops),
            'total_value': float(total_value),
            'weighted_forecast': float(weighted_forecast),
            'stage_breakdown': stage_breakdown,
        })


class QuotationViewSet(viewsets.ModelViewSet):
    queryset = Quotation.objects.select_related(
        'customer', 'mda', 'fund', 'function', 'program', 'geo'
    ).prefetch_related('lines').all()
    serializer_class = QuotationSerializer
    permission_classes = [RBACPermission]
    filterset_fields = ['status', 'customer']
    pagination_class = SalesPagination

    @action(detail=True, methods=['post'])
    def send_quotation(self, request, pk=None):
        quotation = self.get_object()
        quotation.status = 'Sent'
        quotation.save()
        return Response({"status": "Quotation marked as sent"})

    @action(detail=True, methods=['post'])
    def convert_to_order(self, request, pk=None):
        quotation = self.get_object()
        if quotation.status != 'Accepted':
            return Response({"error": "Only accepted quotations can be converted"}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            order = SalesOrder.objects.create(
                customer=quotation.customer,
                quotation=quotation,
                order_date=timezone.now().date(),
                fund=quotation.fund,
                function=quotation.function,
                program=quotation.program,
                geo=quotation.geo,
                status='Draft'
            )

            order_lines = [
                SalesOrderLine(
                    order=order,
                    item=qline.item,
                    item_description=qline.item_description,
                    quantity=qline.quantity,
                    unit_price=qline.unit_price,
                    discount_percent=qline.discount_percent,
                )
                for qline in quotation.lines.select_related('item').all()
            ]
            SalesOrderLine.objects.bulk_create(order_lines)

            quotation.status = 'Converted'
            quotation.save()

        return Response({"status": "Quotation converted to Sales Order", "order_id": order.id})


class SalesOrderViewSet(viewsets.ModelViewSet):
    queryset = SalesOrder.objects.select_related(
        'customer', 'quotation', 'fund', 'function', 'program', 'geo', 'revenue_account'
    ).prefetch_related(
        Prefetch('lines', queryset=SalesOrderLine.objects.select_related('item', 'product_type', 'product_category'))
    ).all()
    serializer_class = SalesOrderSerializer
    permission_classes = [RBACPermission]
    filterset_fields = ['status', 'customer']
    pagination_class = SalesPagination

    def get_permissions(self):
        if self.action in ['approve_order', 'post_order']:
            return [IsApprover()]
        return super().get_permissions()

    def perform_destroy(self, instance):
        if instance.status != 'Draft':
            raise ValidationError("Only draft orders can be deleted.")
        super().perform_destroy(instance)

    @action(detail=True, methods=['post'])
    def submit_for_approval(self, request, pk=None):
        """Submit Sales Order for approval through the centralized workflow engine."""
        from workflow.views import auto_route_approval
        order = self.get_object()
        if order.status not in ['Draft', 'Rejected']:
            return Response(
                {"error": "Only Draft or Rejected orders can be submitted."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Rejected orders must transition back to Draft first (per ALLOWED_TRANSITIONS)
        if order.status == 'Rejected':
            order.status = 'Draft'
            order.save()

        # Calculate total amount for amount-based routing
        amount = getattr(order, 'total_amount', None)

        result = auto_route_approval(
            order, 'salesorder', request,
            title=f"SO-{order.order_number}: {order.customer.name if order.customer else 'N/A'}",
            amount=amount,
        )

        if result.get('auto_approved'):
            order.status = 'Approved'
            msg = "Sales Order auto-approved (below threshold)."
        else:
            order.status = 'Pending'
            msg = "Sales Order submitted for approval."

        order.save()
        return Response({"status": msg, "approval_id": result.get('approval_id')})

    @action(detail=True, methods=['post'])
    def approve_order(self, request, pk=None):
        """Approve a sales order with credit check"""
        from django.conf import settings

        order = self.get_object()
        if order.status not in ['Draft', 'Pending']:
            return Response({"error": "Order cannot be approved in current status."},
                          status=status.HTTP_400_BAD_REQUEST)

        sales_settings = getattr(settings, 'SALES_SETTINGS', {})
        require_approval = sales_settings.get('REQUIRE_SALES_APPROVAL', True)

        if require_approval:
            # Lock the customer row for the duration of credit check + status change so
            # two concurrent approvals cannot both read the same balance and both pass.
            with transaction.atomic():
                customer = Customer.objects.select_for_update().get(pk=order.customer_id)

                if customer.credit_check_enabled:
                    if customer.credit_status_auto == 'Blocked':
                        return Response({
                            "error": "Customer credit is blocked. Please contact accounting."
                        }, status=status.HTTP_400_BAD_REQUEST)

                    order_total = sum(line.total_price for line in order.lines.all())

                    # Include approved-but-not-yet-posted SOs in credit utilization so that
                    # concurrent approvals don't collectively exceed the credit limit.
                    pending_so_total = SalesOrder.objects.filter(
                        customer=customer,
                        status__in=['Approved'],
                    ).exclude(pk=order.pk).aggregate(
                        total=Coalesce(Sum(F('lines__quantity') * F('lines__unit_price') * (1 - F('lines__discount_percent') / 100)), Value(Decimal('0')), output_field=DecimalField())
                    )['total'] or Decimal('0')

                    effective_balance = customer.balance + pending_so_total
                    credit_available = customer.credit_limit - effective_balance

                    if credit_available < order_total:
                        return Response({
                            "error": f"Insufficient credit. Available: {credit_available}, Required: {order_total}",
                            "credit_status": customer.credit_status_auto,
                            "credit_limit": float(customer.credit_limit),
                            "current_balance": float(customer.balance),
                            "pending_approved_total": float(pending_so_total),
                        }, status=status.HTTP_400_BAD_REQUEST)

                    warning_threshold = float(customer.credit_warning_threshold)
                    credit_utilization = (float(effective_balance) + float(order_total)) / float(customer.credit_limit) * 100

                    if credit_utilization >= warning_threshold:
                        logger.warning(
                            f"Credit warning for customer {customer.name}: "
                            f"Utilization at {credit_utilization:.1f}% (threshold: {warning_threshold}%)"
                        )

                order.status = 'Approved'
                order.save()
            
            # O2C-M2: Auto-reserve stock when SO is approved
            try:
                from inventory.models import ItemStock
                warehouse_id = request.data.get('warehouse_id')
                if warehouse_id:
                    reservations = []
                    for line in order.lines.all():
                        if line.item:
                            stock = ItemStock.objects.filter(
                                item=line.item,
                                warehouse_id=warehouse_id
                            ).first()
                            if stock:
                                try:
                                    stock.reserve(
                                        quantity=line.quantity,
                                        reference_type='SalesOrder',
                                        reference_id=order.pk
                                    )
                                    reservations.append({
                                        'item': line.item.sku,
                                        'quantity': float(line.quantity),
                                        'reserved': True
                                    })
                                except ValueError as e:
                                    reservations.append({
                                        'item': line.item.sku,
                                        'quantity': float(line.quantity),
                                        'reserved': False,
                                        'error': str(e)
                                    })
                    if reservations:
                        logger.info(f"Stock reserved for SO {order.order_number}: {reservations}")
            except ImportError as exc:
                logger.warning(
                    "sales: Inventory module unavailable; "
                    "skipping auto-reserve for SO %s: %s",
                    order.order_number, exc,
                )
            
            logger.info(f"Sales Order {order.order_number} approved by {request.user}")
            return Response({"status": f"Sales Order {order.order_number} approved."})
        else:
            return Response({"error": "Approval not required. Use post_order instead."},
                          status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def reject_order(self, request, pk=None):
        """Reject a sales order"""
        order = self.get_object()
        reason = request.data.get('reason', '')

        if order.status not in ['Draft', 'Pending', 'Approved']:
            return Response({"error": "Order cannot be rejected in current status."},
                          status=status.HTTP_400_BAD_REQUEST)

        order.status = 'Rejected'
        order.notes = f"{order.notes}\n\nRejected: {reason}".strip()
        order.save()
        logger.info(f"Sales Order {order.order_number} rejected by {request.user}: {reason}")

        return Response({"status": f"Sales Order {order.order_number} rejected."})

    @action(detail=True, methods=['post'])
    def post_order(self, request, pk=None):
        """Post a sales order to GL"""
        order = self.get_object()

        if order.status == 'Posted':
            return Response({"error": "Order is already posted."}, status=status.HTTP_400_BAD_REQUEST)

        if order.status != 'Approved':
            return Response({"error": "Order must be approved before posting."},
                          status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                order.status = 'Posted'
                order.save()
                journal = TransactionPostingService.post_sales_order(order)

            logger.info(f"Sales Order {order.order_number} posted. Journal: {journal.reference_number}")
            return Response({
                "status": f"Sales Order {order.order_number} posted successfully.",
                "journal_entry_id": journal.id,
                "journal_number": journal.reference_number
            })
        except Exception as e:
            logger.error(f"Failed to post sales order {order.order_number}: {e}", exc_info=True)
            return Response({"error": "Failed to post order. Please try again or contact support."},
                          status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'])
    def credit_check(self, request):
        """Get customers approaching credit limit"""
        at_risk = Customer.objects.filter(
            credit_limit__gt=0,
            balance__gte=F('credit_limit') * Decimal('0.8')
        ).values('id', 'name', 'credit_limit', 'balance')

        result = []
        for c in at_risk:
            credit_available = c['credit_limit'] - c['balance']
            credit_status = 'Credit Exceeded' if c['balance'] >= c['credit_limit'] else 'Credit Warning'
            result.append({
                'id': c['id'],
                'name': c['name'],
                'credit_limit': float(c['credit_limit']),
                'balance': float(c['balance']),
                'credit_available': float(credit_available),
                'status': credit_status,
            })
        return Response(result)


class DeliveryNoteViewSet(viewsets.ModelViewSet):
    queryset = DeliveryNote.objects.select_related(
        'sales_order', 'sales_order__customer'
    ).prefetch_related(
        Prefetch('lines', queryset=DeliveryNoteLine.objects.select_related('so_line'))
    ).all()
    serializer_class = DeliveryNoteSerializer
    permission_classes = [RBACPermission]
    filterset_fields = ['status', 'sales_order']
    pagination_class = SalesPagination

    @action(detail=True, methods=['post'])
    def post_delivery(self, request, pk=None):
        """Post delivery note and update inventory"""
        from inventory.models import StockMovement, Warehouse

        delivery = self.get_object()
        if delivery.status == 'Posted':
            return Response({"error": "Delivery already posted."}, status=status.HTTP_400_BAD_REQUEST)

        warehouse_id = request.data.get('warehouse_id')
        if not warehouse_id:
            return Response({"error": "warehouse_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            warehouse = Warehouse.objects.get(pk=warehouse_id, is_active=True)
        except Warehouse.DoesNotExist:
            return Response({"error": "Invalid or inactive warehouse."}, status=status.HTTP_400_BAD_REQUEST)

        # O2C-H1: Stock Validation Before Delivery
        try:
            from inventory.models import ItemStock
            insufficient_items = []
            for line in delivery.lines.select_related('so_line', 'so_line__item').all():
                if line.so_line and line.so_line.item:
                    stock = ItemStock.objects.filter(
                        item=line.so_line.item,
                        warehouse=warehouse
                    ).first()
                    available_qty = stock.available_quantity if stock else 0
                    if available_qty < line.quantity_delivered:
                        insufficient_items.append({
                            'item': line.so_line.item.sku,
                            'required': float(line.quantity_delivered),
                            'available': float(available_qty)
                        })
            
            if insufficient_items:
                return Response({
                    "error": "Insufficient stock for delivery",
                    "insufficient_items": insufficient_items
                }, status=status.HTTP_400_BAD_REQUEST)
        except ImportError as exc:
            logger.warning("Inventory module unavailable, skipping stock validation for delivery %s: %s", delivery.pk, exc)

        try:
            with transaction.atomic():
                delivery.status = 'Posted'
                delivery.save()
                
                # O2C-H4: Lock Invoice After DN Creation
                # Make invoice read-only after delivery is posted
                try:
                    from accounting.models import CustomerInvoice
                    invoice = CustomerInvoice.objects.filter(
                        sales_order=delivery.sales_order,
                        status__in=['Draft', 'Sent']
                    ).first()
                    if invoice:
                        invoice.status = 'Sent'
                        invoice.save(update_fields=['status'], _allow_status_change=True)
                except ImportError as exc:
                    logger.warning(
                        "sales: CustomerInvoice model unavailable; "
                        "skipping auto-status update for delivery %s: %s",
                        getattr(delivery, 'pk', '?'), exc,
                    )
                
                from inventory.models import ItemStock as _ItemStock
                _items_to_recalculate = set()
                for line in delivery.lines.select_related('so_line', 'so_line__item').all():
                    if line.so_line and line.so_line.item:
                        # DOUBLE-UPDATE FIX: use instance pattern + _skip_stock_update so the
                        # post_save signal (OUT branch: source -= qty) does not fire alongside
                        # the explicit ItemStock.update() below.
                        _dn_movement = StockMovement(
                            item=line.so_line.item,
                            warehouse=warehouse,
                            movement_type='OUT',
                            quantity=line.quantity_delivered,
                            unit_price=line.so_line.unit_price or 0,
                            reference_number=delivery.delivery_number,
                            remarks=f"Sales Delivery: {delivery.delivery_number}"
                        )
                        _dn_movement._skip_stock_update = True  # explicit update below
                        _dn_movement.save()
                        # Decrement ItemStock quantity atomically (single authoritative write)
                        _ItemStock.objects.filter(
                            item=line.so_line.item,
                            warehouse=warehouse,
                        ).update(quantity=F('quantity') - line.quantity_delivered)
                        _items_to_recalculate.add(line.so_line.item)

                # Recalculate item-level aggregates once per unique item (signal was skipped)
                for _recalc_item in _items_to_recalculate:
                    _recalc_item.recalculate_stock_values()

                # PF-7: Release stock reservations after delivery
                # Also decrement reserved_quantity on ItemStock so available_quantity stays accurate
                from inventory.models import Reservation
                for line in delivery.lines.select_related('so_line', 'so_line__item').all():
                    if line.so_line:
                        fulfilled = Reservation.objects.filter(
                            sales_order_line=line.so_line,
                            warehouse=warehouse,
                            status='Pending'
                        )
                        reserved_total = fulfilled.aggregate(
                            total=Coalesce(Sum('quantity'), Value(Decimal('0')), output_field=DecimalField())
                        )['total']
                        fulfilled.update(status='Fulfilled', fulfilled_quantity=F('quantity'))
                        if reserved_total > 0 and line.so_line.item:
                            _ItemStock.objects.filter(
                                item=line.so_line.item,
                                warehouse=warehouse,
                            ).update(reserved_quantity=F('reserved_quantity') - reserved_total)

                journal = TransactionPostingService.post_delivery_note(delivery)

            logger.info(f"Delivery {delivery.delivery_number} posted. Warehouse: {warehouse.name}")
            if journal:
                return Response({
                    "status": f"Delivery {delivery.delivery_number} posted and inventory updated.",
                    "journal_entry_id": journal.id,
                    "journal_number": journal.reference_number
                })
            return Response({"status": f"Delivery {delivery.delivery_number} posted."})
        except Exception as e:
            logger.error(f"Failed to post delivery {delivery.delivery_number}: {e}", exc_info=True)
            return Response({"error": "Failed to post delivery. Please try again or contact support."},
                          status=status.HTTP_400_BAD_REQUEST)


class SalesReturnViewSet(viewsets.ModelViewSet):
    queryset = SalesReturn.objects.select_related('sales_order', 'customer').prefetch_related('lines').all()
    serializer_class = SalesReturnSerializer
    permission_classes = [RBACPermission]
    filterset_fields = ['status', 'customer', 'sales_order']
    pagination_class = SalesPagination

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """
        Approve a Draft or Pending sales return, allowing it to be processed.
        Transitions: Draft/Pending → Approved
        """
        sales_return = self.get_object()
        if sales_return.status not in ('Draft', 'Pending'):
            return Response(
                {"error": f"Only Draft or Pending returns can be approved. Current status: {sales_return.status}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        sales_return.status = 'Approved'
        sales_return.save(update_fields=['status'])
        logger.info(f"Sales Return {sales_return.return_number} approved by {request.user}")
        return Response({"status": f"Sales Return {sales_return.return_number} approved."})

    @action(detail=True, methods=['post'])
    def process(self, request, pk=None):
        """
        Process an Approved sales return:
        - Restores ItemStock for returned items
        - Posts GL reversal (DR Revenue / CR AR + DR Inventory / CR COGS)
        - Reduces customer balance
        - Transitions status to Processed
        """
        sales_return = self.get_object()
        if sales_return.status != 'Approved':
            return Response(
                {"error": f"Only Approved returns can be processed. Current status: {sales_return.status}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with transaction.atomic():
                from inventory.models import ItemStock, StockMovement, Warehouse
                warehouse = Warehouse.objects.filter(is_active=True).first()

                # Restore inventory for each returned item.
                # Create a StockMovement (IN) for full audit trail, using the
                # _skip_stock_update flag so the post_save signal does not also
                # increment stock — the explicit F()-update below is the sole write.
                _items_to_recalculate = set()
                for line in sales_return.lines.select_related('item').all():
                    if line.item and line.quantity > 0 and warehouse:
                        _ret_movement = StockMovement(
                            item=line.item,
                            warehouse=warehouse,
                            movement_type='IN',
                            quantity=line.quantity,
                            unit_price=getattr(line.item, 'average_cost', None) or line.unit_price or 0,
                            reference_number=sales_return.return_number,
                            remarks=f"Sales Return: {sales_return.return_number}",
                        )
                        _ret_movement._skip_stock_update = True
                        _ret_movement.save()
                        ItemStock.objects.update_or_create(
                            item=line.item, warehouse=warehouse, defaults={}
                        )
                        ItemStock.objects.filter(
                            item=line.item, warehouse=warehouse
                        ).update(quantity=F('quantity') + line.quantity)
                        _items_to_recalculate.add(line.item)

                for _recalc_item in _items_to_recalculate:
                    _recalc_item.recalculate_stock_values()

                sales_return.status = 'Processed'
                sales_return.save()

                journal = TransactionPostingService.post_sales_return(sales_return)

            return Response({
                "status": "Sales return processed.",
                "journal_entry_id": journal.id,
                "journal_number": journal.reference_number,
            })
        except Exception as e:
            logger.error(f"Failed to process sales return {sales_return.return_number}: {e}", exc_info=True)
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class CreditNoteViewSet(viewsets.ModelViewSet):
    queryset = CreditNote.objects.select_related('customer', 'sales_return').all()
    serializer_class = CreditNoteSerializer
    permission_classes = [RBACPermission]
    filterset_fields = ['status', 'customer']
    pagination_class = SalesPagination

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """
        Approve a Draft credit note, making it ready for application.
        Transitions: Draft → Approved
        """
        credit_note = self.get_object()
        if credit_note.status != 'Draft':
            return Response(
                {"error": f"Only Draft credit notes can be approved. Current status: {credit_note.status}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        credit_note.status = 'Approved'
        credit_note.save(update_fields=['status'])
        logger.info(f"Credit Note {credit_note.credit_note_number} approved by {request.user}")
        return Response({"status": f"Credit Note {credit_note.credit_note_number} approved."})

    @action(detail=True, methods=['post'])
    def apply(self, request, pk=None):
        """
        Apply an Approved credit note:
        - Posts GL entry (DR Sales Revenue / CR AR)
        - Reduces customer balance by credit note amount
        - Transitions status to Applied
        """
        credit_note = self.get_object()
        if credit_note.status != 'Approved':
            return Response(
                {"error": f"Only Approved credit notes can be applied. Current status: {credit_note.status}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with transaction.atomic():
                credit_note.status = 'Applied'
                credit_note.save()
                journal = TransactionPostingService.post_credit_note(credit_note)

            return Response({
                "status": "Credit note applied.",
                "journal_entry_id": journal.id,
                "journal_number": journal.reference_number,
            })
        except Exception as e:
            logger.error(f"Failed to apply credit note {credit_note.credit_note_number}: {e}", exc_info=True)
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class SalesAnalyticsViewSet(viewsets.ViewSet):
    """Sales analytics and KPI endpoints."""
    permission_classes = [RBACPermission]

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Overall sales summary for a period."""
        from django.db.models import Sum, Count, Avg
        from datetime import date, timedelta

        period = request.query_params.get('period', '30')
        days = int(period)
        start_date = date.today() - timedelta(days=days)

        orders = SalesOrder.objects.filter(
            order_date__gte=start_date,
            status__in=['Approved', 'Posted', 'Closed'],
        )

        total_orders = orders.count()
        # total_amount is a @property (not a DB field), so compute at Python level
        revenue_values = [o.total_amount for o in orders.prefetch_related('lines')]
        total_revenue = sum(revenue_values)
        avg_order_value = total_revenue / total_orders if total_orders else 0

        top_customers = (
            orders.values('customer__name')
            .annotate(count=Count('id'))
            .order_by('-count')[:10]
        )

        top_items = (
            SalesOrderLine.objects.filter(order__in=orders)
            .values('item__name', 'item__sku')
            .annotate(
                total_qty=Sum('quantity'),
                total_value=Sum(F('quantity') * F('unit_price') * (1 - F('discount_percent') / 100)),
            )
            .order_by('-total_value')[:10]
        )

        return Response({
            'period_days': days,
            'total_orders': total_orders,
            'total_revenue': float(total_revenue),
            'avg_order_value': float(avg_order_value),
            'top_customers': list(top_customers),
            'top_items': list(top_items),
        })
