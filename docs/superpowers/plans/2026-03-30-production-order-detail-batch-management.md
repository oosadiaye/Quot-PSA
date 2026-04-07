# Production Order Detail & Batch Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Production Order Detail page with material consumption, finished goods receipt, job cards, batch management, and quality inspection toggle — connecting the existing backend APIs to new frontend UI.

**Architecture:** Modular tab components inside a shell page (`ProductionOrderDetail.tsx`). Each tab is a standalone component. Backend gets 3 new endpoints (backflush, batch split, batch transfer) and 1 new model field (`requires_quality_inspection`). Frontend hooks already exist for most API calls — we add a few new ones and wire everything up.

**Tech Stack:** Django 6 + DRF (backend), React 19 + TypeScript + TanStack Query (frontend), inline styles following existing glassmorphism design system.

**Spec:** `docs/superpowers/specs/2026-03-30-production-order-detail-batch-management-design.md`

---

## File Structure

### New Files
```
frontend/src/features/production/pages/ProductionOrderDetail.tsx   — Shell: header, progress, action bar, tab router
frontend/src/features/production/pages/tabs/MaterialConsumptionTab.tsx — BOM requirements, backflush, manual issue, history
frontend/src/features/production/pages/tabs/FinishedGoodsTab.tsx   — Receive output, scrap, receipt history
frontend/src/features/production/pages/tabs/JobCardsTab.tsx        — Operation cards with start/complete
frontend/src/features/production/pages/tabs/BatchesTab.tsx         — Batches created/consumed by this order
frontend/src/features/production/pages/tabs/QualityTab.tsx         — Quality inspection (conditional on BOM toggle)
```

### Modified Files
```
production/models.py:38                — Add requires_quality_inspection field after is_active
production/serializers.py:36-38        — Add field to BOM serializer, add bom_requires_qi to ProductionOrderSerializer
production/views.py:273-295            — Update quality gate in complete_production
production/views.py:410+               — Add backflush_materials action
inventory/views.py:272-277             — Add split_batch and transfer_batch actions
inventory/serializers.py:110+          — Add BatchSplitSerializer, BatchTransferSerializer
frontend/src/features/production/hooks/useProduction.ts:496+  — Add backflush hook
frontend/src/features/inventory/hooks/useInventory.ts:502+    — Add split/transfer/create batch hooks
frontend/src/features/production/pages/ProductionOrderList.tsx:124 — Add row click navigation
frontend/src/features/production/pages/BillOfMaterialsList.tsx:16-23,236-244 — Add QI toggle to form
frontend/src/App.tsx:609-611           — Add detail route
frontend/src/components/Sidebar.tsx:150 — Rename Batches / Lots to Batch Management
```

---

## Task 1: Backend — Add `requires_quality_inspection` to BOM model

**Files:**
- Modify: `production/models.py:38`
- Modify: `production/serializers.py:36-38`

- [ ] **Step 1: Add field to BillOfMaterials model**

In `production/models.py`, after line 38 (`is_active = models.BooleanField(default=True, db_index=True)`), add:

```python
    requires_quality_inspection = models.BooleanField(default=False)
```

- [ ] **Step 2: Add field to BillOfMaterialsSerializer**

In `production/serializers.py`, update the `fields` list on line 36-37:

```python
        fields = ['id', 'item_code', 'item_name', 'item_type', 'item_type_display',
                  'unit', 'standard_cost', 'is_active', 'requires_quality_inspection', 'lines',
                  'created_at', 'updated_at', 'created_by', 'updated_by']
```

- [ ] **Step 3: Add `bom_requires_quality_inspection` to ProductionOrderSerializer**

In `production/serializers.py`, add a new read-only field to `ProductionOrderSerializer` (after line 45):

```python
    bom_requires_quality_inspection = serializers.BooleanField(
        source='bom.requires_quality_inspection', read_only=True)
```

And add `'bom_requires_quality_inspection'` to the `fields` list (line 49-52):

```python
        fields = ['id', 'order_number', 'bom', 'bom_name', 'quantity_planned',
                  'quantity_produced', 'start_date', 'end_date', 'status', 'status_display',
                  'work_center', 'work_center_name', 'notes', 'bom_requires_quality_inspection',
                  'created_at', 'updated_at', 'created_by', 'updated_by']
```

- [ ] **Step 4: Create and run migration**

```bash
cd "c:/Users/USER/Documents/Antigravity/DTSG erp"
python manage.py makemigrations production --name="add_requires_quality_inspection"
python manage.py migrate_schemas --shared
python manage.py migrate_schemas --tenant
```

- [ ] **Step 5: Commit**

```bash
git add production/models.py production/serializers.py production/migrations/
git commit -m "feat(production): add requires_quality_inspection toggle to BOM model"
```

---

## Task 2: Backend — Update quality gate in `complete_production`

**Files:**
- Modify: `production/views.py:282-295`

- [ ] **Step 1: Update the quality gate to respect BOM toggle**

In `production/views.py`, replace lines 282-295:

```python
        # P2FG-H1: Quality Gate for FG - Only enforce if BOM requires it
        if order.bom.requires_quality_inspection:
            try:
                from quality.models import QualityInspection
                failed_inspection = QualityInspection.objects.filter(
                    production_order=order,
                    lines__result='Fail'
                ).distinct().exists()
                if failed_inspection:
                    return Response({
                        "error": "Cannot complete production: Quality inspection failed. Clear quality issues before completion.",
                        "production_order": order.order_number
                    }, status=status.HTTP_400_BAD_REQUEST)
            except ImportError:
                pass  # Quality module not available
```

- [ ] **Step 2: Verify the view still loads**

```bash
cd "c:/Users/USER/Documents/Antigravity/DTSG erp"
python -c "import django; import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE','dtsg_erp.settings'); django.setup(); from production.views import ProductionOrderViewSet; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add production/views.py
git commit -m "feat(production): quality gate respects requires_quality_inspection toggle"
```

---

## Task 3: Backend — Add `backflush_materials` endpoint

**Files:**
- Modify: `production/views.py` (add new action after `material_requirements` action, around line 410)

- [ ] **Step 1: Add the backflush action to ProductionOrderViewSet**

Add this action after the `material_requirements` action in `production/views.py`:

```python
    @action(detail=True, methods=['post'])
    def backflush_materials(self, request, pk=None):
        """Issue all remaining BOM materials in one click."""
        order = self.get_object()
        if order.status != 'In Progress':
            return Response(
                {"error": "Only in-progress orders can have materials backflushed"},
                status=status.HTTP_400_BAD_REQUEST
            )

        warehouse_id = request.data.get('warehouse')
        if not warehouse_id:
            return Response(
                {"error": "warehouse is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        from inventory.models import Item, ItemStock
        from django.db.models import Sum

        issued_count = 0
        total_qty_issued = Decimal('0')
        skipped = []

        with transaction.atomic():
            for bom_line in order.bom.lines.select_related('component').all():
                required = bom_line.total_quantity * order.quantity_planned
                already_issued = order.material_issues.filter(
                    bom_line=bom_line
                ).aggregate(total=Sum('quantity_issued'))['total'] or Decimal('0')
                remaining = required - already_issued

                if remaining <= 0:
                    continue

                # Find inventory item linked to this BOM component
                inv_item = Item.objects.filter(production_bom=bom_line.component).first()
                if not inv_item:
                    skipped.append({
                        'component': bom_line.component.item_code,
                        'reason': 'No inventory item linked to BOM component'
                    })
                    continue

                # Check stock availability
                stock = ItemStock.objects.filter(
                    item=inv_item, warehouse_id=warehouse_id
                ).first()
                if not stock or stock.available_quantity < remaining:
                    available = stock.available_quantity if stock else Decimal('0')
                    skipped.append({
                        'component': bom_line.component.item_code,
                        'reason': f'Insufficient stock: need {remaining}, available {available}'
                    })
                    continue

                # Create material issue
                issue = MaterialIssue.objects.create(
                    production_order=order,
                    bom_line=bom_line,
                    quantity_issued=remaining,
                    issue_date=timezone.now().date(),
                    notes=f'Backflush issue for {bom_line.component.item_name}'
                )

                # Post to GL
                try:
                    from accounting.transaction_posting import TransactionPostingService
                    TransactionPostingService.post_material_issue(issue)
                except Exception:
                    pass  # GL posting is best-effort during backflush

                issued_count += 1
                total_qty_issued += remaining

        return Response({
            'issued_count': issued_count,
            'total_quantity_issued': str(total_qty_issued),
            'skipped': skipped,
        })
```

- [ ] **Step 2: Ensure Decimal import exists at top of views.py**

Check that `from decimal import Decimal` is in the imports at the top of `production/views.py`. If not, add it.

- [ ] **Step 3: Verify it loads**

```bash
python -c "import django; import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE','dtsg_erp.settings'); django.setup(); from production.views import ProductionOrderViewSet; print('backflush_materials' in dir(ProductionOrderViewSet)); print('OK')"
```

Expected: `True` then `OK`

- [ ] **Step 4: Commit**

```bash
git add production/views.py
git commit -m "feat(production): add backflush_materials endpoint for one-click material issue"
```

---

## Task 4: Backend — Add batch split and transfer endpoints

**Files:**
- Modify: `inventory/views.py:272-277`
- Modify: `inventory/serializers.py:110+`

- [ ] **Step 1: Add serializers for split and transfer**

In `inventory/serializers.py`, add after line 110 (after `ItemBatchSerializer`):

```python
class BatchSplitSerializer(serializers.Serializer):
    split_quantity = serializers.DecimalField(max_digits=15, decimal_places=4)
    new_batch_number = serializers.CharField(max_length=50, required=False)

class BatchTransferSerializer(serializers.Serializer):
    to_warehouse = serializers.IntegerField()
    transfer_quantity = serializers.DecimalField(max_digits=15, decimal_places=4)
```

- [ ] **Step 2: Add split and transfer actions to ItemBatchViewSet**

In `inventory/views.py`, replace the `ItemBatchViewSet` (lines 272-277) with:

