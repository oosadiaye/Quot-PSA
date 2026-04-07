import logging

from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from core.permissions import IsApprover, RBACPermission

from django.db import transaction, IntegrityError
from django.db.models import Sum, F, Q, Value, DecimalField
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from decimal import Decimal
from .models import Vendor, VendorCategory, PurchaseRequest, PurchaseOrder, GoodsReceivedNote, InvoiceMatching, VendorCreditNote, VendorDebitNote, PurchaseReturn, PurchaseReturnLine, DownPaymentRequest
from .serializers import (
    VendorSerializer, VendorCategorySerializer, PurchaseRequestSerializer, PurchaseOrderSerializer,
    GoodsReceivedNoteSerializer, InvoiceMatchingSerializer,
    VendorCreditNoteSerializer, VendorDebitNoteSerializer, PurchaseReturnSerializer,
    DownPaymentRequestSerializer,
)
from accounting.transaction_posting import TransactionPostingService
from accounting.models import BudgetEncumbrance   # BUG-3 FIX: was missing, caused NameError in PR approve

logger = logging.getLogger('dtsg')
class ProcurementPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 50
def _get_doc_amount(obj):
    """Return the best numeric amount for a procurement document."""
    for attr in ('total_amount', 'grand_total', 'invoice_amount', 'estimated_amount'):
        val = getattr(obj, attr, None)
        if val is not None:
            return val
    return None

class VendorCategoryViewSet(viewsets.ModelViewSet):
    queryset = VendorCategory.objects.all().select_related('reconciliation_account')
    serializer_class = VendorCategorySerializer
    permission_classes = [RBACPermission]
    search_fields = ['name', 'code']
    filterset_fields = ['is_active']
    pagination_class = ProcurementPagination

    def get_queryset(self):
        from django.db.models import Count
        return VendorCategory.objects.select_related(
            'reconciliation_account'
        ).annotate(
            _vendor_count=Count('vendors')
        )


class VendorViewSet(viewsets.ModelViewSet):
    queryset = Vendor.objects.all().select_related('category')
    serializer_class = VendorSerializer
    permission_classes = [RBACPermission]
    search_fields = ['name', 'code']
    filterset_fields = ['is_active', 'category']
    pagination_class = ProcurementPagination

    def get_queryset(self):
        return Vendor.objects.select_related('category').annotate(
            current_balance=Coalesce(
                Sum(
                    F('invoices__total_amount') - F('invoices__paid_amount'),
                    filter=Q(invoices__status__in=['Approved', 'Partially Paid']),
                    output_field=DecimalField(),
                ),
                Value(0),
                output_field=DecimalField(),
            )
        )

    @action(detail=True, methods=['get'])
    def performance(self, request, pk=None):
        """Get detailed performance metrics for a vendor"""
        vendor = self.get_object()
        return Response({
            "vendor_id": vendor.id,
            "vendor_name": vendor.name,
            "total_orders": vendor.total_orders,
            "on_time_deliveries": vendor.on_time_deliveries,
            "on_time_delivery_rate": vendor.on_time_delivery_rate,
            "quality_score": vendor.quality_score,
            "performance_rating": vendor.performance_rating,
            "total_purchase_value": vendor.total_purchase_value,
        })

    @action(detail=False, methods=['get'])
    def performance_report(self, request):
        """Get performance report for all active vendors"""
        vendors = Vendor.objects.filter(
            is_active=True
        ).only(
            'id', 'name', 'code', 'total_orders', 'on_time_deliveries',
            'quality_score', 'total_purchase_value',
        ).order_by('-total_purchase_value')
        data = [{
            "vendor_id": v.id,
            "vendor_name": v.name,
            "vendor_code": v.code,
            "total_orders": v.total_orders,
            "on_time_delivery_rate": v.on_time_delivery_rate,
            "quality_score": v.quality_score,
            "performance_rating": v.performance_rating,
            "total_purchase_value": v.total_purchase_value,
        } for v in vendors]
        return Response(data)

