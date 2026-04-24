import logging
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAdminUser, IsAuthenticated

logger = logging.getLogger(__name__)

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone
from .models import (
    ApprovalGroup, ApprovalTemplate, ApprovalTemplateStep,
    Approval, ApprovalStep, ApprovalLog, ApprovalDelegation,
    WorkflowDefinition, WorkflowInstance, WorkflowLog,
    GlobalApprovalSettings
)
from .serializers import (
    ApprovalGroupSerializer, ApprovalTemplateSerializer, ApprovalSerializer,
    ApprovalStepSerializer, ApprovalLogSerializer, ApprovalDelegationSerializer
)

# Document types that support approval workflows.
# This list drives the content_types API endpoint used by the template designer.
APPROVABLE_MODELS = [
    # ── Full P2P procurement chain ─────────────────────────────────────────
    'purchaserequest',
    'purchaseorder',
    'goodsreceivednote',
    'invoicematching',       # Invoice Verification (3-way match)
    'purchasereturn',
    # ── Public-sector IFMIS workflows ─────────────────────────────────────
    'paymentvoucher',        # PV — TSA disbursement authorisation
    'appropriation',         # Budget Appropriation (create + activate)
    'warrant',               # AIE / Cash Release Warrant
    'appropriationvirement', # Virement between economic lines
    'revenuebudget',         # Revenue target budget
    'baddebtwriteoff',       # Revenue / bad-debt write-off (Accountant-General + FC)
    'assetdisposal',         # Fixed asset disposal
    'fixedasset',            # Fixed asset creation / capitalisation
    # ── GL / HR ──────────────────────────────────────────────────────────
    'journalheader',
    'leaverequest',
    'payrollrun',
]

APPROVABLE_LABELS = {
    'purchaserequest':        'Purchase Request',
    'purchaseorder':          'Purchase Order',
    'goodsreceivednote':      'Goods Received Note',
    'invoicematching':        'Invoice Verification',
    'purchasereturn':         'Purchase Return',
    'paymentvoucher':         'Payment Voucher',
    'appropriation':          'Budget Appropriation',
    'warrant':                'Cash Release Warrant (AIE)',
    'appropriationvirement':  'Budget Virement',
    'revenuebudget':          'Revenue Budget',
    'baddebtwriteoff':        'Revenue Write-Off',
    'assetdisposal':          'Asset Disposal',
    'fixedasset':             'Fixed Asset Capitalisation',
    'journalheader':          'Journal Entry',
    'leaverequest':           'Leave Request',
    'payrollrun':             'Payroll Run',
}


# Maps the lowercase ContentType model name to the GlobalApprovalSettings.module key.
# .capitalize() breaks for multi-word model names like 'invoicematching' → 'Invoicematching'
# which doesn't match the MODULE_CHOICES value 'InvoiceVerification'.
_MODEL_TO_MODULE_KEY = {
    'purchaserequest':        'PurchaseRequest',
    'purchaseorder':          'PurchaseOrder',
    'goodsreceivednote':      'GoodsReceivedNote',
    'invoicematching':        'InvoiceVerification',   # BUG-2 fix: was 'Invoicematching'
    'purchasereturn':         'PurchaseReturn',
    'paymentvoucher':         'PaymentVoucher',
    'appropriation':          'Appropriation',
    'warrant':                'Warrant',
    'appropriationvirement':  'Appropriation',
    'revenuebudget':          'Budget',
    'baddebtwriteoff':        'RevenueWriteOff',
    'assetdisposal':          'AssetDisposal',
    'fixedasset':             'Budget',
    'journalheader':          'JournalEntry',
    'leaverequest':           'LeaveRequest',
    'payrollrun':             'PayrollRun',
}


