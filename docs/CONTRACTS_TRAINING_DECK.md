---
marp: true
theme: default
paginate: true
size: 16:9
header: 'Quot PSE · Contract & Milestone Payments'
footer: 'Delta State Government · FY 2026'
style: |
  section { font-family: 'Segoe UI', 'Helvetica', sans-serif; }
  h1 { color: #0b5394; }
  h2 { color: #1a3a5e; border-bottom: 2px solid #d0d7de; padding-bottom: 4px; }
  table { font-size: 0.85em; }
  code { background: #f5f7fa; padding: 1px 5px; border-radius: 3px; }
  .small { font-size: 0.8em; color: #555; }
---

<!-- _class: lead -->

# Contract & Milestone Payment Management

## Training Deck — Delta State IFMIS Pilot

Quot PSE · FY 2026 Rollout

<br>

Ministry of Finance · Office of the Accountant-General · Bureau of Public Procurement

---

## Who this deck is for

| Audience | What you will learn |
|---|---|
| Procurement officers | How to draft and activate contracts |
| Project supervisors / MDAs | Raising milestone certificates (IPCs) |
| Internal auditors | The overpayment controls and audit trail |
| Treasury / PV unit | Voucher raising and payment release |
| System administrators | Configuration, seed data, troubleshooting |

<br>

**Duration:** 90 minutes (60 presentation + 30 hands-on).

---

## The problem we are solving

> In 2023 Nigerian state audit reports flagged **₦14.6 billion** in
> contract overpayments — mostly cases where cumulative payments
> exceeded the contract ceiling, or where mobilization advances were
> paid but never recovered.

Quot PSE's contract module makes every one of those attacks
**physically impossible** before the cash leaves the TSA.

---

## The five layers of defence

| Layer | Stops overpayment by… |
|---|---|
| **Database** | `CheckConstraint` rows + PostgreSQL trigger refuse to persist an over-ceiling balance |
| **Service** | Every money operation runs under `SELECT FOR UPDATE` with an optimistic version bump |
| **API** | Serializers reject malformed money values and permissions block unauthorised actors |
| **UI** | State-invalid buttons are disabled; users physically cannot click them |
| **Workflow** | Segregation of duties — no single person can take a contract from draft to paid |

Only **one** layer has to hold. All five hold.

---

## The contract lifecycle

```
DRAFT ──activate──▶ ACTIVATED ──▶ IN_PROGRESS
                                    │
                                    ▼
                          PRACTICAL_COMPLETION
                                    │
                                    ▼
                          DEFECTS_LIABILITY (typically 365 days)
                                    │
                                    ▼
                          FINAL_COMPLETION ──▶ CLOSED
```

You **cannot** skip a stage. A contract in `DRAFT` cannot jump to
`IN_PROGRESS` — the database rejects it.

---

## The IPC (Interim Payment Certificate) lifecycle

```
DRAFT ──submit──▶ SUBMITTED ──certify──▶ CERTIFIER_REVIEWED
                                              │
                                              ▼
                                          APPROVED ──raise_voucher──▶ VOUCHER_RAISED
                                                                         │
                                                                         ▼
                                                                       PAID
```

Each arrow is a separate action by a separate user. The system refuses
to let the same person do two adjacent steps.

---

## Segregation of duties — the 5 roles

| Role | Permission | Can do |
|---|---|---|
| **Drafter** | `contracts.add_contract` | Create contract, submit IPC |
| **Certifier** | `contracts.certify_ipc` | Certify measured work |
| **Approver** | `contracts.approve_ipc` | Approve certified IPC |
| **Voucher raiser** | `accounting.add_paymentvoucher` | Raise payment voucher |
| **Payer** | `accounting.release_payment` | Release cash from TSA |

Five distinct user accounts are **required** — not a convention.

---

## Worked example: a ₦450M road contract

**DSG/WORKS/2026/001 — Warri-Sapele Road, Section A**

| Quantity | Value |
|---|---|
| Contract sum | ₦450,000,000 |
| Mobilization rate | 15 % |
| Mobilization advance | ₦67,500,000 |
| Retention rate | 5 % |
| Monthly IPC target | ~₦45,000,000 |

Ten monthly IPCs of ₦45M each, mobilization recovered pro-rata,
retention held until defects-liability expiry.

---

## Statutory deductions (Circular AG/CIR/54/C/Vol.10/1/134, Apr 2026)

| Deduction | Rate | When |
|---|---|---|
| **Stamp Duty** | **Nil** — abolished | Never (applies to all awards regardless of date) |
| **Handling Charge** | **0.5 %** of gross contract value (factor 0.5/107.5 = 0.004651) | Point of **first** payment only |
| **Status Verification** | **₦40,000.00** flat | Once per contractor/vendor per year |

Worked: on DSG/WORKS/2026/001 (₦450M):
- Handling Charge at first IPC = 450,000,000 × 0.004651 ≈ **₦2,093,023.26**
- Status Verification (year 1) = **₦40,000.00**
- Stamp Duty = **₦0.00**

All three codified in `accounting.services.contract_deductions`.

---

## What happens if you try to overpay?

Suppose cumulative certified is ₦445M and someone submits a ₦20M IPC:

1. **Service check** — loads `ContractBalance`, computes
   `445M + 20M = 465M > 450M` → raises `OverpaymentError` with a
   human-readable explanation and structured context.
2. **Database backstop** — even if the service check is bypassed
   (bug, direct SQL, malicious actor with DB access), the trigger
   `trg_contracts_balance_guard` raises `SQLSTATE 23514` and the
   transaction aborts.

**No cash moves. No partial update is left behind.**

---

## Mobilization: the advance payment rule

- Paid once, at the start of the contract.
- **Capped at 30 %** (database constraint — cannot be overridden).
- Must be **fully recovered** through IPC deductions before final
  payment.
- `mobilization_recovered ≤ mobilization_paid` — enforced at the
  database layer.

A contract cannot be closed while any mobilization remains
unrecovered.

---

## Retention: the defects-liability guarantee

- Deducted from each IPC (typically 5 %, capped at 20 %).
- Held until the **defects liability period** expires (default 365
  days from practical completion).
- Released in two halves: 50 % at practical completion, 50 % at final
  completion — or per the contract's specific schedule.
- `retention_released ≤ retention_held` — enforced at the database
  layer.

---

## The audit trail

Every state transition writes an immutable `ContractApprovalStep` row:

| Field | What it records |
|---|---|
| `object_type` / `object_id` | Which contract or IPC was acted on |
| `step_number` | Position in the sequence |
| `role_required` | Permission the actor needed |
| `action_by` | The actor |
| `action` | APPROVE / REJECT / RETURN |
| `notes` | Free-text justification |
| `created_at` | Tamper-evident timestamp |

Audit reports pull from this table. Entries are **append-only** — no
delete endpoint exists.

---

## Variations: changing the ceiling

Contracts may need additional work (variation orders) or scope
reductions (omissions). Variations:

1. Must be **approved** before they affect the ceiling.
2. Require the same SoD discipline as IPCs (proposer ≠ approver).
3. Have their own approval tier depending on value (LOCAL / BOARD / BPP).
4. Update `ContractBalance.contract_ceiling` atomically on approval —
   the DB trigger checks the new ceiling against existing certified
   value to prevent retroactive overpayment.

---

## Hands-on: activate a contract (live demo)

1. Log in as `procurement_officer`.
2. Create a DRAFT contract.
3. Try to activate it yourself → **system rejects** (SoD).
4. Log out, log in as `procurement_head`.
5. Activate → contract number assigned, `ContractBalance` created.
6. Open DB console → confirm the balance row exists with
   `version=1` and ceiling matching the original sum.

---

## Hands-on: submit and pay an IPC

1. Drafter creates IPC for ₦10M → SUBMITTED.
2. Certifier reviews measured work → CERTIFIER_REVIEWED.
3. Approver approves → APPROVED, `cumulative_gross_certified` rises to
   ₦10M, `pending_voucher_amount` rises to the net payable.
4. Voucher raiser generates PV → VOUCHER_RAISED.
5. Payer releases cash → PAID, `cumulative_gross_paid` rises,
   `pending_voucher_amount` drops to zero.

Each step is a separate user, separate audit entry.

---

## Reports you can run

| Report | Purpose |
|---|---|
| **Contract register** | All contracts by status, MDA, fiscal year |
| **Payment register** | All IPCs and their state |
| **Ceiling utilisation** | Which contracts are approaching their ceiling |
| **Mobilization recovery** | Outstanding advances by contract |
| **Retention held** | Funds held per contract |
| **SoD compliance** | Any near-violations flagged in audit |

All reports respect tenant isolation — an MDA user sees only its own
MDA's contracts.

---

## Seeded demo contracts (training DB)

Three sample contracts pre-loaded for practice:

| Number | Title | Sum | Status |
|---|---|---|---|
| `DSG/WORKS/2026/001` | Warri-Sapele Road | ₦450M | ACTIVATED |
| `DSG/CONSULTANCY/2026/002` | M&E Framework | ₦45M | ACTIVATED |
| `DSG/GOODS/2026/003` | DELSUTH Medical Equipment | ₦120M | DRAFT |

Run `python manage.py tenant_command seed_demo_contracts --schema=demo`
to (re-)load them. Idempotent — running twice doesn't duplicate.

---

## Common mistakes — and how the system catches them

| Mistake | What the system does |
|---|---|
| Drafter tries to activate own contract | Rejects with `SegregationOfDutiesError` |
| Certifier tries to approve own certification | Rejects with `SegregationOfDutiesError` |
| IPC total exceeds ceiling | Rejects with `OverpaymentError`; DB trigger backs it up |
| Mobilization rate > 30 % entered | Rejected at form validation **and** at DB |
| Two vouchers raised for one IPC | Unique-index rejects the second |
| Payment made without an approved IPC | State check rejects it |

---

## Troubleshooting

| Symptom | First thing to check |
|---|---|
| "Contract not found" | Are you in the right tenant schema? |
| "Cannot activate" | Are `signed_date`, start/end dates all set? |
| "Segregation of duties violation" | Different user must perform this action |
| "Overpayment attempted" | Review prior IPCs — someone may have already paid |
| "Invalid state transition" | Check the current status; skipping stages not allowed |

Full developer docs: `docs/CONTRACTS_MODULE.md`.

---

## What happens if the system is wrong?

It has a bug. Report it. **But** even a bug cannot cause overpayment
because the PostgreSQL trigger is the final gate.

If the trigger itself were bypassed (e.g., superuser direct DML), the
daily reconciliation job would catch the drift the next morning and
raise a ticket — because `ContractBalance.version` would no longer
match the journal of `ContractApprovalStep` entries.

Defence in depth is real. Trust the system; verify with audit.

---

## Go-live checklist

- [ ] All 5 user roles created for each MDA
- [ ] Vendor register seeded
- [ ] NCoA codes configured for the MDA's expenditure heads
- [ ] Fiscal year 2026 created and `ACTIVE`
- [ ] Appropriations loaded for each MDA
- [ ] Demo contracts seeded in UAT schema (for training)
- [ ] At least one full DRAFT → PAID walkthrough completed by each MDA
- [ ] Audit team trained on reading `ContractApprovalStep`
- [ ] Backup & restore drill completed

---

<!-- _class: lead -->

# Questions?

## Contact

- **Technical support:** `ifmis-support@deltastate.gov.ng`
- **Policy / workflow:** Office of the Accountant-General
- **BPP compliance:** Bureau of Public Procurement
- **Training coordination:** Quot PSE rollout team

<br>

<span class="small">Quot PSE · Delta State IFMIS · FY 2026</span>
