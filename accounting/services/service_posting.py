"""
Service Posting Service — accounting domain.

Handles GL posting for field service / helpdesk transactions:
Service Tickets.
"""

import logging
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from accounting.models import JournalHeader, JournalLine
from accounting.services.base_posting import BasePostingService, TransactionPostingError, get_gl_account

logger = logging.getLogger(__name__)


class ServicePostingService(BasePostingService):
    """
    GL posting service for the Service domain.
    """

    @staticmethod
    @transaction.atomic
    def post_service_ticket(ticket):
        """
        Post a Service Ticket resolution to the GL.

        Creates journal entry for:
        - Service Revenue (credit)
        - Accounts Receivable (debit)

        Args:
            ticket: ServiceTicket instance
        """
        if ticket.status not in ['Resolved', 'Closed']:
            raise TransactionPostingError("Ticket must be resolved before posting")

        ServicePostingService._validate_fiscal_period(timezone.now().date())

        # Resolve GL accounts: per-ticket FK override → DEFAULT_GL_ACCOUNTS fallback
        revenue_account = (
            (ticket.service_revenue_account_id and ticket.service_revenue_account)
            or get_gl_account('SERVICE_REVENUE', 'Income', 'Service')
        )
        if not revenue_account:
            raise TransactionPostingError("Service revenue account not found")

        journal_number = f"SV-{ticket.ticket_number}"

        journal = JournalHeader.objects.create(
            reference_number=journal_number,
            description=f"Service: {ticket.subject}",
            posting_date=timezone.now().date(),
            status='Posted',
            source_module='service',
            source_document_id=ticket.pk,
            posted_at=timezone.now(),
        )

        total_cost = Decimal(str(ticket.total_cost or 0))

        if total_cost > 0:
            ar_account = get_gl_account('ACCOUNTS_RECEIVABLE', 'Asset', 'Receivable')
            if not ar_account:
                raise TransactionPostingError(
                    "Accounts Receivable account not found. "
                    "Configure ACCOUNTS_RECEIVABLE in DEFAULT_GL_ACCOUNTS."
                )

            JournalLine.objects.create(
                header=journal,
                account=ar_account,
                debit=total_cost,
                credit=Decimal('0.00'),
                memo="Service Revenue Receivable"
            )
            JournalLine.objects.create(
                header=journal,
                account=revenue_account,
                debit=Decimal('0.00'),
                credit=total_cost,
                memo=f"Service: {ticket.ticket_number}"
            )

        ServicePostingService._validate_journal_balanced(journal)
        ServicePostingService._update_gl_balances(journal)
        return journal