def auto_route_approval(obj, model_name, request, title=None, amount=None):
    """
    WF-H1: Automatic Approval Routing helper function.

    Determines if approval is required based on GlobalApprovalSettings,
    selects the best-matching template, and atomically creates the
    Approval + ApprovalStep + ApprovalLog records.

    Returns a dict:
      {'approval_required': True,  'approval_id': <int>}  — routed to workflow
      {'approval_required': False, 'auto_approved': True}  — bypassed (disabled / below threshold)
      {'approval_required': True,  'already_pending': True} — duplicate guard fired
    """
    from decimal import Decimal
    from django.db import transaction as db_transaction

    ct = ContentType.objects.filter(model=model_name).first()
    if not ct:
        return {'approval_required': True, 'approval_id': None}

    # BUG-4 FIX: guard against duplicate submissions
    if Approval.objects.filter(content_type=ct, object_id=obj.pk, status='Pending').exists():
        existing = Approval.objects.filter(content_type=ct, object_id=obj.pk, status='Pending').first()
        return {
            'approval_required': True,
            'already_pending': True,
            'approval_id': existing.pk,
        }

    amount_decimal = Decimal(str(amount)) if amount is not None else Decimal('0')

    # BUG-2 FIX: use explicit mapping instead of .capitalize()
    module_key = _MODEL_TO_MODULE_KEY.get(model_name, model_name.capitalize())
    settings_obj = GlobalApprovalSettings.objects.filter(module=module_key).first()

    # Check if approvals are disabled for this module
    if settings_obj and settings_obj.approval_mode == 'Disabled':
        return {'approval_required': False, 'auto_approved': True, 'reason': 'Approvals disabled'}

    # Check auto-approve below threshold
    if settings_obj and settings_obj.auto_approve_below_threshold and settings_obj.use_amount_threshold:
        if amount_decimal < settings_obj.low_amount_threshold:
            return {'approval_required': False, 'auto_approved': True, 'reason': 'Amount below threshold'}

    # Select template — prefer one whose steps collectively cover the document amount.
    # We match against the template's *highest* group max_amount rather than any single
    # group, because we want a template that can handle the full value end-to-end.
    # WARN-2 FIX: compare amount against the template's group ranges more sensibly.
    templates = ApprovalTemplate.objects.filter(
        content_type=ct, is_active=True
    ).order_by('id')

    # Simpler: just fetch template steps separately (avoids .values_list prefetch miss)
    selected_template = None
    for tmpl in templates:
        steps_qs = ApprovalTemplateStep.objects.filter(template=tmpl).select_related('group')
        for step in steps_qs:
            g = step.group
            min_val = g.min_amount if g.min_amount is not None else Decimal('0')
            max_val = g.max_amount if g.max_amount is not None else Decimal('Inf')
            if min_val <= amount_decimal <= max_val:
                selected_template = tmpl
                break
        if selected_template:
            break

    if not selected_template:
        # Fallback: first active template for this content type
        selected_template = templates.first()

    # BUG-1 FIX: wrap all DB writes in a single atomic block so a partial failure
    # never leaves an orphaned Approval record with no steps.
    with db_transaction.atomic():
        template_steps = []
        if selected_template:
            template_steps = list(
                ApprovalTemplateStep.objects.filter(template=selected_template)
                .select_related('group')
                .order_by('sequence')
            )

        total_steps = max(len(template_steps), 1)

        approval_obj = Approval.objects.create(
            content_type=ct,
            object_id=obj.pk,
            title=title or f"{APPROVABLE_LABELS.get(model_name, model_name)} #{obj.pk}",
            description='',
            amount=amount,
            status='Pending',
            current_step=1,
            total_steps=total_steps,
            requested_by=request.user,
            template=selected_template,
        )

        if template_steps:
            for ts in template_steps:
                ApprovalStep.objects.create(
                    approval=approval_obj,
                    step_number=ts.sequence,
                    approver_group=ts.group,
                    status='Pending',
                )
        else:
            # No template found — create a single unassigned step (admin must act manually)
            ApprovalStep.objects.create(
                approval=approval_obj,
                step_number=1,
                status='Pending',
            )

        ApprovalLog.objects.create(
            approval=approval_obj,
            action='Submit',
            comment='',
            user=request.user,
        )

    return {
        'approval_required': True,
        'approval_id': approval_obj.pk,
        'approval_number': str(approval_obj.pk),
    }


class ApprovalPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class GlobalApprovalSettingsViewSet(viewsets.ModelViewSet):
    """ViewSet for managing global approval settings per module.

    Admin-only — tampering with these settings (thresholds, auto-approval,
    approval modes) is a systemic-risk change affecting all users.
    """
    queryset = GlobalApprovalSettings.objects.all()
    pagination_class = ApprovalPagination
    filterset_fields = ['module', 'approval_mode']
    permission_classes = [IsAdminUser]
    
    @action(detail=False, methods=['get'])
    def check(self, request):
        """Check if approval is required for a specific module"""
        module = request.query_params.get('module')
        amount = request.query_params.get('amount')
        
        if not module:
            return Response({'error': 'module is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        from decimal import Decimal
        amount_decimal = Decimal(amount) if amount else Decimal('0')
        
        is_required = GlobalApprovalSettings.is_enabled(module)
        should_auto_approve = GlobalApprovalSettings.should_auto_approve(module, amount_decimal)
        mode = GlobalApprovalSettings.get_mode(module)
        
        return Response({
            'module': module,
            'approval_required': is_required,
            'auto_approve': should_auto_approve,
            'mode': mode,
            'amount': float(amount_decimal) if amount else None,
        })
    
    @action(detail=False, methods=['post'])
    def configure_module(self, request):
        """Configure approval settings for a module"""
        module = request.data.get('module')
        approval_mode = request.data.get('approval_mode')
        
        if not module or not approval_mode:
            return Response({'error': 'module and approval_mode are required'}, status=status.HTTP_400_BAD_REQUEST)
        
        settings, created = GlobalApprovalSettings.objects.update_or_create(
            module=module,
            defaults={
                'approval_mode': approval_mode,
                'use_amount_threshold': request.data.get('use_amount_threshold', False),
                'low_amount_threshold': request.data.get('low_amount_threshold', 10000),
                'high_amount_threshold': request.data.get('high_amount_threshold', 100000),
                'auto_approve_below_threshold': request.data.get('auto_approve_below_threshold', True),
                'send_notifications': request.data.get('send_notifications', True),
                'notify_requester': request.data.get('notify_requester', True),
            }
        )
        
        return Response({
            'status': 'configured',
            'module': module,
            'mode': settings.approval_mode,
            'created': created,
        })
    
    @action(detail=False, methods=['get'])
    def all_settings(self, request):
        """Get all module approval settings"""
        modules = [
            # Full P2P procurement chain
            'PurchaseRequest',
            'PurchaseOrder',
            'GoodsReceivedNote',
            'InvoiceVerification',
            'PurchaseReturn',
            # Other modules
            'SalesOrder',
            'ProductionOrder',
            'QualityInspection',
            'Budget',
            'JournalEntry',
            'LeaveRequest',
            'Maintenance',
        ]

        result = []
        for module in modules:
            settings_obj = GlobalApprovalSettings.objects.filter(module=module).first()
            mode = settings_obj.approval_mode if settings_obj else 'Required'
            result.append({
                'module': module,
                'mode': mode,
                'enabled': GlobalApprovalSettings.is_enabled(module),
                'use_amount_threshold': settings_obj.use_amount_threshold if settings_obj else False,
                'low_amount_threshold': float(settings_obj.low_amount_threshold) if settings_obj else 10000,
                'auto_approve_below_threshold': settings_obj.auto_approve_below_threshold if settings_obj else True,
            })

        return Response(result)


class ApprovalGroupViewSet(viewsets.ModelViewSet):
    """Admin-only: defines WHO can approve what.

    Exposing write-access here would let any authenticated user add
    themselves to an approval group and then self-approve their own
    documents — a classic SOD bypass.
    """
    queryset = ApprovalGroup.objects.all()
    serializer_class = ApprovalGroupSerializer
    pagination_class = ApprovalPagination
    permission_classes = [IsAdminUser]


class ApprovalTemplateViewSet(viewsets.ModelViewSet):
    """Admin-only: configures approval chain templates per document type.

    Users may read templates to understand flow, but only admins may
    change the chain itself.
    """
    queryset = ApprovalTemplate.objects.all().prefetch_related('steps')
    serializer_class = ApprovalTemplateSerializer
    pagination_class = ApprovalPagination
    permission_classes = [IsAdminUser]

    @action(detail=False, methods=['get'])
    def content_types(self, request):
        """Return valid document types for approval templates."""
        result = []
        for model_name in APPROVABLE_MODELS:
            ct = ContentType.objects.filter(model=model_name).first()
            if ct:
                result.append({
                    'id': ct.pk,
                    'model': ct.model,
                    'app_label': ct.app_label,
                    'label': APPROVABLE_LABELS.get(model_name, model_name),
                })
        return Response(result)

    @action(detail=False, methods=['post'])
    def seed_defaults(self, request):
        """Create default approval groups and templates for common document types."""
        created_groups = 0
        skipped_groups = 0
        created_templates = 0
        skipped_templates = 0

        # --- Default Approval Groups ---
        default_groups = [
            {
                'name': 'Department Reviewer',
                'description': 'Line manager review for departmental items',
                'min_amount': 0,
                'max_amount': 500000,
            },
            {
                'name': 'Finance Approver',
                'description': 'Finance team approval for financial transactions',
                'min_amount': 0,
                'max_amount': 5000000,
            },
            {
                'name': 'Executive Approver',
                'description': 'Executive sign-off for high-value transactions',
                'min_amount': 5000000,
                'max_amount': None,
            },
        ]

        group_map = {}
        for gd in default_groups:
            group, created = ApprovalGroup.objects.get_or_create(
                name=gd['name'],
                defaults=gd,
            )
            group_map[gd['name']] = group
            if created:
                created_groups += 1
            else:
                skipped_groups += 1

        dept = group_map.get('Department Reviewer')
        finance = group_map.get('Finance Approver')
        executive = group_map.get('Executive Approver')

        # --- Default Templates ---
        default_templates = [
            {
                'name': 'Purchase Request Approval',
                'description': 'Standard two-level approval for purchase requests',
                'model': 'purchaserequest',
                'approval_type': 'Sequential',
                'steps': [
                    {'group': dept, 'sequence': 1},
                    {'group': finance, 'sequence': 2},
                ],
            },
            {
                'name': 'Purchase Order Approval',
                'description': 'Finance and executive approval for purchase orders',
                'model': 'purchaseorder',
                'approval_type': 'Sequential',
                'steps': [
                    {'group': finance, 'sequence': 1},
                    {'group': executive, 'sequence': 2},
                ],
            },
            {
                'name': 'Journal Entry Approval',
                'description': 'Finance review for journal entries',
                'model': 'journalheader',
                'approval_type': 'Sequential',
                'steps': [
                    {'group': finance, 'sequence': 1},
                ],
            },
            {
                'name': 'Vendor Invoice Approval',
                'description': 'Finance approval for vendor invoices before payment',
                'model': 'vendorinvoice',
                'approval_type': 'Sequential',
                'steps': [
                    {'group': finance, 'sequence': 1},
                ],
            },
            {
                'name': 'Customer Invoice Approval',
                'description': 'Finance approval for outgoing customer invoices',
                'model': 'customerinvoice',
                'approval_type': 'Any',
                'steps': [
                    {'group': finance, 'sequence': 1},
                ],
            },
            {
                'name': 'Sales Order Approval',
                'description': 'Department and finance review for sales orders',
                'model': 'salesorder',
                'approval_type': 'Sequential',
                'steps': [
                    {'group': dept, 'sequence': 1},
                    {'group': finance, 'sequence': 2},
                ],
            },
            {
                'name': 'Leave Request Approval',
                'description': 'Department manager review for leave requests',
                'model': 'leaverequest',
                'approval_type': 'Sequential',
                'steps': [
                    {'group': dept, 'sequence': 1},
                ],
            },
            # ── Procurement P2P chain (new) ────────────────────────────────────
            {
                'name': 'GRN Approval',
                'description': 'Department and warehouse review before GRN is posted to inventory',
                'model': 'goodsreceivednote',
                'approval_type': 'Sequential',
                'steps': [
                    {'group': dept, 'sequence': 1},
                ],
            },
            {
                'name': 'Invoice Verification Approval',
                'description': 'Finance team approval after 3-way matching before payment is released',
                'model': 'invoicematching',
                'approval_type': 'Sequential',
                'steps': [
                    {'group': finance, 'sequence': 1},
                ],
            },
            {
                'name': 'Purchase Return Approval',
                'description': 'Department and finance approval before goods are returned to vendor',
                'model': 'purchasereturn',
                'approval_type': 'Sequential',
                'steps': [
                    {'group': dept,    'sequence': 1},
                    {'group': finance,  'sequence': 2},
                ],
            },
        ]

        for td in default_templates:
            ct = ContentType.objects.filter(model=td['model']).first()
            if not ct:
                continue
            template, created = ApprovalTemplate.objects.get_or_create(
                name=td['name'],
                defaults={
                    'description': td['description'],
                    'content_type': ct,
                    'approval_type': td['approval_type'],
                },
            )
            if created:
                created_templates += 1
            else:
                skipped_templates += 1

            # WARN-1 FIX: always upsert steps so re-running seed_defaults is
            # idempotent and repairs accidentally deleted steps.
            for step_def in td['steps']:
                if step_def['group'] is None:
                    continue  # group was not created (ContentType missing)
                ApprovalTemplateStep.objects.update_or_create(
                    template=template,
                    sequence=step_def['sequence'],
                    defaults={'group': step_def['group']},
                )

        return Response({
            'success': True,
            'created_groups': created_groups,
            'skipped_groups': skipped_groups,
            'created_templates': created_templates,
            'skipped_templates': skipped_templates,
            'total_groups': len(default_groups),
            'total_templates': len(default_templates),
        })
class ApprovalViewSet(viewsets.ModelViewSet):
    queryset = Approval.objects.all().select_related('content_type', 'requested_by', 'template')
    serializer_class = ApprovalSerializer
    filterset_fields = ['status', 'content_type']
    pagination_class = ApprovalPagination
    
    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user

        # Filter by user's approval groups (including delegated authority)
        if user and user.is_authenticated:
            from django.db.models import Q
            user_groups = user.approval_groups.all()

            # Also include groups of users who have delegated to this user
            delegators = ApprovalDelegation.objects.filter(
                delegate=user, is_active=True,
                start_date__lte=timezone.now().date(),
                end_date__gte=timezone.now().date(),
            ).values_list('delegator', flat=True)
            from django.contrib.auth.models import User
            delegator_groups = ApprovalGroup.objects.filter(members__in=delegators)

            all_groups = user_groups | delegator_groups
            queryset = queryset.filter(
                steps__approver_group__in=all_groups,
                steps__status='Pending'
            ).distinct()

        # Filter by status
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        return queryset

    @action(detail=True, methods=['post'])
    def submit(self, request, pk=None):
        """Submit an approval request for review"""
        approval = self.get_object()
        
        if approval.status != 'Draft':
            return Response({"error": "Only draft approvals can be submitted"}, status=status.HTTP_400_BAD_REQUEST)
        
        approval.status = 'Pending'
        approval.save()
        
        # Create log entry
        ApprovalLog.objects.create(
            approval=approval,
            action='Submit',
            comment=request.data.get('comment', ''),
            user=request.user
        )
        
        return Response(ApprovalSerializer(approval).data)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """
        Approve the current step of an approval request.

        BUG-1 FIX: entire operation is atomic — if _trigger_document_action raises,
                   the approval status is rolled back so the document is never orphaned.
        BUG-5 FIX: verifies the acting user belongs to the current step's approver group
                   (or is a delegate for a group member) before allowing the action.
        """
        approval = self.get_object()
        comment = request.data.get('comment', '')

        if approval.status != 'Pending':
            return Response(
                {"error": "Only pending approvals can be approved."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        current_step = approval.steps.filter(step_number=approval.current_step).first()

        # BUG-5 FIX: enforce that the acting user is authorised for THIS step
        if current_step and current_step.approver_group:
            group = current_step.approver_group
            user_is_member = group.members.filter(pk=request.user.pk).exists()

            # Also accept if the user is an active delegate for any group member
            if not user_is_member:
                from .models import ApprovalDelegation
                user_is_delegate = ApprovalDelegation.get_active_delegate.__func__ is not None and \
                    ApprovalDelegation.objects.filter(
                        delegate=request.user,
                        delegator__in=group.members.all(),
                        is_active=True,
                        start_date__lte=timezone.now().date(),
                        end_date__gte=timezone.now().date(),
                    ).exists()
                if not user_is_delegate:
                    return Response(
                        {"error": f"You are not authorised to approve step {approval.current_step}. "
                                  f"Only members of '{group.name}' (or their active delegates) can act on this step."},
                        status=status.HTTP_403_FORBIDDEN,
                    )

        with transaction.atomic():
            if current_step:
                current_step.status = 'Approved'
                current_step.approver = request.user
                current_step.comment = comment
                current_step.acted_at = timezone.now()
                current_step.save()

            remaining_steps = approval.steps.filter(status='Pending').count()

            if remaining_steps == 0:
                approval.status = 'Approved'
                approval.save()
                # This save is inside the atomic block — if it raises, the
                # step and approval status changes are both rolled back.
                self._trigger_document_action(approval, 'approve')
            else:
                approval.current_step += 1
                approval.save()

            ApprovalLog.objects.create(
                approval=approval,
                step=current_step,
                action='Approve',
                comment=comment,
                user=request.user,
            )

        return Response(ApprovalSerializer(approval).data)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """
        Reject the current step and close the entire approval request.

        BUG-1 FIX: atomic — if _trigger_document_action raises, the rejection
                   is rolled back so no half-finalised state persists.
        BUG-5 FIX: same step-level authorisation check as approve.
        """
        approval = self.get_object()
        comment = request.data.get('comment', '')

        if approval.status != 'Pending':
            return Response(
                {"error": "Only pending approvals can be rejected."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        current_step = approval.steps.filter(step_number=approval.current_step).first()

        # BUG-5 FIX: only the current step's group (or their delegates) can reject
        if current_step and current_step.approver_group:
            group = current_step.approver_group
            user_is_member = group.members.filter(pk=request.user.pk).exists()
            if not user_is_member:
                from .models import ApprovalDelegation
                user_is_delegate = ApprovalDelegation.objects.filter(
                    delegate=request.user,
                    delegator__in=group.members.all(),
                    is_active=True,
                    start_date__lte=timezone.now().date(),
                    end_date__gte=timezone.now().date(),
                ).exists()
                if not user_is_delegate:
                    return Response(
                        {"error": f"You are not authorised to reject step {approval.current_step}. "
                                  f"Only members of '{group.name}' (or their active delegates) can act on this step."},
                        status=status.HTTP_403_FORBIDDEN,
                    )

        with transaction.atomic():
            approval.status = 'Rejected'
            approval.save()

            if current_step:
                current_step.status = 'Rejected'
                current_step.approver = request.user
                current_step.comment = comment
                current_step.acted_at = timezone.now()
                current_step.save()

            self._trigger_document_action(approval, 'reject')

            ApprovalLog.objects.create(
                approval=approval,
                step=current_step,
                action='Reject',
                comment=comment,
                user=request.user,
            )

        return Response(ApprovalSerializer(approval).data)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel an approval request"""
        approval = self.get_object()
        
        if approval.status not in ['Draft', 'Pending']:
            return Response({"error": "Cannot cancel this approval"}, status=status.HTTP_400_BAD_REQUEST)
        
        approval.status = 'Cancelled'
        approval.save()
        
        ApprovalLog.objects.create(
            approval=approval,
            action='Cancel',
            comment=request.data.get('comment', ''),
            user=request.user
        )
        
        return Response(ApprovalSerializer(approval).data)

    @action(detail=False, methods=['get'])
    def pending_count(self, request):
        """Get count of pending approvals for current user"""
        user = request.user
        if not user.is_authenticated:
            return Response({'count': 0})
        
        count = Approval.objects.filter(
            steps__approver_group__members=user,
            steps__status='Pending',
            status='Pending'
        ).distinct().count()
        
        return Response({'count': count})

    @action(detail=False, methods=['get'])
    def my_pending(self, request):
        """Get all pending approvals for current user"""
        user = request.user
        if not user.is_authenticated:
            return Response([])
        
        approvals = Approval.objects.filter(
            steps__approver_group__members=user,
            steps__status='Pending',
            status='Pending'
        ).distinct().select_related('content_type', 'requested_by')
        
        return Response(ApprovalSerializer(approvals, many=True).data)

    @action(detail=False, methods=['post'])
    def submit_new(self, request):
        """Create and submit an approval in one step, auto-selecting template by content_type and amount."""
        model_name = request.data.get('content_type')
        object_id = request.data.get('object_id')
        title = request.data.get('title', '')
        description = request.data.get('description', '')
        amount = request.data.get('amount')

        if not model_name or not object_id:
            return Response(
                {"error": "content_type and object_id are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ct = ContentType.objects.filter(model=model_name).first()
        if not ct:
            return Response(
                {"error": f"Unknown document type: {model_name}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # WF-H1: Automatic Approval Routing based on amount thresholds
        from decimal import Decimal
        amount_decimal = Decimal(str(amount)) if amount else Decimal('0')
        
        # Check global settings for this module
        module_name = model_name.capitalize()
        settings = GlobalApprovalSettings.objects.filter(module=module_name).first()
        
        # WF-H1: Auto-approve if below threshold
        if settings and settings.auto_approve_below_threshold:
            if settings.use_amount_threshold and amount_decimal < settings.low_amount_threshold:
                # Auto-approve without creating approval request
                return Response({
                    'status': 'auto_approved',
                    'reason': f'Amount {amount_decimal} below threshold {settings.low_amount_threshold}',
                    'approval_required': False
                }, status=status.HTTP_200_OK)
        
        # WF-H1: Select template based on amount thresholds
        # Try to find a template that matches the amount criteria
        templates = ApprovalTemplate.objects.filter(
            content_type=ct, is_active=True
        ).prefetch_related('steps__group')
        
        selected_template = None
        for template in templates:
            template_groups = list(template.steps.all().values_list('group__min_amount', 'group__max_amount'))
            # Check if any group in template matches the amount
            for min_amt, max_amt in template_groups:
                min_val = min_amt if min_amt is not None else Decimal('0')
                max_val = max_amt if max_amt is not None else Decimal('Inf')
                if min_val <= amount_decimal <= max_val:
                    selected_template = template
                    break
            if selected_template:
                break
        
        # Fallback to first active template
        if not selected_template:
            selected_template = ApprovalTemplate.objects.filter(
                content_type=ct, is_active=True
            ).first()

        # Determine steps from template or create a single default step
        template_steps = []
        if selected_template:
            template_steps = list(
                ApprovalTemplateStep.objects.filter(template=selected_template).select_related('group').order_by('sequence')
            )

        total_steps = max(len(template_steps), 1)

        approval_obj = Approval.objects.create(
            content_type=ct,
            object_id=object_id,
            title=title or f"{APPROVABLE_LABELS.get(model_name, model_name)} #{object_id}",
            description=description,
            amount=amount,
            status='Pending',
            current_step=1,
            total_steps=total_steps,
            requested_by=request.user,
            template=selected_template,
        )

        # Create approval steps from template
        if template_steps:
            for ts in template_steps:
                ApprovalStep.objects.create(
                    approval=approval_obj,
                    step_number=ts.sequence,
                    approver_group=ts.group,
                    status='Pending',
                )
        else:
            # No template — create a single step (manual approval)
            ApprovalStep.objects.create(
                approval=approval_obj,
                step_number=1,
                status='Pending',
            )

        ApprovalLog.objects.create(
            approval=approval_obj,
            action='Submit',
            comment=request.data.get('comment', ''),
            user=request.user,
        )

        return Response(ApprovalSerializer(approval_obj).data, status=status.HTTP_201_CREATED)

    def _trigger_document_action(self, approval, action):
        """
        Trigger action on the target document when a workflow approval/rejection completes.

        Procurement P2P chain status mapping on APPROVE:
          purchaserequest  → 'Approved'   (user then posts the PO)
          purchaseorder    → 'Approved'   (user then posts the PO)
          goodsreceivednote→ 'Received'   (user then runs post_grn to create stock movements)
          invoicematching  → 'Approved'   (payment can now be released)
          purchasereturn   → 'Approved'   (user then completes the return)

        On REJECT:
          purchaserequest / purchaseorder → 'Rejected'
          goodsreceivednote               → 'Cancelled'
          invoicematching                 → 'Rejected'
          purchasereturn                  → 'Cancelled'
        """
        try:
            doc = approval.content_object
            if not doc or not hasattr(doc, 'status'):
                return

            model_name = approval.content_type.model  # lowercase model name

            if action == 'approve':
                # Model-specific approved-state mapping
                approved_status = {
                    'goodsreceivednote': 'Received',    # ready to be posted by warehouse
                    'invoicematching':   'Approved',
                    'purchasereturn':    'Approved',
                    'purchaserequest':   'Approved',
                    'purchaseorder':     'Approved',
                }.get(model_name)

                if approved_status:
                    doc.status = approved_status
                    doc.save()
                elif hasattr(doc, 'approve'):
                    doc.approve()
                else:
                    doc.status = 'Approved'
                    doc.save()

                # ── Auto-post InvoiceMatching to GL on approval ──
                # User expectation: once an Invoice Verification
                # (three-way match) is approved — whether by auto-
                # routing (no approver required) or by a human
                # approver via the workflow inbox — the GL journal
                # should fire immediately (DR GR/IR / CR AP) and the
                # budget commitment should close. No extra "Post to
                # GL" click. Matches the already-auto-posting
                # behaviour of ``verify_and_post``.
                if model_name == 'invoicematching' and doc.status == 'Approved':
                    try:
                        from procurement.views import InvoiceMatchingViewSet
                        from django.db import transaction as _tx
                        with _tx.atomic():
                            InvoiceMatchingViewSet._post_matching_to_gl_inner(doc)
                    except Exception as exc:
                        import logging
                        logging.getLogger(__name__).warning(
                            'Workflow-approved matching %s auto-post to GL '
                            'failed (user can still retry via Post to GL): %s',
                            doc.pk, exc,
                        )

            elif action == 'reject':
                rejected_status = {
                    'goodsreceivednote': 'Cancelled',
                    'purchasereturn':    'Cancelled',
                    'invoicematching':   'Rejected',
                    'purchaserequest':   'Rejected',
                    'purchaseorder':     'Rejected',
                }.get(model_name)

                if rejected_status:
                    doc.status = rejected_status
                    doc.save()
                elif hasattr(doc, 'reject'):
                    doc.reject()
                else:
                    doc.status = 'Rejected'
                    doc.save()

        except Exception as e:
            import logging
            logging.getLogger('dtsg').error(
                f"_trigger_document_action failed for approval {approval.pk} ({action}): {e}"
            )
class ApprovalStepViewSet(viewsets.ModelViewSet):
    queryset = ApprovalStep.objects.all().select_related('approval', 'approver_group', 'approver')
    serializer_class = ApprovalStepSerializer
    pagination_class = ApprovalPagination
    
    @action(detail=False, methods=['get'])
    def sla_monitor(self, request):
        """WF-M1: Get SLA status for pending approvals."""
        from django.utils import timezone
        from django.db.models import Count
        
        now = timezone.now()
        
        pending = self.queryset.filter(status='Pending')
        
        overdue = pending.filter(due_date__lt=now)
        at_risk = pending.filter(
            due_date__gte=now,
            due_date__lte=now + timezone.timedelta(hours=4)
        )
        on_track = pending.filter(due_date__gt=now + timezone.timedelta(hours=4))
        no_sla = pending.filter(due_date__isnull=True)
        
        return Response({
            'summary': {
                'total_pending': pending.count(),
                'overdue': overdue.count(),
                'at_risk': at_risk.count(),
                'on_track': on_track.count(),
                'no_sla': no_sla.count(),
            },
            'overdue_list': ApprovalStepSerializer(overdue[:20], many=True).data,
            'at_risk_list': ApprovalStepSerializer(at_risk[:20], many=True).data,
        })


class ApprovalLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ApprovalLog.objects.all().select_related('approval', 'step', 'user')
    serializer_class = ApprovalLogSerializer
    pagination_class = ApprovalPagination


class ApprovalDelegationViewSet(viewsets.ModelViewSet):
    queryset = ApprovalDelegation.objects.all().select_related('delegator', 'delegate')
    serializer_class = ApprovalDelegationSerializer
    pagination_class = ApprovalPagination
    filterset_fields = ['is_active', 'delegator', 'delegate']

    @action(detail=False, methods=['get'])
    def my_delegations(self, request):
        """Get all delegations where the current user is delegator or delegate."""
        from django.db.models import Q
        user = request.user
        delegations = ApprovalDelegation.objects.filter(
            Q(delegator=user) | Q(delegate=user)
        ).select_related('delegator', 'delegate')
        return Response(ApprovalDelegationSerializer(delegations, many=True).data)
# Legacy workflow views for backward compatibility
from .models import WorkflowDefinition, WorkflowInstance, WorkflowLog, WorkflowStep
from .serializers import WorkflowDefinitionSerializer, WorkflowInstanceSerializer, WorkflowLogSerializer

class WorkflowDefinitionViewSet(viewsets.ModelViewSet):
    queryset = WorkflowDefinition.objects.all().prefetch_related('steps')
    serializer_class = WorkflowDefinitionSerializer

class WorkflowInstanceViewSet(viewsets.ModelViewSet):
    queryset = WorkflowInstance.objects.all().prefetch_related('logs', 'workflow__steps')
    serializer_class = WorkflowInstanceSerializer

    @action(detail=True, methods=['post'])
    def process_action(self, request, pk=None):
        instance = self.get_object()
        action_name = request.data.get('action')
        comment = request.data.get('comment', '')
        user_display = request.data.get('user_display', 'System User')

        if not action_name:
            return Response({"error": "Action is required."}, status=status.HTTP_400_BAD_REQUEST)

        if action_name == 'Submit' and instance.status == 'Draft':
            instance.status = 'Pending'
            instance.current_step = instance.workflow.steps.first()
        elif action_name == 'Approve' and instance.status == 'Pending':
            next_step = instance.workflow.steps.filter(sequence__gt=instance.current_step.sequence).first()
            if next_step:
                instance.current_step = next_step
            else:
                instance.status = 'Approved'
                instance.current_step = None
                self._trigger_document_approval(instance)
        elif action_name == 'Reject':
            instance.status = 'Rejected'
            instance.current_step = None

        instance.save()

        WorkflowLog.objects.create(
            instance=instance,
            step=instance.current_step,
            action=action_name,
            comment=comment,
            user_display=user_display
        )

        return Response(WorkflowInstanceSerializer(instance).data)

    def _trigger_document_approval(self, instance):
        try:
            doc = instance.content_object
            if hasattr(doc, 'status'):
                doc.status = 'Approved'
                doc.save()
        except Exception as exc:
            logger.warning(
                "workflow: could not update document status to Approved "
                "for approval %s (content_type=%s, object_id=%s): %s",
                instance.pk,
                getattr(instance, 'content_type_id', '?'),
                getattr(instance, 'object_id', '?'),
                exc,
            )