```python
class ItemBatchViewSet(viewsets.ModelViewSet):
    queryset = ItemBatch.objects.all().select_related('item', 'warehouse')
    serializer_class = ItemBatchSerializer
    filterset_fields = ['item', 'warehouse']
    pagination_class = InventoryPagination

    @action(detail=True, methods=['post'])
    def split(self, request, pk=None):
        """Split a batch into two batches."""
        from .serializers import BatchSplitSerializer
        serializer = BatchSplitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        batch = self.get_object()
        split_qty = serializer.validated_data['split_quantity']

        if split_qty <= 0 or split_qty >= batch.remaining_quantity:
            return Response(
                {"error": "Split quantity must be greater than 0 and less than remaining quantity"},
                status=400
            )

        # Generate batch number if not provided
        new_number = serializer.validated_data.get('new_batch_number')
        if not new_number:
            existing_splits = ItemBatch.objects.filter(
                batch_number__startswith=f"{batch.batch_number}-S"
            ).count()
            new_number = f"{batch.batch_number}-S{existing_splits + 1}"

        with transaction.atomic():
            new_batch = ItemBatch.objects.create(
                item=batch.item,
                warehouse=batch.warehouse,
                batch_number=new_number,
                receipt_date=batch.receipt_date,
                expiry_date=batch.expiry_date,
                quantity=split_qty,
                remaining_quantity=split_qty,
                unit_cost=batch.unit_cost,
                reference_number=f"Split from {batch.batch_number}",
            )
            batch.remaining_quantity -= split_qty
            batch.save(update_fields=['remaining_quantity'])

        return Response(ItemBatchSerializer(new_batch).data, status=201)

    @action(detail=True, methods=['post'])
    def transfer(self, request, pk=None):
        """Transfer batch (or partial) to another warehouse."""
        from .serializers import BatchTransferSerializer
        serializer = BatchTransferSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        batch = self.get_object()
        to_warehouse_id = serializer.validated_data['to_warehouse']
        transfer_qty = serializer.validated_data['transfer_quantity']

        if to_warehouse_id == batch.warehouse_id:
            return Response({"error": "Cannot transfer to the same warehouse"}, status=400)

        if transfer_qty <= 0 or transfer_qty > batch.remaining_quantity:
            return Response(
                {"error": "Transfer quantity must be > 0 and <= remaining quantity"},
                status=400
            )

        from .models import Warehouse, StockMovement

        try:
            to_warehouse = Warehouse.objects.get(pk=to_warehouse_id)
        except Warehouse.DoesNotExist:
            return Response({"error": "Target warehouse not found"}, status=400)

        with transaction.atomic():
            # Create transfer stock movement
            StockMovement.objects.create(
                item=batch.item,
                warehouse=batch.warehouse,
                to_warehouse=to_warehouse,
                movement_type='TRF',
                quantity=transfer_qty,
                unit_price=batch.unit_cost,
                batch=batch,
                reference_number=f"BATCH-TRF-{batch.batch_number}",
                remarks=f"Batch transfer to {to_warehouse.name}",
            )

            if transfer_qty == batch.remaining_quantity:
                # Full transfer — move the batch
                batch.warehouse = to_warehouse
                batch.save(update_fields=['warehouse'])
                result_batch = batch
            else:
                # Partial transfer — create new batch at target
                existing_transfers = ItemBatch.objects.filter(
                    batch_number__startswith=f"{batch.batch_number}-T"
                ).count()
                new_number = f"{batch.batch_number}-T{existing_transfers + 1}"

                result_batch = ItemBatch.objects.create(
                    item=batch.item,
                    warehouse=to_warehouse,
                    batch_number=new_number,
                    receipt_date=batch.receipt_date,
                    expiry_date=batch.expiry_date,
                    quantity=transfer_qty,
                    remaining_quantity=transfer_qty,
                    unit_cost=batch.unit_cost,
                    reference_number=f"Transfer from {batch.batch_number}",
                )
                batch.remaining_quantity -= transfer_qty
                batch.save(update_fields=['remaining_quantity'])

        return Response(ItemBatchSerializer(result_batch).data)
```

- [ ] **Step 3: Ensure `transaction` import exists in inventory/views.py**

Check that `from django.db import transaction` is in the imports at the top of `inventory/views.py`. If not, add it.

- [ ] **Step 4: Verify endpoints load**

```bash
python -c "import django; import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE','dtsg_erp.settings'); django.setup(); from inventory.views import ItemBatchViewSet; print('split' in dir(ItemBatchViewSet), 'transfer' in dir(ItemBatchViewSet))"
```

Expected: `True True`

- [ ] **Step 5: Commit**

```bash
git add inventory/views.py inventory/serializers.py
git commit -m "feat(inventory): add batch split and transfer endpoints"
```

---

## Task 5: Frontend — Add new hooks

**Files:**
- Modify: `frontend/src/features/production/hooks/useProduction.ts:496+`
- Modify: `frontend/src/features/inventory/hooks/useInventory.ts:502+`

- [ ] **Step 1: Add backflush hook to useProduction.ts**

Add after the `usePostMaterialReceiptToGL` hook (after line 496):

```typescript
export const useBackflushMaterials = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ orderId, warehouse }: { orderId: number; warehouse: number }) => {
            const { data } = await apiClient.post(
                `/production/production-orders/${orderId}/backflush_materials/`,
                { warehouse }
            );
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['production-material-issues'] });
            queryClient.invalidateQueries({ queryKey: ['production-material-requirements'] });
            queryClient.invalidateQueries({ queryKey: ['production-order'] });
            queryClient.invalidateQueries({ queryKey: ['inventory-items'] });
            queryClient.invalidateQueries({ queryKey: ['inventory-stock'] });
            queryClient.invalidateQueries({ queryKey: ['inventory-batches'] });
        },
    });
};
```

- [ ] **Step 2: Add batch split, transfer, and create hooks to useInventory.ts**

Add after the `useDeleteBatch` hook (after line 503):

```typescript
export const useCreateBatch = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (payload: any) => {
            const { data } = await apiClient.post('/inventory/batches/', payload);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['inventory-batches'] });
        },
    });
};

export const useSplitBatch = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, split_quantity, new_batch_number }: { id: number; split_quantity: number; new_batch_number?: string }) => {
            const { data } = await apiClient.post(`/inventory/batches/${id}/split/`, {
                split_quantity,
                ...(new_batch_number ? { new_batch_number } : {}),
            });
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['inventory-batches'] });
        },
    });
};

export const useTransferBatch = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, to_warehouse, transfer_quantity }: { id: number; to_warehouse: number; transfer_quantity: number }) => {
            const { data } = await apiClient.post(`/inventory/batches/${id}/transfer/`, {
                to_warehouse,
                transfer_quantity,
            });
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['inventory-batches'] });
            queryClient.invalidateQueries({ queryKey: ['inventory-stock'] });
        },
    });
};
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/features/production/hooks/useProduction.ts frontend/src/features/inventory/hooks/useInventory.ts
git commit -m "feat: add hooks for backflush, batch split, batch transfer, batch create"
```

---

## Task 6: Frontend — Add route and sidebar changes

**Files:**
- Modify: `frontend/src/App.tsx:609-611`
- Modify: `frontend/src/components/Sidebar.tsx:150`

- [ ] **Step 1: Add import for ProductionOrderDetail in App.tsx**

Find the existing production page imports in `App.tsx` (search for `ProductionOrderList`) and add alongside them:

```typescript
const ProductionOrderDetail = lazy(() => import('./features/production/pages/ProductionOrderDetail'));
```

- [ ] **Step 2: Add route for production order detail**

In `App.tsx`, after the `/production/orders` route (line 609-611), add:

```typescript
                        <Route path="/production/orders/:id" element={
                          <ProtectedRoute><ProductionOrderDetail /></ProtectedRoute>
                        } />
```

- [ ] **Step 3: Rename sidebar nav item**

In `frontend/src/components/Sidebar.tsx`, change line 150:

From:
```typescript
            { name: 'Batches / Lots', path: '/inventory/batches', icon: Package },
```
To:
```typescript
            { name: 'Batch Management', path: '/inventory/batches', icon: Package },
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/App.tsx frontend/src/components/Sidebar.tsx
git commit -m "feat: add production order detail route and rename batch nav item"
```

---

## Task 7: Frontend — Add row click navigation to ProductionOrderList

**Files:**
- Modify: `frontend/src/features/production/pages/ProductionOrderList.tsx:1-5,124`

- [ ] **Step 1: Add useNavigate import**

In `ProductionOrderList.tsx`, update line 1 to add `useNavigate`:

```typescript
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
```

- [ ] **Step 2: Add navigate hook inside component**

After line 15 (`const postToGL = usePostProductionToGL();`), add:

```typescript
    const navigate = useNavigate();
```

- [ ] **Step 3: Add onClick and cursor to table row**

Change line 124 from:

```typescript
                                    <tr key={order.id} style={{ borderBottom: '1px solid var(--color-border)' }}>
```

To:

```typescript
                                    <tr key={order.id} onClick={() => navigate(`/production/orders/${order.id}`)} style={{ borderBottom: '1px solid var(--color-border)', cursor: 'pointer', transition: 'background 0.15s' }} onMouseOver={e => e.currentTarget.style.background = 'var(--color-surface-hover, #f8fafc)'} onMouseOut={e => e.currentTarget.style.background = ''}>
```

- [ ] **Step 4: Stop propagation on action buttons**

Wrap each button's onClick handler to stop propagation. For example, change line 144:

From: `onClick={() => handleStart(order.id)}`
To: `onClick={(e) => { e.stopPropagation(); handleStart(order.id); }}`

Apply the same pattern to all action buttons in lines 144, 153, 162, 171.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/production/pages/ProductionOrderList.tsx
git commit -m "feat: add row click navigation to production order detail"
```

---

## Task 8: Frontend — Add QI toggle to BillOfMaterialsList

**Files:**
- Modify: `frontend/src/features/production/pages/BillOfMaterialsList.tsx:16-23,236-244`

- [ ] **Step 1: Add field to form state**

In `BillOfMaterialsList.tsx`, update the `formData` state (lines 16-23) to add the new field:

```typescript
    const [formData, setFormData] = useState({
        item_code: '',
        item_name: '',
        item_type: 'Finished',
        unit: 'PCS',
        standard_cost: '0',
        is_active: true,
        requires_quality_inspection: false,
    });
```

- [ ] **Step 2: Add checkbox to form after Active checkbox**

After the Active checkbox (line 244), add:

```typescript
                                </div>
                                <div style={{ marginBottom: '1.5rem' }}>
                                    <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                        <input
                                            type="checkbox"
                                            checked={formData.requires_quality_inspection}
                                            onChange={e => setFormData({ ...formData, requires_quality_inspection: e.target.checked })}
                                        />
                                        <span>Requires Quality Inspection</span>
                                    </label>
                                </div>
```

- [ ] **Step 3: Update handleEdit to include new field**

Find the `handleEdit` function and add `requires_quality_inspection: bom.requires_quality_inspection ?? false` to the formData set.

- [ ] **Step 4: Update resetForm to include new field**

Find the `resetForm` function and add `requires_quality_inspection: false` to the reset state.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/production/pages/BillOfMaterialsList.tsx
git commit -m "feat: add quality inspection toggle to BOM form"
```

---

## Task 9: Frontend — Build ProductionOrderDetail shell page

**Files:**
- Create: `frontend/src/features/production/pages/ProductionOrderDetail.tsx`

- [ ] **Step 1: Create the shell page**

Create `frontend/src/features/production/pages/ProductionOrderDetail.tsx`:

