"""Revenue Collection GL posting service.

Extracts the journal-building logic from
``RevenueCollectionViewSet._post_revenue_journal`` and the TSA balance
update from ``RevenueCollectionViewSet.post_to_gl`` into a standalone
callable that can be invoked from:

  1. The view (``RevenueCollectionViewSet.post_to_gl``) — same behaviour
     as before extraction, call site updated to call this function.
  2. The workflow-dispatch receiver
     (``accounting.signals.workflow_dispatch``) — auto-post on workflow
     approval without a request context.

Public API
----------
``post_revenue_collection_to_gl(collection, user=None) -> JournalHeader``

  Creates the IPSAS revenue journal (DR Cash in TSA / CR Revenue),
  posts it via ``IPSASJournalService``, updates the TSA balance via
  ``TSABalanceService``, and returns the created ``JournalHeader``.

  The caller is responsible for stamping ``collection.status = 'POSTED'``
  and ``collection.journal = <returned header>`` and calling ``.save()``.
  This separation keeps the service free of model-level side-effects that
  belong to the workflow/view layer.

Atomic boundaries
-----------------
This function does NOT wrap itself in ``transaction.atomic``.  The caller
(view or signal receiver) already runs inside a transaction — the view
through DRF request handling, the receiver through the workflow engine's
own ``transaction.atomic`` block.  Adding a nested ``atomic`` here would
create a savepoint that masks commit/rollback semantics to callers; the
view-side behaviour is identical because the outer transaction already
provides the atomicity guarantee.

Raises
------
``ValueError``  — if an NCoA/GL bridge is not configured.
``Exception``   — propagated from ``IPSASJournalService`` / DB layer.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from accounting.models.revenue import RevenueCollection
    from accounting.models.gl import JournalHeader
    from django.contrib.auth.models import AbstractBaseUser


def post_revenue_collection_to_gl(
    collection: "RevenueCollection",
    user: "AbstractBaseUser | None" = None,
) -> "JournalHeader":
    """Post a confirmed revenue collection to GL and update TSA balance.

    IPSAS Revenue Journal:
        DR  Cash in TSA (resolved per-TSA)   NGN amount
        CR  Revenue Account (1xxxxxxx)       NGN amount

    All GL accounts are resolved via the NCoA → legacy_account bridge;
    no account codes are hardcoded here.

    Args:
        collection: The ``RevenueCollection`` instance to post.  Must be
            in ``CONFIRMED`` status (caller's responsibility to guard).
        user: The user initiating the post, passed through to
            ``IPSASJournalService`` for audit trail.  May be ``None``
            when called from an automated context (signal receiver).

    Returns:
        The newly created and posted ``JournalHeader``.

    Raises:
        ValueError: When the revenue head's economic segment has no
            linked GL account (NCoA bridge not yet seeded).
    """
    # Lazy imports — this module may be loaded before the full app
    # registry is ready when imported from signals.  Safe to import at
    # call time (receiver fires well after app startup).
    from accounting.models.gl import JournalHeader, JournalLine, TransactionSequence
    from accounting.services.ipsas_journal_service import IPSASJournalService
    from accounting.services.tsa_gl_resolver import resolve_tsa_cash_gl
    from accounting.services.treasury_service import TSABalanceService

    ref = TransactionSequence.get_next('journal', prefix='JE-')
    header = JournalHeader.objects.create(
        reference_number=ref,
        description=(
            f"Revenue: {collection.revenue_head.name} from {collection.payer_name}"
        ),
        posting_date=collection.collection_date,
        status='Draft',
        source_module='revenue',
        source_document_id=collection.pk,
    )

    # DR: Cash in TSA — resolved via the collection's TSA account
    # (or tenant default via AccountingSettings.default_cash_account_code,
    # then the first 31* asset GL).  Never a hardcoded code.
    tsa_gl = resolve_tsa_cash_gl(
        tsa_account=getattr(collection, 'tsa_account', None),
    )
    JournalLine.objects.create(
        header=header,
        account=tsa_gl,
        debit=collection.amount,
        credit=0,
        memo=f"Revenue receipt: {collection.receipt_number}",
        ncoa_code=collection.ncoa_code,
    )

    # CR: Revenue account from NCoA bridge
    revenue_gl = collection.revenue_head.economic_segment.legacy_account
    if not revenue_gl:
        raise ValueError(
            f"Revenue head '{collection.revenue_head.name}' has no linked GL "
            f"account.  Run: python manage.py seed_ncoa_as_coa"
        )
    JournalLine.objects.create(
        header=header,
        account=revenue_gl,
        debit=0,
        credit=collection.amount,
        memo=f"Revenue: {collection.revenue_head.name}",
    )

    # Post the journal to GL (sets header.status → 'Posted', updates
    # account balances via the chokepoint).
    IPSASJournalService.post_journal(header, user)

    # Update TSA balance — cash entered the government account.
    # This mirrors what the view does after calling _post_revenue_journal.
    TSABalanceService.process_revenue(collection)

    return header
