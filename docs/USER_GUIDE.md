# Quot PSE — User Guide

One chapter per baseline role. Keep this next to your workstation — each
chapter ends with a checklist of day-to-day actions you own.

For operational incidents, see [RUNBOOK.md](RUNBOOK.md). For the full
API reference, open the Swagger UI: `/api/docs/`.

---

## Table of contents

1. [Budget & Appropriation Manager](#1-budget--appropriation-manager)
2. [Budget Officer](#2-budget-officer)
3. [Accountant-General](#3-accountant-general)
4. [Account Officer](#4-account-officer)
5. [Procurement Manager](#5-procurement-manager)
6. [Procurement Officer](#6-procurement-officer)
7. [All users — common](#7-all-users--common)

---

## 1. Budget & Appropriation Manager

**Who you are.** The legislative-side owner. You propose the annual
budget, move supplementary / virement amendments through the
Appropriation Committee, and sign off the enacted Act.

**Where you live in the app.** Main menu → **Budget** → *Appropriations*,
*Warrants*, *Virements*.

### 1.1 Create the annual budget

1. **Budget** → *Appropriations* → **New Appropriation**
2. Pick the Fiscal Year; select the NCoA administrative/economic/
   functional/programme/fund row.
3. Enter `amount_approved` (the Act figure). Leave `original_amount`
   blank — it is captured automatically when the Appropriation is
   activated.
4. Status: **DRAFT**. Save.

### 1.2 Walk it through approval

`DRAFT → SUBMITTED → APPROVED → ENACTED → ACTIVE`. Each transition
requires the approval-rule matching your scope; the ApprovalLevel
configuration is documented in the Workflow module.

### 1.3 Supplementary / Virement

- **Supplementary** — adds new money. Treat as a fresh Appropriation
  with `appropriation_type=SUPPLEMENTARY`.
- **Virement** — moves money between existing lines. The `BudgetTransfer`
  form enforces the zero-sum invariant on the server.

### 1.4 Monitor execution

Open **Budget Dashboard** → the cards show committed / expended /
available per Appropriation. These numbers are **denormalised**
(P6-T2) — they're fresh within seconds of any PO, invoice, or
payment event.

### Checklist (weekly)

- [ ] Review IPSAS 24 Budget-vs-Actual report for material variances
- [ ] Attach a variance narrative (`variance_explanation`) wherever
      variance > 10 %
- [ ] Confirm no Appropriation is within 5 % of its ceiling without an
      active Supplementary in the pipeline

---

## 2. Budget Officer

**Who you are.** Day-to-day budget execution — you draft, route, and
monitor appropriations under the Manager's direction.

**Where you live.** **Budget** → *Warrants*, *Commitment Register*,
*Appropriation Dashboard*.

### 2.1 Release a warrant

1. **Budget** → *Warrants* → **New Warrant**
2. Link it to an active Appropriation; enter `amount_requested`.
3. Route via workflow (approvals defined in the ApprovalRule matrix).
4. On RELEASED, downstream Treasury / Procurement can draw cash up to
   this ceiling.

### 2.2 Commitment register triage

Open the register (filter by status = ACTIVE / INVOICED) each morning:

- **ACTIVE → aged > 30 days** — the receiving office has not issued a
  GRN. Escalate to Procurement.
- **INVOICED → aged > 14 days** — vendor invoice sitting unpaid. Ping
  the Accounts payable team.

### 2.3 Monthly close prep

Run:
```bash
./manage.py tenant_command resync_appropriation_totals --schema=<t>
```
before the period close meeting so the Accountant-General sees fresh
aggregates rather than the cached ones.

### Checklist (daily)

- [ ] Clear overnight commitment-register exceptions
- [ ] Confirm warrants released today match the Cash Plan forecast

---

## 3. Accountant-General

**Who you are.** The apex finance officer. You own the GL, close
periods, approve material journals, and sign the financial statements.

**Where you live.** **Accounting** → *Journals*, *Period Close*,
*IPSAS Reports*, *Admin Console*.

### 3.1 Post / un-post a journal

1. **Accounting** → *Journals* → select the row → **Post Journal**
2. The server enforces: period is OPEN, debits = credits, lines
   balanced, budget-check passes. Any failure shows the exact
   validation message.
3. **Un-post** is a reversal — it does not delete the journal; it
   records a `JournalReversal` alongside for the audit trail.

Both actions automatically bust the report cache (P6-T4) so dashboards
refresh instantly for everyone.

### 3.2 Close a fiscal period

1. **Accounting** → *Period Close* → select the period
2. Run the close checklist (`PeriodCloseCheck` items — missing GRN,
   unreconciled banks, draft journals). All must pass or be explicitly
   waived.
3. Click **Close Period**. The service transitions the status to
   CLOSED and records the actor + timestamp.

### 3.3 Year-end

See `accounting/services/period_close.py` → `close_fiscal_year`. The
service creates the closing journal (Revenue/Expense → Net Income) and
the opening journal (carry-forward of Assets/Liabilities/Equity).

### 3.4 Dual-Control Override

Some actions (back-dated journals, certain write-offs) require a
**DualControlOverride**. You approve as the first signatory; a
second AG-level user co-signs in the AdminConsole. Every override is
logged in the Override Audit page with both signatures and the reason.

### 3.5 IPSAS reports

**Accounting** → *Reports* gives every IPSAS statement. The heavy three
(SoFP, SoFPerf, Budget-vs-Actual) are served from a 10-min cache so you
can refresh freely. Export buttons produce XLSX (and PDF via WeasyPrint
where installed).

### Checklist (monthly)

- [ ] Run period-close checklist; sign off
- [ ] Review & approve material overrides in the Override Audit page
- [ ] File FIRS VAT / WHT and PENCOM schedule (XML exports)
- [ ] Sign the monthly management pack (SoFP + SoFPerf + Cash Flow)

---

## 4. Account Officer

**Who you are.** Executes the AG's policies — raises journals, posts
invoices, reconciles.

### 4.1 Raise a manual journal

1. **Accounting** → *Journals* → **New Journal**
2. Enter header (posting_date, MDA, fund, description).
3. Lines: DR / CR amounts, account, NCoA code, optional cost_center.
   The DB enforces "exactly one of debit/credit is non-zero".
4. Save as **Draft**; route for approval. The Accountant-General posts.

### 4.2 Vendor invoice (direct, no PO)

1. **Accounting** → *Vendor Invoices* → **New**
2. Post the invoice. The server auto-creates the `DR Expense /
   CR AP` journal, routes for approval, and (once posted) rolls into
   the Appropriation's `cached_total_expended`.

### 4.3 Bank reconciliation

**Accounting** → *Bank Reconciliation* → pick account → **New Run**.
Upload the bank statement CSV. Match lines; unmatched items become
`reconciling items` on the recon report.

### Checklist (daily)

- [ ] Receipts posted same-day
- [ ] Draft journals reviewed & routed
- [ ] Bank recon run end-of-day for the clearing account

---

## 5. Procurement Manager

**Who you are.** Owns the procurement pipeline. You approve purchase
requisitions, award tenders, and release POs into commitment.

### 5.1 Approve a PO

1. **Procurement** → *Purchase Orders* → select DRAFT row.
2. **Approve**. The service:
   - creates a `ProcurementBudgetLink` (status=ACTIVE) — this is the
     commitment that encumbers the appropriation.
   - refreshes the Appropriation's `cached_total_committed`.
3. Budget-exceeded errors are hard blocks — escalate to the Budget
   Manager (§1.3) for a Supplementary or Virement.

### 5.2 Three-way matching

Once the vendor delivers:
- GRN posts → commitment flips ACTIVE → INVOICED
- Vendor invoice posts → commitment flips INVOICED → CLOSED;
  the expense lands in the GL; `cached_total_expended` increments.

The whole chain auto-runs; the Procurement Manager's only job is to
resolve exceptions (mismatch quantity, price, or vendor).

### Checklist (weekly)

- [ ] POs awaiting approval cleared within 3 business days
- [ ] Active commitments aged > 30 days reviewed
- [ ] No vendor on the FIRS non-compliance list in the approved queue

---

## 6. Procurement Officer

**Who you are.** Prepares requisitions, drafts POs, tracks delivery.

### 6.1 Create a PR → PO

1. **Procurement** → *Purchase Requisitions* → **New** → submit.
2. After approval, convert to a draft PO (same screen → **Create PO**).
3. Once the Manager approves, the commitment is created automatically.

### 6.2 Receive goods (GRN)

1. **Procurement** → *GRN* → select the line → enter received qty,
   batch, warehouse. Post.
2. The matching `ProcurementBudgetLink` flips to INVOICED.

### Checklist (daily)

- [ ] Any GRN exceptions resolved before end of day
- [ ] Pending requisitions annotated with ETA so the PM can prioritise

---

## 7. All users — common

### 7.1 Notifications

Click the bell (top-right of sidebar). Badge shows unread count;
dropdown lists the 15 most recent. Clicking an actionable notification
marks it read and navigates to the source record.

### 7.2 Password & account

- Password self-reset: **Profile** → *Security* → *Change password*
- If you're locked out: the tenant super-user can unlock from the
  Django admin or via `./manage.py changepassword <user>`.

### 7.3 Multi-tenant context

Your session always carries an `X-Tenant-Schema` header. When you
switch tenants from the Organization Switcher (top bar), the app
re-hydrates every list; your in-flight drafts on the previous tenant
are **not** migrated — finish or save them first.

### 7.4 Reporting & exports

Every IPSAS and dimension report has an **Export** menu:
- JSON (default)
- HTML
- XLSX
- PDF (where WeasyPrint is available)

Export large reports (>10 k lines) outside peak hours — they're
cache-backed so the first call may take up to 5 s.

### 7.5 Where to get help

- In-app: **Help** menu → *Documentation* (opens this guide)
- Support email: `support@quotpse.ng`
- Incident escalation: `#quotpse-oncall` on Slack
