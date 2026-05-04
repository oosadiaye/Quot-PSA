import logging

from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from core.permissions import IsApprover, RBACPermission

from django.db import transaction
from django.db.models import Sum, F, Q, Value, DecimalField
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from decimal import Decimal
from .models import Vendor, VendorCategory, PurchaseRequest, PurchaseOrder, GoodsReceivedNote, InvoiceMatching, VendorCreditNote, VendorDebitNote, PurchaseReturn, DownPaymentRequest
from .serializers import (
    VendorSerializer, VendorCategorySerializer, PurchaseRequestSerializer, PurchaseOrderSerializer,
    GoodsReceivedNoteSerializer, InvoiceMatchingSerializer,
    VendorCreditNoteSerializer, VendorDebitNoteSerializer, PurchaseReturnSerializer,
    DownPaymentRequestSerializer,
)
from accounting.transaction_posting import TransactionPostingService
from accounting.models import BudgetEncumbrance   # BUG-3 FIX: was missing, caused NameError in PR approve
from core.mixins import OrganizationFilterMixin

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
    queryset = Vendor.objects.all().select_related('category', 'registration_fiscal_year')
    serializer_class = VendorSerializer
    permission_classes = [RBACPermission]
    search_fields = ['name', 'code', 'registration_number', 'bank_name']
    filterset_fields = ['is_active', 'category']
    pagination_class = ProcurementPagination

    def _invoice_gate_enabled(self) -> bool:
        """Check if vendor registration invoice gate is enabled in settings."""
        from accounting.models import AccountingSettings
        settings_obj = AccountingSettings.objects.first()
        return settings_obj.require_vendor_registration_invoice if settings_obj else True

    def perform_create(self, serializer):
        """Force is_active based on invoice gate setting.

        Gate ON  → is_active=False (vendor must pay registration invoice first)
        Gate OFF → is_active=True  (vendor created active immediately)
        """
        if self._invoice_gate_enabled():
            serializer.save(is_active=False)
        else:
            serializer.save(is_active=True)

    def get_queryset(self):
        from datetime import date
        qs = Vendor.objects.select_related('category', 'registration_fiscal_year').annotate(
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
        # Default list excludes expired & pending-activation vendors
        if self.action == 'list':
            qs = qs.filter(
                is_active=True,
            ).filter(
                Q(expiry_date__gte=date.today()) | Q(expiry_date__isnull=True)
            )
        return qs

    @action(detail=False, methods=['get'])
    def active(self, request):
        """List vendors with valid registration (not expired)."""
        from datetime import date
        qs = self.get_queryset().filter(
            is_active=True,
        ).filter(
            Q(expiry_date__gte=date.today()) | Q(expiry_date__isnull=True)
        )
        search = request.query_params.get('search', '')
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(code__icontains=search))
        serializer = self.get_serializer(qs[:100], many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def expired(self, request):
        """List vendors whose registration has expired."""
        from datetime import date
        qs = self.get_queryset().filter(
            expiry_date__lt=date.today(),
        )
        search = request.query_params.get('search', '')
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(code__icontains=search))
        serializer = self.get_serializer(qs[:100], many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def invoice_gate_status(self, request):
        """Return whether vendor registration invoice gate is enabled."""
        return Response({'enabled': self._invoice_gate_enabled()})

    @action(detail=False, methods=['get'])
    def pending_activation(self, request):
        """List newly registered vendors awaiting payment activation."""
        qs = self.get_queryset().filter(
            is_active=False, registration_date__isnull=True,
        )
        search = request.query_params.get('search', '')
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(code__icontains=search))
        serializer = self.get_serializer(qs[:100], many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def generate_registration_invoice(self, request, pk=None):
        """Generate a registration invoice for a new (inactive) vendor.

        Same flow as renewal but for initial activation.
        Only available when invoice gate is enabled.
        """
        if not self._invoice_gate_enabled():
            return Response(
                {'error': 'Invoice gate is disabled. Vendors are activated without invoices.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        vendor = self.get_object()
        if vendor.is_active:
            return Response({'error': 'Vendor is already active'}, status=status.HTTP_400_BAD_REQUEST)

        amount = request.data.get('amount')
        tsa_account_id = request.data.get('tsa_account_id')
        fiscal_year_id = request.data.get('fiscal_year_id')

        if not amount or not tsa_account_id or not fiscal_year_id:
            return Response(
                {'error': 'amount, tsa_account_id, and fiscal_year_id are required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from accounting.models.advanced import FiscalYear
        from accounting.models.treasury import TreasuryAccount
        from .models import VendorRenewalInvoice

        fy = FiscalYear.objects.filter(pk=fiscal_year_id).first()
        tsa = TreasuryAccount.objects.filter(pk=tsa_account_id).first()
        if not fy:
            return Response({'error': 'Fiscal year not found'}, status=status.HTTP_400_BAD_REQUEST)
        if not tsa:
            return Response({'error': 'TSA account not found'}, status=status.HTTP_400_BAD_REQUEST)

        invoice = VendorRenewalInvoice.objects.create(
            invoice_type='REGISTRATION',
            vendor=vendor,
            fiscal_year=fy,
            amount=Decimal(str(amount)),
            tsa_account=tsa,
            due_date=request.data.get('due_date') or fy.end_date,
            notes=request.data.get('notes', ''),
        )

        return Response({
            'id': invoice.id,
            'invoice_number': invoice.invoice_number,
            'invoice_type': 'REGISTRATION',
            'vendor_name': vendor.name,
            'vendor_code': vendor.code,
            'amount': str(invoice.amount),
            'fiscal_year': fy.name or f'FY {fy.year}',
            'tsa_account_number': tsa.account_number,
            'tsa_account_name': tsa.account_name,
            'tsa_bank': tsa.bank,
            'invoice_date': str(invoice.invoice_date),
            'due_date': str(invoice.due_date) if invoice.due_date else None,
            'status': invoice.status,
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def confirm_registration_payment(self, request, pk=None):
        """Confirm initial registration payment → activate vendor + 1 year validity.

        DR TSA Bank Account (cash received)
        CR Revenue - Registration Fees (income recognized)
        Then activates the vendor with 1-year expiry from payment date.
        """
        vendor = self.get_object()
        invoice_id = request.data.get('invoice_id')
        payment_reference = request.data.get('payment_reference', '')

        if not invoice_id:
            return Response({'error': 'invoice_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        from .models import VendorRenewalInvoice
        invoice = VendorRenewalInvoice.objects.filter(
            pk=invoice_id, vendor=vendor, invoice_type='REGISTRATION',
        ).first()
        if not invoice:
            return Response({'error': 'Registration invoice not found'}, status=status.HTTP_400_BAD_REQUEST)
        if invoice.status == 'PAID':
            return Response({'error': 'Invoice already paid'}, status=status.HTTP_400_BAD_REQUEST)

        # Post GL entry: DR TSA, CR Revenue
        from accounting.models.gl import JournalHeader, JournalLine, TransactionSequence, Account
        from accounting.models.ncoa import EconomicSegment
        from accounting.services.ipsas_journal_service import IPSASJournalService
        from accounting.services.treasury_service import TSABalanceService
        from datetime import timedelta

        ref = TransactionSequence.get_next('journal', 'JE-')
        # ``document_number`` is the operator-facing JV-#### identifier
        # the Journal Entries list shows in its DOCUMENT NO column.
        # Earlier code only set ``reference_number``, which left the
        # column rendering "-". Pulling the JV sequence here keeps the
        # column populated for vendor-registration revenue postings the
        # same way AP/AR/Payment journals do.
        jv_number = TransactionSequence.get_next('journal_voucher', 'JV-')
        header = JournalHeader.objects.create(
            reference_number=ref,
            description=f"Vendor Registration: {vendor.name} — {invoice.invoice_number}",
            posting_date=timezone.now().date(),
            document_number=jv_number,
            status='Draft',
            source_module='vendor_registration',
            source_document_id=invoice.pk,
        )

        # ── DR: TSA cash GL ──────────────────────────────────────
        # Resolved via the central tsa_gl_resolver (per-TSA → tenant
        # default → COA scan). Same code path as treasury revenue and
        # payment voucher postings, so registration receipts can never
        # disagree about which cash GL to hit. No hardcoded code.
        from accounting.services.tsa_gl_resolver import resolve_tsa_cash_gl
        try:
            tsa_gl = resolve_tsa_cash_gl(tsa_account=invoice.tsa_account)
        except Exception as exc:
            header.delete()
            return Response(
                {'error': f'Cannot resolve TSA cash GL: {exc}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ── CR: Registration-fee revenue GL ──────────────────────
        # Priority chain mirrors the cash side:
        #   1. AccountingSettings.vendor_registration_revenue_account (FK)
        #   2. Legacy NCoA bridge to 12100200 if the catalogue has it
        #   3. Loud failure with operator-actionable message
        from accounting.models import AccountingSettings
        settings_obj = AccountingSettings.objects.first()
        rev_gl = getattr(settings_obj, 'vendor_registration_revenue_account', None) if settings_obj else None
        if rev_gl is None:
            # Tenant hasn't configured the FK yet — try the conventional
            # NCoA code as a soft fallback so existing seeded tenants
            # keep working until an operator picks an explicit account.
            rev_seg = EconomicSegment.objects.filter(code='12100200').first()
            rev_gl = (
                rev_seg.legacy_account if rev_seg
                else Account.objects.filter(
                    account_type='Income', name__icontains='registration',
                ).first()
            )
        if not rev_gl:
            header.delete()
            return Response(
                {'error': (
                    'Registration-fee revenue account is not configured. Set it in '
                    'Settings → Accounting → Vendor Registration Revenue Account, '
                    'or add an Income account named like "Registration Fees" to the '
                    'Chart of Accounts.'
                )},
                status=status.HTTP_400_BAD_REQUEST,
            )

        JournalLine.objects.create(
            header=header, account=tsa_gl,
            debit=invoice.amount, credit=0,
            memo=f"Registration payment: {vendor.name}",
        )
        JournalLine.objects.create(
            header=header, account=rev_gl,
            debit=0, credit=invoice.amount,
            memo=f"Registration fee: {invoice.invoice_number}",
        )

        IPSASJournalService.post_journal(header, request.user)

        TSABalanceService.process_revenue(type('RC', (), {
            'tsa_account': invoice.tsa_account,
            'amount': invoice.amount,
            'receipt_number': invoice.invoice_number,
        })())

        # Update invoice
        invoice.status = 'PAID'
        invoice.payment_reference = payment_reference
        invoice.payment_date = timezone.now().date()
        invoice.journal = header
        invoice.save(update_fields=['status', 'payment_reference', 'payment_date', 'journal', 'updated_at'])

        # Activate vendor — 1 year from payment date
        today = timezone.now().date()
        vendor.registration_fiscal_year = invoice.fiscal_year
        vendor.registration_date = today
        vendor.expiry_date = today + timedelta(days=365)
        vendor.is_active = True
        vendor.save(update_fields=[
            'registration_fiscal_year', 'registration_date',
            'expiry_date', 'is_active', 'updated_at',
        ])

        return Response({
            'status': 'Payment confirmed. Vendor activated.',
            'invoice_number': invoice.invoice_number,
            'journal_id': header.id,
            'vendor_status': 'ACTIVE',
            'registration_date': str(vendor.registration_date),
            'expiry_date': str(vendor.expiry_date),
        })

    @action(detail=True, methods=['post'])
    def renew(self, request, pk=None):
        """Renew a vendor's registration for a new fiscal year.

        Only available when invoice gate is disabled.
        """
        if self._invoice_gate_enabled():
            return Response(
                {'error': 'Invoice gate is enabled. Use generate_renewal_invoice instead.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        vendor = self.get_object()
        fiscal_year_id = request.data.get('fiscal_year_id')
        expiry_date = request.data.get('expiry_date')

        if not fiscal_year_id:
            return Response({'error': 'fiscal_year_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        from accounting.models.advanced import FiscalYear
        fy = FiscalYear.objects.filter(pk=fiscal_year_id).first()
        if not fy:
            return Response({'error': 'Fiscal year not found'}, status=status.HTTP_400_BAD_REQUEST)

        vendor.registration_fiscal_year = fy
        vendor.registration_date = timezone.now().date()
        vendor.expiry_date = expiry_date or fy.end_date
        vendor.is_active = True
        vendor.save(update_fields=[
            'registration_fiscal_year', 'registration_date',
            'expiry_date', 'is_active', 'updated_at',
        ])

        return Response(VendorSerializer(vendor).data)

    @action(detail=True, methods=['post'])
    def direct_renew(self, request, pk=None):
        """Directly renew a vendor for 1 year without invoice (when gate is disabled)."""
        if self._invoice_gate_enabled():
            return Response(
                {'error': 'Invoice gate is enabled. Use generate_renewal_invoice instead.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        vendor = self.get_object()
        from datetime import timedelta
        today = timezone.now().date()
        vendor.registration_date = today
        vendor.expiry_date = today + timedelta(days=365)
        vendor.is_active = True
        vendor.save(update_fields=[
            'registration_date', 'expiry_date', 'is_active', 'updated_at',
        ])
        return Response({
            'status': 'Vendor renewed for 1 year.',
            'vendor_name': vendor.name,
            'registration_date': str(vendor.registration_date),
            'expiry_date': str(vendor.expiry_date),
        })

    @action(detail=True, methods=['post'])
    def generate_renewal_invoice(self, request, pk=None):
        """Generate a renewal invoice for an expired vendor.

        Creates an invoice with TSA bank details for the vendor to pay.
        Only available when invoice gate is enabled.
        """
        if not self._invoice_gate_enabled():
            return Response(
                {'error': 'Invoice gate is disabled. Use direct_renew instead.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        vendor = self.get_object()
        amount = request.data.get('amount')
        tsa_account_id = request.data.get('tsa_account_id')
        fiscal_year_id = request.data.get('fiscal_year_id')

        if not amount or not tsa_account_id or not fiscal_year_id:
            return Response(
                {'error': 'amount, tsa_account_id, and fiscal_year_id are required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from accounting.models.advanced import FiscalYear
        from accounting.models.treasury import TreasuryAccount
        from .models import VendorRenewalInvoice

        fy = FiscalYear.objects.filter(pk=fiscal_year_id).first()
        tsa = TreasuryAccount.objects.filter(pk=tsa_account_id).first()
        if not fy:
            return Response({'error': 'Fiscal year not found'}, status=status.HTTP_400_BAD_REQUEST)
        if not tsa:
            return Response({'error': 'TSA account not found'}, status=status.HTTP_400_BAD_REQUEST)

        invoice = VendorRenewalInvoice.objects.create(
            vendor=vendor,
            fiscal_year=fy,
            amount=Decimal(str(amount)),
            tsa_account=tsa,
            due_date=request.data.get('due_date') or fy.end_date,
            notes=request.data.get('notes', ''),
        )

        return Response({
            'id': invoice.id,
            'invoice_number': invoice.invoice_number,
            'vendor_name': vendor.name,
            'vendor_code': vendor.code,
            'amount': str(invoice.amount),
            'fiscal_year': fy.name or f'FY {fy.year}',
            'tsa_account_number': tsa.account_number,
            'tsa_account_name': tsa.account_name,
            'tsa_bank': tsa.bank,
            'invoice_date': str(invoice.invoice_date),
            'due_date': str(invoice.due_date) if invoice.due_date else None,
            'status': invoice.status,
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def confirm_renewal_payment(self, request, pk=None):
        """Confirm vendor renewal payment and post GL entry.

        DR TSA Bank Account (cash received)
        CR Revenue - Registration Fees (income recognized)
        Then renews the vendor registration.
        """
        vendor = self.get_object()
        invoice_id = request.data.get('invoice_id')
        payment_reference = request.data.get('payment_reference', '')

        if not invoice_id:
            return Response({'error': 'invoice_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        from .models import VendorRenewalInvoice
        invoice = VendorRenewalInvoice.objects.filter(
            pk=invoice_id, vendor=vendor, invoice_type='RENEWAL',
        ).first()
        if not invoice:
            return Response({'error': 'Renewal invoice not found'}, status=status.HTTP_400_BAD_REQUEST)
        if invoice.status == 'PAID':
            return Response({'error': 'Invoice already paid'}, status=status.HTTP_400_BAD_REQUEST)

        # Post GL entry: DR TSA, CR Revenue
        from accounting.models.gl import JournalHeader, JournalLine, TransactionSequence, Account
        from accounting.models.ncoa import EconomicSegment
        from accounting.services.ipsas_journal_service import IPSASJournalService
        from accounting.services.treasury_service import TSABalanceService

        ref = TransactionSequence.get_next('journal', 'JE-')
        # See companion fix in approve_registration_invoice — JV-####
        # document number kept in sync with the JE- reference so the
        # Journal Entries list always shows a populated DOCUMENT NO.
        jv_number = TransactionSequence.get_next('journal_voucher', 'JV-')
        header = JournalHeader.objects.create(
            reference_number=ref,
            description=f"Vendor Renewal: {vendor.name} — {invoice.invoice_number}",
            posting_date=timezone.now().date(),
            document_number=jv_number,
            status='Draft',
            source_module='vendor_renewal',
            source_document_id=invoice.pk,
        )

        # DR: TSA Bank Account
        tsa_seg = EconomicSegment.objects.filter(code='31100100').first()
        tsa_gl = tsa_seg.legacy_account if tsa_seg else Account.objects.filter(code='31100100').first()
        if not tsa_gl:
            header.delete()
            return Response(
                {'error': 'TSA Cash account (31100100) not found in Chart of Accounts.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # CR: Revenue - Registration Fees
        rev_seg = EconomicSegment.objects.filter(code='12100200').first()
        rev_gl = rev_seg.legacy_account if rev_seg else Account.objects.filter(
            account_type='Income', name__icontains='fee'
        ).first()
        if not rev_gl:
            header.delete()
            return Response(
                {'error': 'Revenue account (Registration Fees / 12100200) not found in Chart of Accounts.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        JournalLine.objects.create(
            header=header, account=tsa_gl,
            debit=invoice.amount, credit=0,
            memo=f"Renewal payment: {vendor.name}",
        )
        JournalLine.objects.create(
            header=header, account=rev_gl,
            debit=0, credit=invoice.amount,
            memo=f"Renewal fee: {invoice.invoice_number}",
        )

        IPSASJournalService.post_journal(header, request.user)

        TSABalanceService.process_revenue(type('RC', (), {
            'tsa_account': invoice.tsa_account,
            'amount': invoice.amount,
            'receipt_number': invoice.invoice_number,
        })())

        # Update invoice
        invoice.status = 'PAID'
        invoice.payment_reference = payment_reference
        invoice.payment_date = timezone.now().date()
        invoice.journal = header
        invoice.save(update_fields=['status', 'payment_reference', 'payment_date', 'journal', 'updated_at'])

        # Renew vendor registration — 1 year from payment date
        from datetime import timedelta
        today = timezone.now().date()
        vendor.registration_fiscal_year = invoice.fiscal_year
        vendor.registration_date = today
        vendor.expiry_date = today + timedelta(days=365)
        vendor.is_active = True
        vendor.save(update_fields=[
            'registration_fiscal_year', 'registration_date',
            'expiry_date', 'is_active', 'updated_at',
        ])

        return Response({
            'status': 'Payment confirmed. Vendor renewed.',
            'invoice_number': invoice.invoice_number,
            'journal_id': header.id,
            'vendor_status': 'ACTIVE',
            'registration_date': str(vendor.registration_date),
            'expiry_date': str(vendor.expiry_date),
        })

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

class PurchaseRequestViewSet(OrganizationFilterMixin, viewsets.ModelViewSet):
    org_filter_field = 'mda'
    queryset = PurchaseRequest.objects.select_related(
        'fund', 'function', 'program', 'geo', 'mda',
    ).prefetch_related(
        'lines', 'lines__account', 'lines__asset', 'lines__item',
    ).all()
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
        if pr.status not in ('Draft', 'Pending'):
            return Response({"error": "Only Draft or Pending PRs can be approved."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                # P2P-H3: Budget Encumbrance on PR Approval
                # Create budget encumbrance when PR is approved
                # Budget check uses MDA + Economic Code (account) + Fund only.
                # Function, Programme, Geo are for reporting — not budget gating.
                budget_totals = {}
                for line in pr.lines.all():
                    if not line.account_id:
                        continue
                    key = (line.account, pr.mda, pr.fund)
                    amount = line.estimated_unit_price * line.quantity
                    budget_totals[key] = budget_totals.get(key, Decimal('0.00')) + amount

                # ── Rule-driven budget check — same engine as JV / AP / PO ──
                # Previously this block only consulted the legacy
                # ``Budget`` table via ``get_active_budget``, which meant
                # tenants running on ``Appropriation`` (the modern
                # NCoA-segmented register) always got "No active budget
                # found" even when ₦Xm was sitting active on the
                # Appropriation report. Route through the centralised
                # policy resolver so PR approval behaves identically to
                # every other posting gate.
                from accounting.budget_logic import get_active_budget
                from accounting.services.budget_check_rules import (
                    check_policy, find_matching_appropriation,
                )
                encumbrance_created = False
                hard_block_messages: list[str] = []

                for (account, mda, fund), total_amount in budget_totals.items():
                    # 1. Legacy Budget encumbrance — keep working for tenants
                    #    still on the old Budget table. If a row exists,
                    #    book the encumbrance; if not, we DO NOT treat it
                    #    as a miss any more (Appropriation is the source
                    #    of truth now).
                    legacy_budget = get_active_budget(
                        dimensions={'mda': mda, 'fund': fund},
                        account=account,
                        date=pr.requested_date,
                    )
                    if legacy_budget:
                        BudgetEncumbrance.objects.create(
                            budget=legacy_budget,
                            reference_type='PR',
                            reference_id=pr.pk,
                            encumbrance_date=pr.requested_date,
                            amount=total_amount,
                            status='ACTIVE',
                            description=f"Encumbrance for PR {pr.request_number}",
                        )
                        encumbrance_created = True

                    # 2. Canonical policy evaluation — fires regardless of
                    #    whether a legacy Budget row exists. Matches the
                    #    tenant's BudgetCheckRule configuration + the
                    #    Appropriation register.
                    fiscal_year = pr.requested_date.year if pr.requested_date else None
                    appropriation = find_matching_appropriation(
                        mda=mda, fund=fund, account=account,
                        fiscal_year=fiscal_year,
                    )
                    result = check_policy(
                        account_code=account.code if account else '',
                        appropriation=appropriation,
                        requested_amount=total_amount,
                        transaction_label='purchase requisition',
                        account_name=getattr(account, 'name', '') if account else '',
                    )
                    if result.blocked:
                        mda_code = mda.code if mda else 'N/A'
                        fund_code = fund.code if fund else 'N/A'
                        acct_code = account.code if account else 'N/A'
                        hard_block_messages.append(
                            f"[{mda_code}/{acct_code}/{fund_code}] {result.reason}"
                        )

                if hard_block_messages:
                    raise ValueError(
                        'Cannot approve PR: ' + '; '.join(hard_block_messages)
                    )

                pr.status = 'Approved'
                pr.save()

                msg = "Purchase Requisition approved successfully."
                if encumbrance_created:
                    msg += f" Legacy budget encumbrance created for {len(budget_totals)} line(s)."
                else:
                    msg += (
                        " Budget check passed via Appropriation register — "
                        "legacy encumbrance skipped."
                    )

                return Response({"status": msg})
        except Exception as e:
            logger.error(f"Failed to approve PR {pr.request_number}: {e}")
            from accounting.services.posting_errors import format_post_error
            return Response(
                format_post_error(e, context='purchase requisition'),
                status=status.HTTP_400_BAD_REQUEST,
            )

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

    @action(detail=False, methods=['post'])
    def bulk_approve(self, request):
        """Approve multiple PRs in one call. Runs the same budget-check gate
        as the single-item approve action — any PR that fails blocks only
        itself; the rest continue."""
        ids = request.data.get('ids', [])
        if not ids:
            return Response({"error": "No IDs provided."}, status=status.HTTP_400_BAD_REQUEST)
        if len(ids) > 100:
            return Response({"error": "Maximum 100 items per bulk operation."}, status=status.HTTP_400_BAD_REQUEST)

        qs = self.get_queryset().filter(pk__in=ids)
        approved, skipped, errors = [], [], []

        for pr in qs:
            if pr.status not in ('Draft', 'Pending'):
                skipped.append({"id": pr.pk, "number": pr.request_number, "reason": f"Status is '{pr.status}', must be Draft or Pending to approve"})
                continue
            try:
                with transaction.atomic():
                    from accounting.budget_logic import get_active_budget
                    from accounting.services.budget_check_rules import check_policy, find_matching_appropriation

                    budget_totals: dict = {}
                    for line in pr.lines.all():
                        if not line.account_id:
                            continue
                        key = (line.account, pr.mda, pr.fund)
                        amount = line.estimated_unit_price * line.quantity
                        budget_totals[key] = budget_totals.get(key, Decimal('0.00')) + amount

                    hard_block_messages: list[str] = []
                    for (account, mda, fund), total_amount in budget_totals.items():
                        legacy_budget = get_active_budget(
                            dimensions={'mda': mda, 'fund': fund},
                            account=account,
                            date=pr.requested_date,
                        )
                        if legacy_budget:
                            BudgetEncumbrance.objects.create(
                                budget=legacy_budget,
                                reference_type='PR',
                                reference_id=pr.pk,
                                encumbrance_date=pr.requested_date,
                                amount=total_amount,
                                status='ACTIVE',
                                description=f"Encumbrance for PR {pr.request_number}",
                            )

                        fiscal_year = pr.requested_date.year if pr.requested_date else None
                        appropriation = find_matching_appropriation(mda=mda, fund=fund, account=account, fiscal_year=fiscal_year)
                        result = check_policy(
                            account_code=account.code if account else '',
                            appropriation=appropriation,
                            requested_amount=total_amount,
                            transaction_label='purchase requisition',
                            account_name=getattr(account, 'name', '') if account else '',
                        )
                        if result.blocked:
                            hard_block_messages.append(result.reason)

                    if hard_block_messages:
                        raise ValueError('; '.join(hard_block_messages))

                    pr.status = 'Approved'
                    pr.save()
                    approved.append({"id": pr.pk, "number": pr.request_number})
            except Exception as exc:
                errors.append({"id": pr.pk, "number": pr.request_number, "reason": str(exc)})

        return Response({"approved": approved, "skipped": skipped, "errors": errors})

    @action(detail=False, methods=['post'])
    def bulk_delete(self, request):
        """Delete multiple PRs. Only Draft or Rejected PRs can be deleted."""
        ids = request.data.get('ids', [])
        if not ids:
            return Response({"error": "No IDs provided."}, status=status.HTTP_400_BAD_REQUEST)
        if len(ids) > 100:
            return Response({"error": "Maximum 100 items per bulk operation."}, status=status.HTTP_400_BAD_REQUEST)

        qs = self.get_queryset().filter(pk__in=ids)
        deleted, skipped = [], []

        for pr in qs:
            if pr.status not in ('Draft', 'Rejected'):
                skipped.append({"id": pr.pk, "number": pr.request_number, "reason": f"Cannot delete a '{pr.status}' PR"})
                continue
            pr_id, pr_num = pr.pk, pr.request_number
            pr.delete()
            deleted.append({"id": pr_id, "number": pr_num})

        return Response({"deleted": deleted, "skipped": skipped})

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

class PurchaseOrderViewSet(OrganizationFilterMixin, viewsets.ModelViewSet):
    org_filter_field = 'mda'
    queryset = PurchaseOrder.objects.select_related(
        'vendor', 'purchase_request', 'fund', 'function', 'program', 'geo'
    ).prefetch_related('lines').all()
    serializer_class = PurchaseOrderSerializer
    permission_classes = [RBACPermission]
    # Added 'mda' so the Invoice Verification screen can scope its PO
    # dropdown to the verifier's selected MDA — prevents cross-MDA
    # postings even at the dropdown level (defense in depth).
    filterset_fields = ['status', 'vendor', 'mda']
    pagination_class = ProcurementPagination

    def get_queryset(self):
        qs = PurchaseOrder.objects.select_related(
            'vendor', 'purchase_request', 'fund', 'function', 'program', 'geo'
        ).annotate(
            computed_subtotal=Coalesce(
                Sum(F('lines__quantity') * F('lines__unit_price'), output_field=DecimalField()),
                Value(0),
                output_field=DecimalField(),
            )
        ).prefetch_related('lines')
        # Most-recently-saved first (by pk desc) so a PO draft the user
        # just captured is always at the top of the list, regardless of
        # order_date (which might be backdated to match a requisition).
        # Column-click sort via ?ordering= still wins.
        if not self.request.query_params.get('ordering'):
            qs = qs.order_by('-id', '-order_date')
        return qs

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
        """Create PO and optionally auto-create a DownPaymentRequest.

        Enforces the "one active PO per PR" business rule BEFORE hitting
        the DB constraint so the user gets an actionable message instead
        of an IntegrityError. The DB constraint
        ``uniq_active_po_per_purchase_request`` is the ultimate guard —
        this pre-check is for the UX.
        """
        pr_id = request.data.get('purchase_request')
        if pr_id:
            from procurement.models import PurchaseOrder
            existing = (
                PurchaseOrder.objects
                .filter(purchase_request_id=pr_id)
                .exclude(status='Rejected')
                .only('id', 'po_number', 'status')
                .first()
            )
            if existing:
                return Response(
                    {
                        'error': (
                            f'This Purchase Requisition has already been '
                            f'converted to Purchase Order '
                            f'{existing.po_number} '
                            f'(status: {existing.status}). A PR can only be '
                            f'converted to one active PO. To re-convert, '
                            f'reject the existing PO first.'
                        ),
                        'detail': (
                            f'Duplicate conversion blocked. Existing PO: '
                            f'{existing.po_number} (id {existing.id}, '
                            f'{existing.status}).'
                        ),
                        'code': 'DUPLICATE_PR_CONVERSION',
                        'existing_po_id': existing.id,
                        'existing_po_number': existing.po_number,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

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
    def approve(self, request, pk=None):
        """Approve a Pending PO directly (Pending → Approved).

        This is the in-list approval path — bypasses the central workflow
        inbox so an authorized user can approve from the PO list. The
        underlying status-transition machinery in `PurchaseOrder.save()`
        will fire `process_budget_encumbrance()` automatically.
        """
        po = self.get_object()
        if po.status != 'Pending':
            return Response(
                {"error": f"Only Pending POs can be approved. Current status: {po.status}."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            po.status = 'Approved'
            po.save()
        except Exception as e:
            logger.error(f"Failed to approve PO {po.po_number}: {e}")
            from accounting.services.posting_errors import format_post_error
            return Response(
                format_post_error(e, context='purchase order'),
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({"status": "Purchase Order approved.", "po_status": po.status})

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """Reject a Pending PO (Pending → Rejected). Author can resubmit later."""
        po = self.get_object()
        if po.status != 'Pending':
            return Response(
                {"error": f"Only Pending POs can be rejected. Current status: {po.status}."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            po.status = 'Rejected'
            po.save()
        except Exception as e:
            logger.error(f"Failed to reject PO {po.po_number}: {e}")
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"status": "Purchase Order rejected.", "po_status": po.status})

    @action(detail=True, methods=['post'])
    def post_order(self, request, pk=None):
        order = self.get_object()
        if order.status == 'Posted':
            return Response({"error": "Order already posted."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                order.status = 'Posted'
                order.save()

                # Post to GL — IPSAS 3-way match keeps GL untouched at
                # PO stage (PO = commitment, not expenditure). The
                # service legitimately returns ``None`` to signal
                # "commitment recorded, no journal needed". We must
                # NOT dereference ``journal.reference_number`` in that
                # branch — earlier code did and crashed with
                # 'NoneType' has no attribute 'reference_number',
                # surfacing as an opaque 400 to the operator.
                journal = TransactionPostingService.post_purchase_order(order)

            if journal is not None:
                logger.info(f"PO {order.po_number} posted with journal {journal.reference_number}")
                return Response({
                    "status": "Purchase Order posted and budget reserved.",
                    "journal_entry_id": journal.id,
                    "journal_number": journal.reference_number,
                })
            # Commitment-only path (default IPSAS behaviour).
            logger.info(f"PO {order.po_number} posted (commitment recorded, no GL journal at PO stage).")
            return Response({
                "status": "Purchase Order posted. Commitment recorded against the appropriation; "
                          "GL recognition will occur at GRN / invoice posting per IPSAS 3-way match.",
                "journal_entry_id": None,
                "journal_number": None,
            })
        except Exception as e:
            logger.error(f"Failed to post PO {order.po_number}: {e}")
            from accounting.services.posting_errors import format_post_error
            return Response(
                format_post_error(e, context='purchase order'),
                status=status.HTTP_400_BAD_REQUEST,
            )

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

class DownPaymentRequestViewSet(OrganizationFilterMixin, viewsets.ModelViewSet):
    org_filter_field = 'purchase_order__mda'
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


class GoodsReceivedNoteViewSet(OrganizationFilterMixin, viewsets.ModelViewSet):
    org_filter_field = 'purchase_order__mda'
    queryset = GoodsReceivedNote.objects.select_related(
        'purchase_order', 'purchase_order__vendor', 'warehouse'
    ).prefetch_related('lines', 'lines__po_line').all()
    serializer_class = GoodsReceivedNoteSerializer
    permission_classes = [RBACPermission]
    # 'mda' filter scopes GRNs to the verifier's selected MDA on the
    # Invoice Verification screen. Filters by GoodsReceivedNote.mda
    # which equals purchase_order.mda (enforced in clean()).
    filterset_fields = ['status', 'purchase_order', 'mda']
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

        try:
            with transaction.atomic():
                # Compute GRN total for the partial-invoice cap check below.
                # Budget availability is NOT re-checked here — it was already
                # gated at PO approval time (create_commitment_for_po). A GRN
                # converts existing commitment → expenditure; running
                # check_budget_availability again would double-count the PO's
                # committed amount and falsely block fully-committed appropriations.
                grn_total = sum(
                    line.quantity_received * (line.po_line.unit_price or Decimal('0'))
                    for line in grn.lines.select_related('po_line').all()
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

                # MDA is the new mandatory receiving dimension. Warehouse
                # is auto-resolved from MDA inside GoodsReceivedNote.save()
                # via inventory.services.get_default_warehouse_for_mda(),
                # so the old "warehouse required" check is replaced by an
                # MDA-required + MDA-matches-PO check (defense in depth —
                # the serializer + model.clean() also enforce this).
                if not grn.mda_id:
                    return Response(
                        {"error": "MDA is required for posting a GRN."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                if grn.purchase_order.mda_id and grn.mda_id != grn.purchase_order.mda_id:
                    return Response(
                        {"error": (
                            f"GRN MDA does not match PO {grn.purchase_order.po_number}'s "
                            f"MDA — refusing to post (cross-MDA receipt is not allowed)."
                        )},
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

class InvoiceMatchingViewSet(viewsets.ModelViewSet):
    queryset = InvoiceMatching.objects.all().select_related('purchase_order', 'purchase_order__vendor', 'goods_received_note')
    serializer_class = InvoiceMatchingSerializer
    permission_classes = [RBACPermission]
    filterset_fields = ['status', 'purchase_order']

    @action(detail=True, methods=['post'], url_path='create-draft-voucher')
    def create_draft_voucher(self, request, pk=None):
        """Auto-create a draft PaymentVoucherGov from the linked vendor
        invoice on this verification record.

        Delegates to :func:`accounting.services.pv_factory.create_draft_voucher_from_invoice`
        — same idempotent factory used by the AP-invoice list action.
        Returns ``{invoice_matching, payment_voucher}`` so the SPA can
        navigate straight to the new PV.
        """
        from accounting.services.pv_factory import (
            create_draft_voucher_from_invoice, PVFactoryError,
        )
        matching = self.get_object()
        if not matching.vendor_invoice_id:
            return Response(
                {'error': 'This verification record has no linked vendor '
                          'invoice — post the verification first.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            pv = create_draft_voucher_from_invoice(
                invoice=matching.vendor_invoice, actor=request.user,
                notes=request.data.get('notes', ''),
            )
        except PVFactoryError as exc:
            return Response(
                {'error': str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({
            'invoice_matching': {
                'id': matching.pk,
                'verification_number': matching.verification_number,
                'status': matching.status,
            },
            'payment_voucher': {
                'id': pv.pk,
                'voucher_number': pv.voucher_number,
                'status': pv.status,
                'gross_amount': str(pv.gross_amount),
                'net_amount': str(pv.net_amount),
            },
        })

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

        # Wrap the entire flow (workflow approval → status flip →
        # auto-post) in a single transaction.atomic block. FAIL-CLOSED:
        # if auto-post fails the status flip rolls back too, so the
        # verification cannot land in "Approved" with a Drafted journal.
        # Previously the auto-post was inside a nested atomic with a
        # bare except, which left verifications in Approved while the
        # journal stayed unposted — silent ledger drift.
        auto_post_info: dict = {}
        with transaction.atomic():
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

            # Auto-post to GL when auto-approved. Errors propagate so
            # the entire submit_for_approval rolls back — matching
            # stays in its prior status, journal isn't created, and
            # the operator sees the actual error to fix.
            if matching.status == 'Approved' and matching.purchase_order:
                vi, journal, closed_count = self._post_matching_to_gl_inner(matching)
                auto_post_info = {
                    'journal_id':         journal.id if journal else None,
                    'journal_reference':  journal.reference_number if journal else None,
                    'vendor_invoice_id':  vi.id if vi else None,
                    'commitment_closed':  bool(closed_count),
                    'auto_posted':        True,
                }
                msg += ' Posted to GL automatically.'

        return Response({
            'status': msg,
            'approval_id': result.get('approval_id'),
            **auto_post_info,
        })

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
            # Budget control: MDA + Account (Economic) + Fund only
            allowed, msg = check_budget_availability(
                dimensions={'mda': po.mda, 'fund': po.fund},
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
        """Reject a matching due to significant variance.

        Locked once a Payment Voucher has been raised against the
        underlying vendor invoice (matched by ``invoice_number`` per
        the ``pv_factory`` convention). Cancel or reverse the PV
        first if the verification needs to be rejected after the
        fact.
        """
        matching = self.get_object()

        # ── PV-link lock ────────────────────────────────────────────
        if matching.vendor_invoice_id:
            invoice_number = matching.vendor_invoice.invoice_number
            if invoice_number:
                from accounting.models.treasury import PaymentVoucherGov
                pv = (
                    PaymentVoucherGov.objects
                    .filter(invoice_number=invoice_number)
                    .order_by('-id')
                    .first()
                )
                if pv is not None and pv.status not in ('CANCELLED', 'REVERSED'):
                    return Response(
                        {
                            'error': (
                                f'Cannot reject this verification: a Payment '
                                f'Voucher ({pv.voucher_number}, status '
                                f'{pv.status}) has been raised against the '
                                f'underlying invoice. Cancel or reverse the '
                                f'PV first.'
                            ),
                            'pv_link_locked': True,
                            'payment_voucher_number': pv.voucher_number,
                            'payment_voucher_status': pv.status,
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

        reason = request.data.get('reason', '')
        matching.variance_reason = reason
        matching.status = 'Rejected'
        matching.save()

        return Response({"status": "Matching rejected."})

    @action(detail=False, methods=['post'])
    def simulate(self, request):
        """
        SAP MIRO "Simulate" — preview the GL journal without posting.

        Builds the proposed DR/CR lines for the invoice the user is about
        to post, *without* creating the InvoiceMatching, VendorInvoice, or
        any journal record. Returns a snapshot the UI can render in a
        modal so the verifier sees the GL hit before committing.

        Mirrors the same accounts the real post path will use:

            DR  GR/IR Clearing      (clears the GRN-time accrual)
            DR  Input Tax           (if invoice has tax)
            CR  Accounts Payable    (recognises the supplier liability)
           [CR  WHT Liability]      (per-line withholding, when applicable)

        Body: same shape as verify_and_post, minus acknowledge_partial
        and variance_reason (simulation never blocks).

        Returns: { proposed_lines: [...], total_debit, total_credit,
                   match_type, status, variance_amount, variance_percentage,
                   partial_receipt, accounts_used }
        """
        from accounting.services.base_posting import get_gl_account
        from accounting.models import Account  # used by reconciliation-type AP lookup below
        from django.conf import settings as dj_settings

        data = request.data or {}

        po_id = data.get('purchase_order')
        if not po_id:
            return Response({"error": "purchase_order is required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            po = PurchaseOrder.objects.get(pk=po_id)
        except PurchaseOrder.DoesNotExist:
            return Response({"error": f"PO id={po_id} not found."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            invoice_amount = Decimal(str(data.get('invoice_amount') or '0'))
        except (ValueError, ArithmeticError, TypeError):
            invoice_amount = Decimal('0')
        if invoice_amount <= 0:
            return Response({"error": "invoice_amount must be greater than zero to simulate."}, status=status.HTTP_400_BAD_REQUEST)

        invoice_subtotal_raw = data.get('invoice_subtotal')
        invoice_tax_raw      = data.get('invoice_tax_amount')
        invoice_subtotal = Decimal(str(invoice_subtotal_raw)) if invoice_subtotal_raw not in (None, '') else None
        invoice_tax      = Decimal(str(invoice_tax_raw))      if invoice_tax_raw      not in (None, '') else Decimal('0')
        if invoice_subtotal is None:
            invoice_subtotal = invoice_amount - invoice_tax

        # Compute the GRN-side total (matches verify_and_post logic)
        grn_total = Decimal('0')
        grn_id = data.get('goods_received_note')
        grn = None
        if grn_id:
            try:
                grn = GoodsReceivedNote.objects.get(pk=grn_id)
                for gl in grn.lines.select_related('po_line').all():
                    if gl.po_line:
                        grn_total += (gl.quantity_received or Decimal('0')) * (gl.po_line.unit_price or Decimal('0'))
            except GoodsReceivedNote.DoesNotExist:
                pass

        po_total = po.total_amount or Decimal('0')

        # 3-way match calculation — compares INVOICE SUBTOTAL (ex-VAT)
        # against GRN value, both on a like-for-like basis. The GRN
        # never books VAT (warehouse-side receipt), so comparing the
        # GROSS invoice (which includes VAT) against the GRN's
        # ex-VAT total fires a false variance equal to the tax rate
        # on every VAT-bearing invoice. Using ``invoice_subtotal``
        # for the comparison makes the check tax-neutral; the
        # gross ``invoice_amount`` still drives AP-credit and the
        # totals card, just not the variance gate.
        compare_amount = invoice_subtotal if invoice_tax > 0 else invoice_amount
        if compare_amount == po_total == grn_total:
            match_type, sim_status, variance_pct = 'Full', 'Matched', Decimal('0')
        elif compare_amount == grn_total:
            match_type = 'Full' if all(l.quantity_received >= l.quantity for l in po.lines.all()) else 'Partial'
            sim_status, variance_pct = 'Matched', Decimal('0')
        else:
            base = grn_total or po_total or compare_amount
            variance_pct = abs((compare_amount - base) / base * Decimal('100')) if base > 0 else Decimal('0')
            threshold = Decimal(str(getattr(dj_settings, 'PROCUREMENT_SETTINGS', {}).get('INVOICE_VARIANCE_THRESHOLD', 5.0)))
            sim_status = 'Matched' if variance_pct <= threshold else 'Variance'
            match_type = 'Partial' if grn_total and compare_amount != grn_total else 'None'

        # Variance amount stays in gross terms because that's the
        # number the operator typed and visually compares against
        # the PO; only the percentage gate is normalised on subtotal.
        variance_amount = invoice_amount - (grn_total or po_total or Decimal('0'))

        # Detect partial receipt (purely informational for simulate)
        partial = po.lines.exists() and any(
            l.quantity_received < l.quantity for l in po.lines.all()
        )

        # Build the proposed DR/CR lines — exact same accounts the post
        # path will use, so the user sees the real GL hit.
        gr_ir = get_gl_account('GOODS_RECEIPT_CLEARING', 'Liability', 'GR/IR')

        # AP discovery — mirrors the ladder in payables.py:post_invoice:
        #   1. reconciliation_type='accounts_payable' (CoA-portable; the
        #      tenant admin's explicit "this is the AP control account"
        #      marker — works regardless of code numbering scheme)
        #   2. DEFAULT_GL_ACCOUNTS code (legacy default)
        #   3. account_type='Liability' + name~'Payable' (last resort)
        # Without this layered lookup, NCoA-first tenants whose AP
        # account doesn't match the legacy hard-coded settings code
        # ended up with NO AP line in the simulation — total credit
        # was zero and the journal flagged "NOT balanced".
        ap = (
            Account.objects.filter(
                reconciliation_type='accounts_payable', is_active=True,
            ).first()
            or get_gl_account('ACCOUNTS_PAYABLE', 'Liability', 'Payable')
        )

        # Resolve the explicit Input VAT and WHT GL accounts from the
        # operator's chosen tax_code / withholding_tax (FK-driven —
        # the right intent rather than a "first Liability whose name
        # contains Tax" heuristic, which collided with WHT accounts
        # like '41030103 UNREMITTED TAXES: WITHHOLDING TAX STATE'
        # whenever VAT was the actual target).
        tax_code_id = data.get('tax_code')
        wht_id      = data.get('withholding_tax')
        tax_code_obj = None
        wht_obj = None
        if tax_code_id:
            try:
                from accounting.models import TaxCode
                tax_code_obj = TaxCode.objects.filter(pk=tax_code_id).first()
            except Exception:
                tax_code_obj = None
        if wht_id:
            try:
                from accounting.models import WithholdingTax
                wht_obj = WithholdingTax.objects.filter(pk=wht_id).first()
            except Exception:
                wht_obj = None

        lines = []

        # DR Input Tax — resolved via the layered ``get_input_vat_account``
        # ladder (tax_code FK → reconciliation_type → settings → name
        # heuristic). Emit the tax line ONLY if a GL is found; otherwise
        # the GR/IR residual below absorbs the tax so the journal
        # balances regardless. We compute it FIRST so the GR/IR debit can
        # subtract the resolved Input VAT total.
        from accounting.services.procurement_posting import get_input_vat_account
        input_tax_dr_total = Decimal('0.00')
        if invoice_tax > 0:
            tax_acct = get_input_vat_account(tax_code_obj)
            if tax_acct is not None:
                lines.append({
                    'account_code': tax_acct.code,
                    'account_name': tax_acct.name,
                    'account_type': tax_acct.account_type,
                    'debit':  str(invoice_tax.quantize(Decimal('0.01'))),
                    'credit': '0.00',
                    'memo':   f'Input VAT @ {tax_code_obj.rate}% ({tax_code_obj.code})' if tax_code_obj else 'Input Tax / VAT',
                })
                input_tax_dr_total = invoice_tax

        # DR GR/IR Clearing — RESIDUAL APPROACH so the simulated journal
        # is ALWAYS balanced. Math:
        #   CR side = AP + WHT = (invoice_amount − WHT) + WHT = invoice_amount
        #   DR side must equal invoice_amount = GR/IR + Input VAT
        #     ⇒ GR/IR debit = invoice_amount − input_tax_dr_total
        # When Input VAT resolves, GR/IR debit = subtotal (textbook split).
        # When it doesn't, GR/IR absorbs the tax — still balanced.
        # The line is appended at the END (below) so the user sees the
        # tax line first when reading top-down.

        # WHT is DETERMINED at invoice level but RECOGNISED at payment
        # (Nigerian PFM cash-basis). The simulator therefore shows NO
        # WHT credit on the invoice journal; the WHT FK + rate are
        # stored on the matching for the PV builder to read at payment
        # time. ``wht_amount`` stays zero so the AP credit below is
        # the full gross.
        wht_amount = Decimal('0')

        # DR GR/IR Clearing — RESIDUAL: balances the journal automatically.
        # Inserted BEFORE the tax line in display order so the user reads
        # the standard "DR GR/IR / DR Input VAT / CR AP / CR WHT" sequence.
        if gr_ir:
            gr_ir_debit = (invoice_amount - input_tax_dr_total).quantize(Decimal('0.01'))
            if gr_ir_debit > 0:
                lines.insert(0, {
                    'account_code': gr_ir.code,
                    'account_name': gr_ir.name,
                    'account_type': gr_ir.account_type,
                    'debit':  str(gr_ir_debit),
                    'credit': '0.00',
                    'memo':   f'Clear GR/IR for {data.get("invoice_reference", "invoice")}',
                })

        # CR Accounts Payable — vendor's net liability = invoice_amount
        # less WHT (which is paid directly to FIRS / state revenue).
        ap_amount = (invoice_amount - wht_amount).quantize(Decimal('0.01'))
        if ap and ap_amount > 0:
            lines.append({
                'account_code': ap.code,
                'account_name': ap.name,
                'account_type': ap.account_type,
                'debit':  '0.00',
                'credit': str(ap_amount),
                'memo':   f'AP {po.vendor.name if po.vendor else "vendor"}',
            })

        total_debit  = sum((Decimal(l['debit'])  for l in lines), Decimal('0'))
        total_credit = sum((Decimal(l['credit']) for l in lines), Decimal('0'))

        return Response({
            'simulated': True,
            'match_type': match_type,
            'status': sim_status,
            'variance_amount': str(variance_amount.quantize(Decimal('0.01'))),
            'variance_percentage': str(variance_pct.quantize(Decimal('0.01'))),
            'partial_receipt': partial,
            'po_total':  str(po_total),
            'grn_total': str(grn_total),
            'invoice_amount':   str(invoice_amount),
            'invoice_subtotal': str(invoice_subtotal),
            'invoice_tax':      str(invoice_tax),
            'proposed_lines':   lines,
            'total_debit':      str(total_debit.quantize(Decimal('0.01'))),
            'total_credit':     str(total_credit.quantize(Decimal('0.01'))),
            'balanced':         total_debit == total_credit,
            'accounts_used': {
                'gr_ir_clearing': gr_ir.code if gr_ir else None,
                'accounts_payable': ap.code if ap else None,
            },
        })

    @action(detail=False, methods=['post'])
    def verify_and_post(self, request):
        """
        SAP MIRO-style Logistics Invoice Verification — single atomic call.

        Creates the InvoiceMatching from the request body, calculates the
        3-way match, and immediately posts the resulting Vendor Invoice to
        the GL — all in one database transaction. Bypasses the
        Pending_Review workflow gate so the verifier can complete
        verification + posting in a single click.

        Variance handling:
        - If the calculated variance exceeds the configured 5% threshold,
          posting is BLOCKED unless the request body includes a
          ``variance_reason``. This forces the verifier to acknowledge the
          variance with an audit trail.
        - If a ``variance_reason`` is supplied, it is recorded on the
          matching and posting proceeds.

        Partial-receipt handling:
        - If the GRN has been only partially received against the PO, the
          client is expected to supply ``acknowledge_partial: true`` after
          showing the user a confirmation modal. Without acknowledgement,
          the request is rejected with a 400 + ``partial_receipt: true``
          flag so the client can prompt and retry.

        Body:
            purchase_order        (int, required)
            goods_received_note   (int, optional but typical)
            invoice_reference     (str, required)
            invoice_date          (date, required)
            invoice_amount        (decimal, required)
            invoice_subtotal      (decimal, optional)
            invoice_tax_amount    (decimal, optional)
            notes                 (str, optional)
            variance_reason       (str, required if variance exceeds 5%)
            acknowledge_partial   (bool, required if GRN < PO qty)
            down_payment_amount   (decimal, optional — apply advance)

        Returns the created matching, vendor invoice, and journal info.
        """
        from accounting.models import VendorInvoice
        from accounting.services.procurement_posting import (
            ProcurementPostingService,
        )
        from accounting.services.procurement_commitments import (
            mark_commitment_closed_for_po,
            refresh_appropriations_for_po,
        )

        data = request.data or {}

        # ── Required fields ─────────────────────────────────────────
        po_id = data.get('purchase_order')
        if not po_id:
            return Response({"error": "purchase_order is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            po = PurchaseOrder.objects.get(pk=po_id)
        except PurchaseOrder.DoesNotExist:
            return Response({"error": f"PO id={po_id} not found."}, status=status.HTTP_400_BAD_REQUEST)

        invoice_reference = (data.get('invoice_reference') or '').strip()
        if not invoice_reference:
            return Response({"error": "invoice_reference is required."}, status=status.HTTP_400_BAD_REQUEST)

        # Parse invoice_date upfront. JSON gives us a string; the GL posting
        # path eventually does `journal.posting_date.year` so it MUST be a
        # real ``datetime.date`` instance, not a string.
        from django.utils.dateparse import parse_date as _parse_date
        from datetime import date as _date
        invoice_date_raw = data.get('invoice_date')
        if isinstance(invoice_date_raw, str):
            invoice_date = _parse_date(invoice_date_raw)
        elif isinstance(invoice_date_raw, _date):
            invoice_date = invoice_date_raw
        else:
            invoice_date = None
        if not invoice_date:
            return Response(
                {"error": "invoice_date is required (YYYY-MM-DD)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            invoice_amount = Decimal(str(data.get('invoice_amount') or '0'))
            if invoice_amount <= 0:
                raise ValueError
        except (ValueError, ArithmeticError, TypeError):
            return Response({"error": "invoice_amount must be greater than zero."}, status=status.HTTP_400_BAD_REQUEST)

        invoice_subtotal_raw = data.get('invoice_subtotal')
        invoice_tax_raw      = data.get('invoice_tax_amount')
        invoice_subtotal = Decimal(str(invoice_subtotal_raw)) if invoice_subtotal_raw not in (None, '') else None
        invoice_tax      = Decimal(str(invoice_tax_raw))      if invoice_tax_raw      not in (None, '') else Decimal('0')
        if invoice_subtotal is None:
            invoice_subtotal = invoice_amount - invoice_tax

        # ── GRN resolution + partial-receipt gate ──────────────────
        grn = None
        grn_id = data.get('goods_received_note')
        if grn_id:
            try:
                grn = GoodsReceivedNote.objects.get(pk=grn_id)
            except GoodsReceivedNote.DoesNotExist:
                return Response({"error": f"GRN id={grn_id} not found."}, status=status.HTTP_400_BAD_REQUEST)

        # ── MDA resolution + cross-MDA boundary check ─────────────
        # The verifier picks an MDA at the start of the Invoice
        # Verification session ("session MDA"). We use that as the
        # journal's posting MDA AND we strictly verify that the chosen
        # PO and GRN belong to the same MDA — preventing a verifier from
        # accidentally booking another ministry's spend.
        from accounting.models import MDA
        mda_override_id = data.get('mda')
        posting_mda = po.mda
        if mda_override_id:
            try:
                posting_mda = MDA.objects.get(pk=mda_override_id)
            except MDA.DoesNotExist:
                return Response(
                    {"error": f"MDA id={mda_override_id} not found."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            # Cross-MDA reject: PO must belong to the session MDA.
            if po.mda_id and po.mda_id != posting_mda.pk:
                return Response({
                    "error": (
                        f"Cross-MDA error: PO {po.po_number} belongs to MDA "
                        f"{po.mda.code if po.mda else po.mda_id}, but the "
                        f"session MDA is {posting_mda.code}. Pick the right "
                        f"MDA at the start of the verification session."
                    ),
                    "cross_mda": True,
                }, status=status.HTTP_400_BAD_REQUEST)
            # Same check for the GRN — defense in depth.
            if grn and grn.mda_id and grn.mda_id != posting_mda.pk:
                return Response({
                    "error": (
                        f"Cross-MDA error: GRN {grn.grn_number} belongs to a "
                        f"different MDA than the session MDA "
                        f"({posting_mda.code})."
                    ),
                    "cross_mda": True,
                }, status=status.HTTP_400_BAD_REQUEST)

        # Detect partial receipt (any PO line not fully received)
        partial = False
        if po.lines.exists():
            for line in po.lines.all():
                if line.quantity_received < line.quantity:
                    partial = True
                    break
        if partial and not data.get('acknowledge_partial'):
            return Response({
                "error": (
                    "Goods are partially received against this PO. Please "
                    "acknowledge before posting."
                ),
                "partial_receipt": True,
            }, status=status.HTTP_400_BAD_REQUEST)

        # ── Warrant ceiling check (PSA Authority to Incur Expenditure) ──
        # Defense-in-depth: even though PO approval already checks this,
        # the warrant might have been suspended/reduced between PO approval
        # and invoice verification. Block posting if the cumulative
        # commitment + this invoice would exceed released warrants.
        # Gated by ``is_warrant_pre_payment_enforced`` — see
        # accounting.budget_logic. Default build setting
        # ``WARRANT_ENFORCEMENT_STAGE='payment'`` skips this check at
        # invoice-verification time; the ceiling is enforced at
        # payment posting only.
        from accounting.budget_logic import (
            check_warrant_availability,
            is_warrant_pre_payment_enforced,
        )
        first_account = po.lines.first().account if po.lines.exists() else None
        if is_warrant_pre_payment_enforced() and first_account:
            allowed, msg, info = check_warrant_availability(
                dimensions={'mda': posting_mda, 'fund': po.fund},
                account=first_account,
                amount=invoice_amount,
                exclude_po=po,  # this PO's commitment is already counted
            )
            if not allowed:
                return Response({
                    "error": msg,
                    "warrant_exceeded": True,
                    "warrant_info": {
                        k: str(v) if hasattr(v, 'quantize') else v
                        for k, v in info.items()
                    } if info else {},
                }, status=status.HTTP_400_BAD_REQUEST)

        # ── Create the matching + auto-calculate ────────────────────
        try:
            with transaction.atomic():
                # Resolve optional tax_code / withholding_tax FKs with
                # vendor-default + exemption ladder:
                #   1. Transaction-level wht_exempt flag → zero WHT, period
                #   2. Vendor.wht_exempt (master-data permanent exemption) → zero WHT
                #   3. Explicit withholding_tax id from the payload → use it
                #   4. Fallback to Vendor.withholding_tax_code default
                from accounting.models import TaxCode, WithholdingTax
                tax_code_id = data.get('tax_code')
                wht_id = data.get('withholding_tax')
                tax_code_obj = (
                    TaxCode.objects.filter(pk=tax_code_id).first()
                    if tax_code_id else None
                )

                # Exemption resolution
                txn_wht_exempt = bool(data.get('wht_exempt'))
                wht_exempt_reason = (data.get('wht_exempt_reason') or '').strip()
                vendor_exempt = bool(getattr(po.vendor, 'wht_exempt', False)) if po.vendor else False
                effective_exempt = txn_wht_exempt or vendor_exempt

                if effective_exempt:
                    wht_obj = None
                elif wht_id:
                    wht_obj = WithholdingTax.objects.filter(pk=wht_id).first()
                else:
                    wht_obj = (
                        getattr(po.vendor, 'withholding_tax_code', None)
                        if po.vendor else None
                    )

                # Compute WHT amount at creation so the stored figure matches
                # what downstream posting / reports will recompute.
                wht_amount = Decimal('0.00')
                if wht_obj and wht_obj.rate and invoice_subtotal:
                    wht_amount = (
                        invoice_subtotal * Decimal(str(wht_obj.rate)) / Decimal('100')
                    ).quantize(Decimal('0.01'))

                matching = InvoiceMatching.objects.create(
                    purchase_order=po,
                    goods_received_note=grn,
                    invoice_reference=invoice_reference,
                    invoice_date=invoice_date,
                    invoice_amount=invoice_amount,
                    invoice_subtotal=invoice_subtotal,
                    invoice_tax_amount=invoice_tax,
                    tax_code=tax_code_obj,
                    withholding_tax=wht_obj,
                    wht_amount=wht_amount,
                    wht_exempt=txn_wht_exempt,
                    wht_exempt_reason=wht_exempt_reason,
                    notes=(data.get('notes') or '').strip(),
                )
                matching.calculate_match()
                matching.save()

                # ── Variance gate ───────────────────────────────────
                variance_reason = (data.get('variance_reason') or '').strip()
                if matching.status == 'Variance' and not variance_reason:
                    transaction.set_rollback(True)
                    return Response({
                        "error": (
                            f"Invoice variance ({matching.variance_percentage}%) "
                            f"exceeds the 5% threshold. Provide a variance_reason "
                            f"to override and post."
                        ),
                        "requires_variance_reason": True,
                        "variance_amount": str(matching.variance_amount or 0),
                        "variance_percentage": str(matching.variance_percentage or 0),
                    }, status=status.HTTP_400_BAD_REQUEST)

                # If a reason was supplied (whether or not variance exceeds
                # the threshold), record it and force-match.
                if variance_reason:
                    matching.variance_reason = variance_reason
                    matching.status = 'Matched'

                # Bypass the workflow gate — single-click posting model.
                matching.status = 'Approved'
                matching.matched_date = timezone.now()
                matching.save()

                # ── Locate or create the linked VendorInvoice ───────
                # Only consider unclaimed Draft VIs (the auto-created shells
                # from GRN posting). Don't reuse Approved VIs from other
                # matchings — those are different invoices waiting to be
                # posted on their own. Posted/Paid VIs are skipped to avoid
                # the ImmutableModelMixin "Cannot modify a posted
                # transaction" error.
                vi = VendorInvoice.objects.filter(
                    purchase_order=po, status='Draft',
                ).exclude(
                    invoice_matchings__isnull=False,
                ).order_by('-created_at').first()
                if vi is None:
                    vi = VendorInvoice.objects.create(
                        vendor=po.vendor,
                        purchase_order=po,
                        reference=invoice_reference,
                        description=(
                            f"Invoice verification {matching.pk} — PO {po.po_number}"
                        ),
                        invoice_date=invoice_date,
                        due_date=getattr(po, 'payment_due_date', None) or invoice_date,
                        mda=posting_mda,
                        fund=po.fund,
                        function=po.function,
                        program=po.program,
                        geo=po.geo,
                        account=po.lines.first().account if po.lines.exists() else None,
                        subtotal=invoice_subtotal,
                        tax_amount=invoice_tax,
                        total_amount=invoice_amount,
                        status='Draft',
                    )

                # Refresh VI fields with the verified amounts. ``invoice_date``
                # is now a real ``date`` instance (parsed above) so downstream
                # ``journal.posting_date.year`` works.
                vi.reference     = invoice_reference
                vi.invoice_date  = invoice_date
                vi.subtotal      = invoice_subtotal
                vi.tax_amount    = invoice_tax
                vi.total_amount  = invoice_amount
                # Honour the MDA override even when reusing an auto-created VI.
                vi.mda           = posting_mda
                if vi.status == 'Draft':
                    vi.status = 'Approved'  # service requires Approved/Paid
                vi.save()

                # ── Post the GL journal ─────────────────────────────
                journal = ProcurementPostingService.post_vendor_invoice(vi)

                vi.status = 'Posted'
                vi.save()

                matching.vendor_invoice = vi
                matching.save()

                # ── Close the budget commitment ─────────────────────
                try:
                    closed_count = mark_commitment_closed_for_po(po)
                except Exception as exc:
                    closed_count = 0
                    logger.warning(
                        "Matching %s: commitment CLOSED flip failed (non-fatal): %s",
                        matching.pk, exc,
                    )

                # ── Belt-and-braces appropriation cache refresh ─────
                # Guarantees ``cached_total_expended`` updates every time
                # invoice verification posts to GL — even if the PO has no
                # ProcurementBudgetLink, spans multiple appropriations, or
                # the JournalHeader post_save signal failed to match the
                # appropriation. This is what every budget execution
                # report and dashboard reads.
                try:
                    refresh_appropriations_for_po(po)
                except Exception as exc:
                    logger.warning(
                        "Matching %s: appropriation refresh failed (non-fatal): %s",
                        matching.pk, exc,
                    )

                # ── Optional: apply down payment to the matching ────
                dp_amount_raw = data.get('down_payment_amount')
                if dp_amount_raw:
                    try:
                        dp_amount = Decimal(str(dp_amount_raw))
                        if dp_amount > 0:
                            matching.down_payment_applied = dp_amount
                            matching.save(update_fields=['down_payment_applied'])
                    except (ValueError, ArithmeticError, TypeError):
                        pass  # non-fatal

            return Response({
                "status": "Invoice verified and posted to GL.",
                "matching_id": matching.id,
                "matching_status": matching.status,
                "match_type": matching.match_type,
                "variance_amount": str(matching.variance_amount or 0),
                "variance_percentage": str(matching.variance_percentage or 0),
                "journal_id": journal.id if journal else None,
                "journal_reference": journal.reference_number if journal else None,
                "vendor_invoice_id": vi.id,
                "vendor_invoice_number": vi.invoice_number,
                "commitment_closed": bool(closed_count),
                "partial_receipt": partial,
                "posted_to_mda": posting_mda.code if posting_mda else None,
                "posted_to_mda_name": posting_mda.name if posting_mda else None,
            })
        except Exception as exc:
            logger.exception("verify_and_post failed: %s", exc)
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    @staticmethod
    def _post_matching_to_gl_inner(matching):
        """Core post-to-GL logic for an approved InvoiceMatching.

        Extracted so the same flow runs from both the explicit
        ``post_to_gl`` action and the auto-post that fires the
        moment a matching is approved (see ``submit_for_approval``
        below). Returns ``(vi, journal, closed_count)`` on success.
        Callers wrap this in ``transaction.atomic()``.
        """
        from accounting.models import VendorInvoice
        from accounting.services.procurement_posting import (
            ProcurementPostingService,
        )
        from accounting.services.procurement_commitments import (
            mark_commitment_closed_for_po,
            refresh_appropriations_for_po,
        )

        po = matching.purchase_order

        # ── Idempotency guard ────────────────────────────────────────
        # An Invoice Verification that already produced a Posted vendor
        # invoice cannot be posted twice — every additional post would
        # double the AP credit, double the budget consumption, and
        # double the GR/IR clearing. Once posted, the only valid
        # corrective action is a Reverse (which writes a REV-* journal
        # and reopens the commitment). Block re-posting at the service
        # layer so every entry path (verify_and_post, post_to_gl,
        # auto-post on approval) gets the same protection.
        existing_vi = matching.vendor_invoice
        if existing_vi and existing_vi.status == 'Posted':
            from rest_framework.exceptions import ValidationError as DRFValidationError
            raise DRFValidationError({
                'error': (
                    "This invoice verification has already been posted to the "
                    "GL and cannot be posted again. To correct it, use the "
                    "Reverse action — that creates a reversing journal "
                    "(REV-*) and reopens the budget commitment so a new "
                    "verification can be raised."
                ),
                'already_posted': True,
                'journal_id': existing_vi.journal_entry_id,
                'vendor_invoice_id': existing_vi.id,
            })

        # 1. Locate or create the VendorInvoice for this matching.
        vi = matching.vendor_invoice
        if vi and vi.status not in ('Draft', 'Approved'):
            vi = None
        if vi is None:
            vi = VendorInvoice.objects.filter(
                purchase_order=po, status='Draft',
            ).exclude(invoicematching__isnull=False).order_by('-created_at').first()
        if vi is None:
            vi = VendorInvoice.objects.create(
                vendor=po.vendor,
                purchase_order=po,
                reference=matching.invoice_reference,
                description=(
                    f"Invoice verification {matching.pk} — PO {po.po_number}"
                ),
                invoice_date=matching.invoice_date,
                due_date=getattr(po, 'payment_due_date', None) or matching.invoice_date,
                mda=po.mda,
                fund=po.fund,
                function=po.function,
                program=po.program,
                geo=po.geo,
                account=po.lines.first().account if po.lines.exists() else None,
                subtotal=matching.invoice_subtotal or matching.invoice_amount,
                tax_amount=matching.invoice_tax_amount or Decimal('0'),
                total_amount=matching.invoice_amount,
                status='Draft',
            )

        vi.reference = matching.invoice_reference or vi.reference
        vi.invoice_date = matching.invoice_date or vi.invoice_date
        vi.subtotal = matching.invoice_subtotal or matching.invoice_amount
        vi.tax_amount = matching.invoice_tax_amount or Decimal('0')
        vi.total_amount = matching.invoice_amount
        if vi.status == 'Draft':
            vi.status = 'Approved'
        vi.save()

        # ── Propagate tax_code / withholding_tax selected on the matching
        # onto a VendorInvoiceLine so procurement_posting can compute VAT/WHT.
        # We rebuild the line each time this runs (the matching is the source of
        # truth); if no taxes are selected we skip so legacy header-level
        # invoice.tax_amount still posts via the fallback path.
        #
        # WHT exemption ladder honoured here:
        #   matching.wht_exempt (transaction) → clear line WHT FK
        #   vendor.wht_exempt (master)        → clear line WHT FK
        # In both cases the posting service will also double-guard, but
        # writing a null FK on the line makes the exemption legible in the
        # VendorInvoiceLine record itself for audit.
        if matching.tax_code_id or matching.withholding_tax_id or matching.wht_exempt:
            from accounting.models import VendorInvoiceLine
            VendorInvoiceLine.objects.filter(invoice=vi).delete()
            expense_account = (
                vi.account
                or (po.lines.first().account if po and po.lines.exists() else None)
            )
            if expense_account:
                vendor_exempt = bool(getattr(po.vendor, 'wht_exempt', False)) if po.vendor else False
                effective_exempt = matching.wht_exempt or vendor_exempt
                line_wht = None if effective_exempt else matching.withholding_tax
                VendorInvoiceLine.objects.create(
                    invoice=vi,
                    account=expense_account,
                    description=(
                        f"Invoice {matching.invoice_reference} — "
                        f"PO {po.po_number if po else ''}"
                    )[:255],
                    amount=vi.subtotal,
                    tax_code=matching.tax_code,
                    withholding_tax=line_wht,
                )

        journal = ProcurementPostingService.post_vendor_invoice(vi)

        vi.status = 'Posted'
        vi.save()

        if matching.vendor_invoice_id != vi.pk:
            matching.vendor_invoice = vi
        if matching.status == 'Matched':
            matching.status = 'Approved'
        matching.save()

        try:
            closed_count = mark_commitment_closed_for_po(po)
        except Exception as exc:
            closed_count = 0
            logger.warning(
                "Matching %s: commitment CLOSED flip failed (non-fatal): %s",
                matching.pk, exc,
            )

        # Belt-and-braces: guarantee appropriation cache reflects the
        # newly-recognised expenditure for every report and dashboard.
        try:
            refresh_appropriations_for_po(po)
        except Exception as exc:
            logger.warning(
                "Matching %s: appropriation refresh failed (non-fatal): %s",
                matching.pk, exc,
            )
        return vi, journal, closed_count

    @action(detail=True, methods=['post'])
    def post_to_gl(self, request, pk=None):
        """
        Post the verified invoice to the General Ledger — IPSAS three-way close.

        This is the final step of Invoice Verification. It locates (or creates)
        the linked VendorInvoice, copies the verified amounts onto it, and
        posts the GL journal that closes the GR/IR accrual:

            DR  GR/IR Clearing    (clears the credit booked at GRN time)
            CR  Accounts Payable  (recognises the supplier liability)
           [DR  Input Tax]        (if invoice has tax)
           [CR  WHT Liability]    (per-line WHT, if applicable)

        Side effects:
        - VendorInvoice.status: Draft/Approved → Posted
        - InvoiceMatching.vendor_invoice ← FK to the posted VI
        - ProcurementBudgetLink.status: INVOICED → CLOSED (commitment released)

        Allowed entry statuses: Matched, Approved.

        Returns the JournalHeader id/reference so the UI can deep-link to
        the posted journal.
        """
        from accounting.models import VendorInvoice
        from accounting.services.procurement_posting import (
            ProcurementPostingService,
        )
        from accounting.services.procurement_commitments import (
            mark_commitment_closed_for_po,
        )

        matching = self.get_object()

        if matching.status not in ('Matched', 'Approved'):
            return Response(
                {"error": (
                    f"Invoice must be 'Matched' or 'Approved' before posting "
                    f"to the GL. Current status: '{matching.status}'."
                )},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not matching.purchase_order:
            return Response(
                {"error": "Cannot post — matching has no Purchase Order link."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        po = matching.purchase_order

        # ── Idempotency check ─────────────────────────────────────
        # If this matching already has a Posted VendorInvoice linked,
        # the work is done — don't re-post (would trigger
        # ImmutableModelMixin's "Cannot modify a posted transaction"
        # error). Just return the existing journal info as success.
        existing_vi = matching.vendor_invoice
        if existing_vi and existing_vi.status == 'Posted':
            existing_journal = existing_vi.journal_entry
            return Response({
                "status": "Invoice was already posted to GL.",
                "already_posted": True,
                "journal_id": existing_journal.id if existing_journal else None,
                "journal_reference": existing_journal.reference_number if existing_journal else None,
                "vendor_invoice_id": existing_vi.id,
                "vendor_invoice_number": existing_vi.invoice_number,
            })

        try:
            with transaction.atomic():
                vi, journal, closed_count = self._post_matching_to_gl_inner(matching)
            return Response({
                "status": "Invoice posted to GL successfully.",
                "journal_id": journal.id if journal else None,
                "journal_reference": journal.reference_number if journal else None,
                "vendor_invoice_id": vi.id,
                "vendor_invoice_number": vi.invoice_number,
                "commitment_closed": bool(closed_count),
            })
        except Exception as exc:
            logger.exception(
                "Matching %s post_to_gl failed: %s", matching.pk, exc,
            )
            return Response(
                {"error": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

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
    def reverse(self, request, pk=None):
        """Reverse a posted Invoice Verification — IPSAS audit-safe undo.

        IPSAS does not allow deletion of posted entries; the canonical
        correction is a reversing journal that mirrors the original DR/CR
        with the signs swapped, leaving an immutable audit trail. This
        endpoint orchestrates that reversal and the related cleanups:

          1. Validates the matching has a Posted vendor invoice + journal.
          2. Calls ``IPSASJournalService.reverse_journal`` to write a
             ``REV-<original-ref>`` journal and post it. Both the original
             and reversal stay on the books; the original gets
             ``is_reversed=True``.
          3. Flips the VendorInvoice back from Posted → Approved so the
             matching is no longer marked "paid liability outstanding".
             (We use Approved rather than Cancelled to keep the record
             editable for a fresh re-post if needed.)
          4. Reopens the commitment: ``ProcurementBudgetLink`` flips
             from CLOSED back to INVOICED so the encumbrance returns to
             ``total_committed`` and ``cached_total_expended`` shrinks.
          5. Refreshes appropriation totals so dashboards and reports
             reflect the reversal immediately.
          6. Audit: ``JournalReversal`` row + ``TransactionAuditLog`` row
             are written by ``reverse_journal`` itself.

        Body: { "reason": "<required reversal narrative>" }
        """
        matching = self.get_object()
        reason = (request.data.get('reason') or '').strip()
        if not reason:
            return Response(
                {"error": "Reversal reason is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        vi = matching.vendor_invoice
        if not vi or vi.status != 'Posted':
            return Response(
                {"error": (
                    "Only posted invoice verifications can be reversed. "
                    f"Current vendor-invoice status: "
                    f"{vi.status if vi else 'none'}."
                )},
                status=status.HTTP_400_BAD_REQUEST,
            )

        journal = vi.journal_entry
        if not journal:
            return Response(
                {"error": "No GL journal linked to this invoice — nothing to reverse."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if getattr(journal, 'is_reversed', False):
            return Response(
                {"error": (
                    "This invoice verification has already been reversed; "
                    "no further reversal is possible."
                )},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from accounting.services.ipsas_journal_service import IPSASJournalService
        from accounting.services.procurement_commitments import (
            refresh_appropriations_for_po,
        )
        from procurement.models import ProcurementBudgetLink

        try:
            with transaction.atomic():
                reversal_journal = IPSASJournalService.reverse_journal(
                    journal, request.user, reason,
                )

                # Flip the VendorInvoice back to Approved so it doesn't
                # count as an outstanding posted liability.
                vi.status = 'Approved'
                vi.save(_allow_status_change=True)

                # Reopen the commitment: CLOSED → INVOICED so the
                # encumbrance is restored. We don't go all the way back
                # to ACTIVE because the GRN is still posted.
                if matching.purchase_order_id:
                    ProcurementBudgetLink.objects.filter(
                        purchase_order=matching.purchase_order,
                        status='CLOSED',
                    ).update(status='INVOICED')
                    # Refresh appropriation cache so reports reflect the
                    # liberated commitment immediately.
                    refresh_appropriations_for_po(matching.purchase_order)

            return Response({
                "status": "Invoice verification reversed successfully.",
                "reversal_journal_id": reversal_journal.id,
                "reversal_journal_reference": reversal_journal.reference_number,
                "original_journal_id": journal.id,
                "original_journal_reference": journal.reference_number,
                "vendor_invoice_id": vi.id,
                "vendor_invoice_status": vi.status,
            })
        except Exception as exc:
            logger.exception("Matching %s reverse failed: %s", matching.pk, exc)
            return Response(
                {"error": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

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


# ─── BPP Due Process ViewSets (Quot PSE Phase 5) ────────────────────

from procurement.models import ProcurementThreshold, CertificateOfNoObjection, ProcurementBudgetLink
from procurement.serializers import (
    ProcurementThresholdSerializer, CertificateOfNoObjectionSerializer,
    ProcurementBudgetLinkSerializer, ThresholdCheckSerializer,
)
from rest_framework.views import APIView


class ProcurementThresholdViewSet(viewsets.ModelViewSet):
    """BPP procurement approval thresholds."""
    serializer_class = ProcurementThresholdSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['category', 'is_active']
    ordering = ['category', 'min_amount']

    def get_queryset(self):
        return ProcurementThreshold.objects.all()


class CertificateOfNoObjectionViewSet(viewsets.ModelViewSet):
    """BPP No Objection Certificates."""
    serializer_class = CertificateOfNoObjectionSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['is_valid', 'authority_level']
    search_fields = ['certificate_number']

    def get_queryset(self):
        return CertificateOfNoObjection.objects.select_related('purchase_order')


class ProcurementBudgetLinkViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only view of PO-to-appropriation budget commitments."""
    serializer_class = ProcurementBudgetLinkSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['status']

    def get_queryset(self):
        return ProcurementBudgetLink.objects.select_related('purchase_order', 'appropriation')


class ThresholdCheckView(APIView):
    """Check which BPP approval authority applies for a given amount."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        ser = ThresholdCheckSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        result = ProcurementThreshold.get_authority_level(
            amount=ser.validated_data['amount'],
            category=ser.validated_data['category'],
        )
        return Response(result)
