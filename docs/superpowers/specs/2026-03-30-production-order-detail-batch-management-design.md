# Production Order Detail & Batch Management — Design Spec

**Date:** 2026-03-30
**Status:** Draft
**Scope:** Production Order Detail page, material consumption, finished goods receipt, job card management, batch management, quality inspection toggle

---

## 1. Problem Statement

The production module backend is fully implemented (material issues, receipts, job cards, routings, GL posting, quality gates) but the frontend only exposes ~30% of this capability. Users cannot:

- View production order details or drill into individual orders
- Consume raw materials from inventory during production
- Receive finished goods back into inventory
- Track manufacturing operations via job cards
- Manage batches (split, transfer, view traceability)
- Control whether a product requires quality inspection

This spec covers the frontend pages, backend additions, and batch management enhancements needed to close these gaps.

---

## 2. Architecture Overview

### Approach: Modular Tab Components

A lightweight shell page (`ProductionOrderDetail.tsx`) hosts tab navigation. Each tab is a standalone component receiving `orderId` and `orderData` as props. This matches existing patterns in the accounting module.

### New Files

```
frontend/src/features/production/pages/
  ProductionOrderDetail.tsx        # Shell: header, action bar, tab router
  tabs/
    MaterialConsumptionTab.tsx      # BOM requirements, backflush, manual issue, history
    FinishedGoodsTab.tsx            # Receive output, scrap, receipt history
    JobCardsTab.tsx                 # Operation cards with start/complete
    BatchesTab.tsx                  # Batches created/consumed by this order
    QualityTab.tsx                  # Quality inspection integration (conditional)
```

### Modified Files

```
frontend/src/features/production/pages/ProductionOrderList.tsx
  - Row click navigates to /production/orders/:id

frontend/src/features/production/hooks/useProduction.ts
  - Add useBackflushMaterials hook
  - Add useBatchSplit, useBatchTransfer hooks

frontend/src/features/inventory/pages/BatchList.tsx
  - Add create form, split modal, transfer modal, expiry management

frontend/src/features/inventory/hooks/useInventory.ts
  - Add useCreateBatch, useSplitBatch, useTransferBatch hooks

frontend/src/App.tsx
  - Add route: /production/orders/:id -> ProductionOrderDetail

frontend/src/components/Sidebar.tsx
  - Add "Batch Management" under Inventory sidebar section

production/models.py
  - Add requires_quality_inspection field to BillOfMaterials

production/views.py
  - Add backflush_materials action to ProductionOrderViewSet
  - Update complete_production to respect quality toggle

production/serializers.py
  - Update BillOfMaterialsSerializer with new field

inventory/views.py
  - Add split_batch and transfer_batch actions to ItemBatchViewSet

inventory/serializers.py
  - Add BatchSplitSerializer, BatchTransferSerializer
```

---

## 3. Production Order Detail Page

### 3.1 Route

- **Path:** `/production/orders/:id`
- **Entry point:** Clicking an order row in ProductionOrderList navigates here
- **Back button:** Returns to `/production/orders`

### 3.2 Header Section

Displays in a card:
- **Order number** + **status badge** (color-coded: Draft=gray, Scheduled=navy, In Progress=blue, Done=green, On Hold=amber, Cancelled=red)
- **Meta grid** (5 columns): Product (BOM name), Work Center, Start Date, End Date, Quantity (produced/planned with unit)
- **Progress bar:** `quantity_produced / quantity_planned` as percentage
- **Quality badge:** Shows "QI Required" or "QI Not Required" based on `bom.requires_quality_inspection`

### 3.3 Action Bar

Context-aware buttons based on `order.status`:

| Status       | Actions Shown                          |
|-------------|----------------------------------------|
| Draft       | Schedule, Edit, Cancel                  |
| Scheduled   | Start Production, Edit, Cancel          |
| In Progress | Complete Production, Cancel             |
| On Hold     | Resume (→ In Progress), Cancel          |
| Done        | Post to GL                             |
| Cancelled   | None                                    |

