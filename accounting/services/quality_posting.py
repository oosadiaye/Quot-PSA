"""
Quality Posting Service — accounting domain.

Handles GL posting for all quality-control transactions:
Quality Inspections and Non-Conformance Reports.
"""

import logging
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from accounting.models import JournalHeader, JournalLine
from accounting.services.base_posting import BasePostingService, TransactionPostingError, get_gl_account

logger = logging.getLogger(__name__)


class QualityPostingService(BasePostingService):
    """
    GL posting service for the Quality domain.
    """

    @staticmethod
    @transaction.atomic
    def post_quality_inspection(inspection):
        """
        Post a Quality Inspection to the GL.

        Creates journal entry for rejected items:
        - Quality Control Expense (debit)
        - Inventory/WIP (credit)

        Args:
            inspection: QualityInspection instance
        """
        if inspection.status != 'Completed':
            raise TransactionPostingError("Inspection must be completed before posting")

        posting_date = inspection.inspection_date or timezone.now().date()
        QualityPostingService._validate_fiscal_period(posting_date)

        rejected_count = inspection.lines.filter(result='Fail').count()
        if rejected_count == 0:
            logger.info(f"QC {inspection.inspection_number}: no failed lines, skipping GL posting")
            return None

        # Calculate cost from item if available
        cost_amount = Decimal('0.00')
        if inspection.item:
            unit_cost = getattr(inspection.item, 'average_cost', None) or Decimal('0.00')
            cost_amount = unit_cost * rejected_count

        if cost_amount <= 0:
            logger.warning(f"QC {inspection.inspection_number}: no cost calculable, skipping GL posting")
            return None

        # Resolve QC expense: per-inspection FK override → DEFAULT_GL_ACCOUNTS fallback
        qc_expense = (
            (inspection.qc_expense_account_id and inspection.qc_expense_account)
            or get_gl_account('QC_EXPENSE', 'Expense', 'Quality Control')
        )
        if not qc_expense:
            raise TransactionPostingError("Quality control expense account not found")

        inventory_account = get_gl_account('INVENTORY', 'Asset', 'Inventory')
        if not inventory_account:
            raise TransactionPostingError("Inventory account not found")

        journal = JournalHeader.objects.create(
            reference_number=f"QC-{inspection.inspection_number}",
            description=f"Quality Inspection: {inspection.inspection_number}",
            posting_date=inspection.inspection_date or timezone.now().date(),
            status='Posted',
            source_module='quality',
            source_document_id=inspection.pk,
            posted_at=timezone.now(),
        )

        JournalLine.objects.create(
            header=journal,
            account=qc_expense,
            debit=cost_amount,
            credit=Decimal('0.00'),
            memo=f"QC Cost: {rejected_count} rejected items"
        )

        JournalLine.objects.create(
            header=journal,
            account=inventory_account,
            debit=Decimal('0.00'),
            credit=cost_amount,
            memo=f"Rejected Items: {rejected_count}"
        )

        QualityPostingService._validate_journal_balanced(journal)
        QualityPostingService._update_gl_balances(journal)
        return journal

    @staticmethod
    @transaction.atomic
    def post_non_conformance(ncr):
        """
        Post a Non-Conformance Report to the GL.

        Creates journal entry for:
        - Scrap/Write-off Expense (debit)
        - Inventory (credit)

        Args:
            ncr: NonConformance instance
        """
        posting_date = ncr.closed_date or timezone.now().date()
        QualityPostingService._validate_fiscal_period(posting_date)

        if ncr.status != 'Closed':
            raise TransactionPostingError("NCR must be closed before posting")

        # Duplicate posting prevention
        if JournalHeader.objects.filter(reference_number=f"NCR-{ncr.ncr_number}").exists():
            raise TransactionPostingError("NCR already posted to GL")

        # Calculate actual cost from related inspection item
        cost_amount = Decimal('0.00')
        if ncr.related_inspection and ncr.related_inspection.item:
            unit_cost = getattr(ncr.related_inspection.item, 'average_cost', None) or Decimal('0.00')
            rejected_count = ncr.related_inspection.lines.filter(result='Fail').count() or 1
            cost_amount = unit_cost * rejected_count

        if cost_amount <= 0:
            logger.warning(f"NCR {ncr.ncr_number}: no cost calculable from related inspection, skipping GL posting")
            return None

        scrap_expense = get_gl_account('SCRAP_EXPENSE', 'Expense', 'Scrap')
        if not scrap_expense:
            raise TransactionPostingError("Scrap expense account not found")

        inventory_account = get_gl_account('INVENTORY', 'Asset', 'Inventory')
        if not inventory_account:
            raise TransactionPostingError("Inventory account not found")

        journal = JournalHeader.objects.create(
            reference_number=f"NCR-{ncr.ncr_number}",
            description=f"NCR: {ncr.title}",
            posting_date=ncr.closed_date or timezone.now().date(),
            status='Posted',
            source_module='quality',
            source_document_id=ncr.pk,
            posted_at=timezone.now(),
        )

        JournalLine.objects.create(
            header=journal,
            account=scrap_expense,
            debit=cost_amount,
            credit=Decimal('0.00'),
            memo=f"NCR Cost: {ncr.ncr_number}"
        )

        JournalLine.objects.create(
            header=journal,
            account=inventory_account,
            debit=Decimal('0.00'),
            credit=cost_amount,
            memo="Inventory Write-off"
        )

        QualityPostingService._validate_journal_balanced(journal)
        QualityPostingService._update_gl_balances(journal)
        return journal
