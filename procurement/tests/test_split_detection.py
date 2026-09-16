"""
Split-purchase and duplicate-payment detection.

No database and no model: the finding half is exact arithmetic over rows,
which is the point — it is cheap, explainable to an auditor in a sentence,
and it cannot hallucinate.

The cases worth pinning are the ones where an obvious implementation is
quietly wrong: calendar bucketing (evaded by splitting across a month
boundary), including orders that were already escalated, and reporting
the same three orders three times because the window was slid from each
of them.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.test import SimpleTestCase

from procurement.services.split_detection import (
    Ceiling,
    PurchaseRecord,
    build_cluster_prompt,
    find_duplicate_candidates,
    find_split_clusters,
    parse_verdict,
)

D = Decimal

#: The real BPP rung: goods above this leave the Accounting Officer.
GOODS = Ceiling(category="GOODS_SERVICES", limit=D("2500000"), escalates_to="PTB")


def _po(pid, day, amount, vendor=1, ref="", desc="", month=1) -> PurchaseRecord:
    return PurchaseRecord(
        purchase_id=pid,
        vendor_id=vendor,
        vendor_name=f"Vendor {vendor}",
        order_date=date(2026, month, day),
        amount=D(amount),
        reference=ref,
        description=desc,
    )


class SplitDetectionTests(SimpleTestCase):

    def test_three_orders_under_the_ceiling_that_together_exceed_it(self):
        # The whole point: each passes every check, the pattern does not.
        pos = [_po(1, 3, "2400000"), _po(2, 8, "2400000"), _po(3, 15, "2400000")]
        out = find_split_clusters(pos, [GOODS])
        assert len(out) == 1
        assert out[0].purchase_ids == (1, 2, 3)
        assert out[0].total == D("7200000")
        assert out[0].escalates_to == "PTB"
        assert out[0].excess == D("4700000")

    def test_orders_below_the_ceiling_that_stay_below_are_not_flagged(self):
        pos = [_po(1, 3, "1000000"), _po(2, 8, "1000000")]
        assert find_split_clusters(pos, [GOODS]) == []

    def test_a_single_order_is_never_a_cluster(self):
        assert find_split_clusters([_po(1, 3, "2400000")], [GOODS]) == []

    def test_different_vendors_are_not_a_split(self):
        pos = [_po(1, 3, "2400000", vendor=1), _po(2, 4, "2400000", vendor=2)]
        assert find_split_clusters(pos, [GOODS]) == []

    def test_orders_outside_the_window_are_not_a_split(self):
        pos = [_po(1, 3, "2400000", month=1), _po(2, 3, "2400000", month=6)]
        assert find_split_clusters(pos, [GOODS]) == []

    def test_the_window_slides_and_does_not_bucket_by_month(self):
        # Calendar bucketing is the obvious implementation and is trivially
        # evaded: 30 Jan / 31 Jan / 1 Feb straddles two months. Anyone
        # dividing a requirement deliberately is watching the calendar.
        pos = [
            _po(1, 30, "2400000", month=1),
            _po(2, 31, "2400000", month=1),
            _po(3, 1, "2400000", month=2),
        ]
        out = find_split_clusters(pos, [GOODS])
        assert len(out) == 1
        assert out[0].purchase_ids == (1, 2, 3)
        assert out[0].span_days == 2

    def test_an_already_escalated_order_is_excluded(self):
        # A 9m order went through PTB. Grouping it with two small ones is
        # not evasion, and reporting it trains reviewers to dismiss the
        # list — which costs more than the finding is worth.
        pos = [_po(1, 3, "9000000"), _po(2, 5, "600000"), _po(3, 7, "700000")]
        assert find_split_clusters(pos, [GOODS]) == []

    def test_immaterial_orders_are_ignored(self):
        # Ten stationery orders at 250,000 crossing the ceiling together is
        # ordinary business. Flagging it buries the real findings.
        pos = [_po(i, i, "250000") for i in range(1, 12)]
        assert find_split_clusters(pos, [GOODS]) == []

    def test_the_same_pattern_is_reported_once_not_once_per_anchor(self):
        # The window slides from every order, so the same three orders are
        # found anchored at each of them. A reviewer should see them once.
        pos = [_po(1, 3, "2400000"), _po(2, 8, "2400000"), _po(3, 15, "2400000")]
        out = find_split_clusters(pos, [GOODS])
        assert len(out) == 1

    def test_a_different_category_does_not_share_a_ceiling(self):
        works = Ceiling(category="WORKS", limit=D("5000000"), escalates_to="MTB")
        pos = [_po(1, 3, "2400000"), _po(2, 8, "2400000")]
        assert find_split_clusters(pos, [works]) == []

    def test_clusters_are_ordered_by_how_far_over_they_went(self):
        pos = [
            _po(1, 3, "2400000", vendor=1), _po(2, 8, "2400000", vendor=1),
            _po(3, 3, "2400000", vendor=2), _po(4, 8, "2400000", vendor=2),
            _po(5, 9, "2400000", vendor=2),
        ]
        out = find_split_clusters(pos, [GOODS])
        assert out[0].vendor_id == 2          # 7.2m beats 4.8m
        assert out[0].excess > out[1].excess

    def test_money_stays_decimal(self):
        pos = [_po(1, 3, "2400000.55"), _po(2, 8, "2400000.55")]
        out = find_split_clusters(pos, [GOODS])
        assert out[0].total == D("4800001.10")
        assert isinstance(out[0].total, Decimal)


class DuplicateDetectionTests(SimpleTestCase):

    def test_near_identical_amounts_close_together_are_flagged(self):
        pos = [_po(1, 3, "1500000", ref="INV-100"), _po(2, 10, "1500000", ref="INV-217")]
        out = find_duplicate_candidates(pos)
        assert len(out) == 1
        assert {out[0].left_id, out[0].right_id} == {1, 2}
        assert out[0].days_apart == 7

    def test_the_same_reference_is_one_document_not_two_payments(self):
        # An identical reference is an import or re-entry artefact. Mixing
        # those in is how a duplicate-payment report loses its audience.
        pos = [_po(1, 3, "1500000", ref="INV-100"), _po(2, 10, "1500000", ref="INV-100")]
        assert find_duplicate_candidates(pos) == []

    def test_different_amounts_are_not_duplicates(self):
        pos = [_po(1, 3, "1500000", ref="A"), _po(2, 10, "1900000", ref="B")]
        assert find_duplicate_candidates(pos) == []

    def test_tolerance_is_proportional_not_absolute(self):
        # A re-keyed duplicate differs by a rounding, and that error scales
        # with the figure. A flat naira tolerance misses large contracts
        # and floods on small ones.
        big = [_po(1, 3, "100000000", ref="A"), _po(2, 5, "100000500", ref="B")]
        assert len(find_duplicate_candidates(big)) == 1
        small = [_po(1, 3, "1000", ref="A"), _po(2, 5, "1500", ref="B")]
        assert find_duplicate_candidates(small) == []

    def test_far_apart_is_not_a_duplicate(self):
        pos = [_po(1, 3, "1500000", ref="A", month=1), _po(2, 3, "1500000", ref="B", month=6)]
        assert find_duplicate_candidates(pos) == []

    def test_different_vendors_are_not_duplicates(self):
        pos = [_po(1, 3, "1500000", ref="A", vendor=1), _po(2, 5, "1500000", ref="B", vendor=2)]
        assert find_duplicate_candidates(pos) == []

    def test_zero_amounts_are_not_duplicates_of_each_other(self):
        pos = [_po(1, 3, "0", ref="A"), _po(2, 5, "0", ref="B")]
        assert find_duplicate_candidates(pos) == []


class PromptTests(SimpleTestCase):

    def _cluster_and_records(self):
        pos = [
            _po(1, 3, "2400000", desc="Supply of A4 paper"),
            _po(2, 8, "2400000", desc="Supply of printing consumables"),
            _po(3, 15, "2400000", desc="Supply of office sundries"),
        ]
        return find_split_clusters(pos, [GOODS])[0], pos

    def test_the_prompt_forbids_recalculation(self):
        # The totals are already verified. Inviting the model to redo them
        # lets an arithmetic error arrive dressed as a finding.
        cluster, pos = self._cluster_and_records()
        prompt = build_cluster_prompt(cluster, pos)
        assert "do not recalculate" in prompt.lower()

    def test_the_prompt_carries_the_descriptions(self):
        cluster, pos = self._cluster_and_records()
        prompt = build_cluster_prompt(cluster, pos)
        assert "A4 paper" in prompt and "office sundries" in prompt

    def test_the_prompt_licenses_a_negative_answer(self):
        # A detector that flags everything gets switched off.
        cluster, pos = self._cluster_and_records()
        assert "SEPARATE" in build_cluster_prompt(cluster, pos)


class VerdictTests(SimpleTestCase):

    def test_a_clean_verdict_is_read(self):
        out = parse_verdict('{"verdict": "DIVIDED", "confidence": 0.8, "reason": "same goods"}')
        assert out["verdict"] == "DIVIDED"
        assert out["confidence"] == 0.8

    def test_fenced_json_is_read(self):
        out = parse_verdict('```json\n{"verdict": "SEPARATE", "confidence": 0.6}\n```')
        assert out["verdict"] == "SEPARATE"

    def test_an_unreadable_reply_is_unclear_not_a_finding(self):
        # The arithmetic that found the cluster stands on its own; what
        # must not happen is attributing an opinion to a model that did
        # not give one.
        for junk in ("", "I think maybe", "{broken", None):
            assert parse_verdict(junk)["verdict"] == "UNCLEAR"

    def test_an_invented_verdict_is_refused(self):
        assert parse_verdict('{"verdict": "FRAUD", "confidence": 1.0}')["verdict"] == "UNCLEAR"

    def test_confidence_is_clamped(self):
        assert parse_verdict('{"verdict": "DIVIDED", "confidence": 9}')["confidence"] == 1.0
        assert parse_verdict('{"verdict": "DIVIDED", "confidence": -2}')["confidence"] == 0.0

    def test_missing_confidence_is_zero(self):
        assert parse_verdict('{"verdict": "DIVIDED"}')["confidence"] == 0.0
