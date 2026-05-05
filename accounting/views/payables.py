from .common import (
    viewsets, status, Response, action, transaction, Decimal, AccountingPagination, Sum,
)
from django.db.models import F
from core.mixins import OrganizationFilterMixin
from core.permissions import IsApprover
from ..models import (
    VendorInvoice, Payment, PaymentAllocation,
    Account, JournalHeader, JournalLine, BudgetEncumbrance, TransactionSequence,
)
from ..serializers import VendorInvoiceSerializer, PaymentSerializer, PaymentAllocationSerializer


class VendorInvoiceViewSet(OrganizationFilterMixin, viewsets.ModelViewSet):
    # Tenant MDA-isolation: in SEPARATED mode the queryset is auto-
    # filtered to the operator's active MDA. In UNIFIED mode every
    # invoice is visible. Mirrors PaymentVoucher / Treasury / Revenue
    # viewsets which already use this mixin.
    org_filter_field = 'mda'
    queryset = VendorInvoice.objects.all().select_related('vendor', 'fund', 'function', 'program', 'geo', 'currency', 'account')
    serializer_class = VendorInvoiceSerializer
    filterset_fields = ['status', 'vendor', 'invoice_date']
    search_fields = ['invoice_number', 'reference', 'vendor__name', 'description']
    ordering_fields = ['invoice_date', 'invoice_number', 'status', 'total_amount']
    pagination_class = AccountingPagination

    def get_queryset(self):
        # Default: most-recently-saved first (by pk desc). A draft
        # invoice just captured by the user must appear at the top of
        # the list regardless of its invoice_date — otherwise back-dated
        # drafts get buried. ``-invoice_date`` stays as a secondary
        # tiebreaker. User can still override via ?ordering=.
        qs = super().get_queryset()
        if not self.request.query_params.get('ordering'):
            qs = qs.order_by('-id', '-invoice_date')
        return qs

    # Project rule (memory: feedback_draft_immutable_after_post): non-Draft
    # documents are immutable. Only Drafts can be edited; users who need to
    # change a Posted/Approved invoice must reverse it (issue a credit memo).
    # Frontend hides the Edit affordance on non-Draft rows; this guard is the
    # backend defense in depth.
    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.status != 'Draft':
            return Response(
                {'error': f'Cannot modify a {instance.status.lower()} vendor invoice. '
                          f'Issue a credit memo to reverse it.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.status != 'Draft':
            return Response(
                {'error': f'Cannot modify a {instance.status.lower()} vendor invoice. '
                          f'Issue a credit memo to reverse it.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # PV-link lock: even Draft invoices can't be edited once a PV
        # has been raised against them (would corrupt the auto-filled
        # PV record). The PV must be cancelled / reversed first.
        if self._linked_active_pv(instance) is not None:
            pv = self._linked_active_pv(instance)
            return Response(
                {
                    'error': (
                        f'Cannot modify this invoice: a Payment Voucher '
                        f'({pv.voucher_number}, status {pv.status}) has '
                        f'been raised against it. Cancel or reverse the '
                        f'PV first.'
                    ),
                    'pv_link_locked': True,
                    'payment_voucher_number': pv.voucher_number,
                    'payment_voucher_status': pv.status,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        """Block delete (the closest thing AP has to "reject") when the
        invoice has an active Payment Voucher linked. Cancel the PV
        first if the invoice really needs to go away."""
        instance = self.get_object()
        pv = self._linked_active_pv(instance)
        if pv is not None:
            return Response(
                {
                    'error': (
                        f'Cannot delete this invoice: a Payment Voucher '
                        f'({pv.voucher_number}, status {pv.status}) has '
                        f'been raised against it. Cancel or reverse the '
                        f'PV first.'
                    ),
                    'pv_link_locked': True,
                    'payment_voucher_number': pv.voucher_number,
                    'payment_voucher_status': pv.status,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().destroy(request, *args, **kwargs)

    @staticmethod
    def _linked_active_pv(invoice):
        """Return the linked PaymentVoucherGov if one exists in a
        non-cancelled / non-reversed state, else None. Mirrors the
        serializer-level lookup convention (match by invoice_number)."""
        if not getattr(invoice, 'invoice_number', None):
            return None
        from accounting.models.treasury import PaymentVoucherGov
        pv = (
            PaymentVoucherGov.objects
            .filter(invoice_number=invoice.invoice_number)
            .order_by('-id')
            .first()
        )
        if pv is not None and pv.status not in ('CANCELLED', 'REVERSED'):
            return pv
        return None

    @action(detail=True, methods=['post'], url_path='create-draft-voucher')
    def create_draft_voucher(self, request, pk=None):
        """Auto-create a draft PaymentVoucherGov from this invoice.

        Same shape as ``contracts.IPCViewSet.create_draft_voucher`` —
        denormalises payee + amount + invoice ref into a fresh PV in
        DRAFT, returns ``{invoice, payment_voucher}`` so the SPA can
        navigate straight to the new PV for review.

        Idempotent: re-calling returns the existing PV linked by
        invoice number rather than creating a duplicate.
        """
        from accounting.services.pv_factory import (
            create_draft_voucher_from_invoice, PVFactoryError,
        )
        invoice = self.get_object()
        try:
            pv = create_draft_voucher_from_invoice(
                invoice=invoice, actor=request.user,
                notes=request.data.get('notes', ''),
            )
        except PVFactoryError as exc:
            return Response(
                {'error': str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({
            'invoice': {
                'id': invoice.pk,
                'invoice_number': invoice.invoice_number,
                'status': invoice.status,
            },
            'payment_voucher': {
                'id': pv.pk,
                'voucher_number': pv.voucher_number,
                'status': pv.status,
                'gross_amount': str(pv.gross_amount),
                'net_amount': str(pv.net_amount),
            },
        })

    @action(detail=False, methods=['get'])
    def payable(self, request):
        """List invoices that are approved and have a balance due — ready for PV creation.

        Supports search via ?search= query param for invoice number or vendor name.
        Used by the Payment Voucher form to search and auto-populate from invoice.
        """
        qs = VendorInvoice.objects.filter(
            status__in=['Approved', 'Partially Paid'],
        ).select_related('vendor', 'account', 'mda', 'fund', 'function', 'program', 'geo')

        search = request.query_params.get('search', '').strip()
        if search:
            from django.db.models import Q
            qs = qs.filter(
                Q(invoice_number__icontains=search) |
                Q(reference__icontains=search) |
                Q(vendor__name__icontains=search) |
                Q(description__icontains=search)
            )

        invoices = qs.order_by('-invoice_date')[:50]

        results = []
        for inv in invoices:
            results.append({
                'id': inv.id,
                'invoice_number': inv.invoice_number,
                'reference': inv.reference,
                'vendor_name': inv.vendor.name if inv.vendor else '',
                'vendor_bank': getattr(inv.vendor, 'bank_name', '') if inv.vendor else '',
                'vendor_account': getattr(inv.vendor, 'bank_account_number', '') if inv.vendor else '',
                'vendor_sort_code': getattr(inv.vendor, 'bank_sort_code', '') if inv.vendor else '',
                'invoice_date': str(inv.invoice_date),
                'due_date': str(inv.due_date),
                'total_amount': str(inv.total_amount),
                'paid_amount': str(inv.paid_amount),
                'balance_due': str(inv.balance_due),
                'description': inv.description,
                'status': inv.status,
                'account_code': inv.account.code if inv.account else '',
                'account_name': inv.account.name if inv.account else '',
                'mda_code': inv.mda.code if inv.mda else '',
                'mda_name': inv.mda.name if inv.mda else '',
                'fund_code': getattr(inv.fund, 'code', '') if inv.fund else '',
                'function_code': getattr(inv.function, 'code', '') if inv.function else '',
                'program_code': getattr(inv.program, 'code', '') if inv.program else '',
                'geo_code': getattr(inv.geo, 'code', '') if inv.geo else '',
                'purchase_order': inv.purchase_order.po_number if inv.purchase_order else '',
            })

        return Response(results)

    @action(detail=False, methods=['get'], url_path='import-template')
    def import_template(self, request):
        """Download CSV template for bulk vendor invoice import."""
        import io
        import csv
        from django.http import HttpResponse

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            'mda_code', 'vendor_name', 'reference', 'invoice_date', 'due_date',
            'description', 'account_code', 'amount', 'tax_code', 'wht_code',
            'fund_code', 'function_code', 'program_code', 'geo_code',
        ])
        writer.writerow([
            '050200000000', 'Acme Supplies Ltd', 'INV-2026-001', '2026-04-15', '2026-05-15',
            'Office supplies Q2', '22100100', '500000.00', '', '',
            '01000', '70100', '01010000000000', '51000000',
        ])
        writer.writerow([
            '050100000000', 'Delta Construction Co', 'INV-2026-002', '2026-04-20', '2026-06-20',
            'Road repair contract', '23100100', '25000000.00', 'VAT', '5%WHT',
            '02000', '70400', '02030100010000', '51000100',
        ])

        response = HttpResponse(output.getvalue(), content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="vendor_invoice_template.csv"'
        return response

    @action(detail=False, methods=['post'], url_path='bulk-import')
    def bulk_import(self, request):
        """Bulk import vendor invoices from CSV/Excel."""
        import pandas as pd
        from accounting.models.gl import MDA, Account

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
        required = {'vendor_name', 'reference', 'invoice_date', 'account_code', 'amount'}
        missing = required - set(df.columns)
        if missing:
            return Response({'error': f'Missing columns: {", ".join(missing)}'}, status=status.HTTP_400_BAD_REQUEST)

        from procurement.models import Vendor
        created, skipped, errors = 0, 0, []

        # Wrap the whole loop in a single atomic. If a row fails its
        # per-row try/except already collects the error and the loop
        # continues. If the request itself dies mid-loop (timeout,
        # OOM, worker kill) the outer atomic rolls back every row
        # that wasn't yet flushed — no partial / inconsistent imports
        # are persisted to the DB.
        with transaction.atomic():
            for idx, row in df.iterrows():
                row_num = idx + 2
                try:
                    vendor_name = str(row['vendor_name']).strip()
                    vendor = Vendor.objects.filter(name__iexact=vendor_name).first()
                    if not vendor:
                        errors.append(f'Row {row_num}: Vendor "{vendor_name}" not found')
                        continue

                    ref = str(row['reference']).strip()
                    if VendorInvoice.objects.filter(reference=ref).exists():
                        skipped += 1
                        continue

                    acct = Account.objects.filter(code=str(row['account_code']).strip()).first()
                    mda = None
                    if 'mda_code' in df.columns and pd.notna(row.get('mda_code')):
                        mda = MDA.objects.filter(code=str(row['mda_code']).strip()).first()

                    amt = float(row['amount'])
                    if amt <= 0:
                        errors.append(f'Row {row_num}: Invalid amount')
                        continue

                    from accounting.models.gl import Fund, Function, Program, Geo
                    fund = Fund.objects.filter(code=str(row.get('fund_code', '')).strip()).first() if pd.notna(row.get('fund_code')) else None
                    func = Function.objects.filter(code=str(row.get('function_code', '')).strip()).first() if pd.notna(row.get('function_code')) else None
                    prog = Program.objects.filter(code=str(row.get('program_code', '')).strip()).first() if pd.notna(row.get('program_code')) else None
                    geo = Geo.objects.filter(code=str(row.get('geo_code', '')).strip()).first() if pd.notna(row.get('geo_code')) else None

                    desc = str(row.get('description', '')).strip() if pd.notna(row.get('description')) else ''
                    due = str(row.get('due_date', row['invoice_date'])).strip()[:10]

                    inv = VendorInvoice.objects.create(
                        vendor=vendor, reference=ref, description=desc,
                        invoice_date=str(row['invoice_date']).strip()[:10],
                        due_date=due,
                        account=acct, mda=mda,
                        fund=fund, function=func, program=prog, geo=geo,
                        total_amount=amt, subtotal=amt,
                    )
                    created += 1
                except Exception as e:
                    errors.append(f'Row {row_num}: {e}')

        return Response({
            'success': True, 'created': created, 'updated': 0, 'skipped': skipped, 'errors': errors,
        })

    def get_permissions(self):
        # S7-01 — MFA-gate the sensitive write actions. A fresh MFA
        # verification is required to post an invoice, approve it, or
        # post a credit memo (all three move money on the GL). Read
        # and draft-edit actions keep the default auth.
        from accounting.permissions import RequiresMFA
        if self.action == 'post_invoice':
            return [IsApprover('post'), RequiresMFA()]
        if self.action in ('approve_invoice', 'post_credit_memo'):
            return [RequiresMFA()]
        return super().get_permissions()

    def perform_destroy(self, instance):
        if instance.status != 'Draft':
            from rest_framework.exceptions import ValidationError
            raise ValidationError("Only draft vendor invoices can be deleted.")
        super().perform_destroy(instance)

    @action(detail=True, methods=['get'])
    def simulate_posting(self, request, pk=None):
        """Return the PROPOSED DR/CR journal entries without writing anything.

        Used by the AP View modal to render accounting entries even for
        Draft / Approved-but-not-posted invoices. The proposal is the
        same journal that ``post_invoice`` would create — calculated
        from the invoice's amounts + configured default GL accounts —
        so what the user sees here equals what actually books on Post.

        Decision tree (mirrors post_invoice):
        - PO-backed (3-way match path): DR GR/IR Clearing
        - Direct (no PO):                DR invoice.account (or
          PURCHASE_EXPENSE fallback)
        - Tax > 0:   DR Input Tax / VAT
        - Always:    CR Accounts Payable  for total_amount

        Returns a response shaped like the JournalDetailSerializer
        output so the frontend can render it with the same React
        component as a posted journal (just flagging ``simulated:
        true`` so the UI can label it "Proposed").
        """
        from django.conf import settings as django_settings
        from decimal import Decimal

        invoice = self.get_object()
        default_gl = getattr(django_settings, 'DEFAULT_GL_ACCOUNTS', {})
        has_po = bool(invoice.purchase_order_id)

        # AP account discovery — same ladder as post_invoice():
        #   1. reconciliation_type='accounts_payable' (CoA-portable)
        #   2. DEFAULT_GL_ACCOUNTS code
        #   3. Liability + name~"Payable" heuristic
        ap_account = Account.objects.filter(
            reconciliation_type='accounts_payable', is_active=True,
        ).first()
        if not ap_account:
            ap_code = default_gl.get('ACCOUNTS_PAYABLE', '20100000')
            ap_account = Account.objects.filter(code=ap_code).first()
        if not ap_account:
            ap_account = Account.objects.filter(
                account_type='Liability', name__icontains='Payable',
            ).first()

        # Build proposed lines by ITERATING the invoice's line items —
        # the form is line-driven, so per-line account + amount + tax
        # code + WHT code is the canonical source. Earlier revisions
        # used header-level ``invoice.account`` and ``invoice.subtotal``
        # which were always empty for line-driven entries, producing
        # an empty preview ("No entries to display") even when the
        # invoice clearly carried lines.
        lines: list = []
        warnings: list = []

        invoice_lines = list(invoice.lines.all().select_related('account', 'tax_code', 'withholding_tax'))

        # Optional GR/IR clearing override for PO-backed invoices
        gr_ir_account = None
        if has_po:
            gr_ir_code = default_gl.get('GOODS_RECEIPT_CLEARING', '20601000')
            gr_ir_account = Account.objects.filter(code=gr_ir_code).first()

        sum_lines = Decimal('0')
        sum_tax = Decimal('0')
        sum_wht = Decimal('0')

        for ln in invoice_lines:
            line_amt = Decimal(str(ln.amount or 0))
            if line_amt <= 0:
                continue
            sum_lines += line_amt

            # DR Expense / Asset / GL — line's own account.
            # PO-backed: route DR to GR/IR Clearing instead (3-way
            # match flow), keeping the line's own account in memo so
            # the preview still shows what was selected.
            dr_acc = gr_ir_account if (has_po and gr_ir_account) else ln.account
            if dr_acc:
                lines.append({
                    'account': dr_acc.pk,
                    'account_code': dr_acc.code,
                    'account_name': dr_acc.name,
                    'debit': str(line_amt.quantize(Decimal('0.01'))),
                    'credit': '0.00',
                    'memo': (
                        f'GR/IR Clearing ({ln.account.code})' if (has_po and gr_ir_account and ln.account)
                        else (ln.description or f'Line: {ln.account.code}' if ln.account else 'Line')
                    ),
                })
            else:
                warnings.append(
                    f'Line {invoice_lines.index(ln) + 1}: no GL account selected — '
                    'preview cannot show a debit row for this line.'
                )

            # DR Input VAT — pulled from the line's tax_code's
            # input_tax_account (or its tax_account fallback).
            tc = ln.tax_code
            if tc and tc.rate and Decimal(str(tc.rate)) > 0:
                tax_amt = (line_amt * Decimal(str(tc.rate)) / Decimal('100')).quantize(Decimal('0.01'))
                if tax_amt > 0:
                    sum_tax += tax_amt
                    tax_acc = (
                        getattr(tc, 'input_tax_account', None)
                        or getattr(tc, 'tax_account', None)
                    )
                    if tax_acc:
                        lines.append({
                            'account': tax_acc.pk,
                            'account_code': tax_acc.code,
                            'account_name': tax_acc.name,
                            'debit': str(tax_amt),
                            'credit': '0.00',
                            'memo': f'Input VAT @ {tc.rate}% ({tc.code})',
                        })
                    else:
                        warnings.append(
                            f'Tax code {tc.code} has no Input Tax / Tax account '
                            'configured — tax will land on the expense account on Post.'
                        )

            # WHT is DETERMINED at invoice but RECOGNISED at payment time
            # (Nigerian PFM cash-basis). The simulator therefore shows
            # NO WHT credit on the invoice journal — AP gets the full
            # gross. The WHT FK on the line is preserved for the PV
            # builder to read at payment time. ``sum_wht`` stays zero
            # so the AP credit below resolves to gross.

        # Fallback: no usable lines — fall back to header-level fields
        # (legacy invoices created before line-driven entry, or test
        # data). Mirrors the original simulator's heuristic.
        if not invoice_lines or sum_lines == 0:
            tax_amount = invoice.tax_amount or Decimal('0')
            header_total = invoice.total_amount or Decimal('0')
            header_subtotal = invoice.subtotal or (header_total - tax_amount)
            debit_account = invoice.account or (
                Account.objects.filter(code=default_gl.get('PURCHASE_EXPENSE', '50100000')).first()
            )
            if debit_account and header_subtotal > 0:
                lines.append({
                    'account': debit_account.pk,
                    'account_code': debit_account.code,
                    'account_name': debit_account.name,
                    'debit': str(header_subtotal.quantize(Decimal('0.01'))),
                    'credit': '0.00',
                    'memo': f'Expense: {invoice.reference or invoice.invoice_number}',
                })
                sum_lines = header_subtotal
                sum_tax = tax_amount
            elif not debit_account:
                warnings.append(
                    'No debit account on invoice header and no line items — '
                    'add a line with an account in the form, or set the header account.'
                )

        # CR AP — full gross (subtotal + VAT). WHT is recognised at
        # payment time on the PV journal, not here. Mirrors what
        # post_invoice() will book under cash-basis WHT.
        ap_amount = (sum_lines + sum_tax) if invoice_lines else (invoice.total_amount or Decimal('0'))
        if ap_account and ap_amount > 0:
            lines.append({
                'account': ap_account.pk,
                'account_code': ap_account.code,
                'account_name': ap_account.name,
                'debit': '0.00',
                'credit': str(ap_amount.quantize(Decimal('0.01'))),
                'memo': f'AP: {invoice.vendor.name if invoice.vendor else "vendor"}',
            })

        if not ap_account:
            warnings.append(
                'Accounts Payable not configured — flag a Liability account '
                "with reconciliation_type='accounts_payable' in Chart of Accounts."
            )

        total_debit = sum((Decimal(l['debit']) for l in lines), Decimal('0'))
        total_credit = sum((Decimal(l['credit']) for l in lines), Decimal('0'))

        return Response({
            'simulated': True,  # flag for UI so it can label the card "Proposed"
            'id': None,
            'reference_number': f'(proposed) VINV-{invoice.invoice_number}',
            'posting_date': invoice.invoice_date,
            'description': f'Vendor Invoice: {invoice.invoice_number}',
            'status': 'Draft',  # never actually written
            'total_debit': str(total_debit),
            'total_credit': str(total_credit),
            'balanced': total_debit == total_credit,
            'lines': lines,
            'warnings': warnings,
        })

    @action(detail=True, methods=['post'])
    def approve_invoice(self, request, pk=None):
        """Approve AP invoice — single-click: validates + posts to GL.

        Prior versions split approve (Draft → Approved) and post (Approved
        → Posted) into separate clicks, which caused users to end at the
        Approved state thinking they'd posted — the GL journal was never
        created and the appropriation's Expended column stayed at zero.

        The new behaviour is SAP-FB60-style: approve = fully post. The
        action runs:
          1. Appropriation validation (via BudgetValidationService)
          2. Warrant ceiling check (via check_warrant_availability)
          3. GL journal posting (DR Expense / CR AP + tax)
          4. Commitment closure if PO-backed
          5. Status flip Draft → Posted

        Callers that want only "Approved" without posting can still
        set status='Approved' via the generic PATCH endpoint.
        """
        invoice = self.get_object()
        if invoice.status not in ('Draft', 'Approved'):
            return Response(
                {"error": f"Only Draft or Approved invoices can be posted. Current: {invoice.status}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # If the invoice is still a Draft, promote to Approved so the
        # downstream post_invoice() sees the state it expects.
        if invoice.status == 'Draft':
            invoice.status = 'Approved'
            invoice.save(_allow_status_change=True)
            invoice.refresh_from_db()

        # Delegate to post_invoice — same validation + posting path the
        # separate endpoint uses. Returns the same structured response
        # shape (appropriation_exceeded / warrant_exceeded flags).
        return self.post_invoice(request, pk=pk)

    @action(detail=True, methods=['post'])
    def post_invoice(self, request, pk=None):
        """Post vendor invoice — validates budget, records obligation, creates GL journal.

        Like SAP FB60: budget check + posting happen together.
        - Validates appropriation exists for this MDA + account + fund
        - Records obligation (encumbrance) against the appropriation
        - Creates IPSAS journal: DR Expense/Asset, CR AP
        """
        invoice = self.get_object()

        if invoice.status == 'Posted':
            return Response({"error": "Invoice already posted."}, status=status.HTTP_400_BAD_REQUEST)

        # S1-06 — fiscal period gate. Reject up-front if the invoice_date
        # falls in a closed/locked period or no period at all. The service
        # layer also enforces this; the view-level check short-circuits
        # expensive budget validation when we already know posting will
        # fail, and gives the user a clear error.
        try:
            from accounting.services.base_posting import BasePostingService
            BasePostingService._validate_fiscal_period(invoice.invoice_date, user=request.user)
        except Exception as exc:
            return Response(
                {"error": str(exc), "period_closed": True},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # If the invoice was created by the multi-line form that only
        # captures line-level accounts, mirror the first line's account
        # up to the header. Downstream budget validation + the
        # Appropriation Report both key off invoice.account to figure out
        # which appropriation to charge — keep them in sync.
        if not invoice.account_id:
            first_line = invoice.lines.select_related('account').first() if hasattr(invoice, 'lines') else None
            if first_line and first_line.account_id:
                invoice.account = first_line.account
                invoice.save(_allow_status_change=True)
                invoice.refresh_from_db()

        # ── TOCTOU guard: lock candidate Appropriations before
        # validation runs.
        #
        # Previously ``validate_expenditure`` ran OUTSIDE any
        # transaction, so two concurrent posts could read the same
        # ``available_balance``, both pass the check, then both
        # proceed to the inner atomic and silently over-appropriate.
        #
        # The fix here: run a short ``transaction.atomic()`` that
        # acquires a row-level lock on every active appropriation
        # in the invoice's (MDA, Fund) tuple, runs the full budget
        # validation inside the lock, and only releases when this
        # method returns or commits. We achieve that by wrapping the
        # entire remainder of ``post_invoice`` in
        # ``transaction.atomic()`` via the helper below.
        return self._post_invoice_locked(request, invoice)

    def _post_invoice_locked(self, request, invoice):
        """Continuation of ``post_invoice`` running inside a single
        ``transaction.atomic()`` so ``select_for_update`` on the
        matched Appropriation rows is held across validation AND
        journal posting. Concurrent posts on the same appropriation
        are serialised on the row lock; posts on different
        appropriations stay parallel.
        """
        with transaction.atomic():
            if invoice.mda_id and invoice.fund_id:
                try:
                    from budget.models import Appropriation
                    from accounting.models.ncoa import (
                        AdministrativeSegment, FundSegment,
                    )
                    _admin_seg = AdministrativeSegment.objects.filter(
                        legacy_mda=invoice.mda,
                    ).first()
                    _fund_seg = FundSegment.objects.filter(
                        legacy_fund=invoice.fund,
                    ).first()
                    if _admin_seg and _fund_seg:
                        list(
                            Appropriation.objects
                            .select_for_update()
                            .filter(
                                administrative=_admin_seg,
                                fund=_fund_seg,
                                status__iexact='ACTIVE',
                            )
                        )
                except Exception:  # noqa: BLE001 — lock is best-effort
                    pass
            return self._post_invoice_body(request, invoice)

    def _post_invoice_body(self, request, invoice):
        """Original budget-validation + posting logic, factored out so
        ``_post_invoice_locked`` can wrap it in a single outer atomic.
        Behaviour is unchanged from the previous monolithic form."""
        # ── Budget Validation (Appropriation availability) ──────────
        # Like SAP FB60: budget check + posting happen together.
        #
        # We check per-line so that every charged GL account (e.g. capex
        # clearing 23040108) is validated against its own economic-segment
        # appropriation. Using only the header account would silently bypass
        # budget control for lines whose account differs from the header.
        #
        # When no invoice lines exist (header-only invoice), we fall back to
        # the header-level account + total amount (legacy path).
        #
        # Missing MDA / Fund is a HARD STOP — the invoice cannot post
        # because there's no budget dimension to validate against,
        # which means there's no appropriation gate. Previously this
        # silently skipped the check; we now refuse.
        if not invoice.mda_id or not invoice.fund_id:
            return Response(
                {
                    "error": (
                        "Cannot post: invoice is missing budget dimensions. "
                        "MDA and Fund are required so the appropriation "
                        "ceiling can be enforced. Edit the invoice to set "
                        "both before posting."
                    ),
                    "missing_dimensions": {
                        "mda": not invoice.mda_id,
                        "fund": not invoice.fund_id,
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        if invoice.mda and invoice.fund:
            try:
                from budget.services import BudgetValidationService, BudgetExceededError
                from accounting.models.ncoa import AdministrativeSegment, EconomicSegment, FundSegment
                from accounting.models.advanced import FiscalYear

                admin_seg = AdministrativeSegment.objects.filter(legacy_mda=invoice.mda).first()
                fund_seg  = FundSegment.objects.filter(legacy_fund=invoice.fund).first()
                active_fy = FiscalYear.objects.filter(is_active=True).first()

                if admin_seg and fund_seg and active_fy:
                    # Build a list of (account, amount) pairs to validate.
                    # Per-line takes priority — gives accurate per-GL-code control.
                    budget_lines = [
                        (ln.account, Decimal(str(ln.amount or 0)))
                        for ln in invoice.lines.select_related('account').all()
                        if ln.account_id and ln.amount and ln.amount > 0
                    ]
                    if not budget_lines and invoice.account and invoice.total_amount:
                        # Header-only fallback (legacy invoices without line items)
                        budget_lines = [(invoice.account, Decimal(str(invoice.total_amount)))]

                    for acct, line_amount in budget_lines:
                        econ_seg = EconomicSegment.objects.filter(legacy_account=acct).first()
                        if not econ_seg:
                            continue  # No NCoA mapping — skip (e.g. internal clearing accounts)
                        try:
                            BudgetValidationService.validate_expenditure(
                                administrative_id=admin_seg.pk,
                                economic_id=econ_seg.pk,
                                fund_id=fund_seg.pk,
                                fiscal_year_id=active_fy.pk,
                                amount=line_amount,
                                source='VENDOR_INVOICE',
                            )
                        except BudgetExceededError as e:
                            return Response({
                                "error": f"Appropriation exceeded for {acct.code} {acct.name}: {str(e)}",
                                "appropriation_exceeded": True,
                                "account_code": acct.code,
                            }, status=status.HTTP_400_BAD_REQUEST)
            except ImportError:
                pass  # Budget module not available — skip validation

        # ── Warrant Ceiling Check (Authority to Incur Expenditure) ──
        # Even when an appropriation exists, the verifier can only spend
        # up to what Treasury has actually warranted (released as cash
        # release authority). This is the second IPSAS budget-control
        # layer — must pass before AP can be recognised. For PO-backed
        # invoices the PO's commitment is excluded from the consumption
        # sum (otherwise we'd double-count).
        # Gated by ``is_warrant_pre_payment_enforced`` — under the
        # default ``WARRANT_ENFORCEMENT_STAGE='payment'`` setting the
        # invoice posts without warrant interrogation; the ceiling is
        # checked at payment time instead. Set the setting to
        # ``'invoice'`` to restore legacy strict behaviour.
        from accounting.budget_logic import (
            check_warrant_availability,
            is_warrant_pre_payment_enforced,
        )
        # Tenant-level kill switch: when the operator has bypassed
        # warrant enforcement entirely, skip the invoice-stage check too.
        # The system-wide ``is_warrant_pre_payment_enforced`` flag still
        # decides which pre-payment stages are gated by default; this
        # tenant flag is the master enable.
        try:
            from accounting.models.advanced import AccountingSettings
            _ap_settings = AccountingSettings.objects.first()
            _tenant_warrant_on = (
                bool(getattr(_ap_settings, 'require_warrant_before_payment', True))
                if _ap_settings is not None else True
            )
        except Exception:
            _tenant_warrant_on = True
        if (
            _tenant_warrant_on
            and is_warrant_pre_payment_enforced()
            and invoice.mda and invoice.account and invoice.fund
        ):
            allowed, msg, info = check_warrant_availability(
                dimensions={'mda': invoice.mda, 'fund': invoice.fund},
                account=invoice.account,
                amount=invoice.total_amount,
                exclude_po=invoice.purchase_order if invoice.purchase_order_id else None,
            )
            if not allowed:
                return Response({
                    "error": msg,
                    "warrant_exceeded": True,
                    "warrant_info": {
                        k: str(v) if hasattr(v, 'quantize') else v
                        for k, v in (info or {}).items()
                    },
                }, status=status.HTTP_400_BAD_REQUEST)

        try:
            from django.conf import settings as django_settings
            default_gl = getattr(django_settings, 'DEFAULT_GL_ACCOUNTS', {})

            with transaction.atomic():
                # ── Expense account discovery ───────────────────────
                # Discovery ladder, in order of trust:
                #   1. ``invoice.account`` — header-level expense account
                #      if the legacy form path set it.
                #   2. First non-null line account — the new line-driven
                #      form path stores the operator's choice on the
                #      lines, not the header. This is the right answer
                #      for the new tenant flow.
                #   3. Hardcoded ``DEFAULT_GL_ACCOUNTS['PURCHASE_EXPENSE']``
                #      (legacy fallback for tenants that mirror the
                #      build's chart codes).
                #   4. Name heuristic — last-resort match on
                #      ``account_type='Expense'`` + a Purchase-ish name.
                expense_account = invoice.account
                if not expense_account:
                    first_line_acc = invoice.lines.exclude(account__isnull=True).values_list('account', flat=True).first()
                    if first_line_acc:
                        expense_account = Account.objects.filter(pk=first_line_acc).first()
                if not expense_account:
                    exp_code = default_gl.get('PURCHASE_EXPENSE', '50100000')
                    expense_account = Account.objects.filter(code=exp_code).first()
                    if not expense_account:
                        expense_account = Account.objects.filter(account_type='Expense', name__icontains='Purchase').first()

                # ── AP account discovery ────────────────────────────
                # Discovery ladder:
                #   1. ``reconciliation_type='accounts_payable'`` — the
                #      tenant-portable CoA marker (works regardless of
                #      what code numbering scheme the tenant adopted).
                #   2. ``DEFAULT_GL_ACCOUNTS['ACCOUNTS_PAYABLE']`` code
                #      (legacy code-match fallback).
                #   3. ``Liability`` + name~"Payable" heuristic.
                # Falls through error only if all three miss — meaning
                # the tenant has not configured an AP control account
                # at all, in which case the operator must add one.
                ap_account = Account.objects.filter(
                    reconciliation_type='accounts_payable', is_active=True,
                ).first()
                if not ap_account:
                    ap_code = default_gl.get('ACCOUNTS_PAYABLE', '20100000')
                    ap_account = Account.objects.filter(code=ap_code).first()
                if not ap_account:
                    ap_account = Account.objects.filter(account_type='Liability', name__icontains='Payable').first()

                if not expense_account or not ap_account:
                    missing = []
                    if not expense_account:
                        missing.append('Expense (no line account, no PURCHASE_EXPENSE default, no Expense+Purchase match)')
                    if not ap_account:
                        missing.append('Accounts Payable (no account flagged reconciliation_type=accounts_payable, no ACCOUNTS_PAYABLE default, no Liability+Payable match)')
                    return Response(
                        {"error": "Required GL accounts not found: " + '; '.join(missing) + ". Configure a Liability account with reconciliation_type='accounts_payable' in Chart of Accounts, or add the corresponding code to DEFAULT_GL_ACCOUNTS in settings."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                amount = invoice.total_amount

                # Assign invoice document number first so the journal
                # can reference it without two trips through the DB.
                if not invoice.document_number:
                    invoice.document_number = TransactionSequence.get_next('vendor_invoice_doc', 'VINV-')

                # Create journal entry as Draft, populate it, then flip
                # to Posted at the very end. ImmutableModelMixin (see
                # JournalHeader) blocks ANY mutation once status='Posted',
                # including ``document_number`` and line additions — even
                # with ``_allow_status_change=True`` (that flag only
                # exempts the status field itself). Building the journal
                # in Draft, locking it Posted last, is the only safe
                # ordering. Reference number uses the bare invoice
                # number to avoid the legacy ``VINV-VINV-…`` double
                # prefix when invoice_number already starts with VINV-.
                ref_seed = invoice.invoice_number or invoice.document_number or ''
                journal_ref = ref_seed if ref_seed.startswith('VINV-') else f"VINV-{ref_seed}"
                # ``mda`` MUST propagate from invoice → journal. The
                # budget enforcement signal reads ``instance.mda`` to
                # call ``find_matching_appropriation``; if it's null
                # the lookup returns None and STRICT rules block the
                # post even when an appropriation legitimately covers
                # the line. Earlier code passed every dimension EXCEPT
                # mda, which is exactly the missing axis the
                # appropriation FK joins on (administrative__legacy_mda
                # = mda). Adding it here keeps the journal's
                # dimensional context complete and the budget check
                # consistent with the form's real-time pill.
                journal = JournalHeader.objects.create(
                    reference_number=journal_ref,
                    description=f"Vendor Invoice: {invoice.invoice_number}",
                    posting_date=invoice.invoice_date,
                    mda=invoice.mda,
                    fund=invoice.fund,
                    function=invoice.function,
                    program=invoice.program,
                    geo=invoice.geo,
                    document_number=TransactionSequence.get_next('journal_voucher', 'JV-'),
                    status='Draft',
                )

                # PF-6: Split expense and tax into separate lines.
                #
                # Money convention (matches the form payload, IPSAS,
                # and the appropriation roll-up):
                #   subtotal     = expense recognised (line gross, ex-VAT)
                #   tax_amount   = input VAT (debit to Input VAT GL)
                #   total_amount = subtotal + tax_amount  (vendor gross)
                #   WHT          = computed at posting from line codes;
                #                  CR WHT Payable + reduce CR AP
                #
                # Earlier code derived expense as ``amount - tax_amount``,
                # which produced a wrong number when ``total_amount``
                # was set to grandTotal (= subtotal + tax - wht). That
                # made the appropriation's expended column understate
                # the actual expense by the WHT amount. Booking
                # ``DR Expense = subtotal`` directly is unambiguous
                # and makes the appropriation report the recognised
                # expense (not the cash-out amount).
                # ── Per-line DR entries ───────────────────────────────────────
                # Iterate invoice lines so each line's own GL account lands in
                # the journal. This is required for SAP-style asset
                # auto-capitalisation: capex GLs flagged auto_create_asset=True
                # must appear as JournalLines so apply_asset_capitalization can
                # detect them and add the clearing contra + asset recon pair.
                # Fallback to the header-level expense_account for invoices that
                # were created without explicit line items (legacy path).
                invoice_lines = list(
                    invoice.lines.all()
                    .select_related('account', 'tax_code', 'withholding_tax')
                )
                input_vat_by_account: dict = {}
                wht_by_account: dict = {}
                line_computed_vat = Decimal('0.00')
                line_computed_wht = Decimal('0.00')

                if invoice_lines:
                    for inv_line in invoice_lines:
                        line_amt = Decimal(str(inv_line.amount or 0))
                        if line_amt <= 0 or not inv_line.account:
                            continue
                        # Per-line Input VAT — compute first so we know
                        # whether to gross-up the expense debit when
                        # the tenant has no Input VAT recoverable
                        # account configured. Without this gross-up the
                        # AP credit (which is always the gross) would
                        # exceed the expense debit by the VAT amount,
                        # producing an unbalanced journal — see the
                        # historical VINV-202604-0004/0005/0006 in
                        # office_of_accountant_general_delta_state for
                        # an exact illustration of the bug.
                        line_dr = line_amt
                        tc = inv_line.tax_code
                        if tc and tc.rate and Decimal(str(tc.rate)) > 0:
                            vat_amt = (
                                line_amt * Decimal(str(tc.rate)) / Decimal('100')
                            ).quantize(Decimal('0.01'))
                            if vat_amt > 0:
                                vat_acct = (
                                    getattr(tc, 'input_tax_account', None)
                                    or getattr(tc, 'tax_account', None)
                                )
                                if vat_acct:
                                    # VAT is recoverable — DR a separate
                                    # Input VAT GL below.
                                    prev = input_vat_by_account.get(vat_acct.id, (vat_acct, Decimal('0.00')))
                                    input_vat_by_account[vat_acct.id] = (vat_acct, prev[1] + vat_amt)
                                    line_computed_vat += vat_amt
                                else:
                                    # VAT not recoverable for this tenant
                                    # — fold it into the expense line so
                                    # the journal still balances. Common
                                    # for Nigerian state government
                                    # entities that aren't VAT-registered.
                                    line_dr = line_amt + vat_amt
                                    line_computed_vat += vat_amt
                        JournalLine.objects.create(
                            header=journal,
                            account=inv_line.account,
                            debit=line_dr,
                            credit=Decimal('0.00'),
                            memo=(
                                inv_line.description
                                or inv_line.account.name
                                or f"Vendor invoice {invoice.invoice_number}"
                            )[:255],
                            document_number=journal.document_number,
                        )
                        # WHT is DETERMINED at invoice verification but
                        # RECOGNISED at payment time (Nigerian PFM cash-
                        # basis). The line's withholding_tax FK is left
                        # intact for the PV builder to read; no WHT
                        # journal line is written here. AP is credited
                        # at the full gross. ``line_computed_wht`` stays
                        # 0 so the AP credit below resolves to gross.
                        pass
                else:
                    # Fallback: header-only invoice (no line items)
                    tax_amount = getattr(invoice, 'tax_amount', None) or Decimal('0.00')
                    expense_amount = getattr(invoice, 'subtotal', None) or (amount - tax_amount)
                    # Resolve a recoverable Input VAT account if one
                    # exists in the CoA. If none, gross-up the expense
                    # so the journal still balances (VAT becomes part
                    # of expense — correct for non-VAT-registered
                    # entities).
                    tax_account = None
                    if tax_amount > 0:
                        tax_account = (
                            Account.objects.filter(
                                account_type='Asset', name__icontains='Input Tax',
                            ).first()
                            or Account.objects.filter(name__icontains='VAT Receivable').first()
                        )
                        if tax_account:
                            input_vat_by_account[-1] = (tax_account, tax_amount)
                            line_computed_vat = tax_amount
                        else:
                            # Roll VAT into the expense line.
                            expense_amount = (expense_amount or Decimal('0.00')) + tax_amount
                            line_computed_vat = tax_amount
                    if expense_amount > 0 and expense_account:
                        JournalLine.objects.create(
                            header=journal,
                            account=expense_account,
                            debit=expense_amount,
                            credit=Decimal('0.00'),
                            memo=f"Vendor invoice {invoice.invoice_number}",
                            document_number=journal.document_number,
                        )

                # DR Input VAT (one row per input_tax_account)
                for _, (vat_acct, vat_amt) in input_vat_by_account.items():
                    if vat_amt > 0:
                        JournalLine.objects.create(
                            header=journal,
                            account=vat_acct,
                            debit=vat_amt,
                            credit=Decimal('0.00'),
                            memo=f"Input VAT — {invoice.invoice_number}",
                            document_number=journal.document_number,
                        )

                # WHT is no longer credited at invoice posting — it's
                # deferred to payment time per Nigerian PFM cash-basis.
                # AP credit below is the full gross (subtotal + VAT).

                # CR AP — full gross. WHT will be deducted on the PV
                # journal at payment time (see treasury_revenue
                # ._post_payment_journal which credits each
                # PaymentVoucherDeduction.gl_account).
                ap_credit = invoice.total_amount or Decimal('0.00')
                JournalLine.objects.create(
                    header=journal,
                    account=ap_account,
                    debit=Decimal('0.00'),
                    credit=ap_credit,
                    memo=f"AP: {invoice.vendor.name if invoice.vendor else 'vendor'}",
                    document_number=journal.document_number,
                )

                # SAP-style asset auto-capitalisation + journal balance check.
                # _validate_journal_balanced calls apply_asset_capitalization
                # which adds CR clearing (23040108) + DR asset recon for any
                # debit line whose account has auto_create_asset=True, then
                # verifies DR total == CR total. Must run BEFORE
                # update_gl_from_journal so the contra/recon lines are
                # included in the GL balance roll-up.
                from accounting.services.base_posting import BasePostingService
                BasePostingService._validate_journal_balanced(journal)

                # Update GL balances — includes auto-cap lines added above.
                from accounting.services import update_gl_from_journal
                update_gl_from_journal(journal, fund=invoice.fund, function=invoice.function,
                                       program=invoice.program, geo=invoice.geo)

                # Lock the journal — flip Draft → Posted. ImmutableModelMixin
                # blocks further mutations once Posted, so this is the last
                # write to journal in this transaction.
                journal.status = 'Posted'
                journal.save(update_fields=['status'], _allow_status_change=True)

                # Link the journal back to the invoice so the AP View modal
                # (and any other journal-drill-down reports) can traverse
                # VendorInvoice.journal_entry to find the GL entries. Without
                # this, the "GL Journal Posted" card never appears on Posted
                # invoices and audit reports show orphan journals.
                invoice.journal_entry = journal
                invoice.status = 'Posted'
                invoice.save(_allow_status_change=True)

                # Subledger sync — increment the vendor's outstanding
                # AP balance by the gross invoice amount. Atomic F()
                # update so concurrent invoice postings on the same
                # vendor don't lose increments. Mirrors the F()-based
                # decrement in ``post_payment`` (line ~1682), so the
                # subledger nets correctly across the lifecycle.
                if invoice.vendor_id:
                    from django.db.models import F
                    type(invoice.vendor).objects.filter(pk=invoice.vendor_id).update(
                        balance=F('balance') + (invoice.total_amount or Decimal('0'))
                    )

                # IPSAS commitment lifecycle: VI Posted → close the
                # ProcurementBudgetLink (INVOICED → CLOSED). The commitment
                # falls out of Appropriation.total_committed so the
                # encumbered balance shrinks; the actual expense is now
                # captured by the JournalLine debits booked above.
                #
                # NOTE: the legacy BudgetEncumbrance update that lived here
                # was removed — it referenced a non-existent
                # `reference_number` field and a non-existent `Liquidated`
                # status, silently swallowed by the bare `except Exception`
                # below. The ProcurementBudgetLink path is the canonical
                # commitment-tracking system in this codebase.
                if hasattr(invoice, 'purchase_order') and invoice.purchase_order:
                    try:
                        from accounting.services.procurement_commitments import (
                            mark_commitment_closed_for_po,
                            refresh_appropriations_for_po,
                        )
                        closed_count = mark_commitment_closed_for_po(invoice.purchase_order)
                        if closed_count == 0:
                            import logging
                            logging.getLogger(__name__).info(
                                "VI %s: no open ProcurementBudgetLink for PO %s "
                                "(commitment may have been closed already, or "
                                "the PO was raised before the commitment-link "
                                "feature was enabled).",
                                invoice.invoice_number,
                                invoice.purchase_order.po_number,
                            )
                        # Belt-and-braces: guarantee Appropriation cache
                        # reflects the recognised expenditure regardless of
                        # whether ProcurementBudgetLink existed.
                        refresh_appropriations_for_po(invoice.purchase_order)
                    except Exception as exc:
                        import logging
                        logging.getLogger(__name__).warning(
                            "VI %s: commitment CLOSED flip failed (non-fatal): %s",
                            invoice.invoice_number, exc,
                        )

                # ── Record obligation (encumbrance) for direct invoices (no PO) ──
                # For direct invoices (no PO upstream) the encumbrance is the
                # invoice itself — there's nothing to liquidate later because
                # the expense is already in the GL. The legacy
                # BudgetEncumbrance.objects.create() call here was removed
                # because it passed `reference_number`, `account`, `mda` and
                # a 'Liquidated' status — none of which exist on the
                # BudgetEncumbrance model. The actual budget consumption was
                # validated above (BudgetValidationService.validate_expenditure)
                # and the GL journal we just posted captures the spend.
                if not invoice.purchase_order:
                    pass  # No commitment record needed for direct invoices.

            return Response({
                "status": "Invoice posted to GL successfully.",
                "journal_id": journal.id,
                "invoice_id": invoice.id,
                "amount": str(amount)
            })
        except Exception as e:
            from accounting.services.posting_errors import format_post_error
            return Response(
                format_post_error(e, context='AP invoice'),
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=True, methods=['post'])
    def post_credit_memo(self, request, pk=None):
        """Post credit memo — Dr AP (reduce payable), Cr Expense (reduce expense).

        Credit memo REVERSES a budget obligation:
        - Reduces the expended amount on the appropriation
        - Creates a negative encumbrance record (obligation reversal)

        SoD: Requires manager/admin role — users who create invoices
        cannot create credit memos to prevent budget abuse.
        """
        invoice = self.get_object()

        if invoice.document_type != 'Credit Memo':
            return Response({"error": "This document is not a credit memo."}, status=status.HTTP_400_BAD_REQUEST)

        if invoice.status == 'Posted':
            return Response({"error": "Credit memo already posted."}, status=status.HTTP_400_BAD_REQUEST)

        # PV-link lock: don't let a credit memo reverse an invoice
        # whose PV is still live. The PV must be cancelled first so
        # the cash-control trail stays intact.
        pv = self._linked_active_pv(invoice)
        if pv is not None:
            return Response(
                {
                    'error': (
                        f'Cannot post this credit memo: a Payment Voucher '
                        f'({pv.voucher_number}, status {pv.status}) has '
                        f'been raised against the original invoice. '
                        f'Cancel or reverse the PV first.'
                    ),
                    'pv_link_locked': True,
                    'payment_voucher_number': pv.voucher_number,
                    'payment_voucher_status': pv.status,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # S1-06 — fiscal period gate.
        try:
            from accounting.services.base_posting import BasePostingService
            BasePostingService._validate_fiscal_period(invoice.invoice_date, user=request.user)
        except Exception as exc:
            return Response(
                {"error": str(exc), "period_closed": True},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # SoD enforcement: credit memo requires elevated role.
        #
        # Fail-CLOSED: any unexpected error reading the role row blocks
        # the credit memo. The previous fail-open behaviour meant that
        # if django_tenants schema-context resolution failed for any
        # reason, a user-role account could post credit memos and
        # reverse AP obligations without segregation of duties.
        from django_tenants.utils import schema_context
        import logging as _logging
        _log_sod = _logging.getLogger(__name__)
        try:
            with schema_context('public'):
                from tenants.models import UserTenantRole
                user_role = UserTenantRole.objects.filter(
                    user=request.user, tenant=request.tenant,
                ).first()
        except Exception as exc:  # noqa: BLE001 — fail closed
            _log_sod.error(
                "Credit-memo SoD check failed for user %s: %s",
                getattr(request.user, 'pk', '?'), exc,
            )
            return Response(
                {"error": (
                    "Could not verify credit-memo authorisation. "
                    "Contact your administrator to check role assignment."
                )},
                status=status.HTTP_403_FORBIDDEN,
            )

        if user_role is None:
            return Response(
                {"error": (
                    "No tenant role assigned. Credit Memo posting "
                    "requires Manager or Admin role."
                )},
                status=status.HTTP_403_FORBIDDEN,
            )
        if user_role.role in ('user', 'viewer'):
            return Response(
                {"error": "Separation of Duties: Credit Memo posting requires Manager or Admin role. "
                          "Users who create vendor invoices cannot post credit memos."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            from django.conf import settings as django_settings
            default_gl = getattr(django_settings, 'DEFAULT_GL_ACCOUNTS', {})

            with transaction.atomic():
                # AP discovery — see post_invoice() docstring for the
                # full ladder. Same logic here so credit-memo posting
                # works on any tenant CoA without legacy code numbering.
                ap_account = Account.objects.filter(
                    reconciliation_type='accounts_payable', is_active=True,
                ).first()
                if not ap_account:
                    ap_code = default_gl.get('ACCOUNTS_PAYABLE', '20100000')
                    ap_account = Account.objects.filter(code=ap_code).first()
                if not ap_account:
                    ap_account = Account.objects.filter(
                        account_type='Liability', name__icontains='Payable'
                    ).first()

                # Expense discovery — same ladder as post_invoice.
                expense_account = invoice.account
                if not expense_account and invoice.lines.exists():
                    expense_account = invoice.lines.first().account
                if not expense_account:
                    exp_code = default_gl.get('PURCHASE_EXPENSE', '50100000')
                    expense_account = Account.objects.filter(code=exp_code).first()
                    if not expense_account:
                        expense_account = Account.objects.filter(
                            account_type='Expense', name__icontains='Purchase'
                        ).first()

                if not ap_account or not expense_account:
                    missing = []
                    if not ap_account:
                        missing.append('Accounts Payable (set reconciliation_type=accounts_payable on a Liability account)')
                    if not expense_account:
                        missing.append('Expense (set on the credit memo line)')
                    return Response(
                        {"error": "Required GL accounts not found: " + '; '.join(missing) + "."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                amount = invoice.total_amount

                # Assign invoice document number first.
                if not invoice.document_number:
                    invoice.document_number = TransactionSequence.get_next('credit_memo_doc', 'CM-')

                # Build the journal as Draft, lock to Posted at the end
                # — same Posted-immutability constraint as post_invoice.
                cm_seed = invoice.invoice_number or invoice.document_number or ''
                cm_ref = cm_seed if cm_seed.startswith('CM-') else f"CM-{cm_seed}"
                # ``mda`` propagated for budget-enforcement signal
                # consistency — see post_invoice rationale.
                journal = JournalHeader.objects.create(
                    reference_number=cm_ref,
                    description=f"Credit Memo: {invoice.invoice_number} — {invoice.vendor.name if invoice.vendor else ''}",
                    posting_date=invoice.invoice_date,
                    mda=invoice.mda,
                    fund=invoice.fund,
                    function=invoice.function,
                    program=invoice.program,
                    geo=invoice.geo,
                    document_number=TransactionSequence.get_next('journal_voucher', 'JV-'),
                    status='Draft',
                )

                # Dr AP — reduces the accounts payable liability
                JournalLine.objects.create(
                    header=journal,
                    account=ap_account,
                    debit=amount,
                    credit=Decimal('0.00'),
                    memo=f"CM AP: {invoice.vendor.name if invoice.vendor else 'vendor'}",
                    document_number=journal.document_number,
                )

                # Cr Expense — reduces the expense (reversing the original charge)
                JournalLine.objects.create(
                    header=journal,
                    account=expense_account,
                    debit=Decimal('0.00'),
                    credit=amount,
                    memo=f"Credit Memo: {invoice.invoice_number}",
                    document_number=journal.document_number,
                )

                # Balance check (also triggers auto-cap if a capex GL was debited)
                from accounting.services.base_posting import BasePostingService
                BasePostingService._validate_journal_balanced(journal)

                # Update GL balances
                from accounting.services import update_gl_from_journal
                update_gl_from_journal(
                    journal,
                    fund=invoice.fund,
                    function=invoice.function,
                    program=invoice.program,
                    geo=invoice.geo,
                )

                # Lock journal — must be the last write to it.
                journal.status = 'Posted'
                journal.save(update_fields=['status'], _allow_status_change=True)

                invoice.status = 'Posted'
                invoice.save(_allow_status_change=True)

                # Subledger sync — credit memo REDUCES vendor AP. Atomic
                # F()-update mirrors the increment on regular invoice
                # posting so the vendor's outstanding balance nets
                # correctly across the lifecycle.
                if invoice.vendor_id:
                    from django.db.models import F
                    type(invoice.vendor).objects.filter(pk=invoice.vendor_id).update(
                        balance=F('balance') - (invoice.total_amount or Decimal('0'))
                    )

                # ── Record obligation REVERSAL for credit memo ──────
                # Credit memo releases budget — creates a negative encumbrance
                try:
                    BudgetEncumbrance.objects.create(
                        reference_number=f"CM-{invoice.invoice_number}",
                        reference_type='CREDIT_MEMO',
                        amount=-invoice.total_amount,  # negative = releases budget
                        liquidated_amount=-invoice.total_amount,
                        status='Liquidated',
                        account=invoice.account,
                        mda=invoice.mda,
                    )
                except Exception:
                    pass  # Non-critical

            return Response({
                "status": "Credit memo posted to GL successfully. Budget obligation reversed.",
                "journal_id": journal.id,
                "invoice_id": invoice.id,
                "amount": str(amount),
            })
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'])
    def aging_report(self, request):
        """Get accounts payable aging report"""
        from django.utils import timezone

        as_of_date = request.query_params.get('as_of_date')
        if as_of_date:
            from datetime import datetime
            as_of_date = datetime.strptime(as_of_date, '%Y-%m-%d').date()
        else:
            as_of_date = timezone.now().date()

        invoices = VendorInvoice.objects.filter(
            status__in=['Approved', 'Partially Paid'],
            invoice_date__lte=as_of_date
        ).select_related('vendor')

        aging_data = {}
        for invoice in invoices:
            vendor_id = invoice.vendor.id
            if vendor_id not in aging_data:
                aging_data[vendor_id] = {
                    'vendor_id': vendor_id,
                    'vendor_name': invoice.vendor.name,
                    'current': Decimal('0'),
                    'days_1_30': Decimal('0'),
                    'days_31_60': Decimal('0'),
                    'days_61_90': Decimal('0'),
                    'days_91_plus': Decimal('0'),
                    'total_due': Decimal('0')
                }

            balance = invoice.balance_due
            days_overdue = (as_of_date - invoice.due_date).days

            if days_overdue <= 0:
                aging_data[vendor_id]['current'] += balance
            elif days_overdue <= 30:
                aging_data[vendor_id]['days_1_30'] += balance
            elif days_overdue <= 60:
                aging_data[vendor_id]['days_31_60'] += balance
            elif days_overdue <= 90:
                aging_data[vendor_id]['days_61_90'] += balance
            else:
                aging_data[vendor_id]['days_91_plus'] += balance

            aging_data[vendor_id]['total_due'] += balance

        total_current = sum(d['current'] for d in aging_data.values())
        total_1_30 = sum(d['days_1_30'] for d in aging_data.values())
        total_31_60 = sum(d['days_31_60'] for d in aging_data.values())
        total_61_90 = sum(d['days_61_90'] for d in aging_data.values())
        total_91_plus = sum(d['days_91_plus'] for d in aging_data.values())

        return Response({
            'as_of_date': as_of_date,
            'vendors': list(aging_data.values()),
            'summary': {
                'current': float(total_current),
                'days_1_30': float(total_1_30),
                'days_31_60': float(total_31_60),
                'days_61_90': float(total_61_90),
                'days_91_plus': float(total_91_plus),
                'total_due': float(total_current + total_1_30 + total_31_60 + total_61_90 + total_91_plus)
            }
        })


class PaymentViewSet(OrganizationFilterMixin, viewsets.ModelViewSet):
    # Tenant MDA-isolation: the Payment doesn't carry an MDA directly,
    # so we filter through ``allocations__invoice__mda``. In UNIFIED
    # mode every payment is visible; in SEPARATED mode the operator
    # sees only payments whose allocations touch their own MDA's
    # invoices. ``.distinct()`` prevents duplicate rows when a
    # payment's allocations span multiple invoices.
    org_filter_field = 'allocations__invoice__mda'

    queryset = Payment.objects.all().select_related(
        'vendor', 'bank_account', 'currency', 'journal_entry'
    ).prefetch_related('allocations').distinct()
    serializer_class = PaymentSerializer
    filterset_fields = ['status', 'payment_date', 'payment_method', 'is_advance', 'vendor']

    def get_permissions(self):
        # S7-01 — MFA-gate cash disbursement.
        from accounting.permissions import RequiresMFA
        if self.action == 'post_payment':
            return [IsApprover('post'), RequiresMFA()]
        return super().get_permissions()

    def perform_destroy(self, instance):
        if instance.status != 'Draft':
            from rest_framework.exceptions import ValidationError
            raise ValidationError("Only draft payments can be deleted.")
        super().perform_destroy(instance)

    @action(detail=True, methods=['post'])
    def post_payment(self, request, pk=None):
        """Post payment — creates journal entry + updates GL balances + vendor balance."""
        payment = self.get_object()
        if payment.status == 'Posted':
            return Response({"error": "Payment already posted."}, status=status.HTTP_400_BAD_REQUEST)

        if not payment.allocations.exists():
            return Response({"error": "Payment has no allocations."}, status=status.HTTP_400_BAD_REQUEST)

        # S1-06 — fiscal period gate on the payment_date.
        try:
            from accounting.services.base_posting import BasePostingService
            BasePostingService._validate_fiscal_period(payment.payment_date, user=request.user)
        except Exception as exc:
            return Response(
                {"error": str(exc), "period_closed": True},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Payment-stage warrant gate. The default behaviour is
        # GIFMIS-compliant — cash cannot leave the consolidated
        # account beyond released warrants — but a per-tenant toggle
        # (``AccountingSettings.require_warrant_before_payment``) can
        # bypass it for jurisdictions / sub-tenants that don't yet
        # operate on warrant-based cash control. The toggle defaults
        # to True; flipping it OFF is an explicit, audited decision
        # the operator makes via Accounting Settings.
        try:
            from accounting.models.advanced import AccountingSettings
            _settings = AccountingSettings.objects.first()
            _enforce_warrant = (
                bool(getattr(_settings, 'require_warrant_before_payment', True))
                if _settings is not None else True
            )
        except Exception:
            # Fail closed: if the settings row is unreadable we still
            # enforce the warrant ceiling — the safer default.
            _enforce_warrant = True

        from accounting.budget_logic import check_warrant_availability
        from collections import defaultdict
        buckets: dict = defaultdict(lambda: {'amount': Decimal('0'), 'mda': None, 'fund': None, 'account': None})
        for alloc in payment.allocations.select_related('invoice').all():
            inv = alloc.invoice
            if not inv or not inv.mda or not inv.fund:
                continue
            key = (inv.mda_id, inv.fund_id, getattr(inv, 'account_id', None))
            b = buckets[key]
            b['amount'] += alloc.amount or Decimal('0')
            b['mda'] = inv.mda
            b['fund'] = inv.fund
            b['account'] = getattr(inv, 'account', None)
        if _enforce_warrant:
            for b in buckets.values():
                if b['amount'] == 0:
                    continue
                allowed, warrant_msg, info = check_warrant_availability(
                    dimensions={'mda': b['mda'], 'fund': b['fund']},
                    account=b['account'],
                    amount=b['amount'],
                )
                if not allowed:
                    # Distinguish two failure modes for a clearer
                    # operator-facing message:
                    #   1. No warrant has been released at all for this
                    #      expense line (warrants_released == 0)
                    #   2. Warrant exists but the amount being paid
                    #      would push consumption past the released
                    #      ceiling
                    # The frontend reads ``warrant_no_warrant`` /
                    # ``warrant_exceeded`` flags to render the
                    # appropriate CTA (release warrant vs. issue
                    # additional warrant).
                    warrants_released = info.get('warrants_released') or Decimal('0')
                    appro_label = info.get('appropriation_label', '')
                    if warrants_released == 0:
                        clean_msg = (
                            f"No Warrant (AIE) has been released for "
                            f"{appro_label or 'this expense line'}. "
                            f"Release a Warrant for this appropriation "
                            f"before posting the payment."
                        )
                        return Response(
                            {
                                "error": clean_msg,
                                "warrant_no_warrant": True,
                                "warrant_exceeded": False,
                                "info": info,
                            },
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                    return Response(
                        {
                            "error": f"Warrant limit exceeded: {warrant_msg}",
                            "warrant_exceeded": True,
                            "warrant_no_warrant": False,
                            "info": info,
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

        # Validate allocations sum equals payment total
        allocation_sum = payment.allocations.aggregate(total=Sum('amount'))['total'] or Decimal('0')
        if allocation_sum != payment.total_amount:
            return Response(
                {"error": f"Allocation total ({allocation_sum}) does not match payment amount ({payment.total_amount})."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # P2P-C4: Matched Status Validation — ensure invoices are matched before payment
        for allocation in payment.allocations.select_related('invoice').all():
            invoice = allocation.invoice
            if invoice:
                matching = None
                try:
                    from procurement.models import InvoiceMatching
                    matching = InvoiceMatching.objects.filter(vendor_invoice=invoice).first()
                    if not matching:
                        matching = InvoiceMatching.objects.filter(
                            invoice_reference=invoice.invoice_number
                        ).first()
                except ImportError as exc:
                    logger.warning(
                        "payables: InvoiceMatching model unavailable; "
                        "skipping match-status check for invoice %s: %s",
                        invoice.invoice_number, exc,
                    )

                if matching and matching.status != 'Matched':
                    return Response({
                        "error": f"Invoice {invoice.invoice_number} is not matched. Matching status: {matching.status}",
                        "invoice": invoice.invoice_number
                    }, status=status.HTTP_400_BAD_REQUEST)

        # P2P-C1: Payment Hold Validation — check payment_hold flag
        for allocation in payment.allocations.select_related('invoice').all():
            invoice = allocation.invoice
            if invoice:
                matching = None
                try:
                    from procurement.models import InvoiceMatching
                    matching = InvoiceMatching.objects.filter(vendor_invoice=invoice).first()
                    if not matching:
                        matching = InvoiceMatching.objects.filter(
                            invoice_reference=invoice.invoice_number
                        ).first()
                except ImportError as exc:
                    logger.warning(
                        "payables: InvoiceMatching model unavailable; "
                        "skipping payment-hold check for invoice %s: %s",
                        invoice.invoice_number, exc,
                    )

                if matching and matching.payment_hold:
                    return Response({
                        "error": f"Payment blocked: Invoice {invoice.invoice_number} has payment hold. Clear hold before processing payment.",
                        "invoice": invoice.invoice_number
                    }, status=status.HTTP_400_BAD_REQUEST)

        try:
            from django.conf import settings as django_settings
            default_gl = getattr(django_settings, 'DEFAULT_GL_ACCOUNTS', {})

            with transaction.atomic():
                # AP discovery — reconciliation_type marker first, then
                # legacy code default, then name heuristic.
                ap_account = Account.objects.filter(
                    reconciliation_type='accounts_payable', is_active=True,
                ).first()
                if not ap_account:
                    ap_code = default_gl.get('ACCOUNTS_PAYABLE', '20100000')
                    ap_account = Account.objects.filter(code=ap_code).first()
                if not ap_account:
                    ap_account = Account.objects.filter(account_type='Liability', name__icontains='Payable').first()

                # Bank/cash GL — prefer the bank_account's configured
                # GL, then the bank_accounting reconciliation marker,
                # then the legacy CASH_ACCOUNT code, then a name match.
                bank_gl_account = None
                if payment.bank_account:
                    bank_gl_account = payment.bank_account.gl_account
                if not bank_gl_account:
                    bank_gl_account = Account.objects.filter(
                        reconciliation_type='bank_accounting', is_active=True,
                    ).first()
                if not bank_gl_account:
                    cash_code = default_gl.get('CASH_ACCOUNT', '10100000')
                    bank_gl_account = Account.objects.filter(code=cash_code).first()
                    if not bank_gl_account:
                        bank_gl_account = Account.objects.filter(account_type='Asset', name__icontains='Bank').first()

                if not ap_account or not bank_gl_account:
                    missing = []
                    if not ap_account:
                        missing.append('Accounts Payable (flag a Liability account with reconciliation_type=accounts_payable)')
                    if not bank_gl_account:
                        missing.append('Bank/Cash (set gl_account on the payment\'s bank account, or flag an Asset with reconciliation_type=bank_accounting)')
                    return Response(
                        {"error": "Required GL accounts not found: " + '; '.join(missing) + "."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                amount = payment.total_amount

                # PF-15: Copy fund/function/program/geo dimensions from the
                # related invoice journal lines so payment journals carry
                # the same dimension coding as their source invoices.
                first_invoice = payment.allocations.select_related('invoice').first()
                inv = first_invoice.invoice if first_invoice else None

                # Assign payment document number first.
                if not payment.document_number:
                    payment.document_number = TransactionSequence.get_next('payment_doc', 'PAY-')

                # Build the journal as Draft, lock to Posted at the end
                # — same Posted-immutability constraint as post_invoice.
                pay_seed = payment.payment_number or payment.document_number or ''
                pay_ref = pay_seed if pay_seed.startswith('PAY-') else f"PAY-{pay_seed}"
                # ``mda`` propagated from source invoice for budget-
                # enforcement signal consistency — see post_invoice
                # rationale. Without this, the payment journal triggers
                # the same false STRICT block at signal time.
                journal = JournalHeader.objects.create(
                    reference_number=pay_ref,
                    description=f"Payment: {payment.payment_number}",
                    posting_date=payment.payment_date,
                    document_number=TransactionSequence.get_next('journal_voucher', 'JV-'),
                    status='Draft',
                    mda=getattr(inv, 'mda', None),
                    fund=getattr(inv, 'fund', None),
                    function=getattr(inv, 'function', None),
                    program=getattr(inv, 'program', None),
                    geo=getattr(inv, 'geo', None),
                )

                # Debit AP (reduce liability)
                JournalLine.objects.create(
                    header=journal,
                    account=ap_account,
                    debit=amount,
                    credit=Decimal('0.00'),
                    memo=f"Payment to {payment.vendor.name if payment.vendor else 'vendor'}",
                    document_number=journal.document_number,
                )

                # Credit Bank (reduce asset)
                JournalLine.objects.create(
                    header=journal,
                    account=bank_gl_account,
                    debit=Decimal('0.00'),
                    credit=amount,
                    memo=f"Bank payment {payment.payment_number}",
                    document_number=journal.document_number,
                )

                # Update GL balances
                self._update_gl_from_journal(journal)

                # Lock journal — must be the last write to it.
                journal.status = 'Posted'
                journal.save(update_fields=['status'], _allow_status_change=True)

                # ── H9 fix: keep BankAccount.current_balance live ────
                # The GL is correct via _update_gl_from_journal above,
                # but BankAccountViewSet.summary and the bank-rec
                # ``book_balance`` read from BankAccount.current_balance
                # — that field was previously stale the moment any
                # AP payment posted (only TSA paths via
                # TSABalanceService.process_payment kept it in sync).
                # F()-decrement under the same atomic so two concurrent
                # payments can't lose-update the bank balance.
                if payment.bank_account_id:
                    from accounting.models.banking import BankAccount as _BankAccount
                    _BankAccount.objects.filter(
                        pk=payment.bank_account_id,
                    ).update(
                        current_balance=F('current_balance') - amount,
                        updated_at=timezone.now(),
                    )

                # Link journal to payment and update status
                payment.journal_entry = journal
                payment.status = 'Posted'
                payment.save(_allow_status_change=True)

                # Update invoice paid amounts.
                #
                # Race-safe pattern: lock the invoice row, atomic
                # F() update of paid_amount, then re-read to compute
                # the new status. Previously this was a read-modify-
                # write (``invoice.paid_amount += allocation.amount``
                # in Python) — two concurrent payment posts against
                # the same invoice would both read the same starting
                # value and the second save would silently drop the
                # first increment, corrupting the AP subledger.
                from accounting.models.receivables import VendorInvoice
                for allocation in payment.allocations.select_related('invoice').all():
                    inv_pk = allocation.invoice_id
                    # Acquire row lock.
                    locked = VendorInvoice.objects.select_for_update().get(pk=inv_pk)
                    # Atomic increment via F().
                    VendorInvoice.objects.filter(pk=inv_pk).update(
                        paid_amount=F('paid_amount') + allocation.amount,
                    )
                    # Re-read post-increment to settle status field.
                    locked.refresh_from_db(fields=['paid_amount', 'total_amount'])
                    new_status = (
                        'Paid' if locked.paid_amount >= locked.total_amount
                        else 'Partially Paid'
                    )
                    VendorInvoice.objects.filter(pk=inv_pk).update(status=new_status)

                # ── PV-driven propagation ────────────────────────────
                # Payments created via the PV ``schedule_payment`` flow
                # don't carry per-invoice allocations — they reference
                # the PaymentVoucherGov directly. When such a payment
                # posts (cash leaves the TSA), we cascade the "Paid"
                # status to every upstream document linked through the
                # PV: the PV itself, the source VendorInvoice (matched
                # by invoice_number), and any contract IPC that has
                # this PV as its ``payment_voucher`` FK.
                #
                # All updates are best-effort — a partial cascade does
                # not roll back the cash event because the cash has
                # already moved. Errors are logged for ops follow-up.
                if payment.payment_voucher_id:
                    import logging as _logging
                    from django.utils import timezone
                    _log = _logging.getLogger(__name__)
                    try:
                        pv = payment.payment_voucher
                        # 1. Flip the PV to PAID (terminal status). If
                        #    a payment_instruction exists, mark it
                        #    PROCESSED so treasury reports stay in sync.
                        if pv.status not in ('PAID', 'CANCELLED', 'REVERSED'):
                            pv.status = 'PAID'
                            pv.save(update_fields=['status', 'updated_at'])
                        try:
                            from accounting.models.treasury import PaymentInstruction
                            pi = PaymentInstruction.objects.filter(payment_voucher=pv).first()
                            if pi and pi.status != 'PROCESSED':
                                pi.status = 'PROCESSED'
                                pi.processed_at = pi.processed_at or timezone.now()
                                pi.save(update_fields=['status', 'processed_at', 'updated_at'])
                        except Exception as exc:  # noqa: BLE001
                            _log.warning("PV propagation: PI sync failed for PV %s: %s", pv.pk, exc)

                        # 2. Mark the source VendorInvoice as Paid
                        #    (allocation-free path — the PV's amount
                        #    is by definition the full settlement).
                        if pv.invoice_number:
                            try:
                                from accounting.models.receivables import VendorInvoice
                                vi = VendorInvoice.objects.filter(
                                    invoice_number=pv.invoice_number,
                                ).first()
                                if vi is not None and vi.status not in ('Paid', 'Void'):
                                    vi.paid_amount = vi.total_amount
                                    vi.status = 'Paid'
                                    vi.save(_allow_status_change=True)
                            except Exception as exc:  # noqa: BLE001
                                _log.warning("PV propagation: VendorInvoice mark-paid failed for PV %s: %s", pv.pk, exc)

                        # 3. Auto-mark every linked IPC as PAID via
                        #    the IPC service (which records the audit
                        #    step and runs SoD checks). The reverse
                        #    manager is ``ipcs`` (declared on
                        #    IPC.payment_voucher).
                        try:
                            from contracts.services.ipc_service import IPCService
                            ipcs = list(pv.ipcs.all())
                        except Exception as exc:  # noqa: BLE001
                            _log.warning("PV propagation: IPC traversal failed for PV %s: %s", pv.pk, exc)
                            ipcs = []
                        for ipc in ipcs:
                            try:
                                if ipc.status != 'PAID':
                                    IPCService.mark_paid(
                                        ipc=ipc,
                                        payment_date=payment.payment_date,
                                        actor=request.user,
                                        notes=f"Auto-marked from Payment {payment.payment_number}",
                                    )
                            except Exception as exc:  # noqa: BLE001
                                # Don't roll back the cash event for
                                # an IPC mark-paid failure — log and
                                # leave the IPC for ops to reconcile.
                                _log.warning(
                                    "PV propagation: IPC %s mark-paid failed: %s",
                                    ipc.pk, exc,
                                )
                    except Exception as exc:  # noqa: BLE001
                        _log.warning("PV propagation: top-level failure for payment %s: %s", payment.pk, exc)

                # Update vendor balance (atomic F()-based)
                if payment.vendor:
                    from django.db.models import F
                    type(payment.vendor).objects.filter(pk=payment.vendor.pk).update(
                        balance=F('balance') - amount
                    )

                # P2P-C2: Encumbrance Liquidation — reduce/clear BudgetEncumbrance when payment is posted
                # Only liquidate if payment is linked to a PO
                po_reference = None
                for allocation in payment.allocations.select_related('invoice').all():
                    invoice = allocation.invoice
                    if invoice and invoice.purchase_order:
                        po_reference = invoice.purchase_order
                        break

                if po_reference:
                    # Race-safe encumbrance liquidation: lock + F() update.
                    # Previously this was read-modify-write so two
                    # concurrent payments against the same PO could both
                    # read the same liquidated_amount and one save would
                    # silently overwrite the other's increment.
                    enc_ids = list(
                        BudgetEncumbrance.objects.filter(
                            reference_type='PO',
                            reference_id=po_reference.pk,
                            status__in=['ACTIVE', 'PARTIALLY_LIQUIDATED'],
                        ).values_list('pk', flat=True)
                    )
                    for enc_id in enc_ids:
                        # Lock + atomic F() update.
                        BudgetEncumbrance.objects.select_for_update().filter(pk=enc_id).update(
                            liquidated_amount=F('liquidated_amount') + allocation.amount,
                        )
                        # Re-read to settle status field.
                        enc = BudgetEncumbrance.objects.get(pk=enc_id)
                        new_status = (
                            'FULLY_LIQUIDATED' if (enc.liquidated_amount or Decimal('0')) >= (enc.amount or Decimal('0'))
                            else 'PARTIALLY_LIQUIDATED'
                        )
                        BudgetEncumbrance.objects.filter(pk=enc_id).update(status=new_status)

            return Response({
                "status": "Payment posted successfully.",
                "journal_id": journal.id,
                "amount": str(amount)
            })
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @staticmethod
    def _update_gl_from_journal(journal):
        """Update GLBalance from journal lines — delegates to atomic F()-based service."""
        from accounting.services import update_gl_from_journal
        update_gl_from_journal(journal)


class PaymentAllocationViewSet(viewsets.ModelViewSet):
    queryset = PaymentAllocation.objects.select_related('payment', 'invoice')
    serializer_class = PaymentAllocationSerializer
    filterset_fields = ['payment', 'invoice']

    def perform_create(self, serializer):
        from rest_framework.exceptions import ValidationError
        payment = serializer.validated_data['payment']
        if payment.status != 'Draft':
            raise ValidationError("Can only allocate to Draft payments.")
        invoice = serializer.validated_data.get('invoice')
        if invoice:
            alloc_amount = Decimal(str(serializer.validated_data['amount']))
            # Sum all existing allocations against this invoice (including other payments
            # AND other allocations within this same payment) to prevent over-allocation.
            all_existing = PaymentAllocation.objects.filter(invoice=invoice).aggregate(
                total=Sum('amount')
            )['total'] or Decimal('0')
            balance_due = invoice.total_amount - invoice.paid_amount
            if all_existing + alloc_amount > balance_due:
                raise ValidationError(
                    f"Allocation of {alloc_amount} exceeds remaining invoice balance ({balance_due - all_existing})."
                )
        serializer.save()

    def perform_destroy(self, instance):
        from rest_framework.exceptions import ValidationError
        if instance.payment.status != 'Draft':
            raise ValidationError("Can only remove allocations from Draft payments.")
        super().perform_destroy(instance)
