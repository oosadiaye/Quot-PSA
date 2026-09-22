"""GL coding check — warn when a line description doesn't fit its GL account.

Hybrid (approach a):

1. A fast, offline **local matcher** scores the account name against the line
   description by meaningful-token overlap (stopwords + generic accounting
   filler dropped; light stemming; edit-distance-1 fuzz for typos/plurals).
2. Lines the local matcher finds suspect are escalated to the tenant's
   configured **AI** (``RECONCILIATION`` capability) — but only if AI is on.
   The LLM verdict overrides, mainly to *rescue* semantic matches the lexical
   check misses. On AI refusal/error the local (suspect) verdict stands.

Advisory only: the caller shows a non-blocking amber warning. Nothing here
blocks a post, and every failure path degrades to "don't crash the posting".

See ``docs/superpowers/specs/2026-09-22-gl-coding-check-design.md``.
"""
from __future__ import annotations

import re

MAX_LINES = 200
OK_THRESHOLD = 0.3

# Generic words that carry no account-identifying signal. Dropped from both
# sides so a shared "expense"/"charges" never counts as a real match.
_STOP = {
    # english function words
    "the", "and", "for", "of", "to", "a", "an", "in", "on", "at", "by", "with",
    "or", "from", "per", "as", "is", "are", "be", "this", "that", "it",
    # generic accounting / ledger filler
    "account", "accounts", "acct", "expense", "expenses", "cost", "costs",
    "charge", "charges", "fee", "fees", "payment", "payments", "paid", "pay",
    "general", "other", "others", "misc", "miscellaneous", "sundry", "various",
    "provision", "provisions", "income", "revenue", "gl", "ledger", "total",
    "amount", "value", "balance", "item", "items", "purchase", "purchases",
    "supply", "supplies", "services", "service", "goods", "bill", "bills",
    "invoice", "monthly", "annual", "being",
}


def _stem(word: str) -> str:
    """Very light stemmer — collapse a trailing plural 's'."""
    if len(word) > 3 and word.endswith("s"):
        return word[:-1]
    return word


def _tokens(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return [_stem(w) for w in words if w not in _STOP]


def _within_edit1(a: str, b: str) -> bool:
    """True when ``a`` and ``b`` are within Levenshtein distance 1."""
    if a == b:
        return True
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    if la > lb:
        a, b, la, lb = b, a, lb, la     # ensure len(a) <= len(b)
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
                j += 1           # substitution
            else:
                j += 1           # insertion into the longer string
    edits += (lb - j) + (la - i)
    return edits <= 1


def _matches(name_tok: str, desc_tokens: list[str]) -> bool:
    for d in desc_tokens:
        if name_tok == d:
            return True
        if len(name_tok) >= 4 and len(d) >= 4 and _within_edit1(name_tok, d):
            return True
    return False


def local_score(name: str, description: str) -> float | None:
    """Overlap coefficient of meaningful tokens, or ``None`` when either side
    has nothing meaningful to compare (can't assess → caller must not warn)."""
    name_tokens = _tokens(name)
    desc_tokens = _tokens(description)
    if not name_tokens or not desc_tokens:
        return None
    matched = sum(1 for t in name_tokens if _matches(t, desc_tokens))
    denom = min(len(name_tokens), len(desc_tokens))
    return min(1.0, matched / denom) if denom else 0.0


def check_line(*, name: str, description: str, code: str = "") -> dict:
    """Local-only verdict for one line."""
    score = local_score(name, description)
    if score is None or score >= OK_THRESHOLD:
        return {"verdict": "ok", "score": score, "reason": "", "ai_used": False}
    return {
        "verdict": "suspect",
        "score": score,
        "reason": f'Description doesn’t look like it belongs to "{name}".',
        "ai_used": False,
    }


def _usable_reconciliation_setting(tenant):
    """The tenant's usable RECONCILIATION AI setting, or None. Defensive — any
    misconfiguration returns None so posting is never blocked by AI plumbing."""
    if tenant is None:
        return None
    try:
        from superadmin.ai_models import AICapability, TenantAISetting
        setting = (
            TenantAISetting.objects
            .filter(tenant=tenant, capability=AICapability.RECONCILIATION)
            .select_related("provider")
            .first()
        )
        if setting is not None and setting.is_usable:
            return setting
    except Exception:            # noqa: BLE001 - never break posting on AI plumbing
        return None
    return None


def _ai_adjudicate(*, setting, tenant, actor, name, code, description) -> dict:
    """Ask the configured model whether the description fits the account."""
    import json

    from superadmin.ai_client import call_model

    system = (
        "You review government ledger postings. Decide whether the line "
        "description plausibly belongs to the given GL account. Reply ONLY as "
        'JSON: {"verdict":"ok"|"mismatch","reason":"<=12 words"}.'
    )
    prompt = f'GL account: "{code} {name}". Line description: "{description}".'
    result = call_model(
        tenant=tenant, setting=setting, prompt=prompt, system=system,
        max_tokens=60, subject={"feature": "gl_coding_check"},
    )
    text = (result.text or "").strip()
    match = re.search(r"\{.*\}", text, re.S)
    data = json.loads(match.group(0)) if match else {}
    verdict = "ok" if str(data.get("verdict", "")).lower().startswith("ok") else "mismatch"
    return {"verdict": verdict, "reason": str(data.get("reason", ""))[:120]}


def check_lines(lines, *, tenant=None, actor=None) -> dict:
    """Check up to ``MAX_LINES`` lines. Escalates only lexically-suspect lines
    to AI, and only when the tenant has a usable RECONCILIATION setting."""
    setting = _usable_reconciliation_setting(tenant)
    ai_used = False
    results: list[dict] = []

    for ln in list(lines)[:MAX_LINES]:
        name = (ln.get("name") or "").strip()
        code = (ln.get("code") or "").strip()
        description = (ln.get("description") or "").strip()
        res = check_line(name=name, description=description, code=code)

        if res["verdict"] == "suspect" and setting is not None:
            try:
                verdict = _ai_adjudicate(
                    setting=setting, tenant=tenant, actor=actor,
                    name=name, code=code, description=description,
                )
                ai_used = True
                if verdict.get("verdict") == "ok":
                    res = {**res, "verdict": "ok", "ai_used": True,
                           "reason": verdict.get("reason", "")}
                else:
                    res = {**res, "verdict": "suspect", "ai_used": True,
                           "reason": verdict.get("reason") or res["reason"]}
            except Exception:    # noqa: BLE001 - AI outage → keep local verdict
                pass

        results.append({
            **res,
            "index": ln.get("index"),
            "name": name, "code": code, "description": description,
        })

    return {"results": results, "ai_used": ai_used}