**Complete Production** opens an inline prompt for `quantity_produced`.

**Cancel** opens a confirmation dialog.

### 3.4 Tabs

Five tabs, each a standalone component:

1. **Materials** — `MaterialConsumptionTab`
2. **Finished Goods** — `FinishedGoodsTab`
3. **Job Cards** — `JobCardsTab`
4. **Batches** — `BatchesTab`
5. **Quality** — `QualityTab`

Each tab shows a count badge (e.g., Materials shows BOM line count, Job Cards shows card count).

---

## 4. Materials Tab — `MaterialConsumptionTab`

### 4.1 Backflush Bar

A prominent action bar at the top:
- **Warehouse dropdown:** Select source warehouse for backflush (defaults to first warehouse with stock)
- **Button:** "Issue All Materials (Backflush)"
- Only shown when order status is "In Progress" and there are un-issued materials
- Calls new `backflush_materials` endpoint with selected warehouse

### 4.2 Requirements vs Issued Table

Fetches from existing `material_requirements` endpoint, cross-referenced with `material_issues`:

| Column       | Source                                    |
|-------------|-------------------------------------------|
| Component    | BOM line → component.item_name            |
| Code         | BOM line → component.item_code            |
| Required Qty | `line.total_quantity * order.quantity_planned` |
| Issued Qty   | Sum of MaterialIssue.quantity_issued for this line |
| Remaining    | Required - Issued                          |
| Status       | Badge: Fully Issued / Partial / Not Issued |
| Action       | "Issue" button (if remaining > 0)          |

### 4.3 Manual Issue Form

Inline form below the requirements table:
- **Component** (dropdown): Only shows components with remaining quantity > 0
- **Quantity** (number input): Defaults to remaining quantity for selected component
- **Warehouse** (dropdown): Fetched from inventory warehouses
- **Source Batch** (dropdown): "Auto (FIFO)" default + available batches for selected component. Optional — if omitted, no batch tracking on the issue.
- **Submit button:** Calls existing `POST /production/material-issues/` then `POST /production/material-issues/{id}/post_to_gl/`

### 4.4 Issue History Table

Lists all `MaterialIssue` records for this order:

| Column     | Source                             |
|-----------|-------------------------------------|
| Date       | issue_date                          |
| Component  | bom_line → component.item_name      |
| Qty Issued | quantity_issued                     |
| Warehouse  | Derived from StockMovement          |
| Batch      | StockMovement.batch (if tracked)    |
| GL Posted  | Badge: Posted / Pending             |

---

## 5. Finished Goods Tab — `FinishedGoodsTab`

### 5.1 Summary Cards

Four metric cards:
- **Planned** — `order.quantity_planned`
- **Received** — Sum of `MaterialReceipt.quantity_received` (non-scrap)
- **Remaining** — Planned - Received
- **Scrap** — Sum of `MaterialReceipt.scrap_quantity`

### 5.2 Receive Form

Inline form:
- **Quantity Received** (number): Required
- **Warehouse** (dropdown): Target warehouse for finished goods
- **Receipt Date** (date): Defaults to today
- **Scrap Qty** (number): Defaults to 0
- **Notes** (text): Optional
- **Submit:** Calls `POST /production/material-receipts/` then `POST /production/material-receipts/{id}/post_to_gl/`

Only shown when order status is "In Progress" or "Done" (before GL posting).

### 5.3 Receipt History Table

| Column        | Source                                |
|--------------|----------------------------------------|
| Date          | receipt_date                           |
| Qty Received  | quantity_received                      |
| Scrap         | scrap_quantity                         |
| Warehouse     | Derived from StockMovement             |
| Batch Created | ItemBatch.batch_number (from movement) |
| GL Posted     | Badge: Posted / Pending                |

---

