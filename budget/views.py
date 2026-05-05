from decimal import Decimal
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination

from django.db.models import Sum
from .models import (
    UnifiedBudget, UnifiedBudgetEncumbrance, UnifiedBudgetVariance,
    UnifiedBudgetAmendment, RevenueBudget, AppropriationVirement,
)
from .serializers import (
    BudgetVarianceSerializer, RevenueBudgetSerializer,
    AppropriationVirementSerializer,
)
from core.mixins import OrganizationFilterMixin


class UnifiedBudgetViewSet(OrganizationFilterMixin, viewsets.ModelViewSet):
    """ViewSet for Unified Budget - supports both Public and Private Sector"""
    org_filter_field = 'mda'
    queryset = UnifiedBudget.objects.all().select_related(
        'mda', 'fund', 'function', 'program', 'geo', 'cost_center', 'account'
    )
    filterset_fields = ['fiscal_year', 'period_type', 'period_number', 'budget_type', 'status', 'mda', 'cost_center']
    search_fields = ['budget_code', 'name', 'description']

    @action(detail=False, methods=['get'])
    def utilization_alerts(self, request):
        """Get budgets exceeding utilization threshold"""
        threshold = request.query_params.get('threshold', 80)
        fiscal_year = request.query_params.get('fiscal_year')

        budgets = UnifiedBudget.objects.filter(
            status='APPROVED'
        ).select_related('mda', 'cost_center', 'account')

        if fiscal_year:
            budgets = budgets.filter(fiscal_year=fiscal_year)

        alerts = []
        for budget in budgets:
            utilization = float(budget.utilization_rate)
            if utilization >= float(threshold):
                alerts.append({
                    'id': budget.id,
                    'budget_code': budget.budget_code,
                    'name': budget.name,
                    'budget_type': budget.budget_type,
                    'mda': budget.mda.name if budget.mda else None,
                    'cost_center': budget.cost_center.name if budget.cost_center else None,
                    'account': budget.account.name if budget.account else None,
                    'allocated_amount': float(budget.allocated_amount),
                    'encumbered_amount': float(budget.encumbered_amount),
                    'actual_expended': float(budget.actual_expended),
                    'available_amount': float(budget.available_amount),
                    'utilization_rate': round(utilization, 2),
                    'threshold': float(threshold),
                    'alert_level': 'Critical' if utilization >= 95 else 'Warning' if utilization >= 80 else 'Info',
                })

        return Response({
            'count': len(alerts),
            'alerts': alerts
        })

    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        budget = self.get_object()
        budget.status = 'APPROVED'
        budget.approved_by = request.user
        from django.utils import timezone
        budget.approved_date = timezone.now()
        budget.save()
        return Response({"status": "Budget activated."})

    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        budget = self.get_object()
        budget.status = 'DRAFT'
        budget.save()
        return Response({"status": "Budget deactivated."})

    @action(detail=True, methods=['post'])
    def close(self, request, pk=None):
        """Close the budget period"""
        budget = self.get_object()
        budget.status = 'CLOSED'
        from django.utils import timezone
        budget.closed_date = timezone.now()
        budget.save()
        return Response({"status": "Budget closed."})

    @action(detail=True, methods=['post'])
    def check_budget(self, request, pk=None):
        """Check if amount is available in this budget"""
        budget = self.get_object()
        amount = request.data.get('amount')

        if not amount:
            return Response({"error": "amount is required"}, status=status.HTTP_400_BAD_REQUEST)

        is_allowed, message, available = budget.check_availability(Decimal(str(amount)))

        return Response({
            "allowed": is_allowed,
            "message": message,
            "available_amount": str(available),
            "allocated_amount": str(budget.allocated_amount),
            "encumbered_amount": str(budget.encumbered_amount),
            "actual_expended": str(budget.actual_expended),
            "utilization_rate": str(budget.utilization_rate)
        })

    @action(detail=True, methods=['get'])
    def summary(self, request, pk=None):
        """Get budget summary with all calculated fields"""
        budget = self.get_object()
        return Response({
            'budget_code': budget.budget_code,
            'name': budget.name,
            'fiscal_year': budget.fiscal_year,
            'period_type': budget.period_type,
            'period_number': budget.period_number,
            'status': budget.status,
            'budget_type': budget.budget_type,
            'original_amount': str(budget.original_amount),
            'revised_amount': str(budget.revised_amount),
            'supplemental_amount': str(budget.supplemental_amount),
            'allocated_amount': str(budget.allocated_amount),
            'encumbered_amount': str(budget.encumbered_amount),
            'actual_expended': str(budget.actual_expended),
            'available_amount': str(budget.available_amount),
            'utilization_rate': str(budget.utilization_rate),
            'variance_amount': str(budget.variance_amount),
            'variance_percent': str(budget.variance_percent),
        })


class UnifiedBudgetEncumbranceViewSet(OrganizationFilterMixin, viewsets.ModelViewSet):
    org_filter_field = 'budget__mda'
    """ViewSet for Budget Encumbrances"""
    queryset = UnifiedBudgetEncumbrance.objects.all().select_related('budget')
    filterset_fields = ['budget', 'reference_type', 'status']
    search_fields = ['reference_number', 'description']

    @action(detail=True, methods=['post'])
    def liquidate(self, request, pk=None):
        """Liquidate (reduce) an encumbrance"""
        encumbrance = self.get_object()
        amount = request.data.get('amount')

        if not amount:
            return Response({"error": "amount is required"}, status=status.HTTP_400_BAD_REQUEST)

        encumbrance.liquidate(Decimal(str(amount)))
        return Response({"status": "Encumbrance liquidated.", "remaining": str(encumbrance.remaining_amount)})

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel an encumbrance"""
        encumbrance = self.get_object()
        reason = request.data.get('reason', 'Manual cancellation')
        encumbrance.cancel(reason)
        return Response({"status": "Encumbrance cancelled."})


class UnifiedBudgetVarianceViewSet(OrganizationFilterMixin, viewsets.ReadOnlyModelViewSet):
    org_filter_field = 'budget__mda'
    """ViewSet for Budget Variance Analysis"""
    queryset = UnifiedBudgetVariance.objects.all().select_related('budget')
    filterset_fields = ['budget', 'fiscal_year', 'period_type', 'period_number', 'variance_type']

    @action(detail=False, methods=['post'])
    def calculate(self, request):
        """Calculate variance for a given period"""
        budget_id = request.data.get('budget_id')
        period_number = request.data.get('period_number')
        period_type = request.data.get('period_type', 'MONTHLY')

        if not budget_id or not period_number:
            return Response({"error": "budget_id and period_number are required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            budget = UnifiedBudget.objects.get(pk=budget_id)
        except UnifiedBudget.DoesNotExist:
            return Response({"error": "Budget not found"}, status=status.HTTP_404_NOT_FOUND)

        variance = UnifiedBudgetVariance.calculate_for_period(budget, int(period_number), period_type)

        return Response(BudgetVarianceSerializer(variance).data)

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Get variance summary"""
        budget_id = request.query_params.get('budget_id')

        variances = UnifiedBudgetVariance.objects.all()
        if budget_id:
            variances = variances.filter(budget_id=budget_id)

        total_budget = variances.aggregate(Sum('ytd_budget'))['ytd_budget__sum'] or 0
        total_actual = variances.aggregate(Sum('ytd_actual'))['ytd_actual__sum'] or 0
        total_variance = total_budget - total_actual

        return Response({
            'total_ytd_budget': float(total_budget),
            'total_ytd_actual': float(total_actual),
            'total_variance': float(total_variance),
            'variance_percent': float((total_variance / total_budget * 100) if total_budget > 0 else 0)
        })


class UnifiedBudgetAmendmentViewSet(OrganizationFilterMixin, viewsets.ModelViewSet):
    org_filter_field = 'budget__mda'
    """ViewSet for Budget Amendments"""
    queryset = UnifiedBudgetAmendment.objects.all().select_related('budget', 'from_budget', 'to_budget')
    filterset_fields = ['budget', 'amendment_type', 'status']
    search_fields = ['amendment_number', 'reason']

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """Approve a budget amendment"""
        amendment = self.get_object()
        amendment.approve(request.user)
        return Response({"status": "Amendment approved.", "new_amount": str(amendment.new_amount)})

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """Reject a budget amendment"""
        amendment = self.get_object()
        reason = request.data.get('reason', 'No reason provided')
        amendment.reject(request.user, reason)
        return Response({"status": "Amendment rejected."})


# Legacy aliases for backward compatibility
BudgetAllocationViewSet = UnifiedBudgetViewSet
BudgetLineViewSet = UnifiedBudgetEncumbranceViewSet
BudgetVarianceViewSet = UnifiedBudgetVarianceViewSet


# ─── Government Appropriation & Warrant (Quot PSE Phase 3) ───────────

from .models import Appropriation, Warrant
from .serializers import (
    AppropriationSerializer, WarrantSerializer, BudgetValidationRequestSerializer,
)
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter


class AppropriationPagination(PageNumberPagination):
    """
    Custom paginator that honours ``?page_size=`` from the client.

    The global DEFAULT_PAGINATION_CLASS uses vanilla PageNumberPagination
    which ignores ``page_size`` query params and pins responses to PAGE_SIZE=20.
    AppropriationDetail.tsx and the rollup detail-fetch both pass
    ``page_size=200`` expecting the full MDA budget back; without this
    paginator the request silently truncated to 20, and the MDA-Total
    footer on the detail page diverged from the rollup card by exactly
    that ratio (e.g. 20-of-55 lines = ~₦420M instead of ~₦3.65B).

    page_size_query_param   — opt-in override per request
    max_page_size           — safety cap so a malicious client can't
                              ask for a million rows
    """
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 10000


