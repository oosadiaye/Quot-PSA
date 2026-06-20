# Indicative Cost & Bill of Materials (BOM) — OAG Delta · QUOT PSA

**Date:** 07/06/2026 · **Currency:** NGN (USD shown for import‑priced hardware @ ~₦1,550/US$)

> ⚠️ **Indicative only.** Hardware/cloud figures are planning estimates and **require formal vendor quotes**. Lines marked **[Vendor commercial]** (software licence, implementation, migration, training, support) are set in the vendor’s commercial proposal and are **not** estimated here. Final sizing depends on confirmed **user counts, data volumes, and facility readiness**.

---

## A. One‑Time — Hardware & Facility (Scenario ① On‑Premise Primary)

| # | Item | Spec (summary) | Indicative NGN | USD ref |
|---|---|---|---|---|
| 1 | Application/DB server | Dell R760 / HPE DL380 Gen11 · Xeon Gold (high‑clock) · 128 GB ECC DDR5 · NVMe RAID‑10 (DB) + RAID‑1 (OS) · redundant PSU · dual 10 GbE | ₦9,000,000 – 18,000,000 | $6k–12k |
| 2 | Online UPS (double‑conversion) | 6 kVA + extended batteries, 30–60 min runtime | ₦1,500,000 – 3,500,000 | — |
| 3 | Standby generator + ATS *(if not already available)* | ~15–20 kVA, automatic change‑over | ₦3,500,000 – 9,000,000 | — |
| 4 | Backup NAS | RAID, ≥8–16 TB usable (local nightly backups) | ₦1,000,000 – 2,500,000 | — |
| 5 | Firewall / UTM | FortiGate/Sophos class + 1‑yr security licence | ₦1,500,000 – 4,000,000 | — |
| 6 | Network & server‑room provisioning | Managed switch, rack, cabling, cooling (AC), access control | ₦1,500,000 – 4,000,000 | — |
| | **Subtotal — Hardware & Facility** | | **₦18,000,000 – 41,000,000** | |

*If OAG already has generator/cooling/rack, deduct items 3 and part of 6.*

---

## B. Recurring — Infrastructure (per scenario, annual)

**Scenario ① — On‑prem primary + Nigerian cloud DR (warm standby + backups):**

| Item | Spec | Indicative NGN / yr |
|---|---|---|
| Cloud DR (Nigerian Tier‑III) | Warm standby (smaller than primary) + object storage + encrypted backups | ₦3,000,000 – 7,200,000 |
| **Subtotal ① (annual)** | | **₦3,000,000 – 7,200,000** |

**Scenario ② — Nigerian sovereign‑cloud primary + on‑prem local backup:**

| Item | Spec | Indicative NGN / yr |
|---|---|---|
| Cloud production | App (8–16 vCPU) + PostgreSQL (8 vCPU/32–64 GB/NVMe) + Redis + object storage + snapshots, ≥99.9% SLA | ₦7,200,000 – 18,000,000 |
| Dual ISP at OAG (resilience) | Two independent links | ₦1,800,000 – 4,800,000 |
| On‑prem local backup (one‑time) | NAS + small UPS *(one‑time, see A4)* | *(one‑time)* |
| **Subtotal ② (annual)** | | **₦9,000,000 – 22,800,000** |

---

## C. Software, Implementation & Services *(vendor commercial — insert figures)*

| Item | Basis | Amount |
|---|---|---|
| QUOT PSA platform licence | Per named user / per department / annual subscription | **[Vendor commercial]** |
| Implementation & configuration | 4 functions (Mgmt Acct, Treasury, Final Reporting, Document Control) | **[Vendor commercial]** |
| Data migration (Odoo → QUOT PSA) | COA→NCoA mapping, balances, open items, contracts, parallel run | **[Vendor commercial]** |
| Training | Role‑based, 4 functions + admin | **[Vendor commercial]** |
| Annual support & maintenance | Typically 18–22% of licence/yr (SLA‑backed) | **[Vendor commercial]** |
| Hypercare (post‑go‑live) | 4–8 weeks | **[Vendor commercial]** |

---

## D. Cost Shape Summary (planning view)

| | Scenario ① On‑prem + Cloud DR | Scenario ② Cloud‑primary + local backup |
|---|---|---|
| One‑time hardware/facility | **₦18M – 41M** (+ NAS) | **₦2M – 5M** (NAS + small UPS only) |
| Recurring infrastructure / yr | **₦3M – 7.2M** | **₦9M – 22.8M** |
| Software/implementation/support | **[Vendor commercial]** (same either way) | **[Vendor commercial]** (same either way) |
| 3‑yr infra TCO (excl. licence) | ≈ ₦27M – 63M | ≈ ₦29M – 73M |
| Best when… | OAG has server room + power | Facility/power not yet ready |

> Over 3–5 years, **Scenario ①** typically has the **lower total infrastructure cost** and **higher sovereignty/performance**, provided OAG can host a secure, well‑powered server room. **Scenario ②** trades higher recurring spend for **lowest upfront cost and fastest start**.

---

## E. Assumptions
- ~50–200 named users across the four functions; sizing tuned at discovery.
- Hardware import‑priced; FX at ~₦1,550/US$ (volatile — confirm at quote time).
- Existing generator/cooling/rack reduce Scenario ① one‑time cost.
- Licence/implementation/support are **vendor commercials**, identical across deployment scenarios.
- Prices exclude VAT/duties and any required network upgrades beyond those listed.
