# Proposal — Upgrade of the OAG Accounting Solution from Odoo to QUOT PSA

**Prepared for:** Office of the Accountant‑General (OAG), Delta State
**Subject:** Replacement/upgrade of the existing Odoo accounting deployment with **QUOT PSA** (Public‑Sector Accounting platform)
**Date:** 07/06/2026
**Status:** Draft for review

---

## 1. Executive Summary

The OAG currently runs **Odoo** for accounting in a **single office (final reporting only)**. This proposal covers upgrading to **QUOT PSA**, a purpose‑built, IPSAS‑compliant, GIFMIS‑aligned public‑sector accounting platform, and extending it across the OAG to cover **four operating functions in one integrated system**:

1. **Management Accounting**
2. **Treasury**
3. **Final Reporting**
4. **Document Control**

**In scope:** General Ledger & Chart of Accounts (NCoA), Budget & Appropriation, **Warrant (AIE)** controls, Treasury & Banking, Accounts Payable/Receivable and **all payment processing**, **Contract Management (with all features — mobilization, retention, IPC/valuations, variations)**, **Fixed Assets**, and **all IPSAS compliance reports**.

**Explicitly out of scope (this phase):** **Procurement / Purchase Orders (PO)** and **Human Resources / Payroll (HR)**.

This document also analyses three deployment models — **online (VPS/cloud)**, **on‑premise (local server)**, and **hybrid** (deploy online + run on‑premise, or deploy on‑premise + back up online) — with pros/cons, recommended server and cloud specifications, and a **recommended best‑fit scenario** tuned to Nigerian public‑sector realities (data sovereignty, power, and connectivity).

> **Bottom line recommendation:** **On‑premise primary at OAG + automated encrypted online (Nigerian Tier‑III) Disaster‑Recovery backup** — the hybrid model that maximises data sovereignty and LAN speed while eliminating the single‑site disaster risk of a pure on‑premise deployment. A fully **Nigerian sovereign‑cloud‑primary** model is the recommended fallback if OAG’s server‑room/power readiness is not yet in place.

---

## 2. Background & Current State

| Item | Current (Odoo) | Target (QUOT PSA) |
|---|---|---|
| Footprint | One office — **final reporting** only | OAG‑wide: **Management Accounting, Treasury, Final Reporting, Document Control** |
| Domain fit | General‑purpose commercial ERP, localised | **Public‑sector‑native** (NCoA, MDA structure, Appropriation, Warrant/AIE, TSA, IPSAS) |
| Budget control | Limited / add‑on | **Native appropriation + warrant ceiling enforcement** at commitment and payment stages |
| Contracts | Generic | **FIDIC/Delta‑WORKS contract lifecycle** (mobilization, retention, IPC) |
| Reporting | Commercial financials | **Full IPSAS suite + budget‑performance reports** |
| Multi‑office | Single instance | **Multi‑department, role‑segregated, audit‑trailed** |

**Why upgrade:** Odoo was adequate for a single final‑reporting office but does not natively model the **Nigerian public‑finance control chain** (Appropriation → Warrant/AIE → Commitment → Payment → IPSAS reporting), nor the **contract certification/mobilization/retention** workflow, nor segregation of duties across treasury vs. reporting vs. management accounting. QUOT PSA is built specifically for these.

---

## 3. Functional Scope (What QUOT PSA Delivers to OAG)

### 3.1 In Scope

