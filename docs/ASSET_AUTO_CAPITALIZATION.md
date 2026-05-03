# Asset Auto-Capitalisation — SAP-Style Clearing Account Approach

## Overview

When a GL account is flagged `auto_create_asset = True` with an `asset_category` assigned in
Chart of Accounts master data, the system automatically:

1. Creates a `FixedAsset` sub-ledger record (SAP "Anlage")
2. Clears the capex GL to zero via a contra credit entry
3. Debits the asset reconciliation GL (cost account on the category)

This mirrors SAP's two-tier asset accounting: the **reconciliation GL** holds the control-account
balance; the **FixedAsset record** holds the per-asset sub-ledger identity and detail.

---

## Trigger Conditions

A line is eligible for auto-capitalisation when **ALL** of the following are true:

| Condition | Where configured |
|-----------|-----------------|
| `Account.auto_create_asset = True` | Chart of Accounts → Edit account |
| `Account.asset_category` is set | Chart of Accounts → Edit account |
| `AssetCategory.cost_account` is set | Settings → Asset Categories |
| The journal line is a **debit** (`line.debit > 0`) | Built by the posting path |

If the flag is on but the category or cost account is missing, posting raises a `ValidationError`
and rolls back — the system never silently skips capitalisation.

---

## Posting Entries by Source Document

### 1 — Journal Entry (manual)

```
DR  23040108  Capex Clearing          100   ← operator enters
CR  Bank / Cash / etc.                100   ← operator enters
─── auto-cap fires ───────────────────────
CR  23040108  Capex Clearing          100   ← contra (clears to zero)
DR  31xxxxxx  Asset Recon GL          100   ← capitalisation debit
```

FixedAsset record created with `acquisition_cost = 100`.

### 2 — AP Invoice (direct, no PO/GRN)

```
DR  23040108  Capex Clearing          100   ← per-line account from invoice line
CR  20100000  Accounts Payable        100   ← AP control (Supplier Recon GL)
    (vendor sub-ledger balance updated on Vendor model)
─── budget appropriation check ────────────
─── auto-cap fires ───────────────────────
CR  23040108  Capex Clearing          100   ← contra (clears to zero)
DR  31xxxxxx  Asset Recon GL          100   ← capitalisation (asset sub-account)
```

**Important:** The debit must be entered at the **invoice line level** (not the header account
field). The posting path iterates `VendorInvoiceLine.account` — only line-level accounts reach
the journal and can trigger auto-cap.

### 3 — Invoice Verification (3-way match: PO → GRN → Invoice)

Auto-cap fires at the **GRN stage**, when the receipt creates the first debit to 23040108:

```
GRN posting:
  DR  23040108  Capex Clearing        100   ← po_line.account (capex GL)
  CR  20601000  GR/IR Clearing        100   ← liability parked until invoice
  ─── auto-cap fires ───────────────────────
  CR  23040108  Capex Clearing        100   ← contra
  DR  31xxxxxx  Asset Recon GL        100   ← capitalisation

Invoice verification posting (clears GR/IR → AP):
  DR  20601000  GR/IR Clearing        100   ← clears the GRN liability
  CR  20100000  Accounts Payable      100   ← AP recognised
  (no second auto-cap — 23040108 is not debited again here)
```

---

## Net Ledger Effect

After all entries, the **capex GL (23040108) nets to zero** — it acts as a clearing account only.
The net impact is:

| Account | Movement |
|---------|----------|
| 23040108 Capex Clearing | DR 100, CR 100 → **net zero** |
| 20100000 Accounts Payable / Bank | CR 100 |
| 31xxxxxx Asset Recon GL | DR 100 |
| FixedAsset sub-ledger | Asset record created, `acquisition_cost = 100` |

---

## Sub-Ledger Linkage

Each auto-cap pair carries `JournalLine.asset = <FixedAsset>`.  The original debit line also has
`asset_id` stamped on it after successful capitalisation.  This provides the two-level drill-down:

- **GL level**: Asset Recon GL (31xxxxxx) shows aggregate balance
- **Sub-ledger level**: FixedAsset record shows per-asset cost, depreciation schedule, and
  source transaction

---

## Service Entry Point

```python
# accounting/services/asset_capitalization.py
from accounting.services.asset_capitalization import apply_asset_capitalization

apply_asset_capitalization(journal)   # idempotent, call inside @transaction.atomic
```

`_validate_journal_balanced` in `BasePostingService` calls this automatically. Every posting
path that calls `_validate_journal_balanced` inherits auto-cap for free:

| Posting path | File | Auto-cap via |
|---|---|---|
| Journal Entry (manual) | `accounting/views/core_gl.py` | `_validate_journal_balanced` |
| AP Invoice (UI path) | `accounting/views/payables.py` | `_validate_journal_balanced` (added 2026-04) |
| AP Invoice (service path) | `accounting/services/procurement_posting.py` | `_validate_journal_balanced` |
| GRN receipt | `accounting/services/procurement_posting.py` | `_validate_journal_balanced` |
| Payment Voucher | (treasury path) | `_validate_journal_balanced` |

---

## Common Configuration Errors

| Error | Cause | Fix |
|---|---|---|
| "Account 23040108 has no asset category" | `auto_create_asset=True` but no category set | Assign a category in Chart of Accounts |
| "Asset Category X has no cost account" | Category exists but `cost_account` is null | Set the Cost Account on the category in Settings |
| Auto-cap fires at GRN, not at invoice | Expected — 3-way match caps at receipt time | No action needed; this is correct behaviour |
| Asset created but capex GL not zeroed | `asset_category.cost_account` missing at time of posting | Assign cost account, reverse and re-post |

---

## Idempotency

The service is safe to call multiple times on the same journal.  A line is skipped if:
- `line._skip_auto_capitalize = True` (in-memory flag on contra/recon lines)
- `line.asset_id` is already set (persistent DB marker — prevents re-creation across restarts)

---

## Future Posting Paths

Any new posting path that creates a journal and calls `_validate_journal_balanced` automatically
gains auto-cap support.  **Do not** call `apply_asset_capitalization` directly from new views —
route through `_validate_journal_balanced` so the balance check and the capitalisation stay
coupled.
