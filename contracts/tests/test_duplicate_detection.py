"""
Duplicate contract and duplicate invoice detection.

No database and no model — normalisation and set overlap over values we
already hold.

The cases that matter are the ones where a plausible implementation is
wrong in a way nobody notices: stopwords left in so every "Supply of X"
matches every other, dashes treated as separators so "Asaba-Ughelli"
splits differently from "Asaba Ughelli", and a single signal (value, or
vendor, or title) being enough on its own to raise a finding.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.test import SimpleTestCase

from contracts.services.duplicate_detection import (
    ContractRecord,
    InvoiceRecord,
    check_before_saving,
    find_duplicate_contracts,
    find_duplicate_invoices,
    normalise_title,
    title_similarity,
)

D = Decimal


def _c(cid, title, value="4250000000.00", vendor=1, day=1, month=6) -> ContractRecord:
    return ContractRecord(
        contract_id=cid,
        contract_number=f"DSG/WORKS/2026/{cid:03d}",
        vendor_id=vendor,
        vendor_name="Adamu Ventures Ltd",
        title=title,
        value=D(value),
        signed_date=date(2026, month, day),
    )


def _i(iid, number, amount="1500000.00", vendor=1, day=1, month=6) -> InvoiceRecord:
    return InvoiceRecord(
        invoice_id=iid, invoice_number=number, vendor_id=vendor,
        vendor_name="Adamu Ventures Ltd", amount=D(amount),
        invoice_date=date(2026, month, day),
    )


class NormalisationTests(SimpleTestCase):

    def test_stopwords_are_dropped(self):
        # Without this "Supply of desks" and "Supply of chairs" share two
        # of three words and score 0.5 — every procurement title in the
        # register would match every other.
        assert "supply" not in normalise_title("Supply of desks")
        assert "of" not in normalise_title("Supply of desks")
        assert "desks" in normalise_title("Supply of desks")

    def test_two_unrelated_supplies_do_not_match(self):
        score, _ = title_similarity("Supply of desks", "Supply of chairs")
        assert score == 0.0

    def test_dashes_join_rather_than_separate(self):
        # "Asaba-Ughelli" and "Asaba Ughelli" are the same two places.
        assert normalise_title("Asaba-Ughelli") == normalise_title("Asaba Ughelli")

    def test_en_dash_is_treated_like_a_hyphen(self):
        assert normalise_title("Asaba–Ughelli") == normalise_title("Asaba-Ughelli")

    def test_word_order_does_not_matter(self):
        assert normalise_title("Asaba Road Rehabilitation") == \
               normalise_title("Rehabilitation of Asaba Road")

    def test_case_and_punctuation_are_ignored(self):
        assert normalise_title("ASABA ROAD.") == normalise_title("asaba road")

    def test_abbreviations_are_expanded(self):
        assert normalise_title("Rehab of Asaba Rd") == normalise_title(
            "Rehabilitation of Asaba Road")

    def test_roman_numerals_are_expanded(self):
        assert normalise_title("Phase II") == normalise_title("Phase 2")

    def test_accents_are_folded(self):
        assert normalise_title("Ilorin Rd") == normalise_title("Ilorín Rd")

    def test_an_empty_title_scores_zero_rather_than_matching_everything(self):
        # A set-overlap implementation that returns 1.0 for two empty sets
        # would mark every untitled contract as a duplicate of every other.
        assert title_similarity("", "")[0] == 0.0
        assert title_similarity("", "Asaba Road")[0] == 0.0


class SimilarityTests(SimpleTestCase):

    def test_the_real_world_case(self):
        score, shared = title_similarity(
            "Rehabilitation of Asaba-Ughelli Road (Phase 2)",
            "Rehab of Asaba Ughelli Rd Phase II",
        )
        assert score == 1.0
        assert "rehabilitation" in shared and "road" in shared

    def test_shared_terms_are_returned_as_evidence(self):
        # The reviewer is shown the words, not asked to trust a number.
        _, shared = title_similarity("Asaba Road Rehabilitation", "Asaba Road Drainage")
        assert set(shared) == {"asaba", "road"}


class ContractDuplicateTests(SimpleTestCase):

    def test_the_same_award_captured_twice_is_found(self):
        rows = [
            _c(1, "Rehabilitation of Asaba-Ughelli Road (Phase 2)", day=1),
            _c(2, "Rehab of Asaba Ughelli Rd Phase II", day=9),
        ]
        out = find_duplicate_contracts(rows)
        assert len(out) == 1
        assert {out[0].left_id, out[0].right_id} == {1, 2}
        assert out[0].similarity == 1.0
        assert out[0].days_apart == 8

    def test_a_similar_title_at_a_different_value_is_not_flagged(self):
        # Two genuine phases of one road, priced differently.
        rows = [
            _c(1, "Rehabilitation of Asaba Road", value="4250000000.00"),
            _c(2, "Rehabilitation of Asaba Road", value="900000000.00", day=9),
        ]
        assert find_duplicate_contracts(rows) == []

    def test_the_same_value_with_an_unrelated_title_is_not_flagged(self):
        # A contractor may well hold two contracts of the same value.
        rows = [
            _c(1, "Rehabilitation of Asaba Road"),
            _c(2, "Supply of hospital consumables", day=9),
        ]
        assert find_duplicate_contracts(rows) == []

    def test_different_vendors_are_never_a_duplicate_pair(self):
        rows = [
            _c(1, "Rehabilitation of Asaba Road", vendor=1),
            _c(2, "Rehabilitation of Asaba Road", vendor=2, day=9),
        ]
        assert find_duplicate_contracts(rows) == []

    def test_outside_the_window_is_not_flagged(self):
        rows = [
            _c(1, "Rehabilitation of Asaba Road", month=1, day=1),
            _c(2, "Rehabilitation of Asaba Road", month=12, day=31),
        ]
        rows[1] = ContractRecord(**{**rows[1].__dict__, "signed_date": date(2028, 1, 1)})
        assert find_duplicate_contracts(rows) == []

    def test_a_small_value_difference_is_tolerated(self):
        # A re-key transposition, not a different contract.
        rows = [
            _c(1, "Rehabilitation of Asaba Road", value="4250000000.00"),
            _c(2, "Rehabilitation of Asaba Road", value="4250000000.50", day=9),
        ]
        assert len(find_duplicate_contracts(rows)) == 1

    def test_zero_value_contracts_are_ignored(self):
        rows = [_c(1, "Asaba Road", value="0"), _c(2, "Asaba Road", value="0", day=9)]
        assert find_duplicate_contracts(rows) == []

    def test_money_stays_decimal(self):
        rows = [
            _c(1, "Asaba Road Rehabilitation", value="4250000000.10"),
            _c(2, "Asaba Road Rehabilitation", value="4250000000.35", day=9),
        ]
        out = find_duplicate_contracts(rows)
        assert out[0].value_difference == D("0.25")
        assert isinstance(out[0].value_difference, Decimal)

    def test_findings_are_ordered_by_similarity(self):
        rows = [
            _c(1, "Rehabilitation of Asaba Road"),
            _c(2, "Rehabilitation of Asaba Road", day=5),      # identical
            _c(3, "Rehabilitation of Asaba Road Drainage", day=9),  # partial
        ]
        out = find_duplicate_contracts(rows)
        assert out[0].similarity >= out[-1].similarity


class CheckBeforeSavingTests(SimpleTestCase):
    """Timing is the point: a draft warning costs a glance."""

    def test_a_new_contract_is_matched_against_existing_ones(self):
        existing = [_c(1, "Rehabilitation of Asaba-Ughelli Road (Phase 2)")]
        candidate = _c(99, "Rehab of Asaba Ughelli Rd Phase II", day=9)
        out = check_before_saving(candidate, existing)
        assert len(out) == 1
        assert {out[0].left_id, out[0].right_id} == {1, 99}

    def test_a_contract_is_never_a_duplicate_of_itself(self):
        # On edit, the row being saved is already in the table.
        rec = _c(1, "Rehabilitation of Asaba Road")
        assert check_before_saving(rec, [rec]) == []

    def test_no_existing_contracts_means_no_warning(self):
        assert check_before_saving(_c(1, "Asaba Road"), []) == []


class InvoiceDuplicateTests(SimpleTestCase):

    def test_same_amount_different_number_close_together(self):
        rows = [_i(1, "INV-100"), _i(2, "INV-217", day=8)]
        out = find_duplicate_invoices(rows)
        assert len(out) == 1
        assert out[0].days_apart == 7

    def test_the_same_number_is_left_to_the_database(self):
        # The per-vendor unique constraint makes that case impossible
        # rather than merely unlikely, so reporting it here would be noise.
        rows = [_i(1, "INV-100"), _i(2, "INV-100", day=8)]
        assert find_duplicate_invoices(rows) == []

    def test_different_vendors_are_not_duplicates(self):
        rows = [_i(1, "INV-100", vendor=1), _i(2, "INV-217", vendor=2, day=8)]
        assert find_duplicate_invoices(rows) == []

    def test_different_amounts_are_not_duplicates(self):
        rows = [_i(1, "INV-100", amount="1500000.00"),
                _i(2, "INV-217", amount="2500000.00", day=8)]
        assert find_duplicate_invoices(rows) == []

    def test_far_apart_is_not_a_duplicate(self):
        rows = [_i(1, "INV-100", month=1), _i(2, "INV-217", month=9)]
        assert find_duplicate_invoices(rows) == []

    def test_tolerance_is_proportional(self):
        big = [_i(1, "A", amount="100000000.00"), _i(2, "B", amount="100000500.00", day=3)]
        assert len(find_duplicate_invoices(big)) == 1
        small = [_i(1, "A", amount="1000.00"), _i(2, "B", amount="1500.00", day=3)]
        assert find_duplicate_invoices(small) == []