class AppropriationViewSet(OrganizationFilterMixin, viewsets.ModelViewSet):
    org_filter_admin_field = 'administrative'
    """Legislative budget appropriation — the legal authority to spend."""
    serializer_class = AppropriationSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = AppropriationPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    # ``economic`` added so Contract / IPC forms can drill down to the
    # specific budget line that funds the contract (MDA × Fund × GL =
    # one appropriation row). Without this filter, the frontend would
    # have to fetch every appropriation under the MDA and filter
    # client-side — fine for 10 lines, slow for 1000.
    filterset_fields = [
        'status', 'appropriation_type', 'fiscal_year',
        'administrative', 'fund', 'economic',
    ]
    search_fields = ['administrative__name', 'economic__name', 'description']
    ordering_fields = ['amount_approved', 'created_at']
    ordering = ['-created_at']

    def get_queryset(self):
        qs = Appropriation.objects.select_related(
            'fiscal_year', 'administrative', 'economic',
            'functional', 'programme', 'fund',
        )
        # Default: newest first. Column-click sort via ?ordering= wins.
        if not self.request.query_params.get('ordering'):
            qs = qs.order_by('-created_at', '-id')
        return qs

    @action(detail=False, methods=['get'], url_path='by-mda')
    def by_mda(self, request):
        """
        Aggregated rollup of appropriations — one row per (MDA, fiscal year).

        Each row carries:
          id                    — synthetic "<mda_id>-<fy_id>" composite, lets
                                  GenericListPage uniquely key rows in the table
          mda_id / mda_code / mda_name
          fiscal_year_id / fiscal_year_label
          appropriation_count   — number of distinct (economic, fund) lines
          amount_approved       — SUM of amount_approved
          total_expended        — SUM of cached_total_expended (NULL-safe)
          available_balance     — amount_approved - total_expended
          execution_rate        — total_expended / amount_approved * 100

        Honours OrganizationFilterMixin so SEPARATED-mode users only see
        their own MDA's rollup. Both filters are optional:
            ?fiscal_year=2026     narrows to a single FY (4-digit year)
            ?administrative=42    narrows to a single MDA (FK id)
        """
        from django.db.models import Sum, Count, Value, DecimalField, F
        from django.db.models.functions import Coalesce
        from decimal import Decimal

        qs = self.filter_queryset(self.get_queryset())
        fy = request.query_params.get('fiscal_year')
        if fy:
            # Accept either the FK id (preferred — matches the flat list endpoint)
            # or the 4-digit year (legacy callers). We disambiguate by magnitude:
            # any value >= 1900 is treated as a 4-digit year.
            try:
                fy_int = int(fy)
            except (TypeError, ValueError):
                return Response(
                    {'error': f"fiscal_year must be an integer (got {fy!r})."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if fy_int >= 1900:
                qs = qs.filter(fiscal_year__year=fy_int)
            else:
                qs = qs.filter(fiscal_year_id=fy_int)
        mda = request.query_params.get('administrative')
        if mda:
            try:
                qs = qs.filter(administrative_id=int(mda))
            except (TypeError, ValueError):
                return Response(
                    {'error': f"administrative must be an integer FK id (got {mda!r})."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        zero = Value(Decimal('0'), output_field=DecimalField(max_digits=20, decimal_places=2))
        from django.db.models import Min
        rollup = (
            qs.values(
                'administrative_id',
                'administrative__code',
                'administrative__name',
                'fiscal_year_id',
                'fiscal_year__year',
            )
            .annotate(
                appropriation_count=Count('id'),
                amount_approved=Coalesce(Sum('amount_approved'), zero),
                total_expended=Coalesce(Sum('cached_total_expended'), zero),
                # Smallest appropriation id under this (MDA, FY) — used by the
                # frontend to deep-link from the rollup row to the existing
                # AppropriationDetail page (which renders the MDA-level
                # summary + every sibling line under the same MDA/FY).
                sample_appropriation_id=Min('id'),
            )
            .annotate(available_balance=F('amount_approved') - F('total_expended'))
            # Newest FY first (most users care about current year), then
            # MDA code ascending so MDAs are easy to find within a year.
            .order_by('-fiscal_year__year', 'administrative__code')
        )

        # Build per-(MDA, FY) status breakdown in one extra query. We split
        # this from the main aggregate because mixing Count('id', filter=…)
        # for every status into the values()/annotate chain would multiply
        # the SQL size — one tight follow-up query is simpler.
        status_qs = (
            qs.values('administrative_id', 'fiscal_year_id', 'status')
              .annotate(n=Count('id'))
        )
        status_map: dict[tuple[int, int], dict[str, int]] = {}
        draft_ids_map: dict[tuple[int, int], list[int]] = {}
        approvable_ids_map: dict[tuple[int, int], list[int]] = {}
        activatable_ids_map: dict[tuple[int, int], list[int]] = {}
        for s in status_qs:
            key = (s['administrative_id'], s['fiscal_year_id'])
            status_map.setdefault(key, {})[s['status']] = s['n']
        # Three id buckets keyed by (MDA, FY). The frontend uses these
        # directly for bulk-delete / bulk-approve / bulk-activate so each
        # action carries the right pre-filtered subset and the server
        # never has to second-guess the selection.
        bucket_qs = qs.values('administrative_id', 'fiscal_year_id', 'id', 'status')
        for row in bucket_qs:
            key = (row['administrative_id'], row['fiscal_year_id'])
            st = row['status']
            if st == 'DRAFT':
                draft_ids_map.setdefault(key, []).append(row['id'])
            if st in ('DRAFT', 'SUBMITTED'):
                approvable_ids_map.setdefault(key, []).append(row['id'])
            if st in ('APPROVED', 'SUBMITTED'):
                activatable_ids_map.setdefault(key, []).append(row['id'])

        def _enrich(row):
            approved = row['amount_approved']
            expended = row['total_expended']
            rate = float(expended / approved * 100) if approved and approved > 0 else 0.0
            mda_id_ = row['administrative_id']
            fy_id_ = row['fiscal_year_id']
            key = (mda_id_, fy_id_)
            counts = status_map.get(key, {})
            draft_ids = draft_ids_map.get(key, [])
            approvable_ids = approvable_ids_map.get(key, [])
            activatable_ids = activatable_ids_map.get(key, [])
            total = sum(counts.values()) or row['appropriation_count']

            # Roll-up status semantics:
            #   - all DRAFT          → "DRAFT"   (deletable in bulk)
            #   - all PENDING        → "PENDING"
            #   - all APPROVED       → "APPROVED"
            #   - all ACTIVE/CLOSED  → that status
            #   - mixed              → "MIXED"   (the most-common status wins
            #                          in `dominant_status`, but the surface
            #                          label is "Mixed" so the user knows to
            #                          drill in)
            if len(counts) == 1:
                rollup_status = next(iter(counts.keys()))
            elif counts:
                rollup_status = 'MIXED'
            else:
                rollup_status = 'DRAFT'
            dominant_status = (
                max(counts.items(), key=lambda kv: kv[1])[0] if counts else 'DRAFT'
            )

            return {
                # Synthetic composite id — GenericListPage uses .id as the
                # row key, and (MDA, FY) is the natural rollup key here.
                'id': f"{mda_id_}-{fy_id_}",
                'mda_id': mda_id_,
                'mda_code': row['administrative__code'] or '',
                'mda_name': row['administrative__name'] or '',
                'fiscal_year_id': fy_id_,
                'fiscal_year_label': f"FY {row['fiscal_year__year']}" if row['fiscal_year__year'] else '',
                'fiscal_year_year': row['fiscal_year__year'] or '',
                'appropriation_count': row['appropriation_count'],
                'amount_approved': str(row['amount_approved']),
                'total_expended': str(row['total_expended']),
                'available_balance': str(row['available_balance']),
                'execution_rate': round(rate, 2),
                'sample_appropriation_id': row['sample_appropriation_id'],
                # Status breakdown — lets the rollup table show the real
                # state ("Draft" when every line is Draft, "Mixed" when
                # only some are) and gates the bulk-delete affordance.
                'status': rollup_status,
                'dominant_status': dominant_status,
                'status_counts': counts,
                'draft_count': counts.get('DRAFT', 0),
                'all_draft': total > 0 and counts.get('DRAFT', 0) == total,
                # Pre-filtered id buckets for the three bulk actions.
                # The frontend passes whichever bucket matches the action,
                # so each request is already correctly scoped.
                'draft_appropriation_ids': draft_ids,
                'approvable_appropriation_ids': approvable_ids,
                'activatable_appropriation_ids': activatable_ids,
            }

        rows = [_enrich(r) for r in rollup]

        # Same {count, next, previous, results} envelope as the flat list,
        # so the frontend's GenericListPage works without modification.
        page = self.paginate_queryset(rows)
        if page is not None:
            return self.get_paginated_response(page)
        return Response(rows)

    @action(detail=True, methods=['get'])
    def transactions(self, request, pk=None):
        """Per-appropriation line-item drill-down.

        Returns every transaction that contributes to the appropriation's
        ``total_committed`` / ``total_expended`` numbers so the user can
        see exactly *what* consumed the budget. Mirrors the source set of
        ``_compute_direct_disbursements`` in ``budget.models.Appropriation``
        — enumerates instead of summing.
        """
        from decimal import Decimal
        try:
            appr = self.get_queryset().get(pk=pk)
        except Appropriation.DoesNotExist:
            return Response(
                {'error': 'Appropriation not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        admin_legacy = getattr(appr.administrative, 'legacy_mda', None) if appr.administrative_id else None
        fund_legacy  = getattr(appr.fund,           'legacy_fund', None) if appr.fund_id else None
        from accounting.models.ncoa import EconomicSegment
        descendant_econ_segs = [appr.economic] if appr.economic_id else []
        frontier = list(descendant_econ_segs)
        while frontier:
            children = list(EconomicSegment.objects.filter(parent__in=frontier))
            descendant_econ_segs.extend(children)
            frontier = children
        legacy_accounts = [
            seg.legacy_account_id for seg in descendant_econ_segs
            if seg.legacy_account_id
        ]

        fy = appr.fiscal_year
        fy_start = getattr(fy, 'start_date', None)
        fy_end = getattr(fy, 'end_date', None)
        fy_year = getattr(fy, 'year', None)

        transactions: list[dict] = []
        # Each source-of-truth scan is wrapped in its own try/except so a
        # single broken FK or stale model field never sinks the whole
        # drill-down. Worst case: some sources are silently skipped and
        # the user still sees the appropriation summary plus whatever
        # transactions DID resolve. Errors are logged at warning.
        import logging
        _logger = logging.getLogger(__name__)

        # 1. PO commitments linked to this appropriation
        try:
            from procurement.models import ProcurementBudgetLink
            pb_links = (
                ProcurementBudgetLink.objects
                .filter(appropriation=appr)
                .select_related('purchase_order', 'purchase_order__vendor')
            )
            for link in pb_links:
                po = link.purchase_order
                # CLOSED commitments mean the vendor invoice has been
                # posted — the most informative source document is the
                # InvoiceMatching (3-way match record), which carries
                # both the GR/IR clearing journal AND the PO/GRN trail.
                # ACTIVE / INVOICED rows still belong with the PO since
                # the invoice may not yet exist or be Posted.
                src_url = f"/procurement/orders/{po.pk}" if po else ''
                src_ref = po.po_number if po else ''
                if link.status == 'CLOSED' and po:
                    matching = po.invoicematching_set.filter(
                        vendor_invoice__status='Posted',
                    ).order_by('-id').first() if hasattr(po, 'invoicematching_set') else None
                    if matching:
                        src_url = f"/procurement/matching/{matching.pk}"
                        src_ref = (
                            getattr(matching, 'verification_number', '')
                            or po.po_number
                        )
                transactions.append({
                    'type':        'PO_COMMITMENT',
                    'status':      link.status,
                    'kind':        'expended' if link.status == 'CLOSED' else 'committed',
                    'date':        (po.order_date.isoformat()
                                    if po and getattr(po, 'order_date', None) else ''),
                    'reference':   src_ref,
                    'description': (po.description or '') if po else '',
                    'party':       (po.vendor.name if po and po.vendor else ''),
                    'amount':      str(link.committed_amount or Decimal('0')),
                    'source_id':   po.pk if po else None,
                    'source_url':  src_url,
                })
        except Exception as exc:
            _logger.warning('appr %s: PO commitment source failed: %s', appr.pk, exc)

        # 2. Direct AP Vendor Invoices (no PO upstream)
        try:
            if admin_legacy and fund_legacy and legacy_accounts:
                from accounting.models.receivables import VendorInvoice
                vi_q = VendorInvoice.objects.filter(
                    status='Posted',
                    purchase_order__isnull=True,
                    mda=admin_legacy,
                    account_id__in=legacy_accounts,
                    fund=fund_legacy,
                ).select_related('vendor')
                if fy_start and fy_end:
                    vi_q = vi_q.filter(invoice_date__gte=fy_start, invoice_date__lte=fy_end)
                elif fy_year:
                    vi_q = vi_q.filter(invoice_date__year=fy_year)
                for vi in vi_q:
                    # Direct AP invoices don't have a dedicated detail
                    # frontend route — the VendorInvoice form is editable
                    # only while Draft, and Posted invoices live in
                    # APManagement's modal which doesn't accept a
                    # deep-link param. Best target is the linked
                    # JournalEntry: it shows the full DR/CR posting and
                    # carries the same memo back to the invoice.
                    je_id = getattr(vi, 'journal_entry_id', None)
                    src_url = (
                        f"/accounting/journals/{je_id}/edit"
                        if je_id else "/accounting/ap"
                    )
                    transactions.append({
                        'type':        'AP_INVOICE',
                        'status':      vi.status,
                        'kind':        'expended',
                        'date':        vi.invoice_date.isoformat() if vi.invoice_date else '',
                        'reference':   vi.invoice_number or '',
                        'description': vi.description or '',
                        'party':       vi.vendor.name if vi.vendor else '',
                        'amount':      str(vi.total_amount or Decimal('0')),
                        'source_id':   vi.pk,
                        'source_url':  src_url,
                    })
        except Exception as exc:
            _logger.warning('appr %s: VendorInvoice source failed: %s', appr.pk, exc)

        # 3. Direct Payment Vouchers
        # ``PaymentVoucherGov`` doesn't carry a dedicated payment_date
        # field — the payment moment is captured by ``updated_at`` once
        # the status flips to PAID, with ``created_at`` as the
        # voucher-creation date. We display whichever date is available
        # to avoid AttributeErrors that would 500 the whole endpoint.
        try:
            for pv in appr.payment_vouchers.filter(status='PAID', source_document=''):
                date_field = (
                    getattr(pv, 'updated_at', None)
                    or getattr(pv, 'created_at', None)
                )
                transactions.append({
                    'type':        'PV',
                    'status':      pv.status,
                    'kind':        'expended',
                    'date':        date_field.date().isoformat() if date_field else '',
                    'reference':   getattr(pv, 'voucher_number', '') or '',
                    'description': getattr(pv, 'narration', '') or '',
                    'party':       getattr(pv, 'payee_name', '') or '',
                    'amount':      str(getattr(pv, 'net_amount', None) or Decimal('0')),
                    'source_id':   pv.pk,
                    'source_url':  f"/accounting/payment-vouchers/{pv.pk}",
                })
        except Exception as exc:
            _logger.warning('appr %s: PaymentVoucher source failed: %s', appr.pk, exc)

        # 4. Direct Journal Entries (manual JVs)
        try:
            if admin_legacy and fund_legacy and legacy_accounts:
                from accounting.models.gl import JournalLine
                from django.db.models import Q
                je_q = JournalLine.objects.filter(
                    header__status='Posted',
                    header__mda=admin_legacy,
                    header__fund=fund_legacy,
                    account_id__in=legacy_accounts,
                ).filter(
                    Q(header__source_module__isnull=True)
                    | Q(header__source_module='')
                ).select_related('header', 'account')
                if fy_start and fy_end:
                    je_q = je_q.filter(
                        header__posting_date__gte=fy_start,
                        header__posting_date__lte=fy_end,
                    )
                elif fy_year:
                    je_q = je_q.filter(header__posting_date__year=fy_year)
                for jl in je_q:
                    hdr = jl.header
                    amt = (jl.debit or Decimal('0')) - (jl.credit or Decimal('0'))
                    transactions.append({
                        'type':        'JE',
                        'status':      hdr.status,
                        'kind':        'expended' if (jl.debit or 0) > 0 else 'reversal',
                        'date':        hdr.posting_date.isoformat() if hdr.posting_date else '',
                        'reference':   hdr.document_number or hdr.reference_number or f'JE-{hdr.pk}',
                        'description': hdr.description or jl.memo or '',
                        'party':       jl.account.name if jl.account else '',
                        'amount':      str(amt),
                        'source_id':   hdr.pk,
                        'source_url':  f"/accounting/journals/{hdr.pk}/edit",
                    })
        except Exception as exc:
            _logger.warning('appr %s: JournalLine source failed: %s', appr.pk, exc)

        transactions.sort(key=lambda t: t['date'] or '', reverse=True)

        committed_total = sum(
            (Decimal(t['amount']) for t in transactions if t['kind'] == 'committed'),
            Decimal('0'),
        )
        expended_total = sum(
            (Decimal(t['amount']) for t in transactions if t['kind'] == 'expended'),
            Decimal('0'),
        )

        return Response({
            'appropriation': AppropriationSerializer(appr).data,
            'transactions':  transactions,
            'summary': {
                'committed_count': sum(1 for t in transactions if t['kind'] == 'committed'),
                'committed_total': str(committed_total),
                'expended_count':  sum(1 for t in transactions if t['kind'] == 'expended'),
                'expended_total':  str(expended_total),
            },
        })

    @action(detail=False, methods=['get'], url_path='import-template')
    def import_template(self, request):
        """Download a CSV template for bulk Appropriation import.

        Every NCoA dimension is referenced by CODE (not numeric id) so the
        template is portable across tenants and re-importable from any
        environment. Comment lines starting with ``#`` are skipped on
        upload (same parser as the COA / Asset Category importers).

        Idempotent on re-upload: rows whose ``(fiscal_year, mda, economic,
        fund)`` tuple already exists are UPDATED in place; new tuples
        are created. The unique constraint on that tuple is enforced at
        the DB layer.
        """
        import io
        import csv as _csv
        from django.http import HttpResponse

        help_lines = [
            'Budget Appropriation import template.',
            'REQUIRED columns: fiscal_year, mda_code, economic_code, fund_code,',
            '  functional_code, programme_code, amount_approved.',
            'OPTIONAL columns and defaults:',
            '  geographic_code (blank = Statewide / non-geographic)',
            '  appropriation_type: ORIGINAL (default) | SUPPLEMENTARY | VIREMENT',
            '  law_reference: e.g. "Appropriation Act 2026"',
            '  enactment_date: YYYY-MM-DD',
            '  description, notes (free text)',
            '',
            'Re-uploading is idempotent — rows with a matching',
            '(fiscal_year, mda_code, economic_code, fund_code) tuple are UPDATED',
            'in place; new tuples are created. This lets you edit a saved CSV',
            'in Excel and re-upload to adjust amounts.',
            '',
            'Lookups by code: every NCoA dimension is resolved against its CODE',
            '(e.g. economic_code "21100100", mda_code "010100000000",',
            'fund_code "02101"). Dimensions whose codes do not exist in your',
            'NCoA tables are rejected with a clear error pointing at the row.',
            'Lines starting with # (like these) are ignored on import.',
        ]

        cols = [
            'fiscal_year', 'mda_code', 'economic_code', 'fund_code',
            'functional_code', 'programme_code', 'geographic_code',
            'appropriation_type', 'amount_approved',
            'law_reference', 'enactment_date', 'description', 'notes',
        ]
        examples = [
            ['2026', '010100000000', '21100100', '02101', '01101', '01000000', '', 'ORIGINAL', '500000000.00', 'Appropriation Act 2026', '2026-01-15', 'Personnel Cost - Salaries (Office of Governor)', ''],
            ['2026', '010100000000', '22100100', '02101', '01101', '01000000', '', 'ORIGINAL', '120000000.00', 'Appropriation Act 2026', '2026-01-15', 'Travel & Transport', ''],
            ['2026', '010100000000', '23010101', '02101', '01101', '01000000', '', 'ORIGINAL', '850000000.00', 'Appropriation Act 2026', '2026-01-15', 'Office Buildings — Capital Project', ''],
            ['2026', '020100000000', '21100100', '02101', '07101', '07000000', '', 'ORIGINAL', '300000000.00', 'Appropriation Act 2026', '2026-01-15', 'Personnel Cost (Min. of Health)', ''],
        ]

        output = io.StringIO()
        writer = _csv.writer(output)
        for line in help_lines:
            writer.writerow([f'# {line}'])
        writer.writerow(cols)
        for row in examples:
            writer.writerow(row)
        response = HttpResponse(output.getvalue(), content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="appropriation_import_template.csv"'
        return response

    @action(detail=False, methods=['post'], url_path='bulk-delete')
    def bulk_delete(self, request):
        """
        Bulk-delete appropriations — DRAFT-only safety gate.

        Only rows with status='DRAFT' may be deleted. Anything else (PENDING,
        APPROVED, ACTIVE, CLOSED, REVISED) is preserved and reported back so
        the UI can surface what was skipped.

        Body: { "ids": [<int>, ...] }
        Returns:
            {
              "deleted":          <count>,
              "skipped":          <count>,
              "skipped_details":  [{id, code, status}, ...]
            }
        """
        from django.db import transaction

        raw_ids = request.data.get('ids') or []
        if not isinstance(raw_ids, list) or not raw_ids:
            return Response(
                {'detail': 'Provide a non-empty "ids" list.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Coerce to ints, drop garbage
        ids: list[int] = []
        for raw in raw_ids:
            try:
                ids.append(int(raw))
            except (TypeError, ValueError):
                continue
        if not ids:
            return Response(
                {'detail': 'No valid integer ids supplied.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Honour OrganizationFilterMixin — SEPARATED users can only touch
        # rows their MDA is allowed to see.
        scoped_qs = self.filter_queryset(self.get_queryset()).filter(id__in=ids)

        # Partition: DRAFT (deletable) vs anything else (skipped).
        # Appropriation has no `code` of its own; surface economic__code
        # so the UI shows a meaningful identifier.
        deletable = list(scoped_qs.filter(status='DRAFT').values_list('id', flat=True))
        skipped_rows = list(
            scoped_qs.exclude(status='DRAFT').values('id', 'economic__code', 'status')
        )

        deleted_count = 0
        if deletable:
            with transaction.atomic():
                deleted_count, _ = (
                    self.get_queryset()
                    .filter(id__in=deletable, status='DRAFT')
                    .delete()
                )

        return Response({
            'deleted': deleted_count,
            'skipped': len(skipped_rows),
            'skipped_details': [
                {'id': r['id'], 'code': r.get('economic__code') or '', 'status': r['status']}
                for r in skipped_rows
            ],
        }, status=status.HTTP_200_OK)

    def _bulk_transition(
        self,
        request,
        *,
        target_status: str,
        from_statuses: tuple[str, ...],
        action_label: str,
    ):
        """
        Shared helper for bulk status transitions.

        Filters the request's `ids` to rows whose current status is in
        `from_statuses` (so an APPROVED row won't be re-approved, an ACTIVE
        row won't be re-activated, etc.), updates them in a single
        transaction, and returns a uniform envelope:

            { "transitioned": N, "skipped": M, "skipped_details": [...] }

        OrganizationFilterMixin scoping carries through, so SEPARATED-mode
        users can only transition their own MDA's lines.
        """
        from django.db import transaction
        from django.utils import timezone

        raw_ids = request.data.get('ids') or []
        if not isinstance(raw_ids, list) or not raw_ids:
            return Response(
                {'detail': 'Provide a non-empty "ids" list.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        ids: list[int] = []
        for raw in raw_ids:
            try:
                ids.append(int(raw))
            except (TypeError, ValueError):
                continue
        if not ids:
            return Response(
                {'detail': 'No valid integer ids supplied.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        scoped = self.filter_queryset(self.get_queryset()).filter(id__in=ids)
        eligible_qs = scoped.filter(status__in=from_statuses)
        eligible_ids = list(eligible_qs.values_list('id', flat=True))
        # Appropriation has no `code` field of its own; surface the
        # economic code instead — that's what users recognise on the line.
        skipped = list(
            scoped.exclude(status__in=from_statuses)
                  .values('id', 'economic__code', 'status')
        )

        transitioned = 0
        if eligible_ids:
            with transaction.atomic():
                now = timezone.now()
                # Match per-row endpoints which save with
                # update_fields=['status', 'updated_at'] — bulk .update()
                # bypasses save() so we set updated_at explicitly.
                update_fields = {'status': target_status, 'updated_at': now}
                # When activating, stamp enactment_date if absent — matches
                # the per-row `enact()` action's behaviour. Only fills
                # nulls so a real legislative date isn't overwritten.
                if target_status == 'ACTIVE':
                    eligible_qs.filter(enactment_date__isnull=True).update(
                        enactment_date=now.date(),
                    )
                transitioned = (
                    self.get_queryset()
                        .filter(id__in=eligible_ids, status__in=from_statuses)
                        .update(**update_fields)
                )

        return Response({
            'action': action_label,
            'transitioned': transitioned,
            'skipped': len(skipped),
            'skipped_details': [
                {'id': r['id'], 'code': r.get('economic__code') or '', 'status': r['status']}
                for r in skipped
            ],
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='bulk-approve')
    def bulk_approve(self, request):
        """
        Bulk-approve appropriations.

        Eligible rows: status in (DRAFT, SUBMITTED) → APPROVED.
        DRAFT rows skip the SUBMITTED step here — pragmatic for bulk
        operations on freshly-imported budgets that haven't gone through
        the per-row Submit click.
        """
        return self._bulk_transition(
            request,
            target_status='APPROVED',
            from_statuses=('DRAFT', 'SUBMITTED'),
            action_label='approve',
        )

    @action(detail=False, methods=['post'], url_path='bulk-activate')
    def bulk_activate(self, request):
        """
        Bulk-activate appropriations.

        Eligible rows: status in (APPROVED, SUBMITTED) → ACTIVE.
        Stamps enactment_date to today on rows that don't already have one.
        """
        return self._bulk_transition(
            request,
            target_status='ACTIVE',
            from_statuses=('APPROVED', 'SUBMITTED'),
            action_label='activate',
        )

    @action(detail=False, methods=['post'], url_path='bulk-import')
    def bulk_import(self, request):
        """Bulk-create or update appropriations from CSV / XLSX."""
        import io as _io
        import pandas as pd
        from decimal import Decimal, InvalidOperation
        from datetime import datetime

        file = request.FILES.get('file')
        if not file:
            return Response(
                {'error': 'A CSV or Excel file is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if file.size > 5 * 1024 * 1024:
            return Response(
                {'error': 'File too large. Maximum 5MB allowed.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        def _is_comment_cell(cell: str) -> bool:
            s = (cell or '').strip()
            return s.startswith('#') or s.startswith('"#') or s.startswith("'#")

        try:
            if file.name.endswith('.xlsx'):
                df_raw = pd.read_excel(
                    file, header=None, nrows=10000, dtype=str,
                    keep_default_na=False, na_filter=False,
                )
                if df_raw.empty:
                    return Response({'error': 'The uploaded spreadsheet is empty.'},
                                    status=status.HTTP_400_BAD_REQUEST)
                header_idx = None
                for i in range(len(df_raw)):
                    first = str(df_raw.iloc[i, 0]) if df_raw.shape[1] else ''
                    if first and first.strip() and not _is_comment_cell(first):
                        header_idx = i
                        break
                if header_idx is None:
                    return Response(
                        {'error': "Could not find a header row (every row starts with '#')."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                cols = df_raw.iloc[header_idx].astype(str).tolist()
                df = df_raw.iloc[header_idx + 1:].reset_index(drop=True)
                df.columns = cols
                if not df.empty:
                    first_col = df.columns[0]
                    mask = df[first_col].astype(str).map(_is_comment_cell)
                    df = df[~mask].reset_index(drop=True)
            else:
                raw = file.read()
                text = raw.decode('utf-8-sig', errors='replace') if isinstance(raw, bytes) else str(raw)
                cleaned_lines = [ln for ln in text.splitlines() if not _is_comment_cell(ln)]
                if not cleaned_lines:
                    return Response(
                        {'error': 'The uploaded CSV is empty (or only contains comment lines).'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                df = pd.read_csv(
                    _io.StringIO('\n'.join(cleaned_lines)),
                    nrows=10000, dtype=str,
                    keep_default_na=False, na_filter=False,
                )
        except Exception as e:
            return Response(
                {'error': f'Failed to parse file: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        df.columns = df.columns.str.strip().str.lower()
        required = {'fiscal_year', 'mda_code', 'economic_code', 'fund_code',
                    'functional_code', 'programme_code', 'amount_approved'}
        missing = required - set(df.columns)
        if missing:
            return Response(
                {'error': f"Missing required columns: {', '.join(sorted(missing))}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Lazy imports to avoid a circular at startup.
        from accounting.models.advanced import FiscalYear
        from accounting.models.ncoa import (
            AdministrativeSegment, EconomicSegment, FunctionalSegment,
            ProgrammeSegment, FundSegment, GeographicSegment,
        )
        from .models import Appropriation

        # Per-code caches so a 500-row CSV with 10 distinct MDAs only hits
        # the AdministrativeSegment table 10 times instead of 500.
        cache: dict[tuple[str, str], object | None] = {}
        def _resolve(model, kw, value):
            value = (value or '').strip()
            if not value:
                return None
            key = (model.__name__, value)
            if key in cache:
                return cache[key]
            obj = model.objects.filter(**{kw: value}).first()
            cache[key] = obj
            return obj

        def _str_cell(row, col, default=''):
            if col not in df.columns:
                return default
            v = row.get(col, '')
            return default if v in ('', None) else str(v).strip()

        valid_types = {'ORIGINAL', 'SUPPLEMENTARY', 'VIREMENT'}
        created = 0
        updated = 0
        errors: list[str] = []

        for idx, row in df.iterrows():
            row_num = idx + 2
            try:
                # Required fields
                year = _str_cell(row, 'fiscal_year')
                mda_code = _str_cell(row, 'mda_code')
                econ_code = _str_cell(row, 'economic_code')
                fund_code = _str_cell(row, 'fund_code')
                func_code = _str_cell(row, 'functional_code')
                prog_code = _str_cell(row, 'programme_code')
                amount_str = _str_cell(row, 'amount_approved')

                if not all([year, mda_code, econ_code, fund_code, func_code, prog_code, amount_str]):
                    errors.append(f'Row {row_num}: One or more required cells are empty.')
                    continue

                # Resolve fiscal_year (FK by year column; year is unique)
                try:
                    year_int = int(year)
                except (TypeError, ValueError):
                    errors.append(f"Row {row_num}: fiscal_year '{year}' must be a 4-digit integer like 2026.")
                    continue
                fy = FiscalYear.objects.filter(year=year_int).first()
                if not fy:
                    errors.append(
                        f'Row {row_num}: Fiscal year {year_int} not found in your '
                        f'Fiscal Years table. Create it first under Settings.'
                    )
                    continue

                mda = _resolve(AdministrativeSegment, 'code', mda_code)
                if not mda:
                    errors.append(f"Row {row_num}: mda_code '{mda_code}' not found in NCoA Administrative Segment.")
                    continue
                econ = _resolve(EconomicSegment, 'code', econ_code)
                if not econ:
                    errors.append(f"Row {row_num}: economic_code '{econ_code}' not found in NCoA Economic Segment.")
                    continue
                fund = _resolve(FundSegment, 'code', fund_code)
                if not fund:
                    errors.append(f"Row {row_num}: fund_code '{fund_code}' not found in NCoA Fund Segment.")
                    continue
                func = _resolve(FunctionalSegment, 'code', func_code)
                if not func:
                    errors.append(f"Row {row_num}: functional_code '{func_code}' not found in NCoA Functional Segment.")
                    continue
                prog = _resolve(ProgrammeSegment, 'code', prog_code)
                if not prog:
                    errors.append(f"Row {row_num}: programme_code '{prog_code}' not found in NCoA Programme Segment.")
                    continue

                # Optional geographic
                geo = None
                geo_code = _str_cell(row, 'geographic_code')
                if geo_code:
                    geo = _resolve(GeographicSegment, 'code', geo_code)
                    if not geo:
                        errors.append(f"Row {row_num}: geographic_code '{geo_code}' not found in NCoA Geographic Segment.")
                        continue

                # Numeric + enum validation
                try:
                    amount = Decimal(amount_str)
                except (TypeError, InvalidOperation):
                    errors.append(f"Row {row_num}: amount_approved '{amount_str}' must be a decimal number.")
                    continue

                appr_type = (_str_cell(row, 'appropriation_type', 'ORIGINAL') or 'ORIGINAL').upper()
                if appr_type not in valid_types:
                    errors.append(
                        f"Row {row_num}: appropriation_type '{appr_type}' must be one of "
                        f"{', '.join(sorted(valid_types))}."
                    )
                    continue

                # enactment_date — accept YYYY-MM-DD or DD/MM/YYYY (Nigeria)
                enact_str = _str_cell(row, 'enactment_date')
                enact_date = None
                if enact_str:
                    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y'):
                        try:
                            enact_date = datetime.strptime(enact_str, fmt).date()
                            break
                        except ValueError:
                            continue
                    if enact_date is None:
                        errors.append(
                            f"Row {row_num}: enactment_date '{enact_str}' must be YYYY-MM-DD or DD/MM/YYYY."
                        )
                        continue

                # Idempotent upsert on the unique tuple. The model has a
                # unique constraint on (fiscal_year, administrative,
                # economic, fund) per migration 0013, so update_or_create
                # by that key never duplicates.
                defaults = {
                    'functional': func,
                    'programme': prog,
                    'geographic': geo,
                    'amount_approved': amount,
                    'appropriation_type': appr_type,
                    'law_reference': _str_cell(row, 'law_reference'),
                    'description': _str_cell(row, 'description')[:500],
                    'notes': _str_cell(row, 'notes'),
                }
                if enact_date is not None:
                    defaults['enactment_date'] = enact_date

                _, was_created = Appropriation.objects.update_or_create(
                    fiscal_year=fy,
                    administrative=mda,
                    economic=econ,
                    fund=fund,
                    defaults=defaults,
                )
                if was_created:
                    created += 1
                else:
                    updated += 1

            except Exception as e:
                errors.append(f'Row {row_num}: {str(e)}')

        return Response({
            'success': True,
            'created': created,
            'updated': updated,
            'skipped': 0,
            'errors': errors,
        })

    @action(detail=False, methods=['get'], url_path='export')
    def export_data(self, request):
        """Export appropriations as a re-importable CSV."""
        import io
        import csv as _csv
        from django.http import HttpResponse

        cols = [
            'fiscal_year', 'mda_code', 'economic_code', 'fund_code',
            'functional_code', 'programme_code', 'geographic_code',
            'appropriation_type', 'amount_approved',
            'law_reference', 'enactment_date', 'description', 'notes',
            'status', 'total_expended', 'available_balance',
        ]
        output = io.StringIO()
        writer = _csv.writer(output)
        writer.writerow(cols)
        # OrganizationFilterMixin.get_queryset already enforces tenant-mode
        # isolation, so this export honours the active org / SEPARATED rules.
        qs = self.filter_queryset(self.get_queryset())
        for a in qs.iterator(chunk_size=500):
            writer.writerow([
                a.fiscal_year.year if a.fiscal_year else '',
                a.administrative.code if a.administrative else '',
                a.economic.code if a.economic else '',
                a.fund.code if a.fund else '',
                a.functional.code if a.functional else '',
                a.programme.code if a.programme else '',
                a.geographic.code if a.geographic else '',
                a.appropriation_type,
                a.amount_approved,
                a.law_reference,
                a.enactment_date.isoformat() if a.enactment_date else '',
                a.description,
                a.notes,
                a.status,
                a.cached_total_expended if a.cached_total_expended is not None else '',
                # available_balance is the live computed value via Account
                # property; export the cached form to avoid N queries.
                (a.amount_approved or 0) - (a.cached_total_expended or 0)
                    if a.cached_total_expended is not None else '',
            ])
        response = HttpResponse(output.getvalue(), content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="appropriations_export.csv"'
        return response

    @action(detail=True, methods=['post'])
    def submit(self, request, pk=None):
        """Submit a draft appropriation for review."""
        appro = self.get_object()
        if appro.status != 'DRAFT':
            return Response(
                {'error': f'Only DRAFT appropriations can be submitted. Current: "{appro.status}"'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        appro.status = 'SUBMITTED'
        appro.save(update_fields=['status', 'updated_at'])
        return Response(AppropriationSerializer(appro).data)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """Approve a submitted appropriation."""
        appro = self.get_object()
        if appro.status != 'SUBMITTED':
            return Response(
                {'error': f'Only SUBMITTED appropriations can be approved. Current: "{appro.status}"'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        appro.status = 'APPROVED'
        appro.save(update_fields=['status', 'updated_at'])
        return Response(AppropriationSerializer(appro).data)

    @action(detail=True, methods=['post'])
    def enact(self, request, pk=None):
        """Enact an approved appropriation — makes it ACTIVE for spending.

        H11 fix: do this race-safely. The previous code took no lock,
        so two concurrent enactments could both see status='APPROVED'
        and both flip ACTIVE — usually harmless but it doubled the
        ``original_amount`` snapshot setup below. Also previously the
        cached commitment totals were not refreshed at activation, so
        the budget execution report could show stale figures from a
        prior closed cycle until the first commit landed and refreshed
        them.

        Steps under one atomic + SELECT FOR UPDATE on the appropriation:
          1. Re-validate status under the lock.
          2. Capture ``original_amount`` snapshot (S2-04) if not set.
          3. Flip to ACTIVE + stamp enactment_date.
          4. Refresh cached committed/expended totals so reports
             show a clean post-enactment baseline immediately.
        """
        from django.db import transaction
        from django.utils import timezone
        from accounting.services.appropriation_totals import refresh_totals

        with transaction.atomic():
            appro = (
                self.get_queryset()
                .select_for_update()
                .get(pk=pk)
            )
            if appro.status not in ('APPROVED', 'SUBMITTED'):
                return Response(
                    {'error': f'Only APPROVED appropriations can be enacted. Current: "{appro.status}"'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            update_fields = ['status', 'enactment_date', 'updated_at']
            appro.status = 'ACTIVE'
            appro.enactment_date = appro.enactment_date or timezone.now().date()
            # S2-04 snapshot — capture the as-enacted amount once. After
            # this point ``amount_approved`` may evolve via virements
            # (becoming the IPSAS 24 "Final Budget"); ``original_amount``
            # stays immutable for the IPSAS variance disclosure.
            if appro.original_amount is None:
                appro.original_amount = appro.amount_approved
                update_fields.append('original_amount')
            appro.save(update_fields=update_fields)

            # Refresh cached totals so reports see a clean baseline.
            refresh_totals(appro)

        return Response(AppropriationSerializer(appro).data)

    @action(detail=True, methods=['post'])
    def close(self, request, pk=None):
        """Close an active appropriation at fiscal year end."""
        appro = self.get_object()
        if appro.status != 'ACTIVE':
            return Response(
                {'error': f'Only ACTIVE appropriations can be closed. Current: "{appro.status}"'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        appro.status = 'CLOSED'
        appro.save(update_fields=['status', 'updated_at'])
        return Response(AppropriationSerializer(appro).data)

    @action(detail=True, methods=['get'])
    def execution(self, request, pk=None):
        """Budget execution details for this appropriation."""
        appro = self.get_object()
        return Response({
            'appropriation_id': appro.pk,
            'mda': appro.administrative.name,
            'account': appro.economic.name,
            'amount_approved': str(appro.amount_approved),
            'total_warrants': str(appro.total_warrants_released),
            'total_committed': str(appro.total_committed),
            'total_expended': str(appro.total_expended),
            'available_balance': str(appro.available_balance),
            'execution_rate': appro.execution_rate,
        })

    @action(detail=False, methods=['get'], url_path='check-line')
    def check_line(self, request):
        """Real-time pre-submit check for a single proposed posting line.

        Used by line-driven forms (AP/AR invoice, Journal) to render a
        green / amber / red status indicator next to each line as the
        operator types account + amount, BEFORE they hit Save. This is
        the same engine that backend posting paths use — the answer
        you see here is the answer you'll get on Post.

        Query params:
            mda     — legacy accounting.MDA pk
            fund    — legacy accounting.Fund pk
            account — legacy accounting.Account pk
            amount  — Decimal-parseable; optional. When provided, also
                      checks the appropriation's available balance.

        Always returns HTTP 200 so the inline UI doesn't have to
        special-case 404 / 400 to render the status. The shape is:

            {
              "level":   "NONE" | "WARNING" | "STRICT",
              "blocked": bool,
              "reason":  str,                         # populated when blocked
              "warnings": [str, ...],                 # advisory notes
              "rule_description": str,                # which rule matched
              "appropriation": null | {
                  "id":             int,
                  "amount_approved":  str,
                  "available_balance": str,
                  "execution_rate":  float,
              },
            }
        """
        from decimal import Decimal as _D, InvalidOperation
        from accounting.models import MDA, Fund, Account
        from accounting.services.budget_check_rules import (
            check_policy, find_matching_appropriation,
        )

        mda_id = request.query_params.get('mda')
        fund_id = request.query_params.get('fund')
        account_id = request.query_params.get('account')
        amount_raw = request.query_params.get('amount')

        if not (mda_id and fund_id and account_id):
            # Not enough info to evaluate — return NONE so the UI shows
            # neutral state ("waiting for line to be filled in") rather
            # than a misleading green tick.
            return Response({
                'level': 'NONE', 'blocked': False, 'reason': '',
                'warnings': [], 'rule_description': '', 'appropriation': None,
            })

        try:
            amount = _D(str(amount_raw)) if amount_raw else None
        except (InvalidOperation, ValueError):
            amount = None

        mda = MDA.objects.filter(pk=mda_id).first()
        fund = Fund.objects.filter(pk=fund_id).first()
        account = Account.objects.filter(pk=account_id).first()
        if not (mda and fund and account):
            # Bad ids — frontend probably has stale dropdowns. Treat
            # as NONE so we don't surface an alarming red banner over
            # what is really a frontend cache problem.
            return Response({
                'level': 'NONE', 'blocked': False, 'reason': '',
                'warnings': ['MDA / Fund / Account id did not resolve to a record.'],
                'rule_description': '', 'appropriation': None,
            })

        appro = find_matching_appropriation(mda=mda, fund=fund, account=account)
        result = check_policy(
            account_code=account.code,
            appropriation=appro,
            requested_amount=amount,
            transaction_label='line',
            account_name=account.name,
        )
        appro_payload = None
        if appro is not None:
            appro_payload = {
                'id': appro.pk,
                'amount_approved': str(appro.amount_approved or 0),
                'available_balance': str(appro.available_balance),
                'execution_rate': appro.execution_rate,
            }
        return Response({
            'level': result.level,
            'blocked': result.blocked,
            'reason': result.reason,
            'warnings': list(result.warnings or []),
            'rule_description': result.rule_description,
            'appropriation': appro_payload,
        })

    @action(detail=False, methods=['get'], url_path='lookup')
    def lookup_by_dimensions(self, request):
        """Lookup an active appropriation by the 3 control pillars.

        Used by the PO form to preview budget availability before commitment.
        Query params: mda (legacy MDA pk), account (legacy Account pk), fund (legacy Fund pk).
        Returns matching appropriation + execution stats, or 404 if none.
        """
        from accounting.models.ncoa import AdministrativeSegment, EconomicSegment, FundSegment

        mda_id = request.query_params.get('mda')
        account_id = request.query_params.get('account')
        fund_id = request.query_params.get('fund')
        if not (mda_id and fund_id):
            return Response(
                {'error': 'mda and fund query parameters are required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Bridge legacy FK ids → NCoA segments via the legacy_* bridges
        try:
            admin_seg = AdministrativeSegment.objects.filter(legacy_mda_id=mda_id).first()
            fund_seg = FundSegment.objects.filter(legacy_fund_id=fund_id).first()
            econ_seg = (
                EconomicSegment.objects.filter(legacy_account_id=account_id).first()
                if account_id else None
            )
        except Exception:
            admin_seg = fund_seg = econ_seg = None

        if not admin_seg or not fund_seg:
            return Response(
                {'error': 'No NCoA segment found for given MDA/Fund',
                 'hint': 'Ensure NCoA segments are seeded and bridged to legacy models.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        qs = Appropriation.objects.filter(
            administrative=admin_seg, fund=fund_seg, status='ACTIVE',
        )
        if econ_seg:
            qs = qs.filter(economic=econ_seg)

        appro = qs.select_related('administrative', 'economic', 'fund').first()
        if not appro:
            return Response(
                {'found': False,
                 'error': f'No ACTIVE appropriation for MDA:{admin_seg.code} / Fund:{fund_seg.code}'
                           + (f' / Economic:{econ_seg.code}' if econ_seg else ''),
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response({
            'found': True,
            'appropriation_id': appro.pk,
            'mda': appro.administrative.name,
            'account': appro.economic.name,
            'fund': appro.fund.name,
            'amount_approved': str(appro.amount_approved),
            'total_warrants': str(appro.total_warrants_released),
            'total_committed': str(appro.total_committed),
            'total_expended': str(appro.total_expended),
            'available_balance': str(appro.available_balance),
            'execution_rate': appro.execution_rate,
        })


class WarrantViewSet(OrganizationFilterMixin, viewsets.ModelViewSet):
    org_filter_admin_field = 'appropriation__administrative'
    """Quarterly cash release (warrant) against enacted appropriation."""
    serializer_class = WarrantSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['status', 'quarter', 'appropriation']
    ordering = ['appropriation', 'quarter']

    def get_permissions(self):
        # S7-01 — Warrant release converts enacted appropriation into
        # actually-spendable cash authority. The action that creates the
        # downstream liability surface MUST be MFA-gated. Suspension
        # and cancellation are similarly sensitive.
        from accounting.permissions import RequiresMFA
        if self.action in ('release', 'suspend', 'cancel', 'revoke'):
            return [IsAuthenticated(), RequiresMFA()]
        return super().get_permissions()

    def get_queryset(self):
        return Warrant.objects.select_related(
            'appropriation__administrative', 'appropriation__economic',
        )

    # ── Cache refresh helper ────────────────────────────────────────────
    # A Warrant doesn't itself add to ``total_expended`` (expenditure is
    # recognised when a vendor invoice posts), but the warrant screen
    # surfaces ``cached_total_expended`` next to the new AIE and that
    # cache may have drifted since its last write. Every warrant
    # mutation refreshes the cached totals so the UI shows fresh
    # numbers immediately. The refresh is a single update with a
    # ``SELECT … FOR UPDATE`` lock — safe under concurrent writers.
    @staticmethod
    def _refresh_appropriation_totals(appropriation):
        if appropriation is None:
            return
        try:
            from accounting.services.appropriation_totals import refresh_totals
            refresh_totals(appropriation)
        except Exception:  # noqa: BLE001 — refresh is best-effort, never blocks the warrant write
            import logging
            logging.getLogger(__name__).exception(
                "Failed to refresh cached totals for appropriation %s",
                getattr(appropriation, 'pk', '?'),
            )

    def perform_create(self, serializer):
        warrant = serializer.save()
        self._refresh_appropriation_totals(warrant.appropriation)

    def perform_update(self, serializer):
        warrant = serializer.save()
        self._refresh_appropriation_totals(warrant.appropriation)

    def perform_destroy(self, instance):
        appropriation = instance.appropriation
        super().perform_destroy(instance)
        self._refresh_appropriation_totals(appropriation)

    @action(detail=True, methods=['post'])
    def release(self, request, pk=None):
        """Release a pending warrant (AIE) and notify MDA accountant + AG."""
        warrant = self.get_object()
        if warrant.status != 'PENDING':
            return Response(
                {'error': f'Only PENDING warrants can be released. Current: "{warrant.status}"'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        warrant.status = 'RELEASED'
        warrant.save(update_fields=['status', 'updated_at'])

        # ── Notify MDA accountant + AG on warrant release ──────
        self._notify_warrant_released(warrant, request.user)
        # ── Refresh cached expended/committed so the UI is fresh ──
        self._refresh_appropriation_totals(warrant.appropriation)

        return Response(WarrantSerializer(warrant).data)

    @action(detail=True, methods=['post'])
    def suspend(self, request, pk=None):
        """Suspend a released warrant."""
        warrant = self.get_object()
        if warrant.status != 'RELEASED':
            return Response(
                {'error': f'Only RELEASED warrants can be suspended. Current: "{warrant.status}"'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        warrant.status = 'SUSPENDED'
        warrant.save(update_fields=['status', 'updated_at'])
        self._refresh_appropriation_totals(warrant.appropriation)
        return Response(WarrantSerializer(warrant).data)

    def _notify_warrant_released(self, warrant, released_by):
        """Send notifications to MDA accountant and AG office on warrant release."""
        from core.models import Notification, UserOrganization

        mda = warrant.appropriation.administrative
        amount = warrant.amount_released
        quarter = warrant.quarter
        fy = warrant.appropriation.fiscal_year

        title = f"Warrant Released — Q{quarter} {fy}"
        message = (
            f"AIE (Authority to Incur Expenditure) released for "
            f"{mda.name}.\n\n"
            f"Quarter: Q{quarter}\n"
            f"Amount: NGN {amount:,.2f}\n"
            f"Appropriation: {warrant.appropriation.economic.name}\n"
            f"Released by: {released_by.get_full_name() or released_by.username}"
        )
        action_url = '/budget/warrants'

        # 1. Notify all users assigned to this MDA
        mda_users = UserOrganization.objects.filter(
            organization__administrative_segment=mda,
            organization__org_role='MDA',
            is_active=True,
        ).select_related('user').values_list('user', flat=True)

        # 2. Notify all users in AG office (FINANCE_AUTHORITY)
        ag_users = UserOrganization.objects.filter(
            organization__org_role='FINANCE_AUTHORITY',
            is_active=True,
        ).select_related('user').values_list('user', flat=True)

        # Combine and deduplicate
        from django.contrib.auth.models import User
        all_user_ids = set(list(mda_users) + list(ag_users))
        # Exclude the person who released it (they already know)
        all_user_ids.discard(released_by.pk)

        if all_user_ids:
            users = User.objects.filter(pk__in=all_user_ids)
            Notification.send(
                users=users,
                category='WARRANT',
                title=title,
                message=message,
                action_url=action_url,
                priority='HIGH',
                related_model='Warrant',
                related_id=warrant.pk,
            )


class BudgetExecutionView(APIView):
    """Budget execution summary + pre-expenditure validation endpoint."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Budget execution summary across all active appropriations.

        When the caller sets ``?format=xlsx|pdf|html`` the response is
        rendered and streamed as a download (routed via
        ``serve_report``). Plain JSON callers continue to get a flat
        list of rows (back-compat with GenericListPage-style consumers).
        """
        from decimal import Decimal
        from accounting.views.reporting_helpers import serve_report

        qs = Appropriation.objects.filter(status='ACTIVE')
        fiscal_year = request.query_params.get('fiscal_year')
        if fiscal_year:
            qs = qs.filter(fiscal_year_id=fiscal_year)

        rows = []
        total_approved = Decimal('0')
        total_committed = Decimal('0')
        total_expended = Decimal('0')
        total_available = Decimal('0')
        for appro in qs.select_related('administrative', 'economic', 'fund')[:100]:
            rows.append({
                'id': appro.pk,
                'mda': appro.administrative.name,
                'mda_code': appro.administrative.code,
                # Include BOTH economic code and name so the UI can render
                # them side-by-side ("24100100 — Domestic Loan Interest")
                # regardless of whether the cell is wide enough for both.
                'account': appro.economic.name,
                'account_code': appro.economic.code,
                'account_name': appro.economic.name,
                'fund': appro.fund.name,
                'fund_code': appro.fund.code,
                'approved': str(appro.amount_approved),
                'committed': str(appro.total_committed),
                'expended': str(appro.total_expended),
                'available': str(appro.available_balance),
                'execution_pct': appro.execution_rate,
            })
            total_approved += appro.amount_approved or Decimal('0')
            total_committed += appro.total_committed or Decimal('0')
            total_expended += appro.total_expended or Decimal('0')
            total_available += appro.available_balance or Decimal('0')

        fmt = (request.query_params.get('format') or 'json').strip().lower()
        if fmt in ('xlsx', 'excel', 'pdf', 'html'):
            overall_exec = (
                float(total_expended / total_approved * 100)
                if total_approved > 0 else 0.0
            )
            payload = {
                'title':       'Budget Execution Report',
                'fiscal_year': int(fiscal_year) if fiscal_year else None,
                'currency':    'NGN',
                'rows':        rows,
                'totals': {
                    'total_approved':   total_approved,
                    'total_committed':  total_committed,
                    'total_expended':   total_expended,
                    'total_available':  total_available,
                    'overall_execution_pct': overall_exec,
                },
            }
            return serve_report(
                request, payload,
                filename_stem=f'budget-execution-{fiscal_year or "all"}',
                report_type='budget.execution',
                fiscal_year=int(fiscal_year) if fiscal_year else 0,
                period=0,
            )

        # Default JSON: preserve the flat-list shape existing clients depend on.
        return Response(rows)

    def post(self, request):
        """Pre-expenditure budget validation (hard-stop check)."""
        ser = BudgetValidationRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        from budget.services import BudgetValidationService, BudgetExceededError
        try:
            result = BudgetValidationService.validate_expenditure(**ser.validated_data)
            return Response(result)
        except BudgetExceededError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class CommitmentReportView(APIView):
    """Budget commitment/encumbrance report — shows PO commitments against appropriations."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from procurement.models import ProcurementBudgetLink
        from django.db.models import Sum
        from accounting.views.reporting_helpers import serve_report

        qs = ProcurementBudgetLink.objects.select_related(
            'purchase_order', 'appropriation__administrative', 'appropriation__economic',
        ).order_by('-committed_at')

        status_filter = request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)

        items = []
        for link in qs[:100]:
            appr = link.appropriation
            items.append({
                'id': link.id,
                'purchase_order': str(link.purchase_order),
                'mda': appr.administrative.name if appr else '',
                'mda_code': appr.administrative.code if appr else '',
                # Emit both the economic code and the name so the UI
                # always shows "{code} — {name}" for the Economic Code
                # column, regardless of grid width.
                'account': appr.economic.name if appr else '',
                'account_code': appr.economic.code if appr else '',
                'account_name': appr.economic.name if appr else '',
                'committed_amount': str(link.committed_amount),
                'status': link.status,
                'committed_at': link.committed_at.isoformat() if link.committed_at else None,
                'appropriation_balance': str(appr.available_balance) if appr else '0',
            })

        totals = qs.aggregate(total_committed=Sum('committed_amount'))
        total_committed = totals['total_committed'] or 0
        count = qs.count()

        fmt = (request.query_params.get('format') or 'json').strip().lower()
        if fmt in ('xlsx', 'excel', 'pdf', 'html'):
            payload = {
                'title':       'Budget Commitment Report',
                'currency':    'NGN',
                'items':       items,
                'totals': {
                    'total_committed': total_committed,
                    'count':           count,
                },
            }
            return serve_report(
                request, payload,
                filename_stem='commitment-report',
                report_type='budget.commitment',
                fiscal_year=0,
                period=0,
            )

        return Response({
            'items': items,
            'total_committed': str(total_committed),
            'count': count,
        })


class WarrantUtilizationReportView(APIView):
    """Warrant utilization — released vs. consumed vs. variance.

    One row per active Appropriation that has at least one warrant (or
    that has actual consumption, so admins can see leaks where
    spending happened against an un-warranted appropriation). Columns:

      * warrants_released : sum of ``Warrant.amount_released`` with
        ``status='RELEASED'``.
      * consumed          : real single-count consumption against the
        appropriation (open_po + closed_po + direct), derived from
        ``amount_approved - available_balance``. Matches what
        ``check_warrant_availability`` uses so the report and the
        enforcement agree.
      * variance          : ``warrants_released - consumed``. Positive
        = headroom left under the warrant. Negative = over-drawn
        (meaning historical activity exceeded the warrant ceiling —
        needs a supplementary warrant or a reversal).
      * utilization_pct   : ``consumed / warrants_released * 100``.
      * status            : OK (util < 70%), WATCH (70-95), EXHAUSTED
        (95-100), OVERDRAWN (> 100).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from decimal import Decimal
        from django.db.models import Sum
        from accounting.views.reporting_helpers import serve_report

        fiscal_year = request.query_params.get('fiscal_year')
        mda_id = request.query_params.get('mda')
        fund_id = request.query_params.get('fund')

        qs = Appropriation.objects.filter(status='ACTIVE').select_related(
            'administrative', 'economic', 'fund', 'fiscal_year',
        )
        if fiscal_year:
            qs = qs.filter(fiscal_year__year=fiscal_year)
        if mda_id:
            qs = qs.filter(administrative_id=mda_id)
        if fund_id:
            qs = qs.filter(fund_id=fund_id)

        items = []
        total_released = Decimal('0')
        total_consumed = Decimal('0')
        total_approved = Decimal('0')
        buckets = {'OK': 0, 'WATCH': 0, 'EXHAUSTED': 0, 'OVERDRAWN': 0,
                   'NO_WARRANT': 0}

        for appro in qs:
            released = appro.total_warrants_released or Decimal('0')
            approved = appro.amount_approved or Decimal('0')
            available = appro.available_balance or Decimal('0')
            consumed = approved - available
            if consumed < 0:
                consumed = Decimal('0')
            variance = released - consumed

            # Skip rows with zero activity and zero warrant — nothing
            # useful to show in the report.
            if released == 0 and consumed == 0:
                continue

            if released == 0:
                util_pct = Decimal('0')
                row_status = 'NO_WARRANT'
            else:
                util_pct = (consumed / released) * Decimal('100')
                if consumed > released:
                    row_status = 'OVERDRAWN'
                elif util_pct >= Decimal('95'):
                    row_status = 'EXHAUSTED'
                elif util_pct >= Decimal('70'):
                    row_status = 'WATCH'
                else:
                    row_status = 'OK'

            # Warrant breakdown per quarter so admins can see the
            # release pattern at a glance.
            warrants_by_qtr = list(
                appro.warrants.filter(status='RELEASED')
                .order_by('quarter')
                .values('quarter', 'amount_released', 'release_date',
                        'authority_reference')
            )

            items.append({
                'appropriation_id':  appro.pk,
                'mda_code':          appro.administrative.code,
                'mda':               appro.administrative.name,
                'account_code':      appro.economic.code,
                'account_name':      appro.economic.name,
                'fund_code':         appro.fund.code,
                'fund':              appro.fund.name,
                'fiscal_year':       appro.fiscal_year.year,
                'amount_approved':   str(approved),
                'warrants_released': str(released),
                'consumed':          str(consumed),
                'variance':          str(variance),
                'utilization_pct':   str(util_pct.quantize(Decimal('0.01'))),
                'status':            row_status,
                'warrants':          [
                    {
                        'quarter':             w['quarter'],
                        'amount_released':     str(w['amount_released']),
                        'release_date':        w['release_date'].isoformat() if w['release_date'] else None,
                        'authority_reference': w['authority_reference'],
                    }
                    for w in warrants_by_qtr
                ],
            })
            total_released += released
            total_consumed += consumed
            total_approved += approved
            buckets[row_status] += 1

        # Sort so OVERDRAWN + EXHAUSTED surface first (admins need to
        # act on those). Then by utilization descending.
        _rank = {
            'OVERDRAWN': 0, 'EXHAUSTED': 1, 'WATCH': 2,
            'OK': 3, 'NO_WARRANT': 4,
        }
        items.sort(
            key=lambda r: (_rank[r['status']], -Decimal(r['utilization_pct'])),
        )

        total_variance = total_released - total_consumed
        overall_util = (
            (total_consumed / total_released * Decimal('100')).quantize(Decimal('0.01'))
            if total_released > 0 else Decimal('0')
        )

        payload = {
            'title':    'Warrant Utilization Report',
            'standard': 'PFM Act / Fin Reg §§ 400–417',
            'currency': 'NGN',
            'fiscal_year': int(fiscal_year) if fiscal_year else None,
            'items':    items,
            'totals': {
                'total_approved':         str(total_approved),
                'total_warrants_released':str(total_released),
                'total_consumed':         str(total_consumed),
                'total_variance':         str(total_variance),
                'overall_utilization_pct':str(overall_util),
                'status_counts':          buckets,
                'row_count':              len(items),
            },
        }

        fmt = (request.query_params.get('format') or 'json').strip().lower()
        if fmt in ('xlsx', 'excel', 'pdf', 'html'):
            return serve_report(
                request, payload,
                filename_stem=f'warrant-utilization-{fiscal_year or "all"}',
                report_type='budget.warrant-utilization',
                fiscal_year=int(fiscal_year) if fiscal_year else 0,
                period=0,
            )

        return Response(payload)


class RevenueBudgetViewSet(OrganizationFilterMixin, viewsets.ModelViewSet):
    """Revenue budget targets — statistical (no enforcement).

    Tracks estimated vs actual IGR/FAAC collections per MDA per account.
    """
    org_filter_admin_field = 'administrative'
    serializer_class = RevenueBudgetSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['fiscal_year', 'status', 'administrative']
    ordering = ['fiscal_year', 'administrative', 'economic']

    def get_queryset(self):
        return RevenueBudget.objects.select_related(
            'administrative', 'economic', 'fund', 'fiscal_year',
        )

    @action(detail=False, methods=['get'], url_path='import-template')
    def import_template(self, request):
        """CSV template for bulk revenue budget import."""
        import io
        import csv
        from django.http import HttpResponse

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            'fiscal_year', 'administrative_code', 'economic_code', 'fund_code',
            'estimated_amount', 'jan', 'feb', 'mar', 'apr', 'may', 'jun',
            'jul', 'aug', 'sep', 'oct', 'nov', 'dec', 'description',
        ])
        writer.writerow([
            '2026', '011300000000', '11100100', '08000',
            '500000000', '', '', '', '', '', '',
            '', '', '', '', '', '', 'PAYE from SIRS',
        ])
        writer.writerow([
            '2026', '010600000000', '12100100', '08000',
            '120000000', '10000000', '10000000', '10000000', '10000000',
            '10000000', '10000000', '10000000', '10000000', '10000000',
            '10000000', '10000000', '10000000', 'Fees and fines',
        ])

        response = HttpResponse(output.getvalue(), content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="revenue_budget_template.csv"'
        return response

    @action(detail=False, methods=['post'], url_path='bulk-import')
    def bulk_import(self, request):
        """Bulk import revenue budget targets from CSV/Excel."""
        import pandas as pd
        from accounting.models.advanced import FiscalYear
        from accounting.models.ncoa import AdministrativeSegment, EconomicSegment, FundSegment

        file = request.FILES.get('file')
        if not file:
            return Response({'error': 'CSV or Excel file required'}, status=status.HTTP_400_BAD_REQUEST)
        if file.size > 5 * 1024 * 1024:
            return Response({'error': 'Max 5MB'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            df = pd.read_excel(file, nrows=10000) if file.name.endswith('.xlsx') else pd.read_csv(file, nrows=10000)
        except Exception as e:
            return Response({'error': f'Parse error: {e}'}, status=status.HTTP_400_BAD_REQUEST)

        df.columns = df.columns.str.strip().str.lower()
        required = {'fiscal_year', 'administrative_code', 'economic_code', 'fund_code', 'estimated_amount'}
        missing = required - set(df.columns)
        if missing:
            return Response({'error': f'Missing columns: {", ".join(missing)}'}, status=status.HTTP_400_BAD_REQUEST)

        month_cols = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec']
        created, skipped, errors = 0, 0, []

        for idx, row in df.iterrows():
            row_num = idx + 2
            try:
                fy = FiscalYear.objects.filter(year=int(row['fiscal_year'])).first()
                admin = AdministrativeSegment.objects.filter(code=str(row['administrative_code']).strip()).first()
                econ = EconomicSegment.objects.filter(code=str(row['economic_code']).strip()).first()
                fund = FundSegment.objects.filter(code=str(row['fund_code']).strip()).first()

                if not fy:
                    errors.append(f'Row {row_num}: Fiscal year {row["fiscal_year"]} not found')
                    continue
                if not admin:
                    errors.append(f'Row {row_num}: Admin code {row["administrative_code"]} not found')
                    continue
                if not econ:
                    errors.append(f'Row {row_num}: Economic code {row["economic_code"]} not found')
                    continue
                if not fund:
                    errors.append(f'Row {row_num}: Fund code {row["fund_code"]} not found')
                    continue

                amt = float(row['estimated_amount'])
                if amt <= 0:
                    errors.append(f'Row {row_num}: Invalid amount')
                    continue

                # Check duplicate
                if RevenueBudget.objects.filter(
                    fiscal_year=fy, administrative=admin, economic=econ, fund=fund,
                ).exists():
                    skipped += 1
                    continue

                # Build monthly spread if any month columns have values
                spread = {}
                for i, col in enumerate(month_cols):
                    if col in df.columns:
                        val = row.get(col)
                        if pd.notna(val) and float(val) > 0:
                            spread[str(i + 1)] = float(val)

                desc = str(row.get('description', '')).strip() if pd.notna(row.get('description')) else ''

                RevenueBudget.objects.create(
                    fiscal_year=fy, administrative=admin, economic=econ, fund=fund,
                    estimated_amount=amt,
                    monthly_spread=spread if spread else None,
                    status='ACTIVE',
                    description=desc,
                )
                created += 1
            except Exception as e:
                errors.append(f'Row {row_num}: {e}')

        return Response({
            'success': True, 'created': created, 'updated': 0, 'skipped': skipped, 'errors': errors,
        })

    @action(detail=False, methods=['post'], url_path='copy-from-prior-year')
    def copy_from_prior_year(self, request):
        """Copy prior year's actual revenue as budget targets for a new year.

        Reads GL credit balances for revenue accounts (type 1) from the prior
        fiscal year and creates DRAFT revenue budget records for the target year.
        """
        from accounting.models.advanced import FiscalYear

        target_year_id = request.data.get('target_fiscal_year_id')
        if not target_year_id:
            return Response({'error': 'target_fiscal_year_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        target_fy = FiscalYear.objects.filter(pk=target_year_id).first()
        if not target_fy:
            return Response({'error': 'Target fiscal year not found'}, status=status.HTTP_400_BAD_REQUEST)

        # Find the prior year
        prior_fy = FiscalYear.objects.filter(year=target_fy.year - 1).first()
        if not prior_fy:
            return Response(
                {'error': f'No fiscal year found for {target_fy.year - 1}. Cannot copy prior year actuals.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Get all existing revenue budgets for this target year (to avoid duplicates)
        existing = set(
            RevenueBudget.objects.filter(fiscal_year=target_fy)
            .values_list('administrative_id', 'economic_id', 'fund_id')
        )

        # Get prior year revenue actuals from appropriations that had revenue accounts
        # Or from GL balances for revenue accounts (type 1)
        from accounting.models.ncoa import EconomicSegment

        revenue_segments = EconomicSegment.objects.filter(
            account_type_code='1', is_active=True,
        )

        created = 0
        skipped = 0

        # Look at prior year's existing revenue budgets and use their actuals
        prior_budgets = RevenueBudget.objects.filter(
            fiscal_year=prior_fy, status__in=['ACTIVE', 'CLOSED'],
        ).select_related('administrative', 'economic', 'fund')

        for pb in prior_budgets:
            key = (pb.administrative_id, pb.economic_id, pb.fund_id)
            if key in existing:
                skipped += 1
                continue

            # Use actual collected if > 0, otherwise use the prior target
            actual = pb.actual_collected
            target = actual if actual > 0 else pb.estimated_amount

            RevenueBudget.objects.create(
                fiscal_year=target_fy,
                administrative=pb.administrative,
                economic=pb.economic,
                fund=pb.fund,
                estimated_amount=target,
                status='DRAFT',
                description=f'Copied from FY{prior_fy.year} — prior actual: NGN {actual:,.2f}',
            )
            created += 1

        return Response({
            'success': True,
            'created': created,
            'skipped': skipped,
            'source_year': prior_fy.year,
            'target_year': target_fy.year,
            'message': f'{created} revenue targets created from FY{prior_fy.year} actuals as DRAFT',
        })


class AppropriationVirementViewSet(viewsets.ModelViewSet):
    """CRUD + workflow actions for Appropriation virements.

    Creation goes through the service layer so every virement picks up
    the integrity guards (same fiscal year, distinct rows, source has
    enough available balance, reference-number allocation).

    Actions:
      * ``POST .../{id}/submit/``   — DRAFT → SUBMITTED
      * ``POST .../{id}/approve/``  — SUBMITTED → APPLIED (atomically
                                      moves the money + resets caches)
      * ``POST .../{id}/reject/``   — with ``reason`` in body
    """
    queryset = AppropriationVirement.objects.select_related(
        'from_appropriation__administrative',
        'from_appropriation__economic',
        'from_appropriation__fund',
        'from_appropriation__fiscal_year',
        'to_appropriation__administrative',
        'to_appropriation__economic',
        'to_appropriation__fund',
        'to_appropriation__fiscal_year',
        'submitted_by', 'approved_by',
    ).all()
    serializer_class = AppropriationVirementSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['status', 'from_appropriation', 'to_appropriation']

    def create(self, request, *args, **kwargs):
        from budget.services_virement import create_virement, VirementError
        from budget.models import Appropriation

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            virement = create_virement(
                from_appropriation=data['from_appropriation'],
                to_appropriation=data['to_appropriation'],
                amount=data['amount'],
                reason=data.get('reason', ''),
                user=request.user,
            )
        except VirementError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        out = self.get_serializer(virement)
        return Response(out.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def submit(self, request, pk=None):
        from budget.services_virement import submit_virement, VirementError
        virement = self.get_object()
        try:
            submit_virement(virement, user=request.user)
        except VirementError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(virement).data)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        from budget.services_virement import (
            approve_and_apply_virement, VirementError,
        )
        virement = self.get_object()
        try:
            approve_and_apply_virement(virement, user=request.user)
        except VirementError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(virement).data)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        from budget.services_virement import reject_virement, VirementError
        virement = self.get_object()
        reason = request.data.get('reason', '')
        if not reason:
            return Response(
                {'detail': 'Rejection reason is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            reject_virement(virement, user=request.user, reason=reason)
        except VirementError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(virement).data)
