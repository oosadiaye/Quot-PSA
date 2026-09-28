# Contract Activity Log (full audit) + fix "View all" 404

**Date:** 2026-09-24
**Branch:** `feat/milestone-as-invoice`
**Status:** Approved — implementing

## Context

The contract detail page's **Recent Activity** panel is hardcoded (placeholder
items from `contract.status`/dates, no actor), and its **"View All Audit Logs"**
button navigates to `/contracts/:id/audit` — a route that isn't registered → 404.

User chose **full generic audit**: show every action carried out on the contract
*and its sub-objects*, with who (actor) + when. Source = `core.AuditLog`
(auto-populated for every `AuditBaseModel` via a `post_save` signal; actor from
the request). `AuditLog` links generically (`content_type` + `object_id`), so a
contract's activity is spread across several models' rows.

## Scope

### Backend — contract-scoped aggregation endpoint
`GET /contracts/contracts/{id}/activity/` (`@action(detail=True)` on
`ContractViewSet`). Compose one OR-query over the contract + its sub-objects:
Contract, MilestoneSchedule, InterimPaymentCertificate, ContractVariation,
MobilizationPayment, RetentionRelease, ContractYearPlan (whichever relations
exist). For each model with ids:
`q |= Q(content_type=ContentType.get_for_model(Model), object_id__in=ids)`.
`AuditLog.objects.filter(q).select_related('user').order_by('-timestamp')`,
paginated, serialized with the existing `AuditLogSerializer`
(username, action, timestamp, model_name, object_repr, old/new_status,
description, reference). The `(content_type, object_id, -timestamp)` index keeps
each clause fast.

### Frontend
- **Recent Activity panel** (`ContractDetail.tsx`): replace placeholders with a
  `useContractActivity(id)` hook on the endpoint; render top ~5 as
  `<action> <object_repr>` · by `<username>` · `<timestamp>`. Extend
  `ActivityItemProps` with an actor line.
- **Fix the 404**: register `/contracts/:id/audit` in `App.tsx` (contracts
  ModuleGuard) + a small `ContractAuditPage` listing the full activity feed
  (styled like `AuditTrailViewer`). Keeps the button's existing target.

### Testing
- Backend: `activity` returns AuditLog entries for the contract + one of its
  milestones (create/update logged) with `username`, newest-first; excludes an
  unrelated contract's entries.
- Frontend: tsc + Playwright (panel shows real entries; "View all" opens the
  page, no 404).

## Out of scope
- Adding a `contract` FK to AuditLog (invasive, backfill).
- Payment audit entries (Payments link to the contract only indirectly via
  invoice reference) — the contract's own objects are the scope.