## 6. Job Cards Tab — `JobCardsTab`

### 6.1 Layout

Card grid (`repeat(auto-fill, minmax(300px, 1fr))`) showing each job card as a visual card with left border color indicating status:
- Gray = Pending
- Blue = In Progress
- Green = Done

### 6.2 Card Content

- **Sequence number** (circle badge)
- **Status badge**
- **Operation name** (bold)
- **Meta grid:** Work Center, Operator, Planned Time, Actual Time, Labor Cost
- **Actions:**
  - Pending: "Start" button → calls `POST /production/job-cards/{id}/start_operation/`
  - In Progress: "Complete" button → opens inline inputs for `time_actual` and `labor_cost`, then calls `POST /production/job-cards/{id}/complete_operation/`
  - Done: No actions

### 6.3 Add Job Card

"+ Add Job Card" button opens an inline form:
- **Sequence** (number)
- **Operation Name** (text)
- **Work Center** (dropdown)
- **Operator** (dropdown, optional) — fetched from HRM employees
- **Planned Time** (hours)
- **Submit:** Calls `POST /production/job-cards/`

Only available when order status is Draft, Scheduled, or In Progress.

---

## 7. Batches Tab — `BatchesTab`

### 7.1 Batches Created by This Order

Table showing `ItemBatch` records created by material receipts for this order:

| Column        | Source                        |
|--------------|--------------------------------|
| Batch #       | batch_number                   |
| Item          | item.name                      |
| Warehouse     | warehouse.name                 |
| Original Qty  | quantity                       |
| Remaining     | remaining_quantity             |
| Unit Cost     | unit_cost                      |
| Received      | receipt_date                   |
| Expiry        | expiry_date (color-coded)      |
| Actions       | Split, Transfer buttons        |

### 7.2 Source Batches Consumed

Table showing batches referenced in material issues for this order:

| Column     | Source                          |
|-----------|----------------------------------|
| Batch #    | StockMovement.batch.batch_number |
| Component  | Component name                   |
| Qty Used   | StockMovement.quantity           |
| Warehouse  | StockMovement.warehouse.name     |
| Issue Date | StockMovement.created_at         |

### 7.3 Batch Actions (Split & Transfer)

**Split Batch** — Modal form:
- **Source Batch** (pre-selected)
- **Split Quantity** (number, must be < remaining_quantity)
- **New Batch Number** (auto-generated, editable)
- Backend: Creates new ItemBatch, decrements source remaining_quantity

**Transfer Batch** — Modal form:
- **Source Batch** (pre-selected)
- **Target Warehouse** (dropdown, excludes current warehouse)
- **Transfer Quantity** (number, must be <= remaining_quantity)
- Backend: Creates StockMovement (TRF), updates ItemBatch warehouse or creates new batch at target

---

## 8. Batch Management — Inventory Module Enhancement

### 8.1 Enhanced BatchList.tsx

Add to the existing inventory batch list page:

**Create Batch Form** (modal):
- Item (dropdown)
- Batch Number (text, auto-generated option)
- Warehouse (dropdown)
- Quantity (number)
- Unit Cost (number)
- Receipt Date (date, default today)
- Expiry Date (date, optional)
- Reference Number (text, optional)

**Split Batch** — Same modal as in production batches tab (reusable component)

**Transfer Batch** — Same modal as in production batches tab (reusable component)

**Expiry Indicators:**
- Green: > 30 days until expiry
- Amber: <= 30 days until expiry
- Red: Expired

### 8.2 Navigation

- **Inventory sidebar:** Rename existing "Batches / Lots" to "Batch Management"
- **Production sidebar:** No change (batches accessed contextually via Production Order Detail)

### 8.3 Backend Endpoints (New)

```
POST /inventory/batches/                           # Already exists (create)
POST /inventory/batches/{id}/split/                # New: split batch
POST /inventory/batches/{id}/transfer/             # New: transfer batch to warehouse
```

