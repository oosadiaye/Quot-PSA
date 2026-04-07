import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '../../../api/client';

// ============================================================================
// PAYLOAD INTERFACES
// ============================================================================

export interface ItemPayload {
    sku: string;
    name: string;
    description?: string;
    product_type?: number;
    product_category?: number;
    category?: number;
    unit_of_measure: string;
    valuation_method?: string;
    selling_price?: number;
    total_quantity?: number;
    total_value?: number;
    reorder_point?: number;
    reorder_quantity?: number;
    barcode?: string;
    min_stock?: number;
    max_stock?: number;
    is_active?: boolean;
    inventory_account?: number;
    expense_account?: number;
}

export interface StockMovementPayload {
    item: number;
    warehouse: number;
    movement_type: string;
    quantity: number;
    unit_price: number;
    batch?: number;
    to_warehouse?: number;
    reference_number?: string;
    remarks?: string;
    cost_method?: string;
}

export interface StockTransferPayload {
    item: number;
    from_warehouse: number;
    to_warehouse: number;
    quantity: number;
    unit_price: number;
    reference_number?: string;
    remarks?: string;
}

export interface ReconciliationPayload {
    reconciliation_type: string;
    warehouse: number;
    reconciliation_date: string;
    status?: string;
    notes?: string;
}

export interface WarehousePayload {
    name: string;
    location?: string;
    is_active?: boolean;
    is_central?: boolean;
}

export interface ProductCategoryPayload {
    name: string;
    product_type: number;
    parent?: number;
}

export interface SerialNumberPayload {
    item: number;
    serial_number: string;
    batch?: number;
    status?: string;
    warehouse?: number;
    purchase_date?: string;
    purchase_price?: number;
    sale_date?: string;
    sales_order_line?: number;
    warranty_start?: string;
    warranty_end?: string;
    current_location?: string;
    notes?: string;
}

const STALE_TIME      = 5 * 60 * 1000;  // 5 min — mostly-static reference data (warehouses, categories)
const LIVE_STALE_TIME = 30 * 1000;       // 30 s — transactional data (movements, alerts, reconciliations)

export const useWarehouses = () => {
    return useQuery({
        queryKey: ['warehouses'],
        queryFn: async () => {
            const { data } = await apiClient.get('/inventory/warehouses/');
            return data;
        },
        staleTime: STALE_TIME,
    });
};

export const useItemCategories = () => {
    return useQuery({
        queryKey: ['inventory-categories'],
        queryFn: async () => {
            const { data } = await apiClient.get('/inventory/categories/');
            return data;
        },
        staleTime: STALE_TIME,
    });
};

export const useItems = (filters = {}) => {
    return useQuery({
        queryKey: ['items', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/inventory/items/', { params: filters });
            return data;
        },
        staleTime: LIVE_STALE_TIME,
        refetchOnWindowFocus: true,
    });
};

export const useItem = (id?: number) => {
    return useQuery({
        queryKey: ['inventory-item', id],
        queryFn: async () => {
            if (!id || isNaN(id)) return null;
            const { data } = await apiClient.get(`/inventory/items/${id}/`);
            return data;
        },
        enabled: Boolean(id) && !isNaN(id as number),
        staleTime: STALE_TIME,
    });
};

export const useCreateItem = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (payload: ItemPayload) => {
            const { data } = await apiClient.post('/inventory/items/', payload);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['items'] });
        },
    });
};

export const useStockByWarehouse = (itemId: number) => {
    return useQuery({
        queryKey: ['inventory-stock', itemId],
        queryFn: async () => {
            const { data } = await apiClient.get(`/inventory/items/${itemId}/stock_by_warehouse/`);
            return data;
        },
        staleTime: LIVE_STALE_TIME,
        refetchOnWindowFocus: true,
        enabled: itemId > 0,
    });
};

