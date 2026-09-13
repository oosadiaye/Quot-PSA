# AI Features — Review and Build Plan

**Status:** Plan. Nothing in this document is built.
**Scope:** AI across the existing application on `main`. **Excludes** the HR
module and everything on `feat/future-modules`, as requested.
**Grounding:** every claim about this codebase was checked against the tree at
`9e33790`. Model names and file paths below are real, not illustrative.

---

## 1. The governing constraint

This is a statutory general ledger. An Accountant-General signs statements built
on it, and an Auditor-General examines them.

> **AI proposes. The ledger disposes.**
>
> Nothing a model produces may post to the GL, approve a payment, or change an
> appropriation. Every AI output lands as a **draft** for a named human to
> accept, edit or reject — and the acceptance, not the generation, is the
> auditable act.

This is not caution for its own sake. It is what makes the features shippable:
a draft that is wrong costs a few seconds of review, while a posted journal that
is wrong costs a restatement. Every feature below is designed to sit on the
draft side of that line, and §8 lists the things this plan therefore refuses to
build.

The codebase already agrees with this shape. `VendorInvoice` carries
`ImmutableModelMixin`, so a posted invoice cannot be edited — a scanned invoice
was always going to have to arrive as a draft.

---

## 2. What the application actually is

| | |
|---|---|
| API surface | **~200 ViewSets** outside HR — accounting 136, procurement 13, contracts 12, inventory 12, budget 9, workflow 9 |
| Accounting logic | **58 service modules** in `accounting/services/` |
| Chart | 6-segment NCoA — Administrative, Economic, Functional, Programme, Fund, Geographic |
| Multi-tenancy | `django-tenants`, schema per State |
| Reconciliation today | `bank_reconciliation.py`, `tsa_bank_reconciliation.py`, `tsa_reconciliation_service.py` |
| Data quality today | `data_quality.py` — rule-based checks over posted lines |
| Async worker | **Celery is not installed** (commented out in `requirements.txt`) |

Two facts shape everything below.

**The rule engines already exist and are good.** This is not a system that lacks
logic. `BankReconciliationService.find_match_candidates` already scores
candidates on date, amount and reference. The opportunity is not to replace that
— it is to take the residue it cannot match, which is where the clerical cost
actually sits.

**There is no async worker.** Every AI call is a network round trip of seconds.
Without a queue, that time lands inside an HTTP request. §6 Phase 1 treats this
as a hard prerequisite, not a detail.

---

## 3. The provider layer

Multi-provider with per-tenant toggles, configured in superadmin, as requested:
**Anthropic (Claude), OpenAI, Google (Gemini), OpenRouter.**

### It already has a house pattern to follow

`superadmin/models.py` contains exactly this shape twice over:

```
LanguageConfig   (global catalogue)  →  TenantLanguageSetting  (per-tenant choice)
CurrencyConfig   (global catalogue)  →  TenantCurrencySetting  (per-tenant choice)
WebhookConfig    (configuration)     →  WebhookDelivery        (per-attempt log)
```

So the AI layer should be:

- **`AIProvider`** — global catalogue row per provider. Key, display name,
  base URL, available models, enabled flag, sort order. Mirrors `LanguageConfig`.
- **`TenantAISetting`** — which provider a tenant uses, per **capability** rather
  than one global choice (§3.2), plus the toggle. Mirrors `TenantLanguageSetting`.
- **`AICall`** — one row per call: capability, provider, model, prompt hash,
  token counts, cost, latency, status, error. Mirrors `WebhookDelivery`.

Nothing novel is required. A reviewer who knows `WebhookConfig` will recognise
all of it.

### 3.1 Credentials

API keys go in the existing `EncryptedCharField` (`superadmin/encryption.py`).

**One thing to fix first.** That field derives its Fernet key from
`SHA-256(settings.SECRET_KEY)`. That is adequate for the SMTP passwords it holds
today and wrong for a wallet of live provider keys: rotating `SECRET_KEY` after a
leak would render every stored key undecryptable at exactly the moment you can
least afford it. Introduce a dedicated `AI_KEK` with versioned keys and a re-wrap
path, on the pattern `snapshots` already uses (`SNAPSHOTS_KEK_HEX`). Small now,
a migration later.

