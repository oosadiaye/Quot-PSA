# Automated Production Completion Pipeline

**Date:** 2026-04-08
**Status:** Approved
**Scope:** End-to-end automation of production order completion: GL posting, finished goods receipt, inventory updates, and conditional QA gate.

---

## 1. Problem Statement

Production completion is currently manual and fragmented:
- Users must click "Complete" on the production order, then separately trigger "Post to GL", then manually create a finished goods receipt.
- No enforcement of QA inspection before completion when the BOM requires it.
- Risk of partial state: order marked Done but GL never posted, or FG never received into inventory.

**Goal:** A single user action completes the production order and atomically performs all downstream operations (GL posting, FG inventory receipt, stock updates), with an optional QA gate driven by BOM configuration.

---

## 2. Architecture

### 2.1 Single Endpoint Orchestrator

One endpoint handles both preview and commit via a `?preview=true` query parameter.

- **Service layer:** `production/services/completion.py` — owns the atomic orchestrator. Fat service, thin view.
- **View:** `ProductionOrderViewSet.complete_production` — delegates entirely to the service.
- **Removed after implementation:** The standalone "Post to GL" action and manual FG receipt tab.

### 2.2 Endpoint Contract

```
POST /api/production/production-orders/{id}/complete_production/
```

**Request body:**
```json
{
  "quantity_produced": 100,
  "warehouse_id": 5,
  "scrap_quantity": 2,
  "scrap_reason": "Defective mold batch"
}
```

**Query parameter:** `?preview=true` returns a dry-run summary without committing.

**Preview response:**
```json
{
  "order_number": "PO-0042",
  "product": "Widget A",
  "quantity_produced": 100,
  "scrap_quantity": 2,
  "warehouse": "Main Warehouse",
  "unit_cost": 45.50,
  "total_cost": 4550.00,
  "scrap_cost": 91.00,
  "journal_lines_preview": [
    {"account": "Finished Goods Inventory", "debit": 4550.00, "credit": 0},
    {"account": "WIP Inventory", "debit": 0, "credit": 4550.00},
    {"account": "Direct Labor", "debit": 800.00, "credit": 0},
    {"account": "Manufacturing Overhead", "debit": 350.00, "credit": 0},
    {"account": "WIP Inventory", "debit": 0, "credit": 1150.00},
    {"account": "Scrap Loss Expense", "debit": 91.00, "credit": 0},
    {"account": "WIP Inventory", "debit": 0, "credit": 91.00}
  ]
}
```

**Exact-match contract:** The confirm call uses the same inputs and produces the same calculations as preview. Preview locks the order row (`select_for_update`) to guarantee consistency.

**Confirm response:** Same structure plus `journal_id`, `material_receipt_id`, `stock_movement_ids`.

---

## 3. Flow: No QA Required

When `BOM.requires_quality_inspection = False`:

```
User clicks "Complete" on production order
  -> Modal opens: input step (quantity_produced, warehouse, scrap_quantity, scrap_reason)
  -> Client-side validation (quantity > 0, warehouse selected, scrap >= 0)
  -> User clicks "Preview"
  -> POST ?preview=true (shows journal lines, costs, FG receipt summary)
  -> User reviews and clicks "Confirm"
  -> POST (no preview param) -> atomic transaction:
       1. Lock order row (select_for_update)
       2. Idempotency check (status != 'Done') — INSIDE transaction, after lock
       3. Set order status = 'Done', actual_quantity, actual_end_date
       4. Create MaterialReceipt (type='production_output', warehouse_id, unit_cost from BOM)
       5. Create StockMovement + update ItemStock + update/create ItemBatch
       6. Link QualityInspection (if any) to this completion
       7. GL Entry 1: DR Finished Goods Inventory / CR WIP Inventory (FG cost)
       8. GL Entry 2: DR Direct Labor + Manufacturing Overhead / CR WIP Inventory (labor+overhead)
       9. GL Entry 3 (conditional, only if scrap > 0): DR Scrap Loss Expense / CR WIP Inventory
      10. All JournalHeaders tagged: source_module='production', source_document_id=order.pk, posted_by=request.user
  -> Toast: "Production order PO-0042 completed. Journal #JE-1234 posted."
  -> Invalidate query caches
```

### 3.1 Validation Rules

| Check | When | Error |
|-------|------|-------|
| All job cards status = 'Done' | Before preview and confirm | "All operations must be completed before finishing the production order." |
| Order status not 'Done' | After lock, inside transaction | "Production order is already completed." (idempotency) |
| Order status = 'In Progress' or 'QA Passed' | Before preview | "Production order must be In Progress or QA Passed to complete." |
| quantity_produced > 0 | Client + server | "Quantity produced must be greater than zero." |
| quantity_produced <= planned_quantity * 1.1 | Server | "Quantity produced exceeds planned quantity by more than 10%." |
| scrap_quantity >= 0 | Client + server | "Scrap quantity cannot be negative." |
| warehouse_id valid and active | Server | "Invalid or inactive warehouse." |

---

## 4. Flow: QA Required

When `BOM.requires_quality_inspection = True`:

