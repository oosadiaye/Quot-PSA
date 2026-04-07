# Inventory Management Module Specification

> **Project:** DTSG ERP
> **Module:** Inventory Management
> **Version:** 1.0.0
> **Last Updated:** 2026-03-01

---

## 1. Module Overview

The Inventory Management module provides comprehensive stock control including multi-warehouse tracking, batch/lot management, serial number tracking, valuation methods, reorder alerts, and stock reconciliation.

### Key Features
- Multi-warehouse inventory tracking
- Batch and lot management with expiry tracking
- Serial number tracking
- Multiple valuation methods (WA, FIFO, LIFO)
- Stock movements (IN, OUT, Adjustment, Transfer)
- Reorder alerts and expiry notifications
- Stock reconciliation/audit

---

## 2. File Structure

```
frontend/src/features/inventory/
├── pages/
│   ├── InventoryDashboard.tsx      # Main dashboard with stock summary
│   ├── ItemInventory.tsx           # Inventory ledger
│   ├── ItemForm.tsx               # Item CRUD form
│   ├── WarehouseList.tsx           # Warehouse management
│   ├── StockMovementList.tsx       # Stock movements (IN/OUT/ADJ/TRF)
│   ├── BatchList.tsx               # Batch/lot tracking
│   ├── StockLevelList.tsx          # Multi-warehouse stock view
│   ├── ProductCategoryList.tsx     # Category management
│   ├── ProductTypes.tsx            # Product types
│   ├── SerialNumberList.tsx        # Serial number tracking
│   ├── ReorderAlertList.tsx       # Low stock alerts
│   ├── ExpiryAlertList.tsx        # Batch expiry alerts
│   ├── ReconciliationList.tsx     # Stock audit
│   └── StockValuation.tsx         # Stock valuation report
├── hooks/
│   └── useInventory.ts            # All API hooks
└── SPEC.md                         # This file
```

---

## 3. Pages/Components

### 3.1 InventoryDashboard
**Route:** `/inventory/dashboard`
- Summary cards: Total Products, Stock Quantity, Inventory Value, Low Stock Alerts
- Quick stock transfer form
- Stock valuation table (top 10 items)
- Reorder alerts list
- Quick links to other inventory pages

### 3.2 ItemInventory (Inventory Ledger)
**Route:** `/inventory`
- Table view of all items with:
  - SKU / Item name
  - Quantity
  - Avg Cost
  - Total Value
  - Status (Low Stock / Healthy)

### 3.3 ItemForm (Create/Edit Item)
**Route:** `/inventory/new` | `/inventory/:id`

**Fields:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| sku | string | Yes | Stock keeping unit |
| name | string | Yes | Item name |
| description | string | No | Item description |
| product_type | FK | Yes | Product type |
| product_category | FK | No | Category |
| unit_of_measure | select | Yes | PCS, KG, L, M, BOX, PKT, SET |
| valuation_method | select | Yes | WA (Weighted Average), FIFO, LIFO |
| reorder_point | number | No | Minimum stock level |
| reorder_quantity | number | No | Qty to reorder |
| min_stock | number | No | Minimum stock |
| max_stock | number | No | Maximum stock |
| barcode | string | No | Barcode number |
| is_active | boolean | No | Active status |

### 3.4 WarehouseList
**Route:** `/inventory/warehouses`

**Features:**
- List all warehouses with status badges
- Create new warehouse form
- Edit warehouse inline
- Delete warehouse
- Mark as central warehouse

**Fields:**
| Field | Type | Description |
|-------|------|-------------|
| name | string | Warehouse name |
| location | string | Physical location |
| is_central | boolean | Is central warehouse |
| is_active | boolean | Active status |

### 3.5 StockMovementList
**Route:** `/inventory/movements`

**Movement Types:**
- **IN** - Stock received (green)
- **OUT** - Stock issued (red)
- **ADJ** - Stock adjustment (amber)
- **TRF** - Transfer between warehouses (blue)

**Features:**
- Create new movement with type selector
- Filter by movement type
- Reference number tracking
- Delete movements

