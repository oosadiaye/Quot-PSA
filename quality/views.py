import logging

from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination

from django.db import transaction
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Avg
from core.permissions import RBACPermission
from .models import (
    QualityInspection, InspectionLine, NonConformance, CustomerComplaint,
    QualityChecklist, QualityChecklistLine, CalibrationRecord, SupplierQuality,
    QAConfiguration
)
from .serializers import (
    QualityInspectionSerializer, InspectionLineSerializer,
    NonConformanceSerializer, CustomerComplaintSerializer,
    QualityChecklistSerializer, QualityChecklistLineSerializer,
    CalibrationRecordSerializer, SupplierQualitySerializer,
    QAConfigurationSerializer
)

logger = logging.getLogger(__name__)


class QualityPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class QualityInspectionViewSet(viewsets.ModelViewSet):
    queryset = QualityInspection.objects.all().select_related(
        'inspector', 'goods_received_note', 'production_order', 'item'
    ).prefetch_related('lines')
    serializer_class = QualityInspectionSerializer
    pagination_class = QualityPagination
    permission_classes = [RBACPermission]
    filterset_fields = ['inspection_type', 'status', 'inspection_date']
    search_fields = ['inspection_number', 'reference_number', 'notes']

    def perform_destroy(self, instance):
        if instance.status != 'Pending':
            raise ValidationError("Only pending inspections can be deleted.")
        super().perform_destroy(instance)

    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        inspection = self.get_object()
        with transaction.atomic():
            inspection.status = 'Completed'
            inspection.save()
        return Response(QualityInspectionSerializer(inspection).data)

    @action(detail=True, methods=['post'])
    def post_to_gl(self, request, pk=None):
        """Post quality inspection to General Ledger"""
        from accounting.transaction_posting import TransactionPostingService
        from accounting.models import JournalHeader

        inspection = self.get_object()

        if inspection.status != 'Completed':
            return Response({'error': 'Inspection must be completed before posting to GL'}, status=status.HTTP_400_BAD_REQUEST)

        if JournalHeader.objects.filter(reference_number__startswith=f"QC-{inspection.inspection_number}").exists():
            return Response({'error': 'Inspection already posted to GL'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            journal = TransactionPostingService.post_quality_inspection(inspection)
            return Response({
                'status': 'Posted to GL',
                'journal_number': journal.reference_number,
                'journal_id': journal.id
            })
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def accept_grn(self, request, pk=None):
        """Accept GRN after quality inspection passed"""
        inspection = self.get_object()

        if inspection.inspection_type != 'Incoming':
            return Response({'error': 'This action is only for incoming inspections'}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            if inspection.goods_received_note:
                grn = inspection.goods_received_note
                if grn.status != 'Posted':
                    grn.status = 'Posted'
                    grn.save()

                    from accounting.transaction_posting import TransactionPostingService
                    try:
                        TransactionPostingService.post_goods_received_note(grn)
                    except Exception as e:
                        logger.error(f"Failed to post GRN {grn.grn_number} to GL: {e}")
                        raise

            inspection.status = 'Passed'
            inspection.save()

        return Response({'status': 'GRN accepted and posted to inventory'})

    @action(detail=True, methods=['post'])
    def reject_grn(self, request, pk=None):
        """Reject GRN items after quality inspection failed"""
        inspection = self.get_object()

        if inspection.inspection_type != 'Incoming':
            return Response({'error': 'This action is only for incoming inspections'}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            ncr = None
            if inspection.goods_received_note:
                grn = inspection.goods_received_note

                failed_items = inspection.lines.filter(result='Fail').count()

                ncr = NonConformance.objects.create(
                    ncr_number=f"NCR-GRN-{grn.grn_number}",
                    title=f"Quality Rejection - GRN {grn.grn_number}",
                    description=f"{failed_items} items failed quality inspection",
                    severity='Major',
                    status='Open',
                    related_inspection=inspection,
                    source_type='Procurement',
                    source_id=grn.id,
                    notes=request.data.get('notes', '')
                )

            inspection.status = 'Failed'
            inspection.save()

        return Response({
            'status': 'GRN rejected',
            'ncr_number': ncr.ncr_number if ncr else None
        })

    @action(detail=True, methods=['post'])
    def add_line(self, request, pk=None):
        inspection = self.get_object()
        serializer = InspectionLineSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(inspection=inspection)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['get'])
    def lines(self, request, pk=None):
        inspection = self.get_object()
        lines = inspection.lines.all()
        serializer = InspectionLineSerializer(lines, many=True)
        return Response(serializer.data)


class InspectionLineViewSet(viewsets.ModelViewSet):
    queryset = InspectionLine.objects.all().select_related('inspection')
    serializer_class = InspectionLineSerializer
    pagination_class = QualityPagination
    permission_classes = [RBACPermission]
    filterset_fields = ['result', 'inspection']


class NonConformanceViewSet(viewsets.ModelViewSet):
    queryset = NonConformance.objects.all().select_related('related_inspection', 'assigned_to')
    serializer_class = NonConformanceSerializer
    pagination_class = QualityPagination
    permission_classes = [RBACPermission]
    filterset_fields = ['severity', 'status']
    search_fields = ['ncr_number', 'title', 'description']

    def perform_destroy(self, instance):
        if instance.status != 'Open':
            raise ValidationError("Only open NCRs can be deleted.")
        super().perform_destroy(instance)

    @action(detail=True, methods=['post'])
    def close(self, request, pk=None):
        ncr = self.get_object()
        with transaction.atomic():
            ncr.status = 'Closed'
            ncr.closed_date = request.data.get('closed_date')
            ncr.save()
        serializer = self.get_serializer(ncr)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def post_to_gl(self, request, pk=None):
        """Post non-conformance to General Ledger"""
        from accounting.transaction_posting import TransactionPostingService
        from accounting.models import JournalHeader

        ncr = self.get_object()

        if ncr.status != 'Closed':
            return Response({'error': 'NCR must be closed before posting to GL'}, status=status.HTTP_400_BAD_REQUEST)

        if JournalHeader.objects.filter(reference_number__startswith=f"NCR-{ncr.ncr_number}").exists():
            return Response({'error': 'NCR already posted to GL'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            journal = TransactionPostingService.post_non_conformance(ncr)
            if journal is None:
                return Response({'warning': 'No cost calculable from related inspection, GL posting skipped'})
            return Response({
                'status': 'Posted to GL',
                'journal_number': journal.reference_number,
                'journal_id': journal.id
            })
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class CustomerComplaintViewSet(viewsets.ModelViewSet):
    queryset = CustomerComplaint.objects.all().select_related('related_ncr', 'related_sales_order')
    serializer_class = CustomerComplaintSerializer
    pagination_class = QualityPagination
    permission_classes = [RBACPermission]
    filterset_fields = ['status']
    search_fields = ['complaint_number', 'customer_name', 'subject']


class QualityChecklistViewSet(viewsets.ModelViewSet):
    queryset = QualityChecklist.objects.all().prefetch_related('lines')
    serializer_class = QualityChecklistSerializer
    pagination_class = QualityPagination
    permission_classes = [RBACPermission]
    filterset_fields = ['checklist_type', 'is_active']
    search_fields = ['name', 'description']


class QualityChecklistLineViewSet(viewsets.ModelViewSet):
    queryset = QualityChecklistLine.objects.all().select_related('checklist')
    serializer_class = QualityChecklistLineSerializer
    pagination_class = QualityPagination
    permission_classes = [RBACPermission]
    filterset_fields = ['checklist', 'is_critical']


class CalibrationRecordViewSet(viewsets.ModelViewSet):
    queryset = CalibrationRecord.objects.all()
    serializer_class = CalibrationRecordSerializer
    pagination_class = QualityPagination
    permission_classes = [RBACPermission]
    filterset_fields = ['equipment_type', 'status']
    search_fields = ['equipment_name', 'equipment_code']

    @action(detail=True, methods=['post'])
    def calibrate(self, request, pk=None):
        from django.utils import timezone
        from dateutil.relativedelta import relativedelta

        record = self.get_object()
        with transaction.atomic():
            record.last_calibration_date = timezone.now().date()
            interval = record.calibration_interval_months
            record.next_calibration_date = record.last_calibration_date + relativedelta(months=interval)
            record.status = 'Calibrated'
            record.save()
        serializer = self.get_serializer(record)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def due_overdue(self, request):
        from django.utils import timezone
        from django.db.models import Q
        today = timezone.now().date()
        records = CalibrationRecord.objects.filter(
            Q(next_calibration_date__lte=today) | Q(status='Due')
        )
        serializer = self.get_serializer(records, many=True)
        return Response(serializer.data)


class SupplierQualityViewSet(viewsets.ModelViewSet):
    queryset = SupplierQuality.objects.all().select_related('vendor')
    serializer_class = SupplierQualitySerializer
    pagination_class = QualityPagination
    permission_classes = [RBACPermission]
    filterset_fields = ['rating']
    search_fields = ['vendor__name', 'comments']

    def perform_create(self, serializer):
        quality_score = serializer.validated_data.get('quality_score', 0)
        delivery_score = serializer.validated_data.get('delivery_score', 0)
        overall = (quality_score + delivery_score) / 2
        serializer.save(overall_score=overall)

    def perform_update(self, serializer):
        quality_score = serializer.validated_data.get('quality_score', 0)
        delivery_score = serializer.validated_data.get('delivery_score', 0)
        overall = (quality_score + delivery_score) / 2
        serializer.save(overall_score=overall)

    @action(detail=False, methods=['get'])
    def by_vendor(self, request):
        vendor_id = request.query_params.get('vendor')
        if vendor_id:
            records = SupplierQuality.objects.filter(vendor_id=vendor_id).select_related('vendor')
        else:
            records = SupplierQuality.objects.all().select_related('vendor')
        serializer = self.get_serializer(records, many=True)
        return Response(serializer.data)


class QAConfigurationViewSet(viewsets.ModelViewSet):
    """ViewSet for QA inspection configuration"""
    queryset = QAConfiguration.objects.all()
    serializer_class = QAConfigurationSerializer
    pagination_class = QualityPagination
    permission_classes = [RBACPermission]
    filterset_fields = ['trigger_event', 'inspection_type', 'is_active']
    search_fields = ['name']
    
    @action(detail=False, methods=['post'])
    def create_from_grn(self, request):
        """Manually create QA inspection from GRN"""
        from django.utils import timezone
        from procurement.models import GoodsReceivedNote
        
        grn_id = request.data.get('grn_id')
        
        if not grn_id:
            return Response({'error': 'grn_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            grn = GoodsReceivedNote.objects.get(pk=grn_id)
        except GoodsReceivedNote.DoesNotExist:
            return Response({'error': 'GRN not found'}, status=status.HTTP_404_NOT_FOUND)
        
        # Check if inspection already exists
        if QualityInspection.objects.filter(goods_received_note=grn).exists():
            return Response({'error': 'Inspection already exists for this GRN'}, status=status.HTTP_400_BAD_REQUEST)
        
        with transaction.atomic():
            last = QualityInspection.objects.select_for_update().order_by('-id').first()
            # Parse max sequence from existing QI numbers to handle ID gaps after deletions
            import re as _re
            max_num = 0
            for qi_num in QualityInspection.objects.values_list('inspection_number', flat=True):
                m = _re.search(r'-(\d+)$', qi_num)
                if m:
                    max_num = max(max_num, int(m.group(1)))
            next_num = max_num + 1 if max_num > 0 else ((last.id + 1) if last else 1)
            inspection_number = f"QI-GRN-{grn.grn_number}-{next_num:04d}"
            
            inspection = QualityInspection.objects.create(
                inspection_number=inspection_number,
                inspection_type='Incoming',
                reference_type='GRN',
                reference_number=grn.grn_number,
                inspection_date=timezone.now().date(),
                status='Pending',
                goods_received_note=grn,
                notes=request.data.get('notes', '')
            )
        
        return Response({
            'status': 'Inspection created',
            'inspection_id': inspection.id,
            'inspection_number': inspection.inspection_number
        })
    
    @action(detail=False, methods=['post'])
    def create_from_production(self, request):
        """Manually create QA inspection from Production Order"""
        from django.utils import timezone
        from production.models import ProductionOrder
        
        production_id = request.data.get('production_id')
        
        if not production_id:
            return Response({'error': 'production_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            production = ProductionOrder.objects.get(pk=production_id)
        except ProductionOrder.DoesNotExist:
            return Response({'error': 'Production order not found'}, status=status.HTTP_404_NOT_FOUND)
        
        if QualityInspection.objects.filter(production_order=production).exists():
            return Response({'error': 'Inspection already exists for this Production Order'}, status=status.HTTP_400_BAD_REQUEST)
        
        with transaction.atomic():
            last = QualityInspection.objects.select_for_update().order_by('-id').first()
            next_num = (last.id + 1) if last else 1
            inspection_number = f"QI-PROD-{production.order_number}-{next_num:04d}"
            
            inspection = QualityInspection.objects.create(
                inspection_number=inspection_number,
                inspection_type='Final',
                reference_type='ProductionOrder',
                reference_number=production.order_number,
                inspection_date=timezone.now().date(),
                status='Pending',
                production_order=production,
                notes=request.data.get('notes', '')
            )
        
        return Response({
            'status': 'Inspection created',
            'inspection_id': inspection.id,
            'inspection_number': inspection.inspection_number
        })
    
    @action(detail=False, methods=['get'])
    def by_trigger(self, request):
        """Get QA configurations by trigger event"""
        trigger = request.query_params.get('trigger')
        
        if not trigger:
            return Response({'error': 'trigger is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        configs = QAConfiguration.objects.filter(
            trigger_event=trigger,
            is_active=True
        )
        
        serializer = self.get_serializer(configs, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def metrics(self, request):
        """REP-L1: Quality Metrics Report - Get pass/fail rates and trends"""
        from datetime import datetime, timedelta
        from .reports import QualityMetricsService
        
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')
        inspection_type = request.query_params.get('type')
        
        if date_from:
            date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
        if date_to:
            date_to = datetime.strptime(date_to, '%Y-%m-%d').date()
        
        pass_fail = QualityMetricsService.get_pass_fail_rate(
            date_from=date_from,
            date_to=date_to,
            inspection_type=inspection_type
        )
        
        ncr_summary = QualityMetricsService.get_ncr_summary(
            date_from=date_from,
            date_to=date_to
        )
        
        trend = QualityMetricsService.get_inspection_trend(months=6)
        
        return Response({
            'pass_fail_rate': pass_fail,
            'ncr_summary': ncr_summary,
            'monthly_trend': trend,
        })
