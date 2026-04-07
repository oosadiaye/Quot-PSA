from .common import (
    viewsets, status, Response, action, DjangoFilterBackend,
    transaction, Decimal, AccountingPagination, Sum,
)
from core.permissions import IsApprover
from ..models import (
    VendorInvoice, Payment, PaymentAllocation,
    Account, JournalHeader, JournalLine, GLBalance, BudgetEncumbrance, TransactionSequence,
)
from ..serializers import VendorInvoiceSerializer, PaymentSerializer, PaymentAllocationSerializer


class VendorInvoiceViewSet(viewsets.ModelViewSet):
    queryset = VendorInvoice.objects.all().select_related('vendor', 'fund', 'function', 'program', 'geo', 'currency', 'account')
    serializer_class = VendorInvoiceSerializer
    filterset_fields = ['status', 'vendor', 'invoice_date']
    pagination_class = AccountingPagination

    def get_permissions(self):
        if self.action == 'post_invoice':
            return [IsApprover('post')]
        return super().get_permissions()

    def perform_destroy(self, instance):
        if instance.status != 'Draft':
            from rest_framework.exceptions import ValidationError
            raise ValidationError("Only draft vendor invoices can be deleted.")
        super().perform_destroy(instance)

    @action(detail=True, methods=['post'])
    def approve_invoice(self, request, pk=None):
        """Approve vendor invoice."""
        invoice = self.get_object()
        if invoice.status != 'Draft':
            return Response({"error": "Only draft invoices can be approved."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            invoice.status = 'Approved'
            invoice.save()
            return Response({"status": "Invoice approved successfully."})
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def post_invoice(self, request, pk=None):
        """Post vendor invoice — creates journal entry with separate expense + AP accounts."""
        invoice = self.get_object()

        if invoice.status == 'Posted':
            return Response({"error": "Invoice already posted."}, status=status.HTTP_400_BAD_REQUEST)

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

                invoice.status = 'Posted'
                invoice.save(_allow_status_change=True)

                # INT-5: Liquidate budget encumbrances when invoice references a PO
                if hasattr(invoice, 'purchase_order') and invoice.purchase_order:
                    from django.db.models import F as _F
                    BudgetEncumbrance.objects.filter(
                        reference_number=invoice.purchase_order.po_number
                    ).update(liquidated_amount=_F('amount'), status='Liquidated')

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
        """Post credit memo — Dr AP (reduce payable), Cr Expense (reduce expense)."""
        invoice = self.get_object()

        if invoice.document_type != 'Credit Memo':
            return Response({"error": "This document is not a credit memo."}, status=status.HTTP_400_BAD_REQUEST)

        if invoice.status == 'Posted':
            return Response({"error": "Credit memo already posted."}, status=status.HTTP_400_BAD_REQUEST)

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

            return Response({
                "status": "Credit memo posted to GL successfully.",
                "journal_id": journal.id,
                "invoice_id": invoice.id,
                "amount": str(amount),
            })
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'])
    def aging_report(self, request):
        """Get accounts payable aging report"""
        from datetime import timedelta
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
        if self.action == 'post_payment':
            return [IsApprover('post')]
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
