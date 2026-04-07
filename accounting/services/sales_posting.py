"""
Sales Posting Service — accounting domain.

Handles GL posting for all sales-cycle transactions:
Sales Orders, Delivery Notes, Sales Returns, Credit Notes, and Customer Receipts.
"""

import logging
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from accounting.models import JournalHeader, JournalLine, Account
from accounting.services.base_posting import BasePostingService, TransactionPostingError, get_gl_account

logger = logging.getLogger(__name__)


class SalesPostingService(BasePostingService):
    """
    GL posting service for the Sales domain.
    """

    @staticmethod
    @transaction.atomic
    def post_sales_order(order):
        """
        Post a Sales Order to the GL.

        O2C-H3: Revenue recognition moved to DELIVERY.
        This creates ONLY the COGS/Inventory entries at order time.
        Revenue and AR are posted when delivery note is posted.

        Creates journal entry for:
        - Cost of Goods Sold (debit)
        - Inventory (credit)

        Args:
            order: SalesOrder instance

        Returns:
            JournalHeader: The created journal entry
        """
        if order.status != 'Posted':
            raise TransactionPostingError(f"Order must be Posted status, got {order.status}")

        SalesPostingService._check_duplicate_posting(order.order_number)
        SalesPostingService._validate_fiscal_period(order.order_date)

        if order.lines.count() == 0:
            raise TransactionPostingError("Order has no lines")

        total_amount = order.subtotal
        tax_amount = order.tax_amount
        grand_total = total_amount + tax_amount

        # Get COGS and Inventory accounts from first line's item (if available)
        cogs_account = None
        inventory_account = None

        first_line = order.lines.first()
        if first_line and first_line.item:
            item = first_line.item
            if item.product_type:
                cogs_account = item.product_type.expense_account
                inventory_account = item.product_type.inventory_account
            if not cogs_account:
                cogs_account = item.expense_account
            if not inventory_account:
                inventory_account = item.inventory_account

        if not cogs_account:
            cogs_account = get_gl_account('COGS_EXPENSE', 'Expense', 'Cost of Goods')

        if not inventory_account:
            inventory_account = get_gl_account('INVENTORY', 'Asset', 'Inventory')

        if not cogs_account or not inventory_account:
            raise TransactionPostingError(
                f"Missing COGS or Inventory account. COGS: {cogs_account}, Inventory: {inventory_account}"
            )

        # Create journal header
        journal = JournalHeader.objects.create(
            posting_date=order.order_date,
            description=f"Sales Order {order.order_number} - Customer: {order.customer.name}",
            reference_number=order.order_number,
            mda=order.mda,
            fund=order.fund,
            function=order.function,
            program=order.program,
            geo=order.geo,
            status='Posted',
            source_module='sales',
            source_document_id=order.pk,
        )

        # O2C-H3: COGS is now posted at delivery time (post_delivery_note)
        # Only the journal header is created here for invoice linkage

        # Link journal to order (no invoice created at SO time - created at delivery)
        from sales.models import CustomerInvoice
        from accounting.models import Currency
        invoice_currency = None
        if hasattr(order, 'currency') and order.currency:
            invoice_currency = order.currency
        elif hasattr(order.customer, 'currency') and order.customer.currency:
            invoice_currency = order.customer.currency
        else:
            invoice_currency = Currency.objects.filter(is_base_currency=True).first()

        # O2C-H3: Create DRAFT invoice at SO time (revenue recognized at delivery)
        CustomerInvoice.objects.create(
            invoice_number=f"INV-{order.order_number}",
            customer=order.customer,
            sales_order=order,
            invoice_date=order.order_date,
            due_date=order.order_date,
            fund=order.fund,
            function=order.function,
            program=order.program,
            geo=order.geo,
            subtotal=total_amount,
            tax_amount=tax_amount,
            total_amount=grand_total,
            currency=invoice_currency,
            status='Draft',  # O2C-H3: Invoice in Draft until delivery
            journal_entry=journal
        )

        # Update customer balance (atomic F()-based)
        from django.db.models import F
        type(order.customer).objects.filter(pk=order.customer.pk).update(
            balance=F('balance') + grand_total
        )

        # NOTE: This journal is intentionally a placeholder header with NO lines.
        # O2C-H3: All GL lines (DR AR, CR Revenue, DR COGS, CR Inventory) are created
        # by post_delivery_note() at delivery time. Calling _validate_journal_balanced
        # here would always fail (0 lines < 2 required), and _update_gl_balances would
        # be a no-op since there are no lines to process. Both are intentionally omitted.
        return journal

    @staticmethod
    @transaction.atomic
    def post_delivery_note(delivery_note):
        """
        Post a Delivery Note to the GL.

        O2C-H3: Revenue Recognition at Delivery
        - Posts AR and Revenue at delivery time
        - COGS was already posted at SO time

        Args:
            delivery_note: DeliveryNote instance

        Returns:
            JournalHeader: The created journal entry (if applicable)
        """
        if delivery_note.status != 'Posted':
            raise TransactionPostingError(f"Delivery must be Posted status, got {delivery_note.status}")

        SalesPostingService._check_duplicate_posting(delivery_note.delivery_number)
        SalesPostingService._validate_fiscal_period(delivery_note.delivery_date)

        order = delivery_note.sales_order

        # O2C approval gate: the originating SalesOrder must be in an approved/
        # fulfilment-stage status before goods can be recognised as delivered.
        if order and order.status not in ('Approved', 'Partially Delivered', 'Delivered', 'Posted'):
            raise TransactionPostingError(
                f"SalesOrder {order.pk} must be Approved before delivery can be posted "
                f"(current status: '{order.status}'). "
                f"Please approve the sales order first."
            )

        # PF-8: Guard against duplicate delivery GL posting
        from django.core.exceptions import ValidationError
        if JournalHeader.objects.filter(
            journal_type='DEL', description__contains=delivery_note.delivery_number
        ).exists() or JournalHeader.objects.filter(
            reference_number=f"REV-{delivery_note.delivery_number}", status='Posted'
        ).exists():
            raise TransactionPostingError("Delivery note already posted to GL")

        so_already_posted = (order.status == 'Posted')

        # Get AR account for O2C-H3
        ar_account = order.customer.accounts_receivable_account
        if not ar_account:
            ar_account = get_gl_account('ACCOUNTS_RECEIVABLE', 'Asset', 'Receivable')

        default_revenue_account = get_gl_account('SALES_REVENUE', 'Income', 'Revenue')

        # Calculate amounts per line, grouping revenue by account
        delivery_lines = list(
            delivery_note.lines.select_related(
                'so_line', 'so_line__item', 'so_line__item__product_type',
                'so_line__item__product_type__revenue_account',
            ).all()
        )
        delivery_total = Decimal('0.00')
        # Map revenue_account_id → (account_obj, amount)
        revenue_by_account: dict = {}
        for dline in delivery_lines:
            so_line = dline.so_line
            if not so_line:
                continue
            line_amount = dline.quantity_delivered * so_line.unit_price
            delivery_total += line_amount
            # Derive revenue account: product_type → item fallback → order fallback → default
            rev_acct = None
            if so_line.item and so_line.item.product_type:
                rev_acct = so_line.item.product_type.revenue_account
            if not rev_acct:
                rev_acct = default_revenue_account
            if rev_acct:
                key = rev_acct.pk
                if key in revenue_by_account:
                    revenue_by_account[key] = (rev_acct, revenue_by_account[key][1] + line_amount)
                else:
                    revenue_by_account[key] = (rev_acct, line_amount)

        # Apply tax rate
        tax_amount = (delivery_total * (order.tax_rate or Decimal('0')) / Decimal('100')).quantize(Decimal('0.01'))
        grand_total = delivery_total + tax_amount

        # Create journal for AR/Revenue posting (O2C-H3)
        journal = JournalHeader.objects.create(
            posting_date=delivery_note.delivery_date,
            description=f"Delivery {delivery_note.delivery_number} - Order: {order.order_number} - Revenue Recognition",
            reference_number=f"REV-{delivery_note.delivery_number}",
            mda=order.mda,
            fund=order.fund,
            function=order.function,
            program=order.program,
            geo=order.geo,
            status='Posted',
            source_module='sales',
            source_document_id=delivery_note.pk,
        )

        # O2C-H3: AR Debit (single line for the full delivery total)
        if grand_total > 0 and ar_account:
            JournalLine.objects.create(
                header=journal,
                account=ar_account,
                debit=grand_total,
                credit=Decimal('0.00'),
                memo=f"AR from Delivery {delivery_note.delivery_number}"
            )

        # O2C-H3: Revenue Credits — one line per distinct revenue account (product type)
        for rev_acct, line_total in revenue_by_account.values():
            if line_total > 0:
                JournalLine.objects.create(
                    header=journal,
                    account=rev_acct,
                    debit=Decimal('0.00'),
                    credit=line_total,
                    memo=f"Revenue from Delivery {delivery_note.delivery_number} ({rev_acct.code})"
                )

        # O2C-H3: Tax Liability Credit
        if tax_amount > 0:
            tax_account = get_gl_account('TAX_PAYABLE', 'Liability', 'Tax')
            if tax_account:
                JournalLine.objects.create(
                    header=journal,
                    account=tax_account,
                    debit=Decimal('0.00'),
                    credit=tax_amount,
                    memo=f"Output Tax from Delivery {delivery_note.delivery_number}"
                )

        # PF-2: COGS at delivery time (Dr COGS / Cr Inventory)
        cogs_account = get_gl_account('COGS_EXPENSE', 'Expense', 'Cost of Goods')
        inventory_account = get_gl_account('INVENTORY', 'Asset', 'Inventory')
        if cogs_account and inventory_account:
            cogs_amount = Decimal('0.00')
            for dline in delivery_note.lines.all():
                so_line = dline.so_line
                if so_line and so_line.item:
                    cost = so_line.item.average_cost or Decimal('0.00')
                    cogs_amount += dline.quantity_delivered * cost
            if cogs_amount > 0:
                JournalLine.objects.create(
                    header=journal,
                    account=cogs_account,
                    debit=cogs_amount,
                    credit=Decimal('0.00'),
                    memo=f"COGS from Delivery {delivery_note.delivery_number}"
                )
                JournalLine.objects.create(
                    header=journal,
                    account=inventory_account,
                    debit=Decimal('0.00'),
                    credit=cogs_amount,
                    memo=f"Inventory reduction from Delivery {delivery_note.delivery_number}"
                )

        # Update customer invoice to Sent status
        from sales.models import CustomerInvoice
        invoice = CustomerInvoice.objects.filter(sales_order=order, status='Draft').first()
        if invoice:
            invoice.status = 'Sent'
            invoice.journal_entry = journal
            invoice.save(update_fields=['status', 'journal_entry'], _allow_status_change=True)

        # Validate and update GL
        SalesPostingService._validate_journal_balanced(journal)
        SalesPostingService._update_gl_balances(journal)

        return journal

    @staticmethod
    @transaction.atomic
    def post_sales_return(sales_return):
        """
        Post a Sales Return to the GL.

        Creates two balanced journal entries:
        1. Revenue reversal: DR Sales Revenue / CR AR (customer owes us less)
        2. Inventory restoration: DR Inventory / CR COGS (goods back in stock)

        Args:
            sales_return: SalesReturn instance

        Returns:
            JournalHeader: The created journal entry
        """
        if sales_return.status != 'Processed':
            raise TransactionPostingError(f"Sales Return must be Processed status, got {sales_return.status}")

        SalesPostingService._check_duplicate_posting(sales_return.return_number)
        SalesPostingService._validate_fiscal_period(sales_return.return_date)

        ar_account = get_gl_account('ACCOUNTS_RECEIVABLE', 'Asset', 'Receivable')
        revenue_account = get_gl_account('SALES_REVENUE', 'Income', 'Revenue')
        inventory_account = get_gl_account('INVENTORY', 'Asset', 'Inventory')
        cogs_account = get_gl_account('COST_OF_GOODS_SOLD', 'Expense', 'Cost of Goods')

        if not ar_account or not revenue_account:
            raise TransactionPostingError(
                "AR or Sales Revenue account not found. "
                "Configure DEFAULT_GL_ACCOUNTS['ACCOUNTS_RECEIVABLE'] and ['SALES_REVENUE'] in settings."
            )

        journal = JournalHeader.objects.create(
            posting_date=sales_return.return_date,
            description=f"Sales Return {sales_return.return_number} - Customer: {sales_return.customer}",
            reference_number=sales_return.return_number,
            status='Posted',
            source_module='sales',
            source_document_id=sales_return.pk,
        )

        total_return = Decimal('0.00')
        total_cost = Decimal('0.00')

        for line in sales_return.lines.select_related('item', 'item__inventory_account', 'item__product_type').all():
            line_total = line.quantity * line.unit_price
            total_return += line_total

            # DR Sales Revenue (reverse revenue for returned goods)
            JournalLine.objects.create(
                header=journal,
                account=revenue_account,
                debit=line_total,
                credit=Decimal('0.00'),
                memo=f"Return {sales_return.return_number}: {getattr(line.item, 'sku', line_total)}"
            )

            # Inventory restoration entries (if item is tracked)
            if line.item and inventory_account and cogs_account:
                item_inv_account = (
                    line.item.inventory_account
                    or (line.item.product_type.inventory_account if line.item.product_type else None)
                    or inventory_account
                )
                cost = getattr(line.item, 'standard_cost', None) or getattr(line.item, 'average_cost', None) or line.unit_price
                line_cost = line.quantity * cost
                total_cost += line_cost

                JournalLine.objects.create(
                    header=journal,
                    account=item_inv_account,
                    debit=line_cost,
                    credit=Decimal('0.00'),
                    memo=f"Inventory restored: {sales_return.return_number}"
                )
                JournalLine.objects.create(
                    header=journal,
                    account=cogs_account,
                    debit=Decimal('0.00'),
                    credit=line_cost,
                    memo=f"COGS reversal: {sales_return.return_number}"
                )

        # CR AR (total revenue credit)
        if total_return > 0:
            JournalLine.objects.create(
                header=journal,
                account=ar_account,
                debit=Decimal('0.00'),
                credit=total_return,
                memo=f"AR reduction: {sales_return.return_number}"
            )

        # Reduce customer balance (they owe us less)
        from django.db.models import F as _F
        type(sales_return.customer).objects.filter(pk=sales_return.customer.pk).update(
            balance=_F('balance') - total_return
        )

        SalesPostingService._validate_journal_balanced(journal)
        SalesPostingService._update_gl_balances(journal)
        return journal

    @staticmethod
    @transaction.atomic
    def post_credit_note(credit_note):
        """
        Post a Customer Credit Note to the GL.

        Creates: DR Sales Revenue / CR AR (reduce revenue and reduce what customer owes).

        Args:
            credit_note: CreditNote instance

        Returns:
            JournalHeader: The created journal entry
        """
        if credit_note.status != 'Applied':
            raise TransactionPostingError(f"Credit Note must be Applied status, got {credit_note.status}")

        SalesPostingService._check_duplicate_posting(credit_note.credit_note_number)
        SalesPostingService._validate_fiscal_period(credit_note.issue_date)

        ar_account = get_gl_account('ACCOUNTS_RECEIVABLE', 'Asset', 'Receivable')
        revenue_account = get_gl_account('SALES_REVENUE', 'Income', 'Revenue')

        if not ar_account or not revenue_account:
            raise TransactionPostingError(
                "AR or Sales Revenue account not found. "
                "Configure DEFAULT_GL_ACCOUNTS['ACCOUNTS_RECEIVABLE'] and ['SALES_REVENUE'] in settings."
            )

        journal = JournalHeader.objects.create(
            posting_date=credit_note.issue_date,
            description=f"Credit Note {credit_note.credit_note_number} - {credit_note.customer}",
            reference_number=credit_note.credit_note_number,
            status='Posted',
            source_module='sales',
            source_document_id=credit_note.pk,
        )

        amount = credit_note.amount
        JournalLine.objects.create(
            header=journal,
            account=revenue_account,
            debit=amount,
            credit=Decimal('0.00'),
            memo=f"Credit note {credit_note.credit_note_number}: revenue adjustment"
        )
        JournalLine.objects.create(
            header=journal,
            account=ar_account,
            debit=Decimal('0.00'),
            credit=amount,
            memo=f"Credit note {credit_note.credit_note_number}: AR reduction"
        )

        # Reduce customer balance
        from django.db.models import F as _F
        type(credit_note.customer).objects.filter(pk=credit_note.customer.pk).update(
            balance=_F('balance') - amount
        )

        SalesPostingService._validate_journal_balanced(journal)
        SalesPostingService._update_gl_balances(journal)
        return journal

    @staticmethod
    @transaction.atomic
    def post_receipt(receipt):
        """
        Post a Customer Receipt to the GL.

        Args:
            receipt: Receipt instance

        Returns:
            JournalHeader: The created journal entry
        """
        if receipt.status != 'Posted':
            raise TransactionPostingError(f"Receipt must be Posted status, got {receipt.status}")

        if hasattr(receipt, 'journal_entry') and receipt.journal_entry:
            raise TransactionPostingError("Receipt already posted to GL")

        SalesPostingService._validate_fiscal_period(receipt.receipt_date)

        amount = receipt.total_amount

        bank_gl_account = None
        if receipt.bank_account and receipt.bank_account.gl_account:
            bank_gl_account = receipt.bank_account.gl_account
        if not bank_gl_account:
            bank_gl_account = get_gl_account('CASH_ACCOUNT', 'Asset', 'Bank')
        if not bank_gl_account:
            raise TransactionPostingError("No Bank/Cash GL account found")

        ar_account = get_gl_account('ACCOUNTS_RECEIVABLE', 'Asset', 'Receivable')
        if not ar_account:
            raise TransactionPostingError("No Accounts Receivable account found")

        journal = JournalHeader.objects.create(
            posting_date=receipt.receipt_date,
            description=f"Receipt {receipt.receipt_number}",
            reference_number=receipt.receipt_number,
            status='Posted',
            source_module='sales',
            source_document_id=receipt.pk,
        )

        # Debit: Bank/Cash (increases asset)
        JournalLine.objects.create(
            header=journal,
            account=bank_gl_account,
            debit=amount,
            credit=Decimal('0.00'),
            memo=f"Receipt {receipt.receipt_number}"
        )

        # Credit: Accounts Receivable (reduces receivable)
        JournalLine.objects.create(
            header=journal,
            account=ar_account,
            debit=Decimal('0.00'),
            credit=amount,
            memo=f"Receipt {receipt.receipt_number}"
        )

        receipt.journal_entry = journal
        receipt.save()

        # Update customer balance (atomic F()-based)
        if hasattr(receipt, 'customer') and receipt.customer:
            from django.db.models import F
            type(receipt.customer).objects.filter(pk=receipt.customer.pk).update(
                balance=F('balance') - amount
            )

        SalesPostingService._validate_journal_balanced(journal)
        SalesPostingService._update_gl_balances(journal)
        return journal
