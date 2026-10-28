"""Master-data duplicate lookup — warn before a near-duplicate record is created.

Used by the "create" forms for Vendor, Chart-of-Accounts GL, MDA and the other
registered master data. Given the values being typed, it returns the existing
records that look like the same thing so the operator can **adopt the existing
record**, **create anyway**, or **go back**. Advisory only: nothing here blocks
a save (DB uniqueness on ``code`` still does that), and every failure path
degrades to "no matches" so a lookup problem never blocks data entry.

Two kinds of evidence, strongest first:

* **exact** – an identifier collides after normalisation (same code, tax ID,
  registration number, e-mail, phone, bank account, short name …).
* **likely / similar** – the *name* is close: legal suffixes ("Ltd", "Nigeria
  Limited", "Plc") and filler words are dropped, tokens are lightly stemmed,
  and typos within edit-distance 1 are forgiven, so "Acme Nig. Ltd" and
  "ACME Nigeria Limited" collapse to the same thing.

Adding a new master-data type is one ``EntitySpec`` entry in ``ENTITIES``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from django.apps import apps

# Name similarity at/above these scores are reported. ``LIKELY`` is "almost
# certainly the same record"; ``SIMILAR`` is "worth a look".
LIKELY_THRESHOLD = 0.90
SIMILAR_THRESHOLD = 0.70

DEFAULT_LIMIT = 5
# Hard ceiling on rows pulled for fuzzy comparison. Master-data tables are
# small; if one ever exceeds this we still compare the first N rather than
# stream an unbounded table through Python on a keystroke.
MAX_CANDIDATES = 20000

# Legal-form / filler tokens that say nothing about *which* entity it is.
_NAME_STOP = {
    "the", "and", "of", "for", "to", "a", "an", "in", "on", "at", "by", "with",
    # legal forms
    "ltd", "limited", "plc", "llc", "inc", "incorporated", "corp", "corporation",
    "co", "company", "nig", "nigeria", "nigerian", "enterprises", "enterprise",
    "ent", "gmbh", "sa", "nv", "bv", "llp", "lp", "unltd", "unlimited",
    "venture", "ventures", "global", "intl", "international",
}


def _stem(word: str) -> str:
    if len(word) > 3 and word.endswith("s"):
        return word[:-1]
    return word


def name_tokens(text: str) -> list[str]:
    """Meaningful, stemmed tokens of a name (legal suffixes and filler dropped)."""
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return [_stem(w) for w in words if w not in _NAME_STOP]


def _within_edit1(a: str, b: str) -> bool:
    if a == b:
        return True
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    if la > lb:
        a, b, la, lb = b, a, lb, la
    i = j = edits = 0
    while i < la and j < lb:
        if a[i] == b[j]:
            i += 1
            j += 1
        else:
            edits += 1
            if edits > 1:
                return False
            if la == lb:
                i += 1
                j += 1
            else:
                j += 1
    edits += (lb - j) + (la - i)
    return edits <= 1


def _tok_match(a: str, b: str) -> bool:
    if a == b:
        return True
    return len(a) >= 4 and len(b) >= 4 and _within_edit1(a, b)


def name_similarity(a: str, b: str) -> float:
    """0..1 similarity of two names. ``1.0`` means identical once legal
    suffixes / punctuation / case are ignored."""
    ta, tb = name_tokens(a), name_tokens(b)
    if not ta or not tb:
        return 0.0
    if sorted(ta) == sorted(tb):
        return 1.0

    # Token score: fuzzy-matched tokens over the *larger* side (Jaccard-like,
    # so "Ministry of Health" vs "Ministry of Health and Works" isn't a 1.0).
    remaining = list(tb)
    matched = 0
    for t in ta:
        for k, u in enumerate(remaining):
            if _tok_match(t, u):
                matched += 1
                del remaining[k]
                break
    tok_score = matched / max(len(ta), len(tb))

    # Character score on the order-insensitive form catches run-together words
    # and multi-typo names the token pass misses.
    seq_score = SequenceMatcher(None, " ".join(sorted(ta)), " ".join(sorted(tb))).ratio()

    score = max(tok_score, seq_score)

    # One name wholly contained in the other ("Ministry of Health" inside
    # "Ministry of Health and Works") is worth flagging as similar — but only
    # when the shorter side has ≥2 tokens, so a lone generic word doesn't match
    # everything.
    short, long_ = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    if len(short) >= 2 and matched == len(short):
        score = max(score, SIMILAR_THRESHOLD + 0.05)
    # Only an identical token set scores 1.0 ("Same name"); a typo-tolerant
    # match is at most "almost the same".
    return round(min(score, 0.97), 3)


def _alnum(value) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def _digits(value) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _norm_phone(value) -> str:
    """Compare phones on their last 9 digits so +234 / 0 prefixes don't hide a match."""
    d = _digits(value)
    return d[-9:] if len(d) >= 7 else ""


def _norm_email(value) -> str:
    return str(value or "").strip().lower()


@dataclass(frozen=True)
class Identifier:
    field: str
    label: str
    normalise: callable = _alnum


@dataclass(frozen=True)
class EntitySpec:
    label: str                       # "Vendor"
    model: str                       # "procurement.Vendor"
    name_field: str = "name"
    code_field: str | None = "code"
    identifiers: tuple[Identifier, ...] = ()
    # Extra columns returned to the UI as context (never identifiers/secrets).
    extra_fields: tuple[str, ...] = ()
    active_field: str | None = "is_active"