### 3.2 Toggles are per capability, not per tenant

A single "which AI provider" switch is the wrong granularity, because the tasks
genuinely differ:

| Capability | Wants | Reasonable default |
|---|---|---|
| Document extraction (scan) | Strong vision, structured output | Claude or Gemini |
| Reconciliation reasoning | Careful, cheap, high volume | A small fast model |
| Narrative / analysis | Long context, good prose | Claude or GPT |
| Classification (NCoA) | Cheapest that clears the bar | Anything; often no LLM at all |

`TenantAISetting` therefore keys on `(tenant, capability)` and falls back to a
platform default. OpenRouter exists precisely to make "try a different model for
this one capability" a configuration change rather than a deployment.

### 3.3 What leaves the tenant

Cloud APIs mean ledger content crosses a boundary. That is a decision already
taken; this plan's job is to make it **governable** rather than to re-argue it:

- **A redaction layer** sits between the application and the provider. Vendor
  bank account numbers, BVN/TIN, and personal contact details are replaced with
  stable tokens before the call and restored after. A matching task needs *that
  these two references are similar*, not the account number itself.
- **`AICall` records a hash of what was sent**, never the raw payload, so the
  audit trail proves what happened without becoming a second copy of the data.
- **Per-provider data policy flags** — `sends_document_images`,
  `sends_ledger_amounts`, `retains_data` — recorded on `AIProvider` and shown in
  the superadmin UI, so whoever flips the toggle sees what it implies.
- **A tenant kill switch** that disables all AI in one action, because the first
  question in any incident is "can you stop it now".

---

## 4. The four you asked for

### 4.1 Payment and bank reconciliation

**Today:** `find_match_candidates` filters on `total_amount=amount` exactly,
within `MATCH_TOLERANCE_DAYS`, then scores date, amount and reference.

**Therefore it cannot match** — and a human does by hand:

| Residue | Why the rule misses it |
|---|---|
| Partial payment | Amount differs |
| Bundled transfer | One credit against several invoices |
| Bank charges deducted | Amount differs by the fee |
| Reference typed differently | `PB/2026/0001` vs `PB 2026 0001` vs `Payment Batch 1` |
| FX-settled payment | Amount differs by the rate |

**Build:** a second pass over **only the unmatched residue**. The rule engine
runs first and keeps everything it already wins; AI never sees what was matched
deterministically. Each proposal carries a confidence and a one-line reason
("statement credit ₦4,770,750.44 = invoices INV-8821 + INV-8830 less ₦250 charge").

**Controls:** proposals land in the existing reconciliation review queue as
suggestions. Auto-accept is available **only** above a configured confidence
**and** below a configured amount, defaulting to off. A human accepts.

**Why this is first:** it is measurable. Unmatched-line count before and after is
a number you can put in front of a Treasury, and reconciliation backlog is the
most visible recurring clerical cost in the module.

### 4.2 Scan to draft invoice

**Target exists:** `VendorInvoice` + `VendorInvoiceLine` already carry every
field a scan would fill — `invoice_number`, `reference`, `vendor`,
`invoice_date`, `due_date`, `purchase_order`, all six NCoA dimensions,
`subtotal` / `tax_amount` / `total_amount`, and per-line `account`, `amount`,
`tax_code`, `withholding_tax`.

**Flow:** upload PDF or photo → extract → resolve vendor against the register by
name/TIN → propose NCoA coding from the description → **draft** invoice with
every field marked as extracted, with its confidence, and the page region it came
from → human confirms.

**The part that earns its keep** is not OCR. It is the two resolutions that
follow: which registered vendor is this, and which economic segment does this
line belong to. Those are where clerks actually spend their time, and both are
checkable against tables the system already holds.