```typescript
import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { useProductionOrder } from '../hooks/useProduction';
import Sidebar from '../../../components/Sidebar';
import BackButton from '../../../components/BackButton';
import LoadingScreen from '../../../components/common/LoadingScreen';
import MaterialConsumptionTab from './tabs/MaterialConsumptionTab';
import FinishedGoodsTab from './tabs/FinishedGoodsTab';
import JobCardsTab from './tabs/JobCardsTab';
import BatchesTab from './tabs/BatchesTab';
import QualityTab from './tabs/QualityTab';
import {
    useStartProduction, useCompleteProduction, usePostProductionToGL,
} from '../hooks/useProduction';
import { Package, CheckCircle, Layers, ClipboardList, Shield, Play, FileCheck, XCircle } from 'lucide-react';

type TabKey = 'materials' | 'finished' | 'jobcards' | 'batches' | 'quality';

const STATUS_COLORS: Record<string, string> = {
    Draft: '#64748b',
    Scheduled: '#191e6a',
    'In Progress': '#3b82f6',
    'On Hold': '#f59e0b',
    Done: '#10b981',
    Cancelled: '#ef4444',
};

const ProductionOrderDetail = () => {
    const { id } = useParams<{ id: string }>();
    const orderId = id ? parseInt(id) : undefined;
    const { data: order, isLoading } = useProductionOrder(orderId);
    const startProduction = useStartProduction();
    const completeProduction = useCompleteProduction();
    const postToGL = usePostProductionToGL();
    const [activeTab, setActiveTab] = useState<TabKey>('materials');
    const [completeQty, setCompleteQty] = useState('');
    const [showCompletePrompt, setShowCompletePrompt] = useState(false);

    if (isLoading || !order) {
        return <LoadingScreen message="Loading production order..." />;
    }

    const progress = order.quantity_planned > 0
        ? Math.round((order.quantity_produced / order.quantity_planned) * 100)
        : 0;

    const statusColor = STATUS_COLORS[order.status] || '#64748b';

    const handleStart = async () => {
        await startProduction.mutateAsync(order.id);
    };

    const handleComplete = async () => {
        const qty = parseFloat(completeQty);
        if (!qty || qty <= 0) return;
        await completeProduction.mutateAsync({ id: order.id, quantity_produced: qty });
        setShowCompletePrompt(false);
        setCompleteQty('');
    };

    const handlePostToGL = async () => {
        await postToGL.mutateAsync(order.id);
    };

    const tabs: { key: TabKey; label: string; icon: any }[] = [
        { key: 'materials', label: 'Materials', icon: Package },
        { key: 'finished', label: 'Finished Goods', icon: CheckCircle },
        { key: 'jobcards', label: 'Job Cards', icon: ClipboardList },
        { key: 'batches', label: 'Batches', icon: Layers },
        { key: 'quality', label: 'Quality', icon: Shield },
    ];

    return (
        <div style={{ display: 'flex', minHeight: '100vh', background: 'var(--color-bg, #f1f5f9)' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2rem 2.5rem' }}>
                <BackButton />

                {/* ── Header Card ─────────────────────────── */}
                <div style={{
                    background: 'var(--color-surface, #fff)', border: '1px solid var(--color-border, #e2e8f0)',
                    borderRadius: '14px', padding: '24px 28px', boxShadow: '0 1px 2px rgba(0,0,0,0.05)',
                    marginBottom: '20px',
                }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
                            <h1 style={{ fontSize: '22px', fontWeight: 800, letterSpacing: '-0.5px' }}>{order.order_number}</h1>
                            <span style={{
                                padding: '5px 14px', borderRadius: '20px', fontSize: '11px',
                                fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.5px',
                                background: `${statusColor}1a`, color: statusColor,
                            }}>{order.status}</span>
                            {order.bom_requires_quality_inspection && (
                                <span style={{
                                    padding: '4px 10px', borderRadius: '20px', fontSize: '10px',
                                    fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.5px',
                                    background: 'rgba(139,92,246,0.1)', color: '#8b5cf6',
                                }}>QI Required</span>
                            )}
                        </div>
                    </div>

                    <div style={{
                        display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '20px',
                        paddingTop: '16px', borderTop: '1px solid var(--color-border, #e2e8f0)',
                    }}>
                        {[
                            { label: 'Product (BOM)', value: order.bom_name },
                            { label: 'Work Center', value: order.work_center_name || '—' },
                            { label: 'Start Date', value: order.start_date || '—' },
                            { label: 'End Date', value: order.end_date || '—' },
                            { label: 'Quantity', value: `${order.quantity_produced} / ${order.quantity_planned}` },
                        ].map(m => (
                            <div key={m.label}>
                                <div style={{ fontSize: '11px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px', color: 'var(--color-text-muted, #64748b)', marginBottom: '4px' }}>{m.label}</div>
                                <div style={{ fontSize: '14px', fontWeight: 600 }}>{m.value}</div>
                            </div>
                        ))}
                    </div>

                    {/* Progress bar */}
                    <div style={{ marginTop: '14px', paddingTop: '14px', borderTop: '1px solid var(--color-border, #e2e8f0)' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', fontWeight: 600, color: 'var(--color-text-muted, #64748b)', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: '6px' }}>
                            <span>Production Progress</span>
                            <span style={{ color: '#191e6a', fontWeight: 700 }}>{progress}%</span>
                        </div>
                        <div style={{ height: '8px', borderRadius: '99px', background: '#e2e8f0', overflow: 'hidden' }}>
                            <div style={{ height: '100%', borderRadius: '99px', background: 'linear-gradient(90deg, #191e6a, #4a52c0)', width: `${progress}%`, transition: 'width 0.5s ease' }} />
                        </div>
                    </div>
                </div>

                {/* ── Action Bar ──────────────────────────── */}
                <div style={{ display: 'flex', gap: '10px', marginBottom: '20px', flexWrap: 'wrap', alignItems: 'center' }}>
                    {order.status === 'Draft' && (
                        <button onClick={handleStart} style={{ padding: '9px 20px', borderRadius: '8px', fontSize: '13px', fontWeight: 600, border: 'none', cursor: 'pointer', background: 'linear-gradient(135deg, #0f1240, #191e6a)', color: 'white', boxShadow: '0 4px 12px rgba(15,18,64,0.3)', fontFamily: 'inherit', display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                            <Play size={14} /> Schedule
                        </button>
                    )}
                    {order.status === 'Scheduled' && (
                        <button onClick={handleStart} style={{ padding: '9px 20px', borderRadius: '8px', fontSize: '13px', fontWeight: 600, border: 'none', cursor: 'pointer', background: 'linear-gradient(135deg, #0f1240, #191e6a)', color: 'white', boxShadow: '0 4px 12px rgba(15,18,64,0.3)', fontFamily: 'inherit', display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                            <Play size={14} /> Start Production
                        </button>
                    )}
                    {order.status === 'In Progress' && !showCompletePrompt && (
                        <button onClick={() => setShowCompletePrompt(true)} style={{ padding: '9px 20px', borderRadius: '8px', fontSize: '13px', fontWeight: 600, border: 'none', cursor: 'pointer', background: 'linear-gradient(135deg, #059669, #10b981)', color: 'white', boxShadow: '0 4px 12px rgba(16,185,129,0.3)', fontFamily: 'inherit', display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                            <CheckCircle size={14} /> Complete Production
                        </button>
                    )}
                    {showCompletePrompt && (
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '6px 14px', borderRadius: '8px', background: 'rgba(16,185,129,0.06)', border: '1px solid rgba(16,185,129,0.2)' }}>
                            <label style={{ fontSize: '12px', fontWeight: 600, color: 'var(--color-text-muted)' }}>Qty Produced:</label>
                            <input type="number" value={completeQty} onChange={e => setCompleteQty(e.target.value)} placeholder={String(order.quantity_planned)} style={{ width: '100px', padding: '6px 10px', borderRadius: '6px', border: '2px solid var(--color-border, #e2e8f0)', fontSize: '13px', fontFamily: 'inherit' }} />
                            <button onClick={handleComplete} style={{ padding: '6px 14px', borderRadius: '6px', fontSize: '12px', fontWeight: 600, border: 'none', cursor: 'pointer', background: '#10b981', color: 'white', fontFamily: 'inherit' }}>Confirm</button>
                            <button onClick={() => setShowCompletePrompt(false)} style={{ padding: '6px 14px', borderRadius: '6px', fontSize: '12px', fontWeight: 600, border: '1px solid var(--color-border)', cursor: 'pointer', background: 'var(--color-surface)', color: 'var(--color-text-secondary)', fontFamily: 'inherit' }}>Cancel</button>
                        </div>
                    )}
                    {order.status === 'Done' && (
                        <button onClick={handlePostToGL} style={{ padding: '9px 20px', borderRadius: '8px', fontSize: '13px', fontWeight: 600, border: 'none', cursor: 'pointer', background: 'linear-gradient(135deg, #0f1240, #191e6a)', color: 'white', boxShadow: '0 4px 12px rgba(15,18,64,0.3)', fontFamily: 'inherit', display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                            <FileCheck size={14} /> Post to GL
                        </button>
                    )}
                    {['Draft', 'Scheduled', 'In Progress'].includes(order.status) && (
                        <button style={{ padding: '9px 20px', borderRadius: '8px', fontSize: '13px', fontWeight: 600, border: '1.5px solid rgba(239,68,68,0.3)', cursor: 'pointer', background: 'var(--color-surface, #fff)', color: '#ef4444', fontFamily: 'inherit', display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                            <XCircle size={14} /> Cancel Order
                        </button>
                    )}
                </div>

                {/* ── Tabs ────────────────────────────────── */}
                <div style={{ display: 'flex', gap: 0, borderBottom: '2px solid var(--color-border, #e2e8f0)', marginBottom: '20px' }}>
                    {tabs.map(t => (
                        <div key={t.key} onClick={() => setActiveTab(t.key)} style={{
                            padding: '10px 20px', fontSize: '13px', fontWeight: 600, cursor: 'pointer',
                            color: activeTab === t.key ? '#191e6a' : 'var(--color-text-muted, #64748b)',
                            borderBottom: activeTab === t.key ? '2px solid #191e6a' : '2px solid transparent',
                            marginBottom: '-2px', transition: 'all 0.15s',
                            display: 'flex', alignItems: 'center', gap: '6px',
                        }}>
                            <t.icon size={14} /> {t.label}
                        </div>
                    ))}
                </div>

                {/* ── Tab Content ─────────────────────────── */}
                {activeTab === 'materials' && <MaterialConsumptionTab orderId={order.id} order={order} />}
                {activeTab === 'finished' && <FinishedGoodsTab orderId={order.id} order={order} />}
                {activeTab === 'jobcards' && <JobCardsTab orderId={order.id} order={order} />}
                {activeTab === 'batches' && <BatchesTab orderId={order.id} order={order} />}
                {activeTab === 'quality' && <QualityTab orderId={order.id} order={order} />}
            </main>
        </div>
    );
};

export default ProductionOrderDetail;
```

