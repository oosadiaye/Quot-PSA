"""
Inventory Posting Service — accounting domain.

Handles GL posting for all inventory transactions:
Stock Movements, Inter-Warehouse Transfer Dispatches and Receipts,
and Stock Reconciliations.
"""

import logging
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from accounting.models import JournalHeader, JournalLine, Account
from accounting.services.base_posting import BasePostingService, TransactionPostingError, get_gl_account

logger = logging.getLogger(__name__)


class InventoryPostingService(BasePostingService):
    """
    GL posting service for the Inventory domain.
    """

    @staticmethod
    def _resolve_transfer_accounts(movement):
        """
        Resolve the inventory account and Goods-in-Transit account for a transfer movement.
        Raises TransactionPostingError if either cannot be found.
        """
        from inventory.models import Item  # avoid circular import at module level
        item = movement.item

        inventory_account = item.inventory_account
        if not inventory_account and item.product_type:
            inventory_account = item.product_type.inventory_account
        if not inventory_account:
            raise TransactionPostingError(f"No inventory account configured for item '{item.sku}'.")

        git_account = None
        if item.product_type:
            git_account = item.product_type.goods_in_transit_account
        if not git_account:
            # Primary: look up via DEFAULT_GL_ACCOUNTS key (10500000 - Goods in Transit)
            git_account = get_gl_account('GOODS_IN_TRANSIT', 'Asset', 'Goods in Transit')
        if not git_account:
            # Secondary fallback: any active account whose name contains "Goods in Transit"
            git_account = Account.objects.filter(
                name__icontains='goods in transit', is_active=True
            ).first()
        if not git_account:
            raise TransactionPostingError(
                f"No Goods in Transit account found for item '{item.sku}'. "
                "Configure GOODS_IN_TRANSIT in DEFAULT_GL_ACCOUNTS or set one on the Product Type."
            )

        return inventory_account, git_account

    @staticmethod
    @transaction.atomic
    def post_stock_movement(movement):
        """
        Post a Stock Movement to the GL.

        Args:
            movement: StockMovement instance

        Returns:
            JournalHeader: The created journal entry
        """
        posting_date = timezone.now().date()
        InventoryPostingService._validate_fiscal_period(posting_date)

        item = movement.item
        quantity = movement.quantity
        unit_price = movement.unit_price
        amount = quantity * unit_price

        # Get accounts
        inventory_account = item.inventory_account
        if not inventory_account and item.product_type:
            inventory_account = item.product_type.inventory_account

        expense_account = item.expense_account
        if not expense_account and item.product_type:
            expense_account = item.product_type.expense_account

        if not inventory_account:
            raise TransactionPostingError(f"No inventory account for item {item.sku}")

        journal = JournalHeader.objects.create(
            posting_date=timezone.now().date(),
            description=f"Stock {movement.get_movement_type_display()} - {item.sku}",
            reference_number=movement.reference_number or f"SM-{movement.pk}",
            status='Posted',
            source_module='inventory',
            source_document_id=movement.pk,
            posted_at=timezone.now(),
        )

        if movement.movement_type == 'IN':
            # Inventory Debit
            JournalLine.objects.create(
                header=journal,
                account=inventory_account,
                debit=amount,
                credit=Decimal('0.00'),
                memo=f"Stock In: {item.sku}"
            )

            # Credit: AP or Cash
            if expense_account:
                JournalLine.objects.create(
                    header=journal,
                    account=expense_account,
                    debit=Decimal('0.00'),
                    credit=amount,
                    memo=f"Stock In: {item.sku}"
                )

        elif movement.movement_type == 'OUT':
            # Inventory Credit (reduction)
            JournalLine.objects.create(
                header=journal,
                account=inventory_account,
                debit=Decimal('0.00'),
                credit=amount,
                memo=f"Stock Out: {item.sku}"
            )

            # Debit: COGS or Expense
            if expense_account:
                JournalLine.objects.create(
                    header=journal,
                    account=expense_account,
                    debit=amount,
                    credit=Decimal('0.00'),
                    memo=f"COGS: {item.sku}"
                )

        elif movement.movement_type == 'ADJ':
            # Adjustment — direction depends on sign of quantity.
            # Positive qty (gain / stock increase): DR Inventory / CR Adjustment Income
            # Negative qty (loss / stock decrease): DR Shrinkage Expense / CR Inventory
            # Use dedicated DEFAULT_GL_ACCOUNTS keys so account resolution is
            # deterministic — no fragile name__icontains fallback searches.
            abs_amount = abs(amount)

            if amount >= Decimal('0.00'):
                # ── Gain: Inventory increases ──────────────────────────
                adj_income_account = (
                    get_gl_account('INVENTORY_ADJUSTMENT_INCOME', 'Income', 'Adjustment Income')
                )

                JournalLine.objects.create(
                    header=journal,
                    account=inventory_account,
                    debit=abs_amount,
                    credit=Decimal('0.00'),
                    memo=f"Inventory Gain Adjustment: {item.sku}"
                )
                if adj_income_account:
                    JournalLine.objects.create(
                        header=journal,
                        account=adj_income_account,
                        debit=Decimal('0.00'),
                        credit=abs_amount,
                        memo=f"Inventory Gain Adjustment: {item.sku}"
                    )
            else:
                # ── Loss: Inventory decreases (shrinkage/write-off) ────
                adj_expense_account = (
                    get_gl_account('INVENTORY_SHRINKAGE', 'Expense', 'Shrinkage')
                    or expense_account
                )

                if adj_expense_account:
                    JournalLine.objects.create(
                        header=journal,
                        account=adj_expense_account,
                        debit=abs_amount,
                        credit=Decimal('0.00'),
                        memo=f"Inventory Loss Adjustment: {item.sku}"
                    )
                JournalLine.objects.create(
                    header=journal,
                    account=inventory_account,
                    debit=Decimal('0.00'),
                    credit=abs_amount,
                    memo=f"Inventory Loss Adjustment: {item.sku}"
                )

        InventoryPostingService._validate_journal_balanced(journal)
        InventoryPostingService._update_gl_balances(journal)
        return journal

    @staticmethod
    @transaction.atomic
    def post_transfer_dispatch(movement):
        """
        GL Step 1 — Dispatch from source warehouse.

        Journal entry:
            DR  Goods in Transit          (clearing asset — goods leaving WH A)
            CR  Inventory Account / WH A  (source warehouse inventory relieved)

        The GIT account carries the value until Warehouse B calls post_transfer_receive().
        """
        InventoryPostingService._validate_fiscal_period(timezone.now().date())
        inventory_account, git_account = InventoryPostingService._resolve_transfer_accounts(movement)

        item   = movement.item
        amount = movement.quantity * movement.unit_price

        journal = JournalHeader.objects.create(
            posting_date=timezone.now().date(),
            description=(
                f"Transfer Dispatch – {item.sku} "
                f"from WH#{movement.warehouse_id} → WH#{movement.to_warehouse_id}"
            ),
            reference_number=movement.reference_number or f"TRF-D-{movement.pk}",
            status='Posted',
            source_module='inventory',
            source_document_id=movement.pk,
            posted_at=timezone.now(),
        )

        # DR: Goods in Transit (asset increases — goods are "in the air")
        JournalLine.objects.create(
            header=journal,
            account=git_account,
            debit=amount,
            credit=Decimal('0.00'),
            memo=f"Goods in Transit: {item.sku} qty={movement.quantity}",
        )
        # CR: Inventory at source warehouse (asset decreases)
        JournalLine.objects.create(
            header=journal,
            account=inventory_account,
            debit=Decimal('0.00'),
            credit=amount,
            memo=f"Transfer out of WH#{movement.warehouse_id}: {item.sku}",
        )

        InventoryPostingService._validate_journal_balanced(journal)
        InventoryPostingService._update_gl_balances(journal)
        return journal

    @staticmethod
    @transaction.atomic
    def post_transfer_receive(movement):
        """
        GL Step 2 — Receipt at destination warehouse.

        Journal entry:
            DR  Inventory Account / WH B  (destination warehouse inventory grows)
            CR  Goods in Transit          (clearing account zeroed out)

        After both steps the GIT account net = 0 for this transfer.
        """
        InventoryPostingService._validate_fiscal_period(timezone.now().date())
        inventory_account, git_account = InventoryPostingService._resolve_transfer_accounts(movement)

        item   = movement.item
        amount = movement.quantity * movement.unit_price

        journal = JournalHeader.objects.create(
            posting_date=timezone.now().date(),
            description=(
                f"Transfer Receive – {item.sku} "
                f"at WH#{movement.to_warehouse_id} (from WH#{movement.warehouse_id})"
            ),
            reference_number=(movement.reference_number or f"TRF-R-{movement.pk}"),
            status='Posted',
            source_module='inventory',
            source_document_id=movement.pk,
            posted_at=timezone.now(),
        )

        # DR: Inventory at destination warehouse (asset increases — goods received)
        JournalLine.objects.create(
            header=journal,
            account=inventory_account,
            debit=amount,
            credit=Decimal('0.00'),
            memo=f"Transfer received at WH#{movement.to_warehouse_id}: {item.sku}",
        )
        # CR: Goods in Transit (clearing account relieved)
        JournalLine.objects.create(
            header=journal,
            account=git_account,
            debit=Decimal('0.00'),
            credit=amount,
            memo=f"GIT cleared for {item.sku} qty={movement.quantity}",
        )

        InventoryPostingService._validate_journal_balanced(journal)
        InventoryPostingService._update_gl_balances(journal)
        return journal

    @staticmethod
    @transaction.atomic
    def post_stock_reconciliation(reconciliation):
        """
        Post Stock Reconciliation adjustments to the GL.

        Creates journal entries for inventory gains/losses:
        - Gain (physical > system): Debit Inventory, Credit Inventory Adjustment Income
        - Loss (physical < system): Debit Inventory Shrinkage Expense, Credit Inventory

        Args:
            reconciliation: StockReconciliation instance

        Returns:
            JournalHeader: The created journal entry
        """
        InventoryPostingService._validate_fiscal_period(reconciliation.reconciliation_date)

        lines_with_variance = [
            line for line in reconciliation.lines.all()
            if line.is_adjusted and line.variance_quantity != 0
        ]

        if not lines_with_variance:
            return None

        journal = JournalHeader.objects.create(
            posting_date=reconciliation.reconciliation_date,
            description=f"Stock Reconciliation {reconciliation.reconciliation_number}",
            reference_number=reconciliation.reconciliation_number,
            status='Posted',
            source_module='inventory',
            source_document_id=reconciliation.pk,
            posted_at=timezone.now(),
        )

        total_gains = Decimal('0.00')
        total_losses = Decimal('0.00')

        for line in lines_with_variance:
            item = line.item
            variance_value = abs(line.variance_value)

            inventory_account = item.inventory_account
            if not inventory_account and item.product_type:
                inventory_account = item.product_type.inventory_account
            if not inventory_account:
                inventory_account = Account.objects.filter(
                    account_type='Asset', name__icontains='Inventory'
                ).first()

            if not inventory_account:
                continue

            if line.variance_quantity > 0:
                # Gain: Debit Inventory, Credit Adjustment Income
                total_gains += variance_value
                JournalLine.objects.create(
                    header=journal,
                    account=inventory_account,
                    debit=variance_value,
                    credit=Decimal('0.00'),
                    memo=f"Inventory gain: {item.sku} (+{line.variance_quantity})"
                )
            else:
                # Loss: Credit Inventory
                total_losses += variance_value
                JournalLine.objects.create(
                    header=journal,
                    account=inventory_account,
                    debit=Decimal('0.00'),
                    credit=variance_value,
                    memo=f"Inventory loss: {item.sku} ({line.variance_quantity})"
                )

        # Credit side for gains — Inventory Adjustment Income
        if total_gains > 0:
            adj_income = Account.objects.filter(
                account_type='Income',
                name__icontains='Adjustment'
            ).first() or Account.objects.filter(
                account_type='Income'
            ).first()
            if adj_income:
                JournalLine.objects.create(
                    header=journal,
                    account=adj_income,
                    debit=Decimal('0.00'),
                    credit=total_gains,
                    memo=f"Inventory adjustment gain: {reconciliation.reconciliation_number}"
                )

        # Debit side for losses — Shrinkage/Adjustment Expense
        if total_losses > 0:
            shrinkage_expense = Account.objects.filter(
                account_type='Expense',
                name__icontains='Shrinkage'
            ).first() or Account.objects.filter(
                account_type='Expense',
                name__icontains='Adjustment'
            ).first() or Account.objects.filter(
                account_type='Expense'
            ).first()
            if shrinkage_expense:
                JournalLine.objects.create(
                    header=journal,
                    account=shrinkage_expense,
                    debit=total_losses,
                    credit=Decimal('0.00'),
                    memo=f"Inventory shrinkage: {reconciliation.reconciliation_number}"
                )

        InventoryPostingService._validate_journal_balanced(journal)
        InventoryPostingService._update_gl_balances(journal)
        return journal
