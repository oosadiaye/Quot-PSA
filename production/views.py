import logging

from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination

from decimal import Decimal
from django.db import transaction
from django.db.models import Count, DecimalField, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from core.permissions import RBACPermission
from .models import (
    WorkCenter, BillOfMaterials, BOMLine, ProductionOrder,
    MaterialIssue, MaterialReceipt, JobCard, Routing
)
from .serializers import (
    WorkCenterSerializer, BillOfMaterialsSerializer, BOMLineSerializer,
    ProductionOrderSerializer, MaterialIssueSerializer, MaterialReceiptSerializer,
    JobCardSerializer, RoutingSerializer
)
from accounting.models import JournalHeader, JournalLine


class ProductionPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class WorkCenterViewSet(viewsets.ModelViewSet):
    queryset = WorkCenter.objects.all()
    serializer_class = WorkCenterSerializer
    pagination_class = ProductionPagination
    permission_classes = [RBACPermission]
    filterset_fields = ['is_active']
    search_fields = ['name', 'code']

    @action(detail=True, methods=['get'])
    def capacity(self, request, pk=None):
        """Get work center capacity utilization"""
        from datetime import timedelta
        
        work_center = self.get_object()
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        
        if not start_date:
            start_date = timezone.now().date()
        else:
            start_date = timezone.datetime.strptime(start_date, '%Y-%m-%d').date()
        
        if not end_date:
            end_date = start_date + timedelta(days=7)
        else:
            end_date = timezone.datetime.strptime(end_date, '%Y-%m-%d').date()
        
        days_in_range = (end_date - start_date).days + 1
        
        available_hours = float(work_center.capacity_hours) * days_in_range
        efficiency_factor = float(work_center.efficiency) / 100
        total_available = available_hours * efficiency_factor
        
        routing_hours_subquery = Subquery(
            Routing.objects.filter(bom=OuterRef('bom'))
            .values('bom')
            .annotate(total=Sum('time_hours'))
            .values('total')[:1],
            output_field=DecimalField(),
        )
        scheduled_orders = ProductionOrder.objects.filter(
            work_center=work_center,
            start_date__lte=end_date,
            end_date__gte=start_date,
            status__in=['Scheduled', 'In Progress']
        ).annotate(
            routing_hours_total=Coalesce(routing_hours_subquery, Value(0, output_field=DecimalField()))
        )

        scheduled_hours = sum(
            float(order.routing_hours_total) * float(order.quantity_planned)
            for order in scheduled_orders
        )
        
        utilization_percent = (scheduled_hours / total_available * 100) if total_available > 0 else 0
        
        return Response({
            'work_center': work_center.name,
            'capacity_hours_per_day': float(work_center.capacity_hours),
            'efficiency_percent': float(work_center.efficiency),
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(),
            'days': days_in_range,
            'total_available_hours': round(total_available, 2),
            'scheduled_hours': round(scheduled_hours, 2),
            'available_hours': round(total_available - scheduled_hours, 2),
            'utilization_percent': round(utilization_percent, 2),
            'is_overloaded': scheduled_hours > total_available,
        })

    @action(detail=False, methods=['get'])
    def capacity_summary(self, request):
        """Get capacity summary for all work centers"""
        start_date = request.query_params.get('start_date', timezone.now().date().isoformat())
        end_date = request.query_params.get('end_date')
        
        from datetime import timedelta

        if end_date:
            end_date = timezone.datetime.strptime(end_date, '%Y-%m-%d').date()
        else:
            end_date = timezone.now().date() + timedelta(days=7)

        start_date_parsed = timezone.datetime.strptime(start_date, '%Y-%m-%d').date()
        days = (end_date - start_date_parsed).days + 1

        work_centers = WorkCenter.objects.filter(is_active=True).annotate(
            scheduled_count=Count(
                'productionorder',
                filter=Q(
                    productionorder__start_date__lte=end_date,
                    productionorder__end_date__gte=start_date_parsed,
                    productionorder__status__in=['Scheduled', 'In Progress'],
                )
            )
        )

        summary = []
        for wc in work_centers:
            total_hours = float(wc.capacity_hours) * days * (float(wc.efficiency) / 100)
            summary.append({
                'id': wc.id,
                'name': wc.name,
                'code': wc.code,
                'total_capacity_hours': round(total_hours, 2),
                'scheduled_orders': wc.scheduled_count,
                'available_hours': round(total_hours, 2),
            })
        
        return Response(summary)


