# E-Payment — real-time gateway disbursement on Payment post (Sub-project B)

**Date:** 2026-09-28
**Status:** Design approved (brainstorming), ready for implementation plan
**Base branch:** new `feat/epayment` off current `main`

## 1. Goal

When a tenant has an **e-payment (gateway) toggle active** and platform keys are
configured, **posting an outgoing Payment to a vendor with bank details** fires a
**real-time Remita disbursement** instead of a direct bank debit. The accounting
posts to a **Gateway Settlement Clearing** GL at post time; the PSP webhook later
settles the clearing to Bank (or auto-reverses on failure). This is
**sub-project B**, built on the seam sub-project A created (`post_payment`).

## 2. Decisions (from brainstorming)

- **Base strategy:** **port + fix** the gateway code from `feat/payment-gateways`
  onto a fresh `feat/epayment` branch off `main` (main is ~41 commits ahead of
  that branch; only 4 files git-conflict). Do NOT merge the stale branch.
- **Auto-fire scope:** only **vendor payments with bank details** — i.e. a
  Payment whose `payment.vendor` is set and has a NUBAN `bank_account_number`,
  that is a real payable (invoice-backed / has allocations), and is NOT an
  advance or a direct/non-invoice PV. This is also the fix for CRITICAL (c).
- **Scope:** **disbursement (Remita) only.** Collections (Xpresspay/IGR, the
  `revenue_admin`/`integrations` apps, `gateway_collection.py`) are DEFERRED to a
  later cycle. Port the shared gateway core + the disbursement path.

## 3. Current state (what exists on `feat/payment-gateways`, tip `363a585`)