### 3.6 BatchList
**Route:** `/inventory/batches`

**Features:**
- Batch number tracking
- Expiry date display
- Color coding: Expired (red), Expiring soon (amber), OK (default)
- Receipt date
- Quantity and unit cost

### 3.7 StockLevelList
**Route:** `/inventory/stocks`

**Features:**
- Grouped by warehouse
- Shows: Quantity, Reserved, Available
- Color coding for low stock

### 3.8 ProductCategoryList
**Route:** `/inventory/categories`

**Features:**
- Hierarchical categories
- Parent-child relationships
- Product type association

### 3.9 SerialNumberList
**Route:** `/inventory/serial-numbers`

**Features:**
- Serial number entry
- Status tracking (available, sold, returned)
- Warehouse assignment
- Purchase date

### 3.10 ReorderAlertList
**Route:** `/inventory/reorder-alerts`

**Features:**
- Auto-generated alerts
- Shows: Item, Warehouse, Current Stock, Reorder Point, Suggested Qty
- Dismiss alert action
- Generate alerts button

### 3.11 ExpiryAlertList
**Route:** `/inventory/expiry-alerts`

**Features:**
- Batches expiring within 30 days
- Expired batches highlighted in red
- Days until expiry display

### 3.12 ReconciliationList
**Route:** `/inventory/reconciliations`

**Features:**
- Create new reconciliation
- Full or partial count
- Complete & adjust action
- Status tracking (pending, completed)

### 3.13 StockValuation
**Route:** `/inventory/valuation`

**Features:**
- Total inventory value
- Per-item valuation
- Valuation method display

### 3.14 ProductTypes
**Route:** `/inventory/product-types`

**Features:**
- CRUD for product types
- GL account mapping (inventory, expense, revenue, asset accounts)

---

## 4. API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/inventory/warehouses/` | GET, POST | List/Create warehouses |
| `/api/inventory/warehouses/:id/` | GET, PATCH, DELETE | Retrieve/Update/Delete |
| `/api/inventory/items/` | GET, POST | List/Create items |
| `/api/inventory/items/:id/` | GET, PATCH, DELETE | Retrieve/Update/Delete |
| `/api/inventory/items/:id/stock_by_warehouse/` | GET | Stock per warehouse |
| `/api/inventory/items/:id/batches/` | GET | Item batches |
| `/api/inventory/items/stock_valuation/` | GET | Valuation report |
| `/api/inventory/items/reorder_alerts/` | GET | Low stock alerts |
| `/api/inventory/stocks/` | GET | All stock levels |
| `/api/inventory/batches/` | GET | All batches |
| `/api/inventory/movements/` | GET, POST | List/Create movements |
| `/api/inventory/movements/transfer/` | POST | Transfer stock |
| `/api/inventory/product-types/` | GET, POST | Product types |
| `/api/inventory/product-categories/` | GET, POST | Categories |
| `/api/inventory/serial-numbers/` | GET, POST | Serial numbers |
| `/api/inventory/reorder-alerts/` | GET | Reorder alerts |
| `/api/inventory/reorder-alerts/generate_alerts/` | POST | Generate alerts |
| `/api/inventory/reconciliations/` | GET, POST | Reconciliations |
| `/api/inventory/reconciliations/:id/adjust/` | POST | Apply adjustments |

---

## 5. Frontend Routes

| Route | Component | Description |
|-------|-----------|-------------|
| `/inventory/dashboard` | InventoryDashboard | Main dashboard |
| `/inventory` | ItemInventory | Items list |
| `/inventory/new` | ItemForm | Create item |
| `/inventory/:id` | ItemForm | Edit item |
| `/inventory/valuation` | StockValuation | Valuation report |
| `/inventory/product-types` | ProductTypes | Product types |
| `/inventory/categories` | ProductCategoryList | Categories |
| `/inventory/warehouses` | WarehouseList | Warehouses |
| `/inventory/stocks` | StockLevelList | Stock levels |
| `/inventory/batches` | BatchList | Batches/Lots |
| `/inventory/serial-numbers` | SerialNumberList | Serial numbers |
| `/inventory/movements` | StockMovementList | Movements |
| `/inventory/reconciliations` | ReconciliationList | Reconciliations |
| `/inventory/reorder-alerts` | ReorderAlertList | Reorder alerts |
| `/inventory/expiry-alerts` | ExpiryAlertList | Expiry alerts |

