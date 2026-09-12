# ERP Interoperability Gateway — Build Plan

**Status:** Plan. Nothing in this document is built.
**Scope:** Connecting Quot PSA to a *different vendor's ERP* — SAP, Oracle,
FreeBalance, or an open-source suite — in either direction.
**Author's note:** every claim about this codebase below was checked against the
tree at `9e33790`; every claim about a third-party product is sourced in §10.

---

## 1. What this is, and what it is not

This plan covers **ERP-to-ERP interoperability**: moving master data and
transactions between Quot PSA and another vendor's financial system.

It is **not** the same thing as the `integrations` module already sketched in
`FUTURE_MODULES.md` (gap G7). That module covers **Nigerian payment and
identity rails** — Remita, NIBSS, GIFMIS, IPPIS, BVN/TIN. Those are
*counterparty* connections: a bank, a collections agent, a federal register.

The distinction matters because the failure modes differ:

| | Rails gateway (G7) | ERP gateway (this plan) |
|---|---|---|
| Counterparty | A service with one job | A system that also keeps a general ledger |
| Data shape | Fixed by the counterparty | Two charts of accounts that must be reconciled |
| Hardest problem | Retry / reconciliation | **Semantic mapping and system-of-record** |
| Failure looks like | A payment not confirmed | A trial balance that no longer balances |

They should share infrastructure — run log, credential store, retry, replay —
and they should **not** share adapters. §4 proposes one core that serves both.

> `FUTURE_MODULES.md` currently lives only on the unmerged `feat/future-modules`
> branch. This document stands alone and does not depend on that branch landing.
> If it does land, §4's core should be built once and G7 rebased onto it.

---

## 2. What exists today

Checked, not assumed:

| Fact | Evidence |
|---|---|
| **491 registered API endpoints** across 10 apps | `router.register` count in `*/urls.py` |
| OpenAPI schema is published | `drf-spectacular` 0.29.0, `/api/schema/`, `/api/docs/` |
| **No outbound integration exists** | `requests`/`httpx` imported in exactly one file, `superadmin/views.py` |
| `integrations/` app is a **dead stub** | No models, no migrations, not in `INSTALLED_APPS` |
| Encrypted credential storage exists | `superadmin/encryption.py` — Fernet, `EncryptedCharField` |
| Per-tenant module switching exists | `core.TenantModule`, per-tenant schema |
| Chart is a **6-segment NCoA** | Administrative, Economic, Functional, Programme, Fund, Geographic |
| Async worker is optional, not installed | `django-celery-beat` commented out in `requirements.txt` |

The two that shape the plan most:

**The API surface is already large and documented.** For *inbound* integration —
another system pushing into Quot — much of the work is already done. What is
missing is not endpoints but machine identity, idempotency and a staging area.

**There is no outbound capability at all.** For *outbound* — Quot calling SAP or
Oracle — this is a genuine greenfield: no HTTP client policy, no retry, no
circuit breaker, no run log, no credential rotation, no worker to run any of it.

---

## 3. What the targets actually expose

This is where a generic plan goes wrong, so it is worth being concrete. These
four systems are **not** four instances of the same problem.

| System | Real-time | Bulk | Auth | Difficulty |
|---|---|---|---|---|
| **SAP S/4HANA** | OData v2/v4 business objects | IDoc, file | OAuth 2.0 / basic / X.509 | Medium |
| **SAP ECC (legacy)** | BAPI / RFC | IDoc | SAP-proprietary | **High** |
| **Oracle Fusion ERP** | REST, per-transaction | **FBDI** — CSV → UCM → import job | OAuth 2.0 / basic | Medium |
| **FreeBalance** | **None published** | — | — | **Commercial, not technical** |
| **Odoo** | JSON-RPC / XML-RPC | Same | API key / session | Low |
| **ERPNext / Frappe** | REST | REST + bulk | Token / OAuth 2.0 | Low |

### The FreeBalance finding

FreeBalance's own *Version 7 Technology Brief* — 22 pages, their document —
contains **zero occurrences** of `API`, `REST`, `SOAP`, `web service`, `ESB`,
`JSON` or `XML`. Independent software directories list the product as **not
offering an API**.

Their interoperability claim is architectural, not programmatic. In their words,
the platform is *"fully unified… to enable seamless integration and
interoperability"* — meaning integration **between their own modules**, in
contrast to suites that *"require additional metadata management tools to achieve
interoperability… even within a suite of software from the same vendor."* Their
stated benefit is **"reducing interfaces"** — one system instead of several.

