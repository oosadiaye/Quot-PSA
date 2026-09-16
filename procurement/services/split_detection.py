"""
Split-purchase and duplicate-payment detection.

``ProcurementThreshold`` already enforces the BPP ceilings: a goods order
above ₦2,500,000 leaves the Accounting Officer's authority and needs the
Parastatal Tenders Board. That rule works, and it is not the evasion.

The evasion is **three orders at ₦2,400,000 each**, to the same vendor,
in the same fortnight, with deliberately different descriptions — seven
million pounds of procurement that never left one officer's desk. Every
individual order passes every check, because each one is genuinely under
the ceiling. Only the pattern is wrong.

Work is split in two, and the split is the whole design:

**Finding is deterministic.** Clustering by vendor, window and threshold
is exact arithmetic over rows we already hold. It is cheap, it runs over
everything, it is explainable in a sentence to an auditor, and it never
hallucinates. No model is involved.

**Only judging is delegated.** Given a cluster the arithmetic already
found, is this one requirement deliberately divided, or three genuinely
separate needs that happen to fall near each other? That is the question
a rule cannot answer — the descriptions differ on purpose — and it runs
over a handful of clusters rather than the whole ledger.

Nothing here blocks anything. It advises, on transactions that have in
most cases already been paid, so the control risk is close to zero and
the value is entirely in what a reviewer is pointed at.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Iterable, Sequence

#: How close together orders must fall to be worth considering as one
#: divided requirement. A sliding window, deliberately — see
#: :func:`find_split_clusters`.
DEFAULT_WINDOW_DAYS = 30

#: Orders far below a ceiling are ordinary business. Flagging every pair
#: of small stationery orders that happen to cross a ceiling together
#: would bury the real findings, and a detector nobody reads is worse
#: than none. Only orders at or above this fraction of the ceiling are
#: treated as candidates for deliberate division.
DEFAULT_MATERIALITY = Decimal("0.25")


@dataclass(frozen=True)
class PurchaseRecord:
    """One order, as the detector sees it.

    A plain value object rather than a Django instance so the detection
    logic runs — and is tested — without a database.
    """

    purchase_id: int
    vendor_id: int
    vendor_name: str
    order_date: date
    amount: Decimal
    reference: str = ""
    description: str = ""
    category: str = "GOODS_SERVICES"


@dataclass(frozen=True)
class SplitCluster:
    """Orders that individually clear a ceiling but together do not."""

    vendor_id: int
    vendor_name: str
    purchase_ids: tuple[int, ...]
    total: Decimal
    ceiling: Decimal
    #: The authority the combined value would have required.
    escalates_to: str
    first_date: date
    last_date: date

    @property
    def span_days(self) -> int:
        return (self.last_date - self.first_date).days

    @property
    def excess(self) -> Decimal:
        return self.total - self.ceiling


@dataclass(frozen=True)
class DuplicatePair:
    """Two orders that look like the same obligation paid twice."""

    vendor_id: int
    vendor_name: str
    left_id: int
    right_id: int
    amount: Decimal
    difference: Decimal
    days_apart: int


@dataclass(frozen=True)
class Ceiling:
    """One rung of the BPP ladder, flattened for the detector."""

    category: str
    limit: Decimal
    #: Authority required once the limit is exceeded.
    escalates_to: str


# ── Split detection ──────────────────────────────────────────────────


def find_split_clusters(
    records: Sequence[PurchaseRecord],
    ceilings: Sequence[Ceiling],
    *,
    window_days: int = DEFAULT_WINDOW_DAYS,
    materiality: Decimal = DEFAULT_MATERIALITY,
) -> list[SplitCluster]:
    """Find orders that together should have escalated and did not.

    The window **slides from each order** rather than bucketing by
    calendar month. Bucketing is the obvious implementation and it is
    trivially evaded: orders on 30 January, 31 January and 1 February
    fall in two different months and the pattern disappears. Anyone
    dividing a requirement on purpose is watching the calendar.

    A cluster is reported only when **every member is individually under
    the ceiling**. An order already above it went through the higher
    authority, so a group containing one is not evasion — it is a large
    purchase with some small ones near it, and reporting it would train
    reviewers to dismiss the list.
    """
    clusters: dict[tuple, SplitCluster] = {}

    by_vendor: dict[int, list[PurchaseRecord]] = {}
    for rec in records:
        by_vendor.setdefault(rec.vendor_id, []).append(rec)

    for vendor_id, rows in by_vendor.items():
        rows = sorted(rows, key=lambda r: (r.order_date, r.purchase_id))
        for ceiling in ceilings:
            floor = ceiling.limit * materiality
            eligible = [
                r for r in rows
                if r.category == ceiling.category
                and r.amount <= ceiling.limit      # already-escalated orders excluded
                and r.amount >= floor
            ]
            for anchor in eligible:
                window_end = anchor.order_date + timedelta(days=window_days)
                group = [
                    r for r in eligible
                    if anchor.order_date <= r.order_date <= window_end
                ]
                if len(group) < 2:
                    continue
                total = sum((r.amount for r in group), Decimal("0"))
                if total <= ceiling.limit:
                    continue
                key = (vendor_id, ceiling.category, tuple(r.purchase_id for r in group))
                clusters.setdefault(key, SplitCluster(
                    vendor_id=vendor_id,
                    vendor_name=group[0].vendor_name,
                    purchase_ids=tuple(r.purchase_id for r in group),
                    total=total,
                    ceiling=ceiling.limit,
                    escalates_to=ceiling.escalates_to,
                    first_date=min(r.order_date for r in group),
                    last_date=max(r.order_date for r in group),
                ))

    deduped = _drop_subsets(list(clusters.values()))
    deduped.sort(key=lambda c: (-c.excess, c.vendor_id))
    return deduped


def _drop_subsets(clusters: list[SplitCluster]) -> list[SplitCluster]:
    """Keep the largest grouping and discard its subsets.

    Sliding a window from every order finds the same pattern several
    times over — anchored at the first order, then the second, and so on.
    Reporting all of them would show a reviewer the same three orders
    three times and make the list look larger than the problem.
    """
    kept: list[SplitCluster] = []
    for cluster in sorted(clusters, key=lambda c: -len(c.purchase_ids)):
        ids = set(cluster.purchase_ids)
        if any(
            ids < set(other.purchase_ids) or ids == set(other.purchase_ids)
            for other in kept
        ):
            continue
        kept.append(cluster)
    return kept


# ── Duplicate detection ──────────────────────────────────────────────


def find_duplicate_candidates(
    records: Sequence[PurchaseRecord],
    *,
    window_days: int = 45,
    tolerance: Decimal = Decimal("0.01"),
) -> list[DuplicatePair]:
    """Same vendor, near-identical amount, close together, different refs.

    ``tolerance`` is a fraction, not an absolute: a duplicate re-keyed by
    hand tends to differ by a rounding or a transposed minor unit, and
    that error scales with the figure. A flat naira tolerance would miss
    duplicates on large contracts and flood on small ones.

    Orders sharing a reference are **not** reported. An identical
    reference is the same document seen twice — a data-entry or import
    artefact, not two payments — and mixing those into a duplicate-payment
    report is how the report loses its audience.
    """
    pairs: list[DuplicatePair] = []
    by_vendor: dict[int, list[PurchaseRecord]] = {}
    for rec in records:
        by_vendor.setdefault(rec.vendor_id, []).append(rec)

    for rows in by_vendor.values():
        rows = sorted(rows, key=lambda r: (r.order_date, r.purchase_id))
        for i, left in enumerate(rows):
            for right in rows[i + 1:]:
                gap = (right.order_date - left.order_date).days
                if gap > window_days:
                    break                      # sorted: nothing later is closer
                if left.reference and left.reference == right.reference:
                    continue
                if left.amount <= 0 or right.amount <= 0:
                    continue
                difference = abs(left.amount - right.amount)
                if difference > left.amount * tolerance:
                    continue
                pairs.append(DuplicatePair(
                    vendor_id=left.vendor_id,
                    vendor_name=left.vendor_name,
                    left_id=left.purchase_id,
                    right_id=right.purchase_id,
                    amount=left.amount,
                    difference=difference,
                    days_apart=gap,
                ))

    pairs.sort(key=lambda p: (-p.amount, p.days_apart))
    return pairs


# ── Prompt for the judging step ──────────────────────────────────────


def build_cluster_prompt(
    cluster: SplitCluster,
    records: Iterable[PurchaseRecord],
) -> str:
    """Ask whether a cluster is one divided requirement or several real ones.

    The arithmetic is stated rather than asked for — the model is not
    being invited to recompute a total we already know, only to read the
    descriptions. Asking it to do both would let a confident arithmetic
    error arrive dressed as a finding.
    """
    by_id = {r.purchase_id: r for r in records}
    lines = "\n".join(
        f"  - {by_id[i].order_date.isoformat()} {by_id[i].amount} "
        f"ref={by_id[i].reference or '-'} :: {(by_id[i].description or '-')[:120]}"
        for i in cluster.purchase_ids if i in by_id
    )
    return (
        f"{len(cluster.purchase_ids)} purchase orders were raised to "
        f"{cluster.vendor_name} within {cluster.span_days} days. Each is below "
        f"the {cluster.ceiling} approval ceiling. Together they total "
        f"{cluster.total}, which would have required {cluster.escalates_to} "
        f"approval.\n\nORDERS\n{lines}\n\n"
        "These figures are already verified — do not recalculate them. Judge "
        "only the descriptions: do they read as ONE requirement divided to stay "
        "under the ceiling, or as genuinely separate needs that happen to fall "
        "close together?\n\n"
        "Ordinary recurring supply to a regular vendor is normal and should be "
        "called SEPARATE. Say so plainly when that is the answer — a detector "
        "that flags everything gets switched off.\n\n"
        'Reply with JSON only:\n'
        '{"verdict": "DIVIDED" | "SEPARATE" | "UNCLEAR", '
        '"confidence": 0.0-1.0, "reason": "one sentence"}'
    )


VERDICTS = ("DIVIDED", "SEPARATE", "UNCLEAR")


# ── Loading (needs a database) ───────────────────────────────────────


#: Orders that represent a commitment. Draft and Rejected never bound the
#: organisation to anything, so including them would report intentions as
#: findings.
COMMITTED_STATUSES = ("Approved", "Posted", "Closed")


def load_ceilings() -> list[Ceiling]:
    """Flatten ``ProcurementThreshold`` into the rungs the detector uses.

    The table stores bands (0–2.5m Accounting Officer, 2.5m–10m PTB, …).
    What matters here is the **edge**: the value at which authority
    changes hands, and who it changes to. So each band's ``max_amount``
    becomes a ceiling, labelled with the authority of the band above it.

    Read from the table rather than hard-coded because BPP revises these
    by circular, and a detector quoting a superseded figure would be
    reporting against a rule nobody is breaking.
    """
    from procurement.models import ProcurementThreshold

    ceilings: list[Ceiling] = []
    rows = list(
        ProcurementThreshold.objects
        .filter(is_active=True)
        .order_by("category", "min_amount")
    )
    by_category: dict[str, list] = {}
    for row in rows:
        by_category.setdefault(row.category, []).append(row)

    for category, band in by_category.items():
        for lower, upper in zip(band, band[1:]):
            if lower.max_amount is None:
                continue
            ceilings.append(Ceiling(
                category=category,
                limit=Decimal(str(lower.max_amount)),
                escalates_to=upper.authority_level,
            ))
    return ceilings


def load_purchases(*, since: date, until: date) -> list[PurchaseRecord]:
    """Committed purchase orders in a date range.

    ``PurchaseOrder.total_amount`` is a **property** computed from the
    order's lines, not a column, so it cannot be filtered or summed in
    SQL. The range therefore has to bound the work instead — which is
    also why callers pass one rather than scanning the whole ledger.
    """
    from procurement.models import PurchaseOrder

    rows = (
        PurchaseOrder.objects
        .filter(
            status__in=COMMITTED_STATUSES,
            order_date__gte=since,
            order_date__lte=until,
        )
        .select_related("vendor")
        .prefetch_related("lines")
    )

    records: list[PurchaseRecord] = []
    for po in rows:
        if po.vendor_id is None:
            continue
        records.append(PurchaseRecord(
            purchase_id=po.id,
            vendor_id=po.vendor_id,
            vendor_name=str(po.vendor),
            order_date=po.order_date,
            amount=Decimal(str(po.total_amount or 0)),
            reference=po.po_number or "",
            description=(po.notes or "")[:300],
            category=_category_for(po),
        ))
    return records


def _category_for(po) -> str:
    """Which BPP ladder an order is judged against.

    Falls back to goods and services, which is the lowest ceiling of the
    three and therefore the conservative default: it flags more, and a
    reviewer dismissing a wrongly-categorised cluster costs far less than
    a works contract judged against a ceiling five times too high.
    """
    purchase_type = getattr(po, "purchase_type", None)
    name = (str(getattr(purchase_type, "name", "")) or "").upper()
    if "WORK" in name or "CONSTRUCT" in name:
        return "WORKS"
    if "CONSULT" in name:
        return "CONSULTANCY"
    return "GOODS_SERVICES"


def detect(
    *,
    since: date,
    until: date,
    tenant=None,
    setting=None,
    judge_limit: int = 10,
) -> dict:
    """Run both detectors, and optionally have a model judge the clusters.

    The arithmetic runs regardless. Judging is an enhancement layered on
    top: when AI is switched off, unconfigured or unreachable, every
    cluster still appears with verdict UNCLEAR and the report is still
    worth reading. A control that stops working because a third party is
    down is not a control.
    """
    records = load_purchases(since=since, until=until)
    ceilings = load_ceilings()
    clusters = find_split_clusters(records, ceilings)
    duplicates = find_duplicate_candidates(records)

    usable = bool(setting is not None and getattr(setting, "is_usable", False))
    judged: list[dict] = []

    for cluster in clusters:
        verdict = {"verdict": "UNCLEAR", "confidence": 0.0, "reason": ""}
        if usable and len(judged) < judge_limit:
            verdict = _judge(cluster, records, tenant, setting)
        judged.append({
            "vendor_id": cluster.vendor_id,
            "vendor_name": cluster.vendor_name,
            "purchase_ids": list(cluster.purchase_ids),
            "total": str(cluster.total),
            "ceiling": str(cluster.ceiling),
            "excess": str(cluster.excess),
            "escalates_to": cluster.escalates_to,
            "first_date": cluster.first_date.isoformat(),
            "last_date": cluster.last_date.isoformat(),
            "span_days": cluster.span_days,
            **verdict,
        })

    return {
        "window": {"since": since.isoformat(), "until": until.isoformat()},
        "orders_examined": len(records),
        "ai_judging": usable,
        "split_clusters": judged,
        "duplicate_candidates": [
            {
                "vendor_id": d.vendor_id,
                "vendor_name": d.vendor_name,
                "purchase_ids": [d.left_id, d.right_id],
                "amount": str(d.amount),
                "difference": str(d.difference),
                "days_apart": d.days_apart,
            }
            for d in duplicates
        ],
    }


def _judge(cluster, records, tenant, setting) -> dict:
    """One judging call. Never raises — see :func:`detect`."""
    from superadmin.ai_client import call_model

    try:
        result = call_model(
            tenant=tenant,
            setting=setting,
            prompt=build_cluster_prompt(cluster, records),
            system=(
                "You review Nigerian public-sector procurement for threshold "
                "evasion. You advise; a procurement officer decides. Ordinary "
                "recurring supply is normal — say SEPARATE when it is."
            ),
            max_tokens=400,
            subject={"model": "PurchaseOrderCluster",
                     "ids": list(cluster.purchase_ids)},
        )
    except Exception:                                 # noqa: BLE001
        return {"verdict": "UNCLEAR", "confidence": 0.0,
                "reason": "The AI provider could not be reached."}
    return parse_verdict(result.text)


def parse_verdict(text: str) -> dict:
    """Read a judgement, defaulting to UNCLEAR.

    An unreadable reply must not become a finding. UNCLEAR keeps the
    cluster in front of a reviewer — the arithmetic that found it stands
    on its own — without attributing an opinion to a model that did not
    give one.
    """
    import json
    import re

    fallback = {"verdict": "UNCLEAR", "confidence": 0.0, "reason": ""}
    if not text:
        return fallback
    blob = text.strip()
    if blob.startswith("```"):
        blob = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", blob).strip()
    match = re.search(r"\{.*\}", blob, re.DOTALL)
    if not match:
        return fallback
    try:
        data = json.loads(match.group(0))
    except (ValueError, TypeError):
        return fallback
    if not isinstance(data, dict):
        return fallback
    verdict = str(data.get("verdict", "")).upper()
    if verdict not in VERDICTS:
        return fallback
    try:
        confidence = max(0.0, min(1.0, float(data.get("confidence", 0))))
    except (TypeError, ValueError):
        confidence = 0.0
    return {
        "verdict": verdict,
        "confidence": confidence,
        "reason": str(data.get("reason", ""))[:400],
    }
