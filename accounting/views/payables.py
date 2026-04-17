from .common import (
    viewsets, status, Response, action, transaction, Decimal, AccountingPagination, Sum,
)
from core.permissions import IsApprover
from ..models import (
    VendorInvoice, Payment, PaymentAllocation,
    Account, JournalHeader, JournalLine, BudgetEncumbrance, TransactionSequence,
)
from ..serializers import VendorInvoiceSerializer, PaymentSerializer, PaymentAllocationSerializer


class VendorInvoiceViewSet(viewsets.ModelViewSet):
    queryset = VendorInvoice.objects.all().select_related('vendor', 'fund', 'function', 'program', 'geo', 'currency', 'account')
    serializer_class = VendorInvoiceSerializer
    filterset_fields = ['status', 'vendor', 'invoice_date']
    search_fields = ['invoice_number', 'reference', 'vendor__name', 'description']
    pagination_class = AccountingPagination

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

        # Resolve accounts, falling back to settings defaults.
        has_po = bool(invoice.purchase_order_id)

        # Debit side (1 of 2 paths)
        debit_account = None
        debit_memo_prefix = 'Expense'
        if has_po:
            gr_ir_code = default_gl.get('GOODS_RECEIPT_CLEARING', '20601000')
            debit_account = Account.objects.filter(code=gr_ir_code).first()
            debit_memo_prefix = 'GR/IR Clearing'
        if not debit_account:
            debit_account = invoice.account
        if not debit_account:
            exp_code = default_gl.get('PURCHASE_EXPENSE', '50100000')
            debit_account = Account.objects.filter(code=exp_code).first()

        # Tax account (only if invoice has tax)
        tax_amount = invoice.tax_amount or Decimal('0')
        tax_account = None
        if tax_amount > 0:
            tax_account = Account.objects.filter(
                account_type='Asset', name__icontains='Input Tax'
            ).first() or Account.objects.filter(
                name__icontains='VAT Receivable'
            ).first() or Account.objects.filter(
                code=default_gl.get('TAX_PAYABLE', '20500000')
            ).first()

        # AP account (always on credit side)
        ap_code = default_gl.get('ACCOUNTS_PAYABLE', '20100000')
        ap_account = Account.objects.filter(code=ap_code).first()
        if not ap_account:
            ap_account = Account.objects.filter(
                account_type='Liability', name__icontains='Payable',
            ).first()

        # Build proposed lines — matches JournalLineDetailSerializer shape
        # so the frontend can render with the same component.
        lines = []
        subtotal = invoice.subtotal or Decimal('0')
        net_amount = subtotal if subtotal > 0 else (invoice.total_amount or Decimal('0')) - tax_amount
        total_amount = invoice.total_amount or Decimal('0')

        if debit_account and net_amount > 0:
            lines.append({
                'account': debit_account.pk,
                'account_code': debit_account.code,
                'account_name': debit_account.name,
                'debit': str(net_amount.quantize(Decimal('0.01'))),
                'credit': '0.00',
                'memo': f'{debit_memo_prefix}: {invoice.reference or invoice.invoice_number}',
            })

        if tax_account and tax_amount > 0:
            lines.append({
                'account': tax_account.pk,
                'account_code': tax_account.code,
                'account_name': tax_account.name,
                'debit': str(tax_amount.quantize(Decimal('0.01'))),
                'credit': '0.00',
                'memo': f'Input Tax: {invoice.reference or invoice.invoice_number}',
            })

        if ap_account and total_amount > 0:
            lines.append({
                'account': ap_account.pk,
                'account_code': ap_account.code,
                'account_name': ap_account.name,
                'debit': '0.00',
                'credit': str(total_amount.quantize(Decimal('0.01'))),
                'memo': f'AP: {invoice.vendor.name if invoice.vendor else "vendor"}',
            })

        # Warnings — surface configuration gaps so the finance team sees
        # them BEFORE attempting a Post and hitting a hard-stop.
        warnings = []
        if not debit_account:
            warnings.append(
                'No debit account configured (invoice.account is empty and '
                'PURCHASE_EXPENSE default is missing).'
            )
        if not ap_account:
            warnings.append('Accounts Payable account is not configured.')
        if tax_amount > 0 and not tax_account:
            warnings.append(
                'Invoice has tax but no Input Tax account is configured — '
                'the tax will land on the expense account on Post.'
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

        # ── Budget Validation (Appropriation availability) ──────────
        # Like SAP FB60: budget check + posting happen together. Validates
        # that the appropriation has enough remaining capacity for this
        # invoice. Returns a structured 400 with `appropriation_exceeded`
        # so the frontend can render a clear "budget overrun" modal.
        if invoice.mda and invoice.account and invoice.fund:
            try:
                from budget.services import BudgetValidationService, BudgetExceededError
                from accounting.models.ncoa import AdministrativeSegment, EconomicSegment, FundSegment
                from accounting.models.advanced import FiscalYear

                admin_seg = AdministrativeSegment.objects.filter(legacy_mda=invoice.mda).first()
                econ_seg  = EconomicSegment.objects.filter(legacy_account=invoice.account).first()
                fund_seg  = FundSegment.objects.filter(legacy_fund=invoice.fund).first()
                active_fy = FiscalYear.objects.filter(is_active=True).first()

                if admin_seg and econ_seg and fund_seg and active_fy:
                    try:
                        BudgetValidationService.validate_expenditure(
                            administrative_id=admin_seg.pk,
                            economic_id=econ_seg.pk,
                            fund_id=fund_seg.pk,
                            fiscal_year_id=active_fy.pk,
                            amount=invoice.total_amount,
                            source='VENDOR_INVOICE',
                        )
                    except BudgetExceededError as e:
                        return Response({
                            "error": f"Appropriation exceeded: {str(e)}",
                            "appropriation_exceeded": True,
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
        if invoice.mda and invoice.account and invoice.fund:
            from accounting.budget_logic import check_warrant_availability
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
                # Expense account: use invoice.account or fallback to settings
                expense_account = invoice.account
                if not expense_account:
                    exp_code = default_gl.get('PURCHASE_EXPENSE', '50100000')
                    expense_account = Account.objects.filter(code=exp_code).first()
                    if not expense_account:
                        expense_account = Account.objects.filter(account_type='Expense', name__icontains='Purchase').first()

                # AP account: ALWAYS from settings (separate from expense)
                ap_code = default_gl.get('ACCOUNTS_PAYABLE', '20100000')
                ap_account = Account.objects.filter(code=ap_code).first()
                if not ap_account:
                    ap_account = Account.objects.filter(account_type='Liability', name__icontains='Payable').first()

                if not expense_account or not ap_account:
                    return Response({"error": "Required GL accounts (Expense / AP) not found."}, status=status.HTTP_400_BAD_REQUEST)

                amount = invoice.total_amount

                # Create journal entry
                journal = JournalHeader.objects.create(
                    reference_number=f"VINV-{invoice.invoice_number}",
                    description=f"Vendor Invoice: {invoice.invoice_number}",
                    posting_date=invoice.invoice_date,
                    fund=invoice.fund,
                    function=invoice.function,
                    program=invoice.program,
                    geo=invoice.geo,
                    status='Posted'
                )

                # Assign Document Numbers
                if not invoice.document_number:
                    invoice.document_number = TransactionSequence.get_next('vendor_invoice_doc', 'VINV-')

                journal.document_number = TransactionSequence.get_next('journal_voucher', 'JV-')
                journal.save(update_fields=['document_number'], _allow_status_change=True)

                # PF-6: Split expense and tax into separate lines
                tax_amount = getattr(invoice, 'tax_amount', None) or Decimal('0.00')
                tax_account = None
                if tax_amount > 0:
                    tax_account = Account.objects.filter(
                        account_type='Asset', name__icontains='Input Tax'
                    ).first() or Account.objects.filter(
                        name__icontains='VAT Receivable'
                    ).first()

                if tax_amount > 0 and tax_account:
                    net_amount = amount - tax_amount
                else:
                    net_amount = amount

                # Debit Expense (net amount, or full amount if no tax split)
                JournalLine.objects.create(
                    header=journal,
                    account=expense_account,
                    debit=net_amount,
                    credit=Decimal('0.00'),
                    memo=f"Vendor invoice {invoice.invoice_number}"
                )

                # Debit Input Tax (if applicable and account exists)
                if tax_amount > 0 and tax_account:
                    JournalLine.objects.create(
                        header=journal,
                        account=tax_account,
                        debit=tax_amount,
                        credit=Decimal('0.00'),
                        memo=f"Input Tax: {invoice.invoice_number}"
                    )

                # Credit AP (total amount)
                JournalLine.objects.create(
                    header=journal,
                    account=ap_account,
                    debit=Decimal('0.00'),
                    credit=amount,
                    memo=f"AP: {invoice.vendor.name if invoice.vendor else 'vendor'}",
                    document_number=journal.document_number
                )

                # Set line document numbers
                for line in journal.lines.all():
                    line.document_number = journal.document_number
                    line.save(update_fields=['document_number'])

                # Update GL balances (atomic F()-based)
                from accounting.services import update_gl_from_journal
                update_gl_from_journal(journal, fund=invoice.fund, function=invoice.function,
                                       program=invoice.program, geo=invoice.geo)

                # Link the journal back to the invoice so the AP View modal
                # (and any other journal-drill-down reports) can traverse
                # VendorInvoice.journal_entry to find the GL entries. Without
                # this, the "GL Journal Posted" card never appears on Posted
                # invoices and audit reports show orphan journals.
                invoice.journal_entry = journal
                invoice.status = 'Posted'
                invoice.save(_allow_status_change=True)

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
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

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

        # S1-06 — fiscal period gate.
        try:
            from accounting.services.base_posting import BasePostingService
            BasePostingService._validate_fiscal_period(invoice.invoice_date, user=request.user)
        except Exception as exc:
            return Response(
                {"error": str(exc), "period_closed": True},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # SoD enforcement: credit memo requires elevated role
        from django_tenants.utils import schema_context
        try:
            with schema_context('public'):
                from tenants.models import UserTenantRole
                user_role = UserTenantRole.objects.filter(
                    user=request.user, tenant=request.tenant,
                ).first()
                if user_role and user_role.role in ('user', 'viewer'):
                    return Response(
                        {"error": "Separation of Duties: Credit Memo posting requires Manager or Admin role. "
                                  "Users who create vendor invoices cannot post credit memos."},
                        status=status.HTTP_403_FORBIDDEN,
                    )
        except Exception:
            pass  # If role check fails, allow through (fail-open for now)

        try:
            from django.conf import settings as django_settings
            default_gl = getattr(django_settings, 'DEFAULT_GL_ACCOUNTS', {})

            with transaction.atomic():
                # AP account: always from settings
                ap_code = default_gl.get('ACCOUNTS_PAYABLE', '20100000')
                ap_account = Account.objects.filter(code=ap_code).first()
                if not ap_account:
                    ap_account = Account.objects.filter(
                        account_type='Liability', name__icontains='Payable'
                    ).first()

                # Expense account: from invoice.account or line items or fallback
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
                    return Response(
                        {"error": "Required GL accounts (AP / Expense) not found."},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                amount = invoice.total_amount

                journal = JournalHeader.objects.create(
                    reference_number=f"CM-{invoice.invoice_number}",
                    description=f"Credit Memo: {invoice.invoice_number} — {invoice.vendor.name if invoice.vendor else ''}",
                    posting_date=invoice.invoice_date,
                    fund=invoice.fund,
                    function=invoice.function,
                    program=invoice.program,
                    geo=invoice.geo,
                    status='Posted',
                )

                # Assign document numbers
                if not invoice.document_number:
                    invoice.document_number = TransactionSequence.get_next('credit_memo_doc', 'CM-')

                journal.document_number = TransactionSequence.get_next('journal_voucher', 'JV-')
                journal.save(update_fields=['document_number'], _allow_status_change=True)

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

                # Update GL balances
                from accounting.services import update_gl_from_journal
                update_gl_from_journal(
                    journal,
                    fund=invoice.fund,
                    function=invoice.function,
                    program=invoice.program,
                    geo=invoice.geo,
                )

                invoice.status = 'Posted'
                invoice.save(_allow_status_change=True)

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


class PaymentViewSet(viewsets.ModelViewSet):
    queryset = Payment.objects.all().select_related(
        'vendor', 'bank_account', 'currency', 'journal_entry'
    ).prefetch_related('allocations')
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

        # S1-11 — Re-check warrant availability at payment time. A warrant
        # released at invoice time may have been suspended or fully
        # consumed by other disbursements before this cheque goes out.
        # Walk through each allocation and ensure aggregate MDA/fund
        # commitment stays under warrant ceiling.
        try:
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
            for b in buckets.values():
                if b['amount'] == 0:
                    continue
                allowed, warrant_msg, info = check_warrant_availability(
                    dimensions={'mda': b['mda'], 'fund': b['fund']},
                    account=b['account'],
                    amount=b['amount'],
                )
                if not allowed:
                    return Response(
                        {
                            "error": f"Warrant ceiling breached at payment time: {warrant_msg}",
                            "warrant_exceeded": True,
                            "info": info,
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
        except ImportError:
            pass

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
                # Resolve GL accounts
                ap_code = default_gl.get('ACCOUNTS_PAYABLE', '20100000')
                ap_account = Account.objects.filter(code=ap_code).first()
                if not ap_account:
                    ap_account = Account.objects.filter(account_type='Liability', name__icontains='Payable').first()

                bank_gl_account = None
                if payment.bank_account:
                    bank_gl_account = payment.bank_account.gl_account
                if not bank_gl_account:
                    cash_code = default_gl.get('CASH_ACCOUNT', '10100000')
                    bank_gl_account = Account.objects.filter(code=cash_code).first()
                    if not bank_gl_account:
                        bank_gl_account = Account.objects.filter(account_type='Asset', name__icontains='Bank').first()

                if not ap_account or not bank_gl_account:
                    return Response({"error": "Required GL accounts (AP / Bank) not found."}, status=status.HTTP_400_BAD_REQUEST)

                amount = payment.total_amount

                # PF-15: Copy fund/function/program/geo dimensions from the
                # related invoice journal lines so payment journals carry
                # the same dimension coding as their source invoices.
                first_invoice = payment.allocations.select_related('invoice').first()
                inv = first_invoice.invoice if first_invoice else None

                # Create journal entry with dimensions from invoice
                journal = JournalHeader.objects.create(
                    reference_number=f"PAY-{payment.payment_number}",
                    description=f"Payment: {payment.payment_number}",
                    posting_date=payment.payment_date,
                    status='Posted',
                    fund=getattr(inv, 'fund', None),
                    function=getattr(inv, 'function', None),
                    program=getattr(inv, 'program', None),
                    geo=getattr(inv, 'geo', None),
                )

                # Assign Document Numbers
                if not payment.document_number:
                    payment.document_number = TransactionSequence.get_next('payment_doc', 'PAY-')

                journal.document_number = TransactionSequence.get_next('journal_voucher', 'JV-')
                journal.save(update_fields=['document_number'], _allow_status_change=True)

                # Debit AP (reduce liability)
                JournalLine.objects.create(
                    header=journal,
                    account=ap_account,
                    debit=amount,
                    credit=Decimal('0.00'),
                    memo=f"Payment to {payment.vendor.name if payment.vendor else 'vendor'}"
                )

                # Credit Bank (reduce asset)
                JournalLine.objects.create(
                    header=journal,
                    account=bank_gl_account,
                    debit=Decimal('0.00'),
                    credit=amount,
                    memo=f"Bank payment {payment.payment_number}",
                    document_number=journal.document_number
                )

                # Set line document numbers
                for line in journal.lines.all():
                    line.document_number = journal.document_number
                    line.save(update_fields=['document_number'])

                # Update GL balances
                self._update_gl_from_journal(journal)

                # Link journal to payment and update status
                payment.journal_entry = journal
                payment.status = 'Posted'
                payment.save(_allow_status_change=True)

                # Update invoice paid amounts
                for allocation in payment.allocations.select_related('invoice').all():
                    invoice = allocation.invoice
                    invoice.paid_amount += allocation.amount
                    if invoice.paid_amount >= invoice.total_amount:
                        invoice.status = 'Paid'
                    else:
                        invoice.status = 'Partially Paid'
                    invoice.save(_allow_status_change=True)

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
                    encumbrances = BudgetEncumbrance.objects.filter(
                        reference_type='PO',
                        reference_id=po_reference.pk,
                        status__in=['ACTIVE', 'PARTIALLY_LIQUIDATED']
                    )
                    for enc in encumbrances:
                        enc.liquidated_amount = (enc.liquidated_amount or Decimal('0')) + allocation.amount
                        if enc.liquidated_amount >= enc.amount:
                            enc.status = 'FULLY_LIQUIDATED'
                        else:
                            enc.status = 'PARTIALLY_LIQUIDATED'
                        enc.save()

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
