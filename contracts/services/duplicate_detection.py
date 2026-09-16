"""
Duplicate contract and duplicate invoice detection.

The database constraints added alongside this file stop the *mechanical*
duplicate: the same vendor invoice number twice, two live payment
vouchers citing one source document. They cannot see the duplicate that
actually costs money, because it does not repeat any single field.

A contract captured twice gets two auto-generated contract numbers — the
`unique=True` on `contract_number` is satisfied by construction and
therefore protects nothing. What repeats is the *substance*: same
contractor, same money, same window, and a title that is recognisably
the same requirement written out differently.

    "Rehabilitation of Asaba-Ughelli Road (Phase 2)"
    "Rehab of Asaba Ughelli Rd Phase II"

Finding that is string comparison, not machine learning, and this module
is deliberate about saying so. Token overlap over normalised titles is
explainable to an auditor in one sentence — "these two share 86% of
their significant words, here they are" — which matters more here than a
percentage point of accuracy would.

Everything is pure: value objects in, findings out, no database and no
model. The loaders at the bottom adapt Django rows into those objects.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Sequence

#: Two contracts must be at least this similar by title to be reported.
#: Tuned low rather than high on purpose: this warns a clerk at draft,
#: where a false positive costs a glance and a miss costs a duplicated
#: contract nobody looks for again.
DEFAULT_MIN_SIMILARITY = 0.55

#: How far apart two contract values may sit and still be the same
#: contract re-keyed. Proportional, because a transposition error scales
#: with the figure.
DEFAULT_VALUE_TOLERANCE = Decimal("0.02")

#: Contracts signed further apart than this are unlikely to be a
#: double capture of one award, however similar the wording.
DEFAULT_WINDOW_DAYS = 365

#: Words that carry no distinguishing signal in Nigerian public-sector
#: contract titles. Dropping them is what makes "Supply of desks" and
#: "Supply of chairs" score zero instead of 0.5 on the shared "supply of".
_STOPWORDS = frozenset("""
a an and at by for from in into of on or the to with within
contract project works work supply provision procurement services service
lot phase part tranche batch
""".split())

#: Abbreviations seen routinely in MDA contract registers. An explicit
#: map is honest about its own limits — it expands what it knows and
#: silently leaves the rest, rather than pretending to understand text.
_EXPANSIONS = {
    "rd": "road", "rds": "roads",
    "rehab": "rehabilitation", "rehabil": "rehabilitation",
    "constr": "construction", "constrn": "construction",
    "maint": "maintenance",
    "govt": "government", "gov": "government",
    "sch": "school", "schs": "schools",
    "hosp": "hospital",
    "ltd": "limited", "nig": "nigeria",
    "st": "street", "ave": "avenue",
    "bldg": "building", "blg": "building",
    "equip": "equipment",
    "i": "1", "ii": "2", "iii": "3", "iv": "4", "v": "5",
}


@dataclass(frozen=True)
class ContractRecord:
    """One contract as the detector sees it."""

    contract_id: int
    contract_number: str
    vendor_id: int
    vendor_name: str
    title: str
    value: Decimal
    signed_date: date
    status: str = ""


@dataclass(frozen=True)
class InvoiceRecord:
    """One vendor invoice as the detector sees it."""

    invoice_id: int
    invoice_number: str
    vendor_id: int
    vendor_name: str
    amount: Decimal
    invoice_date: date
    description: str = ""


@dataclass(frozen=True)
class DuplicateContract:
    """Two contracts that may be one award captured twice."""

    left_id: int
    right_id: int
    left_number: str
    right_number: str
    vendor_id: int
    vendor_name: str
    similarity: float
    #: The significant words both titles share — the evidence, shown to
    #: the reviewer rather than summarised into a score they must trust.
    shared_terms: tuple[str, ...]
    value_difference: Decimal
    days_apart: int


@dataclass(frozen=True)
class DuplicateInvoice:
    """Two invoices that may be one obligation billed twice."""

    left_id: int
    right_id: int
    left_number: str
    right_number: str
    vendor_id: int
    vendor_name: str
    amount: Decimal
    difference: Decimal
    days_apart: int


# ── Title normalisation and similarity ───────────────────────────────


_PUNCT = re.compile(r"[^\w\s]")
_SPACE = re.compile(r"\s+")


def normalise_title(text: str) -> tuple[str, ...]:
    """Reduce a title to its significant words.

    Accents are folded, punctuation dropped, roman numerals and common
    MDA abbreviations expanded, stopwords removed. The result is a
    *set-like* tuple: order carries no meaning here, because "Asaba Road
    Rehabilitation" and "Rehabilitation of Asaba Road" are the same
    requirement.
    """
    if not text:
        return ()
    folded = unicodedata.normalize("NFKD", text)
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    # Hyphens and en/em dashes need no special handling: ``_PUNCT`` matches
    # any non-word, non-space character, so "Asaba-Ughelli" and
    # "Asaba–Ughelli" both become two words here. Kept as a note rather
    # than a redundant replace() that would look load-bearing to the next
    # reader — the behaviour is pinned by the dash tests.
    words = _SPACE.sub(" ", _PUNCT.sub(" ", folded.lower())).strip().split()

    out: list[str] = []
    for word in words:
        word = _EXPANSIONS.get(word, word)
        if word in _STOPWORDS or not word:
            continue
        out.append(word)
    return tuple(sorted(set(out)))


def title_similarity(left: str, right: str) -> tuple[float, tuple[str, ...]]:
    """Jaccard overlap of significant words, with the shared words.

    Jaccard rather than cosine over term frequency: contract titles are
    short and repetition is meaningless in them, so weighting a word
    twice because it appears twice would add noise, not signal. It also
    has the property that matters most here — an auditor can recompute
    it by hand from the two word lists.
    """
    a, b = set(normalise_title(left)), set(normalise_title(right))
    if not a or not b:
        return 0.0, ()
    shared = a & b
    union = a | b
    return len(shared) / len(union), tuple(sorted(shared))


# ── Detection ────────────────────────────────────────────────────────


def find_duplicate_contracts(
    records: Sequence[ContractRecord],
    *,
    min_similarity: float = DEFAULT_MIN_SIMILARITY,
    value_tolerance: Decimal = DEFAULT_VALUE_TOLERANCE,
    window_days: int = DEFAULT_WINDOW_DAYS,
) -> list[DuplicateContract]:
    """Contracts to the same vendor that look like one award twice.

    All three signals must agree — same vendor, similar value, similar
    title, within a window. Any one alone is ordinary: a contractor may
    hold several contracts of the same value, and "Borehole drilling"
    recurs across an entire state. It is the conjunction that is unlikely
    to be a coincidence.
    """
    found: list[DuplicateContract] = []
    by_vendor: dict[int, list[ContractRecord]] = {}
    for rec in records:
        by_vendor.setdefault(rec.vendor_id, []).append(rec)

    for rows in by_vendor.values():
        rows = sorted(rows, key=lambda r: (r.signed_date, r.contract_id))
        for i, left in enumerate(rows):
            for right in rows[i + 1:]:
                gap = (right.signed_date - left.signed_date).days
                if gap > window_days:
                    break                      # sorted: nothing later is closer
                if left.value <= 0 or right.value <= 0:
                    continue
                difference = abs(left.value - right.value)
                if difference > left.value * value_tolerance:
                    continue
                score, shared = title_similarity(left.title, right.title)
                if score < min_similarity:
                    continue
                found.append(DuplicateContract(
                    left_id=left.contract_id, right_id=right.contract_id,
                    left_number=left.contract_number,
                    right_number=right.contract_number,
                    vendor_id=left.vendor_id, vendor_name=left.vendor_name,
                    similarity=round(score, 4), shared_terms=shared,
                    value_difference=difference, days_apart=gap,
                ))

    found.sort(key=lambda d: (-d.similarity, -d.value_difference))
    return found


def find_duplicate_invoices(
    records: Sequence[InvoiceRecord],
    *,
    window_days: int = 90,
    tolerance: Decimal = Decimal("0.01"),
) -> list[DuplicateInvoice]:
    """Same vendor, near-identical amount, close together, different numbers.

    The per-vendor unique constraint already blocks the same number
    twice. What it cannot see is the same work re-billed under a fresh
    number, which is the form a duplicate invoice usually takes — so
    invoices sharing a number are not reported here, because the database
    made that case impossible rather than merely unlikely.
    """
    found: list[DuplicateInvoice] = []
    by_vendor: dict[int, list[InvoiceRecord]] = {}
    for rec in records:
        by_vendor.setdefault(rec.vendor_id, []).append(rec)

    for rows in by_vendor.values():
        rows = sorted(rows, key=lambda r: (r.invoice_date, r.invoice_id))
        for i, left in enumerate(rows):
            for right in rows[i + 1:]:
                gap = (right.invoice_date - left.invoice_date).days
                if gap > window_days:
                    break
                if left.amount <= 0 or right.amount <= 0:
                    continue
                if left.invoice_number and left.invoice_number == right.invoice_number:
                    continue
                difference = abs(left.amount - right.amount)
                if difference > left.amount * tolerance:
                    continue
                found.append(DuplicateInvoice(
                    left_id=left.invoice_id, right_id=right.invoice_id,
                    left_number=left.invoice_number,
                    right_number=right.invoice_number,
                    vendor_id=left.vendor_id, vendor_name=left.vendor_name,
                    amount=left.amount, difference=difference, days_apart=gap,
                ))

    found.sort(key=lambda d: (-d.amount, d.days_apart))
    return found


def check_before_saving(
    candidate: ContractRecord,
    existing: Sequence[ContractRecord],
    *,
    min_similarity: float = DEFAULT_MIN_SIMILARITY,
    value_tolerance: Decimal = DEFAULT_VALUE_TOLERANCE,
    window_days: int = DEFAULT_WINDOW_DAYS,
) -> list[DuplicateContract]:
    """Warn about one contract being captured, against what already exists.

    Separate from :func:`find_duplicate_contracts` because the timing is
    the point. A duplicate caught at draft costs a clerk one glance; the
    same duplicate caught after the first interim certificate costs a
    reversal, a variation and an audit note. A periodic report finds it
    at the wrong end of that.
    """
    others = [r for r in existing if r.contract_id != candidate.contract_id]
    return find_duplicate_contracts(
        [candidate, *others],
        min_similarity=min_similarity,
        value_tolerance=value_tolerance,
        window_days=window_days,
    )


# ── Loaders (need a database) ────────────────────────────────────────


def load_contracts(vendor_id: int | None = None) -> list[ContractRecord]:
    """Contracts worth comparing against.

    Cancelled and rejected contracts are excluded: they bound nobody to
    anything, and reporting a live contract as a duplicate of an
    abandoned one would be noise in the place least able to absorb it.
    """
    from contracts.models import Contract

    qs = Contract.objects.select_related("vendor").exclude(
        status__in=["CANCELLED", "REJECTED", "TERMINATED"],
    )
    if vendor_id is not None:
        qs = qs.filter(vendor_id=vendor_id)

    out: list[ContractRecord] = []
    for c in qs:
        signed = (
            getattr(c, "signed_date", None)
            or getattr(c, "commencement_date", None)
            or getattr(c, "created_at", None)
        )
        if signed is None:
            continue
        out.append(ContractRecord(
            contract_id=c.id,
            contract_number=c.contract_number or "",
            vendor_id=c.vendor_id,
            vendor_name=str(c.vendor),
            title=c.title or "",
            value=Decimal(str(c.original_sum or 0)),
            signed_date=signed.date() if hasattr(signed, "date") else signed,
            status=c.status,
        ))
    return out


def load_vendor_invoices(*, since: date, until: date) -> list[InvoiceRecord]:
    """Vendor invoices in a range, excluding voided ones."""
    from accounting.models import VendorInvoice

    qs = (
        VendorInvoice.objects
        .select_related("vendor")
        .filter(invoice_date__gte=since, invoice_date__lte=until)
        .exclude(status="Void")
        .exclude(vendor__isnull=True)
    )
    return [
        InvoiceRecord(
            invoice_id=i.id,
            invoice_number=i.invoice_number or "",
            vendor_id=i.vendor_id,
            vendor_name=str(i.vendor),
            amount=Decimal(str(i.total_amount or 0)),
            invoice_date=i.invoice_date,
            description=(i.description or "")[:300],
        )
        for i in qs
    ]