class BillOfMaterialsViewSet(viewsets.ModelViewSet):
    queryset = BillOfMaterials.objects.all().prefetch_related('lines__component')
    serializer_class = BillOfMaterialsSerializer
    pagination_class = ProductionPagination
    permission_classes = [RBACPermission]
    filterset_fields = ['item_type', 'is_active']
    search_fields = ['item_code', 'item_name']


class BOMLineViewSet(viewsets.ModelViewSet):
    queryset = BOMLine.objects.all().select_related('bom', 'component')
    serializer_class = BOMLineSerializer
    pagination_class = ProductionPagination
    permission_classes = [RBACPermission]


class ProductionOrderViewSet(viewsets.ModelViewSet):
    queryset = ProductionOrder.objects.all().select_related(
        'bom', 'work_center'
    ).prefetch_related('job_cards', 'material_issues', 'material_receipts')
    serializer_class = ProductionOrderSerializer
    pagination_class = ProductionPagination
    permission_classes = [RBACPermission]
    filterset_fields = ['status', 'bom']
    search_fields = ['order_number']

    def perform_destroy(self, instance):
        if instance.status not in ('Draft', 'Scheduled'):
            raise ValidationError("Only draft or scheduled production orders can be deleted.")
        super().perform_destroy(instance)

    @action(detail=True, methods=['post'])
    def submit_for_approval(self, request, pk=None):
        """Submit Production Order for approval through the centralized workflow engine."""
        from workflow.views import auto_route_approval
        order = self.get_object()
        if order.status not in ['Draft', 'Rejected']:
            return Response(
                {"error": "Only Draft or Rejected production orders can be submitted."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = auto_route_approval(
            order, 'productionorder', request,
            title=f"PO-{order.order_number}: {order.bom.item_name}",
            amount=None,
        )

        if result.get('auto_approved'):
            order.status = 'Approved'
            msg = "Production Order auto-approved."
        else:
            order.status = 'Pending'
            msg = "Production Order submitted for approval."

        order.save()
        return Response({"status": msg, "approval_id": result.get('approval_id')})

    @action(detail=True, methods=['post'])
    def schedule(self, request, pk=None):
        """Schedule production order with work center capacity validation"""
        order = self.get_object()
        if order.status != 'Draft':
            return Response(
                {"error": "Only draft orders can be scheduled"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # P2FG-H5: Work Center Capacity Check
        work_center = order.work_center
        if not work_center:
            return Response(
                {"error": "Work center is required for scheduling"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        start_date = request.data.get('start_date')
        end_date = request.data.get('end_date')
        
        if not start_date:
            return Response(
                {"error": "start_date is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            from datetime import datetime
            start = datetime.strptime(start_date, '%Y-%m-%d').date()
            if end_date:
                end = datetime.strptime(end_date, '%Y-%m-%d').date()
            else:
                from datetime import timedelta
                end = start + timedelta(days=7)
        except ValueError:
            return Response(
                {"error": "Invalid date format. Use YYYY-MM-DD"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check work center capacity
        days = (end - start).days + 1
        available_hours = float(work_center.capacity_hours) * days
        efficiency = float(work_center.efficiency) / 100
        total_capacity = available_hours * efficiency
        
        # Calculate estimated hours for this order from BOM routing
        routing_hours = float(
            Routing.objects.filter(bom=order.bom).aggregate(
                total=Sum('time_hours')
            )['total'] or 0
        )
        estimated_hours = routing_hours * float(order.quantity_planned)

        # Check existing scheduled orders
        scheduled = ProductionOrder.objects.filter(
            work_center=work_center,
            start_date__lte=end,
            end_date__gte=start,
            status__in=['Scheduled', 'In Progress']
        ).exclude(pk=order.pk)

        scheduled_hours = 0
        for so in scheduled:
            so_routing_hours = float(
                Routing.objects.filter(bom=so.bom).aggregate(
                    total=Sum('time_hours')
                )['total'] or 0
            )
            scheduled_hours += so_routing_hours * float(so.quantity_planned)
        
        total_scheduled = scheduled_hours + estimated_hours
        
        if total_scheduled > total_capacity:
            return Response({
                "error": "Work center capacity exceeded",
                "details": {
                    "work_center": work_center.name,
                    "total_capacity_hours": round(total_capacity, 2),
                    "already_scheduled_hours": round(scheduled_hours, 2),
                    "this_order_hours": round(estimated_hours, 2),
                    "total_required_hours": round(total_scheduled, 2),
                    "overload_hours": round(total_scheduled - total_capacity, 2)
                }
            }, status=status.HTTP_400_BAD_REQUEST)
        
        with transaction.atomic():
            order.start_date = start
            order.end_date = end
            order.status = 'Scheduled'
            order.save()
        
        return Response({
            "status": "Production order scheduled",
            "order_number": order.order_number,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "work_center": work_center.name,
            "capacity_check": {
                "capacity_hours": round(total_capacity, 2),
                "scheduled_hours": round(total_scheduled, 2),
                "utilization": round((total_scheduled / total_capacity * 100) if total_capacity > 0 else 0, 2)
            }
        })

    @action(detail=True, methods=['post'])
    def start_production(self, request, pk=None):
        order = self.get_object()
        if order.status != 'Scheduled':
            return Response(
                {"error": "Only scheduled orders can be started"},
                status=status.HTTP_400_BAD_REQUEST
            )
        with transaction.atomic():
            order.status = 'In Progress'
            order.save()
        return Response(ProductionOrderSerializer(order).data)

    @action(detail=True, methods=['post'])
    def complete_production(self, request, pk=None):
        order = self.get_object()
        if order.status != 'In Progress':
            return Response(
                {"error": "Only in-progress orders can be completed"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # P2FG-H1: Quality Gate for FG - Only enforce if BOM requires it
        if order.bom.requires_quality_inspection:
            try:
                from quality.models import QualityInspection
                failed_inspection = QualityInspection.objects.filter(
                    production_order=order,
                    lines__result='Fail'
                ).distinct().exists()
                if failed_inspection:
                    return Response({
                        "error": "Cannot complete production: Quality inspection failed. Clear quality issues before completion.",
                        "production_order": order.order_number
                    }, status=status.HTTP_400_BAD_REQUEST)
            except ImportError as exc:
                logging.getLogger('dtsg').warning("Quality module unavailable, skipping quality gate for production order %s: %s", order.order_number, exc)

        quantity = request.data.get('quantity_produced')
        if not quantity:
            return Response(
                {"error": "quantity_produced is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        try:
            quantity = float(quantity)
            if quantity <= 0:
                raise ValueError()
        except (ValueError, TypeError):
            return Response(
                {"error": "quantity_produced must be a positive number"},
                status=status.HTTP_400_BAD_REQUEST
            )
        with transaction.atomic():
            order.quantity_produced = quantity
            order.status = 'Done'
            order.end_date = timezone.now().date()
            order.save()
        return Response(ProductionOrderSerializer(order).data)

    @action(detail=True, methods=['post'])
    def post_to_gl(self, request, pk=None):
        """Post production order to General Ledger"""
        from accounting.transaction_posting import TransactionPostingService
        from accounting.models import JournalHeader

        order = self.get_object()

        if order.status != 'Done':
            return Response({'error': 'Production order must be completed before posting to GL'}, status=status.HTTP_400_BAD_REQUEST)

        if JournalHeader.objects.filter(reference_number__startswith=f"MFG-{order.order_number}").exists():
            return Response({'error': 'Production order already posted to GL'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            journal = TransactionPostingService.post_production_order(order)
            return Response({
                'status': 'Posted to GL',
                'journal_number': journal.reference_number,
                'journal_id': journal.id
            })
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def create_quality_inspection(self, request, pk=None):
        """Create a quality inspection for this production order"""
        from quality.models import QualityInspection, InspectionLine

        order = self.get_object()

        with transaction.atomic():
            last = QualityInspection.objects.select_for_update().order_by('-id').first()
            next_num = (last.id + 1) if last else 1
            inspection_number = f"QI-PROD-{order.order_number}-{next_num:04d}"

            inspection = QualityInspection.objects.create(
                inspection_number=inspection_number,
                inspection_type='In-Process',
                reference_type='ProductionOrder',
                reference_number=order.order_number,
                inspection_date=timezone.now().date(),
                status='Pending',
                production_order=order,
                notes=request.data.get('notes', '')
            )

            lines = []
            for job_card in order.job_cards.all():
                lines.append(InspectionLine(
                    inspection=inspection,
                    parameter=f"Operation: {job_card.operation_name}",
                    specification=f"Planned: {job_card.time_planned} hours",
                    result='Pass'
                ))
            if lines:
                InspectionLine.objects.bulk_create(lines)

        return Response({
            'status': 'Quality inspection created',
            'inspection_id': inspection.id,
            'inspection_number': inspection.inspection_number
        })

    @action(detail=True, methods=['get'])
    def quality_inspection(self, request, pk=None):
        """Get quality inspection for this production order if exists"""
        order = self.get_object()
        inspection = order.quality_inspections.first()

        if not inspection:
            return Response({'error': 'No quality inspection found'}, status=status.HTTP_404_NOT_FOUND)

        from quality.serializers import QualityInspectionSerializer
        return Response(QualityInspectionSerializer(inspection).data)

    @action(detail=True, methods=['get'])
    def material_requirements(self, request, pk=None):
        order = self.get_object()
        bom = order.bom
        requirements = []
        for line in bom.lines.all().select_related('component'):
            required = line.total_quantity * order.quantity_planned
            requirements.append({
                'bom_line_id': line.id,
                'component_name': line.component.item_name,
                'component_code': line.component.item_code,
                'quantity_per_unit': float(line.quantity),
                'required_quantity': float(required),
                'unit': line.unit,
                'scrap_percentage': float(line.scrap_percentage or 0)
            })
        return Response(requirements)

    @action(detail=True, methods=['post'])
    def backflush_materials(self, request, pk=None):
        """Issue all remaining BOM materials in one click."""
        order = self.get_object()
        if order.status != 'In Progress':
            return Response(
                {"error": "Only in-progress orders can have materials backflushed"},
                status=status.HTTP_400_BAD_REQUEST
            )

        warehouse_id = request.data.get('warehouse')
        if not warehouse_id:
            return Response(
                {"error": "warehouse is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        from inventory.models import Item, ItemStock, StockMovement
        from django.db.models import Sum, F as _F

        issued_count = 0
        total_qty_issued = Decimal('0')
        skipped = []
        gl_failures = []

        with transaction.atomic():
            for bom_line in order.bom.lines.select_related('component').all():
                required = bom_line.total_quantity * order.quantity_planned
                already_issued = order.material_issues.filter(
                    bom_line=bom_line
                ).aggregate(total=Sum('quantity_issued'))['total'] or Decimal('0')
                remaining = required - already_issued

                if remaining <= 0:
                    continue

                # Find inventory item linked to this BOM component
                inv_item = Item.objects.filter(production_bom=bom_line.component).first()
                if not inv_item:
                    skipped.append({
                        'component': bom_line.component.item_code,
                        'reason': 'No inventory item linked to BOM component'
                    })
                    continue

                # Check stock availability
                stock = ItemStock.objects.filter(
                    item=inv_item, warehouse_id=warehouse_id
                ).first()
                if not stock or stock.available_quantity < remaining:
                    available = stock.available_quantity if stock else Decimal('0')
                    skipped.append({
                        'component': bom_line.component.item_code,
                        'reason': f'Insufficient stock: need {remaining}, available {available}'
                    })
                    continue

                # Create material issue
                issue = MaterialIssue.objects.create(
                    production_order=order,
                    bom_line=bom_line,
                    quantity_issued=remaining,
                    issue_date=timezone.now().date(),
                    notes=f'Backflush issue for {bom_line.component.item_name}'
                )

                # Each component is processed in its own inner savepoint so that a GL
                # posting failure rolls back only that line's stock changes without
                # aborting the entire backflush (other components still get issued).
                try:
                    with transaction.atomic():
                        # DOUBLE-UPDATE FIX: instance pattern + _skip_stock_update suppresses
                        # the post_save signal so the explicit F()-update below is the sole write.
                        _bf_movement = StockMovement(
                            item=inv_item,
                            warehouse_id=warehouse_id,
                            movement_type='OUT',
                            quantity=remaining,
                            unit_price=bom_line.component.standard_cost,
                            cost_method=inv_item.valuation_method or 'WA',
                            reference_number=f"BF-{order.order_number}-{issue.id}",
                            remarks=f"Backflush: {bom_line.component.item_name} for {order.order_number}",
                        )
                        _bf_movement._skip_stock_update = True
                        _bf_movement.save()
                        ItemStock.objects.filter(
                            item=inv_item, warehouse_id=warehouse_id
                        ).update(quantity=_F('quantity') - remaining)
                        inv_item.recalculate_stock_values()

                        # Post to GL — inside the savepoint so failure rolls back stock too
                        from accounting.transaction_posting import TransactionPostingService
                        TransactionPostingService.post_material_issue(issue)

                except Exception as e:
                    # Roll back this component's stock changes and record the failure.
                    # The outer transaction.atomic() is still intact; only this savepoint
                    # was aborted.  Other components continue to be processed.
                    gl_failures.append({
                        'component': bom_line.component.item_code,
                        'error': str(e)
                    })
                    continue

                issued_count += 1
                total_qty_issued += remaining

        return Response({
            'issued_count': issued_count,
            'total_quantity_issued': str(total_qty_issued),
            'skipped': skipped,
            'gl_failures': gl_failures,
        })


class MaterialIssueViewSet(viewsets.ModelViewSet):
    queryset = MaterialIssue.objects.all().select_related(
        'production_order', 'bom_line', 'bom_line__component'
    )
    serializer_class = MaterialIssueSerializer
    pagination_class = ProductionPagination
    permission_classes = [RBACPermission]
    filterset_fields = ['production_order']
    search_fields = ['production_order__order_number']

    def perform_destroy(self, instance):
        from accounting.models import JournalHeader
        if JournalHeader.objects.filter(reference_number=f"MI-{instance.id}").exists():
            raise ValidationError("Cannot delete a material issue that has been posted to GL.")
        super().perform_destroy(instance)

    @action(detail=True, methods=['post'])
    def post_to_gl(self, request, pk=None):
        """Post material issue to General Ledger and update inventory"""
        from accounting.transaction_posting import TransactionPostingService
        from accounting.models import JournalHeader

        material_issue = self.get_object()

        if JournalHeader.objects.filter(reference_number=f"MI-{material_issue.id}").exists():
            return Response({'error': 'Material issue already posted to GL'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                journal = TransactionPostingService.post_material_issue(material_issue)

                from inventory.models import StockMovement, ItemStock, Warehouse
                from django.db.models import F

                warehouse = Warehouse.objects.filter(is_active=True).first()
                if not warehouse:
                    raise ValidationError('No active warehouse found')

                from inventory.models import Item
                component_bom = material_issue.bom_line.component
                inv_item = Item.objects.filter(production_bom=component_bom).first()
                if not inv_item:
                    raise ValidationError("No inventory item linked to this BOM component")
                quantity = material_issue.quantity_issued

                # DOUBLE-UPDATE FIX: instance pattern + _skip_stock_update suppresses
                # the post_save signal so the explicit F()-update below is the sole write.
                stock_movement = StockMovement(
                    item=inv_item,
                    warehouse=warehouse,
                    movement_type='OUT',
                    quantity=quantity,
                    unit_price=inv_item.standard_cost or 0,
                    reference_number=f"MI-{material_issue.id}",
                    remarks=f"Material Issue for Production: {material_issue.production_order.order_number}"
                )
                stock_movement._skip_stock_update = True
                stock_movement.save()

                ItemStock.objects.update_or_create(item=inv_item, warehouse=warehouse, defaults={})
                ItemStock.objects.filter(
                    item=inv_item, warehouse=warehouse
                ).update(quantity=F('quantity') - quantity)
                inv_item.recalculate_stock_values()

            return Response({
                'status': 'Posted to GL and Inventory updated',
                'journal_number': journal.reference_number,
                'journal_id': journal.id,
                'stock_movement_id': stock_movement.id
            })
        except ValidationError:
            raise
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class MaterialReceiptViewSet(viewsets.ModelViewSet):
    queryset = MaterialReceipt.objects.all().select_related('production_order')
    serializer_class = MaterialReceiptSerializer
    pagination_class = ProductionPagination
    permission_classes = [RBACPermission]
    filterset_fields = ['production_order']
    search_fields = ['production_order__order_number']

    def perform_destroy(self, instance):
        from accounting.models import JournalHeader
        ref = f"MFG-{instance.production_order.order_number}"
        if JournalHeader.objects.filter(reference_number=ref).exists():
            raise ValidationError("Cannot delete a material receipt that has been posted to GL.")
        super().perform_destroy(instance)

    @action(detail=True, methods=['post'])
    def post_to_gl(self, request, pk=None):
        """Post finished goods receipt to GL and inventory"""
        from accounting.transaction_posting import TransactionPostingService
        from accounting.models import JournalHeader
        from inventory.models import StockMovement, ItemStock, ItemBatch, Warehouse

        material_receipt = self.get_object()

        ref = f"MFG-{material_receipt.production_order.order_number}"
        if JournalHeader.objects.filter(reference_number=ref).exists():
            return Response({'error': 'Material receipt already posted to GL'}, status=status.HTTP_400_BAD_REQUEST)

        warehouse = Warehouse.objects.filter(is_active=True).first()
        if not warehouse:
            return Response({'error': 'No active warehouse found'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                journal = TransactionPostingService.post_material_receipt(material_receipt)

                from django.db.models import F

                from inventory.models import Item
                production_order = material_receipt.production_order
                inv_item = Item.objects.filter(production_bom=production_order.bom).first()
                if not inv_item:
                    raise ValidationError("No inventory item linked to this BOM")
                quantity = material_receipt.quantity_received

                # DOUBLE-UPDATE FIX: instance pattern + _skip_stock_update suppresses
                # the post_save signal so the explicit F()-update below is the sole write.
                # Also fixed total_value expression: (F('quantity') + quantity) would have
                # been evaluated BEFORE the quantity update, causing (old+2*qty)*cost overcount.
                # recalculate_stock_values() re-derives totals from the source of truth instead.
                stock_movement = StockMovement(
                    item=inv_item,
                    warehouse=warehouse,
                    movement_type='IN',
                    quantity=quantity,
                    unit_price=inv_item.standard_cost or 0,
                    reference_number=ref,
                    remarks=f"Production Receipt: {production_order.order_number}"
                )
                stock_movement._skip_stock_update = True
                stock_movement.save()

                ItemStock.objects.update_or_create(item=inv_item, warehouse=warehouse, defaults={})
                ItemStock.objects.filter(
                    item=inv_item, warehouse=warehouse
                ).update(quantity=F('quantity') + quantity)
                inv_item.recalculate_stock_values()

                if quantity > 0:
                    ItemBatch.objects.create(
                        item=inv_item,
                        warehouse=warehouse,
                        batch_number=f"BATCH-{production_order.order_number}",
                        quantity=quantity,
                        unit_cost=inv_item.standard_cost or 0,
                        reference_number=production_order.order_number,
                        receipt_date=timezone.now().date()
                    )

                # P2FG-M3: Scrap GL Tracking - post scrap losses to GL
                if material_receipt.is_scrap and material_receipt.scrap_quantity > 0:
                    scrap_cost = (material_receipt.scrap_quantity * (inv_item.standard_cost or 0))
                    if scrap_cost > 0:
                        scrap_account = getattr(inv_item, 'expense_account', None)
                        if not scrap_account:
                            from accounting.transaction_posting import get_gl_account
                            scrap_account = get_gl_account('SCRAP_LOSS', 'Expense', 'Loss')
                        
                        if scrap_account:
                            scrap_journal = JournalHeader.objects.create(
                                posting_date=material_receipt.receipt_date,
                                description=f"Scrap Loss: {production_order.order_number}",
                                reference_number=f"SCRAP-{production_order.order_number}",
                                mda=getattr(production_order, 'mda', None),
                                fund=getattr(production_order, 'fund', None),
                                status='Posted'
                            )
                            JournalLine.objects.create(
                                header=scrap_journal,
                                account=scrap_account,
                                debit=scrap_cost,
                                credit=Decimal('0.00'),
                                memo=f"Scrap loss: {material_receipt.scrap_quantity} units"
                            )
                            inventory_account = getattr(inv_item, 'inventory_account', None)
                            if inventory_account:
                                JournalLine.objects.create(
                                    header=scrap_journal,
                                    account=inventory_account,
                                    debit=Decimal('0.00'),
                                    credit=scrap_cost,
                                    memo=f"Reduce inventory for scrap"
                                )

            return Response({
                'status': 'Posted to GL and inventory updated',
                'journal_number': journal.reference_number,
                'journal_id': journal.id,
                'stock_movement_id': stock_movement.id,
                'quantity_received': float(quantity)
            })
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class JobCardViewSet(viewsets.ModelViewSet):
    queryset = JobCard.objects.all().select_related('production_order', 'work_center', 'operator__user')
    serializer_class = JobCardSerializer
    pagination_class = ProductionPagination
    permission_classes = [RBACPermission]
    filterset_fields = ['production_order', 'status']
    search_fields = ['operation_name', 'production_order__order_number']

    @action(detail=True, methods=['post'])
    def start_operation(self, request, pk=None):
        job = self.get_object()
        if job.status != 'Pending':
            return Response(
                {"error": "Only pending jobs can be started"},
                status=status.HTTP_400_BAD_REQUEST
            )
        with transaction.atomic():
            job.status = 'In Progress'
            job.save()
        return Response(JobCardSerializer(job).data)

    @action(detail=True, methods=['post'])
    def complete_operation(self, request, pk=None):
        self.get_object()  # permission check
        time_actual = request.data.get('time_actual')
        labor_cost = request.data.get('labor_cost')

        if time_actual is not None:
            try:
                time_actual = float(time_actual)
                if time_actual < 0:
                    raise ValueError()
            except (ValueError, TypeError):
                return Response(
                    {"error": "time_actual must be a non-negative number"},
                    status=status.HTTP_400_BAD_REQUEST
                )

        if labor_cost is not None:
            try:
                labor_cost = float(labor_cost)
                if labor_cost < 0:
                    raise ValueError()
            except (ValueError, TypeError):
                return Response(
                    {"error": "labor_cost must be a non-negative number"},
                    status=status.HTTP_400_BAD_REQUEST
                )

        with transaction.atomic():
            job = JobCard.objects.select_for_update().get(pk=self.kwargs['pk'])
            if job.status != 'In Progress':
                return Response(
                    {"error": "Only in-progress jobs can be completed"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            if time_actual is not None:
                job.time_actual = time_actual
            if labor_cost is not None:
                job.labor_cost = labor_cost
            job.status = 'Done'
            job.save()
        return Response(JobCardSerializer(job).data)


class RoutingViewSet(viewsets.ModelViewSet):
    queryset = Routing.objects.all().select_related('bom', 'work_center')
    serializer_class = RoutingSerializer
    pagination_class = ProductionPagination
    permission_classes = [RBACPermission]
    filterset_fields = ['bom']
    search_fields = ['bom__item_code', 'bom__item_name']
