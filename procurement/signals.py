"""Cross-module signal handlers for procurement events.

This module is intentionally minimal. The legacy ``on_grn_posted`` handler
that updated ``accounting.BudgetEncumbrance`` was removed because:

1. It used a non-existent ``reference_number`` field on
   ``BudgetEncumbrance`` (the real key is ``reference_type`` +
   ``reference_id``), which raised ``FieldError`` on every GRN post and
   produced a 400 Bad Request from the API.

2. The same lifecycle event is now handled by the canonical, schema-
   correct path:

       GoodsReceivedNote.save()
         → mark_commitment_invoiced_for_po(po)
           → ProcurementBudgetLink.status: ACTIVE → INVOICED

   This is the IPSAS-compliant commitment progression that the Budget
   Execution Report and Appropriation.total_committed depend on. See
   ``accounting/services/procurement_commitments.py`` for the helpers.

If you ever need a cross-module side effect on GRN posting, prefer
calling a service helper from ``GoodsReceivedNote.save()`` rather than
re-introducing a signal — signals make the side-effect graph harder to
reason about and harder to test.
"""
# Intentionally empty.