**Split endpoint:**
- Input: `{ split_quantity, new_batch_number? }`
- Validation: split_quantity > 0 and < source.remaining_quantity
- Creates new ItemBatch with split_quantity, decrements source.remaining_quantity
- Auto-generates batch number if not provided: `{source_batch_number}-S{count+1}`

**Transfer endpoint:**
- Input: `{ to_warehouse, transfer_quantity }`
- Validation: transfer_quantity > 0 and <= remaining_quantity, to_warehouse != current warehouse
- Creates StockMovement (TRF) with batch reference
- If full transfer: updates batch warehouse
- If partial: creates new batch at target warehouse, decrements source

---

## 9. Quality Inspection Toggle

### 9.1 Model Change

Add to `BillOfMaterials`:
```python
requires_quality_inspection = models.BooleanField(default=False)
```

### 9.2 BOM Form Update

Add checkbox in `BillOfMaterialsList.tsx` create/edit form:
- Label: "Requires Quality Inspection"
- Default: unchecked (False)

### 9.3 Quality Tab Behavior

**When `bom.requires_quality_inspection = True`:**
- Shows "Create Quality Inspection" button if none exists
- Shows inspection status, lines, pass/fail results if inspection exists
- Links to quality module for detailed editing
- Quality gate enforced on `complete_production`

**When `bom.requires_quality_inspection = False`:**
- Shows informational message: "Quality inspection is not required for this product"
- No create button
- Quality gate skipped on `complete_production`

### 9.4 Backend Change

In `ProductionOrderViewSet.complete_production`:
```python
# Only enforce quality gate if BOM requires it
if order.bom.requires_quality_inspection:
    from quality.models import QualityInspection
    failed_inspection = QualityInspection.objects.filter(
        production_order=order,
        lines__result='Fail'
    ).distinct().exists()
    if failed_inspection:
        return Response({"error": "..."}, status=400)
```

### 9.5 Serializer Update

Add `requires_quality_inspection` to `BillOfMaterialsSerializer` and `ProductionOrderSerializer` (nested from bom).

---

## 10. Backflush Materials — New Endpoint

### Endpoint

```
POST /production/production-orders/{id}/backflush_materials/
```

### Input

```json
{
  "warehouse": 1
}
```

### Logic

1. Validate order status is "In Progress"
2. For each BOM line:
   - Calculate required: `line.total_quantity * order.quantity_planned`
   - Calculate already issued: sum of MaterialIssue.quantity_issued for this line
   - Calculate remaining: required - issued
   - If remaining > 0:
     - Create MaterialIssue with quantity_issued = remaining
     - Post to GL (WIP debit / Raw Materials credit)
     - Create StockMovement (OUT)
3. Return summary: `{ issued_count, total_quantity_issued, skipped_count }`

### Validation

- Order must be "In Progress"
- Each component must have a linked inventory item (via `production_bom`)
- Sufficient stock must exist in the specified warehouse

---

## 11. Data Flow Diagrams

### Material Consumption Flow

```
User clicks "Issue All Materials" or submits manual issue form
  -> Frontend: POST /production/material-issues/ (creates MaterialIssue)
  -> Frontend: POST /production/material-issues/{id}/post_to_gl/
     -> Backend: Creates JournalHeader (WIP Debit / Raw Materials Credit)
     -> Backend: Creates StockMovement (OUT)
     -> Backend: Signal updates ItemStock.quantity
     -> Backend: Updates ItemStock.total_value
  -> Frontend: Invalidates queries (material-issues, material-requirements)
```

### Finished Goods Receipt Flow

