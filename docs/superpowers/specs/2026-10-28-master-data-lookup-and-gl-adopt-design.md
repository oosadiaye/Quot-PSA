# Master-data duplicate lookup + "adopt an existing GL" on posting

**Date:** 2026-10-28
**Status:** Implemented

## Goal

1. **Creating master data** (Vendor, GL account / COA, MDA, and other registered
   master data): look up what already exists while the operator types and again
   on save. If something matches, warn and let them **use the existing record**,
   **create anyway**, or **go back** — so the same supplier / GL / MDA isn't
   registered twice under slightly different spellings.
2. **Posting**: the existing GL-coding check already warns when a line's
   description doesn't fit its GL account. Extend it so the warning also
   **suggests existing GL accounts that do fit**, and the operator can **adopt**
   one (the line is recoded), **post anyway**, or **go back**.

Both are advisory. Nothing blocks a save except the DB's own uniqueness rules.

## 1. Master-data duplicate lookup

### Backend

- `core/services/duplicate_lookup.py` — registry-driven. One `EntitySpec` per
  master-data type (`vendor`, `account`, `mda`, `admin_segment`,
  `ncoa_fund`, `ncoa_functional`, `ncoa_programme`, `ncoa_geographic`,
  `tsa_account`, `vendor_category`, `asset_category`, `item`): model, name field, code field,
  identifier fields, context fields. Adding a type is one registry entry.
- `find_matches(entity, values, exclude_id=None, limit=5)` returns
  `{id, code, name, is_active, level, score, reasons, extra}` ordered
  exact → likely → similar.
  - **exact** — same code, or an identifier collides after normalisation
    (Tax ID, registration number, e-mail, phone — compared on the last 9 digits
    so `+234` / `0` prefixes don't hide a match — bank account, MDA short name).
  - **likely / similar** — name similarity. Legal suffixes and filler
    (`Ltd`, `Limited`, `Plc`, `Nig`, `Nigeria`, `Enterprises` …) are dropped,
    tokens lightly stemmed, typos within edit-distance 1 forgiven, word order
    ignored. `1.0` only for an identical token set; fuzzy matches cap at `0.97`.
    `>= 0.90` is "likely", `>= 0.70` is "similar". A multi-word name wholly
    contained in another is "similar"; a single generic word never matches.
  - `exclude_id` omits the record being edited.
- `POST /core/duplicate-check/` `{entity, values, exclude_id?}` →
  `{entity, label, matches}`. Requires the tenant role's `view_<model>`
  permission for the entity (it reads the master list). Unknown entity → 400.
  Lookup errors degrade to `matches: []`.

### Frontend

- `hooks/useDuplicateCheck.ts`
  - `useDuplicateLookup(entity, values, {excludeId, enabled})` — debounced
    as-you-type matches; ignores out-of-order responses.
  - `useDuplicateGuard(entity)` → `guard(values, onProceed, {excludeId,
    onUseExisting})` + `modalProps`. A failed lookup never blocks the save.
- `components/DuplicateHint.tsx` — inline amber hint under the name field.
- `components/DuplicateWarningModal.tsx` — save-time prompt. "Create anyway" is
  hidden when the **code** collides (the server would reject it).
- Wired into: `VendorList` (Use this one → opens the existing vendor for edit),
  `ChartOfAccounts` (→ opens the existing account), `NCoAAdminForm` (MDA →
  navigates to the existing MDA's edit page), `ItemForm` (inventory product →
  opens the existing product), the NCoA Fund / Functional / Programme /
  Geographic forms, `TSAAccountForm` (bank account number + name), and the
  inline Vendor Category and Asset Category forms (→ switch to editing the
  existing category). Guard runs on **create** only; the inline hint
  also shows while editing (excluding the record itself).
- **Vendor CSV import** checks every row before creating it and *skips* exact /
  likely duplicates (including rows duplicated within the same file), listing
  them in the import summary.

## 2. Posting: adopt an existing GL

### Backend

`accounting/services/gl_coding_check.py` — for every line judged *suspect*,
`check_lines` now adds `suggestions: [{id, code, name, account_type, score,
source}]` (max 3):

- Candidates: active, **postable**, non-reconciliation accounts (header / control
  accounts are never suggested), restricted to the **same `account_type`** as the
  chosen account when it is known (a mis-coded expense line is recoded to another
  expense account, not to a bank account).
- Ranked by account-name fit to the description (`>= 0.5`), plus a small boost
  per similar **past posted** line coded to the account; an account with no name
  fit but `>= 2` similar past postings is suggested with `source: "history"`.
- One account-index query per call; history lookups capped at 25 suspect lines.
  Suggestion failures never break the check.

### Frontend

- `useGlCodingGuard.guard(lines, onProceed, onAdopt?, canUse?)` — `onAdopt(index,
  account)` recodes the line; `canUse` hides suggestions the form's account
  picker can't select. Adopting drops the line from the warning; once every
  flagged line is resolved the modal closes **without posting**, so the operator
  reviews the recoded lines and posts again (which re-checks them).
- `GlCodingWarningModal` lists suggestions per flagged line with **Use this
  account**. Without `onAdopt` the suggestions are shown as information only.
- Wired into the five forms that already ran the check — Journal, AP invoice,
  customer invoice, Purchase Requisition, Purchase Order — plus the Recurring
  Journal form (which posts automatically later, so a wrong GL costs more).

## Tests

- `accounting/tests/test_duplicate_lookup.py` — scoring, `find_matches` per
  entity, endpoint, GL suggestions.
- `frontend/src/hooks/__tests__/duplicateAndGlGuards.test.tsx` — both guards.

## Not in scope / follow-ups

- Forms without free-text GL coding were left alone: payment vouchers inherit the
  GL from an already-coded invoice, and accrual / deferral forms code one account
  at header level.
- The lookup is advisory in the UI; direct API clients bypass it. A server-side
  `?force=true` confirm on create is a possible v2.
- `accounting.MDA` (legacy model) has no create screen in the frontend; `admin_segment` is the
  MDA the UI creates.
