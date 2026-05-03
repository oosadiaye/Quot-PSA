# Contract & Milestone Payment Management Module

Developer documentation for the `contracts/` Django app. This module
runs Delta State's contract lifecycle from award through final
payment, with **structural overpayment prevention** as the core design
constraint.

---

## 1. Goal

Make contract overpayment **physically impossible** at every layer:

| Layer | Control |
|---|---|
| Database | `CheckConstraint` rows + PostgreSQL `BEFORE UPDATE` trigger + partial `UNIQUE INDEX` |
| Service | `@transaction.atomic` + `select_for_update()` + optimistic `version` bump |
| API | DRF permissions + serializer validation |
| UI | Disabled controls on state-invalid actions |
| Workflow | Segregation of duties: drafter ≠ certifier ≠ approver ≠ voucher raiser ≠ payer |

Only **one** of these layers has to hold for a given attack to fail.
The test suite in `test_overpayment_integration.py` exercises 15
attack vectors; all are blocked.

---

## 2. Domain model

```
Contract (root aggregate)
├── ContractBalance          (1:1 — single-row ledger, DB-enforced)
├── ContractVariation *      (additions / omissions, approval-gated)
├── ContractMilestone *
│   └── InterimPaymentCertificate (IPC) *
│       └── ContractPayment  (the actual cash-out event)
└── ContractApprovalStep *   (immutable audit trail)
```

### Contract

| Field | Type | Invariants |
|---|---|---|
| `contract_number` | `CharField(30) UNIQUE` | Auto-assigned on activation (`DSG/{TYPE}/{YEAR}/{NNN}`) |
| `original_sum` | `Decimal(20,2)` | `> 0` (CheckConstraint) |
| `mobilization_rate` | `Decimal(5,2)` | `0..30` (CheckConstraint + validator) |
| `retention_rate` | `Decimal(5,2)` | `0..20` (CheckConstraint + validator) |
| `status` | `CharField(30)` | State machine — see §4 |

Computed: `contract_ceiling = original_sum + Σ(approved variations)`.

### ContractBalance — the single-row ledger

One row per contract. Stores *cumulative* amounts so every write is
idempotent and auditable:

| Field | Invariant |
|---|---|
| `contract_ceiling` | Snapshot of the current ceiling |
| `cumulative_gross_certified` | `≥ 0` |
| `pending_voucher_amount` | `≥ 0` |
| `cumulative_gross_paid` | `≥ 0`, `≤ cumulative_gross_certified` |
| `mobilization_paid` / `mobilization_recovered` | `mobilization_recovered ≤ mobilization_paid` |
| `retention_held` / `retention_released` | `retention_released ≤ retention_held` |
| `version` | Monotonic — bumped on every write |

**Six `CheckConstraint` rows** enforce these at the DB layer:
`certified_non_negative`, `paid_non_negative`, `paid_lte_certified`,
`mob_recovered_lte_paid`, `retention_released_lte_held`,
`ceiling_positive`.

### The trigger

`contracts/migrations/0002_contract_balance_trigger.py` installs
`trg_contracts_balance_guard` — a `BEFORE UPDATE` trigger that raises
`SQLSTATE 23514` (check_violation) when the sum of certified plus
pending exceeds the ceiling. This is the **last line of defence**: if
a service bug lets through an over-ceiling write, the trigger rejects
it before commit.

A partial `UNIQUE INDEX` on `(contract_id)` where row is active
prevents a second `ContractBalance` row from being inserted — you
cannot overpay by creating a parallel ledger.

---

## 3. Services (state-mutating operations)

All services are class-methods under `contracts/services/`. They share
three conventions:

1. `@transaction.atomic` at the entrypoint.
2. `select_for_update()` on the `ContractBalance` row to serialise
   concurrent writes.
3. Optimistic `version` bump — a second transaction on the same
   balance either blocks on the row lock or fails the `version` check.

| Service | Entry method | Role |
|---|---|---|
| `ContractActivationService` | `activate(contract, actor)` | DRAFT → ACTIVATED, creates `ContractBalance` |
| `IPCService` | `submit`, `certify`, `approve`, `raise_voucher`, `pay` | IPC lifecycle + ledger updates |
| `MobilizationService` | `pay_advance`, `recover` | Advance payment and recovery |
| `RetentionService` | `release` | Retention released at final completion |
| `VariationService` | `approve` | Increases / decreases the ceiling |
| `ContractClosureService` | `close` | Final completion → CLOSED |

### Structured exceptions

All services raise subclasses of `ContractServiceError` with a `.code`
and `.context`, and a `.to_dict()` method for API responses:

```python
raise OverpaymentError(
    "IPC total would exceed contract ceiling.",
    context={
        "contract_id": contract.pk,
        "ceiling": str(ceiling),
        "attempted_total": str(attempted),
    },
)
```

Views map these to HTTP 409/422 via `contracts/views/_helpers.py`.

---

## 4. State machines

### Contract

```
DRAFT → ACTIVATED → IN_PROGRESS → PRACTICAL_COMPLETION
      → DEFECTS_LIABILITY → FINAL_COMPLETION → CLOSED
```

`ALLOWED_CONTRACT_TRANSITIONS` in `contracts/models/contract.py` is the
single source of truth. `Contract.transition_to()` rejects any
non-adjacent jump with `InvalidTransitionError`.

### IPC

```
DRAFT → SUBMITTED → CERTIFIER_REVIEWED → APPROVED
      → VOUCHER_RAISED → PAID
```

Skipping states is impossible — the service entry method checks the
current state first.

---

## 5. Segregation of duties

Each IPC transition requires a different user from the previous one:

| Action | Blocks if actor is previous… |
|---|---|
| `certify` | drafter / submitter |
| `approve` | certifier |
| `raise_voucher` | approver |
| `pay` | voucher raiser |

Implemented in each service by comparing `actor.pk` to the stored
`*_by_id` field. Violation raises `SegregationOfDutiesError`.

Activation has the same rule: `created_by ≠ actor`.

---

## 6. Numbering

`contracts/services/numbering.py::next_contract_number()` generates a
gap-free sequence per `(contract_type, fiscal_year)` by locking the
max existing number with `select_for_update()`. Format:

```
DSG/{WORKS|GOODS|CONSULTANCY|NON_CONSULTANCY}/{YYYY}/{NNN}
```

---

## 7. Tests

```
contracts/tests/
├── conftest.py                        — tenant schema + shared fixtures
├── test_structural_controls.py        — pure-logic (stub fixtures)
├── test_computations.py               — money arithmetic
├── test_numbering.py                  — numbering collisions
├── test_overpayment_integration.py    — 15 attack vectors (DB-backed)
├── test_seed_demo_contracts.py        — seed command structural checks
├── test_sla.py
└── test_tasks.py
```

### Running

```bash
# Full suite with coverage
pytest contracts/tests/ --cov=contracts --cov-report=term-missing

# Just the overpayment attacks
pytest contracts/tests/test_overpayment_integration.py -v

# Structural-only (no DB, fast)
pytest contracts/tests/test_structural_controls.py contracts/tests/test_seed_demo_contracts.py
```

### Tenant-schema quirk

Integration tests run under a dedicated `pytest_schema` tenant. The
session-scoped `django_db_setup` fixture in `conftest.py` disconnects
the `core.log_model_changes` audit signal while the tenant schema
migrates — otherwise migration `0080_budgetcheckrule` trips on the
legacy `django_content_type.name NOT NULL` column that
`contenttypes.0002` fails to strip from tenant schemas.

---

## 8. Seed data

```bash
python manage.py tenant_command seed_demo_contracts --schema=<tenant>
python manage.py tenant_command seed_demo_contracts --schema=<tenant> --clear
python manage.py tenant_command seed_demo_contracts --schema=<tenant> --dry-run
```

Three Delta State contracts (idempotent):

| Number | Title | MDA | Sum | Status |
|---|---|---|---|---|
| `DSG/WORKS/2026/001` | Warri-Sapele Road (Section A) | Ministry of Works | ₦450,000,000 | ACTIVATED |
| `DSG/CONSULTANCY/2026/002` | M&E Framework Consultancy | Ministry of Economic Planning | ₦45,000,000 | ACTIVATED |
| `DSG/GOODS/2026/003` | Medical Equipment for DELSUTH | Ministry of Health | ₦120,000,000 | DRAFT |

Total demo ceiling: **₦615,000,000**.

The `reference` field (not `contract_number`) carries the `DEMO-CON`
marker so `--clear` can find seeded rows without polluting the
production-facing contract identifier.

---

## 9. API surface (DRF)

Routes mounted under `/api/contracts/` via `contracts/urls.py`:

| Verb | Path | Action |
|---|---|---|
| `GET / POST` | `/contracts/` | List / create contracts |
| `POST` | `/contracts/{id}/activate/` | → ACTIVATED |
| `POST` | `/contracts/{id}/variations/` | Add variation |
| `POST` | `/variations/{id}/approve/` | Approve variation |
| `POST` | `/ipcs/{id}/submit/` | DRAFT → SUBMITTED |
| `POST` | `/ipcs/{id}/certify/` | → CERTIFIER_REVIEWED |
| `POST` | `/ipcs/{id}/approve/` | → APPROVED |
| `POST` | `/ipcs/{id}/raise_voucher/` | → VOUCHER_RAISED |
| `POST` | `/ipcs/{id}/pay/` | → PAID |

Errors:

| Code | Meaning |
|---|---|
| `400` | Validation error (malformed input) |
| `403` | Permission or segregation of duty |
| `409` | Invalid state transition |
| `422` | Overpayment / ceiling breach |

---

## 10. Statutory deductions on contract payments

Per Delta State Circular **AG/CIR/54/C/Vol.10/1/134** (April 2026),
contract payments carry three deductions. All rates are centralised in
`accounting.services.contract_deductions` — **do not** hard-code them
elsewhere.

| Deduction | Rate | Trigger |
|---|---|---|
| Stamp Duty | **Nil** (abolished) | — |
| Handling Charge | **0.5 %** of gross contract value (factor = 0.5/107.5 = 0.004651) | First payment on contract / first payment after upward revision |
| Status Verification | **₦40,000.00** flat | Once per contractor/vendor per calendar year |

Callers (IPC pay service, PV service) should invoke
`compute_all(gross_contract_value, payment_amount, is_first_payment,
status_verification_paid_this_year)` and persist the non-zero lines as
`PaymentVoucherDeduction` rows. Zero lines are useful to retain in the
audit trail to prove the rule was evaluated.

Tests: `accounting/tests/test_contract_deductions.py` — freezes rates
and circular reference so a policy change is a deliberate edit, not a
silent drift.

---

## 11. Extending the module

**Adding a new IPC state**: update `ALLOWED_IPC_TRANSITIONS`, add the
service entry method, add the SoD check, add an attack test.

**Adding a new overpayment invariant**: add a `CheckConstraint` on
`ContractBalance`, then update the trigger, then add a service-layer
check that raises `OverpaymentError`, then add an attack test that
tries to break it at each layer.

**The golden rule**: every invariant is enforced at **at least two
independent layers**. The DB is the final backstop; the service layer
provides the user-friendly error. Never rely on one alone.
