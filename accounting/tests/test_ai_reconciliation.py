"""
The reconciliation proposal validator.

No database and no model. This layer exists to *refuse* things, and every
refusal is pure arithmetic over values we already hold — which is exactly
the part worth pinning, because a proposal that survives validation is
one a reviewer is being invited to click.

The bar for each test: it must fail if the corresponding guard is deleted.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.test import SimpleTestCase

from accounting.services.ai_reconciliation import (
    CandidateRecord,
    Kind,
    Proposal,
    Reject,
    Rejected,
    StatementLineRecord,
    build_prompt,
    expected_direction,
    parse_response,
    validate_all,
    validate_proposal,
)

D = Decimal


def _line(amount="1000000.00", is_credit=True, line_id=1) -> StatementLineRecord:
    return StatementLineRecord(
        line_id=line_id,
        transaction_date=date(2026, 9, 1),
        amount=D(amount),
        is_credit=is_credit,
        description="NIP TRF",
        reference="REF/001",
    )


def _cand(tid, amount, ttype="PAYMENT", day=1) -> CandidateRecord:
    return CandidateRecord(
        transaction_id=tid,
        transaction_type=ttype,
        transaction_date=date(2026, 9, day),
        amount=D(amount),
        reference=f"PV/{tid:04d}",
    )


class DirectionTests(SimpleTestCase):
    """A bank line can only be explained by one side of the ledger."""

    def test_money_out_is_explained_by_payments(self):
        assert expected_direction(_line(is_credit=True)) == "PAYMENT"

    def test_money_in_is_explained_by_receipts(self):
        assert expected_direction(_line(is_credit=False)) == "RECEIPT"


class BundleTests(SimpleTestCase):
    """The case the exact-amount rule cannot see."""

    def test_several_vouchers_summing_to_the_line_are_a_bundle(self):
        cands = [_cand(1, "400000.00"), _cand(2, "600000.00")]
        out = validate_proposal({"transaction_ids": [1, 2], "confidence": 0.9}, _line(), cands)
        assert isinstance(out, Proposal)
        assert out.kind == Kind.BUNDLE
        assert out.proposed_total == D("1000000.00")
        assert out.variance == 0
        assert out.is_exact

    def test_a_single_exact_voucher_is_not_called_a_bundle(self):
        cands = [_cand(1, "1000000.00")]
        out = validate_proposal({"transaction_ids": [1]}, _line(), cands)
        assert out.kind == Kind.ONE_TO_ONE

    def test_the_total_is_recomputed_not_read_from_the_reply(self):
        # The single most important guard here. A model asserting a total
        # that does not add up must not be able to launder a wrong bundle
        # past review by stating the number a reviewer expects to see.
        # The vouchers really sum to 1,050,000 against a 1,000,000 bank
        # line — a 50,000 shortfall. The reply insists the total is exactly
        # the line. Trusting it would label this an exact BUNDLE and hide
        # the shortfall completely.
        cands = [_cand(1, "600000.00"), _cand(2, "450000.00")]
        out = validate_proposal(
            {"transaction_ids": [1, 2], "total": "1000000.00", "confidence": 1.0},
            _line("1000000.00"), cands,
        )
        assert isinstance(out, Proposal)
        assert out.proposed_total == D("1050000.00")     # ours, not theirs
        assert out.variance == D("-50000.00")
        assert out.kind == Kind.PARTIAL                  # not BUNDLE


class HallucinationTests(SimpleTestCase):
    """Only the ids we supplied may be used."""

    def test_an_invented_id_is_refused(self):
        cands = [_cand(1, "400000.00")]
        out = validate_proposal({"transaction_ids": [1, 999]}, _line(), cands)
        assert isinstance(out, Rejected)
        assert out.reason == Reject.UNKNOWN_ID

    def test_the_same_voucher_twice_is_refused(self):
        # Double-counting is the easiest way to make a bundle appear to
        # balance, and the hardest to catch by eye in a column of figures.
        cands = [_cand(1, "500000.00")]
        out = validate_proposal({"transaction_ids": [1, 1]}, _line(), cands)
        assert isinstance(out, Rejected)
        assert out.reason == Reject.DUPLICATE_ID

    def test_an_empty_proposal_is_refused(self):
        out = validate_proposal({"transaction_ids": []}, _line(), [_cand(1, "1.00")])
        assert out.reason == Reject.NO_IDS

    def test_a_non_numeric_id_is_refused(self):
        out = validate_proposal({"transaction_ids": ["PV/0001"]}, _line(), [_cand(1, "1.00")])
        assert out.reason == Reject.MALFORMED

    def test_a_receipt_cannot_explain_money_leaving(self):
        cands = [_cand(1, "1000000.00", ttype="RECEIPT")]
        out = validate_proposal({"transaction_ids": [1]}, _line(is_credit=True), cands)
        assert out.reason == Reject.WRONG_DIRECTION


class VarianceTests(SimpleTestCase):
    """Differences must be named, and some must not be proposed at all."""

    def test_a_small_shortfall_is_a_bank_charge(self):
        cands = [_cand(1, "1000000.00")]
        out = validate_proposal({"transaction_ids": [1]}, _line("999950.00"), cands)
        assert out.kind == Kind.FEE_ADJUSTED
        # Negative: the bank line is 50 less than the vouchers it settles.
        assert out.variance == D("-50.00")

    def test_a_large_shortfall_is_a_partial_settlement(self):
        cands = [_cand(1, "1000000.00")]
        out = validate_proposal({"transaction_ids": [1]}, _line("400000.00"), cands)
        assert out.kind == Kind.PARTIAL

    def test_the_bank_moving_more_than_the_vouchers_is_never_proposed(self):
        # There is no benign story for the bank paying out more than the
        # ledger authorises. Surfacing a cheerful explanation for it would
        # invite someone to accept it.
        cands = [_cand(1, "400000.00")]
        out = validate_proposal({"transaction_ids": [1]}, _line("1000000.00"), cands)
        assert isinstance(out, Rejected)
        assert out.reason == Reject.UNEXPLAINED_VARIANCE

    def test_the_fee_boundary_is_inclusive(self):
        cands = [_cand(1, "1000000.00")]
        out = validate_proposal(
            {"transaction_ids": [1]}, _line("995000.00"), cands,
            fee_tolerance=D("5000.00"),
        )
        assert out.kind == Kind.FEE_ADJUSTED

    def test_just_past_the_fee_boundary_is_partial(self):
        cands = [_cand(1, "1000000.00")]
        out = validate_proposal(
            {"transaction_ids": [1]}, _line("994999.99"), cands,
            fee_tolerance=D("5000.00"),
        )
        assert out.kind == Kind.PARTIAL

    def test_the_kind_in_the_reply_is_ignored(self):
        # The arithmetic already determines this. Letting the reply choose
        # would let a confident mislabel carry a variance past review.
        cands = [_cand(1, "1000000.00")]
        out = validate_proposal(
            {"transaction_ids": [1], "kind": "BUNDLE"}, _line("400000.00"), cands,
        )
        assert out.kind == Kind.PARTIAL

    def test_money_is_never_a_float(self):
        cands = [_cand(1, "0.10"), _cand(2, "0.20")]
        out = validate_proposal({"transaction_ids": [1, 2]}, _line("0.30"), cands)
        assert out.proposed_total == D("0.30")
        assert out.variance == 0
        assert isinstance(out.proposed_total, Decimal)


class ExclusivityTests(SimpleTestCase):
    """One ledger transaction cannot settle two bank lines."""

    def test_an_already_matched_transaction_is_refused(self):
        cands = [_cand(1, "1000000.00")]
        out = validate_proposal(
            {"transaction_ids": [1]}, _line(), cands, already_matched=[1],
        )
        assert out.reason == Reject.ALREADY_MATCHED

    def test_two_proposals_cannot_both_spend_one_voucher(self):
        # A single reply can contain competing proposals. Accepting both
        # would hand a reviewer a contradiction with two clickable sides.
        cands = [_cand(1, "600000.00"), _cand(2, "400000.00"), _cand(3, "400000.00")]
        accepted, rejected = validate_all(
            [
                {"transaction_ids": [1, 2], "confidence": 0.9},
                {"transaction_ids": [1, 3], "confidence": 0.8},
            ],
            _line(), cands,
        )
        assert len(accepted) == 1
        assert len(rejected) == 1
        assert rejected[0].reason == Reject.ALREADY_MATCHED

    def test_exact_proposals_are_offered_before_approximate_ones(self):
        cands = [_cand(1, "1000000.00"), _cand(2, "999000.00")]
        accepted, _ = validate_all(
            [
                {"transaction_ids": [2], "confidence": 0.99},   # variance
                {"transaction_ids": [1], "confidence": 0.40},   # exact
            ],
            _line(), cands,
        )
        assert accepted[0].transaction_ids == (1,)


class ConfidenceTests(SimpleTestCase):

    def test_confidence_is_clamped(self):
        cands = [_cand(1, "1000000.00")]
        assert validate_proposal({"transaction_ids": [1], "confidence": 4.2}, _line(), cands).confidence == 1.0
        assert validate_proposal({"transaction_ids": [1], "confidence": -3}, _line(), cands).confidence == 0.0

    def test_missing_or_junk_confidence_is_zero_not_one(self):
        # Absent evidence of confidence is not evidence of confidence.
        cands = [_cand(1, "1000000.00")]
        assert validate_proposal({"transaction_ids": [1]}, _line(), cands).confidence == 0.0
        assert validate_proposal({"transaction_ids": [1], "confidence": "high"}, _line(), cands).confidence == 0.0


class ParseTests(SimpleTestCase):
    """Model replies are third-party text, not an API."""

    def test_plain_json(self):
        assert parse_response('{"proposals": [{"transaction_ids": [1]}]}') == [{"transaction_ids": [1]}]

    def test_fenced_json(self):
        text = '```json\n{"proposals": [{"transaction_ids": [2]}]}\n```'
        assert parse_response(text) == [{"transaction_ids": [2]}]

    def test_json_wrapped_in_prose(self):
        text = 'Here is my analysis.\n{"proposals": [{"transaction_ids": [3]}]}\nHope that helps.'
        assert parse_response(text) == [{"transaction_ids": [3]}]

    def test_unparseable_text_is_no_suggestion_not_an_error(self):
        # An outage in the middle of a reconciliation should degrade to
        # "no help offered", never to a traceback on the reviewer's screen.
        for junk in ("", "I could not determine a match.", "{not json", None):
            assert parse_response(junk) == []

    def test_an_explicit_empty_answer_is_honoured(self):
        assert parse_response('{"proposals": []}') == []

    def test_non_dict_entries_are_dropped(self):
        assert parse_response('{"proposals": [1, "x", {"transaction_ids": [4]}]}') == [{"transaction_ids": [4]}]


class PromptTests(SimpleTestCase):

    def test_the_prompt_carries_the_ids_the_model_may_use(self):
        cands = [_cand(7, "100.00"), _cand(9, "200.00")]
        prompt = build_prompt(_line(), cands)
        assert "id=7" in prompt and "id=9" in prompt
        assert "use only these ids" in prompt

    def test_the_prompt_states_the_direction(self):
        assert "money out" in build_prompt(_line(is_credit=True), [])
        assert "money in" in build_prompt(_line(is_credit=False), [])

    def test_an_empty_answer_is_invited(self):
        # Without this the model reaches for the least-bad guess, which is
        # the failure mode that makes the whole feature untrustworthy.
        assert "empty answer is a" in build_prompt(_line(), [])
