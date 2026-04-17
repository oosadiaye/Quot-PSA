"""
P2-T3 — GRN ↔ MDA wiring + PO INVOICED transition smoke tests.

Verifies the wiring is present without requiring a DB roundtrip:

* GoodsReceivedNote model has the ``mda`` FK with match-PO enforcement.
* ``mark_commitment_invoiced_for_po`` is importable from
  procurement_commitments (the symbol that GRN.save() looks up).
* The GRN save-flow calls the INVOICED helper on Draft→Posted transition.
"""
from __future__ import annotations

import inspect


class TestGRNHasMDAField:

    def test_mda_field_exists(self):
        from procurement.models import GoodsReceivedNote
        f = GoodsReceivedNote._meta.get_field('mda')
        assert f.null is True  # nullable for migration, enforced by clean()

    def test_warehouse_field_still_present_for_inventory(self):
        from procurement.models import GoodsReceivedNote
        f = GoodsReceivedNote._meta.get_field('warehouse')
        assert f.null is True

    def test_clean_enforces_mda_matches_po(self):
        """Source-level assertion so a refactor that drops the clean()
        MDA guard trips a test."""
        from procurement.models import GoodsReceivedNote
        src = inspect.getsource(GoodsReceivedNote.clean)
        assert 'purchase_order' in src
        assert 'mda' in src
        assert 'ValidationError' in src


class TestCommitmentHelpers:
    """mark_commitment_invoiced_for_po must exist + be importable from
    the exact path GRN.save() uses."""

    def test_mark_commitment_invoiced_importable(self):
        from accounting.services.procurement_commitments import (
            mark_commitment_invoiced_for_po,
        )
        assert callable(mark_commitment_invoiced_for_po)

    def test_create_commitment_importable(self):
        from accounting.services.procurement_commitments import (
            create_commitment_for_po,
        )
        assert callable(create_commitment_for_po)

    def test_cancel_commitment_importable(self):
        from accounting.services.procurement_commitments import (
            cancel_commitment_for_po,
        )
        assert callable(cancel_commitment_for_po)


class TestGRNSaveCallsInvoicedHelper:
    """The Draft → Posted transition on a GRN must flip its PO's
    ProcurementBudgetLink from ACTIVE → INVOICED. Source-level check."""

    def test_save_hook_calls_helper(self):
        from procurement.models import GoodsReceivedNote
        src = inspect.getsource(GoodsReceivedNote.save)
        assert 'mark_commitment_invoiced_for_po' in src

    def test_invoiced_status_on_budget_link(self):
        from procurement.models import ProcurementBudgetLink
        # Status is an inline-choices CharField, not a module-level tuple.
        status_field = ProcurementBudgetLink._meta.get_field('status')
        valid = {choice[0] for choice in status_field.choices}
        assert 'INVOICED' in valid
        assert 'ACTIVE' in valid
        assert 'CLOSED' in valid
        assert 'CANCELLED' in valid