- [ ] **Step 2: Create tabs directory**

```bash
mkdir -p "c:/Users/USER/Documents/Antigravity/DTSG erp/frontend/src/features/production/pages/tabs"
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/features/production/pages/ProductionOrderDetail.tsx
git commit -m "feat: add ProductionOrderDetail shell page with header, action bar, tabs"
```

---

## Task 10: Frontend — Build MaterialConsumptionTab

**Files:**
- Create: `frontend/src/features/production/pages/tabs/MaterialConsumptionTab.tsx`

- [ ] **Step 1: Create the component**

Create `frontend/src/features/production/pages/tabs/MaterialConsumptionTab.tsx`:

```typescript
import { useState } from 'react';
import {
    useMaterialRequirements, useMaterialIssues,
    useCreateMaterialIssue, usePostMaterialIssueToGL,
    useBackflushMaterials,
} from '../../hooks/useProduction';
import { useWarehouses } from '../../../inventory/hooks/useInventory';
import { Zap } from 'lucide-react';

interface Props {
    orderId: number;
    order: any;
}

const MaterialConsumptionTab = ({ orderId, order }: Props) => {
    const { data: requirements } = useMaterialRequirements(orderId);
    const { data: issuesData } = useMaterialIssues({ production_order: orderId });
    const { data: warehousesData } = useWarehouses();
    const createIssue = useCreateMaterialIssue();
    const postIssueToGL = usePostMaterialIssueToGL();
    const backflush = useBackflushMaterials();

    const [issueForm, setIssueForm] = useState({ bom_line: '', quantity: '', warehouse: '', notes: '' });
    const [backflushWarehouse, setBackflushWarehouse] = useState('');

    const issues = issuesData?.results || issuesData || [];
    const warehouses = warehousesData?.results || warehousesData || [];
    const reqs = Array.isArray(requirements) ? requirements : [];

    // Calculate issued quantities per BOM line
    const issuedByLine: Record<number, number> = {};
    issues.forEach((iss: any) => {
        issuedByLine[iss.bom_line] = (issuedByLine[iss.bom_line] || 0) + parseFloat(iss.quantity_issued || 0);
    });

    const isInProgress = order.status === 'In Progress';
    const hasRemaining = reqs.some((r: any) => {
        const issued = issuedByLine[r.bom_line_id] || 0;
        return r.required_quantity - issued > 0;
    });

    const handleIssue = async (e: React.FormEvent) => {
        e.preventDefault();
        const result = await createIssue.mutateAsync({
            production_order: orderId,
            bom_line: parseInt(issueForm.bom_line),
            quantity_issued: parseFloat(issueForm.quantity),
            issue_date: new Date().toISOString().split('T')[0],
            notes: issueForm.notes,
        });
        // Auto-post to GL
        try { await postIssueToGL.mutateAsync(result.id); } catch {}
        setIssueForm({ bom_line: '', quantity: '', warehouse: '', notes: '' });
    };

    const handleBackflush = async () => {
        if (!backflushWarehouse) return;
        await backflush.mutateAsync({ orderId, warehouse: parseInt(backflushWarehouse) });
    };

    const cardStyle: React.CSSProperties = {
        background: 'var(--color-surface, #fff)', border: '1px solid var(--color-border, #e2e8f0)',
        borderRadius: '12px', padding: '20px', marginBottom: '16px', boxShadow: '0 1px 2px rgba(0,0,0,0.05)',
    };
    const thStyle: React.CSSProperties = {
        padding: '10px 14px', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase',
        letterSpacing: '0.5px', color: 'var(--color-text-muted, #64748b)', textAlign: 'left',
        background: 'rgba(15,18,64,0.04)', borderBottom: '1.5px solid var(--color-border, #e2e8f0)',
    };
    const tdStyle: React.CSSProperties = {
        padding: '12px 14px', fontSize: '13px', borderBottom: '1px solid var(--color-border, #e2e8f0)',
    };
    const badgeStyle = (color: string, bg: string): React.CSSProperties => ({
        display: 'inline-flex', padding: '3px 10px', borderRadius: '6px',
        fontSize: '11px', fontWeight: 600, background: bg, color,
    });

    return (
        <div>
            {/* Backflush bar */}
            {isInProgress && hasRemaining && (
                <div style={{
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    padding: '14px 18px', borderRadius: '10px',
                    background: 'rgba(25,30,106,0.04)', border: '1px solid rgba(25,30,106,0.1)',
                    marginBottom: '16px',
                }}>
                    <span style={{ fontSize: '13px', fontWeight: 500, display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <Zap size={14} /> <strong>Quick Action:</strong> Issue all remaining BOM materials
                    </span>
                    <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                        <select value={backflushWarehouse} onChange={e => setBackflushWarehouse(e.target.value)} style={{ padding: '7px 12px', borderRadius: '6px', border: '2px solid var(--color-border)', fontSize: '12px', fontFamily: 'inherit' }}>
                            <option value="">Select warehouse...</option>
                            {warehouses.map((w: any) => <option key={w.id} value={w.id}>{w.name}</option>)}
                        </select>
                        <button onClick={handleBackflush} disabled={!backflushWarehouse || backflush.isPending} style={{
                            padding: '7px 18px', borderRadius: '6px', fontSize: '12px', fontWeight: 600,
                            border: 'none', cursor: 'pointer', fontFamily: 'inherit',
                            background: 'linear-gradient(135deg, #0f1240, #191e6a)', color: 'white',
                            opacity: !backflushWarehouse ? 0.5 : 1,
                        }}>
                            {backflush.isPending ? 'Issuing...' : 'Issue All Materials (Backflush)'}
                        </button>
                    </div>
                </div>
            )}

            {/* Requirements vs Issued */}
            <div style={cardStyle}>
                <h3 style={{ fontSize: '14px', fontWeight: 700, marginBottom: '14px' }}>Material Requirements vs Issued</h3>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead>
                        <tr>
                            <th style={thStyle}>Component</th>
                            <th style={thStyle}>Code</th>
                            <th style={thStyle}>Required</th>
                            <th style={thStyle}>Issued</th>
                            <th style={thStyle}>Remaining</th>
                            <th style={thStyle}>Status</th>
                        </tr>
                    </thead>
                    <tbody>
                        {reqs.map((r: any) => {
                            const issued = issuedByLine[r.bom_line_id] || 0;
                            const remaining = r.required_quantity - issued;
                            const isFull = remaining <= 0;
                            const isPartial = issued > 0 && remaining > 0;
                            return (
                                <tr key={r.bom_line_id}>
                                    <td style={{ ...tdStyle, fontWeight: 600 }}>{r.component_name}</td>
                                    <td style={{ ...tdStyle, color: 'var(--color-text-muted)', fontSize: '12px' }}>{r.component_code}</td>
                                    <td style={tdStyle}>{Number(r.required_quantity).toFixed(2)}</td>
                                    <td style={tdStyle}>{issued.toFixed(2)}</td>
                                    <td style={tdStyle}>{remaining > 0 ? remaining.toFixed(2) : '0.00'}</td>
                                    <td style={tdStyle}>
                                        {isFull && <span style={badgeStyle('#10b981', 'rgba(16,185,129,0.1)')}>Fully Issued</span>}
                                        {isPartial && <span style={badgeStyle('#f59e0b', 'rgba(245,158,11,0.1)')}>Partial</span>}
                                        {!isFull && !isPartial && <span style={badgeStyle('#64748b', 'rgba(100,116,139,0.1)')}>Not Issued</span>}
                                    </td>
                                </tr>
                            );
                        })}
                        {reqs.length === 0 && (
                            <tr><td colSpan={6} style={{ ...tdStyle, textAlign: 'center', color: 'var(--color-text-muted)' }}>No BOM lines found</td></tr>
                        )}
                    </tbody>
                </table>
            </div>

            {/* Manual Issue Form */}
            {isInProgress && (
                <div style={cardStyle}>
                    <h3 style={{ fontSize: '14px', fontWeight: 700, marginBottom: '14px' }}>+ Manual Material Issue</h3>
                    <form onSubmit={handleIssue} style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr auto', gap: '12px', alignItems: 'end' }}>
                        <div>
                            <label style={{ display: 'block', fontSize: '11px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px', color: 'var(--color-text-muted)', marginBottom: '6px' }}>Component</label>
                            <select value={issueForm.bom_line} onChange={e => setIssueForm({ ...issueForm, bom_line: e.target.value })} required style={{ width: '100%', padding: '9px 14px', borderRadius: '8px', border: '2px solid var(--color-border)', fontSize: '13px', fontFamily: 'inherit', background: 'var(--color-surface-hover, #f8fafc)' }}>
                                <option value="">Select component...</option>
                                {reqs.filter((r: any) => (r.required_quantity - (issuedByLine[r.bom_line_id] || 0)) > 0).map((r: any) => (
                                    <option key={r.bom_line_id} value={r.bom_line_id}>{r.component_code} — {r.component_name}</option>
                                ))}
                            </select>
                        </div>
                        <div>
                            <label style={{ display: 'block', fontSize: '11px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px', color: 'var(--color-text-muted)', marginBottom: '6px' }}>Quantity</label>
                            <input type="number" step="0.01" value={issueForm.quantity} onChange={e => setIssueForm({ ...issueForm, quantity: e.target.value })} required style={{ width: '100%', padding: '9px 14px', borderRadius: '8px', border: '2px solid var(--color-border)', fontSize: '13px', fontFamily: 'inherit', background: 'var(--color-surface-hover, #f8fafc)' }} />
                        </div>
                        <div>
                            <label style={{ display: 'block', fontSize: '11px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px', color: 'var(--color-text-muted)', marginBottom: '6px' }}>Warehouse</label>
                            <select value={issueForm.warehouse} onChange={e => setIssueForm({ ...issueForm, warehouse: e.target.value })} style={{ width: '100%', padding: '9px 14px', borderRadius: '8px', border: '2px solid var(--color-border)', fontSize: '13px', fontFamily: 'inherit', background: 'var(--color-surface-hover, #f8fafc)' }}>
                                <option value="">Select warehouse...</option>
                                {warehouses.map((w: any) => <option key={w.id} value={w.id}>{w.name}</option>)}
                            </select>
                        </div>
                        <button type="submit" disabled={createIssue.isPending} style={{ padding: '9px 18px', borderRadius: '8px', fontSize: '12px', fontWeight: 600, border: 'none', cursor: 'pointer', background: 'linear-gradient(135deg, #0f1240, #191e6a)', color: 'white', fontFamily: 'inherit', height: '38px' }}>
                            {createIssue.isPending ? 'Issuing...' : 'Issue'}
                        </button>
                    </form>
                </div>
            )}

            {/* Issue History */}
            <div style={cardStyle}>
                <h3 style={{ fontSize: '14px', fontWeight: 700, marginBottom: '14px' }}>Issue History</h3>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead>
                        <tr>
                            <th style={thStyle}>Date</th>
                            <th style={thStyle}>Component</th>
                            <th style={thStyle}>Qty Issued</th>
                            <th style={thStyle}>Notes</th>
                        </tr>
                    </thead>
                    <tbody>
                        {issues.map((iss: any) => (
                            <tr key={iss.id}>
                                <td style={tdStyle}>{iss.issue_date}</td>
                                <td style={{ ...tdStyle, fontWeight: 600 }}>
                                    {reqs.find((r: any) => r.bom_line_id === iss.bom_line)?.component_name || `Line #${iss.bom_line}`}
                                </td>
                                <td style={tdStyle}>{Number(iss.quantity_issued).toFixed(2)}</td>
                                <td style={{ ...tdStyle, color: 'var(--color-text-muted)', fontSize: '12px' }}>{iss.notes || '—'}</td>
                            </tr>
                        ))}
                        {issues.length === 0 && (
                            <tr><td colSpan={4} style={{ ...tdStyle, textAlign: 'center', color: 'var(--color-text-muted)' }}>No materials issued yet</td></tr>
                        )}
                    </tbody>
                </table>
            </div>
        </div>
    );
};

