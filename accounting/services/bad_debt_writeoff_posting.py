"""Bad Debt Write-Off GL posting service.

Extracted from ``accounting/views/workflows.py:BadDebtWriteOffViewSet.post_writeoff``
so the same logic can be called from both the DRF action (operator-initiated) and
the ``document_approval_completed`` signal receiver (workflow-triggered).

Entry point:
    post_bad_debt_writeoff(writeoff, user=None)

Journal:
    DR  Allowance for Doubtful Accounts   amount_written_off
    CR  Accounts Receivable                                   amount_written_off

On success the function stamps:
    writeoff.journal_id = journal.pk
    writeoff.status     = 'POSTED'
via a bulk ``update()`` to avoid re-triggering save-time signals inside the
workflow's ``transaction.atomic()`` block.

Failure: raises the underlying exception (``JournalPostingError`` or any DB
error). The caller decides whether to re-raise (signal receiver → rolls back
the approval) or catch and surface as an HTTP error (view action → 400 response).
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING

from django.db import transaction

if TYPE_CHECKING:
    from accounting.models.audit import BadDebtWriteOff

logger = logging.getLogger(__name__)


def post_bad_debt_writeoff(writeoff: "BadDebtWriteOff", user=None) -> object:
    """Post a bad-debt write-off journal entry to GL.

    Parameters
    ----------
    writeoff:
        A ``BadDebtWriteOff`` instance in ``'APPROVED'`` status.  The caller is
        responsible for the idempotency pre-check (skip if ``status == 'POSTED'``
        or ``journal_id`` is set); this function does NOT re-check.
    user:
        The acting user (for ``IPSASJournalService`` audit trail).  May be
        ``None`` when called from the signal receiver (the approval itself
        already carries the approver identity).

    Returns
    -------
    JournalHeader
        The newly posted journal.

    Raises
    ------
    JournalPostingError
        If the IPSAS period gate, balance check, or any other posting
        validation fails.
    Exception
        Any other DB or service error propagates to the caller.
    """
    from accounting.models.audit import BadDebtWriteOff
    from accounting.models import Account, JournalHeader, JournalLine
    from accounting.services.ipsas_journal_service import (
        IPSASJournalService,
        JournalPostingError,  # noqa: F401 — re-exported for caller convenience
    )
    from accounting.transaction_posting import get_gl_account

    with transaction.atomic():
        ar_account = get_gl_account('ACCOUNTS_RECEIVABLE', 'Asset', 'Receivable')
        allowance_account = Account.objects.filter(
            name__icontains='Allowance', account_type='Asset',
        ).first()

        if not ar_account or not allowance_account:
            raise ValueError(
                "AR or Allowance for Doubtful Accounts GL account not found. "
                "Configure the chart of accounts before posting bad-debt write-offs."
            )

        journal = JournalHeader.objects.create(
            reference_number=f"BDWO-{writeoff.write_off_number}",
            description=f"Bad Debt Write-Off {writeoff.write_off_number}",
            posting_date=writeoff.write_off_date,
            status='Draft',
            source_module='workflow.bad_debt_writeoff',
            source_document_id=writeoff.pk,
        )

        amount = writeoff.amount_written_off
        JournalLine.objects.create(
            header=journal,
            account=allowance_account,
            debit=amount,
            credit=Decimal('0.00'),
            memo=f"Write-off {writeoff.write_off_number}",
            document_number=journal.document_number,
        )
        JournalLine.objects.create(
            header=journal,
            account=ar_account,
            debit=Decimal('0.00'),
            credit=amount,
            memo=f"AR write-off {writeoff.write_off_number}",
            document_number=journal.document_number,
        )

        IPSASJournalService.post_journal(journal, user=user)

        # Stamp status + journal FK via update() to avoid re-triggering
        # save-time signals inside the workflow's atomic block.
        BadDebtWriteOff.objects.filter(pk=writeoff.pk).update(
            journal_id=journal.pk,
            status='POSTED',
        )

    return journal