**A. General Ledger & Chart of Accounts**
- Multi‑dimensional **National Chart of Accounts (NCoA)**: Administrative (MDA), Economic, Fund, Functional, Programme, and Geographic segments.
- Journal entries with auto‑numbered vouchers (JV‑####), multi‑dimensional posting, draft → posted controls, reversals, and **drill‑down from any GL balance to the originating document and its double‑entry**.
- Period control and **year‑end close**.

**B. Budget & Appropriation**
- Appropriation capture (original + supplementary), **virement/transfer** between lines.
- **Budget‑check rules** (NONE / WARNING / HARD‑STOP) per GL series.
- Budget vs. Actual, commitment, and execution tracking.

**C. Warrant (AIE) Controls** *(a core differentiator)*
- **Authority to Incur Expenditure (AIE)/Warrant** release against appropriations (quarterly/periodic cash release).
- **Warrant‑ceiling enforcement** so cash cannot leave the Treasury Single Account beyond released warrants — enforced at **AP‑invoice posting, outgoing payment, vendor down‑payment, and contract mobilization** stages, with a single tenant‑level master switch (GIFMIS‑compliant by default).
- Warrant expiry/lifecycle management.

**D. Treasury & Banking**
- **Treasury Single Account (TSA)** management, TSA transfers, cash position.
- **Payment Vouchers (PV)** with the full authority‑to‑pay workflow.
- **All outgoing payments** (vendor payments, advances/down‑payments, mobilization disbursements), payment allocation/matching, and **bank reconciliation**.

**E. Accounts Payable / Receivable & All Payments**
- Vendor invoices, customer invoices, payments, **allocation to outstanding invoices**, vendor advances (F‑48) and clearing (F‑54).
- Supplier account/transaction history with cleared/outstanding visibility and Excel export.

**F. Contract Management (all features)**
- Contract register and activation; **mobilization advances with FIDIC pro‑rata recovery**; **retention (lump‑sum reserve model)**; **Interim Payment Certificates (IPC)/valuations**; variations; segregation‑of‑duties on certify/approve/pay.
- Appropriation + warrant validation on mobilization and certified payments.

**G. Fixed Assets**
- Capitalisation, depreciation runs, disposal, and revaluation with automatic GL posting.

**H. IPSAS Compliance Reporting (full suite)**
- Statement of Financial Position, Statement of Financial Performance, **Cash Flow Statement**, Statement of Changes in Net Assets, **Notes to the Financial Statements**.
- Budget‑performance suite: Budget vs. Actual, Execution, Variance Analysis, Revenue Performance, and Programme/Functional/Fund/Geographic performance.
- One‑click **Excel/PDF export** on reports and ledgers.

**I. Document Control**
- Attachment management on source documents (invoices, vouchers, contracts, IPCs), with controlled storage and retrieval — supported by **S3‑compatible object storage** (on‑prem MinIO or cloud bucket).

**J. Platform Controls (cross‑cutting)**
- **Role‑Based Access Control (RBAC)** + **Segregation of Duties (SoD)** (e.g., the staff who create invoices cannot release funds).
- **Approval workflows**, full **audit trail**, and multi‑department isolation.

### 3.2 Out of Scope (this phase)
- **Procurement / Purchase Orders (PO)** — vendors and direct invoices are supported, but the PO/requisition/GRN procurement chain is excluded.
- **Human Resources / Payroll (HR)**.

> These can be activated in a later phase; the platform already contains the modules, so enabling them is a configuration/rollout exercise rather than new development.

---

## 4. Technical Architecture (Summary)

| Layer | Technology | Notes |
|---|---|---|
| Frontend | React + Vite (TypeScript) | SPA; route‑level code‑splitting for fast page loads |
| Application | Django + Django REST Framework (Python) | Business logic, IPSAS engine, warrant/budget controls |
| Background jobs | Celery + Redis | Warrant expiry, depreciation runs, scheduled postings, notifications |
| Database | **PostgreSQL** (schema‑per‑tenant / department isolation) | The performance‑critical component |
| Cache/queue | Redis | Sessions, caching, task broker |
| Object storage | S3‑compatible (MinIO on‑prem / cloud bucket) | Document control attachments |
| Web/Proxy | Nginx | TLS termination, static serving, reverse proxy |

This is a standard, well‑understood stack that runs equally well **on‑premise** or in a **VPS/cloud**, which is what makes the hybrid options below practical.

---

## 5. Deployment Options — Pros & Cons

### 5.1 Option A — Online (VPS / Cloud)

**Best when:** OAG lacks a data‑center‑grade server room, reliable power, or in‑house infrastructure staff; or wants fastest time‑to‑deploy and built‑in resilience.

| Pros | Cons |
|---|---|
| No large upfront hardware capex (OpEx model) | Recurring monthly/annual cost indefinitely |
| Professional data‑center power, cooling, network, physical security | **Dependent on internet** — an OAG link outage blocks all users (mitigate with dual ISP) |
| Built‑in snapshots, backups, and easy scaling (add vCPU/RAM on demand) | **Data‑sovereignty/control** concerns if hosted offshore (mitigate by hosting **in Nigeria**) |
| Fast provisioning; deploy in days, not weeks | Less direct physical control of the hardware |
| Easier secure remote access for distributed users | Performance depends on provider not over‑subscribing the VPS |
| DDoS protection, managed firewalling available | Long‑term TCO can exceed on‑prem over 4–5 years |

### 5.2 Option B — On‑Premise (Local Server at OAG)

**Best when:** Data sovereignty is paramount (it is, for state finance data), OAG has/will build a secure server room with redundant power, and most users are on the OAG LAN/WAN.

| Pros | Cons |
|---|---|
| **Full data sovereignty & control** — data never leaves OAG (strong NDPA 2023 alignment) | **Upfront capital cost** for server, UPS, generator, network gear |
| **LAN‑speed performance** — no internet round‑trip for in‑office users | **Power risk** in Nigeria — mandatory UPS + generator + change‑over |
| Works during internet outages (LAN keeps running) | **Single‑site disaster risk** (fire/theft/flood) unless backed up offsite |
| One‑time capex; predictable long‑term cost | Requires in‑house/contracted IT for patching, monitoring, backups |
| No dependence on a third‑party provider’s SLA | Remote access needs a VPN you operate; harder for off‑site users |

### 5.3 Hybrid Options

**Option C — Deploy Online (primary) + Run On‑Premise (local node).**
Primary in a Nigerian cloud, with an **on‑premise read replica/cache** (and/or local app node) so the office keeps working at LAN speed and survives short internet outages.
- *Pros:* cloud resilience + local speed; remote access easy.
- *Cons:* most complex to operate; needs reliable replication and conflict handling; two environments to maintain.

**Option D — Deploy On‑Premise (primary) + Back Up Online (DR).**  ⭐ *recommended*
Primary runs on a hardened OAG server (sovereignty + LAN speed + offline resilience); **automated, encrypted backups and a warm standby replicate continuously to a Nigerian Tier‑III cloud** for disaster recovery and optional secure remote access.
- *Pros:* best balance — sovereignty, performance, **and** offsite DR; clear primary; simpler than active‑active.
- *Cons:* needs the OAG server room + a modest cloud DR subscription; failover is warm (minutes), not instant.

---

## 6. Recommended Infrastructure Specifications

> Sized for an OAG deployment of roughly **50–200 named users** across the four functions, with headroom. Scale RAM/vCPU up for higher concurrency or heavy month‑end/year‑end reporting peaks.

### 6.1 On‑Premise Server (for speed & reliability)

**Form factor:** Enterprise rack server — e.g. **Dell PowerEdge R760/R660**, **HPE ProLiant DL380 Gen11**, or **Lenovo ThinkSystem SR650 V3**.

| Component | Recommended | Why it matters |
|---|---|---|
| **CPU** | 1× (or 2× for HA headroom) **Intel Xeon Gold** (e.g. Gold 5418Y, 24‑core) or **AMD EPYC 9004**; favour **high clock speed** | Django request handling and PostgreSQL benefit from strong single‑thread performance |
| **RAM** | **128 GB ECC DDR5** (minimum 64 GB) | PostgreSQL caches working set in RAM → biggest single speed lever |
| **Storage (DB)** | **Enterprise/datacenter NVMe SSD in RAID 10** (e.g. 2–4 × 1.92 TB, Micron 7450 / Samsung PM9A3) | **NVMe is critical** for transaction throughput and report queries; RAID 10 = speed + redundancy |
| **Storage (OS/app)** | 2 × 960 GB NVMe **RAID 1** | Isolates OS/app I/O from the DB |
| **RAID** | Hardware RAID controller with cache + battery/flash backup | Write‑back cache safety |
| **Network** | Dual **10 GbE** NIC (bonded) | LAN throughput for concurrent users |
| **Power** | **Redundant hot‑swap PSUs** | No single power‑supply failure |
| **Remote mgmt** | iDRAC (Dell) / iLO (HPE) | Out‑of‑band administration |

**Supporting room infrastructure (mandatory in Nigeria):**
- **Online (double‑conversion) UPS** sized for 30–60 min (e.g. APC Smart‑UPS SRT 3–6 kVA) **+ standby generator with automatic change‑over (ATS)**.
- **Local backup NAS** (e.g. Synology/QNAP, RAID, ≥8 TB usable) for nightly backups, separate from the server.
- **Firewall/UTM** (FortiGate / Sophos / pfSense), managed switch, **VLAN segmentation**, and **air‑conditioned, access‑controlled** server room.

### 6.2 VPS / Cloud Specification

| Tier | Spec | Notes |
|---|---|---|
| App server | **8 vCPU / 32 GB RAM / 100 GB NVMe** (scale to 16/64) | Gunicorn/Uvicorn + Nginx |
| Database | **8 vCPU / 32 GB RAM / 500 GB NVMe** (dedicated or managed PostgreSQL) | NVMe‑backed; daily snapshots + PITR |
| Cache/jobs | 2 vCPU / 4 GB (Redis + Celery worker) | Background processing |
| Object storage | S3‑compatible bucket (start ~250–500 GB, grows) | Document Control attachments |
| Network | ≥99.9% SLA, dual‑homed; **dual ISP at OAG** for client side | Avoid single connectivity point |

**Insist on:** **dedicated/reserved vCPU (not over‑subscribed shared)**, **NVMe** storage, automated snapshots + off‑node backups, and a documented **SLA (≥99.9%)**.

### 6.3 Recommended VPS Cloud Type

For **state government financial data**, prioritise **data sovereignty (NDPA 2023)** and **low latency to Nigeria**:

1. **Nigerian / sovereign cloud (preferred):**
   - **Galaxy Backbone** (the Federal Government’s own cloud/ICT infrastructure provider — strongest sovereignty fit for government workloads).
   - **Rack Centre (Lagos, Tier III, carrier‑neutral)**, **Open Access Data Centres (OADC)**, **MainOne/Equinix LG1**, **Layer3 Cloud**, **Suburban** — Tier III Nigerian data centres offering VPS/private cloud.
2. **Africa‑region hyperscaler (alternative):** AWS **af‑south‑1 (Cape Town)** or Azure **South Africa North (Johannesburg)** — lower latency than EU/US, but **offshore**, so confirm it satisfies OAG/State data‑residency policy before use.

> **Recommendation:** a **VPS / private (single‑tenant) cloud in a Tier‑III Nigerian data centre**, ideally **Galaxy Backbone or Rack Centre**, with reserved NVMe compute and a ≥99.9 % SLA. This keeps sovereign data in‑country while giving data‑centre‑grade power, cooling, and network.

---

## 7. Best‑Fit Deployment Scenarios (Recommendation)

### 🥇 Scenario 1 (Recommended) — On‑Premise Primary + Online (Nigerian) DR Backup  *(Option D)*
- **Primary:** hardened OAG on‑premise server (§6.1) — sovereignty, LAN speed, works offline.
- **DR:** continuous **encrypted backup + warm standby** to a Nigerian Tier‑III cloud (§6.3); restore/failover in minutes; doubles as a secure remote‑access entry point over VPN.
- **Why best:** maximises sovereignty and in‑office performance **and** removes the single‑site disaster risk — the classic government best practice.
- **Prerequisite:** OAG server room with redundant power (UPS + generator) and basic IT support.

### 🥈 Scenario 2 (Fallback) — Nigerian Sovereign‑Cloud Primary + On‑Premise Local Backup/Cache  *(Option C, simplified)*
- **Primary:** VPS/private cloud in a Nigerian Tier‑III DC; **local on‑prem backup** (NAS) + optional read cache for offline resilience.
- **Why:** best when OAG’s server‑room/power readiness is not yet in place; data stays in Nigeria; fastest to stand up.
- **Watch‑out:** require **dual ISP** at OAG so a single link failure doesn’t stop work.

### 🥉 Scenario 3 (Advanced/Future) — Active‑Active On‑Prem + Cloud (HA)
- Both sites live with load balancing/replication for near‑zero downtime. Highest resilience, highest operational complexity and cost — consider only once volumes/criticality justify it.

| Criterion | Sc.1 On‑prem+Cloud DR | Sc.2 Cloud‑primary+local backup |
|---|---|---|
| Data sovereignty | ★★★★★ | ★★★★☆ (in‑country) |
| In‑office speed | ★★★★★ (LAN) | ★★★★☆ (depends on link) |
| Resilience to internet outage | ★★★★★ | ★★☆☆☆ (needs dual ISP) |
| Disaster recovery | ★★★★★ | ★★★★☆ |
| Upfront cost | Higher (hardware) | Lower |
| Ongoing cost | Lower | Higher (recurring) |
| Setup time | Longer (room + hardware) | Shortest |
| Best if… | OAG has a proper server room + power | Facility/power not yet ready |

---

## 8. Security, Compliance & Controls
- **NDPA 2023** alignment via in‑country hosting, encryption **in transit (TLS)** and **at rest**, and least‑privilege access.
- **RBAC + Segregation of Duties** enforced in the application (create vs. approve vs. pay).
- **Full audit trail** of every posting, approval, and master‑data change.
- **IPSAS** accrual reporting + **GIFMIS‑aligned** budget/warrant control out of the box.
- Hardened deployment: firewall/UTM, VLAN segmentation, VPN‑only remote access, regular patching, and tested restores.

## 9. Migration Approach (Odoo → QUOT PSA)
1. **Discovery & mapping** — map Odoo chart of accounts to the **NCoA** segments; inventory open items.
2. **Extract** — Odoo COA, balances, vendors/customers, open invoices/payments, contracts, and GL history.
3. **Transform & validate** — segment mapping, opening‑balance trial‑balance reconciliation (debits = credits).
4. **Load** — into QUOT PSA per department/schema; verify control totals.
5. **Parallel run** — run final reporting in both systems for 1–2 periods; reconcile.
6. **Cutover** — freeze Odoo, go live on QUOT PSA, retain Odoo read‑only for history.

## 10. Indicative Implementation Phases
| Phase | Focus | Indicative duration |
|---|---|---|
| 0 | Mobilisation, infrastructure provisioning, server‑room/cloud readiness | 2–4 weeks |
| 1 | Core GL/NCoA, Budget & Appropriation, Warrant/AIE config | 3–5 weeks |
| 2 | Treasury (TSA, PV, payments), AP/AR | 3–5 weeks |
| 3 | Contract Management, Fixed Assets, Document Control | 3–4 weeks |
| 4 | IPSAS & budget‑performance reporting, data migration, parallel run | 3–5 weeks |
| 5 | Training (4 functions), UAT, go‑live, hypercare | 3–4 weeks |

*(Phases overlap; total typically 4–6 months depending on data quality and readiness.)*

## 11. Backup & Disaster Recovery
- **3‑2‑1 rule:** 3 copies, 2 media, 1 offsite — satisfied natively by Scenario 1/2.
- Automated **nightly full + frequent incremental** PostgreSQL backups with **Point‑in‑Time Recovery (PITR)**; document‑store (object) backups; **encrypted** at rest and in transit.
- **Quarterly restore drills** to prove recoverability (RPO target ≤ 24 h, ideally ≤ 1 h with PITR; RTO target a few hours).

## 12. Key Risks & Mitigations
| Risk | Mitigation |
|---|---|
| Power instability (on‑prem) | Online UPS + generator + ATS; cloud DR as fallback |
| Internet outage (cloud‑primary) | Dual ISP; on‑prem cache/backup; on‑prem primary (Scenario 1) |
| Data sovereignty | In‑country (Nigerian Tier‑III) hosting only |
| Data‑migration errors | Trial‑balance reconciliation + parallel run before cutover |
| Skills/operations | Admin training + support/maintenance contract |
| Single‑site loss | Offsite encrypted DR (Scenario 1/2) |

## 13. Recommended Next Steps
1. Confirm **user counts** per function and peak concurrency (to finalise sizing).
2. Assess **OAG server‑room & power readiness** → decide Scenario 1 vs. Scenario 2.
3. Confirm **hosting choice** (Galaxy Backbone / Rack Centre / other) and data‑residency policy.
4. Approve scope (this phase: **no PO, no HR**) and migration plan.
5. Finalise commercials (licence + implementation + hosting/hardware + support) and project schedule.

---

*Prepared as a working draft for OAG Delta State. Figures (server sizing, durations) are indicative and will be confirmed during the discovery phase against actual user counts, data volumes, and facility readiness.*