export default MaterialConsumptionTab;
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/features/production/pages/tabs/MaterialConsumptionTab.tsx
git commit -m "feat: add MaterialConsumptionTab with backflush, manual issue, and history"
```

---

## Task 11: Frontend — Build FinishedGoodsTab

**Files:**
- Create: `frontend/src/features/production/pages/tabs/FinishedGoodsTab.tsx`

- [ ] **Step 1: Create the component**

Create `frontend/src/features/production/pages/tabs/FinishedGoodsTab.tsx`:

```typescript
import { useState } from 'react';
import {
    useMaterialReceipts, useCreateMaterialReceipt, usePostMaterialReceiptToGL,
} from '../../hooks/useProduction';
import { useWarehouses } from '../../../inventory/hooks/useInventory';

interface Props {
    orderId: number;
    order: any;
}

const FinishedGoodsTab = ({ orderId, order }: Props) => {
    const { data: receiptsData } = useMaterialReceipts({ production_order: orderId });
    const { data: warehousesData } = useWarehouses();
    const createReceipt = useCreateMaterialReceipt();
    const postReceiptToGL = usePostMaterialReceiptToGL();

    const [form, setForm] = useState({ quantity_received: '', warehouse: '', receipt_date: new Date().toISOString().split('T')[0], scrap_quantity: '0', notes: '' });

    const receipts = receiptsData?.results || receiptsData || [];
    const warehouses = warehousesData?.results || warehousesData || [];

    const totalReceived = receipts.reduce((s: number, r: any) => s + parseFloat(r.quantity_received || 0), 0);
    const totalScrap = receipts.reduce((s: number, r: any) => s + parseFloat(r.scrap_quantity || 0), 0);
    const remaining = parseFloat(order.quantity_planned) - totalReceived;

    const canReceive = ['In Progress', 'Done'].includes(order.status);

    const handleReceive = async (e: React.FormEvent) => {
        e.preventDefault();
        const scrap = parseFloat(form.scrap_quantity) || 0;
        const result = await createReceipt.mutateAsync({
            production_order: orderId,
            quantity_received: parseFloat(form.quantity_received),
            receipt_date: form.receipt_date,
            is_scrap: scrap > 0,
            scrap_quantity: scrap,
            notes: form.notes,
        });
        try { await postReceiptToGL.mutateAsync(result.id); } catch {}
        setForm({ quantity_received: '', warehouse: '', receipt_date: new Date().toISOString().split('T')[0], scrap_quantity: '0', notes: '' });
    };

    const cardStyle: React.CSSProperties = {
        background: 'var(--color-surface, #fff)', border: '1px solid var(--color-border, #e2e8f0)',
        borderRadius: '12px', padding: '20px', marginBottom: '16px', boxShadow: '0 1px 2px rgba(0,0,0,0.05)',
    };
    const thStyle: React.CSSProperties = {
        padding: '10px 14px', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase',
        letterSpacing: '0.5px', color: 'var(--color-text-muted, #64748b)', textAlign: 'left',
        background: 'rgba(15,18,64,0.04)', borderBottom: '1.5px solid var(--color-border, #e2e8f0)',
    };
    const tdStyle: React.CSSProperties = {
        padding: '12px 14px', fontSize: '13px', borderBottom: '1px solid var(--color-border, #e2e8f0)',
    };

    const summaryCards = [
        { label: 'Planned', value: order.quantity_planned, color: '#0f172a' },
        { label: 'Received', value: totalReceived.toFixed(2), color: '#10b981' },
        { label: 'Remaining', value: remaining > 0 ? remaining.toFixed(2) : '0.00', color: '#f59e0b' },
        { label: 'Scrap', value: totalScrap.toFixed(2), color: '#ef4444' },
    ];

    return (
        <div>
            {/* Summary cards */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '14px', marginBottom: '16px' }}>
                {summaryCards.map(c => (
                    <div key={c.label} style={{ ...cardStyle, textAlign: 'center', marginBottom: 0 }}>
                        <div style={{ fontSize: '24px', fontWeight: 800, color: c.color, letterSpacing: '-0.5px' }}>{c.value}</div>
                        <div style={{ fontSize: '11px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px', color: 'var(--color-text-muted)', marginTop: '4px' }}>{c.label}</div>
                    </div>
                ))}
            </div>

            {/* Receive form */}
            {canReceive && (
                <div style={cardStyle}>
                    <h3 style={{ fontSize: '14px', fontWeight: 700, marginBottom: '14px' }}>+ Receive Finished Goods</h3>
                    <form onSubmit={handleReceive} style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr auto auto', gap: '12px', alignItems: 'end' }}>
                        <div>
                            <label style={{ display: 'block', fontSize: '11px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px', color: 'var(--color-text-muted)', marginBottom: '6px' }}>Quantity Received</label>
                            <input type="number" step="0.01" value={form.quantity_received} onChange={e => setForm({ ...form, quantity_received: e.target.value })} required style={{ width: '100%', padding: '9px 14px', borderRadius: '8px', border: '2px solid var(--color-border)', fontSize: '13px', fontFamily: 'inherit', background: 'var(--color-surface-hover, #f8fafc)' }} />
                        </div>
                        <div>
                            <label style={{ display: 'block', fontSize: '11px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px', color: 'var(--color-text-muted)', marginBottom: '6px' }}>Warehouse</label>
                            <select value={form.warehouse} onChange={e => setForm({ ...form, warehouse: e.target.value })} style={{ width: '100%', padding: '9px 14px', borderRadius: '8px', border: '2px solid var(--color-border)', fontSize: '13px', fontFamily: 'inherit', background: 'var(--color-surface-hover, #f8fafc)' }}>
                                <option value="">Select warehouse...</option>
                                {warehouses.map((w: any) => <option key={w.id} value={w.id}>{w.name}</option>)}
                            </select>
                        </div>
                        <div>
                            <label style={{ display: 'block', fontSize: '11px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px', color: 'var(--color-text-muted)', marginBottom: '6px' }}>Receipt Date</label>
                            <input type="date" value={form.receipt_date} onChange={e => setForm({ ...form, receipt_date: e.target.value })} style={{ width: '100%', padding: '9px 14px', borderRadius: '8px', border: '2px solid var(--color-border)', fontSize: '13px', fontFamily: 'inherit', background: 'var(--color-surface-hover, #f8fafc)' }} />
                        </div>
                        <div>
                            <label style={{ display: 'block', fontSize: '11px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px', color: 'var(--color-text-muted)', marginBottom: '6px' }}>Scrap Qty</label>
                            <input type="number" step="0.01" value={form.scrap_quantity} onChange={e => setForm({ ...form, scrap_quantity: e.target.value })} style={{ width: '80px', padding: '9px 14px', borderRadius: '8px', border: '2px solid var(--color-border)', fontSize: '13px', fontFamily: 'inherit', background: 'var(--color-surface-hover, #f8fafc)' }} />
                        </div>
                        <button type="submit" disabled={createReceipt.isPending} style={{ padding: '9px 18px', borderRadius: '8px', fontSize: '12px', fontWeight: 600, border: 'none', cursor: 'pointer', background: 'linear-gradient(135deg, #059669, #10b981)', color: 'white', fontFamily: 'inherit', height: '38px' }}>
                            {createReceipt.isPending ? 'Receiving...' : 'Receive'}
                        </button>
                    </form>
                </div>
            )}

            {/* Receipt history */}
            <div style={cardStyle}>
                <h3 style={{ fontSize: '14px', fontWeight: 700, marginBottom: '14px' }}>Receipt History</h3>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead>
                        <tr>
                            <th style={thStyle}>Date</th>
                            <th style={thStyle}>Qty Received</th>
                            <th style={thStyle}>Scrap</th>
                            <th style={thStyle}>Notes</th>
                        </tr>
                    </thead>
                    <tbody>
                        {receipts.map((r: any) => (
                            <tr key={r.id}>
                                <td style={tdStyle}>{r.receipt_date}</td>
                                <td style={{ ...tdStyle, fontWeight: 600 }}>{Number(r.quantity_received).toFixed(2)}</td>
                                <td style={tdStyle}>{Number(r.scrap_quantity || 0).toFixed(2)}</td>
                                <td style={{ ...tdStyle, color: 'var(--color-text-muted)', fontSize: '12px' }}>{r.notes || '—'}</td>
                            </tr>
                        ))}
                        {receipts.length === 0 && (
                            <tr><td colSpan={4} style={{ ...tdStyle, textAlign: 'center', color: 'var(--color-text-muted)' }}>No finished goods received yet</td></tr>
                        )}
                    </tbody>
                </table>
            </div>
        </div>
    );
};

export default FinishedGoodsTab;
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/features/production/pages/tabs/FinishedGoodsTab.tsx
git commit -m "feat: add FinishedGoodsTab with receive form, scrap tracking, receipt history"
```

---

## Task 12: Frontend — Build JobCardsTab

**Files:**
- Create: `frontend/src/features/production/pages/tabs/JobCardsTab.tsx`

- [ ] **Step 1: Create the component**

Create `frontend/src/features/production/pages/tabs/JobCardsTab.tsx`:

```typescript
import { useState } from 'react';
import {
    useJobCards, useCreateJobCard, useStartJobCard, useCompleteJobCard,
    useWorkCenters,
} from '../../hooks/useProduction';
import { Play, CheckCircle, Plus } from 'lucide-react';

interface Props {
    orderId: number;
    order: any;
}

const STATUS_BORDER: Record<string, string> = {
    Pending: '#94a3b8',
    'In Progress': '#3b82f6',
    Done: '#10b981',
};

