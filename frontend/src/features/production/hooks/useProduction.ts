import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '../../../api/client';

// ============================================================================
// PAYLOAD INTERFACES
// ============================================================================

export interface WorkCenterPayload {
    name: string;
    code: string;
    description?: string;
    capacity_hours: number;
    efficiency?: number;
    labor_rate?: number;
    overhead_rate?: number;
    is_active?: boolean;
}

export interface BillOfMaterialsPayload {
    item_code: string;
    item_name: string;
    item_type: string;
    unit: string;
    standard_cost?: number;
    is_active?: boolean;
}

export interface BOMLinePayload {
    bom: number;
    component: number;
    quantity: number;
    unit: string;
    scrap_percentage?: number;
    notes?: string;
}

export interface ProductionOrderPayload {
    order_number: string;
    bom: number;
    quantity_planned: number;
    quantity_produced?: number;
    start_date: string;
    end_date?: string | null;
    status?: string;
    work_center?: number | null;
    notes?: string;
}

export interface MaterialIssuePayload {
    production_order: number;
    bom_line: number;
    quantity_issued: number;
    issue_date: string;
    notes?: string;
}

export interface MaterialReceiptPayload {
    production_order: number;
    quantity_received: number;
    receipt_date: string;
    is_scrap?: boolean;
    scrap_quantity?: number;
    notes?: string;
}

export interface JobCardPayload {
    production_order: number;
    work_center: number;
    sequence: number;
    operation_name: string;
    time_planned: number;
    time_actual?: number;
    labor_cost?: number;
    operator?: number | null;
    status?: string;
    notes?: string;
}

export interface RoutingPayload {
    bom: number;
    sequence: number;
    operation_name: string;
    work_center: number;
    time_hours: number;
    labor_cost?: number;
    notes?: string;
}

const STALE_TIME = 5 * 60 * 1000;

// ============================================================================
// WORK CENTER HOOKS
// ============================================================================

export const useWorkCenters = (filters = {}) => {
    return useQuery({
        queryKey: ['production-work-centers', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/production/work-centers/', { params: filters });
            return data;
        },
        staleTime: STALE_TIME,
    });
};

export const useWorkCenter = (id?: number) => {
    return useQuery({
        queryKey: ['production-work-center', id],
        queryFn: async () => {
            if (!id || isNaN(id)) return null;
            const { data } = await apiClient.get(`/production/work-centers/${id}/`);
            return data;
        },
        enabled: Boolean(id) && !isNaN(id),
        staleTime: STALE_TIME,
    });
};

export const useCreateWorkCenter = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (payload: WorkCenterPayload) => {
            const { data } = await apiClient.post('/production/work-centers/', payload);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['production-work-centers'] });
        },
    });
};

export const useUpdateWorkCenter = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, data }: { id: number; data: Partial<WorkCenterPayload> }) => {
            const { data: result } = await apiClient.patch(`/production/work-centers/${id}/`, data);
            return result;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['production-work-centers'] });
        },
    });
};

export const useDeleteWorkCenter = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            await apiClient.delete(`/production/work-centers/${id}/`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['production-work-centers'] });
        },
    });
};

// ============================================================================
// BILL OF MATERIALS HOOKS
// ============================================================================

export const useBillOfMaterials = (filters = {}) => {
    return useQuery({
        queryKey: ['production-boms', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/production/bills-of-materials/', { params: filters });
            return data;
        },
        staleTime: STALE_TIME,
    });
};

export const useBillOfMaterialsWithLines = (filters = {}) => {
    return useQuery({
        queryKey: ['production-boms-full', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/production/bills-of-materials/', { 
                params: { ...filters, include_lines: true } 
            });
            return data;
        },
        staleTime: STALE_TIME,
    });
};