ENTITIES: dict[str, EntitySpec] = {
    "vendor": EntitySpec(
        label="Vendor", model="procurement.Vendor",
        identifiers=(
            Identifier("tax_id", "Tax ID"),
            Identifier("registration_number", "registration number"),
            Identifier("email", "e-mail", _norm_email),
            Identifier("phone", "phone number", _norm_phone),
            Identifier("bank_account_number", "bank account number", _digits),
        ),
    ),
    "account": EntitySpec(
        label="GL account", model="accounting.Account",
        extra_fields=("account_type",),
    ),
    "mda": EntitySpec(
        label="MDA", model="accounting.MDA",
        identifiers=(Identifier("short_name", "short name"),),
        extra_fields=("mda_type",),
    ),
    "admin_segment": EntitySpec(
        label="MDA", model="accounting.AdministrativeSegment",
        identifiers=(Identifier("short_name", "short name"),),
        extra_fields=("level",),
    ),
    # NCoA classification segments: the code is the unique key, the name is
    # what operators mistype / re-register under a different spelling.
    "ncoa_fund": EntitySpec(label="Fund", model="accounting.FundSegment"),
    "ncoa_functional": EntitySpec(label="Functional segment", model="accounting.FunctionalSegment"),
    "ncoa_programme": EntitySpec(label="Programme", model="accounting.ProgrammeSegment"),
    "ncoa_geographic": EntitySpec(label="Geographic segment", model="accounting.GeographicSegment"),
    "tsa_account": EntitySpec(
        label="Bank / TSA account", model="accounting.TreasuryAccount",
        name_field="account_name", code_field="account_number",
        extra_fields=("account_type",),
    ),
    "vendor_category": EntitySpec(
        label="Vendor category", model="procurement.VendorCategory",
        active_field=None,
    ),
    "asset_category": EntitySpec(
        label="Asset category", model="accounting.AssetCategory",
        active_field=None,
    ),
    "item": EntitySpec(
        label="Inventory item", model="inventory.Item",
        code_field="sku", active_field=None,
    ),
}


def get_spec(entity: str) -> EntitySpec | None:
    return ENTITIES.get(entity)


def get_model(spec: EntitySpec):
    return apps.get_model(spec.model)


def _model_has(model, name: str | None) -> bool:
    if not name:
        return False
    try:
        model._meta.get_field(name)
        return True
    except Exception:  # noqa: BLE001 - FieldDoesNotExist and friends
        return False


def find_matches(entity: str, values: dict, *, exclude_id=None, limit: int = DEFAULT_LIMIT) -> list[dict]:
    """Existing records that look like the one described by ``values``.

    ``values`` carries whatever the form has typed so far (``name``, ``code``,
    and any identifier fields); blank keys are ignored. Returns up to ``limit``
    dicts ``{id, code, name, is_active, level, score, reasons, extra}`` ordered
    exact → likely → similar, then by score. ``exclude_id`` omits the record
    being edited. Unknown entity → ``[]``.
    """
    spec = get_spec(entity)
    if spec is None:
        return []
    values = values or {}
    model = get_model(spec)

    name = str(values.get(spec.name_field) or "").strip()
    code = str(values.get(spec.code_field) or "").strip() if spec.code_field else ""
    code_n = _alnum(code)

    idents = [
        (ident, ident.normalise(values.get(ident.field)))
        for ident in spec.identifiers
        if _model_has(model, ident.field)
    ]
    idents = [(i, n) for i, n in idents if n]

    if not name and not code_n and not idents:
        return []

    cols = ["id", spec.name_field]
    if spec.code_field and _model_has(model, spec.code_field):
        cols.append(spec.code_field)
    if spec.active_field and _model_has(model, spec.active_field):
        cols.append(spec.active_field)
    cols += [f for f in spec.extra_fields if _model_has(model, f)]
    cols += [i.field for i, _ in idents]
    cols = list(dict.fromkeys(cols))

    qs = model._default_manager.all()
    if exclude_id not in (None, ""):
        qs = qs.exclude(pk=exclude_id)
    rows = qs.order_by("id").values(*cols)[:MAX_CANDIDATES]

    found: list[dict] = []
    for row in rows:
        reasons: list[str] = []
        level = None
        score = 0.0

        row_code = row.get(spec.code_field) if spec.code_field else ""
        if code_n and _alnum(row_code) == code_n:
            reasons.append("Same code")
            level, score = "exact", 1.0

        for ident, wanted in idents:
            if ident.normalise(row.get(ident.field)) == wanted:
                reasons.append(f"Same {ident.label}")
                level, score = "exact", 1.0

        if name:
            sim = name_similarity(name, row.get(spec.name_field) or "")
            if sim >= SIMILAR_THRESHOLD:
                if sim >= 1.0:
                    reasons.append("Same name")
                elif sim >= LIKELY_THRESHOLD:
                    reasons.append("Almost the same name")
                else:
                    reasons.append("Similar name")
                if level is None:
                    level = "likely" if sim >= LIKELY_THRESHOLD else "similar"
                score = max(score, sim)

        if level is None:
            continue
        found.append({
            "id": row["id"],
            "code": row_code or "",
            "name": row.get(spec.name_field) or "",
            "is_active": row.get(spec.active_field) if spec.active_field and spec.active_field in row else True,
            "level": level,
            "score": round(score, 3),
            "reasons": reasons,
            "extra": {f: row.get(f) for f in spec.extra_fields if f in row},
        })

    order = {"exact": 0, "likely": 1, "similar": 2}
    found.sort(key=lambda m: (order[m["level"]], -m["score"], m["name"]))
    return found[:limit]