export const useItemBatches = (itemId: number) => {
    return useQuery({
        queryKey: ['inventory-batches', itemId],
        queryFn: async () => {
            const { data } = await apiClient.get(`/inventory/items/${itemId}/batches/`);
            return data;
        },
        staleTime: STALE_TIME,
    });
};

export const useStockValuation = (params: { product_type?: string; category?: string } = {}) => {
    return useQuery({
        queryKey: ['inventory-valuation', params],
        queryFn: async () => {
            const { data } = await apiClient.get('/inventory/items/stock_valuation/', {
                params: Object.fromEntries(
                    Object.entries(params).filter(([, v]) => v !== '' && v !== undefined)
                ),
            });
            return data;
        },
        staleTime: 0,                  // always consider stale — refetch on every mount/focus
        refetchOnWindowFocus: true,    // refresh when user switches back to the tab
        refetchInterval: 30_000,       // background poll every 30 s
    });
};

export const useReorderAlerts = (options: { refetchInterval?: number } = {}) => {
    return useQuery({
        queryKey: ['inventory-reorder-alerts'],
        queryFn: async () => {
            const { data } = await apiClient.get('/inventory/reorder-alerts/');
            return data;
        },
        staleTime: LIVE_STALE_TIME,
        refetchOnWindowFocus: true,
        refetchInterval: options.refetchInterval ?? 60_000,
        ...options,
    });
};

export const useGenerateReorderAlerts = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async () => {
            const { data } = await apiClient.post('/inventory/reorder-alerts/generate_alerts/');
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['inventory-reorder-alerts'] });
        },
    });
};

export const useStockMovements = (filters = {}) => {
    return useQuery({
        queryKey: ['stock-movements', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/inventory/movements/', { params: filters });
            return data;
        },
        staleTime: LIVE_STALE_TIME,
        refetchOnWindowFocus: true,
        refetchInterval: 30_000,
    });
};

export const useCreateStockMovement = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (movementData: StockMovementPayload) => {
            const { data } = await apiClient.post('/inventory/movements/', movementData);
            return data;
        },
        // FIX #23: invalidate both the list key ['inventory-stocks'] AND the
        // per-item key ['inventory-stock', itemId] so useStockByWarehouse() updates.
        onSuccess: (_data, variables) => {
            queryClient.invalidateQueries({ queryKey: ['items'] });
            queryClient.invalidateQueries({ queryKey: ['stock-movements'] });
            queryClient.invalidateQueries({ queryKey: ['inventory-stocks'] });
            queryClient.invalidateQueries({ queryKey: ['inventory-stock', variables.item] });
        },
    });
};

export const useStockTransfer = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (payload: StockTransferPayload) => {
            const { data } = await apiClient.post('/inventory/movements/transfer/', payload);
            return data;
        },
        // FIX #23: also invalidate inventory-stocks list and per-item stock.
        onSuccess: (_data, variables) => {
            queryClient.invalidateQueries({ queryKey: ['stock-movements'] });
            queryClient.invalidateQueries({ queryKey: ['items'] });
            queryClient.invalidateQueries({ queryKey: ['inventory-stocks'] });
            queryClient.invalidateQueries({ queryKey: ['inventory-stock', variables.item] });
        },
    });
};

export const useReceiveTransfer = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            const { data } = await apiClient.post(`/inventory/movements/${id}/receive/`);
            return data;
        },
        // FIX #23: also invalidate all per-item stock queries (prefix match)
        // since the movement id alone doesn't tell us which item was affected.
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['stock-movements'] });
            queryClient.invalidateQueries({ queryKey: ['items'] });
            queryClient.invalidateQueries({ queryKey: ['inventory-stocks'] });
            queryClient.invalidateQueries({ queryKey: ['inventory-stock'] }); // prefix match
        },
    });
};

export const useStockByWarehouseList = () => {
    return useQuery({
        queryKey: ['inventory-stocks'],
        queryFn: async () => {
            const { data } = await apiClient.get('/inventory/stocks/');
            return data;
        },
        staleTime: LIVE_STALE_TIME,
        refetchOnWindowFocus: true,
        refetchInterval: 30_000,
    });
};