class PurchaseRequestViewSet(viewsets.ModelViewSet):
    queryset = PurchaseRequest.objects.select_related(
        'fund', 'function', 'program', 'geo'
    ).prefetch_related('lines').all()
    serializer_class = PurchaseRequestSerializer
    permission_classes = [RBACPermission]
    filterset_fields = ['status']
    pagination_class = ProcurementPagination

    def get_permissions(self):
        if self.action == 'approve':
            return [IsApprover()]
        return super().get_permissions()

    @action(detail=True, methods=['post'])
    def submit_for_approval(self, request, pk=None):
        """Submit PR for approval through the centralized workflow engine."""
        from workflow.views import auto_route_approval
        pr = self.get_object()
        if pr.status not in ['Draft', 'Rejected']:
            return Response(
                {"error": "Only Draft or Rejected PRs can be submitted."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = auto_route_approval(
            pr, 'purchaserequest', request,
            title=f"PR-{pr.request_number}: {pr.description[:50]}",
            amount=_get_doc_amount(pr),
        )

        if result.get('auto_approved'):
            pr.status = 'Approved'
            msg = "Purchase Request auto-approved (below threshold)."
        else:
            pr.status = 'Pending'
            msg = "Purchase Request submitted for approval."

        pr.save()
        return Response({"status": msg, "approval_id": result.get('approval_id')})

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """Approve a purchase requisition"""
        pr = self.get_object()
        if pr.status != 'Pending':
            return Response({"error": "Only pending PRs can be approved."}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            with transaction.atomic():
                # P2P-H3: Budget Encumbrance on PR Approval
                # Create budget encumbrance when PR is approved
                budget_totals = {}
                for line in pr.lines.all():
                    # FIX #18: Skip lines without a GL account — no budget dimension
                    # is available for encumbrance, so these lines are not tracked.
                    if not line.account_id:
                        continue
                    key = (line.account, pr.mda, pr.fund, pr.function, pr.program, pr.geo)
                    amount = line.estimated_unit_price * line.quantity
                    budget_totals[key] = budget_totals.get(key, Decimal('0.00')) + amount

                from accounting.budget_logic import get_active_budget
                encumbrance_created = False
                
                missing_budget_keys = []
                for (account, mda, fund, function, program, geo), total_amount in budget_totals.items():
                    budget = get_active_budget(
                        dimensions={
                            'mda': mda,
                            'fund': fund,
                            'function': function,
                            'program': program,
                            'geo': geo
                        },
                        account=account,
                        date=pr.requested_date
                    )

                    if budget:
                        BudgetEncumbrance.objects.create(
                            budget=budget,
                            reference_type='PR',
                            reference_id=pr.pk,
                            encumbrance_date=pr.requested_date,
                            amount=total_amount,
                            status='ACTIVE',
                            description=f"Encumbrance for PR {pr.request_number}"
                        )
                        encumbrance_created = True
                    else:
                        # Record which dimension combination had no active budget
                        fund_code = fund.code if fund else 'N/A'
                        function_code = function.code if function else 'N/A'
                        missing_budget_keys.append(f"Fund:{fund_code}/Function:{function_code}")

                if missing_budget_keys and not encumbrance_created:
                    # No budget found for ANY line — block approval to enforce financial control
                    raise ValueError(
                        f"No active budget found for dimension(s): {', '.join(missing_budget_keys)}. "
                        "Create or activate a budget period before approving this PR."
                    )

                pr.status = 'Approved'
                pr.save()

                msg = "Purchase Requisition approved successfully."
                if encumbrance_created:
                    msg += f" Budget encumbrance created for {len(budget_totals)} line(s)."
                if missing_budget_keys:
                    msg += f" Warning: no active budget for {', '.join(missing_budget_keys)} — encumbrance skipped for those lines."

                return Response({"status": msg})
        except Exception as e:
            logger.error(f"Failed to approve PR {pr.request_number}: {e}")
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """Reject a purchase requisition"""
        pr = self.get_object()
        if pr.status not in ['Pending', 'Draft']:
            return Response({"error": "Cannot reject this PR."}, status=status.HTTP_400_BAD_REQUEST)

        pr.status = 'Rejected'
        # Store rejection reason if the field exists on the model
        reason = request.data.get('reason', '')
        if hasattr(pr, 'rejection_reason'):
            pr.rejection_reason = reason
        if hasattr(pr, 'notes') and reason:
            pr.notes = f"{pr.notes}\nRejected: {reason}".strip()
        pr.save()
        return Response({"status": "Purchase Requisition rejected."})

    @action(detail=True, methods=['post'])
    def convert_to_po(self, request, pk=None):
        """Convert approved PR to PO"""
        pr = self.get_object()
        if pr.status != 'Approved':
            return Response({"error": "Only approved PRs can be converted to PO."}, status=status.HTTP_400_BAD_REQUEST)
        
        vendor_id = request.data.get('vendor_id')
        order_date = request.data.get('order_date')
        expected_delivery_date = request.data.get('expected_delivery_date')
        
        if not vendor_id or not order_date:
            return Response({"error": "vendor_id and order_date are required."}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            from .models import Vendor, PurchaseOrderLine
            import datetime

            vendor = Vendor.objects.get(id=vendor_id)
            now = datetime.datetime.now()

            with transaction.atomic():
                last_po = PurchaseOrder.objects.select_for_update().order_by('-id').first()
                # Parse max sequence from existing PO numbers to handle ID gaps after deletions
                import re as _re
                max_seq = 0
                for po_num in PurchaseOrder.objects.filter(po_number__startswith=f"PO-{now.year}-").values_list('po_number', flat=True):
                    m = _re.search(r'PO-\d{4}-(\d+)', po_num)
                    if m:
                        max_seq = max(max_seq, int(m.group(1)))
                next_seq = max_seq + 1 if max_seq > 0 else ((last_po.id + 1) if last_po else 1)
                po_number = f"PO-{now.year}-{next_seq:05d}"

                po = PurchaseOrder.objects.create(
                    po_number=po_number,
                    vendor=vendor,
                    purchase_request=pr,
                    order_date=order_date,
                    expected_delivery_date=expected_delivery_date,
                    fund=pr.fund,
                    function=pr.function,
                    program=pr.program,
                    geo=pr.geo,
                    status='Draft'
                )

                po_lines = [
                    PurchaseOrderLine(
                        po=po,
                        item_description=pr_line.item_description,
                        quantity=pr_line.quantity,
                        unit_price=pr_line.estimated_unit_price,
                        account=pr_line.account,
                        asset=pr_line.asset,
                        item=pr_line.item,
                        product_type=pr_line.product_type,
                        product_category=pr_line.product_category,
                    )
                    for pr_line in pr.lines.all()
                ]
                PurchaseOrderLine.objects.bulk_create(po_lines)

            return Response({
                "status": "PO created successfully.",
                "po_id": po.id,
                "po_number": po.po_number
            })
        except Exception as e:
            logger.error("Failed to create PO from PR %s: %s", pr.pk, e)
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

class PurchaseOrderViewSet(viewsets.ModelViewSet):
    queryset = PurchaseOrder.objects.select_related(
        'vendor', 'purchase_request', 'fund', 'function', 'program', 'geo'
    ).prefetch_related('lines').all()
    serializer_class = PurchaseOrderSerializer
    permission_classes = [RBACPermission]
    filterset_fields = ['status', 'vendor']
    pagination_class = ProcurementPagination

    def get_queryset(self):
        return PurchaseOrder.objects.select_related(
            'vendor', 'purchase_request', 'fund', 'function', 'program', 'geo'
        ).annotate(
            computed_subtotal=Coalesce(
                Sum(F('lines__quantity') * F('lines__unit_price'), output_field=DecimalField()),
                Value(0),
                output_field=DecimalField(),
            )
        ).prefetch_related('lines')

    # ─── GRN lock helper ─────────────────────────────────────────────────────
    @staticmethod
    def _active_grn_count(po):
        """Return number of non-Cancelled GRNs for this PO."""
        return GoodsReceivedNote.objects.filter(purchase_order=po).exclude(status='Cancelled').count()

    def update(self, request, *args, **kwargs):
        """Block PO edits when one or more active (non-Cancelled) GRNs exist."""
        po = self.get_object()
        count = self._active_grn_count(po)
        if count > 0:
            return Response(
                {"error": f"Cannot modify PO {po.po_number}: {count} active GRN(s) exist. "
                          "Cancel or reverse all GRNs before editing the PO."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        """Block partial PO edits when active GRNs exist."""
        po = self.get_object()
        count = self._active_grn_count(po)
        if count > 0:
            return Response(
                {"error": f"Cannot modify PO {po.po_number}: {count} active GRN(s) exist. "
                          "Cancel or reverse all GRNs before editing the PO."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().partial_update(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        """Create PO and optionally auto-create a DownPaymentRequest."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        po = serializer.save(created_by=request.user)

        dp_data = request.data.get('down_payment_request')
        if dp_data and dp_data.get('enabled'):
            try:
                DownPaymentRequest.objects.create(
                    purchase_order=po,
                    calc_type=dp_data.get('calc_type', 'percentage'),
                    calc_value=Decimal(str(dp_data.get('calc_value', 0))),
                    requested_amount=Decimal(str(dp_data.get('requested_amount', 0))),
                    payment_method=dp_data.get('payment_method', 'Bank'),
                    bank_account_id=dp_data.get('bank_account') or None,
                    notes=dp_data.get('notes', ''),
                    created_by=request.user,
                )
            except Exception as e:
                logger.warning(f"Failed to create DownPaymentRequest for PO {po.po_number}: {e}")

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    @action(detail=True, methods=['post'])
    def submit_for_approval(self, request, pk=None):
        """Submit PO for approval through the centralized workflow engine."""
        from workflow.views import auto_route_approval
        po = self.get_object()
        if po.status not in ['Draft', 'Rejected']:
            return Response(
                {"error": "Only Draft or Rejected POs can be submitted."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = auto_route_approval(
            po, 'purchaseorder', request,
            title=f"PO-{po.po_number}: {po.vendor.name}",
            amount=_get_doc_amount(po),
        )

        if result.get('auto_approved'):
            po.status = 'Approved'
            msg = "Purchase Order auto-approved (below threshold)."
        else:
            po.status = 'Pending'
            msg = "Purchase Order submitted for approval."

        po.save()
        return Response({"status": msg, "approval_id": result.get('approval_id')})

    @action(detail=True, methods=['post'])
    def post_order(self, request, pk=None):
        order = self.get_object()
        if order.status == 'Posted':
            return Response({"error": "Order already posted."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                order.status = 'Posted'
                order.save()

                # Post to GL in real-time
                journal = TransactionPostingService.post_purchase_order(order)

            logger.info(f"PO {order.po_number} posted with journal {journal.reference_number}")
            return Response({
                "status": "Purchase Order posted and budget reserved.",
                "journal_entry_id": journal.id,
                "journal_number": journal.reference_number
            })
        except Exception as e:
            logger.error(f"Failed to post PO {order.po_number}: {e}")
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def close_order(self, request, pk=None):
        """
        Close a PO. Valid only from Approved or Posted status.
        Blocked when active (non-Cancelled) GRNs exist.
        """
        order = self.get_object()
        if order.status == 'Closed':
            return Response({"error": "Purchase Order is already closed."}, status=status.HTTP_400_BAD_REQUEST)
        if order.status not in ('Approved', 'Posted'):
            return Response(
                {"error": f"Cannot close a PO in '{order.status}' status. "
                          "Only Approved or Posted POs can be closed."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        count = self._active_grn_count(order)
        if count > 0:
            return Response(
                {"error": f"Cannot close PO {order.po_number}: {count} active GRN(s) exist. "
                          "Cancel or reverse all GRNs before closing the PO."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        order.status = 'Closed'
        order.save()
        return Response({"status": "Purchase Order closed."})

    @action(detail=True, methods=['post'])
    def cancel_order(self, request, pk=None):
        """
        Cancel / reject a PO. Maps to 'Rejected' status (the only cancellation state in the PO
        state machine). Blocked when active GRNs or live invoice matchings exist.

        Allowed from: Draft, Pending, Approved.
        Not allowed from: Posted (already committed to GL — use close_order instead), Closed, Rejected.
        """
        order = self.get_object()

        # Already in a terminal/cancelled state
        if order.status == 'Rejected':
            return Response({"error": "Purchase Order is already cancelled (Rejected)."}, status=status.HTTP_400_BAD_REQUEST)
        if order.status in ('Closed',):
            return Response({"error": f"Cannot cancel a {order.status} PO."}, status=status.HTTP_400_BAD_REQUEST)
        if order.status == 'Posted':
            return Response(
                {"error": "Cannot cancel a Posted PO. Reverse the GRNs and use close_order to close it."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Hard block: cannot cancel when GRNs exist
        count = self._active_grn_count(order)
        if count > 0:
            return Response(
                {"error": f"Cannot cancel PO {order.po_number}: {count} active GRN(s) exist. "
                          "Cancel or reverse all GRNs before cancelling the PO."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Also block if any non-rejected invoice matching exists
        active_matching = InvoiceMatching.objects.filter(
            purchase_order=order
        ).exclude(status__in=['Rejected', 'Draft']).count()
        if active_matching > 0:
            return Response(
                {"error": f"Cannot cancel PO {order.po_number}: {active_matching} invoice matching record(s) exist. "
                          "Reject or remove all invoice matchings before cancelling."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 'Rejected' is the cancellation state — valid from Draft, Pending, Approved
        order.status = 'Rejected'
        order.save()
        return Response({"status": f"Purchase Order {order.po_number} cancelled (Rejected)."})

class DownPaymentRequestViewSet(viewsets.ModelViewSet):
    """Finance-facing view to list, review, and process down payment requests."""
    queryset = DownPaymentRequest.objects.select_related(
        'purchase_order', 'purchase_order__vendor', 'bank_account', 'payment'
    ).all()
    serializer_class = DownPaymentRequestSerializer
    permission_classes = [RBACPermission]
    filterset_fields = ['status', 'payment_method', 'purchase_order']
    pagination_class = ProcurementPagination

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        dpr = self.get_object()
        if dpr.status != 'Pending':
            return Response({"error": f"Cannot approve a request in '{dpr.status}' status."}, status=status.HTTP_400_BAD_REQUEST)
        dpr.status = 'Approved'
        dpr.save()
        return Response({"status": "Down payment request approved."})

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        dpr = self.get_object()
        if dpr.status not in ('Pending', 'Approved'):
            return Response({"error": f"Cannot reject a request in '{dpr.status}' status."}, status=status.HTTP_400_BAD_REQUEST)
        dpr.status = 'Rejected'
        dpr.notes = request.data.get('reason', dpr.notes)
        dpr.save()
        return Response({"status": "Down payment request rejected."})

    @action(detail=True, methods=['post'])
    def process(self, request, pk=None):
        """Finance processes the DPR — creates a Draft Payment record and marks DPR as Processed."""
        dpr = self.get_object()
        if dpr.status != 'Approved':
            return Response({"error": "Only approved requests can be processed."}, status=status.HTTP_400_BAD_REQUEST)
        if dpr.payment_id:
            return Response({"error": "A payment has already been created for this request."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            from accounting.models import Payment
            import datetime

            year = datetime.date.today().year
            seq = Payment.objects.filter(payment_number__startswith=f'PAY-{year}-').count() + 1
            payment_number = f'PAY-{year}-{seq:05d}'

            method_map = {'Bank': 'Wire', 'Cash': 'Cash'}
            payment = Payment.objects.create(
                payment_number=payment_number,
                payment_date=datetime.date.today(),
                payment_method=method_map.get(dpr.payment_method, 'Wire'),
                total_amount=dpr.requested_amount,
                vendor=dpr.purchase_order.vendor,
                bank_account=dpr.bank_account,
                is_advance=True,
                advance_type='Supplier Advance',
                advance_remaining=dpr.requested_amount,
                status='Draft',
                reference_number=dpr.request_number,
                created_by=request.user,
            )
            dpr.payment = payment
            dpr.status = 'Processed'
            dpr.save()
            return Response({
                "status": "Payment record created.",
                "payment_id": payment.id,
                "payment_number": payment.payment_number,
            })
        except Exception as e:
            logger.error(f"Failed to process DownPaymentRequest {dpr.request_number}: {e}")
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class GoodsReceivedNoteViewSet(viewsets.ModelViewSet):
    queryset = GoodsReceivedNote.objects.select_related(
        'purchase_order', 'purchase_order__vendor', 'warehouse'
    ).prefetch_related('lines', 'lines__po_line').all()
    serializer_class = GoodsReceivedNoteSerializer
    permission_classes = [RBACPermission]
    filterset_fields = ['status', 'purchase_order']
    pagination_class = ProcurementPagination

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    # ─── Invoice-verification lock ────────────────────────────────────────────
    @staticmethod
    def _invoice_match_lock_reason(grn):
        """
        Return a human-readable error string if this GRN should be locked from editing,
        or None if editing is still allowed.

        Locked when: at least one InvoiceMatching with status Matched or Approved exists
        against this GRN — meaning financial records have already been committed.
        """
        locked_match = InvoiceMatching.objects.filter(
            goods_received_note=grn,
            status__in=['Matched', 'Approved'],
        ).first()
        if locked_match:
            return (
                f"GRN {grn.grn_number} is locked: invoice matching "
                f"'{locked_match.invoice_reference}' has been {locked_match.status.lower()}. "
                "Cancel the invoice matching first before editing this GRN."
            )
        return None

    def update(self, request, *args, **kwargs):
        """Block GRN edits once invoice verification has been matched/approved."""
        grn = self.get_object()
        reason = self._invoice_match_lock_reason(grn)
        if reason:
            return Response({"error": reason}, status=status.HTTP_400_BAD_REQUEST)
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        """Block partial GRN edits once invoice verification has been matched/approved."""
        grn = self.get_object()
        reason = self._invoice_match_lock_reason(grn)
        if reason:
            return Response({"error": reason}, status=status.HTTP_400_BAD_REQUEST)
        return super().partial_update(request, *args, **kwargs)

    @action(detail=True, methods=['post'])
    def submit_for_approval(self, request, pk=None):
        """
        Submit a Draft GRN for warehouse / department approval.

        Status transitions:
          Draft  → On Hold  (awaiting approval in workflow inbox)
          On Hold → Received  (when workflow engine calls _trigger_document_action approve)
          On Hold → Cancelled (when rejected)
        """
        from workflow.views import auto_route_approval
        grn = self.get_object()
        if grn.status not in ['Draft']:
            return Response(
                {"error": f"Only Draft GRNs can be submitted for approval. Current status: '{grn.status}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # BUG-6 FIX: GoodsReceivedNote has no total_amount field — compute from lines.
        grn_amount = sum(
            line.quantity_received * (line.po_line.unit_price or Decimal('0'))
            for line in grn.lines.select_related('po_line').all()
        )
        result = auto_route_approval(
            grn, 'goodsreceivednote', request,
            title=f"GRN-{grn.grn_number}: {grn.purchase_order.vendor.name if grn.purchase_order else 'N/A'}",
            amount=grn_amount,
        )

        if result.get('auto_approved'):
            grn.status = 'Received'
            msg = "GRN auto-approved and marked as Received."
        else:
            grn.status = 'On Hold'
            msg = "GRN submitted for approval. Awaiting review."

        grn.save()
        return Response({"status": msg, "approval_id": result.get('approval_id')})

    @action(detail=True, methods=['post'])
    def post_grn(self, request, pk=None):
        grn = self.get_object()
        if grn.status == 'Posted':
            return Response({"error": "GRN already posted."}, status=status.HTTP_400_BAD_REQUEST)

        # WARN-4 FIX: block posting whenever a Pending approval exists — regardless
        # of GRN status — so stale approvals can't be bypassed via direct status patches.
        from workflow.models import Approval as WorkflowApproval
        if WorkflowApproval.objects.filter(
            content_type=ContentType.objects.get_for_model(grn),
            object_id=grn.pk,
            status='Pending',
        ).exists():
            return Response(
                {"error": "GRN is awaiting workflow approval. Posting is only allowed after the approval is granted."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Require PO to be in an approved/posted state before receiving
        po = grn.purchase_order
        if po.status not in ('Approved', 'Posted', 'Closed'):
            return Response(
                {"error": f"PO must be Approved or Posted before GRN can be posted. Current PO status: {po.status}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # P2P-H1: GRN Quality Enforcement — block GRN posting if quality inspection not passed
        try:
            from quality.models import QualityInspection, QAConfiguration
            # Check if any GRN line items require quality inspection
            for grn_line in grn.lines.select_related('po_line__item', 'po_line__product_type').all():
                po_line = grn_line.po_line
                item = po_line.item
                if not item:
                    continue

                # Check if QA configuration requires inspection for this item's category or product type
                qa_required = QAConfiguration.objects.filter(
                    trigger_event='GRN_Created',
                    is_required=True,
                    is_active=True,
                ).filter(
                    Q(item_category=getattr(item, 'category', None)) |
                    Q(product_type=getattr(item, 'product_type', None)) |
                    Q(item_category__isnull=True, product_type__isnull=True)
                ).exists()

                if qa_required:
                    # Inspection is required — check that one exists AND has passed
                    passed_inspection = QualityInspection.objects.filter(
                        goods_received_note=grn,
                        item=item,
                        status='Passed'
                    ).exists()
                    if not passed_inspection:
                        failed_inspection = QualityInspection.objects.filter(
                            goods_received_note=grn,
                            item=item,
                            status='Failed'
                        ).exists()
                        if failed_inspection:
                            return Response({
                                "error": f"Cannot post GRN: Quality inspection failed for item '{item}'. Clear quality issues before posting.",
                                "grn": grn.grn_number
                            }, status=status.HTTP_400_BAD_REQUEST)
                        else:
                            return Response({
                                "error": f"Quality inspection required before GRN posting for item '{item}'. No passed inspection found.",
                                "grn": grn.grn_number
                            }, status=status.HTTP_400_BAD_REQUEST)
        except ImportError as exc:
            logger.warning("Quality module unavailable, skipping quality check for GRN %s: %s", grn.grn_number, exc)

        try:
            with transaction.atomic():
                # Budget check: verify GRN amount against PO encumbered budget
                from accounting.budget_logic import check_budget_availability
                grn_total = sum(
                    line.quantity_received * (line.po_line.unit_price or Decimal('0'))
                    for line in grn.lines.select_related('po_line').all()
                )
                if po.fund and grn_total > 0:
                    # Use select_for_update on budget to prevent concurrent modifications
                    from accounting.models import Budget as BudgetModel
                    budget_qs = BudgetModel.objects.select_for_update().filter(
                        fund=po.fund, function=po.function, program=po.program, geo=po.geo
                    )
                    # Force evaluation of select_for_update
                    list(budget_qs[:1])

                    allowed, msg = check_budget_availability(
                        dimensions={
                            'mda': po.mda, 'fund': po.fund,
                            'function': po.function, 'program': po.program, 'geo': po.geo,
                        },
                        account=po.lines.first().account if po.lines.exists() else None,
                        amount=grn_total,
                        date=grn.received_date,
                        transaction_type='GRN',
                        transaction_id=grn.pk or 0,
                    )
                    if not allowed:
                        return Response(
                            {"error": f"Budget check failed for GRN: {msg}"},
                            status=status.HTTP_400_BAD_REQUEST,
                        )

                # Validate GRN line quantities before posting (M2)
                for grn_line in grn.lines.select_related('po_line').all():
                    remaining = grn_line.po_line.quantity - grn_line.po_line.quantity_received
                    if grn_line.quantity_received > remaining:
                        return Response(
                            {"error": f"GRN line exceeds PO remaining quantity for '{grn_line.po_line.item_description}'. "
                                      f"Remaining: {remaining}, Received: {grn_line.quantity_received}"},
                            status=status.HTTP_400_BAD_REQUEST,
                        )

                # P2P-L5: Partial invoice cap — if a partial invoice matching already exists for
                # this PO, the total GRN value being posted must not exceed the PO value minus
                # the already-invoiced (Matched/Approved) amount.
                # grn_total was already computed above for the budget check — reuse it here
                # to avoid iterating grn.lines a second time.
                existing_invoiced = InvoiceMatching.objects.filter(
                    purchase_order=po,
                    status__in=['Matched', 'Approved'],
                ).aggregate(
                    total=Coalesce(Sum('invoice_amount'), Value(0), output_field=DecimalField())
                )['total']
                if existing_invoiced > 0:
                    po_total = Decimal(str(po.total_amount or 0))
                    remaining_invoiceable = po_total - existing_invoiced
                    grn_value_decimal = Decimal(str(grn_total))
                    if grn_value_decimal > remaining_invoiceable:
                        return Response(
                            {"error": f"GRN value ({grn_value_decimal}) exceeds the remaining invoiceable amount "
                                      f"({remaining_invoiceable}) on PO {po.po_number}. "
                                      f"Already invoiced: {existing_invoiced}."},
                            status=status.HTTP_400_BAD_REQUEST,
                        )

                # Require warehouse before posting (M3)
                if not grn.warehouse:
                    return Response(
                        {"error": "Warehouse is required for posting"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                grn.status = 'Posted'
                grn.save()

                # Post to GL in real-time.
                # ItemStock and po_line.quantity_received are already updated
                # inside GRN.save() above — do not repeat here.
                journal = TransactionPostingService.post_goods_received_note(grn)

            response_data = {"status": "GRN posted and Inventory updated."}
            if journal:
                response_data["journal_entry_id"] = journal.id
                response_data["journal_number"] = journal.reference_number
            return Response(response_data)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def cancel_grn(self, request, pk=None):
        """Cancel a posted GRN and reverse inventory movements."""
        grn = self.get_object()
        if grn.status == 'Cancelled':
            return Response({"error": "GRN is already cancelled."}, status=status.HTTP_400_BAD_REQUEST)
        # Validate that transition to Cancelled is allowed from current status
        allowed_from = GoodsReceivedNote.ALLOWED_TRANSITIONS.get(grn.status, [])
        if 'Cancelled' not in allowed_from:
            return Response(
                {"error": f"Cannot cancel GRN in '{grn.status}' status. Allowed transitions: {allowed_from}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        # P2P-L4: Prevent GRN cancel if InvoiceMatching exists in any active state.
        # Status list mirrors _invoice_match_lock_reason to ensure consistent enforcement:
        # 'Matched', 'Approved' lock edits; 'Pending_Review' also blocks cancellation
        # since it indicates a verification is in progress.
        if grn.status in ['Received', 'Posted']:
            from procurement.models import InvoiceMatching
            matching_exists = InvoiceMatching.objects.filter(
                goods_received_note=grn,
                status__in=['Matched', 'Approved', 'Pending_Review']
            ).exists()
            if matching_exists:
                return Response({
                    "error": "Cannot cancel GRN: Invoice matching exists. Cancel or remove the matching first."
                }, status=status.HTTP_400_BAD_REQUEST)
        
        if grn.status == 'Draft':
            grn.status = 'Cancelled'
            grn.save()
            return Response({"status": "Draft GRN cancelled."})

        try:
            with transaction.atomic():
                from inventory.models import StockMovement, Warehouse

                # Determine warehouse used for posting
                receiving_warehouse = grn.warehouse
                if not receiving_warehouse:
                    receiving_warehouse = Warehouse.objects.filter(is_active=True).first()

                if grn.status == 'Posted':
                    from inventory.models import ItemStock
                    for grn_line in grn.lines.select_related('po_line', 'po_line__item').all():
                        po_line = grn_line.po_line
                        # Reverse quantity received on PO line
                        po_line.quantity_received = max(0, po_line.quantity_received - grn_line.quantity_received)
                        po_line.save()

                        # Create reverse stock movement and decrement ItemStock.
                        # DOUBLE-UPDATE FIX: use instance pattern + _skip_stock_update
                        # so the post_save signal does NOT also decrement the stock.
                        if po_line.item and grn_line.quantity_received > 0 and receiving_warehouse:
                            rev_movement = StockMovement(
                                item=po_line.item,
                                warehouse=receiving_warehouse,
                                movement_type='OUT',
                                quantity=grn_line.quantity_received,
                                unit_price=po_line.unit_price,
                                reference_number=grn.grn_number,
                                remarks=f"GRN Cancellation: {grn.grn_number}"
                            )
                            rev_movement._skip_stock_update = True
                            rev_movement.save()
                            ItemStock.objects.filter(
                                item=po_line.item,
                                warehouse=receiving_warehouse,
                            ).update(quantity=F('quantity') - grn_line.quantity_received)
                            po_line.item.recalculate_stock_values()

                    # Only re-open PO if it was in Posted status (not Closed)
                    po = grn.purchase_order
                    if po.status == 'Posted':
                        # PO stays in Posted - no status change needed
                        pass

                grn.status = 'Cancelled'
                grn.save()

            return Response({"status": "GRN cancelled and inventory reversed."})
        except Exception as e:
            logger.error(f"Failed to cancel GRN {grn.grn_number}: {e}")
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'])
    def bulk_cancel(self, request):
        """Bulk cancel multiple GRNs."""
        ids = request.data.get('ids', [])
        if not ids:
            return Response({"error": "No GRN IDs provided."}, status=status.HTTP_400_BAD_REQUEST)
        if len(ids) > 100:
            return Response({"error": "Maximum 100 items per bulk operation"}, status=status.HTTP_400_BAD_REQUEST)

        results = []
        for grn_id in ids:
            try:
                grn = GoodsReceivedNote.objects.get(pk=grn_id)
                if grn.status == 'Cancelled':
                    results.append({"id": grn_id, "status": "skipped", "message": "Already cancelled"})
                    continue

                with transaction.atomic():
                    from inventory.models import StockMovement, Warehouse
                    receiving_warehouse = grn.warehouse
                    if not receiving_warehouse:
                        receiving_warehouse = Warehouse.objects.filter(is_active=True).first()

                    if grn.status == 'Posted':
                        from inventory.models import ItemStock
                        for grn_line in grn.lines.select_related('po_line', 'po_line__item').all():
                            po_line = grn_line.po_line
                            po_line.quantity_received = max(0, po_line.quantity_received - grn_line.quantity_received)
                            po_line.save()

                            if po_line.item and grn_line.quantity_received > 0 and receiving_warehouse:
                                # DOUBLE-UPDATE FIX: same pattern as single cancel_grn.
                                bulk_rev = StockMovement(
                                    item=po_line.item,
                                    warehouse=receiving_warehouse,
                                    movement_type='OUT',
                                    quantity=grn_line.quantity_received,
                                    unit_price=po_line.unit_price,
                                    reference_number=grn.grn_number,
                                    remarks=f"GRN Cancellation: {grn.grn_number}"
                                )
                                bulk_rev._skip_stock_update = True
                                bulk_rev.save()
                                ItemStock.objects.filter(
                                    item=po_line.item,
                                    warehouse=receiving_warehouse,
                                ).update(quantity=F('quantity') - grn_line.quantity_received)
                                po_line.item.recalculate_stock_values()

                    grn.status = 'Cancelled'
                    grn.save()
                    results.append({"id": grn_id, "status": "cancelled", "message": "Cancelled successfully"})
            except GoodsReceivedNote.DoesNotExist:
                results.append({"id": grn_id, "status": "error", "message": "GRN not found"})
            except Exception as e:
                results.append({"id": grn_id, "status": "error", "message": str(e)})

        return Response({"results": results})

    @action(detail=True, methods=['post'])
    def create_quality_inspection(self, request, pk=None):
        """Create a quality inspection for this GRN"""
        from quality.models import QualityInspection, InspectionLine
        from django.utils import timezone
        from django.utils.crypto import get_random_string

        grn = self.get_object()

        inspection_number = f"QI-{grn.grn_number}-{get_random_string(4, allowed_chars='0123456789')}"
        
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
        
        for grn_line in grn.lines.all():
            if grn_line.po_line.item:
                InspectionLine.objects.create(
                    inspection=inspection,
                    parameter=f"Quantity Check - {grn_line.po_line.item.name}",
                    specification=f"Expected: {grn_line.quantity_received}",
                    result='Pass'
                )
        
        return Response({
            'status': 'Quality inspection created',
            'inspection_id': inspection.id,
            'inspection_number': inspection.inspection_number
        })

    @action(detail=True, methods=['get'])
    def quality_inspection(self, request, pk=None):
        """Get quality inspection for this GRN if exists"""
        grn = self.get_object()
        inspection = grn.quality_inspections.first()
        
        if not inspection:
            return Response({'error': 'No quality inspection found'}, status=status.HTTP_404_NOT_FOUND)
        
        from quality.serializers import QualityInspectionSerializer
        return Response(QualityInspectionSerializer(inspection).data)

class InvoiceMatchingViewSet(viewsets.ModelViewSet):
    queryset = InvoiceMatching.objects.all().select_related('purchase_order', 'purchase_order__vendor', 'goods_received_note')
    serializer_class = InvoiceMatchingSerializer
    permission_classes = [RBACPermission]
    filterset_fields = ['status', 'purchase_order']

    @action(detail=True, methods=['post'])
    def submit_for_approval(self, request, pk=None):
        """
        Submit a Matched invoice verification record for finance approval.

        The expected flow is:
          Draft → (calculate_match) → Matched → (submit_for_approval) → Pending_Review
          → Workflow approves → Approved   (payment can be released)
          → Workflow rejects  → Rejected
        """
        from workflow.views import auto_route_approval
        matching = self.get_object()
        if matching.status not in ['Draft', 'Matched']:
            return Response(
                {"error": f"Only Draft or Matched invoice records can be submitted. Current status: '{matching.status}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = auto_route_approval(
            matching, 'invoicematching', request,
            title=f"Invoice {matching.invoice_reference}: {matching.purchase_order.vendor.name if matching.purchase_order else 'N/A'}",
            amount=matching.invoice_amount,
        )

        if result.get('auto_approved'):
            matching.status = 'Approved'
            msg = "Invoice verification auto-approved."
        else:
            matching.status = 'Pending_Review'
            msg = "Invoice verification submitted for approval."

        matching.save()
        return Response({"status": msg, "approval_id": result.get('approval_id')})

    @action(detail=True, methods=['post'])
    def match(self, request, pk=None):
        """Manually match an invoice after reviewing variance"""
        matching = self.get_object()

        if matching.status in ('Matched', 'Approved', 'Rejected'):
            return Response(
                {"error": f"Cannot manually match an invoice with status '{matching.status}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Budget check before approving the invoice match
        po = matching.purchase_order
        if po and po.fund and matching.invoice_amount:
            from accounting.budget_logic import check_budget_availability
            allowed, msg = check_budget_availability(
                dimensions={
                    'mda': po.mda, 'fund': po.fund,
                    'function': po.function, 'program': po.program, 'geo': po.geo,
                },
                account=po.lines.first().account if po.lines.exists() else None,
                amount=matching.invoice_amount,
                date=matching.invoice_date,
                transaction_type='INV',
                transaction_id=matching.pk or 0,
            )
            if not allowed:
                return Response(
                    {"error": f"Budget check failed for invoice: {msg}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        variance_reason = request.data.get('variance_reason', '')

        matching.variance_reason = variance_reason
        matching.status = 'Matched'
        matching.matched_date = timezone.now()
        matching.save()

        # Post variance to GL if significant (price diff between PO and invoice)
        variance_amount = getattr(matching, 'variance_amount', None) or Decimal('0')
        journal_ref = None
        if variance_amount and abs(variance_amount) > Decimal('0.01'):
            try:
                from accounting.transaction_posting import get_gl_account
                from accounting.models import JournalHeader, JournalLine
                ap_account = get_gl_account('ACCOUNTS_PAYABLE', 'Liability', 'Payable')
                ppv_account = get_gl_account('PPV', 'Expense', 'Purchase Price Variance')
                if not ppv_account:
                    ppv_account = get_gl_account('PURCHASE_EXPENSE', 'Expense', 'Purchase')

                if ap_account and ppv_account:
                    ppv_journal = JournalHeader.objects.create(
                        posting_date=matching.invoice_date or timezone.now().date(),
                        description=f"Invoice Variance: {matching.invoice_reference} vs PO {matching.purchase_order.po_number if matching.purchase_order else ''}",
                        reference_number=f"PPV-{matching.pk}",
                        mda=matching.purchase_order.mda if matching.purchase_order else None,
                        fund=matching.purchase_order.fund if matching.purchase_order else None,
                        function=matching.purchase_order.function if matching.purchase_order else None,
                        program=matching.purchase_order.program if matching.purchase_order else None,
                        geo=matching.purchase_order.geo if matching.purchase_order else None,
                        status='Posted',
                    )
                    abs_variance = abs(variance_amount)
                    if variance_amount > 0:
                        # Invoice > PO: we owe more — additional AP, PPV is a loss
                        JournalLine.objects.create(header=ppv_journal, account=ppv_account, debit=abs_variance, credit=Decimal('0.00'), memo=f"Purchase price variance: {matching.invoice_reference}")
                        JournalLine.objects.create(header=ppv_journal, account=ap_account, debit=Decimal('0.00'), credit=abs_variance, memo=f"AP adjustment: {matching.invoice_reference}")
                    else:
                        # Invoice < PO: we owe less — reduce AP, PPV is a gain
                        JournalLine.objects.create(header=ppv_journal, account=ap_account, debit=abs_variance, credit=Decimal('0.00'), memo=f"AP reduction: {matching.invoice_reference}")
                        JournalLine.objects.create(header=ppv_journal, account=ppv_account, debit=Decimal('0.00'), credit=abs_variance, memo=f"Purchase price variance gain: {matching.invoice_reference}")
                    from accounting.transaction_posting import TransactionPostingService
                    TransactionPostingService._update_gl_balances(ppv_journal)
                    journal_ref = ppv_journal.reference_number
            except Exception as e:
                logger.warning(f"Variance GL posting failed for matching {matching.pk}: {e}")

        response_data = {"status": "Invoice matched successfully."}
        if journal_ref:
            response_data["variance_journal"] = journal_ref
        return Response(response_data)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """Reject a matching due to significant variance"""
        matching = self.get_object()
        reason = request.data.get('reason', '')
        
        matching.variance_reason = reason
        matching.status = 'Rejected'
        matching.save()
        
        return Response({"status": "Matching rejected."})

    @action(detail=True, methods=['post'])
    def calculate_match(self, request, pk=None):
        """Auto-calculate match between PO, GRN, and Invoice"""
        matching = self.get_object()

        if matching.status in ('Approved', 'Rejected'):
            return Response(
                {"error": f"Cannot recalculate a match that is already '{matching.status}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        matching.calculate_match()
        matching.save()
        
        return Response({
            "status": "Match calculated",
            "match_type": matching.match_type,
            "po_amount": matching.po_amount,
            "grn_amount": matching.grn_amount,
            "invoice_amount": matching.invoice_amount,
            "variance_amount": matching.variance_amount,
            "variance_percentage": matching.variance_percentage,
            "status": matching.status
        })

    @action(detail=False, methods=['get'])
    def pending(self, request):
        """Get all pending matchings"""
        pending = InvoiceMatching.objects.filter(status__in=['Draft', 'Pending_Review', 'Variance'])
        serializer = self.get_serializer(pending, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def apply_down_payment(self, request, pk=None):
        """
        Deduct an existing down payment / advance from this invoice matching.

        Body: { "amount": <decimal> }   — optional; omit to apply the full available advance.

        Rules enforced:
        - The PO must have a Processed DownPaymentRequest with an associated Payment.
        - The deduction cannot exceed the invoice amount or the advance_remaining balance.
        - Idempotent on re-apply: previous down_payment_applied is credited back to advance_remaining
          before the new amount is applied (allows adjustments).
        """
        matching = self.get_object()

        if not matching.purchase_order_id:
            return Response({"error": "No purchase order linked to this invoice matching."},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            dpr = DownPaymentRequest.objects.filter(
                purchase_order_id=matching.purchase_order_id,
                status='Processed',
            ).select_related('payment').first()
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        if not dpr or not dpr.payment:
            return Response(
                {"error": "No processed down payment found for this PO."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        payment = dpr.payment
        # Restore any amount previously applied so the pool is correctly sized for re-application
        previously_applied = matching.down_payment_applied or Decimal('0')

        available = payment.advance_remaining + previously_applied  # pool before this invoice's claim

        # Determine requested amount (default: apply as much as possible)
        raw_amount = request.data.get('amount')
        if raw_amount is not None:
            try:
                requested = Decimal(str(raw_amount))
            except Exception:
                return Response({"error": "Invalid amount."}, status=status.HTTP_400_BAD_REQUEST)
            if requested < Decimal('0'):
                return Response({"error": "Amount cannot be negative."}, status=status.HTTP_400_BAD_REQUEST)
        else:
            requested = available  # apply all available

        # Cap at invoice amount and available balance
        to_apply = min(requested, matching.invoice_amount, available)

        with transaction.atomic():
            # Update advance_remaining on the Payment record
            payment.advance_remaining = available - to_apply
            payment.save(update_fields=['advance_remaining'])

            # Record on matching
            matching.down_payment_applied = to_apply
            matching.save(update_fields=['down_payment_applied'])

        return Response({
            "status": "Down payment applied.",
            "down_payment_applied": str(to_apply),
            "net_payable": str(matching.net_payable),
            "advance_remaining": str(payment.advance_remaining),
        })

class VendorCreditNoteViewSet(viewsets.ModelViewSet):
    queryset = VendorCreditNote.objects.all().select_related('vendor', 'purchase_order', 'goods_received_note', 'journal_entry')
    serializer_class = VendorCreditNoteSerializer
    permission_classes = [RBACPermission]
    search_fields = ['credit_note_number', 'vendor__name']
    filterset_fields = ['vendor', 'status']
    pagination_class = ProcurementPagination

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """Approve the credit note"""
        credit_note = self.get_object()
        if credit_note.status != 'Draft':
            return Response({"error": "Only draft credit notes can be approved"}, status=status.HTTP_400_BAD_REQUEST)
        credit_note.status = 'Approved'
        credit_note.save()
        return Response({"status": "Credit note approved"})

    @action(detail=True, methods=['post'])
    def post_to_gl(self, request, pk=None):
        """Post credit note to general ledger"""
        credit_note = self.get_object()
        
        if credit_note.status != 'Approved':
            return Response({"error": "Credit note must be approved before posting"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            journal = TransactionPostingService.post_vendor_credit_note(credit_note)
            credit_note.journal_entry = journal
            credit_note.status = 'Posted'
            credit_note.save()
            return Response({
                "status": "Posted to GL",
                "journal_number": journal.reference_number,
                "journal_id": journal.id
            })
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def void(self, request, pk=None):
        """Void the credit note"""
        credit_note = self.get_object()
        if credit_note.status == 'Posted':
            return Response({"error": "Cannot void a posted credit note"}, status=status.HTTP_400_BAD_REQUEST)
        credit_note.status = 'Void'
        credit_note.save()
        return Response({"status": "Credit note voided"})
class VendorDebitNoteViewSet(viewsets.ModelViewSet):
    queryset = VendorDebitNote.objects.all().select_related('vendor', 'purchase_order', 'journal_entry')
    serializer_class = VendorDebitNoteSerializer
    permission_classes = [RBACPermission]
    search_fields = ['debit_note_number', 'vendor__name']
    filterset_fields = ['vendor', 'status']
    pagination_class = ProcurementPagination

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """Approve the debit note"""
        debit_note = self.get_object()
        if debit_note.status != 'Draft':
            return Response({"error": "Only draft debit notes can be approved"}, status=status.HTTP_400_BAD_REQUEST)
        debit_note.status = 'Approved'
        debit_note.save()
        return Response({"status": "Debit note approved"})

    @action(detail=True, methods=['post'])
    def post_to_gl(self, request, pk=None):
        """Post debit note to general ledger"""
        debit_note = self.get_object()
        
        if debit_note.status != 'Approved':
            return Response({"error": "Debit note must be approved before posting"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            journal = TransactionPostingService.post_vendor_debit_note(debit_note)
            debit_note.journal_entry = journal
            debit_note.status = 'Posted'
            debit_note.save()
            return Response({
                "status": "Posted to GL",
                "journal_number": journal.reference_number,
                "journal_id": journal.id
            })
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def void(self, request, pk=None):
        """Void the debit note"""
        debit_note = self.get_object()
        if debit_note.status == 'Posted':
            return Response({"error": "Cannot void a posted debit note"}, status=status.HTTP_400_BAD_REQUEST)
        debit_note.status = 'Void'
        debit_note.save()
        return Response({"status": "Debit note voided"})
class PurchaseReturnViewSet(viewsets.ModelViewSet):
    queryset = PurchaseReturn.objects.all().select_related(
        'vendor', 'purchase_order', 'goods_received_note', 'credit_note'
    ).prefetch_related('lines', 'lines__item', 'lines__po_line')
    serializer_class = PurchaseReturnSerializer
    permission_classes = [RBACPermission]
    search_fields = ['return_number', 'vendor__name']
    filterset_fields = ['vendor', 'status', 'purchase_order']
    pagination_class = ProcurementPagination

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    # ─── Workflow actions ──────────────────────────────────────────────────────

    @action(detail=True, methods=['post'])
    def submit_for_approval(self, request, pk=None):
        """Submit a Draft return through the centralized workflow engine (Draft → Pending)."""
        from workflow.views import auto_route_approval
        ret = self.get_object()
        if ret.status != 'Draft':
            return Response(
                {"error": f"Only Draft returns can be submitted. Current status: '{ret.status}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not ret.lines.exists():
            return Response(
                {"error": "Cannot submit a return with no line items. Add at least one item to return."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = auto_route_approval(
            ret, 'purchasereturn', request,
            title=f"Return {ret.return_number}: {ret.vendor.name if ret.vendor else 'N/A'}",
            amount=_get_doc_amount(ret),
        )

        if result.get('auto_approved'):
            ret.status = 'Approved'
            msg = "Purchase return auto-approved."
        else:
            ret.status = 'Pending'
            msg = "Purchase return submitted for approval."

        ret.save()
        return Response({
            "status": msg,
            "return_number": ret.return_number,
            "approval_id": result.get('approval_id'),
        })

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """Approve a Pending return (Pending → Approved). Fixed: was incorrectly checking for Draft."""
        ret = self.get_object()
        if ret.status != 'Pending':
            return Response(
                {"error": f"Only Pending returns can be approved. Current status: '{ret.status}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        ret.status = 'Approved'
        ret.save()
        return Response({"status": "Purchase return approved.", "return_number": ret.return_number})

    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        """
        Complete a return (Approved → Completed).

        Atomically:
        1. Recalculates total_amount from lines.
        2. Decrements inventory (StockMovement OUT) for lines with item FK.
        3. Posts GL reversal via TransactionPostingService.
        4. Auto-creates a VendorCreditNote for the return value if one doesn't exist.
        """
        ret = self.get_object()
        if ret.status != 'Approved':
            return Response(
                {"error": "Return must be in Approved status before completing."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not ret.lines.exists():
            return Response(
                {"error": "Cannot complete a return with no line items."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with transaction.atomic():
                # Step 1 — Recalculate total
                ret.update_total()
                ret.refresh_from_db()

                # Step 2 — Resolve warehouse
                from inventory.models import StockMovement, Warehouse
                warehouse_id = request.data.get('warehouse_id')
                warehouse = None
                if warehouse_id:
                    warehouse = Warehouse.objects.filter(id=warehouse_id, is_active=True).first()
                if not warehouse and ret.goods_received_note:
                    warehouse = getattr(ret.goods_received_note, 'warehouse', None)
                if not warehouse:
                    warehouse = Warehouse.objects.filter(is_active=True).first()
                if not warehouse:
                    raise ValueError("No active warehouse found. Please set up a warehouse before completing a return.")

                # Step 3 — Stock movements (OUT) + ItemStock decrement for inventory tracking
                # DOUBLE-UPDATE FIX: instance pattern + _skip_stock_update so the
                # post_save signal does NOT also decrement — the explicit F() update is
                # the single authoritative write (same pattern as GRN cancel).
                from inventory.models import ItemStock
                for line in ret.lines.select_related('item').all():
                    if line.item:
                        ret_movement = StockMovement(
                            item=line.item,
                            warehouse=warehouse,
                            movement_type='OUT',
                            quantity=line.quantity,
                            unit_price=line.unit_price,
                            reference_number=ret.return_number,
                            remarks=f"Purchase Return: {ret.return_number} — {line.display_description}",
                        )
                        ret_movement._skip_stock_update = True
                        ret_movement.save()
                        ItemStock.objects.filter(
                            item=line.item,
                            warehouse=warehouse,
                        ).update(quantity=F('quantity') - line.quantity)
                        line.item.recalculate_stock_values()

                # Step 4 — Mark Completed
                ret.status = 'Completed'
                ret.save()

                # Step 5 — Post GL reversal
                journal_ref = None
                try:
                    journal = TransactionPostingService.post_purchase_return(ret)
                    journal_ref = journal.reference_number
                    logger.info(f"Purchase return {ret.return_number} GL posted: {journal_ref}")
                except Exception as e:
                    logger.error(f"GL posting failed for purchase return {ret.return_number}: {e}")
                    # Non-fatal: complete the return but log the GL failure for manual correction

                # Step 6 — Auto-create VendorCreditNote if none linked
                credit_note_number = None
                if not ret.credit_note_id and ret.total_amount > 0:
                    try:
                        import datetime
                        year = datetime.date.today().year
                        cn_prefix = f'CN-{year}-'
                        # Race-safe: lock last CN row and derive next seq from its number
                        last_cn = (
                            VendorCreditNote.objects
                            .select_for_update()
                            .filter(credit_note_number__startswith=cn_prefix)
                            .order_by('-credit_note_number')
                            .first()
                        )
                        if last_cn and last_cn.credit_note_number:
                            try:
                                cn_seq = int(last_cn.credit_note_number.split('-')[-1]) + 1
                            except (ValueError, IndexError):
                                cn_seq = VendorCreditNote.objects.filter(
                                    credit_note_number__startswith=cn_prefix
                                ).count() + 1
                        else:
                            cn_seq = 1
                        credit_note_number = f'{cn_prefix}{cn_seq:05d}'

                        credit_note = VendorCreditNote.objects.create(
                            credit_note_number=credit_note_number,
                            vendor=ret.vendor,
                            purchase_order=ret.purchase_order,
                            goods_received_note=ret.goods_received_note,
                            credit_note_date=ret.return_date,
                            reason=f"Purchase Return {ret.return_number}: {ret.reason[:200]}",
                            amount=ret.total_amount,
                            tax_amount=Decimal('0'),
                            # total_amount is required (no DB default); equals amount + tax_amount
                            total_amount=ret.total_amount,
                            status='Draft',
                        )
                        ret.credit_note = credit_note
                        PurchaseReturn.objects.filter(pk=ret.pk).update(credit_note=credit_note)
                    except Exception as e:
                        logger.error(f"Credit note auto-creation failed for {ret.return_number}: {e}")

            return Response({
                "status": "Purchase return completed.",
                "return_number": ret.return_number,
                "total_amount": str(ret.total_amount),
                "credit_note_number": credit_note_number,
                "journal_reference": journal_ref,
            })
        except Exception as e:
            logger.error(f"Failed to complete purchase return {ret.return_number}: {e}")
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel a return. Not allowed once Completed."""
        ret = self.get_object()
        if ret.status == 'Completed':
            return Response(
                {"error": "Cannot cancel a Completed return. It has already been processed."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if ret.status == 'Cancelled':
            return Response({"error": "Return is already cancelled."}, status=status.HTTP_400_BAD_REQUEST)
        ret.status = 'Cancelled'
        ret.save()
        return Response({"status": "Purchase return cancelled.", "return_number": ret.return_number})