export const useBOM = (id?: number) => {
    return useQuery({
        queryKey: ['production-bom', id],
        queryFn: async () => {
            if (!id || isNaN(id)) return null;
            const { data } = await apiClient.get(`/production/bills-of-materials/${id}/`);
            return data;
        },
        enabled: Boolean(id) && !isNaN(id),
        staleTime: STALE_TIME,
    });
};

export const useCreateBOM = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (payload: BillOfMaterialsPayload) => {
            const { data } = await apiClient.post('/production/bills-of-materials/', payload);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['production-boms'] });
            queryClient.invalidateQueries({ queryKey: ['production-boms-full'] });
        },
    });
};

export const useUpdateBOM = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, data }: { id: number; data: Partial<BillOfMaterialsPayload> }) => {
            const { data: result } = await apiClient.patch(`/production/bills-of-materials/${id}/`, data);
            return result;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['production-boms'] });
            queryClient.invalidateQueries({ queryKey: ['production-boms-full'] });
        },
    });
};

export const useDeleteBOM = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            await apiClient.delete(`/production/bills-of-materials/${id}/`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['production-boms'] });
            queryClient.invalidateQueries({ queryKey: ['production-boms-full'] });
        },
    });
};

// ============================================================================
// BOM LINE HOOKS
// ============================================================================

export const useBOMLines = (bomId?: number) => {
    return useQuery({
        queryKey: ['production-bom-lines', bomId],
        queryFn: async () => {
            if (!bomId || isNaN(bomId)) return [];
            const { data } = await apiClient.get('/production/bom-lines/', { params: { bom: bomId } });
            return data;
        },
        enabled: Boolean(bomId) && !isNaN(bomId),
        staleTime: STALE_TIME,
    });
};

export const useCreateBOMLine = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ bomId, payload }: { bomId: number; payload: BOMLinePayload }) => {
            const { data } = await apiClient.post('/production/bom-lines/', payload);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['production-bom-lines'] });
        },
    });
};

export const useDeleteBOMLine = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ bomId, lineId }: { bomId: number; lineId: number }) => {
            await apiClient.delete(`/production/bom-lines/${lineId}/`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['production-bom-lines'] });
        },
    });
};

// ============================================================================
// PRODUCTION ORDER HOOKS
// ============================================================================

export const useProductionOrders = (filters = {}) => {
    return useQuery({
        queryKey: ['production-orders', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/production/production-orders/', { params: filters });
            return data;
        },
        staleTime: STALE_TIME,
    });
};

export const useProductionOrder = (id?: number) => {
    return useQuery({
        queryKey: ['production-order', id],
        queryFn: async () => {
            if (!id || isNaN(id)) return null;
            const { data } = await apiClient.get(`/production/production-orders/${id}/`);
            return data;
        },
        enabled: Boolean(id) && !isNaN(id),
        staleTime: STALE_TIME,
    });
};

export const useCreateProductionOrder = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (payload: ProductionOrderPayload) => {
            const { data } = await apiClient.post('/production/production-orders/', payload);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['production-orders'] });
        },
    });
};

export const useUpdateProductionOrder = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, data }: { id: number; data: Partial<ProductionOrderPayload> }) => {
            const { data: result } = await apiClient.patch(`/production/production-orders/${id}/`, data);
            return result;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['production-orders'] });
            queryClient.invalidateQueries({ queryKey: ['production-order'] });
        },
    });
};

export const useDeleteProductionOrder = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            await apiClient.delete(`/production/production-orders/${id}/`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['production-orders'] });
        },
    });
};

export const useScheduleProduction = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, start_date, end_date }: { id: number; start_date: string; end_date?: string }) => {
            const { data } = await apiClient.post(`/production/production-orders/${id}/schedule/`, {
                start_date,
                end_date,
            });
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['production-orders'] });
            queryClient.invalidateQueries({ queryKey: ['production-order'] });
        },
    });
};

export const useStartProduction = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            const { data } = await apiClient.post(`/production/production-orders/${id}/start_production/`);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['production-orders'] });
        },
    });
};