export const useBatches = (filters = {}) => {
    return useQuery({
        queryKey: ['inventory-batches', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/inventory/batches/', { params: filters });
            return data;
        },
        staleTime: STALE_TIME,
    });
};

export const useReconciliations = () => {
    return useQuery({
        queryKey: ['inventory-reconciliations'],
        queryFn: async () => {
            const { data } = await apiClient.get('/inventory/reconciliations/');
            return data;
        },
        staleTime: LIVE_STALE_TIME,
        refetchOnWindowFocus: true,
    });
};

export const useCreateReconciliation = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (payload: ReconciliationPayload) => {
            const { data } = await apiClient.post('/inventory/reconciliations/', payload);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['inventory-reconciliations'] });
        },
    });
};

export const useCompleteReconciliation = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            const { data } = await apiClient.post(`/inventory/reconciliations/${id}/adjust/`);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['inventory-reconciliations'] });
            queryClient.invalidateQueries({ queryKey: ['inventory-stocks'] });
            queryClient.invalidateQueries({ queryKey: ['inventory-stock'] }); // prefix match — all per-item keys
            queryClient.invalidateQueries({ queryKey: ['items'] });
            queryClient.invalidateQueries({ queryKey: ['stock-movements'] });
            queryClient.invalidateQueries({ queryKey: ['inventory-valuation'] });
            queryClient.invalidateQueries({ queryKey: ['journals'] });
        },
    });
};

export const useAddReconciliationLine = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (payload: { recId: number; item: number; physical_quantity: number; reason?: string }) => {
            const { recId, ...body } = payload;
            const { data } = await apiClient.post(`/inventory/reconciliations/${recId}/add_line/`, body);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['inventory-reconciliations'] });
        },
    });
};

export const usePopulateReconciliation = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            const { data } = await apiClient.post(`/inventory/reconciliations/${id}/populate_items/`);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['inventory-reconciliations'] });
        },
    });
};

export const useStartReconciliation = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            const { data } = await apiClient.post(`/inventory/reconciliations/${id}/start/`);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['inventory-reconciliations'] });
        },
    });
};

export const useUpdateReconciliationLine = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (payload: { recId: number; lineId: number; physical_quantity: number; reason?: string }) => {
            const { recId, lineId, ...body } = payload;
            const { data } = await apiClient.post(`/inventory/reconciliations/${recId}/update_line/`, {
                line_id: lineId,
                ...body,
            });
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['inventory-reconciliations'] });
        },
    });
};

export const useCreateWarehouse = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (payload: WarehousePayload) => {
            const { data } = await apiClient.post('/inventory/warehouses/', payload);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['warehouses'] });
        },
    });
};

export const useUpdateWarehouse = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, data }: { id: number; data: Partial<WarehousePayload> }) => {
            const { data: response } = await apiClient.patch(`/inventory/warehouses/${id}/`, data);
            return response;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['warehouses'] });
        },
    });
};

export const useDeleteWarehouse = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            await apiClient.delete(`/inventory/warehouses/${id}/`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['warehouses'] });
        },
    });
};

export const useProductTypes = () => {
    return useQuery({
        queryKey: ['product-types'],
        queryFn: async () => {
            const { data } = await apiClient.get('/inventory/product-types/');
            // Always return a plain array — unpack DRF paginated envelope if present
            return Array.isArray(data) ? data : (data?.results ?? []);
        },
        staleTime: STALE_TIME,   // product types change rarely — 5 min is fine
        refetchOnWindowFocus: true,
    });
};

export const useProductCategories = (productType?: string) => {
    return useQuery({
        queryKey: ['product-categories', productType],
        queryFn: async () => {
            const params = productType ? { product_type: productType } : {};
            const { data } = await apiClient.get('/inventory/product-categories/', { params });
            return data;
        },
        staleTime: STALE_TIME,
    });
};

