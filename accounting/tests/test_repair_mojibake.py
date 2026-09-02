"""Mojibake repair rules — QA finding L-2.

The corrupted names come in two shapes that need OPPOSITE fixes, and a
single blanket substitution silently ruins one of them:

    "Fees � General"     -> dash       -> "Fees - General"
    "Governor�s Office"  -> apostrophe -> "Governor's Office"

A naive ``replace("�", "-")`` yields "Governor-s Office", which is worse
than the corruption it replaces. These tests pin the distinction.

Pure functions — no database.
"""
from __future__ import annotations

import pytest

REPLACEMENT = "�"


@pytest.mark.unit
class TestDashPattern:
    """Space-delimited: the original was a dash."""

    def test_repairs_spaced_replacement_as_dash(self):
        from accounting.management.commands.repair_mojibake import _repair
        assert _repair(f"Fees {REPLACEMENT} General") == "Fees - General"

    def test_repairs_multiword_name(self):
        from accounting.management.commands.repair_mojibake import _repair
        assert _repair(f"Budget Augmentation {REPLACEMENT} Derivation") == \
            "Budget Augmentation - Derivation"

    def test_does_not_leave_double_spaces(self):
        from accounting.management.commands.repair_mojibake import _repair
        assert "  " not in _repair(f"Training {REPLACEMENT} General")

    def test_handles_name_with_slash(self):
        from accounting.management.commands.repair_mojibake import _repair
        assert _repair(f"Domestic Debt / Discounts {REPLACEMENT} Treasury Bill") == \
            "Domestic Debt / Discounts - Treasury Bill"


@pytest.mark.unit
class TestApostrophePattern:
    """Letter-adjacent: the original was an apostrophe."""

    def test_repairs_possessive_as_apostrophe(self):
        from accounting.management.commands.repair_mojibake import _repair
        assert _repair(f"Governor{REPLACEMENT}s Office") == "Governor's Office"

    def test_repairs_possessive_mid_sentence(self):
        from accounting.management.commands.repair_mojibake import _repair
        assert _repair(
            f"Directorate of Project Monitoring Governor{REPLACEMENT}s Office"
        ) == "Directorate of Project Monitoring Governor's Office"

    def test_never_turns_a_possessive_into_a_hyphen(self):
        """The exact regression a blanket replace would introduce."""
        from accounting.management.commands.repair_mojibake import _repair
        assert "Governor-s" not in _repair(f"Governor{REPLACEMENT}s Office")

    def test_repairs_trailing_possessive(self):
        from accounting.management.commands.repair_mojibake import _repair
        assert _repair(f"Workers{REPLACEMENT} Union") == "Workers' Union"


@pytest.mark.unit
class TestSafety:

    def test_leaves_clean_text_untouched(self):
        from accounting.management.commands.repair_mojibake import _repair
        for text in ["Fees - General", "Governor's Office", "Cash at Bank"]:
            assert _repair(text) == text

    def test_leaves_unrecognised_pattern_unrepaired(self):
        """Position gives no clue, so the caller must report rather than
        write a guess. The marker must survive for that check to work."""
        from accounting.management.commands.repair_mojibake import _repair
        assert REPLACEMENT in _repair(f"{REPLACEMENT}Leading")

    def test_repairs_every_occurrence_in_one_name(self):
        from accounting.management.commands.repair_mojibake import _repair
        assert _repair(
            f"Governor{REPLACEMENT}s Office {REPLACEMENT} Recurrent"
        ) == "Governor's Office - Recurrent"
