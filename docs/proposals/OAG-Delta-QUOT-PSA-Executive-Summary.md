# Executive Summary — Upgrade from Odoo to QUOT PSA

**Office of the Accountant‑General (OAG), Delta State** · **Date:** 07/06/2026

## The Opportunity
The OAG runs **Odoo** for accounting in **one office (final reporting only)**. This proposal upgrades the OAG to **QUOT PSA** — a purpose‑built, **IPSAS‑compliant, GIFMIS‑aligned** public‑sector accounting platform — and extends it across **four functions in one integrated system**: **Management Accounting, Treasury, Final Reporting, and Document Control.**

## Scope
**In:** General Ledger & National Chart of Accounts (NCoA) · Budget & Appropriation · **Warrant (AIE)** controls · Treasury & Banking (TSA, Payment Vouchers) · **all payment processing** · Accounts Payable/Receivable · **Contract Management** (mobilization, retention, IPC/valuations, variations) · Fixed Assets · **full IPSAS report suite** · Document Control.
**Out (this phase):** **Procurement / Purchase Orders (PO)** and **Human Resources / Payroll (HR)** — available later as configuration, not new build.

## Why QUOT PSA over Odoo
Odoo is a general commercial ERP; it does not natively model the **Nigerian public‑finance control chain** — *Appropriation → Warrant/AIE → Commitment → Payment → IPSAS reporting* — nor contract certification/mobilization/retention, nor cross‑department segregation of duties. **QUOT PSA is built specifically for these**, with the warrant ceiling enforced before cash leaves the Treasury Single Account, full audit trails, and one‑click IPSAS statements.

## Deployment — Recommended Path
| Option | Sovereignty | In‑office speed | Outage resilience | Cost shape |
|---|---|---|---|---|
| Online (VPS/cloud) | In‑country if Nigerian DC | Depends on link | Needs dual ISP | Recurring |
| On‑premise | Highest | LAN‑fast | Works offline | Upfront |
| **① On‑prem + online DR (recommended)** | **Highest** | **LAN‑fast** | **Best (offsite DR)** | Upfront + small recurring |
| ② Cloud‑primary + local backup (fallback) | In‑country | Good (dual ISP) | Moderate | Recurring |

- **🥇 Recommended:** **On‑premise primary at OAG + automated encrypted Disaster‑Recovery backup to a Nigerian Tier‑III cloud** — maximises **data sovereignty + LAN speed** while removing single‑site disaster risk. *Requires a server room with redundant power (UPS + generator).*
- **🥈 Fallback (if the server room/power isn’t ready):** **Nigerian sovereign‑cloud primary + on‑prem local backup**, with **dual ISP** at OAG.

## Infrastructure at a Glance
- **On‑prem server (for speed):** enterprise rack server (Dell R760 / HPE DL380 Gen11), **high‑clock Xeon Gold, 128 GB ECC RAM, enterprise NVMe SSD in RAID 10**, redundant power, dual 10 GbE — plus **UPS + generator + ATS** and a local backup NAS.
- **Cloud:** **Nigerian Tier‑III / sovereign cloud** (e.g. **Galaxy Backbone** or **Rack Centre**), reserved NVMe vCPU, **≥99.9 % SLA**, NDPA‑2023‑compliant in‑country hosting.

## Compliance & Controls
**IPSAS** accrual reporting · **GIFMIS‑aligned** budget/warrant control · **RBAC + Segregation of Duties** · full **audit trail** · **NDPA 2023** alignment via in‑country hosting and encryption in transit and at rest.

## Indicative Timeline
**4–6 months** across six overlapping phases: mobilisation → core GL/Budget/Warrant → Treasury/AP‑AR → Contracts/Assets/Documents → IPSAS reporting + data migration + parallel run → training, UAT, go‑live, hypercare.

## Decisions Needed to Finalise
1. **User counts** per function + peak concurrency (final sizing).
2. **OAG server‑room & power readiness** → selects Scenario ① vs ②.
3. **Hosting choice** (Galaxy Backbone / Rack Centre / other) and data‑residency policy.

*Indicative figures will be confirmed at discovery against actual user counts, data volumes, and facility readiness. See the full proposal and the indicative cost/BOM for detail.*
