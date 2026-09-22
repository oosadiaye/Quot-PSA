# GL Coding Check — description-vs-account sanity warning

**Date:** 2026-09-22
**Status:** Approved (brainstorming) — approach (a) hybrid

## Goal

Reduce mis-posting by warning (amber, non-blocking) when a posting line's
**description** does not look like it belongs to the selected **GL account**.
Fires when the user clicks Post/Save on: AP Invoice, Customer Invoice, General
Journal Entry, Purchase Requisition, Purchase Order.

## Mechanism — hybrid

Per line, compare the account label (`code + name`) against the `description`:

1. **Local similarity (always, free, instant, offline):** normalise → tokenise
   → drop stopwords + generic accounting filler ("account", "expense", "cost",
   "other", "sundry", "misc"…) → light stem (trailing `s`) → token overlap with
   an edit-distance-≤1 fuzzy fallback for tokens ≥4 chars. Score = matched /
   min(|name tokens|, |desc tokens|) (overlap coefficient).
   - `score >= OK_THRESHOLD (0.3)` → **ok** (done; no AI).
   - Either side has no meaningful tokens (all-generic name, or empty/generic
     description) → **ok/neutral** (can't assess → never warn; avoids noise).
   - else → **lexically suspect**.
2. **LLM escalation (only for lexically-suspect lines, only if the tenant has
   AI on):** call `superadmin.ai_client.call_model` with the tenant's
   `RECONCILIATION` capability setting → `{verdict: ok|mismatch, reason}`. The
   LLM verdict overrides — it mainly **rescues** semantic matches the lexical
   check missed ("vehicle fuel" ↔ "Motor Running Costs"), cutting false alarms.
   On AI-refused/error → keep the local (suspect) verdict (fail to the warning,
   which is non-blocking anyway).

## Backend

- `accounting/services/gl_coding_check.py`
  - `local_score(name, description) -> float | None` (None = can't assess).
  - `check_line(name, code, description, *, tenant=None, ai_setting=None) -> dict`
    `{verdict: 'ok'|'suspect', score, reason, ai_used}`.
  - `check_lines(lines, *, tenant, actor) -> {results, ai_used}` — resolves the
    tenant's usable `RECONCILIATION` setting once; escalates only suspect lines;
    caps at 200 lines.
- Endpoint `POST /accounting/gl-coding-check/` (authenticated; advisory, no
  posting permission needed): body `{lines:[{index?, name, code?, description}]}`
  → `{results:[{index, name, code, description, verdict, score, reason}], ai_used}`.
  Frontend passes the GL **name it already shows in the picker** + the line
  description, so the check is uniform across all five surfaces regardless of
  their differing line models (AP/customer/journal have an Account FK; PR/PO GL
  is via budget/NCoA — the resolved label sidesteps that).

## Frontend

- `useGlCodingCheck()` — mutation posting lines → results.
- `GlCodingWarningModal` — amber modal listing suspect lines (GL name ·
  description · reason) with **Post anyway** (acknowledge → continue submit) and
  **Go back & fix** (abort).
- `runGlCheckedSubmit({ lines, onProceed })` helper the five forms call in their
  Post/Save handler: check → if any suspect, open modal and await the user; on
  Post-anyway run `onProceed()`; else abort. Lines with empty name or empty
  description are skipped client-side before the call.

## Non-goals (v2)

- Hard block / approval gate (this is advisory only).
- Learning from historical postings; per-account synonym dictionaries.
- Batch re-scan of already-posted journals.

## Tests (TDD)

- `test_gl_coding_check.py` (django_db):
  - clear match ("Diesel fuel for generator" ↔ "Motor Vehicle Fuel") → ok;
  - clear mismatch ("Diesel fuel" ↔ "Bank Charges") → suspect;
  - generic-only account ("Sundry Expenses") or empty description → ok/neutral;
  - plural/typo fuzz ("vehicles" ↔ "Vehicle …") → ok;
  - `check_lines` returns per-line verdicts; AI off → local only (`ai_used=false`);
  - AI on (monkeypatched `call_model`) → mismatch rescued to ok / confirmed.
- Endpoint test: posts lines → returns verdicts; caps > 200.
