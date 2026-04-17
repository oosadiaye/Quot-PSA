"""
Procurement Posting Service — accounting domain.

Handles GL posting for all purchase-cycle transactions:
Purchase Orders, Goods Received Notes, Vendor Invoices, Payments,
Purchase Returns, Vendor Credit Notes, and Vendor Debit Notes.
"""

import logging
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from accounting.models import JournalHeader, JournalLine, Account
from accounting.services.base_posting import BasePostingService, TransactionPostingError, get_gl_account

logger = logging.getLogger(__name__)


class ProcurementPostingService(BasePostingService):
    """
    GL posting service for the Procurement domain.
    """

    @staticmethod
    @transaction.atomic
    def post_purchase_order(po):
        """
        Post a Purchase Order to the GL.

        Creates journal entry for:
        - Inventory/Asset (debit)
        - Accounts Payable (credit)

        Args:
            po: PurchaseOrder instance

        Returns:
            JournalHeader: The created journal entry
        """
        if po.status != 'Posted':
            raise TransactionPostingError(f"PO must be Posted status, got {po.status}")

        ProcurementPostingService._check_duplicate_posting(po.po_number)
        ProcurementPostingService._validate_fiscal_period(po.order_date)

        if po.lines.count() == 0:
            raise TransactionPostingError("PO has no lines")

        total_amount = po.subtotal
        tax_amount = po.tax_amount
        grand_total = total_amount + tax_amount

        # Get AP account from configured defaults
        ap_account = get_gl_account('ACCOUNTS_PAYABLE', 'Liability', 'Payable')
        if not ap_account:
            raise TransactionPostingError(
                "No Accounts Payable account found. "
                "Configure DEFAULT_GL_ACCOUNTS['ACCOUNTS_PAYABLE'] in settings."
            )

        # Create journal header
        journal = JournalHeader.objects.create(
            posting_date=po.order_date,
            description=f"Purchase Order {po.po_number} - Vendor: {po.vendor.name}",
            reference_number=po.po_number,
            mda=po.mda,
            fund=po.fund,
            function=po.function,
            program=po.program,
            geo=po.geo,
            status='Posted',
            source_module='procurement',
            source_document_id=po.pk,
        )

        # Inventory/Asset Debit
        if total_amount > 0:
            # Group by account
            account_totals = {}
            for line in po.lines.all():
                inventory_account = line.item.inventory_account if line.item else None
                if not inventory_account and line.product_type:
                    inventory_account = line.product_type.inventory_account

                if not inventory_account:
                    # Use configured default inventory account
                    inventory_account = get_gl_account('INVENTORY', 'Asset', 'Inventory')

                if inventory_account.id not in account_totals:
                    account_totals[inventory_account.id] = {
                        'account': inventory_account,
                        'amount': Decimal('0.00')
                    }

                line_total = line.quantity * line.unit_price
                account_totals[inventory_account.id]['amount'] += line_total

            for acc_data in account_totals.values():
                JournalLine.objects.create(
                    header=journal,
                    account=acc_data['account'],
                    debit=acc_data['amount'],
                    credit=Decimal('0.00'),
                    memo=f"PO {po.po_number}"
                )

        # AP Credit (full amount including tax)
        if grand_total > 0:
            JournalLine.objects.create(
                header=journal,
                account=ap_account,
                debit=Decimal('0.00'),
                credit=grand_total,
                memo=f"AP from PO {po.po_number}"
            )

        # Tax Liability Debit (if tax amount)
        if tax_amount > 0:
            tax_account = get_gl_account('TAX_PAYABLE', 'Liability', 'Tax')
            if tax_account:
                JournalLine.objects.create(
                    header=journal,
                    account=tax_account,
                    debit=tax_amount,
                    credit=Decimal('0.00'),
                    memo=f"Input Tax from PO {po.po_number}"
                )

        # Update vendor balance (atomic F()-based)
        if hasattr(po, 'vendor') and po.vendor:
            from django.db.models import F
            type(po.vendor).objects.filter(pk=po.vendor.pk).update(
                balance=F('balance') + grand_total
            )

        # Validate journal is balanced before GL update
        ProcurementPostingService._validate_journal_balanced(journal)

        # Update GL balances
        ProcurementPostingService._update_gl_balances(journal)

        # ── Commitment link: safety net in case the Approved-status hook
        # was bypassed (e.g. legacy data migrated into 'Posted' directly).
        # ``create_commitment_for_po`` is idempotent — if a link already
        # exists it just refreshes the committed amount.
        #
        # S1-10 — ``BudgetExceededError`` MUST propagate so the PO post
        # fails when the appropriation ceiling would be breached. The old
        # blanket ``except Exception: log.warning`` swallowed this error
        # and silently allowed over-commitment. We now let the ceiling
        # error bubble up while still tolerating non-critical failures
        # (missing NCoA bridges, etc.) so the GL post isn't aborted by
        # a configuration issue.
        try:
            create_commitment_for_po(po, grand_total)
        except Exception as exc:
            # Ceiling breaches MUST abort posting.
            from budget.services import BudgetExceededError
            if isinstance(exc, BudgetExceededError):
                raise
            import logging
            logging.getLogger(__name__).warning(
                "Failed to create ProcurementBudgetLink for PO %s: %s",
                po.po_number, exc,
            )

        return journal

    @staticmethod
    def _create_budget_commitment(po, committed_amount):
        """Deprecated alias — delegates to ``procurement_commitments.create_commitment_for_po``.

        Kept for backward compatibility with the GL-posting call site.
        New callers (e.g. the PO model's status-transition hook) should
        use ``create_commitment_for_po`` from the commitments module
        directly so the same logic runs for any "Approved" → commitment
        trigger, not only "Posted" → GL entry.
        """
        from accounting.services.procurement_commitments import create_commitment_for_po
        return create_commitment_for_po(po, committed_amount)

    # NOTE: Commitment helpers (create_commitment_for_po,
    # cancel_commitment_for_po, mark_commitment_invoiced_for_po) live in
    # ``accounting/services/procurement_commitments.py`` so model save()
    # hooks can import them without pulling in the whole service class.

    @staticmethod
    @transaction.atomic
    def post_goods_received_note(grn):
        """
        Post a Goods Received Note to the GL — IPSAS three-way match.

        P2P accounting logic:

        - **PO Posted first** (legacy/inventoried path): DR Inventory / CR AP
          was already recorded at PO posting. GRN here only confirms physical
          receipt — no additional GL entry. Returns ``None``.

        - **PO not yet Posted** (canonical 3-way match):
            * DR Expense / Asset / Inventory  (per po_line — see priority below)
            * CR GR/IR Clearing                                  (liability)

          Debit-account priority per line:
            1. Inventoriable item  → ``item.inventory_account``
                                     → ``product_type.inventory_account``
                                     → ``DEFAULT_GL_ACCOUNTS['INVENTORY']``
            2. Fixed asset PO line → ``po_line.asset.gl_account``
            3. Service / direct expense → ``po_line.account`` (always set)

        The credit (GR/IR Clearing) is parked until the vendor invoice clears
        it via ``post_vendor_invoice`` — at which point AP is recognised and
        the budget commitment moves INVOICED → CLOSED.

        Args:
            grn: GoodsReceivedNote instance (must be in 'Posted' status)

        Returns:
            JournalHeader or None
        """
        if grn.status != 'Posted':
            raise TransactionPostingError(f"GRN must be Posted status, got {grn.status}")

        ProcurementPostingService._check_duplicate_posting(grn.grn_number)
        ProcurementPostingService._validate_fiscal_period(grn.received_date)

        po = grn.purchase_order

        if po.status == 'Posted':
            # Inventory and AP were already recognised when the PO was posted.
            # GRN confirms physical receipt only — no GL entry required.
            return None

        # PO was not yet posted — GRN is the first accounting entry for this purchase.
        # 3-way match: DR Inventory / CR GR/IR Clearing (NOT AP directly).
        # AP is recognised only when the vendor invoice is matched and posted.
        grn_ir_account = get_gl_account('GOODS_RECEIPT_CLEARING', 'Liability', 'GR/IR')
        if not grn_ir_account:
            raise TransactionPostingError(
                "GR/IR Clearing account not found. "
                "Configure DEFAULT_GL_ACCOUNTS['GOODS_RECEIPT_CLEARING'] in settings "
                "and ensure account 20600000 exists in the Chart of Accounts."
            )

        journal = JournalHeader.objects.create(
            posting_date=grn.received_date,
            description=f"GRN {grn.grn_number} - PO: {po.po_number}",
            reference_number=grn.grn_number,
            mda=po.mda,
            fund=po.fund,
            function=po.function,
            program=po.program,
            geo=po.geo,
            status='Posted',
            source_module='procurement',
            source_document_id=grn.pk,
        )

        # IPSAS three-way match — debit side selection priority:
        #   1. Inventoriable items: DR Inventory account (item.inventory_account
        #      → product_type.inventory_account → DEFAULT_GL_ACCOUNTS['INVENTORY'])
        #   2. Fixed-asset POs: DR the asset's GL account (capitalised on receipt)
        #   3. Service / direct-expense lines: DR po_line.account (the expense
        #      account chosen when the PO line was raised)
        # In all three cases we credit GR/IR Clearing — the liability that
        # parks the value until the vendor invoice clears it.
        total_received = Decimal('0.00')
        skipped_lines = []
        for grn_line in grn.lines.all():
            po_line = grn_line.po_line
            if not po_line:
                skipped_lines.append(grn_line.pk)
                continue

            quantity = grn_line.quantity_received
            unit_cost = po_line.unit_price
            line_total = quantity * unit_cost
            if line_total <= 0:
                continue

            # Resolve debit account — see priority order above.
            debit_account = None
            memo_label = po_line.item_description or 'Goods/Services'

            if po_line.item:
                item = po_line.item
                debit_account = item.inventory_account
                if not debit_account and item.product_type:
                    debit_account = item.product_type.inventory_account
                if not debit_account:
                    debit_account = get_gl_account('INVENTORY', 'Asset', 'Inventory')
                memo_label = f"{item.sku} x {quantity}"
            elif po_line.asset and getattr(po_line.asset, 'gl_account', None):
                debit_account = po_line.asset.gl_account
                memo_label = f"FA {po_line.asset} x {quantity}"

            # Fall back to the PO line's chosen GL account (always set — see
            # PurchaseOrderLine.account = ForeignKey(Account, on_delete=PROTECT)).
            if not debit_account:
                debit_account = po_line.account

            if not debit_account:
                # Should be unreachable, but keep the journal balanced rather
                # than silently posting an asymmetric entry.
                skipped_lines.append(grn_line.pk)
                continue

            total_received += line_total
            JournalLine.objects.create(
                header=journal,
                account=debit_account,
                debit=line_total,
                credit=Decimal('0.00'),
                memo=f"GRN {grn.grn_number}: {memo_label}",
            )

        # Credit GR/IR Clearing (3-way match — AP recognised at invoice matching).
        # The credit total equals the sum of debits to keep the journal balanced.
        if total_received > 0:
            JournalLine.objects.create(
                header=journal,
                account=grn_ir_account,
                debit=Decimal('0.00'),
                credit=total_received,
                memo=f"GR/IR Clearing from GRN {grn.grn_number}",
            )

        if skipped_lines:
            import logging
            logging.getLogger(__name__).warning(
                "GRN %s posted but %d line(s) had no resolvable debit account "
                "and were skipped: %s",
                grn.grn_number, len(skipped_lines), skipped_lines,
            )

        ProcurementPostingService._validate_journal_balanced(journal)
        ProcurementPostingService._update_gl_balances(journal)

        return journal

    @staticmethod
    @transaction.atomic
    def post_vendor_invoice(invoice):
        """
        Post a Vendor Invoice to the GL.

        Args:
            invoice: VendorInvoice instance

        Returns:
            JournalHeader: The created journal entry
        """
        if invoice.status not in ['Approved', 'Paid']:
            raise TransactionPostingError(f"Invoice must be Approved or Paid, got {invoice.status}")

        ProcurementPostingService._check_duplicate_posting(invoice.invoice_number)
        ProcurementPostingService._validate_fiscal_period(invoice.invoice_date)

        journal = JournalHeader.objects.create(
            posting_date=invoice.invoice_date,
            description=f"Vendor Invoice {invoice.invoice_number}",
            reference_number=invoice.invoice_number,
            mda=invoice.mda,
            fund=invoice.fund,
            function=invoice.function,
            program=invoice.program,
            geo=invoice.geo,
            status='Posted',
            source_module='procurement',
            source_document_id=invoice.pk,
        )

        # 3-way match: if this invoice is linked to a GRN (via a PO that was NOT pre-posted),
        # debit GR/IR Clearing to clear it and credit AP. If there's no GRN link (direct
        # invoice) debit the expense/inventory account directly and credit AP.
        grn_ir_account = get_gl_account('GOODS_RECEIPT_CLEARING', 'Liability', 'GR/IR')
        has_grn_match = (
            grn_ir_account is not None
            and invoice.purchase_order is not None
            and invoice.purchase_order.status != 'Posted'  # PO was not pre-posted → GRN created GR/IR
        )

        if has_grn_match:
            # DR GR/IR Clearing (clears the liability created at GRN time)
            if invoice.subtotal > 0:
                JournalLine.objects.create(
                    header=journal,
                    account=grn_ir_account,
                    debit=invoice.subtotal,
                    credit=Decimal('0.00'),
                    memo=f"GR/IR Clearing — Invoice {invoice.invoice_number}"
                )
        else:
            # Direct invoice (no prior GRN) — debit the expense/inventory account
            if invoice.subtotal > 0:
                expense_account = invoice.account
                if expense_account:
                    JournalLine.objects.create(
                        header=journal,
                        account=expense_account,
                        debit=invoice.subtotal,
                        credit=Decimal('0.00'),
                        memo=f"Invoice {invoice.invoice_number}"
                    )

        # Credit: Accounts Payable
        ap_account = get_gl_account('ACCOUNTS_PAYABLE', 'Liability', 'Payable')
        if not ap_account:
            raise TransactionPostingError(
                "Accounts Payable account not found. "
                "Configure DEFAULT_GL_ACCOUNTS['ACCOUNTS_PAYABLE'] in settings."
            )

        if invoice.total_amount > 0:
            JournalLine.objects.create(
                header=journal,
                account=ap_account,
                debit=Decimal('0.00'),
                credit=invoice.total_amount,
                memo=f"AP {invoice.invoice_number}"
            )

        # Tax handling
        if invoice.tax_amount > 0:
            tax_account = get_gl_account('TAX_PAYABLE', 'Liability', 'Tax')
            if tax_account:
                JournalLine.objects.create(
                    header=journal,
                    account=tax_account,
                    debit=invoice.tax_amount,
                    credit=Decimal('0.00'),
                    memo=f"Input Tax {invoice.invoice_number}"
                )

        # Withholding tax handling — compute from invoice lines
        wht_totals = {}  # {withholding_account_id: (account, amount)}
        for line in invoice.lines.all():
            if line.withholding_tax and line.withholding_tax.rate > 0:
                wht = line.withholding_tax
                wht_amount = (line.amount * wht.rate / Decimal('100')).quantize(Decimal('0.01'))
                wht_acct = wht.withholding_account
                if wht_acct:
                    if wht_acct.id not in wht_totals:
                        wht_totals[wht_acct.id] = (wht_acct, Decimal('0'))
                    acct, running = wht_totals[wht_acct.id]
                    wht_totals[wht_acct.id] = (acct, running + wht_amount)

        for acct_id, (acct, amount) in wht_totals.items():
            if amount > 0:
                JournalLine.objects.create(
                    header=journal,
                    account=acct,
                    debit=Decimal('0.00'),
                    credit=amount,
                    memo=f"WHT Liability {invoice.invoice_number}"
                )

        invoice.journal_entry = journal
        invoice.save()

        ProcurementPostingService._validate_journal_balanced(journal)
        ProcurementPostingService._update_gl_balances(journal)
        return journal

    @staticmethod
    @transaction.atomic
    def post_payment(payment):
        """
        Post a Payment to the GL.

        Args:
            payment: Payment instance

        Returns:
            JournalHeader: The created journal entry
        """
        if payment.status != 'Posted':
            raise TransactionPostingError(f"Payment must be Posted status, got {payment.status}")

        if hasattr(payment, 'journal_entry') and payment.journal_entry:
            raise TransactionPostingError("Payment already posted to GL")

        ProcurementPostingService._validate_fiscal_period(payment.payment_date)

        amount = payment.total_amount

        ap_account = get_gl_account('ACCOUNTS_PAYABLE', 'Liability', 'Payable')
        if not ap_account:
            raise TransactionPostingError("No Accounts Payable account found")

        bank_gl_account = None
        if payment.bank_account and payment.bank_account.gl_account:
            bank_gl_account = payment.bank_account.gl_account
        if not bank_gl_account:
            bank_gl_account = get_gl_account('CASH_ACCOUNT', 'Asset', 'Bank')
        if not bank_gl_account:
            raise TransactionPostingError("No Bank/Cash GL account found")

        journal = JournalHeader.objects.create(
            posting_date=payment.payment_date,
            description=f"Payment {payment.payment_number}",
            reference_number=payment.payment_number,
            status='Posted',
            source_module='procurement',
            source_document_id=payment.pk,
        )

        # Debit: Accounts Payable (reduces liability)
        JournalLine.objects.create(
            header=journal,
            account=ap_account,
            debit=amount,
            credit=Decimal('0.00'),
            memo=f"Payment {payment.payment_number}"
        )

        # Credit: Bank/Cash (reduces asset)
        JournalLine.objects.create(
            header=journal,
            account=bank_gl_account,
            debit=Decimal('0.00'),
            credit=amount,
            memo=f"Payment {payment.payment_number}"
        )

        payment.journal_entry = journal
        payment.save()

        # Update vendor balance (atomic F()-based)
        if hasattr(payment, 'vendor') and payment.vendor:
            from django.db.models import F
            type(payment.vendor).objects.filter(pk=payment.vendor.pk).update(
                balance=F('balance') - amount
            )

        ProcurementPostingService._validate_journal_balanced(journal)
        ProcurementPostingService._update_gl_balances(journal)
        return journal

    @staticmethod
    @transaction.atomic
    def post_purchase_return(purchase_return):
        """
        Post a Purchase Return to the GL.

        Creates journal entry for:
        - Accounts Payable (debit) — reduces what we owe vendor
        - Inventory (credit) — reduces inventory value

        Args:
            purchase_return: PurchaseReturn instance

        Returns:
            JournalHeader: The created journal entry
        """
        ap_account = Account.objects.filter(
            account_type='Liability',
            name__icontains='Payable'
        ).first()

        if not ap_account:
            raise TransactionPostingError("No Accounts Payable account found")

        journal = JournalHeader.objects.create(
            posting_date=purchase_return.return_date,
            description=f"Purchase Return {purchase_return.return_number} - {purchase_return.vendor.name}",
            reference_number=purchase_return.return_number,
            status='Posted',
            source_module='procurement',
            source_document_id=purchase_return.pk,
            posted_at=timezone.now(),
        )

        # Process each return line
        account_totals = {}
        for line in purchase_return.lines.all():
            line_total = line.quantity * line.unit_price

            inventory_account = None
            if line.item:
                inventory_account = line.item.inventory_account
                if not inventory_account and line.item.product_type:
                    inventory_account = line.item.product_type.inventory_account

            if not inventory_account:
                inventory_account = Account.objects.filter(
                    account_type='Asset',
                    name__icontains='Inventory'
                ).first()

            if inventory_account:
                acc_id = inventory_account.id
                if acc_id not in account_totals:
                    account_totals[acc_id] = {'account': inventory_account, 'amount': Decimal('0.00')}
                account_totals[acc_id]['amount'] += line_total

        total_return_amount = sum(d['amount'] for d in account_totals.values())

        # Debit AP (reduce payable)
        if total_return_amount > 0:
            JournalLine.objects.create(
                header=journal,
                account=ap_account,
                debit=total_return_amount,
                credit=Decimal('0.00'),
                memo=f"AP reversal: Return {purchase_return.return_number}"
            )

        # Credit Inventory accounts
        for acc_data in account_totals.values():
            JournalLine.objects.create(
                header=journal,
                account=acc_data['account'],
                debit=Decimal('0.00'),
                credit=acc_data['amount'],
                memo=f"Inventory return: {purchase_return.return_number}"
            )

        # Update vendor balance (atomic F()-based — reduce what we owe)
        if hasattr(purchase_return, 'vendor') and purchase_return.vendor and total_return_amount > 0:
            from django.db.models import F
            type(purchase_return.vendor).objects.filter(pk=purchase_return.vendor.pk).update(
                balance=F('balance') - total_return_amount
            )

        ProcurementPostingService._validate_journal_balanced(journal)
        ProcurementPostingService._update_gl_balances(journal)
        return journal

    @staticmethod
    @transaction.atomic
    def post_vendor_credit_note(credit_note):
        """
        Post a Vendor Credit Note to the GL.

        Creates journal entry for:
        - Accounts Payable (debit) — reduces what we owe vendor
        - Inventory/Expense (credit) — reduces inventory value or records cost reduction

        Args:
            credit_note: VendorCreditNote instance

        Returns:
            JournalHeader: The created journal entry
        """
        if credit_note.status not in ['Approved', 'Posted']:
            raise TransactionPostingError(f"Credit note must be Approved, got {credit_note.status}")

        ap_account = Account.objects.filter(
            account_type='Liability',
            name__icontains='Payable'
        ).first()

        if not ap_account:
            raise TransactionPostingError("No Accounts Payable account found")

        journal = JournalHeader.objects.create(
            posting_date=credit_note.credit_note_date,
            description=f"Vendor Credit Note {credit_note.credit_note_number} - {credit_note.vendor.name}",
            reference_number=credit_note.credit_note_number,
            status='Posted',
            source_module='procurement',
            source_document_id=credit_note.pk,
            posted_at=timezone.now(),
        )

        total_amount = credit_note.total_amount

        # Debit AP (reduce payable)
        JournalLine.objects.create(
            header=journal,
            account=ap_account,
            debit=total_amount,
            credit=Decimal('0.00'),
            memo=f"AP reduction: Credit Note {credit_note.credit_note_number}"
        )

        # Credit Inventory/Expense account
        inventory_account = None
        if credit_note.purchase_order:
            # Try to get inventory account from PO lines
            for line in credit_note.purchase_order.lines.all():
                if line.item and line.item.inventory_account:
                    inventory_account = line.item.inventory_account
                    break
                if line.product_type and line.product_type.inventory_account:
                    inventory_account = line.product_type.inventory_account
                    break

        if not inventory_account:
            inventory_account = Account.objects.filter(
                account_type='Asset',
                name__icontains='Inventory'
            ).first()

        if inventory_account:
            JournalLine.objects.create(
                header=journal,
                account=inventory_account,
                debit=Decimal('0.00'),
                credit=total_amount,
                memo=f"Credit Note {credit_note.credit_note_number}"
            )

        # Update vendor balance (atomic F()-based — reduce what we owe)
        if hasattr(credit_note, 'vendor') and credit_note.vendor:
            from django.db.models import F
            type(credit_note.vendor).objects.filter(pk=credit_note.vendor.pk).update(
                balance=F('balance') - total_amount
            )

        ProcurementPostingService._validate_journal_balanced(journal)
        ProcurementPostingService._update_gl_balances(journal)
        return journal

    @staticmethod
    @transaction.atomic
    def post_vendor_debit_note(debit_note):
        """
        Post a Vendor Debit Note to the GL.

        Creates journal entry for:
        - Expense/Inventory (debit) — additional charge
        - Accounts Payable (credit) — increases what we owe vendor

        Args:
            debit_note: VendorDebitNote instance

        Returns:
            JournalHeader: The created journal entry
        """
        if debit_note.status not in ['Approved', 'Posted']:
            raise TransactionPostingError(f"Debit note must be Approved, got {debit_note.status}")

        ap_account = Account.objects.filter(
            account_type='Liability',
            name__icontains='Payable'
        ).first()

        if not ap_account:
            raise TransactionPostingError("No Accounts Payable account found")

        journal = JournalHeader.objects.create(
            posting_date=debit_note.debit_note_date,
            description=f"Vendor Debit Note {debit_note.debit_note_number} - {debit_note.vendor.name}",
            reference_number=debit_note.debit_note_number,
            status='Posted',
            source_module='procurement',
            source_document_id=debit_note.pk,
            posted_at=timezone.now(),
        )

        total_amount = debit_note.total_amount

        # Debit Expense/Inventory account
        expense_account = None
        if debit_note.purchase_order:
            for line in debit_note.purchase_order.lines.all():
                if line.item and line.item.expense_account:
                    expense_account = line.item.expense_account
                    break
                if line.product_type and line.product_type.expense_account:
                    expense_account = line.product_type.expense_account
                    break

        if not expense_account:
            expense_account = Account.objects.filter(
                account_type='Expense',
                name__icontains='Purchase'
            ).first() or Account.objects.filter(
                account_type='Asset',
                name__icontains='Inventory'
            ).first()

        if expense_account:
            JournalLine.objects.create(
                header=journal,
                account=expense_account,
                debit=total_amount,
                credit=Decimal('0.00'),
                memo=f"Debit Note {debit_note.debit_note_number}"
            )

        # Credit AP (increase payable)
        JournalLine.objects.create(
            header=journal,
            account=ap_account,
            debit=Decimal('0.00'),
            credit=total_amount,
            memo=f"AP from Debit Note {debit_note.debit_note_number}"
        )

        # Update vendor balance (atomic F()-based — increase what we owe)
        if hasattr(debit_note, 'vendor') and debit_note.vendor:
            from django.db.models import F
            type(debit_note.vendor).objects.filter(pk=debit_note.vendor.pk).update(
                balance=F('balance') + total_amount
            )

        ProcurementPostingService._validate_journal_balanced(journal)
        ProcurementPostingService._update_gl_balances(journal)
        return journal
