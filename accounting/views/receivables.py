from django.db.models import F
from .common import (
    viewsets, status, Response, action, DjangoFilterBackend,
    transaction, Decimal, AccountingPagination, Sum,
)
from core.permissions import IsApprover
from ..models import (
    CustomerInvoice, Receipt, ReceiptAllocation,
    Account, JournalHeader, JournalLine, GLBalance, TransactionSequence,
)
from ..serializers import CustomerInvoiceSerializer, ReceiptSerializer, ReceiptAllocationSerializer


class CustomerInvoiceViewSet(viewsets.ModelViewSet):
    queryset = CustomerInvoice.objects.all().select_related('customer', 'fund', 'function', 'program', 'geo', 'currency')
    serializer_class = CustomerInvoiceSerializer
    filterset_fields = ['status', 'customer', 'invoice_date']

    def perform_destroy(self, instance):
        if instance.status != 'Draft':
            from rest_framework.exceptions import ValidationError
            raise ValidationError("Only draft customer invoices can be deleted.")
        super().perform_destroy(instance)

    def _post_to_gl(self, invoice, user):
        """Post customer invoice to GL in real-time with proper journal entry creation."""
        from django.conf import settings

        default_gl = getattr(settings, 'DEFAULT_GL_ACCOUNTS', {})

        ar_code = default_gl.get('ACCOUNTS_RECEIVABLE', '10200000')
        ar_account = Account.objects.filter(code=ar_code).first()
        if not ar_account:
            ar_account = Account.objects.filter(
                account_type='Asset', is_reconciliation=True,
                reconciliation_type='accounts_receivable'
            ).first()

        rev_code = default_gl.get('SALES_REVENUE', '40100000')
        revenue_account = Account.objects.filter(code=rev_code).first()

        if not ar_account or not revenue_account:
            raise Exception("Required GL accounts (AR / Revenue) not found. Configure DEFAULT_GL_ACCOUNTS in settings.")

        amount = invoice.total_amount

        with transaction.atomic():
            # Generate document number for the invoice
            if not invoice.document_number:
                invoice.document_number = TransactionSequence.get_next('invoice_doc', 'INV-')
                invoice.save(update_fields=['document_number'])

            # Create proper journal entry for audit trail
            journal = JournalHeader.objects.create(
                reference_number=f"CINV-{invoice.invoice_number}",
                description=f"Customer Invoice: {invoice.invoice_number}",
                posting_date=invoice.invoice_date,
                fund=invoice.fund,
                function=invoice.function,
                program=invoice.program,
                geo=invoice.geo,
                status='Posted',
            )

            journal.document_number = TransactionSequence.get_next('journal_voucher', 'JV-')
            journal.save(update_fields=['document_number'], _allow_status_change=True)

            # Debit AR (increase receivable)
            JournalLine.objects.create(
                header=journal,
                account=ar_account,
                debit=amount,
                credit=Decimal('0.00'),
                memo=f"AR from invoice {invoice.invoice_number}",
                document_number=journal.document_number,
            )

            # Credit Revenue
            JournalLine.objects.create(
                header=journal,
                account=revenue_account,
                debit=Decimal('0.00'),
                credit=amount,
                memo=f"Revenue: {invoice.customer.name if invoice.customer else 'customer'}",
                document_number=journal.document_number,
            )

            # Update GL balances from journal lines
            self._update_gl_from_journal(journal)

            # Link journal to invoice and persist
            invoice.journal_entry = journal
            invoice.save(update_fields=['journal_entry'])

    @action(detail=True, methods=['post'])
    def send_invoice(self, request, pk=None):
        """Mark invoice as sent to customer."""
        invoice = self.get_object()
        if invoice.status != 'Draft':
            return Response({"error": "Only draft invoices can be sent."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            invoice.status = 'Sent'
            invoice.save()
            return Response({"status": "Invoice sent successfully."})
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def post_invoice(self, request, pk=None):
        """Post customer invoice to GL in real-time."""
        invoice = self.get_object()

        if invoice.status == 'Posted':
            return Response({"error": "Invoice already posted."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            self._post_to_gl(invoice, request.user)

            invoice.status = 'Posted'
            invoice.save(_allow_status_change=True)

            return Response({
                "status": "Invoice posted to GL successfully.",
                "invoice_id": invoice.id,
                "amount": str(invoice.total_amount),
                "fiscal_year": invoice.invoice_date.year,
                "period": invoice.invoice_date.month
            })
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @staticmethod
    def _update_gl_from_journal(journal):
        """Update GLBalance from journal lines — delegates to atomic F()-based service."""
        from accounting.services import update_gl_from_journal
        update_gl_from_journal(journal)

    @action(detail=True, methods=['post'])
    def post_credit_memo(self, request, pk=None):
        """Post AR credit memo to GL: Dr Revenue / Cr Accounts Receivable."""
        invoice = self.get_object()

        if invoice.document_type != 'Credit Memo':
            return Response({"error": "This document is not a Credit Memo."}, status=status.HTTP_400_BAD_REQUEST)
        if invoice.status == 'Posted':
            return Response({"error": "Credit memo already posted."}, status=status.HTTP_400_BAD_REQUEST)

        from django.conf import settings as django_settings
        default_gl = getattr(django_settings, 'DEFAULT_GL_ACCOUNTS', {})

        ar_code = default_gl.get('ACCOUNTS_RECEIVABLE', '10200000')
        ar_account = Account.objects.filter(code=ar_code).first()
        if not ar_account:
            ar_account = Account.objects.filter(
                account_type='Asset', is_reconciliation=True,
                reconciliation_type='accounts_receivable'
            ).first()

        rev_code = default_gl.get('SALES_REVENUE', '40100000')
        revenue_account = Account.objects.filter(code=rev_code).first()

        if not ar_account or not revenue_account:
            return Response(
                {"error": "Required GL accounts (AR / Revenue) not found. Configure DEFAULT_GL_ACCOUNTS in settings."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        amount = invoice.total_amount

        try:
            with transaction.atomic():
                if not invoice.document_number:
                    invoice.document_number = TransactionSequence.get_next('credit_memo_ar_doc', 'ARCM-')
                    invoice.save(update_fields=['document_number'])

                journal = JournalHeader.objects.create(
                    reference_number=f"ARCM-{invoice.invoice_number}",
                    description=f"AR Credit Memo: {invoice.invoice_number}",
                    posting_date=invoice.invoice_date,
                    fund=invoice.fund,
                    function=invoice.function,
                    program=invoice.program,
                    geo=invoice.geo,
                    status='Posted',
                )
                journal.document_number = TransactionSequence.get_next('journal_voucher', 'JV-')
                journal.save(update_fields=['document_number'], _allow_status_change=True)

                # Dr Revenue (reverses revenue earned)
                JournalLine.objects.create(
                    header=journal,
                    account=revenue_account,
                    debit=amount,
                    credit=Decimal('0.00'),
                    memo=f"CR Memo revenue reversal: {invoice.invoice_number}",
                    document_number=journal.document_number,
                )
                # Cr AR (reduces receivable)
                JournalLine.objects.create(
                    header=journal,
                    account=ar_account,
                    debit=Decimal('0.00'),
                    credit=amount,
                    memo=f"CR Memo AR reduction: {invoice.customer.name if invoice.customer else ''}",
                    document_number=journal.document_number,
                )

                CustomerInvoiceViewSet._update_gl_from_journal(journal)

                invoice.journal_entry = journal
                invoice.status = 'Posted'
                invoice.save(_allow_status_change=True)

            return Response({
                "status": "Credit memo posted to GL successfully.",
                "invoice_id": invoice.id,
                "amount": str(amount),
            })
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'])
    def aging_report(self, request):
        """Get accounts receivable aging report"""
        from datetime import timedelta
        from django.utils import timezone

        as_of_date = request.query_params.get('as_of_date')
        if as_of_date:
            from datetime import datetime
            as_of_date = datetime.strptime(as_of_date, '%Y-%m-%d').date()
        else:
            as_of_date = timezone.now().date()

        invoices = CustomerInvoice.objects.filter(
            status__in=['Sent', 'Partially Paid', 'Overdue'],
            invoice_date__lte=as_of_date
        ).select_related('customer')

        aging_data = {}
        for invoice in invoices:
            customer_id = invoice.customer.id
            if customer_id not in aging_data:
                aging_data[customer_id] = {
                    'customer_id': customer_id,
                    'customer_name': invoice.customer.name,
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
                aging_data[customer_id]['current'] += balance
            elif days_overdue <= 30:
                aging_data[customer_id]['days_1_30'] += balance
            elif days_overdue <= 60:
                aging_data[customer_id]['days_31_60'] += balance
            elif days_overdue <= 90:
                aging_data[customer_id]['days_61_90'] += balance
            else:
                aging_data[customer_id]['days_91_plus'] += balance

            aging_data[customer_id]['total_due'] += balance

        total_current = sum(d['current'] for d in aging_data.values())
        total_1_30 = sum(d['days_1_30'] for d in aging_data.values())
        total_31_60 = sum(d['days_31_60'] for d in aging_data.values())
        total_61_90 = sum(d['days_61_90'] for d in aging_data.values())
        total_91_plus = sum(d['days_91_plus'] for d in aging_data.values())

        return Response({
            'as_of_date': as_of_date,
            'customers': list(aging_data.values()),
            'summary': {
                'current': float(total_current),
                'days_1_30': float(total_1_30),
                'days_31_60': float(total_31_60),
                'days_61_90': float(total_61_90),
                'days_91_plus': float(total_91_plus),
                'total_due': float(total_current + total_1_30 + total_31_60 + total_61_90 + total_91_plus)
            }
        })


class ReceiptViewSet(viewsets.ModelViewSet):
    queryset = Receipt.objects.all().select_related(
        'customer', 'bank_account', 'currency', 'journal_entry'
    ).prefetch_related('allocations')
    serializer_class = ReceiptSerializer
    filterset_fields = ['status', 'receipt_date', 'payment_method']

    def get_permissions(self):
        if self.action == 'post_receipt':
            return [IsApprover('post')]
        return super().get_permissions()

    def perform_destroy(self, instance):
        if instance.status != 'Draft':
            from rest_framework.exceptions import ValidationError
            raise ValidationError("Only draft receipts can be deleted.")
        super().perform_destroy(instance)

    @action(detail=True, methods=['post'])
    def post_receipt(self, request, pk=None):
        """Post receipt — creates journal entry + updates GL balances + customer balance."""
        receipt = self.get_object()
        if receipt.status == 'Posted':
            return Response({"error": "Receipt already posted."}, status=status.HTTP_400_BAD_REQUEST)

        # Advance / downpayment receipts do not require invoice allocations
        if receipt.is_advance:
            pass  # Skip allocation check — handled via Customer Advances GL account below
        else:
            if not receipt.allocations.exists():
                return Response({"error": "Receipt has no allocations."}, status=status.HTTP_400_BAD_REQUEST)

            # Validate allocations sum equals receipt total
            allocation_sum = receipt.allocations.aggregate(total=Sum('amount'))['total'] or Decimal('0')
            if allocation_sum != receipt.total_amount:
                return Response(
                    {"error": f"Allocation total ({allocation_sum}) does not match receipt amount ({receipt.total_amount})."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        try:
            from django.conf import settings as django_settings
            default_gl = getattr(django_settings, 'DEFAULT_GL_ACCOUNTS', {})

            with transaction.atomic():
                # Resolve GL accounts
                ar_code = default_gl.get('ACCOUNTS_RECEIVABLE', '10200000')
                ar_account = Account.objects.filter(code=ar_code).first()
                if not ar_account:
                    ar_account = Account.objects.filter(account_type='Asset', name__icontains='Receivable').first()

                bank_gl_account = None
                if receipt.bank_account:
                    bank_gl_account = receipt.bank_account.gl_account
                if not bank_gl_account:
                    cash_code = default_gl.get('CASH_ACCOUNT', '10100000')
                    bank_gl_account = Account.objects.filter(code=cash_code).first()
                    if not bank_gl_account:
                        bank_gl_account = Account.objects.filter(account_type='Asset', name__icontains='Bank').first()

                if not bank_gl_account:
                    return Response({"error": "Required GL account (Bank / Cash) not found."}, status=status.HTTP_400_BAD_REQUEST)

                amount = receipt.total_amount

                # Create journal entry
                journal = JournalHeader.objects.create(
                    reference_number=f"RCT-{receipt.receipt_number}",
                    description=f"{'Downpayment' if receipt.is_advance else 'Receipt'}: {receipt.receipt_number}",
                    posting_date=receipt.receipt_date,
                    status='Posted'
                )

                # Assign Document Numbers
                if not receipt.document_number:
                    receipt.document_number = TransactionSequence.get_next('receipt_doc', 'RCT-')

                journal.document_number = TransactionSequence.get_next('journal_voucher', 'JV-')
                journal.save(update_fields=['document_number'], _allow_status_change=True)

                # Debit Bank (increase asset)
                JournalLine.objects.create(
                    header=journal,
                    account=bank_gl_account,
                    debit=amount,
                    credit=Decimal('0.00'),
                    memo=f"{'Downpayment' if receipt.is_advance else 'Bank receipt'} {receipt.receipt_number}"
                )

                if receipt.is_advance:
                    # Credit Customer Advances Received (liability) for downpayments
                    from accounting.models import AccountingSettings as _Settings
                    _s = _Settings.objects.first()
                    credit_account = (_s.downpayment_gl_account if _s and _s.downpayment_gl_account else None)
                    if not credit_account:
                        adv_code = default_gl.get('CUSTOMER_ADVANCES', '22000000')
                        credit_account = Account.objects.filter(code=adv_code).first()
                        if not credit_account:
                            credit_account = Account.objects.filter(
                                account_type='Liability', name__icontains='Advance'
                            ).first()
                    if not credit_account:
                        return Response({"error": "Customer Advances GL account not found. Set it in Accounting Settings."}, status=status.HTTP_400_BAD_REQUEST)
                    JournalLine.objects.create(
                        header=journal,
                        account=credit_account,
                        debit=Decimal('0.00'),
                        credit=amount,
                        memo=f"Customer downpayment from {receipt.customer.name if receipt.customer else 'customer'}",
                        document_number=journal.document_number
                    )
                    # Track remaining advance balance
                    receipt.advance_remaining = amount
                else:
                    if not ar_account:
                        return Response({"error": "Required GL account (Accounts Receivable) not found."}, status=status.HTTP_400_BAD_REQUEST)
                    # Credit AR (reduce receivable) for regular receipts
                    JournalLine.objects.create(
                        header=journal,
                        account=ar_account,
                        debit=Decimal('0.00'),
                        credit=amount,
                        memo=f"Receipt from {receipt.customer.name if receipt.customer else 'customer'}",
                        document_number=journal.document_number
                    )

                # Set line document numbers
                for line in journal.lines.all():
                    line.document_number = journal.document_number
                    line.save(update_fields=['document_number'])

                # Update GL balances
                self._update_gl_from_journal(journal)

                # Link journal to receipt and update status
                receipt.journal_entry = journal
                receipt.status = 'Posted'
                receipt.save(_allow_status_change=True)

                # Update invoice received amounts atomically (F() prevents lost-update race)
                if not receipt.is_advance:
                    for allocation in receipt.allocations.select_related('invoice').all():
                        CustomerInvoice.objects.filter(pk=allocation.invoice_id).update(
                            received_amount=F('received_amount') + allocation.amount
                        )
                        # Re-fetch to compute new status from DB value
                        updated = CustomerInvoice.objects.get(pk=allocation.invoice_id)
                        new_status = 'Paid' if updated.received_amount >= updated.total_amount else 'Partially Paid'
                        CustomerInvoice.objects.filter(pk=allocation.invoice_id).update(status=new_status)

                # Update customer balance (atomic F()-based)
                if receipt.customer:
                    type(receipt.customer).objects.filter(pk=receipt.customer.pk).update(
                        balance=F('balance') - amount
                    )

            return Response({
                "status": "Receipt posted to GL successfully.",
                "journal_id": journal.id,
                "receipt_id": receipt.id,
                "amount": str(amount)
            })
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @staticmethod
    def _update_gl_from_journal(journal):
        """Update GLBalance from journal lines — delegates to atomic F()-based service."""
        from accounting.services import update_gl_from_journal
        update_gl_from_journal(journal)


class ReceiptAllocationViewSet(viewsets.ModelViewSet):
    """
    Manage allocations that link a Receipt to a CustomerInvoice.

    Allocations are only valid on Draft receipts — modifying them after
    posting would produce GL inconsistencies, so create/destroy are blocked
    once the parent Receipt is no longer in Draft status.
    """
    queryset = ReceiptAllocation.objects.select_related('receipt', 'invoice')
    serializer_class = ReceiptAllocationSerializer
    filterset_fields = ['receipt', 'invoice']

    def _assert_receipt_draft(self, receipt_id, operation='modified'):
        from rest_framework.exceptions import ValidationError
        try:
            receipt = Receipt.objects.get(pk=receipt_id)
        except Receipt.DoesNotExist:
            raise ValidationError("Receipt not found.")
        if receipt.status != 'Draft':
            raise ValidationError(
                f"Receipt allocations cannot be {operation} once the receipt is {receipt.status}."
            )
        return receipt

    def perform_create(self, serializer):
        self._assert_receipt_draft(
            self.request.data.get('receipt'), operation='created'
        )
        receipt_id = self.request.data.get('receipt')
        receipt = Receipt.objects.get(pk=receipt_id)
        existing = ReceiptAllocation.objects.filter(receipt=receipt).aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0')
        new_amount = Decimal(str(self.request.data.get('amount', 0)))
        if existing + new_amount > receipt.total_amount:
            from rest_framework.exceptions import ValidationError
            raise ValidationError(
                f"Allocation would exceed receipt total "
                f"({existing + new_amount} > {receipt.total_amount})."
            )
        serializer.save()

    def perform_destroy(self, instance):
        self._assert_receipt_draft(instance.receipt_id, operation='deleted')
        instance.delete()


class CustomerLedgerView(viewsets.ViewSet):
    """Unified customer transaction ledger — invoices, receipts, and credit memos."""

    def list(self, request):
        customer_id = request.query_params.get('customer')
        if not customer_id:
            return Response({"error": "customer query parameter is required"}, status=status.HTTP_400_BAD_REQUEST)

        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        doc_number = request.query_params.get('document_number')
        account_id = request.query_params.get('account')
        min_amount = request.query_params.get('min_amount')
        max_amount = request.query_params.get('max_amount')

        entries = []

        # Invoices (debits to customer)
        inv_qs = CustomerInvoice.objects.filter(
            customer_id=customer_id
        ).exclude(status='Void').select_related('customer', 'journal_entry')

        if start_date:
            inv_qs = inv_qs.filter(invoice_date__gte=start_date)
        if end_date:
            inv_qs = inv_qs.filter(invoice_date__lte=end_date)
        if doc_number:
            inv_qs = inv_qs.filter(invoice_number__icontains=doc_number)

        for inv in inv_qs:
            amt = float(inv.total_amount or 0)
            if min_amount and amt < float(min_amount):
                continue
            if max_amount and amt > float(max_amount):
                continue
            entries.append({
                'date': str(inv.invoice_date),
                'type': 'Invoice',
                'document_number': inv.invoice_number,
                'description': inv.description or f'Invoice {inv.invoice_number}',
                'debit': str(inv.total_amount),
                'credit': '0.00',
                'status': inv.status,
                'reference': inv.reference or '',
                'journal_number': inv.journal_entry.reference_number if inv.journal_entry else '',
                'id': inv.id,
            })

        # Receipts (credits from customer)
        rcpt_qs = Receipt.objects.filter(
            customer_id=customer_id
        ).exclude(status='Void').select_related('customer', 'journal_entry')

        if start_date:
            rcpt_qs = rcpt_qs.filter(receipt_date__gte=start_date)
        if end_date:
            rcpt_qs = rcpt_qs.filter(receipt_date__lte=end_date)
        if doc_number:
            rcpt_qs = rcpt_qs.filter(receipt_number__icontains=doc_number)

        for rcpt in rcpt_qs:
            amt = float(rcpt.total_amount or 0)
            if min_amount and amt < float(min_amount):
                continue
            if max_amount and amt > float(max_amount):
                continue
            entries.append({
                'date': str(rcpt.receipt_date),
                'type': 'Receipt',
                'document_number': rcpt.receipt_number,
                'description': f'Payment received — {rcpt.get_payment_method_display()}',
                'debit': '0.00',
                'credit': str(rcpt.total_amount),
                'status': rcpt.status,
                'reference': rcpt.reference_number or '',
                'journal_number': rcpt.journal_entry.reference_number if rcpt.journal_entry else '',
                'id': rcpt.id,
            })

        # Filter by GL account if requested (via journal lines)
        if account_id:
            journal_refs = set()
            jl_qs = JournalLine.objects.filter(
                account_id=account_id,
                header__status='Posted',
            ).values_list('header__reference_number', flat=True)
            journal_refs = set(jl_qs)
            entries = [e for e in entries if e['journal_number'] in journal_refs or e['document_number'] in journal_refs]

        # Sort by date descending
        entries.sort(key=lambda e: e['date'], reverse=True)

        # Running balance
        balance = Decimal('0.00')
        for e in reversed(entries):
            balance += Decimal(e['debit']) - Decimal(e['credit'])
            e['running_balance'] = str(balance)

        # Summary
        total_debit = sum(Decimal(e['debit']) for e in entries)
        total_credit = sum(Decimal(e['credit']) for e in entries)

        return Response({
            'entries': entries,
            'summary': {
                'total_debit': str(total_debit),
                'total_credit': str(total_credit),
                'balance': str(total_debit - total_credit),
                'transaction_count': len(entries),
            }
        })
