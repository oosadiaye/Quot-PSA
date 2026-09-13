"""
Redaction for payloads sent to third-party AI providers.

Cloud providers are a decision already taken, so this module's job is to
make it governable: strip the identifiers that have no business leaving a
State's tenant, while preserving the *structure* the model needs to do
the work.

The distinction that matters
----------------------------
A reconciliation task needs to know that two references are similar. It
does not need the account number. So identifiers are replaced with
**stable tokens** rather than removed:

    "Paid 0123456789 ref PB/2026/0001"
    -> "Paid [ACCT_1] ref PB/2026/0001"

Stable, because the same value maps to the same token within one payload.
A model asked "do these two lines refer to the same account?" can still
answer, because ``[ACCT_1]`` appearing twice is the signal — the digits
never were.

Restoring
---------
:func:`redact` returns the text and a mapping. :func:`restore` puts the
originals back into a model's *output*, so a proposal can quote the
reference an operator will recognise without the value having travelled.

What is deliberately not here
-----------------------------
This is not a general PII scrubber and must not be sold as one. It covers
the identifiers this application actually stores and that a finance
payload actually carries: bank accounts, BVN, TIN, card-like numbers,
emails and phone numbers. Free prose can always carry an identifier no
pattern anticipates, which is why §3.3 of the plan pairs redaction with
per-provider data-policy flags rather than treating it as sufficient on
its own.

Amounts are **not** redacted. A reconciliation or analysis task is about
the amounts; removing them removes the task.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# ── Patterns ─────────────────────────────────────────────────────────
#
# Overlap between the digit patterns is prevented by the lookarounds,
# not by this ordering. _ACCOUNT is (?<!\d)\d{10}(?!\d), so inside an
# 11-digit BVN every 10-digit window has a digit on one side and the
# match is refused. Verified by mutation: swapping BVN and ACCT here
# changes no behaviour.
#
# The ordering is kept as defence in depth for whoever loosens a
# lookaround later, and because TIN and EMAIL are genuinely more
# specific than the bare digit runs. Do not rely on it alone.

#: Nigerian BVN — exactly 11 digits.
_BVN = re.compile(r"(?<!\d)\d{11}(?!\d)")

#: Nigerian NUBAN bank account — exactly 10 digits.
_ACCOUNT = re.compile(r"(?<!\d)\d{10}(?!\d)")

#: Tax Identification Number, e.g. 12345678-0001.
_TIN = re.compile(r"(?<!\w)\d{8}-\d{4}(?!\w)")

#: 13-19 digit card-like runs, optionally grouped.
_CARD = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")

#: International or local Nigerian mobile numbers.
_PHONE = re.compile(r"(?<!\w)(?:\+234|0)[\s-]?\d{3}[\s-]?\d{3}[\s-]?\d{4}(?!\w)")

#: (label, pattern) in the order they are applied.
_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("TIN", _TIN),          # has a hyphen; match before bare digit runs
    ("CARD", _CARD),        # longest digit run
    ("BVN", _BVN),          # 11 digits, before 10
    ("ACCT", _ACCOUNT),     # 10 digits
    ("EMAIL", _EMAIL),
    ("PHONE", _PHONE),
)


@dataclass
class Redaction:
    """Redacted text plus the mapping needed to restore it."""

    text: str
    #: token -> original value, e.g. {"[ACCT_1]": "0123456789"}
    mapping: dict[str, str] = field(default_factory=dict)

    @property
    def redacted_count(self) -> int:
        return len(self.mapping)


def redact(text: str) -> Redaction:
    """Replace identifiers with stable tokens.

    The same original value always receives the same token within one
    call, so equality and similarity survive the substitution even though
    the value does not.
    """
    if not text:
        return Redaction(text=text)

    mapping: dict[str, str] = {}
    reverse: dict[str, str] = {}   # original -> token, for stability
    counters: dict[str, int] = {}

    def _token_for(label: str, original: str) -> str:
        if original in reverse:
            return reverse[original]
        counters[label] = counters.get(label, 0) + 1
        token = f"[{label}_{counters[label]}]"
        mapping[token] = original
        reverse[original] = token
        return token

    result = text
    for label, pattern in _RULES:
        def _sub(match: re.Match[str], _label: str = label) -> str:
            return _token_for(_label, match.group(0))

        result = pattern.sub(_sub, result)

    return Redaction(text=result, mapping=mapping)


def restore(text: str, mapping: dict[str, str]) -> str:
    """Put original values back into a model's output.

    Longest token first, so ``[ACCT_1]`` is never partially matched by a
    prefix of ``[ACCT_11]``.
    """
    if not text or not mapping:
        return text
    for token in sorted(mapping, key=len, reverse=True):
        text = text.replace(token, mapping[token])
    return text


def redact_payload(payload: dict) -> tuple[dict, dict[str, str]]:
    """Redact every string in a nested dict/list structure.

    One shared mapping across the whole payload, so a value appearing in
    two different fields gets one token — which is what lets a model
    reason across fields.
    """
    mapping: dict[str, str] = {}
    reverse: dict[str, str] = {}
    counters: dict[str, int] = {}

    def _redact_string(value: str) -> str:
        inner = redact(value)
        out = inner.text
        # Re-key this call's tokens onto the shared, payload-wide numbering.
        for token, original in inner.mapping.items():
            label = token.strip("[]").rsplit("_", 1)[0]
            if original in reverse:
                shared = reverse[original]
            else:
                counters[label] = counters.get(label, 0) + 1
                shared = f"[{label}_{counters[label]}]"
                mapping[shared] = original
                reverse[original] = shared
            out = out.replace(token, shared)
        return out

    def _walk(node):
        if isinstance(node, str):
            return _redact_string(node)
        if isinstance(node, dict):
            return {k: _walk(v) for k, v in node.items()}
        if isinstance(node, (list, tuple)):
            return [_walk(v) for v in node]
        # Numbers, bools, None and Decimals pass through untouched:
        # amounts are the task, not the risk.
        return node

    return _walk(payload), mapping
