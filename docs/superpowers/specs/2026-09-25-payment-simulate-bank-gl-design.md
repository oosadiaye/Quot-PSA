# Payment posting — Simulate button + bank-account-driven cash GL

**Date:** 2026-09-25
**Branch:** `feat/milestone-as-invoice`
**Status:** Approved — implementing

## Context

The Outgoing Payment form always shows a "Proposed journal entries" preview whose
**Bank/Cash line falls back to a hardcoded GL (`31010101`)** when no bank account
is selected — and the *actual* `post_payment` resolves the same way, so a payment
can silently post to that default. The product owner wants an SAP-style
**Simulate** step: no preview by default; a Simulate button that shows the entries
using the **selected bank account's GL**, so the operator validates the posting
hits the right GL. Missing bank account → no fake GL.

**Decision (user):** require a bank account to post (remove the silent `31010101`
fallback). The simulation always equals what posts.

## Scope

### Backend
1. **`payment_preview.compute_payment_entries(payment, *, bank_account=None)`**
   - `_resolve_bank_account` uses `bank_account` (the operator's current, possibly
     unsaved selection) first, then `payment.bank_account.gl_account`. **No
     `31010101`/CASH_ACCOUNT fallback.** When neither yields a GL, emit a
     placeholder cash line (`account="— select a bank account —"`, no code) at
     `credit = net` and flag it.
   - Return value gains nothing structurally, but the caller detects the missing
     GL (placeholder line) to set a response flag.
2. **`proposed_entries` action** — accept `?bank_account=<id>`, resolve the
   `BankAccount`, pass it as the override. Add `needs_bank_account: bool` to the
   response (true when the cash GL is unresolved).
3. **`post_payment`** — drop the `31010101`/CASH_ACCOUNT fallbacks for
   `bank_gl_account`: it is `payment.bank_account.gl_account` or nothing. The
   existing `missing` check then returns a clear 400 ("select a bank account with
   a GL") when absent. (Advance path already requires a bank account.)

### Frontend (`OutgoingPaymentsPage`)
4. **`ProposedEntries`** rendered **inside** `PaymentFormModal` (so it sees
   `form.bank_account`), not via the parent `footerSlot`:
   - No auto-preview. A **Simulate** button; on click it fetches
     `proposed_entries?bank_account=<form.bank_account>` and shows the table.
   - Changing the Bank Account selection **clears** the simulation (re-Simulate),
     so a stale GL is never shown.
   - When `needs_bank_account`, the cash line shows the placeholder and a hint to
     pick a bank account; a "Re-simulate" button lets the operator refresh.
   - Prop change: `PaymentFormModal` takes `proposedPaymentId` instead of a
     prebuilt `footerSlot`.

## Testing
- Backend (`accounting/tests/test_payment_proposed_entries.py`): with a
  `bank_account` override the cash line uses that account's GL; with none, the
  cash line is the placeholder and `needs_bank_account` is true (no `31010101`).
- Backend (`test_central_payment_processing` / payment-post tests): posting
  without a bank account returns 400; with one, the bank leg uses its GL. Update
  any test that posted without a bank account to set one.
- Live Playwright: open the payment form, click Simulate → cash line shows the
  selected bank account's GL; deselect the bank account → Simulate shows the
  placeholder; Save without a bank account is rejected.

## Out of scope
- Reworking the posted-payment view of `proposed_entries` (it already shows the
  real booked lines).