**Controls:** arithmetic is **recomputed, never trusted** — lines must sum to
subtotal, plus tax equals total, or the draft is flagged rather than saved.
Duplicate detection against `invoice_number` + vendor runs before the draft is
offered. WHT is derived by the existing `wht_payment_derivation.py`, not by the
model.

### 4.3 Scan to draft contract

**Target exists:** `ContractDocument` already has a `FileField`, a
`DocumentType` enum and a contract FK. The file store is built.

**Extract:** parties, contract value, dates, milestone schedule, retention
percentage, mobilisation terms, payment terms — into a draft `Contract` plus
milestone rows.

**Higher value than the invoice case, and higher risk.** A misread retention
percentage or milestone date propagates into IPC valuations and payment
certificates. So: every extracted term shows its source clause, and a
**contract cannot leave Draft** on extracted values alone — a human confirms each
financial term. The existing `contract_deductions.py` computes deductions; the
model never does arithmetic that reaches a payment.

### 4.4 Report analysis

**Today** the system computes IPSAS statements, budget execution, variance and
ageing correctly. What it does not do is **explain** them.

**Build** narrative over figures the system has already calculated — never over
raw data the model might re-add:

- Budget variance: which MDAs drive the top variances, and what changed month
  over month.
- Execution-rate commentary for the quarterly report.
- Ageing commentary — concentration, trend, the vendors that matter.
- A plain-language summary of the IPSAS statements for a non-finance reader.

**The rule that makes this safe:** the model receives **aggregates, not
transactions**, and every figure in the narrative must be traceable to one it was
given. Numbers are inserted by template from the computed values; the model
writes the prose between them. A model that is free to state figures will
eventually state a wrong one, and a wrong figure in a signed statement is a very
expensive kind of wrong.

---

## 5. What the review turned up — my own recommendations

Ranked by value per engineer-month, and each tied to something that already
exists.

### 5.1 Duplicate and split-payment detection — **highest control value**

`procurement/models.py` shows BPP thresholds are configured and enforced. The
classic evasion is not exceeding a threshold — it is **three purchases just
beneath it**, to the same vendor, in the same week, for the same thing.

A rule cannot catch this well, because the descriptions differ deliberately.
Similarity across description, vendor, timing and amount is exactly what a model
is good at. Pair it with duplicate-payment detection (same vendor, near-identical
amount, close dates, different invoice numbers).

This is the feature an Accountant-General will care about most and the strongest
line in any tender response. It is also pure detection — it advises, it never
blocks — so the control risk is near zero.

### 5.2 NCoA coding assistant

Six segments, thousands of valid combinations, and the single most common source
of miscoding. The system already holds every valid code and a history of how
similar descriptions were coded.

Suggest the full 6-segment combination from a free-text description, ranked, with
the historical precedent shown. Fits invoice entry, requisition, budget
preparation and the import templates alike.