export const useCreateProductCategory = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (payload: ProductCategoryPayload) => {
            const { data } = await apiClient.post('/inventory/product-categories/', payload);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['product-categories'] });
        },
    });
};

export const useUpdateProductCategory = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, data }: { id: number; data: Partial<ProductCategoryPayload> }) => {
            const { data: response } = await apiClient.patch(`/inventory/product-categories/${id}/`, data);
            return response;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['product-categories'] });
        },
    });
};

export const useDeleteProductCategory = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            await apiClient.delete(`/inventory/product-categories/${id}/`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['product-categories'] });
        },
    });
};

export const useSerialNumbers = (filters = {}) => {
    return useQuery({
        queryKey: ['serial-numbers', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/inventory/serial-numbers/', { params: filters });
            return data;
        },
        staleTime: STALE_TIME,
    });
};

export const useCreateSerialNumber = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (payload: SerialNumberPayload) => {
            const { data } = await apiClient.post('/inventory/serial-numbers/', payload);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['serial-numbers'] });
        },
    });
};

export const useDeleteSerialNumber = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            await apiClient.delete(`/inventory/serial-numbers/${id}/`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['serial-numbers'] });
        },
    });
};

export const useExpiryAlerts = (options: { refetchInterval?: number } = {}) => {
    return useQuery({
        queryKey: ['expiry-alerts'],
        queryFn: async () => {
            const { data } = await apiClient.get('/inventory/expiry-alerts/');
            return data;
        },
        staleTime: LIVE_STALE_TIME,
        refetchOnWindowFocus: true,
        refetchInterval: options.refetchInterval ?? 60_000,
        ...options,
    });
};

export const useGenerateExpiryAlerts = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async () => {
            const { data } = await apiClient.post('/inventory/expiry-alerts/generate_expiry_alerts/');
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['expiry-alerts'] });
        },
    });
};

export const useUpdateItem = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, data }: { id: number; data: Partial<ItemPayload> }) => {
            const { data: response } = await apiClient.patch(`/inventory/items/${id}/`, data);
            return response;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['items'] });
        },
    });
};

export const useDeleteItem = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            await apiClient.delete(`/inventory/items/${id}/`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['items'] });
        },
    });
};

export const useDeleteBatch = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            await apiClient.delete(`/inventory/batches/${id}/`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['inventory-batches'] });
        },
    });
};

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
        // FIX #22: prefix-match invalidation covers all ['inventory-stock', itemId] keys
        // since the batch payload does not include item id.
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['inventory-batches'] });
            queryClient.invalidateQueries({ queryKey: ['inventory-stocks'] });
            queryClient.invalidateQueries({ queryKey: ['inventory-stock'] }); // prefix match
            queryClient.invalidateQueries({ queryKey: ['stock-movements'] });
        },
    });
};

export const useDeleteReorderAlert = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            await apiClient.delete(`/inventory/reorder-alerts/${id}/`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['inventory-reorder-alerts'] });
        },
    });
};

export const useDeleteStockMovement = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            await apiClient.delete(`/inventory/movements/${id}/`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['stock-movements'] });
            queryClient.invalidateQueries({ queryKey: ['items'] });
        },
    });
};

// ─── Inventory Settings ───────────────────────────────────────────────────────

export interface InventorySettingsPayload {
    auto_po_enabled?: boolean;
    auto_po_draft_only?: boolean;
}

export const useInventorySettings = () => {
    return useQuery({
        queryKey: ['inventory-settings'],
        queryFn: async () => {
            const { data } = await apiClient.get('/inventory/settings/');
            return data;
        },
        staleTime: 0,
    });
};

export const useUpdateInventorySettings = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (payload: InventorySettingsPayload) => {
            const { data } = await apiClient.patch('/inventory/settings/', payload);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['inventory-settings'] });
        },
    });
};