const STATUS_BADGE: Record<string, { bg: string; color: string }> = {
    Pending: { bg: 'rgba(100,116,139,0.12)', color: '#64748b' },
    'In Progress': { bg: 'rgba(59,130,246,0.12)', color: '#3b82f6' },
    Done: { bg: 'rgba(16,185,129,0.12)', color: '#10b981' },
};

const JobCardsTab = ({ orderId, order }: Props) => {
    const { data: cardsData } = useJobCards({ production_order: orderId });
    const { data: workCentersData } = useWorkCenters();
    const createCard = useCreateJobCard();
    const startCard = useStartJobCard();
    const completeCard = useCompleteJobCard();

    const [showForm, setShowForm] = useState(false);
    const [form, setForm] = useState({ sequence: '', operation_name: '', work_center: '', time_planned: '', notes: '' });
    const [completeForm, setCompleteForm] = useState<{ id: number; time_actual: string; labor_cost: string } | null>(null);

    const cards = cardsData?.results || cardsData || [];
    const workCenters = workCentersData?.results || workCentersData || [];
    const canEdit = ['Draft', 'Scheduled', 'In Progress'].includes(order.status);

    const handleCreate = async (e: React.FormEvent) => {
        e.preventDefault();
        await createCard.mutateAsync({
            production_order: orderId,
            sequence: parseInt(form.sequence),
            operation_name: form.operation_name,
            work_center: parseInt(form.work_center),
            time_planned: parseFloat(form.time_planned),
            notes: form.notes,
        });
        setForm({ sequence: '', operation_name: '', work_center: '', time_planned: '', notes: '' });
        setShowForm(false);
    };

    const handleStart = async (id: number) => { await startCard.mutateAsync(id); };

    const handleComplete = async () => {
        if (!completeForm) return;
        await completeCard.mutateAsync({
            id: completeForm.id,
            time_actual: parseFloat(completeForm.time_actual) || 0,
            labor_cost: parseFloat(completeForm.labor_cost) || 0,
        });
        setCompleteForm(null);
    };

    const inputStyle: React.CSSProperties = { width: '100%', padding: '9px 14px', borderRadius: '8px', border: '2px solid var(--color-border)', fontSize: '13px', fontFamily: 'inherit', background: 'var(--color-surface-hover, #f8fafc)' };
    const labelStyle: React.CSSProperties = { display: 'block', fontSize: '11px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px', color: 'var(--color-text-muted)', marginBottom: '6px' };

    return (
        <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                <h3 style={{ fontSize: '14px', fontWeight: 700 }}>Operations</h3>
                {canEdit && (
                    <button onClick={() => setShowForm(!showForm)} style={{ padding: '7px 16px', borderRadius: '8px', fontSize: '12px', fontWeight: 600, border: '1.5px solid var(--color-border)', cursor: 'pointer', background: 'var(--color-surface, #fff)', color: 'var(--color-text-secondary)', fontFamily: 'inherit', display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                        <Plus size={14} /> Add Job Card
                    </button>
                )}
            </div>

            {/* Add form */}
            {showForm && (
                <div style={{ background: 'var(--color-surface, #fff)', border: '1px solid var(--color-border)', borderRadius: '12px', padding: '20px', marginBottom: '16px' }}>
                    <form onSubmit={handleCreate} style={{ display: 'grid', gridTemplateColumns: 'auto 1fr 1fr 1fr auto', gap: '12px', alignItems: 'end' }}>
                        <div>
                            <label style={labelStyle}>Seq #</label>
                            <input type="number" value={form.sequence} onChange={e => setForm({ ...form, sequence: e.target.value })} required style={{ ...inputStyle, width: '70px' }} />
                        </div>
                        <div>
                            <label style={labelStyle}>Operation Name</label>
                            <input value={form.operation_name} onChange={e => setForm({ ...form, operation_name: e.target.value })} required style={inputStyle} />
                        </div>
                        <div>
                            <label style={labelStyle}>Work Center</label>
                            <select value={form.work_center} onChange={e => setForm({ ...form, work_center: e.target.value })} required style={inputStyle}>
                                <option value="">Select...</option>
                                {workCenters.map((w: any) => <option key={w.id} value={w.id}>{w.name}</option>)}
                            </select>
                        </div>
                        <div>
                            <label style={labelStyle}>Planned Time (hrs)</label>
                            <input type="number" step="0.1" value={form.time_planned} onChange={e => setForm({ ...form, time_planned: e.target.value })} required style={inputStyle} />
                        </div>
                        <button type="submit" disabled={createCard.isPending} style={{ padding: '9px 18px', borderRadius: '8px', fontSize: '12px', fontWeight: 600, border: 'none', cursor: 'pointer', background: 'linear-gradient(135deg, #0f1240, #191e6a)', color: 'white', fontFamily: 'inherit', height: '38px' }}>
                            Add
                        </button>
                    </form>
                </div>
            )}

            {/* Job card grid */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '14px' }}>
                {cards.map((card: any) => {
                    const badge = STATUS_BADGE[card.status] || STATUS_BADGE.Pending;
                    return (
                        <div key={card.id} style={{ background: 'var(--color-surface, #fff)', border: '1px solid var(--color-border)', borderRadius: '12px', padding: '18px', borderLeft: `3px solid ${STATUS_BORDER[card.status] || '#94a3b8'}` }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                                    <div style={{ width: '30px', height: '30px', borderRadius: '8px', background: 'rgba(25,30,106,0.08)', color: '#191e6a', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '13px', fontWeight: 800 }}>{card.sequence}</div>
                                    <span style={{ padding: '3px 10px', borderRadius: '20px', fontSize: '10px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.5px', background: badge.bg, color: badge.color }}>{card.status}</span>
                                </div>
                            </div>
                            <div style={{ fontSize: '14px', fontWeight: 700, marginBottom: '10px' }}>{card.operation_name}</div>
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px', fontSize: '12px' }}>
                                <div><span style={{ fontSize: '10px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px', color: 'var(--color-text-muted)' }}>Work Center</span><div style={{ fontWeight: 600 }}>{card.work_center_name || '—'}</div></div>
                                <div><span style={{ fontSize: '10px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px', color: 'var(--color-text-muted)' }}>Operator</span><div style={{ fontWeight: 600 }}>{card.operator_name || 'Unassigned'}</div></div>
                                <div><span style={{ fontSize: '10px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px', color: 'var(--color-text-muted)' }}>Planned</span><div style={{ fontWeight: 600 }}>{card.time_planned} hrs</div></div>
                                <div><span style={{ fontSize: '10px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px', color: 'var(--color-text-muted)' }}>Actual</span><div style={{ fontWeight: 600, color: card.time_actual ? '#10b981' : 'var(--color-text-subtle)' }}>{card.time_actual ? `${card.time_actual} hrs` : '—'}</div></div>
                                {card.labor_cost > 0 && <div><span style={{ fontSize: '10px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px', color: 'var(--color-text-muted)' }}>Labor Cost</span><div style={{ fontWeight: 600 }}>${Number(card.labor_cost).toFixed(2)}</div></div>}
                            </div>

                            {/* Actions */}
                            {card.status === 'Pending' && (
                                <div style={{ marginTop: '12px', paddingTop: '12px', borderTop: '1px solid var(--color-border)' }}>
                                    <button onClick={() => handleStart(card.id)} style={{ padding: '6px 14px', borderRadius: '6px', fontSize: '11px', fontWeight: 600, border: 'none', cursor: 'pointer', background: 'linear-gradient(135deg, #0f1240, #191e6a)', color: 'white', fontFamily: 'inherit', display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                                        <Play size={12} /> Start
                                    </button>
                                </div>
                            )}
                            {card.status === 'In Progress' && completeForm?.id !== card.id && (
                                <div style={{ marginTop: '12px', paddingTop: '12px', borderTop: '1px solid var(--color-border)' }}>
                                    <button onClick={() => setCompleteForm({ id: card.id, time_actual: '', labor_cost: '' })} style={{ padding: '6px 14px', borderRadius: '6px', fontSize: '11px', fontWeight: 600, border: 'none', cursor: 'pointer', background: 'linear-gradient(135deg, #059669, #10b981)', color: 'white', fontFamily: 'inherit', display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                                        <CheckCircle size={12} /> Complete
                                    </button>
                                </div>
                            )}
                            {completeForm?.id === card.id && (
                                <div style={{ marginTop: '12px', paddingTop: '12px', borderTop: '1px solid var(--color-border)', display: 'flex', gap: '8px', alignItems: 'end' }}>
                                    <div>
                                        <label style={{ fontSize: '10px', fontWeight: 600, color: 'var(--color-text-muted)' }}>Actual Time (hrs)</label>
                                        <input type="number" step="0.1" value={completeForm.time_actual} onChange={e => setCompleteForm({ ...completeForm, time_actual: e.target.value })} style={{ width: '80px', padding: '5px 8px', borderRadius: '6px', border: '2px solid var(--color-border)', fontSize: '12px', fontFamily: 'inherit' }} />
                                    </div>
                                    <div>
                                        <label style={{ fontSize: '10px', fontWeight: 600, color: 'var(--color-text-muted)' }}>Labor Cost</label>
                                        <input type="number" step="0.01" value={completeForm.labor_cost} onChange={e => setCompleteForm({ ...completeForm, labor_cost: e.target.value })} style={{ width: '80px', padding: '5px 8px', borderRadius: '6px', border: '2px solid var(--color-border)', fontSize: '12px', fontFamily: 'inherit' }} />
                                    </div>
                                    <button onClick={handleComplete} style={{ padding: '5px 12px', borderRadius: '6px', fontSize: '11px', fontWeight: 600, border: 'none', cursor: 'pointer', background: '#10b981', color: 'white', fontFamily: 'inherit' }}>Done</button>
                                    <button onClick={() => setCompleteForm(null)} style={{ padding: '5px 12px', borderRadius: '6px', fontSize: '11px', fontWeight: 600, border: '1px solid var(--color-border)', cursor: 'pointer', background: 'var(--color-surface)', fontFamily: 'inherit' }}>Cancel</button>
                                </div>
                            )}
                        </div>
                    );
                })}
            </div>
            {cards.length === 0 && (
                <div style={{ textAlign: 'center', padding: '48px 0', color: 'var(--color-text-muted)' }}>
                    <div style={{ fontSize: '14px', fontWeight: 600, marginBottom: '6px' }}>No job cards yet</div>
                    <div style={{ fontSize: '13px' }}>Add job cards to track manufacturing operations</div>
                </div>
            )}
        </div>
    );
};

export default JobCardsTab;
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/features/production/pages/tabs/JobCardsTab.tsx
git commit -m "feat: add JobCardsTab with card grid, start/complete operations"
```

---

## Task 13: Frontend — Build BatchesTab

**Files:**
- Create: `frontend/src/features/production/pages/tabs/BatchesTab.tsx`

- [ ] **Step 1: Create the component**

Create `frontend/src/features/production/pages/tabs/BatchesTab.tsx`:

```typescript
import { useState } from 'react';
import { useBatches, useWarehouses, useSplitBatch, useTransferBatch } from '../../../inventory/hooks/useInventory';
import { useMaterialReceipts, useMaterialIssues } from '../../hooks/useProduction';

interface Props {
    orderId: number;
    order: any;
}

const BatchesTab = ({ orderId, order }: Props) => {
    const { data: batchesData } = useBatches();
    const { data: receiptsData } = useMaterialReceipts({ production_order: orderId });
    const { data: issuesData } = useMaterialIssues({ production_order: orderId });
    const { data: warehousesData } = useWarehouses();
    const splitBatch = useSplitBatch();
    const transferBatch = useTransferBatch();

    const [splitModal, setSplitModal] = useState<any>(null);
    const [transferModal, setTransferModal] = useState<any>(null);
    const [splitQty, setSplitQty] = useState('');
    const [transferQty, setTransferQty] = useState('');
    const [targetWarehouse, setTargetWarehouse] = useState('');

    const allBatches = batchesData?.results || batchesData || [];
    const warehouses = warehousesData?.results || warehousesData || [];

    // Batches created by this production order (match by reference pattern)
    const orderBatches = allBatches.filter((b: any) =>
        b.reference_number?.includes(order.order_number) || b.batch_number?.includes(order.order_number)
    );

    const handleSplit = async () => {
        if (!splitModal || !splitQty) return;
        await splitBatch.mutateAsync({ id: splitModal.id, split_quantity: parseFloat(splitQty) });
        setSplitModal(null);
        setSplitQty('');
    };

    const handleTransfer = async () => {
        if (!transferModal || !transferQty || !targetWarehouse) return;
        await transferBatch.mutateAsync({ id: transferModal.id, to_warehouse: parseInt(targetWarehouse), transfer_quantity: parseFloat(transferQty) });
        setTransferModal(null);
        setTransferQty('');
        setTargetWarehouse('');
    };

    const cardStyle: React.CSSProperties = {
        background: 'var(--color-surface, #fff)', border: '1px solid var(--color-border, #e2e8f0)',
        borderRadius: '12px', overflow: 'hidden', marginBottom: '16px',
    };
    const headerStyle: React.CSSProperties = {
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '16px 20px', borderBottom: '1px solid var(--color-border)', background: 'rgba(15,18,64,0.02)',
    };
    const thStyle: React.CSSProperties = {
        padding: '10px 14px', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase',
        letterSpacing: '0.5px', color: 'var(--color-text-muted)', textAlign: 'left',
        background: 'rgba(15,18,64,0.04)', borderBottom: '1.5px solid var(--color-border)',
    };
    const tdStyle: React.CSSProperties = {
        padding: '12px 14px', fontSize: '13px', borderBottom: '1px solid var(--color-border)',
    };
    const btnStyle: React.CSSProperties = {
        padding: '4px 10px', borderRadius: '6px', fontSize: '11px', fontWeight: 600,
        cursor: 'pointer', border: '1.5px solid var(--color-border)', background: 'var(--color-surface)',
        color: 'var(--color-text-secondary)', fontFamily: 'inherit', transition: 'all 0.15s',
    };
    const modalOverlay: React.CSSProperties = {
        position: 'fixed', inset: 0, background: 'rgba(15,23,42,0.55)', display: 'flex',
        alignItems: 'center', justifyContent: 'center', zIndex: 9999, backdropFilter: 'blur(2px)',
    };
    const modalBox: React.CSSProperties = {
        background: 'white', borderRadius: '16px', padding: '28px', maxWidth: '420px', width: '90%',
        boxShadow: '0 24px 64px rgba(0,0,0,0.25)',
    };
    const inputStyle: React.CSSProperties = {
        width: '100%', padding: '9px 14px', borderRadius: '8px', border: '2px solid var(--color-border)',
        fontSize: '13px', fontFamily: 'inherit', background: '#f8fafc',
    };

    const expiryBadge = (date: string) => {
        if (!date) return null;
        const days = Math.ceil((new Date(date).getTime() - Date.now()) / 86400000);
        const color = days <= 0 ? '#ef4444' : days <= 30 ? '#f59e0b' : '#10b981';
        const bg = days <= 0 ? 'rgba(239,68,68,0.1)' : days <= 30 ? 'rgba(245,158,11,0.1)' : 'rgba(16,185,129,0.1)';
        return <span style={{ padding: '3px 8px', borderRadius: '4px', fontSize: '11px', fontWeight: 600, background: bg, color }}>{date}</span>;
    };

    return (
        <div>
            {/* Batches created by this order */}
            <div style={cardStyle}>
                <div style={headerStyle}>
                    <h3 style={{ fontSize: '14px', fontWeight: 700 }}>Batches Created by This Order</h3>
                </div>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead>
                        <tr>
                            <th style={thStyle}>Batch #</th>
                            <th style={thStyle}>Item</th>
                            <th style={thStyle}>Warehouse</th>
                            <th style={thStyle}>Original</th>
                            <th style={thStyle}>Remaining</th>
                            <th style={thStyle}>Unit Cost</th>
                            <th style={thStyle}>Received</th>
                            <th style={thStyle}>Expiry</th>
                            <th style={thStyle}>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        {orderBatches.map((b: any) => (
                            <tr key={b.id}>
                                <td style={{ ...tdStyle, fontWeight: 700, color: '#191e6a' }}>{b.batch_number}</td>
                                <td style={tdStyle}>{b.item_name}</td>
                                <td style={tdStyle}>{b.warehouse_name}</td>
                                <td style={tdStyle}>{Number(b.quantity).toFixed(2)}</td>
                                <td style={tdStyle}>{Number(b.remaining_quantity).toFixed(2)}</td>
                                <td style={tdStyle}>${Number(b.unit_cost).toFixed(2)}</td>
                                <td style={tdStyle}>{b.receipt_date}</td>
                                <td style={tdStyle}>{expiryBadge(b.expiry_date)}</td>
                                <td style={tdStyle}>
                                    <div style={{ display: 'flex', gap: '4px' }}>
                                        <button style={btnStyle} onClick={() => setSplitModal(b)}>Split</button>
                                        <button style={btnStyle} onClick={() => setTransferModal(b)}>Transfer</button>
                                    </div>
                                </td>
                            </tr>
                        ))}
                        {orderBatches.length === 0 && (
                            <tr><td colSpan={9} style={{ ...tdStyle, textAlign: 'center', color: 'var(--color-text-muted)' }}>No batches created yet — receive finished goods to create batches</td></tr>
                        )}
                    </tbody>
                </table>
            </div>

            {/* Split Modal */}
            {splitModal && (
                <div style={modalOverlay} onClick={() => setSplitModal(null)}>
                    <div style={modalBox} onClick={e => e.stopPropagation()}>
                        <h3 style={{ fontSize: '16px', fontWeight: 700, marginBottom: '16px' }}>Split Batch</h3>
                        <p style={{ fontSize: '13px', color: 'var(--color-text-secondary)', marginBottom: '16px' }}>
                            Splitting <strong>{splitModal.batch_number}</strong> (remaining: {Number(splitModal.remaining_quantity).toFixed(2)})
                        </p>
                        <div style={{ marginBottom: '16px' }}>
                            <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, marginBottom: '6px' }}>Split Quantity</label>
                            <input type="number" step="0.01" value={splitQty} onChange={e => setSplitQty(e.target.value)} placeholder="Enter quantity to split off" style={inputStyle} />
                        </div>
                        <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
                            <button onClick={() => setSplitModal(null)} style={{ padding: '9px 20px', borderRadius: '8px', fontSize: '13px', fontWeight: 600, border: '1px solid var(--color-border)', cursor: 'pointer', background: '#f8fafc', color: 'var(--color-text-secondary)', fontFamily: 'inherit' }}>Cancel</button>
                            <button onClick={handleSplit} disabled={splitBatch.isPending} style={{ padding: '9px 20px', borderRadius: '8px', fontSize: '13px', fontWeight: 600, border: 'none', cursor: 'pointer', background: 'linear-gradient(135deg, #0f1240, #191e6a)', color: 'white', fontFamily: 'inherit' }}>
                                {splitBatch.isPending ? 'Splitting...' : 'Split'}
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* Transfer Modal */}
            {transferModal && (
                <div style={modalOverlay} onClick={() => setTransferModal(null)}>
                    <div style={modalBox} onClick={e => e.stopPropagation()}>
                        <h3 style={{ fontSize: '16px', fontWeight: 700, marginBottom: '16px' }}>Transfer Batch</h3>
                        <p style={{ fontSize: '13px', color: 'var(--color-text-secondary)', marginBottom: '16px' }}>
                            Transferring from <strong>{transferModal.batch_number}</strong> (remaining: {Number(transferModal.remaining_quantity).toFixed(2)})
                        </p>
                        <div style={{ marginBottom: '12px' }}>
                            <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, marginBottom: '6px' }}>Target Warehouse</label>
                            <select value={targetWarehouse} onChange={e => setTargetWarehouse(e.target.value)} style={inputStyle}>
                                <option value="">Select warehouse...</option>
                                {warehouses.filter((w: any) => w.id !== transferModal.warehouse).map((w: any) => (
                                    <option key={w.id} value={w.id}>{w.name}</option>
                                ))}
                            </select>
                        </div>
                        <div style={{ marginBottom: '16px' }}>
                            <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, marginBottom: '6px' }}>Transfer Quantity</label>
                            <input type="number" step="0.01" value={transferQty} onChange={e => setTransferQty(e.target.value)} placeholder="Enter quantity" style={inputStyle} />
                        </div>
                        <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
                            <button onClick={() => setTransferModal(null)} style={{ padding: '9px 20px', borderRadius: '8px', fontSize: '13px', fontWeight: 600, border: '1px solid var(--color-border)', cursor: 'pointer', background: '#f8fafc', color: 'var(--color-text-secondary)', fontFamily: 'inherit' }}>Cancel</button>
                            <button onClick={handleTransfer} disabled={transferBatch.isPending} style={{ padding: '9px 20px', borderRadius: '8px', fontSize: '13px', fontWeight: 600, border: 'none', cursor: 'pointer', background: 'linear-gradient(135deg, #0f1240, #191e6a)', color: 'white', fontFamily: 'inherit' }}>
                                {transferBatch.isPending ? 'Transferring...' : 'Transfer'}
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default BatchesTab;
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/features/production/pages/tabs/BatchesTab.tsx
git commit -m "feat: add BatchesTab with batch split and transfer modals"
```

---

## Task 14: Frontend — Build QualityTab

**Files:**
- Create: `frontend/src/features/production/pages/tabs/QualityTab.tsx`

- [ ] **Step 1: Create the component**

Create `frontend/src/features/production/pages/tabs/QualityTab.tsx`:

```typescript
import {
    useProductionQualityInspection, useCreateQualityInspectionFromProduction,
} from '../../hooks/useProduction';
import { Shield } from 'lucide-react';

interface Props {
    orderId: number;
    order: any;
}

const QualityTab = ({ orderId, order }: Props) => {
    const { data: inspection } = useProductionQualityInspection(orderId);
    const createInspection = useCreateQualityInspectionFromProduction();

    const requiresQI = order.bom_requires_quality_inspection;

    const handleCreate = async () => {
        await createInspection.mutateAsync(orderId);
    };

    if (!requiresQI) {
        return (
            <div style={{ textAlign: 'center', padding: '48px 0', color: 'var(--color-text-muted)' }}>
                <div style={{ fontSize: '48px', marginBottom: '12px' }}><Shield size={48} strokeWidth={1} /></div>
                <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '6px' }}>Quality Inspection Not Required</h3>
                <p style={{ fontSize: '13px' }}>This product does not require quality inspection. You can enable it in the BOM settings.</p>
            </div>
        );
    }

    if (!inspection) {
        return (
            <div style={{ textAlign: 'center', padding: '48px 0', color: 'var(--color-text-muted)' }}>
                <div style={{ fontSize: '48px', marginBottom: '12px' }}><Shield size={48} strokeWidth={1} /></div>
                <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '6px' }}>No Quality Inspection</h3>
                <p style={{ fontSize: '13px', marginBottom: '16px' }}>Create a quality inspection to verify production output before completion</p>
                <button onClick={handleCreate} disabled={createInspection.isPending} style={{
                    padding: '9px 20px', borderRadius: '8px', fontSize: '13px', fontWeight: 600,
                    border: 'none', cursor: 'pointer', fontFamily: 'inherit',
                    background: 'linear-gradient(135deg, #0f1240, #191e6a)', color: 'white',
                    boxShadow: '0 4px 12px rgba(15,18,64,0.3)',
                }}>
                    {createInspection.isPending ? 'Creating...' : '+ Create Quality Inspection'}
                </button>
            </div>
        );
    }

    // Show inspection details
    const statusColor = inspection.status === 'Pass' ? '#10b981' : inspection.status === 'Fail' ? '#ef4444' : '#f59e0b';

    return (
        <div>
            <div style={{
                background: 'var(--color-surface, #fff)', border: '1px solid var(--color-border)',
                borderRadius: '12px', padding: '20px', marginBottom: '16px',
            }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
                    <h3 style={{ fontSize: '14px', fontWeight: 700 }}>Quality Inspection: {inspection.inspection_number || `#${inspection.id}`}</h3>
                    <span style={{
                        padding: '5px 14px', borderRadius: '20px', fontSize: '11px', fontWeight: 700,
                        textTransform: 'uppercase', letterSpacing: '0.5px',
                        background: `${statusColor}1a`, color: statusColor,
                    }}>{inspection.status}</span>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '16px', fontSize: '13px' }}>
                    <div>
                        <div style={{ fontSize: '11px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px', color: 'var(--color-text-muted)', marginBottom: '4px' }}>Type</div>
                        <div style={{ fontWeight: 600 }}>{inspection.inspection_type || 'In-Process'}</div>
                    </div>
                    <div>
                        <div style={{ fontSize: '11px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px', color: 'var(--color-text-muted)', marginBottom: '4px' }}>Date</div>
                        <div style={{ fontWeight: 600 }}>{inspection.inspection_date || '—'}</div>
                    </div>
                    <div>
                        <div style={{ fontSize: '11px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px', color: 'var(--color-text-muted)', marginBottom: '4px' }}>Inspector</div>
                        <div style={{ fontWeight: 600 }}>{inspection.inspector_name || '—'}</div>
                    </div>
                </div>

                {inspection.notes && (
                    <div style={{ marginTop: '12px', padding: '10px 14px', borderRadius: '8px', background: 'var(--color-surface-hover, #f8fafc)', fontSize: '13px', color: 'var(--color-text-secondary)' }}>
                        {inspection.notes}
                    </div>
                )}

                <div style={{ marginTop: '16px', paddingTop: '12px', borderTop: '1px solid var(--color-border)', fontSize: '12px', color: 'var(--color-text-muted)' }}>
                    To edit inspection details, manage this inspection in the <strong>Quality</strong> module.
                </div>
            </div>
        </div>
    );
};