### 4.1 QA Gate Behavior (Option A: Block at Completion)

The system blocks the "Complete" action until QA passes. QA is auto-created when the last job card is marked Done.

### 4.2 QA Trigger

When `complete_operation` is called on the last job card of a production order:

```python
# Inside complete_operation, after setting job_card.status = 'Done':
all_done = not order.job_cards.exclude(pk=job_card.pk).exclude(status='Done').exists()
if all_done and order.bom and order.bom.requires_quality_inspection:
    # Check for existing non-Failed inspection
    existing = QualityInspection.objects.filter(
        production_order=order
    ).exclude(status='Failed').first()
    if not existing:
        QualityInspection.objects.create(
            production_order=order,
            inspection_type='Final',
            status='Pending',
            requested_by=request.user,
        )
        order.status = 'Pending QA'
        order.save()
```

### 4.3 QA State Machine

```
Production Order States:
  In Progress -> Pending QA (auto, when last job card done + QA required)
  Pending QA -> QA Passed (auto, when inspection passes)
  Pending QA -> On Hold (auto, when inspection fails)
  On Hold -> Pending QA (manual, when user creates re-inspection)
  QA Passed -> Done (user triggers completion)
```

### 4.4 QA Failure and Re-Inspection

When a `QualityInspection` is marked `Failed`:
- Production order status changes to `On Hold`
- User can create a new inspection (re-inspection) which sets order back to `Pending QA`
- The new inspection excludes the failed one from duplicate checks (filter `.exclude(status='Failed')`)
- Only the passing inspection is linked to the completion record

### 4.5 QA Pass -> Completion

When inspection passes:
- Order status auto-updates to `QA Passed`
- The "Complete" button becomes enabled in the UI
- User proceeds with the same completion modal as the no-QA flow
- The passing `QualityInspection` is linked to the completion transaction

---

## 5. Service Layer

### 5.1 File: `production/services/completion.py`

```python
class ProductionCompletionService:
    """Orchestrates the atomic production completion pipeline."""

    @staticmethod
    def preview(order_id, quantity_produced, warehouse_id, scrap_quantity=0, scrap_reason=''):
        """Lock the order and compute a dry-run preview."""
        order = ProductionOrder.objects.select_for_update().get(pk=order_id)
        # Validate state, compute costs, build journal preview
        return preview_data

    @staticmethod
    def complete(order_id, quantity_produced, warehouse_id, scrap_quantity=0,
                 scrap_reason='', user=None):
        """Execute the full atomic completion pipeline."""
        with transaction.atomic():
            order = ProductionOrder.objects.select_for_update().get(pk=order_id)
            # Idempotency check
            if order.status == 'Done':
                raise ValidationError("Already completed.")
            # Steps 3-10 from Section 3
            ...
            return result
```

### 5.2 Key Design Decisions

- **Preview also locks:** `select_for_update()` in preview ensures the cost calculation matches what confirm will produce. The lock is released when the preview transaction ends (autocommit).
- **Idempotency inside transaction:** The `status != 'Done'` check happens after `select_for_update()`, not before, to prevent race conditions.
- **MaterialReceipt includes warehouse:** The receipt record carries the user-selected `warehouse_id` and the BOM-calculated `unit_cost`.
- **Scrap credits WIP, not Inventory:** `DR Scrap Loss Expense / CR WIP Inventory` — scrap is a cost of production, not a reduction of finished goods.
- **QA inspection linked to completion:** The passing inspection FK is set on the completion record for traceability.

### 5.3 Cost Calculation

```
unit_cost = sum(BOM material costs) / planned_quantity
fg_total_cost = unit_cost * quantity_produced
scrap_cost = unit_cost * scrap_quantity
labor_cost = sum(job_card.actual_hours * labor_rate)   # from JobCard records
overhead_cost = labor_cost * overhead_rate              # from ProductionConfig or BOM
```

---

## 6. GL Journal Entries

All entries posted atomically within the completion transaction.

### 6.1 Finished Goods Receipt

| Account | Debit | Credit |
|---------|-------|--------|
| Finished Goods Inventory | fg_total_cost | |
| WIP Inventory | | fg_total_cost |

### 6.2 Labor and Overhead Absorption

| Account | Debit | Credit |
|---------|-------|--------|
| Direct Labor | labor_cost | |
| Manufacturing Overhead | overhead_cost | |
| WIP Inventory | | labor_cost + overhead_cost |

### 6.3 Scrap Write-Off (conditional: only when scrap_quantity > 0)

| Account | Debit | Credit |
|---------|-------|--------|
| Scrap Loss Expense | scrap_cost | |
| WIP Inventory | | scrap_cost |

### 6.4 Source Tagging

All `JournalHeader` records include:
- `source_module = 'production'`
- `source_document_id = order.pk`
- `posted_by = request.user`
- `posted_at = timezone.now()`

---

## 7. Frontend

### 7.1 CompleteProductionModal

A two-step modal component:

**Step 1 — Input:**
- Quantity produced (number input, required, > 0)
- Warehouse selector (dropdown, required, fetched from inventory API)
- Scrap quantity (number input, optional, >= 0)
- Scrap reason (text input, required if scrap > 0)
- Client-side validation before enabling "Preview" button

**Step 2 — Preview:**
- Read-only summary: order details, costs, journal lines table
- Scrap journal line shown conditionally (only when scrap > 0)
- "Confirm" button to execute
- "Back" button to return to input step

### 7.2 Loading States

Two separate loading states:
- `isLoadingPreview` — shown during preview fetch, "Preview" button disabled
- `isCompleting` — shown during confirm, "Confirm" button disabled with spinner

### 7.3 Button State Logic

The "Complete" button on the production order detail page:

| Order Status | BOM QA Required | Button State |
|-------------|----------------|--------------|
| In Progress | No | Enabled |
| In Progress | Yes | Disabled, tooltip: "Waiting for all operations to complete" |
| Pending QA | Yes | Disabled, tooltip: "Quality inspection in progress" |
| On Hold | Yes | Disabled, tooltip: "QA failed — create re-inspection to proceed" |
| QA Passed | Yes | Enabled |
| Done | Any | Hidden |

### 7.4 Success Feedback

Toast notification includes journal reference:
> "Production order PO-0042 completed. Journal #JE-1234 posted. 100 units received into Main Warehouse."

### 7.5 Cache Invalidation

On successful completion, invalidate these TanStack Query keys:
1. `['production-orders']` — list refreshes status
2. `['production-order', orderId]` — detail refreshes status + costs
3. `['inventory-items']` — stock levels updated
4. `['journal-entries']` — new GL entries visible

### 7.6 Removals

After implementation:
- Remove standalone "Post to GL" button from production order detail
- Remove manual FG receipt tab/workflow

---

## 8. complete_operation Enhancement

The `JobCardViewSet.complete_operation` action gains QA auto-creation logic:

```python
@action(detail=True, methods=['post'])
def complete_operation(self, request, pk=None):
    job_card = self.get_object()
    # ... existing completion logic (set status='Done', actual times) ...

    order = job_card.production_order
    all_done = not order.job_cards.exclude(pk=job_card.pk).exclude(status='Done').exists()

    if all_done and order.bom and getattr(order.bom, 'requires_quality_inspection', False):
        existing = QualityInspection.objects.filter(
            production_order=order
        ).exclude(status='Failed').first()

        if not existing:
            QualityInspection.objects.create(
                production_order=order,
                inspection_type='Final',
                status='Pending',
            )
            order.status = 'Pending QA'
            order.save()
    elif all_done and not getattr(order.bom, 'requires_quality_inspection', False):
        # No QA required — order stays In Progress, user completes manually
        pass

    return Response(...)
```

---

## 9. Model Changes

### 9.1 ProductionOrder

Add status choices if not already present:
- `Pending QA`
- `QA Passed`
- `On Hold`

### 9.2 BOM

Confirm `requires_quality_inspection = BooleanField(default=False)` exists. Add if missing.

### 9.3 MaterialReceipt

Ensure fields exist:
- `warehouse` (FK to Warehouse)
- `unit_cost` (DecimalField)
- `production_order` (FK to ProductionOrder)
- `receipt_type` (CharField with 'production_output' option)

---

## 10. Error Handling

| Scenario | Behavior |
|----------|----------|
| Transaction fails mid-way | Full rollback via `transaction.atomic()` — no partial state |
| GL account not configured | Raise `TransactionPostingError` with specific missing account name |
| Warehouse inactive/deleted | 400 error before transaction starts |
| Concurrent completion race | Second request hits idempotency check after lock, returns 409 Conflict |
| QA inspection not passed | 400: "Quality inspection must pass before completion" |
| Job cards not all done | 400: "All operations must be completed first" |

---

## 11. Files to Create/Modify

| File | Action | Purpose |
|------|--------|---------|
| `production/services/completion.py` | **Create** | Atomic orchestrator service |
| `production/views.py` | Modify | Rewrite `complete_production` to delegate to service; update `complete_operation` with QA auto-creation |
| `production/models.py` | Modify | Add status choices (Pending QA, QA Passed, On Hold); confirm BOM field |
| `accounting/services/production_posting.py` | Modify | Refactor GL posting to be callable from completion service |
| `inventory/models.py` | Modify | Ensure MaterialReceipt has warehouse, unit_cost, production_order fields |
| `frontend/src/features/production/components/CompleteProductionModal.tsx` | **Create** | Two-step completion modal |
| `frontend/src/features/production/hooks/useProduction.ts` | Modify | Add `useCompleteProduction` mutation + preview query |
| `frontend/src/features/production/pages/ProductionOrderDetail.tsx` | Modify | Wire modal, button state logic, remove manual GL/FG actions |

---

## 12. Out of Scope

- Partial completion (completing a fraction of the order) — future enhancement
- Batch/lot number auto-generation rules — uses existing ItemBatch logic
- Cost variance analysis reports — separate feature
- Multi-warehouse split receipt — single warehouse per completion
- Undo/reverse completion — requires separate reversal journal flow