export const useCompleteProduction = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, quantity_produced }: { id: number; quantity_produced: number }) => {
            const { data } = await apiClient.post(`/production/production-orders/${id}/complete_production/`, { quantity_produced });
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['production-orders'] });
            queryClient.invalidateQueries({ queryKey: ['production-job-cards'] });
            queryClient.invalidateQueries({ queryKey: ['production-material-requirements'] });
            // Completing production posts finished goods back to inventory
            queryClient.invalidateQueries({ queryKey: ['items'] });
            queryClient.invalidateQueries({ queryKey: ['inventory-stocks'] });
        },
    });
};

export const usePostProductionToGL = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            const { data } = await apiClient.post(`/production/production-orders/${id}/post_to_gl/`);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['production-orders'] });
            queryClient.invalidateQueries({ queryKey: ['journals'] });
            queryClient.invalidateQueries({ queryKey: ['gl-balances'] });
            // Production GL posting creates finished goods StockMovement + updates ItemStock
            queryClient.invalidateQueries({ queryKey: ['stock-movements'] });
            queryClient.invalidateQueries({ queryKey: ['inventory-stocks'] });
            queryClient.invalidateQueries({ queryKey: ['inventory-stock'] });
            queryClient.invalidateQueries({ queryKey: ['inventory-valuation'] });
            queryClient.invalidateQueries({ queryKey: ['items'] });
        },
    });
};

export const useMaterialRequirements = (orderId?: number) => {
    return useQuery({
        queryKey: ['production-material-requirements', orderId],
        queryFn: async () => {
            if (!orderId || isNaN(orderId)) return [];
            const { data } = await apiClient.get(`/production/production-orders/${orderId}/material_requirements/`);
            return data;
        },
        enabled: Boolean(orderId) && !isNaN(orderId),
        staleTime: STALE_TIME,
    });
};

// ============================================================================
// MATERIAL ISSUE HOOKS
// ============================================================================

export const useMaterialIssues = (filters = {}) => {
    return useQuery({
        queryKey: ['production-material-issues', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/production/material-issues/', { params: filters });
            return data;
        },
        staleTime: STALE_TIME,
    });
};

export const useCreateMaterialIssue = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (payload: MaterialIssuePayload) => {
            const { data } = await apiClient.post('/production/material-issues/', payload);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['production-material-issues'] });
            // Issuing materials reduces inventory stock levels
            queryClient.invalidateQueries({ queryKey: ['items'] });
            queryClient.invalidateQueries({ queryKey: ['inventory-stocks'] });
        },
    });
};

export const usePostMaterialIssueToGL = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            const { data } = await apiClient.post(`/production/material-issues/${id}/post_to_gl/`);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['production-material-issues'] });
            queryClient.invalidateQueries({ queryKey: ['journals'] });
            queryClient.invalidateQueries({ queryKey: ['gl-balances'] });
            // Material issue reduces raw material inventory and creates StockMovement
            queryClient.invalidateQueries({ queryKey: ['stock-movements'] });
            queryClient.invalidateQueries({ queryKey: ['inventory-stocks'] });
            queryClient.invalidateQueries({ queryKey: ['inventory-stock'] });
            queryClient.invalidateQueries({ queryKey: ['inventory-valuation'] });
            queryClient.invalidateQueries({ queryKey: ['items'] });
        },
    });
};

// ============================================================================
// MATERIAL RECEIPT HOOKS
// ============================================================================

export const useMaterialReceipts = (filters = {}) => {
    return useQuery({
        queryKey: ['production-material-receipts', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/production/material-receipts/', { params: filters });
            return data;
        },
        staleTime: STALE_TIME,
    });
};

export const useCreateMaterialReceipt = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (payload: MaterialReceiptPayload) => {
            const { data } = await apiClient.post('/production/material-receipts/', payload);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['production-material-receipts'] });
            // Receiving production output adds finished goods to inventory
            queryClient.invalidateQueries({ queryKey: ['items'] });
            queryClient.invalidateQueries({ queryKey: ['inventory-stocks'] });
        },
    });
};

