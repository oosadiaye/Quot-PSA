"""
Production Posting Service — accounting domain.

Handles GL posting for all manufacturing/production transactions:
Production Orders, Material Issues, Material Receipts, and Work Orders.
"""

import logging
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from accounting.models import JournalHeader, JournalLine
from accounting.services.base_posting import BasePostingService, TransactionPostingError, get_gl_account

logger = logging.getLogger(__name__)


class ProductionPostingService(BasePostingService):
    """
    GL posting service for the Production domain.
    """

    @staticmethod
    @transaction.atomic
    def post_production_order(production_order):
        """
        Post a Production Order completion to the GL.

        Creates journal entry for:
        - Finished Goods (debit)
        - WIP Inventory (credit)
        - Labor Cost (debit)
        - Manufacturing Overhead (credit)

        Args:
            production_order: ProductionOrder instance
        """
        if production_order.status != 'Done':
            raise TransactionPostingError("Production order must be completed before posting")

        posting_date = production_order.end_date or timezone.now().date()
        ProductionPostingService._validate_fiscal_period(posting_date)

        # Resolve GL accounts: per-order FK override → DEFAULT_GL_ACCOUNTS fallback
        finished_goods = (
            (production_order.finished_goods_account_id and production_order.finished_goods_account)
            or get_gl_account('FINISHED_GOODS', 'Asset', 'Finished Goods')
        )
        wip_inventory = (
            (production_order.wip_account_id and production_order.wip_account)
            or get_gl_account('WIP_INVENTORY', 'Asset', 'Work in Process')
        )

        if not finished_goods:
            raise TransactionPostingError("Finished goods account not found")
        if not wip_inventory:
            raise TransactionPostingError("WIP inventory account not found")

        journal_number = f"MFG-{production_order.order_number}"

        journal = JournalHeader.objects.create(
            reference_number=journal_number,
            description=f"Production: {production_order.bom.item_name}",
            posting_date=production_order.end_date or timezone.now().date(),
            status='Posted',
            source_module='production',
            source_document_id=production_order.pk,
            posted_at=timezone.now(),
        )

        quantity = Decimal(str(production_order.quantity_produced or 0))
        unit_cost = Decimal(str(production_order.bom.standard_cost or 0))
        total_cost = quantity * unit_cost

        JournalLine.objects.create(
            header=journal,
            account=finished_goods,
            debit=total_cost,
            credit=Decimal('0.00'),
            memo=f"Finished Goods: {quantity} units"
        )

        JournalLine.objects.create(
            header=journal,
            account=wip_inventory,
            debit=Decimal('0.00'),
            credit=total_cost,
            memo="WIP Reduction"
        )

        total_labor_cost = Decimal('0.00')
        labor_account = get_gl_account('LABOR_EXPENSE', 'Expense', 'Labor')

        # Validate LABOR_EXPENSE account exists before iterating job cards,
        # so we fail early rather than silently omitting labor cost GL lines.
        labor_cards = list(production_order.job_cards.filter(status='Done'))
        has_labor = any(Decimal(str(jc.labor_cost or 0)) > 0 for jc in labor_cards)
        if has_labor and not labor_account:
            raise TransactionPostingError(
                "Labor Expense account not found. "
                "Configure LABOR_EXPENSE in DEFAULT_GL_ACCOUNTS."
            )

        for job_card in labor_cards:
            if labor_account and job_card.labor_cost > 0:
                labor_amount = Decimal(str(job_card.labor_cost))
                JournalLine.objects.create(
                    header=journal,
                    account=labor_account,
                    debit=labor_amount,
                    credit=Decimal('0.00'),
                    memo=f"Labor: {job_card.operation_name}"
                )
                total_labor_cost += labor_amount

        # Credit WIP for total labor to balance the journal
        if total_labor_cost > 0:
            JournalLine.objects.create(
                header=journal,
                account=wip_inventory,
                debit=Decimal('0.00'),
                credit=total_labor_cost,
                memo="WIP Labor Cost Release"
            )

        ProductionPostingService._validate_journal_balanced(journal)
        ProductionPostingService._update_gl_balances(journal)
        return journal

    @staticmethod
    @transaction.atomic
    def post_material_issue(material_issue):
        """
        Post Material Issue for production to the GL.

        Creates journal entry for:
        - WIP Inventory (debit)
        - Raw Materials (credit)

        Args:
            material_issue: MaterialIssue instance
        """
        ProductionPostingService._validate_fiscal_period(material_issue.issue_date)

        raw_materials = get_gl_account('RAW_MATERIALS', 'Asset', 'Raw Material')
        wip_inventory = get_gl_account('WIP_INVENTORY', 'Asset', 'Work in Process')

        if not raw_materials:
            raise TransactionPostingError("Raw materials account not found")
        if not wip_inventory:
            raise TransactionPostingError("WIP inventory account not found")

        journal_number = f"MI-{material_issue.id}"

        journal = JournalHeader.objects.create(
            reference_number=journal_number,
            description=f"Material Issue: {material_issue.production_order.order_number}",
            posting_date=material_issue.issue_date,
            status='Posted',
            source_module='production',
            source_document_id=material_issue.pk,
            posted_at=timezone.now(),
        )

        quantity = Decimal(str(material_issue.quantity_issued))
        unit_cost = Decimal(str(material_issue.bom_line.component.standard_cost or 0))
        total_cost = quantity * unit_cost

        JournalLine.objects.create(
            header=journal,
            account=wip_inventory,
            debit=total_cost,
            credit=Decimal('0.00'),
            memo="WIP Materials"
        )

        JournalLine.objects.create(
            header=journal,
            account=raw_materials,
            debit=Decimal('0.00'),
            credit=total_cost,
            memo="Raw Materials Consumed"
        )

        ProductionPostingService._validate_journal_balanced(journal)
        ProductionPostingService._update_gl_balances(journal)
        return journal

    @staticmethod
    @transaction.atomic
    def post_material_receipt(material_receipt):
        """
        Post Material Receipt (finished goods) to the GL.

        Creates journal entry for:
        - Finished Goods (debit)
        - WIP Inventory (credit)

        Args:
            material_receipt: MaterialReceipt instance
        """
        ProductionPostingService._validate_fiscal_period(material_receipt.receipt_date)

        finished_goods = get_gl_account('FINISHED_GOODS', 'Asset', 'Finished Goods')
        wip_inventory = get_gl_account('WIP_INVENTORY', 'Asset', 'Work in Process')

        if not finished_goods:
            raise TransactionPostingError("Finished goods account not found")
        if not wip_inventory:
            raise TransactionPostingError("WIP inventory account not found")

        journal_number = f"MR-{material_receipt.id}"

        journal = JournalHeader.objects.create(
            reference_number=journal_number,
            description=f"Material Receipt: {material_receipt.production_order.order_number}",
            posting_date=material_receipt.receipt_date,
            status='Posted',
            source_module='production',
            source_document_id=material_receipt.pk,
            posted_at=timezone.now(),
        )

        quantity = Decimal(str(material_receipt.quantity_received))
        unit_cost = Decimal(str(material_receipt.production_order.bom.standard_cost or 0))
        total_cost = quantity * unit_cost

        JournalLine.objects.create(
            header=journal,
            account=finished_goods,
            debit=total_cost,
            credit=Decimal('0.00'),
            memo=f"Finished Goods Receipt: {quantity} units"
        )

        JournalLine.objects.create(
            header=journal,
            account=wip_inventory,
            debit=Decimal('0.00'),
            credit=total_cost,
            memo="WIP Reduction - Goods Completed"
        )

        ProductionPostingService._validate_journal_balanced(journal)
        ProductionPostingService._update_gl_balances(journal)
        return journal

    @staticmethod
    @transaction.atomic
    def post_work_order(work_order):
        """
        Post a Service Work Order completion to the GL.

        Creates journal entry for:
        - Service Revenue (credit)
        - Work Order Cost (debit)

        Args:
            work_order: WorkOrder instance
        """
        if work_order.status != 'Completed':
            raise TransactionPostingError("Work order must be completed before posting")

        posting_date = work_order.completed_date or timezone.now().date()
        ProductionPostingService._validate_fiscal_period(posting_date)

        # Resolve GL accounts: per-work-order FK override → DEFAULT_GL_ACCOUNTS fallback
        revenue_account = (
            (work_order.service_revenue_account_id and work_order.service_revenue_account)
            or get_gl_account('SERVICE_REVENUE', 'Income', 'Service')
        )
        if not revenue_account:
            raise TransactionPostingError("Service revenue account not found")

        journal_number = f"WO-{work_order.work_order_number}"

        journal = JournalHeader.objects.create(
            reference_number=journal_number,
            description=f"Work Order: {work_order.title}",
            posting_date=work_order.completed_date or timezone.now().date(),
            status='Posted',
            source_module='production',
            source_document_id=work_order.pk,
            posted_at=timezone.now(),
        )

        total_cost = Decimal(str(work_order.total_cost or 0))

        if total_cost > 0:
            expense_account = (
                (work_order.service_expense_account_id and work_order.service_expense_account)
                or get_gl_account('SERVICE_EXPENSE', 'Expense', 'Service')
            )
            if not expense_account:
                raise TransactionPostingError(
                    "Service Expense account not found. "
                    "Configure SERVICE_EXPENSE in DEFAULT_GL_ACCOUNTS."
                )

            JournalLine.objects.create(
                header=journal,
                account=expense_account,
                debit=total_cost,
                credit=Decimal('0.00'),
                memo="Service Cost"
            )
            JournalLine.objects.create(
                header=journal,
                account=revenue_account,
                debit=Decimal('0.00'),
                credit=total_cost,
                memo=f"Work Order Revenue: {work_order.work_order_number}"
            )

        ProductionPostingService._validate_journal_balanced(journal)
        ProductionPostingService._update_gl_balances(journal)
        return journal