---

## 6. Custom Hooks

### Query Hooks
| Hook | Parameters | Returns |
|------|------------|---------|
| `useWarehouses()` | - | Warehouse list |
| `useItems(filters)` | filters object | Item list |
| `useItem(id)` | item ID | Single item |
| `useStockByWarehouse(itemId)` | item ID | Stock by warehouse |
| `useItemBatches(itemId)` | item ID | Item batches |
| `useStockValuation()` | - | Valuation data |
| `useReorderAlerts()` | - | Reorder alerts |
| `useStockMovements(filters)` | filters | Movement list |
| `useStockByWarehouseList()` | - | All stocks |
| `useBatches(filters)` | filters | Batch list |
| `useReconciliations()` | - | Reconciliation list |
| `useProductTypes()` | - | Product types |
| `useProductCategories(productType)` | type filter | Categories |
| `useSerialNumbers(filters)` | filters | Serial numbers |
| `useExpiryAlerts()` | - | Expiry alerts |

### Mutation Hooks
| Hook | Purpose |
|------|---------|
| `useCreateItem()` | Create item |
| `useUpdateItem()` | Update item |
| `useDeleteItem()` | Delete item |
| `useCreateWarehouse()` | Create warehouse |
| `useUpdateWarehouse()` | Update warehouse |
| `useDeleteWarehouse()` | Delete warehouse |
| `useCreateStockMovement()` | Create movement |
| `useStockTransfer()` | Transfer stock |
| `useCreateProductCategory()` | Create category |
| `useDeleteProductCategory()` | Delete category |
| `useCreateSerialNumber()` | Create serial |
| `useDeleteSerialNumber()` | Delete serial |
| `useGenerateReorderAlerts()` | Generate alerts |
| `useGenerateExpiryAlerts()` | Generate expiry alerts |
| `useCreateReconciliation()` | Create reconciliation |
| `useCompleteReconciliation()` | Complete reconciliation |
| `useDeleteBatch()` | Delete batch |
| `useDeleteReorderAlert()` | Delete alert |
| `useDeleteStockMovement()` | Delete movement |

---

## 7. Sidebar Menu Structure

```
Inventory
├── Inventory Dashboard (/inventory/dashboard)
├── Items (/inventory)
├── Product Types (/inventory/product-types)
├── Product Categories (/inventory/categories)
├── Warehouses (/inventory/warehouses)
├── Stock Levels (/inventory/stocks)
├── Batches / Lots (/inventory/batches)
├── Serial Numbers (/inventory/serial-numbers)
├── Stock Movements (/inventory/movements)
├── Stock Valuation (/inventory/valuation)
├── Reconciliation (/inventory/reconciliations)
├── Reorder Alerts (/inventory/reorder-alerts)
└── Expiry Alerts (/inventory/expiry-alerts)
```

---

## 8. Design System Compliance

All components follow the MASTER.md design system:

- **Colors:** Use CSS variables (--color-primary, --color-success, --color-error, etc.)
- **Typography:** IBM Plex Sans
- **Icons:** Lucide React
- **Spacing:** Follow spacing tokens (--space-xs, --space-sm, --space-md, etc.)
- **Components:** Cards, buttons, tables, forms as per design spec
- **Dark Mode:** Supported via CSS variables

---

## 9. Dependencies

### Frontend
- React 18+
- React Router DOM
- TanStack Query (React Query)
- Lucide React (icons)
- Axios (API client)

### Backend (Expected)
- Django REST Framework
- inventory app with models

---

## 10. Implementation Notes

1. All pages include BackButton for navigation
2. Forms include proper validation and error handling
3. Tables support empty states with appropriate messaging
4. Loading states handled with LoadingScreen component
5. Delete operations require confirmation
6. Stock movements update related queries on success

---

*End of Specification*
