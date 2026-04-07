from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination

from django.utils import timezone
from django.db.models import Count, Avg, Sum, Q, Case, When, IntegerField
from datetime import timedelta
from .models import ServiceAsset, Technician, ServiceTicket, MaintenanceSchedule, WorkOrder, WorkOrderMaterial, CitizenRequest, ServiceMetric
from .serializers import ServiceAssetSerializer, TechnicianSerializer, ServiceTicketSerializer, MaintenanceScheduleSerializer, WorkOrderSerializer, WorkOrderMaterialSerializer, CitizenRequestSerializer, ServiceMetricSerializer
class ServicePagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100
class ServiceAssetViewSet(viewsets.ModelViewSet):
    queryset = ServiceAsset.objects.all()
    serializer_class = ServiceAssetSerializer
    search_fields = ['name', 'serial_number']
    pagination_class = ServicePagination

class TechnicianViewSet(viewsets.ModelViewSet):
    queryset = Technician.objects.all().select_related('employee__user')
    serializer_class = TechnicianSerializer
    filterset_fields = ['is_active', 'is_available', 'specialization']
    search_fields = ['name', 'employee_code']
    pagination_class = ServicePagination

class ServiceTicketViewSet(viewsets.ModelViewSet):
    queryset = ServiceTicket.objects.all().select_related('asset', 'technician').prefetch_related('sla')
    serializer_class = ServiceTicketSerializer
    filterset_fields = ['status', 'priority', 'asset', 'technician']
    pagination_class = ServicePagination

    @action(detail=True, methods=['post'])
    def resolve_ticket(self, request, pk=None):
        ticket = self.get_object()
        if ticket.status == 'Resolved':
            return Response({"error": "Ticket is already resolved."}, status=status.HTTP_400_BAD_REQUEST)

        ticket.status = 'Resolved'
        ticket.save()

        # Auto-check SLA on resolve
        if hasattr(ticket, 'sla'):
            ticket.sla.check_sla()

        return Response({"status": f"Ticket {ticket.ticket_number} marked as Resolved."})

    @action(detail=True, methods=['post'])
    def post_to_gl(self, request, pk=None):
        """Post a resolved/closed service ticket to the General Ledger.

        Journal entry (post_service_ticket):
            DR  Accounts Receivable  (service revenue billable to customer)
            CR  Service Revenue
        """
        from accounting.transaction_posting import TransactionPostingService

        ticket = self.get_object()

        if ticket.status not in ['Resolved', 'Closed']:
            return Response(
                {'error': 'Ticket must be Resolved or Closed before posting to GL'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            journal = TransactionPostingService.post_service_ticket(ticket)
            return Response({
                'status': 'Posted to GL',
                'journal_number': journal.reference_number,
                'journal_id': journal.id,
            })
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def assign_technician(self, request, pk=None):
        ticket = self.get_object()
        technician_id = request.data.get('technician_id')

        if not technician_id:
            return Response({"error": "technician_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        ticket.technician_id = technician_id
        ticket.status = 'In Progress'
        ticket.save()

        # Auto-set first_response_at for SLA tracking
        if hasattr(ticket, 'sla') and not ticket.sla.first_response_at:
            ticket.sla.first_response_at = timezone.now()
            ticket.sla.save()

        return Response({"status": f"Ticket assigned to technician"})

    @action(detail=False, methods=['get'])
    def unassigned(self, request):
        tickets = ServiceTicket.objects.filter(technician__isnull=True, status='Open')
        serializer = self.get_serializer(tickets, many=True)
        return Response(serializer.data)

class MaintenanceScheduleViewSet(viewsets.ModelViewSet):
    queryset = MaintenanceSchedule.objects.all().select_related('asset')
    serializer_class = MaintenanceScheduleSerializer
    filterset_fields = ['asset', 'frequency', 'is_active']

    @action(detail=True, methods=['post'])
    def generate_ticket(self, request, pk=None):
        schedule = self.get_object()
        ticket = schedule.generate_ticket()
        return Response({"status": "Maintenance ticket created", "ticket_id": ticket.id})
class WorkOrderViewSet(viewsets.ModelViewSet):
    queryset = WorkOrder.objects.all().select_related('asset', 'technician').prefetch_related('materials')
    serializer_class = WorkOrderSerializer
    filterset_fields = ['status', 'priority', 'asset', 'technician']
    search_fields = ['work_order_number', 'title']
    pagination_class = ServicePagination

    @action(detail=True, methods=['post'])
    def add_material(self, request, pk=None):
        work_order = self.get_object()
        serializer = WorkOrderMaterialSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(work_order=work_order)
            work_order.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        work_order = self.get_object()
        work_order.status = 'Completed'
        work_order.completed_date = timezone.now().date()
        work_order.save()
        return Response({"status": f"Work order {work_order.work_order_number} completed"})

    @action(detail=True, methods=['post'])
    def post_to_gl(self, request, pk=None):
        """Post work order to General Ledger"""
        from accounting.transaction_posting import TransactionPostingService
        
        work_order = self.get_object()
        
        if work_order.status != 'Completed':
            return Response({'error': 'Work order must be completed before posting to GL'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            journal = TransactionPostingService.post_work_order(work_order)
            return Response({
                'status': 'Posted to GL',
                'journal_number': journal.reference_number,
                'journal_id': journal.id
            })
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'])
    def pending(self, request):
        work_orders = WorkOrder.objects.filter(status='Pending')
        serializer = self.get_serializer(work_orders, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def create_purchase_request(self, request, pk=None):
        """Create a purchase request from work order materials."""
        try:
            from procurement.models import PurchaseRequest, PurchaseRequestLine, Fund, Function, Program, Geo
            from django.db import transaction as db_transaction

            work_order = self.get_object()
            materials = work_order.materials.all()

            if not materials:
                return Response({"error": "No materials to procure"}, status=status.HTTP_400_BAD_REQUEST)

            fund_id = request.data.get('fund')
            function_id = request.data.get('function')
            program_id = request.data.get('program')
            geo_id = request.data.get('geo')

            if not all([fund_id, function_id, program_id, geo_id]):
                return Response({"error": "fund, function, program, geo are required"}, status=status.HTTP_400_BAD_REQUEST)

            account_id = request.data.get('account')
            if not account_id:
                return Response({"error": "account is required"}, status=status.HTTP_400_BAD_REQUEST)

            with db_transaction.atomic():
                last_pr = PurchaseRequest.objects.select_for_update().order_by('-id').first()
                next_num = (last_pr.id + 1) if last_pr else 1
                pr_number = f"PR-WO-{timezone.now().strftime('%Y%m%d')}-{next_num:05d}"

            pr = PurchaseRequest.objects.create(
                request_number=pr_number,
                description=f"Materials for Work Order: {work_order.work_order_number} - {work_order.title}",
                fund_id=fund_id,
                function_id=function_id,
                program_id=program_id,
                geo_id=geo_id,
                status='Draft'
            )
            
            for material in materials:
                PurchaseRequestLine.objects.create(
                    request=pr,
                    item_description=material.item_description,
                    quantity=material.quantity,
                    estimated_unit_price=material.unit_price,
                    account_id=account_id
                )
            
            return Response({"status": "Purchase request created", "pr_id": pr.id, "pr_number": pr.request_number})
        except ImportError:
            return Response({"error": "Procurement module not available"}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def create_journal_entry(self, request, pk=None):
        """Create a journal entry for work order costs."""
        try:
            from accounting.models import JournalHeader, JournalLine
            from django.db import transaction as db_transaction

            work_order = self.get_object()

            if work_order.total_cost <= 0:
                return Response({"error": "No costs to record"}, status=status.HTTP_400_BAD_REQUEST)

            debit_account = request.data.get('debit_account')
            credit_account = request.data.get('credit_account')
            if not debit_account or not credit_account:
                return Response({"error": "debit_account and credit_account are required"}, status=status.HTTP_400_BAD_REQUEST)
            if debit_account == credit_account:
                return Response({"error": "debit_account and credit_account must be different"}, status=status.HTTP_400_BAD_REQUEST)

            with db_transaction.atomic():
                last_je = JournalHeader.objects.select_for_update().order_by('-id').first()
                next_num = (last_je.id + 1) if last_je else 1
                je_number = f"JE-WO-{timezone.now().strftime('%Y%m%d')}-{next_num:05d}"

            journal = JournalHeader.objects.create(
                reference_number=je_number,
                description=f"Costs for Work Order: {work_order.work_order_number} - {work_order.title}",
                posting_date=timezone.now().date(),
                status='Draft'
            )

            JournalLine.objects.create(
                header=journal,
                account_id=debit_account,
                debit=work_order.total_cost,
                credit=0,
                memo="Work Order Costs"
            )

            JournalLine.objects.create(
                header=journal,
                account_id=credit_account,
                debit=0,
                credit=work_order.total_cost,
                memo="Work Order Costs"
            )

            return Response({"status": "Journal entry created", "journal_id": journal.id, "journal_number": journal.reference_number})
        except ImportError:
            return Response({"error": "Accounting module not available"}, status=status.HTTP_400_BAD_REQUEST)
class WorkOrderMaterialViewSet(viewsets.ModelViewSet):
    queryset = WorkOrderMaterial.objects.all()
    serializer_class = WorkOrderMaterialSerializer
    filterset_fields = ['work_order']
    pagination_class = ServicePagination
class CitizenRequestViewSet(viewsets.ModelViewSet):
    queryset = CitizenRequest.objects.all().select_related('related_ticket')
    serializer_class = CitizenRequestSerializer
    filterset_fields = ['status', 'category']
    search_fields = ['request_number', 'citizen_name', 'subject']
    pagination_class = ServicePagination

    @action(detail=True, methods=['post'])
    def acknowledge(self, request, pk=None):
        citizen_request = self.get_object()
        if citizen_request.status == 'Submitted':
            citizen_request.status = 'Acknowledged'
            citizen_request.save()
        return Response({"status": f"Request {citizen_request.request_number} acknowledged"})

    @action(detail=True, methods=['post'])
    def convert_to_ticket(self, request, pk=None):
        from .models import ServiceTicket
        from django.db import transaction as db_transaction
        citizen_request = self.get_object()

        with db_transaction.atomic():
            last_tkt = ServiceTicket.objects.select_for_update().order_by('-id').first()
            next_num = (last_tkt.id + 1) if last_tkt else 1
            ticket_number = f"TKT-{timezone.now().strftime('%Y%m%d')}-{next_num:06d}"

        ticket = ServiceTicket.objects.create(
            ticket_number=ticket_number,
            subject=f"Citizen Request: {citizen_request.subject}",
            description=citizen_request.description,
            status='Open',
            priority='Medium'
        )
        
        citizen_request.related_ticket = ticket
        citizen_request.status = 'In Progress'
        citizen_request.save()
        
        serializer = CitizenRequestSerializer(citizen_request)
        return Response({"status": "Ticket created from citizen request", "ticket_id": ticket.id})

    @action(detail=False, methods=['get'])
    def public_list(self, request):
        citizen_requests = CitizenRequest.objects.filter(status__in=['Submitted', 'Acknowledged', 'In Progress'])
        serializer = self.get_serializer(citizen_requests, many=True)
        return Response(serializer.data)
class ServiceMetricViewSet(viewsets.ModelViewSet):
    queryset = ServiceMetric.objects.all()
    serializer_class = ServiceMetricSerializer
    filterset_fields = ['period']
    search_fields = ['name']

    @action(detail=False, methods=['post'])
    def generate_metrics(self, request):
        period = request.data.get('period', 'Monthly')
        
        now = timezone.now()
        if period == 'Daily':
            start = now.date()
            end = now.date()
        elif period == 'Weekly':
            start = (now - timedelta(days=7)).date()
            end = now.date()
        elif period == 'Monthly':
            start = now.replace(day=1).date()
            end = now.date()
        elif period == 'Quarterly':
            start = (now - timedelta(days=90)).date()
            end = now.date()
        else:
            start = now.replace(month=1, day=1).date()
            end = now.date()
        
        # Optimized: Use aggregation to reduce queries
        ticket_stats = ServiceTicket.objects.filter(
            created_at__date__gte=start, created_at__date__lte=end
        ).aggregate(
            total=Count('id'),
            open=Count(Case(When(status__in=['Open', 'In Progress'], then=1))),
            resolved=Count(Case(When(status='Resolved', then=1))),
            closed=Count(Case(When(status='Closed', then=1))),
        )
        
        work_order_stats = WorkOrder.objects.filter(
            created_at__date__gte=start, created_at__date__lte=end
        ).aggregate(
            total=Count('id'),
            completed=Count(Case(When(status='Completed', then=1))),
            total_labor=Sum('labor_hours'),
            total_cost=Sum('total_cost'),
        )
        
        metric = ServiceMetric.objects.create(
            name=f"Service Metrics - {period}",
            period=period,
            period_start=start,
            period_end=end,
            total_tickets=ticket_stats['total'],
            open_tickets=ticket_stats['open'],
            resolved_tickets=ticket_stats['resolved'],
            closed_tickets=ticket_stats['closed'],
            avg_response_time=0,
            avg_resolution_time=0,
            total_work_orders=work_order_stats['total'],
            completed_work_orders=work_order_stats['completed'],
            total_labor_hours=work_order_stats['total_labor'] or 0,
            total_cost=work_order_stats['total_cost'] or 0
        )
        
        serializer = ServiceMetricSerializer(metric)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['get'])
    def dashboard(self, request):
        now = timezone.now()
        start = now.replace(day=1).date()
        
        # Optimized: Single aggregation query for both tickets and work orders
        ticket_stats = ServiceTicket.objects.filter(created_at__date__gte=start).aggregate(
            total=Count('id'),
            open=Count(Case(When(status__in=['Open', 'In Progress'], then=1))),
            resolved=Count(Case(When(status='Resolved', then=1))),
        )
        
        work_order_stats = WorkOrder.objects.filter(created_at__date__gte=start).aggregate(
            total=Count('id'),
            pending=Count(Case(When(status='Pending', then=1))),
            completed=Count(Case(When(status='Completed', then=1))),
        )
        
        data = {
            'total_tickets': ticket_stats['total'],
            'open_tickets': ticket_stats['open'],
            'resolved_tickets': ticket_stats['resolved'],
            'total_work_orders': work_order_stats['total'],
            'pending_work_orders': work_order_stats['pending'],
            'completed_work_orders': work_order_stats['completed'],
            'total_citizen_requests': CitizenRequest.objects.filter(created_at__date__gte=start).count(),
            'technicians_available': Technician.objects.filter(is_available=True).count(),
        }
        return Response(data)