export const usePostMaterialReceiptToGL = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            const { data } = await apiClient.post(`/production/material-receipts/${id}/post_to_gl/`);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['production-material-receipts'] });
            queryClient.invalidateQueries({ queryKey: ['journals'] });
            queryClient.invalidateQueries({ queryKey: ['gl-balances'] });
            // Material receipt adds finished goods inventory and creates StockMovement
            queryClient.invalidateQueries({ queryKey: ['stock-movements'] });
            queryClient.invalidateQueries({ queryKey: ['inventory-stocks'] });
            queryClient.invalidateQueries({ queryKey: ['inventory-stock'] });
            queryClient.invalidateQueries({ queryKey: ['inventory-valuation'] });
            queryClient.invalidateQueries({ queryKey: ['items'] });
            queryClient.invalidateQueries({ queryKey: ['inventory-batches'] });
        },
    });
};

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
            queryClient.invalidateQueries({ queryKey: ['items'] });
            queryClient.invalidateQueries({ queryKey: ['inventory-stocks'] });
            queryClient.invalidateQueries({ queryKey: ['inventory-batches'] });
        },
    });
};

// ============================================================================
// JOB CARD HOOKS
// ============================================================================

export const useJobCards = (filters = {}) => {
    return useQuery({
        queryKey: ['production-job-cards', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/production/job-cards/', { params: filters });
            return data;
        },
        staleTime: STALE_TIME,
    });
};

export const useCreateJobCard = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (payload: JobCardPayload) => {
            const { data } = await apiClient.post('/production/job-cards/', payload);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['production-job-cards'] });
        },
    });
};

export const useStartJobCard = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            const { data } = await apiClient.post(`/production/job-cards/${id}/start_operation/`);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['production-job-cards'] });
        },
    });
};

export const useCompleteJobCard = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, time_actual, labor_cost }: { id: number; time_actual?: number; labor_cost?: number }) => {
            const { data } = await apiClient.post(`/production/job-cards/${id}/complete_operation/`, { time_actual, labor_cost });
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['production-job-cards'] });
            queryClient.invalidateQueries({ queryKey: ['production-orders'] });
        },
    });
};

// ============================================================================
// QUALITY INSPECTION FROM PRODUCTION
// ============================================================================

export const useCreateQualityInspectionFromProduction = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, notes }: { id: number; notes?: string }) => {
            const { data } = await apiClient.post(`/production/production-orders/${id}/create_quality_inspection/`, { notes });
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['production-orders'] });
            queryClient.invalidateQueries({ queryKey: ['quality-inspections'] });
        },
    });
};

export const useProductionQualityInspection = (orderId?: number) => {
    return useQuery({
        queryKey: ['production-quality-inspection', orderId],
        queryFn: async () => {
            if (!orderId || isNaN(orderId)) return null;
            try {
                const { data } = await apiClient.get(`/production/production-orders/${orderId}/quality_inspection/`);
                return data;
            } catch (err: any) {
                if (err?.response?.status === 404) return null;
                throw err;
            }
        },
        enabled: Boolean(orderId) && !isNaN(orderId),
        staleTime: STALE_TIME,
    });
};

// ============================================================================
// ROUTING HOOKS
// ============================================================================

export const useRoutings = (filters = {}) => {
    return useQuery({
        queryKey: ['production-routings', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/production/routings/', { params: filters });
            return data;
        },
        staleTime: STALE_TIME,
    });
};

export const useCreateRouting = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (payload: RoutingPayload) => {
            const { data } = await apiClient.post('/production/routings/', payload);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['production-routings'] });
        },
    });
};

export const useDeleteRouting = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            await apiClient.delete(`/production/routings/${id}/`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['production-routings'] });
        },
    });
};
