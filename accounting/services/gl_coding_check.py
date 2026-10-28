"""GL coding check — warn when a line description doesn't fit its GL account.

Hybrid (approach a):

1. A fast, offline **local matcher** scores the account name against the line
   description by meaningful-token overlap (stopwords + generic accounting
   filler dropped; light stemming; edit-distance-1 fuzz for typos/plurals).
2. Lines the local matcher finds suspect are escalated to the tenant's
   configured **AI** (``RECONCILIATION`` capability) — but only if AI is on.
   The LLM verdict overrides, mainly to *rescue* semantic matches the lexical
   check misses. On AI refusal/error the local (suspect) verdict stands.

3. For every suspect line, **suggest existing GL accounts** that do fit the
   description (name match against the chart of accounts, boosted by how
   similar past *posted* lines were coded) so the operator can adopt one
   instead of posting to the wrong account.

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
    return _score_tokens(_tokens(name), _tokens(description))


def _score_tokens(name_tokens: list[str], desc_tokens: list[str]) -> float | None:
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


# ── Suggestions: "adopt an existing GL instead" ──────────────────────────────

SUGGEST_MIN_SCORE = 0.5     # at least half the account-name tokens must fit the description
SUGGEST_LIMIT = 3
HISTORY_SCAN = 300          # recent posted lines inspected per suspect line
HISTORY_MIN_SCORE = 0.6     # a past memo must clearly match the description
MAX_HISTORY_LOOKUPS = 25    # suspect lines that get a history lookup per call


class _AccountIndex:
    """One-query snapshot of the chart of accounts with pre-tokenised names, so
    scoring N lines doesn't re-tokenise every account N times."""

    def __init__(self):
        from accounting.models import Account
        rows = Account.objects.filter(is_active=True).values(
            "id", "code", "name", "account_type", "is_postable", "is_reconciliation",
        )
        self.by_code: dict[str, dict] = {}
        self.candidates: list[dict] = []
        for r in rows:
            r["tokens"] = _tokens(r["name"])
            self.by_code[r["code"]] = r
            # Header / control (reconciliation) accounts are never valid line
            # targets for a free-text description, so never suggest them.
            if r["is_postable"] and not r["is_reconciliation"] and r["tokens"]:
                self.candidates.append(r)
        self.by_id = {r["id"]: r for r in self.candidates}


def _history_votes(description: str, desc_tokens: list[str]) -> dict[int, int]:
    """account_id → how many recent *posted* lines with a memo like
    ``description`` were coded to it."""
    probe = max((t for t in desc_tokens if len(t) >= 4), key=len, default="")
    if not probe:
        return {}
    from accounting.models import JournalLine
    memos = (
        JournalLine.objects
        .filter(header__status="Posted", memo__icontains=probe)
        .order_by("-id")
        .values_list("account_id", "memo")[:HISTORY_SCAN]
    )
    votes: dict[int, int] = {}
    for account_id, memo in memos:
        score = _score_tokens(_tokens(memo), desc_tokens)
        if score is not None and score >= HISTORY_MIN_SCORE:
            votes[account_id] = votes.get(account_id, 0) + 1
    return votes


def suggest_accounts(index: _AccountIndex, *, description: str, current_code: str = "",
                     use_history: bool = True, limit: int = SUGGEST_LIMIT) -> list[dict]:
    """Postable GL accounts that fit ``description`` better than the one chosen.

    Same ``account_type`` as the current account when it is known (a mis-coded
    expense line should be recoded to another expense account, not to a bank
    account). Ranked by name fit plus a small boost per past posting.
    """
    desc_tokens = _tokens(description)
    if not desc_tokens:
        return []
    current = index.by_code.get(current_code) if current_code else None
    want_type = current["account_type"] if current else None

    votes = _history_votes(description, desc_tokens) if use_history else {}

    scored: list[tuple[float, dict, str]] = []
    for acct in index.candidates:
        if current_code and acct["code"] == current_code:
            continue
        if want_type and acct["account_type"] != want_type:
            continue
        name_score = _score_tokens(acct["tokens"], desc_tokens) or 0.0
        v = votes.get(acct["id"], 0)
        if name_score >= SUGGEST_MIN_SCORE:
            scored.append((min(1.0, name_score + 0.05 * min(v, 4)), acct, "name"))
        elif v >= 2:
            scored.append((min(0.9, 0.5 + 0.1 * min(v, 4)), acct, "history"))

    # Prefer the more specific account (more name tokens) on equal score.
    scored.sort(key=lambda t: (-t[0], -len(t[1]["tokens"]), t[1]["code"]))
    return [
        {"id": a["id"], "code": a["code"], "name": a["name"],
         "account_type": a["account_type"], "score": round(sc, 3), "source": src}
        for sc, a, src in scored[:limit]
    ]


def check_lines(lines, *, tenant=None, actor=None) -> dict:
    """Check up to ``MAX_LINES`` lines. Escalates only lexically-suspect lines
    to AI, and only when the tenant has a usable RECONCILIATION setting."""
    setting = _usable_reconciliation_setting(tenant)
    ai_used = False
    results: list[dict] = []
    index = None            # built lazily — only if a line turns out suspect
    history_lookups = 0

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

        suggestions: list[dict] = []
        if res["verdict"] == "suspect":
            try:
                if index is None:
                    index = _AccountIndex()
                use_history = history_lookups < MAX_HISTORY_LOOKUPS
                history_lookups += 1
                suggestions = suggest_accounts(
                    index, description=description, current_code=code,
                    use_history=use_history,
                )
            except Exception:    # noqa: BLE001 - suggestions are a bonus; never break the check
                suggestions = []

        results.append({
            **res,
            "suggestions": suggestions,
            "index": ln.get("index"),
            "name": name, "code": code, "description": description,
        })

    return {"results": results, "ai_used": ai_used}
