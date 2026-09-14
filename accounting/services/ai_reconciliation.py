"""
AI-assisted bank reconciliation — the residue only.

``BankReconciliationService.find_match_candidates`` filters GL
transactions on ``total_amount=amount`` **exactly**, within a five-day
window. That is a good rule and it should keep everything it already
wins. What it cannot see, by construction, is every case where the bank
figure and the ledger figure legitimately differ:

  * a **bundle** — one bank debit covering several payment vouchers;
  * a **partial** — a payment settled in tranches;
  * a **fee adjustment** — the transfer minus a bank charge;
  * a **date drift** beyond the window.

Those land in the unmatched pile and become somebody's afternoon. This
module proposes answers for that pile and nothing else, so the rule
engine's output is never second-guessed and the cost is bounded by the
size of the residue rather than the size of the statement.

**Nothing here matches anything.** Every output is a proposal carrying
its own arithmetic, for a named officer to accept in the existing
reconciliation screen. That is not decoration: a wrong proposal costs
seconds of review, a wrong auto-match costs a reconciliation that ties
out to the wrong number and is discovered at year end.

The validation layer is the point of this file. A language model asked
for a bundle will occasionally invent a voucher id, repeat one twice, or
assert a total that does not add up — so nothing it returns is trusted:
ids are checked against the candidate set we supplied, and **the total is
recomputed from our own records** rather than read from the reply.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Iterable, Sequence

#: How far a proposal's recomputed total may sit from the bank line and
#: still be called a fee adjustment rather than a partial settlement.
#: Nigerian interbank transfer charges are small and capped; anything
#: larger is a different kind of difference and must be labelled as one.
DEFAULT_FEE_TOLERANCE = Decimal("5000.00")

#: Ceiling on how many candidates are put in front of a model at once.
#: Not a cost control — a correctness one. A long list invites the model
#: to assemble a plausible-looking bundle out of unrelated vouchers.
MAX_CANDIDATES = 40


class Kind:
    """What sort of difference a proposal is claiming to explain."""

    ONE_TO_ONE = "ONE_TO_ONE"
    BUNDLE = "BUNDLE"
    PARTIAL = "PARTIAL"
    FEE_ADJUSTED = "FEE_ADJUSTED"


class Reject:
    """Why a proposal was thrown away before any human saw it."""

    UNKNOWN_ID = "unknown_transaction_id"
    DUPLICATE_ID = "duplicate_transaction_id"
    ALREADY_MATCHED = "already_matched_elsewhere"
    NO_IDS = "no_transaction_ids"
    WRONG_DIRECTION = "wrong_direction"
    UNEXPLAINED_VARIANCE = "unexplained_variance"
    MALFORMED = "malformed_proposal"


@dataclass(frozen=True)
class CandidateRecord:
    """A GL transaction offered to the model as a possible match.

    Deliberately a plain value object rather than a Django instance: the
    validation below must be runnable — and testable — without a database.
    """

    transaction_id: int
    transaction_type: str          # PAYMENT | RECEIPT
    transaction_date: date
    amount: Decimal
    reference: str = ""
    description: str = ""


#: Which way the money moved. Carried as meaning rather than as a raw
#: column flag on purpose: this codebase has two statement models whose
#: conventions are **opposite**. ``BankStatementLine`` treats a credit as
#: money leaving; ``TSABankStatementLine`` treats a debit as money leaving
#: (its parser maps "withdrawal" to debit). Passing ``is_credit`` through
#: to shared logic would mean one of the two stacks proposed revenue
#: against outgoing transfers — plausibly, and in the right currency.
#: Each adapter states its own mapping once, here.
OUT = "OUT"   # money left the bank account -> settled by a payment
IN = "IN"     # money arrived -> explained by a receipt / revenue


@dataclass(frozen=True)
class StatementLineRecord:
    """The unmatched bank line a proposal is about."""

    line_id: int
    transaction_date: date
    amount: Decimal
    direction: str                 # OUT | IN — see the note above
    description: str = ""
    reference: str = ""


@dataclass(frozen=True)
class Proposal:
    """A validated suggestion. Still only a suggestion."""

    line_id: int
    transaction_ids: tuple[int, ...]
    transaction_type: str
    kind: str
    confidence: float
    explanation: str
    #: Recomputed from our own records — never the model's stated figure.
    proposed_total: Decimal
    line_amount: Decimal
    variance: Decimal

    @property
    def is_exact(self) -> bool:
        return self.variance == 0


@dataclass(frozen=True)
class Rejected:
    """A proposal that did not survive validation, and why."""

    line_id: int
    reason: str
    detail: str = ""
    raw: dict = field(default_factory=dict)


# ── Prompt ───────────────────────────────────────────────────────────


def expected_direction(line: StatementLineRecord) -> str:
    """Which ledger side can possibly explain this bank line.

    Money out is settled by a payment; money in is explained by a
    receipt. Enforcing this after the model replies is what stops a
    tidy-looking bundle of receipts being offered against an outgoing
    transfer — and the adapters, not this function, are where each
    statement model's debit/credit convention is interpreted.
    """
    return "PAYMENT" if line.direction == OUT else "RECEIPT"


def build_prompt(
    line: StatementLineRecord,
    candidates: Sequence[CandidateRecord],
) -> str:
    """Describe one unmatched line and its candidate pool.

    Amounts, dates and document references are included on purpose. They
    are the entire basis for reasoning about a bundle or a bank charge,
    and redaction — applied downstream by the AI gateway — removes
    identity (bank accounts, BVN, TIN), not the transaction.
    """
    rows = "\n".join(
        f"  - id={c.transaction_id} type={c.transaction_type} "
        f"date={c.transaction_date.isoformat()} amount={c.amount} "
        f"ref={c.reference or '-'} desc={(c.description or '-')[:80]}"
        for c in candidates
    )
    return (
        "A bank statement line could not be matched automatically because no "
        "single ledger transaction has exactly its amount.\n\n"
        f"BANK LINE\n"
        f"  date: {line.transaction_date.isoformat()}\n"
        f"  amount: {line.amount}\n"
        f"  direction: {'money out' if line.direction == OUT else 'money in'}\n"
        f"  description: {line.description or '-'}\n"
        f"  reference: {line.reference or '-'}\n\n"
        f"CANDIDATE LEDGER TRANSACTIONS (use only these ids)\n{rows or '  (none)'}\n\n"
        "Decide whether some combination of the candidates explains the bank "
        "line. Typical causes: several vouchers paid in one transfer (BUNDLE), "
        "a payment settled in tranches (PARTIAL), or the transfer minus a bank "
        "charge (FEE_ADJUSTED). If nothing fits, say so — an empty answer is a "
        "correct answer and is far more useful than a guess.\n\n"
        "Reply with JSON only:\n"
        '{"proposals": [{"transaction_ids": [1,2], "kind": "BUNDLE", '
        '"confidence": 0.0-1.0, "explanation": "one sentence"}]}'
    )


# ── Parsing ──────────────────────────────────────────────────────────


_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


def parse_response(text: str) -> list[dict]:
    """Pull proposals out of a model reply.

    Tolerant by design: models wrap JSON in prose or fences often enough
    that a strict parse would turn a good answer into an outage. Anything
    that cannot be read yields an empty list — which the caller treats as
    "no suggestion", the safe reading.
    """
    if not text:
        return []
    blob = text.strip()
    if blob.startswith("```"):
        blob = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", blob).strip()
    match = _JSON_BLOCK.search(blob)
    if not match:
        return []
    try:
        data = json.loads(match.group(0))
    except (ValueError, TypeError):
        return []
    proposals = data.get("proposals") if isinstance(data, dict) else None
    if not isinstance(proposals, list):
        return []
    return [p for p in proposals if isinstance(p, dict)]


def _as_decimal(value) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _as_confidence(value) -> float:
    """Clamp to [0, 1]. A model claiming 1.4 confidence is still a model."""
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


# ── Validation — the part that matters ───────────────────────────────


def validate_proposal(
    raw: dict,
    line: StatementLineRecord,
    candidates: Sequence[CandidateRecord],
    *,
    already_matched: Iterable[int] = (),
    fee_tolerance: Decimal = DEFAULT_FEE_TOLERANCE,
) -> Proposal | Rejected:
    """Turn one raw suggestion into a Proposal, or explain why not.

    Every check here exists because a model can produce output that looks
    entirely reasonable and is wrong in a way a reviewer would not catch
    by eye — an id that was never offered, the same voucher counted
    twice, or a stated total that simply does not add up.
    """
    by_id = {c.transaction_id: c for c in candidates}
    matched = set(already_matched)

    ids_raw = raw.get("transaction_ids")
    if not isinstance(ids_raw, list) or not ids_raw:
        return Rejected(line.line_id, Reject.NO_IDS, raw=raw)

    ids: list[int] = []
    for value in ids_raw:
        try:
            ids.append(int(value))
        except (TypeError, ValueError):
            return Rejected(line.line_id, Reject.MALFORMED, f"bad id {value!r}", raw)

    if len(set(ids)) != len(ids):
        # Double-counting a voucher is the easiest way to make a bundle
        # appear to add up, and the hardest to spot in a list of figures.
        return Rejected(line.line_id, Reject.DUPLICATE_ID, raw=raw)

    unknown = [i for i in ids if i not in by_id]
    if unknown:
        # The model was given the only ids it may use. Anything else is
        # invented, and an invented voucher number that happens to exist
        # elsewhere in the ledger is worse than one that does not.
        return Rejected(line.line_id, Reject.UNKNOWN_ID, f"ids {unknown}", raw)

    clash = [i for i in ids if i in matched]
    if clash:
        # One ledger transaction cannot settle two bank lines.
        return Rejected(line.line_id, Reject.ALREADY_MATCHED, f"ids {clash}", raw)

    want = expected_direction(line)
    wrong = [i for i in ids if by_id[i].transaction_type != want]
    if wrong:
        return Rejected(line.line_id, Reject.WRONG_DIRECTION, f"ids {wrong}", raw)

    # The arithmetic is ours. The model may state a total; we do not read
    # it. Decimal throughout — this is money.
    total = sum((by_id[i].amount for i in ids), Decimal("0"))
    variance = line.amount - total

    kind = _classify(variance, len(ids), fee_tolerance)
    if kind is None:
        return Rejected(
            line.line_id,
            Reject.UNEXPLAINED_VARIANCE,
            f"line {line.amount} vs candidates {total} (variance {variance})",
            raw,
        )

    return Proposal(
        line_id=line.line_id,
        transaction_ids=tuple(ids),
        transaction_type=want,
        kind=kind,
        confidence=_as_confidence(raw.get("confidence")),
        explanation=str(raw.get("explanation", ""))[:500],
        proposed_total=total,
        line_amount=line.amount,
        variance=variance,
    )


def _classify(variance: Decimal, id_count: int, fee_tolerance: Decimal) -> str | None:
    """Name the difference, or refuse to.

    The model's own ``kind`` is ignored. It is a label for something the
    arithmetic already determines, and letting the reply choose it would
    mean a confident mislabel could carry a variance past review.
    """
    # ``variance = line.amount - total``, so it is NEGATIVE when the bank
    # moved less than the vouchers account for. Worth stating plainly:
    # getting this sign backwards silently swaps "the bank underpaid"
    # for "the bank overpaid", which are opposite findings.
    if variance == 0:
        return Kind.BUNDLE if id_count > 1 else Kind.ONE_TO_ONE
    if variance > 0:
        # The bank moved MORE than the vouchers authorise. There is no
        # benign story for that, so it is not proposed at all — offering
        # a tidy explanation would invite someone to accept it.
        return None
    shortfall = -variance
    if shortfall <= fee_tolerance:
        # A charge was deducted in transit.
        return Kind.FEE_ADJUSTED
    # Materially less than the obligation: settled in part.
    return Kind.PARTIAL


def validate_all(
    raws: Sequence[dict],
    line: StatementLineRecord,
    candidates: Sequence[CandidateRecord],
    *,
    already_matched: Iterable[int] = (),
    fee_tolerance: Decimal = DEFAULT_FEE_TOLERANCE,
) -> tuple[list[Proposal], list[Rejected]]:
    """Validate a batch, keeping each proposal's ids exclusive.

    A single reply can contain two proposals that both spend the same
    voucher. Accepting both would present a reviewer with a contradiction
    and let either one be clicked.
    """
    accepted: list[Proposal] = []
    rejected: list[Rejected] = []
    claimed = set(already_matched)

    for raw in raws:
        result = validate_proposal(
            raw, line, candidates,
            already_matched=claimed, fee_tolerance=fee_tolerance,
        )
        if isinstance(result, Proposal):
            accepted.append(result)
            claimed.update(result.transaction_ids)
        else:
            rejected.append(result)

    accepted.sort(key=lambda p: (p.variance != 0, -p.confidence))
    return accepted, rejected


# ── Orchestration (needs a database and a provider) ──────────────────


def gather_candidates(
    line,
    bank_account_id: int,
    *,
    window_days: int = 30,
    limit: int = MAX_CANDIDATES,
) -> list[CandidateRecord]:
    """The pool for one unmatched line.

    Two deliberate differences from ``find_match_candidates``:

    * **no exact-amount filter** — that is the entire reason this line is
      unmatched, so applying it again would return the empty set;
    * **a wider date window** — date drift is one of the causes being
      investigated, so the window that failed is not the one to search.

    Transactions already reconciled against another line are excluded
    here rather than merely rejected later, so the model never sees them
    and cannot build a bundle that has to be thrown away.
    """
    from datetime import timedelta

    from accounting.models import BankStatementLine, Payment, Receipt

    is_credit = line.direction == OUT
    lo = line.transaction_date - timedelta(days=window_days)
    hi = line.transaction_date + timedelta(days=window_days)

    spoken_for = set(
        BankStatementLine.objects
        .filter(
            match_status="MATCHED",
            matched_transaction_type="PAYMENT" if is_credit else "RECEIPT",
        )
        .values_list("matched_transaction_id", flat=True)
    )

    if is_credit:
        rows = Payment.objects.filter(
            bank_account_id=bank_account_id, status="Posted",
            payment_date__gte=lo, payment_date__lte=hi,
        ).exclude(total_amount=line.amount).exclude(id__in=spoken_for)
        return [
            CandidateRecord(
                transaction_id=p.id, transaction_type="PAYMENT",
                transaction_date=p.payment_date, amount=p.total_amount,
                reference=p.reference_number or p.payment_number or "",
                description=getattr(p, "description", "") or "",
            )
            for p in rows[:limit]
        ]

    rows = Receipt.objects.filter(
        bank_account_id=bank_account_id, status="Posted",
        receipt_date__gte=lo, receipt_date__lte=hi,
    ).exclude(total_amount=line.amount).exclude(id__in=spoken_for)
    return [
        CandidateRecord(
            transaction_id=r.id, transaction_type="RECEIPT",
            transaction_date=r.receipt_date, amount=r.total_amount,
            reference=r.reference_number or r.receipt_number or "",
            description=getattr(r, "description", "") or "",
        )
        for r in rows[:limit]
    ]


def to_line_record(line) -> StatementLineRecord:
    """Adapt a ``BankStatementLine``.

    This model's convention: ``is_credit`` True means money **left** the
    account — which ``find_match_candidates`` encodes by looking for
    Payments on a credit. Unusual, and the opposite of the TSA model, so
    it is translated here rather than carried further.
    """
    return StatementLineRecord(
        line_id=line.id,
        transaction_date=line.transaction_date,
        amount=line.amount,
        direction=OUT if line.is_credit else IN,
        description=line.description or "",
        reference=line.reference or "",
    )


def tsa_to_line_record(line) -> StatementLineRecord:
    """Adapt a ``TSABankStatementLine``.

    This model's convention is the ordinary banking one and the reverse
    of the above: a **debit** is money leaving, which is why its importer
    maps "withdrawal" to debit and its lines settle against a
    ``PaymentInstruction``.
    """
    debit = line.debit or Decimal("0")
    credit = line.credit or Decimal("0")
    return StatementLineRecord(
        line_id=line.id,
        transaction_date=line.transaction_date,
        amount=debit if debit else credit,
        direction=OUT if debit else IN,
        description=line.description or "",
        reference=line.reference or "",
    )


def tsa_gather_candidates(
    line: StatementLineRecord,
    statement,
    *,
    window_days: int = 30,
    limit: int = MAX_CANDIDATES,
) -> list[CandidateRecord]:
    """Candidate pool for a TSA statement line.

    Same two departures from the auto-matcher as the other stack: no
    exact-amount filter (that is why the line is unmatched) and a wider
    date window (drift is one of the causes under investigation). Rows
    already linked to another line are excluded before the model sees
    them — the model cannot propose what it is never shown.
    """
    from datetime import timedelta

    from accounting.models import PaymentInstruction, RevenueCollection

    lo = line.transaction_date - timedelta(days=window_days)
    hi = line.transaction_date + timedelta(days=window_days)
    tsa = statement.tsa_account

    # Scope, status and date field are taken from the auto-matcher in
    # ``tsa_bank_reconciliation`` rather than reinvented — a pool assembled
    # on different rules than the one that already ran would be proposing
    # from a different ledger than the reconciliation is about.
    if line.direction == OUT:
        taken = set(
            statement.lines.exclude(matched_payment__isnull=True)
            .values_list("matched_payment_id", flat=True)
        )
        rows = (
            PaymentInstruction.objects
            .filter(
                tsa_account=tsa,
                status="PROCESSED",
                processed_at__date__gte=lo,
                processed_at__date__lte=hi,
            )
            .exclude(id__in=taken)
            .exclude(amount=line.amount)      # the rule matcher owns these
        )
        return [
            CandidateRecord(
                transaction_id=p.id, transaction_type="PAYMENT",
                transaction_date=p.processed_at.date() if p.processed_at else line.transaction_date,
                amount=p.amount,
                reference=p.bank_reference or p.batch_reference or "",
                description=p.narration or p.beneficiary_name or "",
            )
            for p in rows[:limit]
        ]

    taken = set(
        statement.lines.exclude(matched_revenue__isnull=True)
        .values_list("matched_revenue_id", flat=True)
    )
    rows = (
        RevenueCollection.objects
        .filter(
            tsa_account=tsa,
            status__in=["POSTED", "RECONCILED"],
            collection_date__gte=lo,
            collection_date__lte=hi,
        )
        .exclude(id__in=taken)
        .exclude(amount=line.amount)
    )
    return [
        CandidateRecord(
            transaction_id=r.id, transaction_type="RECEIPT",
            transaction_date=r.collection_date,
            amount=r.amount,
            reference=r.receipt_number or r.payment_reference or "",
            description=r.description or "",
        )
        for r in rows[:limit]
    ]


def propose_for_line(
    *,
    tenant,
    setting,
    line,
    bank_account_id: int,
    window_days: int = 30,
    fee_tolerance: Decimal = DEFAULT_FEE_TOLERANCE,
) -> dict:
    """Ask the configured model to explain one unmatched line.

    Returns a plain dict so the caller can serialise it without knowing
    about dataclasses. Raises nothing on a model failure — an outage
    during a reconciliation should degrade to "no suggestion offered",
    not to a traceback on the reviewer's screen.
    """
    from superadmin.ai_client import AIRefused, call_model

    record = to_line_record(line)
    candidates = gather_candidates(
        record, bank_account_id, window_days=window_days,
    )
    if not candidates:
        return {
            "line_id": record.line_id, "proposals": [], "rejected": [],
            "detail": "No candidate transactions in the search window.",
        }

    try:
        result = call_model(
            tenant=tenant,
            setting=setting,
            prompt=build_prompt(record, candidates),
            system=(
                "You reconcile Nigerian public-sector bank statements. You "
                "propose; a finance officer decides. Never guess: replying "
                "with no proposals is correct when nothing fits."
            ),
            max_tokens=800,
            subject={"model": "BankStatementLine", "id": record.line_id},
        )
    except AIRefused as exc:
        return {
            "line_id": record.line_id, "proposals": [], "rejected": [],
            "detail": str(exc),
        }
    except Exception as exc:                      # noqa: BLE001
        return {
            "line_id": record.line_id, "proposals": [], "rejected": [],
            "detail": f"The AI provider could not be reached: {str(exc)[:200]}",
        }

    accepted, rejected = validate_all(
        parse_response(result.text), record, candidates,
        fee_tolerance=fee_tolerance,
    )
    return {
        "line_id": record.line_id,
        "candidates_considered": len(candidates),
        "proposals": [
            {
                "transaction_ids": list(p.transaction_ids),
                "transaction_type": p.transaction_type,
                "kind": p.kind,
                "confidence": p.confidence,
                "explanation": p.explanation,
                "proposed_total": str(p.proposed_total),
                "line_amount": str(p.line_amount),
                "variance": str(p.variance),
            }
            for p in accepted
        ],
        # Surfaced rather than swallowed: a run where most suggestions were
        # discarded as invented ids is a fact about the model that whoever
        # chose it needs to see.
        "rejected": [{"reason": r.reason, "detail": r.detail} for r in rejected],
        "cost_usd": str(result.cost_usd),
        "call_id": result.call_id,
    }