The gateway is fully built on that branch (three-dot `main...feat` = 49 files):
- **superadmin/** encrypted key store `PaymentGatewayProvider` (`gateway_models.py`,
  Fernet under `GATEWAY_KEK_HEX`, `gateway_crypto.py`), Remita connector +
  `disburse()` seam (`gateway_client.py`), inbound webhook (`gateway_webhook.py`),
  per-tenant toggle `TenantGatewaySetting` (fail-closed `is_usable`), append-only
  `GatewayTransaction` log, superadmin CRUD API (`gateway_views.py`), migration
  `superadmin/0016`.
- **accounting/services/** `gateway_disbursement.py` (`dispatch_payment_via_gateway`
  + `settle_gateway_disbursement`), `disbursement_controls.py`
  (`enforce_fiscal_period`/`enforce_payment_warrant`, extracted from post_payment).
- **core/** tenant enable endpoints (`core/views/gateway.py`), middleware pinning
  `/api/v1/gateway/webhook/` to the public schema.
- **frontend/** tenant page `PaymentGatewaySettings.tsx` (`/settings/payment-gateways`).
- **NOT present:** the superadmin credential-entry frontend tab (backend API
  exists, no React screen); `GATEWAY_SETTLEMENT_CLEARING` is NOT in
  `DEFAULT_GL_ACCOUNTS`; the 3 CRITICALs below are unfixed.

**The 4 git-conflict files** (touched by both branch and main): `accounting/views/payables.py`,
`frontend/src/App.tsx`, `frontend/src/components/Sidebar.tsx`, `quot_pse/settings.py`.
All other ported files are NEW. **Semantic deps** the ported code assumes from
main (verify signatures at port time): `get_vendor_ap_account`, `BasePostingService`
helpers, `get_gl_account`, `Payment`/`PaymentVoucherGov`/`Vendor` fields (all
confirmed present on main; `Vendor.bank_account_number`/`bank_sort_code`/`bank_name`
exist — NUBAN-validated).

## 4. The three CRITICALs — fixed as part of the port

**(a) Fail-open webhook.** `verify_webhook` HMACs the body with `provider.webhook_secret`;
when that secret is empty (it is NOT required by `is_configured`/`is_usable`), the
key is the publicly-known empty string, so an attacker forges a valid signature and
drives `settle_gateway_disbursement`. **Fix:** first line of each connector's
`verify_webhook` (remita + xpresspay) — `if not provider.webhook_secret: return False`;
and require `webhook_secret` presence for a webhook-driven provider to be usable.

**(b) Double-settlement race.** `settle_gateway_disbursement` / `settle_collection`
guard on an **unlocked** in-memory `txn.status`; PSPs retry callbacks concurrently, so
two deliveries both pass the guard and post two settlement journals (double cash-out /
double reversal). **Fix:** re-fetch under `select_for_update()` and re-check status
inside the atomic; add a partial unique index on the settlement `JournalHeader`
(`source_module='gateway_settlement'` + `source_document_id` + Posted) as a DB backstop.

**(c) PV misclassification.** `dispatch_payment_via_gateway` unconditionally books
`DR Accounts Payable (gross)`, which is wrong for advances and direct/non-invoice PVs
(salary/pension/statutory) — those must recognise expenditure and run the STRICT
appropriation + direct-PV warrant checks that `_post_direct_pv_payment` performs.
**Fix (= the auto-fire guard, §6):** only take the gateway path when the payment is a
real payable (`payment.vendor` with bank details, invoice-backed/allocations present),
NOT `is_advance`, NOT a direct/non-invoice PV.

## 5. Clearing GL

- `GATEWAY_SETTLEMENT_CLEARING` resolves via `get_gl_account("GATEWAY_SETTLEMENT_CLEARING",
  "Liability", "Gateway Clearing")`. It is **not seeded** — `_clearing_account()` raises
  otherwise. **Fix:** add `'GATEWAY_SETTLEMENT_CLEARING': '<4xxxxxxx liability code>'` to
  `DEFAULT_GL_ACCOUNTS` and seed the account per tenant (CoA rule: 4xxxxxxx = Liability;
  2xxxxxxx blocked). Confirm the code against the OAG chart (its liabilities are 4103xxxx).
- Journal shapes: **disburse** `DR AP gross · CR deductions · CR Clearing net`
  (cash not yet moved); **settle success** `DR Clearing net · CR Bank net`;
  **settle failure** reverse every original line + reinstate `vendor.balance += gross`.

## 6. Auto-fire wiring (the seam)

In `post_payment` (accounting/views/payables.py), in the normal AP branch, BEFORE the
DR-AP/CR-Bank post, add the gateway branch (this both auto-fires and enforces the
CRITICAL (c) classification guard):

```python
vendor = payment.vendor
is_real_payable = payment.allocations.exists() or _pv_is_invoice_backed(pv)
if (vendor and vendor.bank_account_number and not payment.is_advance and is_real_payable):
    setting = (TenantGatewaySetting.objects.select_related('provider')
        .filter(tenant=connection.tenant, is_active=True,
                provider__is_enabled=True, provider__supports_disbursement=True)
        .order_by('-is_default', 'provider__sort_order').first())
    if setting is not None and setting.is_usable:      # fail-closed: absent/inactive -> bank path
        result, journal = dispatch_payment_via_gateway(payment, setting, actor=request.user)
        return Response(self.get_serializer(payment).data)
# else fall through to the existing DR AP / CR Bank post (unchanged)
```

- **Fail-closed:** no setting, `is_active=False`, or unconfigured provider → the existing
  bank-debit path runs; the gateway never fires silently.
- The `IsApprover('post') + RequiresMFA()` gate on `post_payment` is untouched and still
  applies. `dispatch_payment_via_gateway` re-checks fiscal period + warrant.
- **PD-sourced payments** carry no `payment.vendor` (multi-line), so they never take the
  gateway branch — they post their own journal to bank via `post_document_sourced_payment`
  (unchanged). (A single-vendor PD provisioning could set `payment.vendor` to opt in — a
  documented future refinement, not v1.)

## 7. Configuration surfaces

- **Superadmin credential tab (the GAP):** a React screen mirroring `AIProvidersTab.tsx`
  against `PaymentGatewayProviderViewSet` — enter/rotate `api_key`/`secret_key`/
  `webhook_secret` (write-only), toggle `is_enabled`, `test_connection`, and view the
  `GatewayTransaction` log. Under the existing superadmin frontend.
- **Tenant e-payment settings:** the ported `/settings/payment-gateways` page + a
  **settlement-account view** — show which clearing GL is used (`GATEWAY_SETTLEMENT_CLEARING`
  resolved account), where it's used (the disburse/settle legs), and allow the tenant to
  change the mapped account (optional, per the request). Editing writes the tenant's GL
  mapping (a small settings model or an override on `DEFAULT_GL_ACCOUNTS` resolution).

## 8. Data flow (end to end)

```
Post Payment (vendor + bank details, invoice-backed, gateway active)
  → dispatch_payment_via_gateway: DR AP gross / CR deductions / CR Gateway Clearing net
    → disburse() seam → Remita (real-time), GatewayTransaction(status=sent), Payment Posted
  → PSP webhook (HMAC-verified, public schema):
       success → settle: DR Clearing / CR Bank (cash leaves), txn=success
       failure → reverse original journal, vendor.balance += gross, txn=reversed
Gateway inactive / no vendor bank details → existing DR AP / CR Bank (unchanged)
```

## 9. Error handling & controls

- Fail-closed toggle (§6); HMAC-required webhook (fix a); idempotent settle under lock +
  DB backstop (fix b); classification guard (fix c); auto-reversal on PSP failure;
  `GatewayTransaction` append-only, hash-not-payload; `per_transaction_cap` honored;
  `reconcile_gateway_transactions` poller as a webhook fallback.

## 10. Testing

- Toggle OFF → posting books the unchanged `DR AP / CR Bank` journal, no gateway call.
- Toggle ON + vendor-with-bank invoice payment → clearing journal posted + `disburse()`
  called (connector mocked), Payment Posted, `GatewayTransaction(sent)`.
- Advance / direct-PV / no-vendor / vendor-without-bank → gateway NOT fired (bank path),
  proving the classification guard (fix c) — non-vacuous.
- Webhook success → `DR Clearing / CR Bank`; webhook failure → reversal + vendor reinstated.
- **HMAC-required:** empty-secret / forged-signature webhook → 403 (fix a, non-vacuous).
- **Double-settle:** second concurrent settle is a no-op (fix b), no second journal.
- Clearing GL missing → clear error; seeded → resolves.
- Superadmin tab: keys write-only (never returned), toggle, test_connection.

## 11. Out of scope (deferred)

Collections/IGR (Xpresspay, `gateway_collection.py`, `revenue_admin`/`integrations`
apps) — a possible sub-project C. Single-vendor-PD gateway opt-in. Multi-beneficiary
batch gateway disbursement.

## 12. Risks

- **Porting 45 new files + 4 hand-merges** onto a moved-on main; the semantic deps must
  be re-validated. Mitigate: port in dependency order (superadmin core → services →
  wiring → frontend), compile/`manage.py check` after each group.
- The clearing-GL code + per-tenant seeding must match each tenant's CoA.
- Real Remita sandbox behavior is VERIFY-AGAINST-SANDBOX (connector marked so); tests mock
  the connector, so live sandbox verification is a separate manual step.