That is a coherent product position. It is also the opposite of an integration
surface. **A FreeBalance connector cannot be planned as an engineering task**,
because there is no published contract to build against. It resolves to one of:

1. **Database-level extraction** — read replica or scheduled dump. Their brief
   stresses database portability (an "open systems" argument), so the schema is
   reachable in principle. Reading another vendor's schema without a contract is
   unsupported and breaks on their upgrades.
2. **File exchange** — agree a CSV/fixed-width interface with the customer's
   FreeBalance implementation team.
3. **Their professional services** build the interface, at the customer's cost.

**Recommendation:** plan for (2), price it as a per-engagement integration rather
than a product feature, and do not put "FreeBalance connector" on a roadmap or a
tender response as though it were shipped code. Option (1) should be used only
for a one-time takeover, never for ongoing sync.

---

## 4. Architecture

One core, many adapters. The core is where correctness lives; adapters are
deliberately thin and stupid.

```
                    ┌──────────────────────────────────────────┐
                    │            Integration Core              │
  external  ──────► │  identity · staging · mapping · idem-    │ ◄────── Quot
   system           │  potency · run log · replay · recon      │          domain
                    └──────────────────────────────────────────┘
                        ▲          ▲          ▲          ▲
                   ┌────┴───┐ ┌────┴────┐ ┌───┴────┐ ┌───┴──────┐
                   │ sap-s4 │ │ oracle- │ │  odoo  │ │ generic- │
                   │ OData  │ │ fusion  │ │ RPC    │ │ csv/sftp │
                   └────────┘ └─────────┘ └────────┘ └──────────┘
                                                          ▲
                                              FreeBalance lands here
```

### Core models

- **`IntegrationSystem`** — one row per connected ERP per tenant. Adapter key,
  environment, base URL, enabled flag, credentials in the existing
  `EncryptedCharField`.
- **`EntityBinding`** — *per entity*, not per system: which side is authoritative
  for vendors, for the chart, for journals. §5 argues this is the single most
  important table in the design.
- **`FieldMap` / `ValueMap`** — the chart translation, versioned and effective-dated.
- **`StagingRecord`** — everything inbound lands here **first**, validated, and is
  promoted to a domain object only on success.
- **`IntegrationRun`** and **`IntegrationMessage`** — every exchange, with payload
  hash, direction, status, attempt count, and a failure reason an operator can act
  on without reading a log file.
- **`ExternalRef`** — `(system, entity_type, local_id, external_id)`, unique. The
  idempotency spine.

### Adapter contract

An adapter implements a narrow interface and is forbidden from touching domain
models directly. It declares capability rather than being assumed:

```python
class ErpAdapter(Protocol):
    key: str
    capabilities: frozenset[str]     # {"pull.coa", "push.journal", ...}

    def test_connection(self) -> HealthReport: ...
    def pull(self, entity: str, since: datetime | None) -> Iterator[dict]: ...
    def push(self, entity: str, payloads: list[dict]) -> list[PushResult]: ...
```

`capabilities` is what makes "any other ERP" tractable: the UI offers only what
an adapter declares, so a file-only adapter (FreeBalance) and a full REST adapter
(ERPNext) coexist without the core pretending they are equivalent.

---

## 5. The three hard problems

Everything else is plumbing. These three are where an ERP integration actually
fails, and they should be designed before any adapter is written.

### 5.1 Chart of accounts mapping

Quot's NCoA is **6 independent segments**. SAP uses company code + G/L account +
cost centre + profit centre + functional area. Oracle Fusion uses a configurable
chart of accounts with up to 30 segments. These do not correspond.

The mapping is therefore **many-to-many and lossy in at least one direction**, and
the loss is not symmetric: an inbound SAP posting may carry a dimension Quot has
no segment for, and an outbound Quot journal carries a Programme segment most
commercial charts have nowhere to put.

Consequences to design for, not discover:

- Mapping is **data, not code** — `ValueMap` rows, editable by a finance user,
  versioned, with an effective date. A code-level mapping means a deployment for
  every new cost centre.
- **Unmappable must be a first-class state.** A posting with no target segment is
  parked in staging for a human, never guessed and never silently dropped.
- The mapping needs its own **completeness report** before go-live: every active
  account on both sides, matched or explicitly waived.

### 5.2 System of record, declared per entity

The most expensive mistake available here is deciding "SAP is the master" or
"Quot is the master" as a single global answer. In practice it is per entity, and
often per field:

| Entity | Typical authority | Why |
|---|---|---|
| Chart of accounts | External, if a parent ministry mandates it | Federal return must reconcile |
| Vendors | Contested — usually external | But Quot holds the tax-clearance state |
| Appropriations | **Quot** | It is the legal authority to spend |
| Journals | **Quot**, pushed out | Quot is the transaction system |
| Payroll master | External (IPPIS) | Nominal roll is held federally |

`EntityBinding` stores this explicitly, with a direction (`pull`, `push`,
`bidirectional`, `off`) and a conflict rule. Bidirectional on any entity without
a documented conflict rule should be **refused by validation**, not merely
discouraged.

### 5.3 Idempotency, because this is a general ledger

A redelivered message must never double-post. This is the difference between an
integration bug and an audit finding.

- Every inbound message carries a **payload hash**; a repeat hash for the same
  `(system, entity, external_id)` is acknowledged and discarded.
- Every created object records an `ExternalRef` **in the same transaction** that
  creates it. A row created without its ref is a row that will be created twice.
- Outbound pushes use a **client-generated idempotency key** where the target
  supports one, and a pre-push existence check where it does not.
- Reversals are posted as **new reversing entries**, never as deletes — the
  existing `ImmutableModelMixin` already enforces this for posted records, and
  the gateway must not be given a way around it.

---

## 6. Phasing

Estimates are engineer-months and assume one engineer who already knows this
codebase. They exclude customer-side effort, which for SAP and Oracle is usually
larger than ours.

| Phase | What lands | Est. | Depends on |
|---|---|---|---|
| **0** | **Decisions** (§9) and one pilot customer with a named counterpart system | 0.25 | — |
| **1** | **Inbound foundation** — machine identity (API keys/OAuth client credentials, scoped, rotatable), staging, `ExternalRef`, run log, replay. No adapter yet. | 1.5–2 | — |
| **2** | **`generic-csv` adapter** — SFTP/upload, mapping UI, completeness report, reconciliation. Serves FreeBalance and any system with no API. | 1–1.5 | 1 |
| **3** | **Outbound foundation** — HTTP client policy, retry with backoff, circuit breaker, credential rotation, **and a real worker** (Celery is not currently installed) | 1–1.5 | 1 |
| **4** | **`odoo` or `erpnext` adapter** — cheapest real API, proves the adapter contract against something live | 0.5–1 | 3 |
| **5** | **`oracle-fusion` adapter** — REST for master data, FBDI for bulk journals | 2–3 | 3 |
| **6** | **`sap-s4` adapter** — OData; **ECC/BAPI is a separate estimate** and should not be promised without a scoping engagement | 2–3 | 3 |
| **7** | **Reconciliation & assurance** — period-end tie-out between both ledgers, drift alerting | 1–1.5 | 2+ |

**Total: 9.25–13.75 engineer-months** for all of it.

Phases 1–2 alone (**2.5–3.5 months**) deliver a defensible answer to *"can you
integrate with our existing system?"* for every counterparty including
FreeBalance, because file exchange is the universal fallback. That is the
recommended first commitment. Phases 5 and 6 should each wait for a customer who
is actually paying for that specific connector.

`★ Sequencing note ─────────────────────────────`
Phase 4 before 5 and 6 is deliberate. Building the adapter contract against Odoo
or ERPNext — free, self-hostable, honest REST — surfaces contract design errors
in days. Discovering the same errors against a customer's SAP sandbox costs weeks
and burns goodwill you cannot recover.
`───────────────────────────────────────────────`

---

## 7. Security

An integration gateway is a privileged, network-facing component that writes to
the general ledger. It gets its own review, not a shared one.

- **Machine identity is not a user account.** Per-system credentials, scoped to
  declared entities and directions, rotatable without downtime, revocable
  independently. Never a superuser token, never a human's token.
- **Credentials at rest** use the existing `EncryptedCharField` (Fernet) — but
  read `superadmin/encryption.py:27` before relying on it. The key is
  `SHA-256(settings.SECRET_KEY)`, not a dedicated KEK.

  That is adequate for the handful of SMTP passwords it holds today. It is a
  problem for a gateway holding production credentials to a customer's SAP or
  Oracle instance, because **rotating `SECRET_KEY` silently renders every stored
  credential undecryptable** — and rotating `SECRET_KEY` is exactly what you must
  do after a leak, which is exactly when you can least afford to also lose every
  integration credential.

  **Phase 1 should introduce a dedicated `INTEGRATION_KEK`** with versioned keys
  and a re-wrap path, on the pattern the snapshots module already uses
  (`SNAPSHOTS_KEK_HEX`, `snapshots/checks.py`) rather than the `SECRET_KEY`
  derivation. This is a small change now and a migration later.