```
User submits receive form
  -> Frontend: POST /production/material-receipts/ (creates MaterialReceipt)
  -> Frontend: POST /production/material-receipts/{id}/post_to_gl/
     -> Backend: Creates JournalHeader (Finished Goods Debit / WIP Credit)
     -> Backend: Creates StockMovement (IN)
     -> Backend: Creates ItemBatch (BATCH-{order_number})
     -> Backend: Signal updates ItemStock.quantity
     -> Backend: If scrap > 0: Creates SCRAP_LOSS journal entry
  -> Frontend: Invalidates queries (material-receipts, production-order)
```

### Batch Split Flow

```
User clicks "Split" on a batch row -> modal opens
  -> Frontend: POST /inventory/batches/{id}/split/
     -> Backend: Validates split_quantity < remaining_quantity
     -> Backend: Creates new ItemBatch (copies item, warehouse, unit_cost, expiry_date)
     -> Backend: Decrements source.remaining_quantity
  -> Frontend: Invalidates queries (batches)
```

### Batch Transfer Flow

```
User clicks "Transfer" on a batch row -> modal opens
  -> Frontend: POST /inventory/batches/{id}/transfer/
     -> Backend: Validates to_warehouse != current, transfer_quantity <= remaining
     -> Backend: Full transfer: updates batch.warehouse
     -> Backend: Partial transfer: creates new batch at target, decrements source
     -> Backend: Creates StockMovement (TRF) with batch reference
  -> Frontend: Invalidates queries (batches, stock-movements)
```

---

## 12. Error Handling

| Scenario | Behavior |
|----------|----------|
| Insufficient stock for material issue | 400 error with message "Insufficient stock for {component} in {warehouse}" |
| Backflush with no inventory items linked | 400 error listing which BOM components lack `production_bom` links |
| Split quantity >= remaining | 400 error "Split quantity must be less than remaining quantity" |
| Transfer to same warehouse | 400 error "Cannot transfer to the same warehouse" |
| Complete with failed QI (when required) | 400 error "Cannot complete: Quality inspection failed" |
| Post to GL when already posted | 400 error "Already posted to GL" |
| Delete posted material issue/receipt | 400 error "Cannot delete: GL entries exist" |

---

## 13. Files Changed Summary

### New Files (Frontend)
- `frontend/src/features/production/pages/ProductionOrderDetail.tsx`
- `frontend/src/features/production/pages/tabs/MaterialConsumptionTab.tsx`
- `frontend/src/features/production/pages/tabs/FinishedGoodsTab.tsx`
- `frontend/src/features/production/pages/tabs/JobCardsTab.tsx`
- `frontend/src/features/production/pages/tabs/BatchesTab.tsx`
- `frontend/src/features/production/pages/tabs/QualityTab.tsx`

### Modified Files (Frontend)
- `frontend/src/features/production/pages/ProductionOrderList.tsx` — row click navigation
- `frontend/src/features/production/hooks/useProduction.ts` — backflush hook, batch query hooks
- `frontend/src/features/inventory/pages/BatchList.tsx` — create form, split/transfer modals
- `frontend/src/features/inventory/hooks/useInventory.ts` — create/split/transfer batch hooks
- `frontend/src/features/production/pages/BillOfMaterialsList.tsx` — QI toggle checkbox
- `frontend/src/App.tsx` — new route
- `frontend/src/components/Sidebar.tsx` — rename batch nav item

### Modified Files (Backend)
- `production/models.py` — `requires_quality_inspection` on BillOfMaterials
- `production/views.py` — `backflush_materials` action, quality gate update
- `production/serializers.py` — new field on BOM serializer
- `inventory/views.py` — `split_batch`, `transfer_batch` actions
- `inventory/serializers.py` — BatchSplitSerializer, BatchTransferSerializer
- New migration for `requires_quality_inspection` field

---

## 14. Out of Scope

- Batch merge (combining two batches into one) — can be added later
- Routing management UI (defining operation sequences on BOMs) — separate enhancement
- Production scheduling Gantt chart / calendar view
- WIP valuation reports
- Batch expiry alert email notifications
- BOM component lines management in BOM form (separate enhancement)