export default QualityTab;
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/features/production/pages/tabs/QualityTab.tsx
git commit -m "feat: add QualityTab with conditional display based on BOM toggle"
```

---

## Task 15: Frontend — Enhance BatchList with create, split, transfer

**Files:**
- Modify: `frontend/src/features/inventory/pages/BatchList.tsx`

- [ ] **Step 1: Add imports for new hooks**

Update line 2 of `BatchList.tsx`:

From:
```typescript
import { useBatches, useItems, useWarehouses, useDeleteBatch } from '../hooks/useInventory';
```
To:
```typescript
import { useBatches, useItems, useWarehouses, useDeleteBatch, useCreateBatch, useSplitBatch, useTransferBatch } from '../hooks/useInventory';
```

Add `Plus, Scissors, ArrowRightLeft` to the lucide imports (line 5):
```typescript
import { Package, Calendar, MapPin, Trash2, Plus, Scissors, ArrowRightLeft } from 'lucide-react';
```

- [ ] **Step 2: Add hooks and state inside component**

After line 15 (`const [confirmDelete, setConfirmDelete] = useState<number | null>(null);`), add:

```typescript
    const createBatch = useCreateBatch();
    const splitBatch = useSplitBatch();
    const transferBatch = useTransferBatch();
    const [showCreate, setShowCreate] = useState(false);
    const [createForm, setCreateForm] = useState({ item: '', batch_number: '', warehouse: '', quantity: '', unit_cost: '', receipt_date: new Date().toISOString().split('T')[0], expiry_date: '', reference_number: '' });
    const [splitModal, setSplitModal] = useState<any>(null);
    const [splitQty, setSplitQty] = useState('');
    const [transferModal, setTransferModal] = useState<any>(null);
    const [transferQty, setTransferQty] = useState('');
    const [targetWarehouse, setTargetWarehouse] = useState('');