- **Egress is allow-listed.** Outbound calls go only to hosts configured on
  `IntegrationSystem`. An adapter that can be pointed at an arbitrary URL by
  data is an SSRF primitive.
- **Payloads are evidence.** Retained with their hash for the audit trail — but
  vendor bank details and employee PII inside them are subject to the existing
  `pii_crypto` rules and log redaction filter. Do not log raw payloads.
- **SoD applies to integration too.** A connector that can both create and
  approve a payment has bypassed the segregation-of-duties controls the rest of
  the system enforces. Machine identities must carry a role that cannot approve.
- **Replay is an authorised action**, permission-gated and audit-logged, because
  replaying a payment batch is not a neutral operation.

---

## 8. What this plan deliberately excludes

- **A real-time two-way journal sync with SAP.** Sub-second bidirectional GL
  replication between two systems that both enforce budget control is a
  distributed-consensus problem wearing a business hat. Batch with reconciliation
  is the correct answer for PFM, and is what auditors expect to see.
- **An iPaaS.** MuleSoft, Boomi and Workato solve this, and a State ICT agency
  that already licenses one should use it. This plan assumes no iPaaS because most
  Nigerian States do not have one; if the customer does, phases 3–6 shrink
  substantially and should be re-estimated.
- **SAP ECC / BAPI / RFC.** Reachable, but a different skill set and a separate
  estimate. Do not bundle it into a S/4HANA quote.
- **Writing to another vendor's database.** Reading one under a takeover is
  defensible. Writing to one is not, under any deadline.

---

## 9. Decisions needed before Phase 1

These are yours, not mine, and each one changes the build:

1. **Which counterparty system is real, and for which customer?** A generic
   framework built without one concrete target tends to be generically wrong.
2. **Is there a paying customer for SAP or Oracle specifically?** If not, phases
   5–6 should stay unscheduled rather than sit on a roadmap.
3. **Celery** — Phase 3 needs a worker. `django-celery-beat` is currently
   commented out in `requirements.txt`. Adopting it is a deployment change
   (broker, worker process, monitoring) that should be decided on its own merits.
4. **Does any target customer already license an iPaaS?** Changes §8 materially.
5. **Who owns the mapping?** A finance user maintaining `ValueMap` rows is the
   design assumption. If it will in practice be an engineer, the UI investment in
   Phase 2 can be cut.

---

## 10. Sources

Third-party product claims above rest on these; codebase claims rest on the tree
at `9e33790` and are cited inline in §2.

- [FreeBalance Version 7 Technology Brief (PDF)](https://www.freebalance.com/wp-content/uploads/2022/03/Version-7-Technology-Brief.pdf) — 22pp; text extraction shows no occurrence of API/REST/SOAP/web service/ESB/JSON/XML. Interoperability and "reducing interfaces" quotes are from pp. 9–12.
- [FreeBalance Accountability Suite — Capterra](https://www.capterra.com/p/2710/FreeBalance-Accountability-Suite/) and [SoftwareSuggest](https://www.softwaresuggest.com/freebalance-accountability-suite) — both list the product as not offering an API.
- [FreeBalance product overview](https://www.freebalance.com/en/products/) — platform and architecture positioning.
- [Oracle Cloud ERP Integrations: APIs, Adapters & Integration Patterns — ERP Research](https://www.erpresearch.com/en-us/oracle-erp-cloud-integrations)
- [Oracle Fusion HDL vs FBDI vs REST API (2026 guide) — Lanverse](https://lanverse.in/blog/oracle-fusion-hdl-vs-fbdi-vs-rest-api-which-integration-method-should-you-use-2026-guide) — REST for per-transaction, FBDI for bulk.
- [FBDI and ERP adapter patterns — oAppsNet](https://www.oappsnet.com/2026/09/solving-the-data-integration-puzzle-in-oracle-fusion-cloud-how-fbdi-and-erp-adapter-tools-close-the-gap/) — CSV → UCM → import job.
- [Oracle A-Team: Fusion Cloud ERP integration patterns](https://www.ateam-oracle.com/oracle-fusion-cloud-erp-applications-integrations-guidelines-patternsuse-cases-using-oracle-paas)
- [Modernizing SAP with Oracle Fusion — Oracle docs](https://docs.oracle.com/en/solutions/modernize-sap-aidp-fusion/) — S/4HANA OData adapter, ECC via IDoc/file.
