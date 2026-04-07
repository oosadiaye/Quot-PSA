# Production Module Specification

## Overview
Production & Manufacturing module for DTSG ERP system. Manages work centers, bills of materials (BOM), and production orders.

## Routes

| Route | Component | Description |
|-------|-----------|-------------|
| `/production/dashboard` | ProductionDashboard | Production overview and stats |
| `/production/bom` | BillOfMaterialsList | Bill of Materials management |
| `/production/work-centers` | WorkCenterList | Work center management |
| `/production/orders` | ProductionOrderList | Production order management |

## Hooks (useProduction.ts)

### Work Center Hooks
- `useWorkCenters(filters?)` - List work centers
- `useWorkCenter(id)` - Get work center details
- `useCreateWorkCenter()` - Create work center
- `useUpdateWorkCenter(id)` - Update work center
- `useDeleteWorkCenter(id)` - Delete work center

### Bill of Materials Hooks
- `useBillOfMaterials(filters?)` - List BOMs
- `useBillOfMaterialsWithLines(filters?)` - List BOMs with lines
- `useBOM(id)` - Get BOM details
- `useCreateBOM()` - Create BOM
- `useUpdateBOM(id)` - Update BOM
- `useDeleteBOM(id)` - Delete BOM
- `useBOMLines(bomId)` - Get BOM line items
- `useCreateBOMLine()` - Create BOM line
- `useDeleteBOMLine()` - Delete BOM line

### Production Order Hooks
- `useProductionOrders(filters?)` - List production orders
- `useProductionOrder(id)` - Get production order details
- `useCreateProductionOrder()` - Create production order
- `useUpdateProductionOrder(id)` - Update production order
- `useDeleteProductionOrder(id)` - Delete production order
- `useStartProduction(id)` - Start production
- `useCompleteProduction({ id, quantity_produced })` - Complete production
- `usePostProductionToGL(id)` - Post to General Ledger
- `useMaterialRequirements(orderId)` - Get material requirements

### Material Issue Hooks
- `useMaterialIssues(filters?)` - List material issues
- `useCreateMaterialIssue()` - Create material issue
- `usePostMaterialIssueToGL(id)` - Post to GL

### Material Receipt Hooks
- `useMaterialReceipts(filters?)` - List material receipts
- `useCreateMaterialReceipt()` - Create material receipt
- `usePostMaterialReceiptToGL(id)` - Post to GL

### Job Card Hooks
- `useJobCards(filters?)` - List job cards
- `useCreateJobCard()` - Create job card
- `useStartJobCard(id)` - Start operation
- `useCompleteJobCard({ id, time_actual, labor_cost })` - Complete operation

### Routing Hooks
- `useRoutings(filters?)` - List routings
- `useCreateRouting()` - Create routing
- `useDeleteRouting(id)` - Delete routing

## API Endpoints

All endpoints prefixed with `/api/production/`

- `GET/POST /work-centers/`
- `GET/PUT/DELETE /work-centers/{id}/`
- `GET/POST /bills-of-materials/`
- `GET/PUT/DELETE /bills-of-materials/{id}/`
- `GET/POST /bom-lines/`
- `GET/PUT/DELETE /bom-lines/{id}/`
- `GET/POST /production-orders/`
- `GET/PUT/DELETE /production-orders/{id}/`
- `POST /production-orders/{id}/start_production/`
- `POST /production-orders/{id}/complete_production/`
- `POST /production-orders/{id}/post_to_gl/`
- `GET /production-orders/{id}/material_requirements/`
- `GET/POST /material-issues/`
- `POST /material-issues/{id}/post_to_gl/`
- `GET/POST /material-receipts/`
- `POST /material-receipts/{id}/post_to_gl/`
- `GET/POST /job-cards/`
- `POST /job-cards/{id}/start_operation/`
- `POST /job-cards/{id}/complete_operation/`
- `GET/POST /routings/`
- `GET/PUT/DELETE /routings/{id}/`

## Pagination

API responses use `{ results: [], count: number, next: string, previous: string }` format. Frontend hooks handle this automatically.

## Production Order Status Workflow

1. **Draft** → Created, not yet scheduled
2. **Scheduled** → Ready to start
3. **In Progress** → Manufacturing started
4. **Done** → Manufacturing completed
5. **Cancelled** → Order cancelled

## Bill of Materials Types

- **Finished** - Completed products
- **Semi-Finished** - Intermediate products
- **Raw Material** - Base materials