```

- [ ] **Step 3: Add handler functions**

After the `isExpired` function, add:

```typescript
    const handleCreateBatch = async (e: React.FormEvent) => {
        e.preventDefault();
        await createBatch.mutateAsync({
            item: parseInt(createForm.item),
            batch_number: createForm.batch_number,
            warehouse: parseInt(createForm.warehouse),
            quantity: parseFloat(createForm.quantity),
            remaining_quantity: parseFloat(createForm.quantity),
            unit_cost: parseFloat(createForm.unit_cost),
            receipt_date: createForm.receipt_date,
            expiry_date: createForm.expiry_date || null,
            reference_number: createForm.reference_number,
        });
        setCreateForm({ item: '', batch_number: '', warehouse: '', quantity: '', unit_cost: '', receipt_date: new Date().toISOString().split('T')[0], expiry_date: '', reference_number: '' });
        setShowCreate(false);
    };

    const handleSplit = async () => {
        if (!splitModal || !splitQty) return;
        await splitBatch.mutateAsync({ id: splitModal.id, split_quantity: parseFloat(splitQty) });
        setSplitModal(null);
        setSplitQty('');
    };

    const handleTransfer = async () => {
        if (!transferModal || !transferQty || !targetWarehouse) return;
        await transferBatch.mutateAsync({ id: transferModal.id, to_warehouse: parseInt(targetWarehouse), transfer_quantity: parseFloat(transferQty) });
        setTransferModal(null);
        setTransferQty('');
        setTargetWarehouse('');
    };
```

- [ ] **Step 4: Add "New Batch" button next to header**

Find the page header area (search for "Batches" heading in the JSX) and add a "New Batch" button next to it:

```typescript
<button onClick={() => setShowCreate(true)} style={{ padding: '0.5rem 1rem', borderRadius: '8px', fontSize: '13px', fontWeight: 600, border: 'none', cursor: 'pointer', background: 'linear-gradient(135deg, #0f1240, #191e6a)', color: 'white', fontFamily: 'inherit', display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
    <Plus size={14} /> New Batch
</button>
```

- [ ] **Step 5: Add Split and Transfer buttons to each batch row's action area**

In the actions column of the batch table (near the delete button), add before the delete button:

```typescript
<button onClick={(e) => { e.stopPropagation(); setSplitModal(batch); }} style={{ background: 'none', border: '1px solid var(--color-border)', borderRadius: '6px', padding: '4px 8px', cursor: 'pointer', fontSize: '11px', fontWeight: 600, color: 'var(--color-text-secondary)', fontFamily: 'inherit' }} title="Split Batch">
    <Scissors size={12} />
</button>
<button onClick={(e) => { e.stopPropagation(); setTransferModal(batch); }} style={{ background: 'none', border: '1px solid var(--color-border)', borderRadius: '6px', padding: '4px 8px', cursor: 'pointer', fontSize: '11px', fontWeight: 600, color: 'var(--color-text-secondary)', fontFamily: 'inherit' }} title="Transfer Batch">
    <ArrowRightLeft size={12} />
</button>
```

- [ ] **Step 6: Add create form modal, split modal, and transfer modal JSX**

Add before the closing `</div>` of the component — the same split and transfer modal patterns used in `BatchesTab.tsx`, plus a create form modal with fields for item, batch_number, warehouse, quantity, unit_cost, receipt_date, expiry_date, reference_number.

The create modal should follow the existing modal pattern in the codebase (fixed overlay + centered white card). Form fields use the same inline style tokens as `VendorInvoiceForm.tsx`.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/features/inventory/pages/BatchList.tsx
git commit -m "feat: enhance BatchList with create, split, and transfer batch capabilities"
```

---

## Task 16: Build and verify

- [ ] **Step 1: Build frontend**

```bash
cd "c:/Users/USER/Documents/Antigravity/DTSG erp/frontend"
npm run build
```

Fix any TypeScript errors that arise.

- [ ] **Step 2: Verify Django server starts**

```bash
cd "c:/Users/USER/Documents/Antigravity/DTSG erp"
python manage.py check
```

Expected: `System check identified no issues`

- [ ] **Step 3: Start dev server and test navigation**

```bash
cd "c:/Users/USER/Documents/Antigravity/DTSG erp/frontend"
npm run dev
```

Manually verify:
- Navigate to `/production/orders` → click an order → detail page loads
- All 5 tabs render without errors
- Materials tab shows BOM requirements
- BOM form shows "Requires Quality Inspection" checkbox
- Sidebar shows "Batch Management" instead of "Batches / Lots"

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "fix: resolve any build issues from production order detail implementation"
```