**Note:** this may not need an LLM at all. A nearest-neighbour model over
historical codings is cheaper, faster, fully explainable ("coded this way 47
times before") and does not leave the tenant. Worth measuring before assuming.

### 5.3 Data-quality triage

`data_quality.py` produces findings. At State scale it will produce many, and a
long undifferentiated list gets ignored — which is the failure mode that matters,
since an ignored finding is indistinguishable from no check at all.

Rank by materiality and likely cause, cluster the ones that share a root cause,
and draft the correcting entry for a human to approve. Turns a list into a queue.

### 5.4 Anomalous journal detection

Journals posted outside normal hours, unusual account pairings for an MDA,
round-number entries near period end, first-time account combinations. Flag for
review, never block.

Complements the existing `dual_control.py` and SoD rules: those enforce *who*
may post; this notices *what* looks unlike everything else.

### 5.5 Procurement document drafting

Generate a first-draft specification, evaluation criteria or bid-analysis summary
from a requisition. Saves real time in a process that is mostly document
production — and carries no ledger risk, because nothing it produces posts
anywhere.

### 5.6 Audit-trail question answering

`audit_trail.py` holds the record. "Who changed this appropriation, and when?" is
a question people currently answer by exporting and filtering.

Natural-language query over the audit trail, **returning rows rather than
prose** — the model translates the question into a filter; the system returns the
records. The answer is then as trustworthy as the database, because it *is* the
database.

---

## 6. Phasing

Estimates are engineer-months for one engineer who knows this codebase.

| Phase | Lands | Est. |
|---|---|---|
| **0** | Decisions (§9); provider accounts; a DPA per provider | 0.25 |
| **1** | **Foundation** — `AIProvider` / `TenantAISetting` / `AICall`, superadmin page with toggles, `AI_KEK`, redaction layer, cost caps, kill switch, **and a worker** (Celery is not installed) | 2–2.5 |
| **2** | **Reconciliation assist** (§4.1) — residue only, review queue, measured against current unmatched volume | 1.5–2 |
| **3** | **Scan to draft invoice** (§4.2) | 1.5–2 |
| **4** | **Duplicate / split-purchase detection** (§5.1) | 1–1.5 |
| **5** | **Scan to draft contract** (§4.3) | 1.5–2 |
| **6** | **Report analysis** (§4.4) | 1–1.5 |
| **7** | NCoA assistant (§5.2), data-quality triage (§5.3) | 1.5–2 |
| **8** | Anomalous journals (§5.4), procurement drafting (§5.5), audit Q&A (§5.6) | 2–3 |

**Total 12.25–16.75 engineer-months.**

**Phases 1–2 (3.5–4.5 months)** give a working provider layer with toggles and
one feature whose value is measurable. That is the right first commitment:
it proves the foundation against a real workload rather than a demo.

Phase 4 is deliberately early despite not being in the original four — it is the
cheapest item on the list with the highest control value, and it is pure
detection.

---

## 7. Cost and failure

Two operational realities that decide whether this survives contact with a State
budget.

**Token spend is a per-tenant budget, enforced.** `AICall` records cost per call;
`TenantAISetting` carries a monthly ceiling; crossing it disables AI features and
alerts rather than silently billing. Document extraction on a large PDF is not
cheap, and invoice volume at State scale is not small.

**Every feature degrades to the current behaviour.** Provider down, budget spent,
toggle off — reconciliation returns rule-only results, scanning returns an empty
draft form, reports render without narrative. No screen may become unusable
because a third party is unavailable. This is what makes the toggles safe to use.

---

## 8. What this plan refuses to build

Stated so they are not proposed later as obvious wins:

- **Auto-posting to the GL.** Not at any confidence. §1.
- **Autonomous payment approval.** Approval is a segregation-of-duties control
  with a named human on it; a model cannot hold that role.
- **Model-computed figures in statutory reports.** Figures come from the ledger
  by template; the model writes prose between them.
- **A chatbot over the whole database.** Sounds impressive, has an unbounded
  blast radius, and answers questions nobody asked. Targeted assistants where
  the output is checkable — §5.6 returns rows, not prose.
- **Training on tenant data.** Ruled out unless a State explicitly asks and
  contracts for it. One tenant's ledger must never influence another's output.

---

## 9. Decisions needed before Phase 1

1. **Celery.** Phase 1 needs a worker. It is commented out in
   `requirements.txt`, and adopting it is a deployment change — broker, worker
   process, monitoring — that should be decided on its own merits.
2. **Which provider accounts exist today**, and is there a DPA with each?
   OpenRouter is a *broker*: it routes to upstream providers, so its data policy
   is the union of theirs. That is worth knowing before it is toggled on for a
   government tenant.
3. **Who pays for tokens** — platform, or the tenant? This decides whether §7's
   ceiling is a cost control or a billing line, and it changes the data model.
4. **Is the redaction layer (§3.3) required or optional?** Required is the right
   answer for vendor bank details; confirm before build, because retrofitting
   redaction after the first integration is materially harder.
5. **A pilot tenant with real volume.** Reconciliation assist cannot be evaluated
   against seeded demo data — the residue is the whole point, and demo data has
   none.
