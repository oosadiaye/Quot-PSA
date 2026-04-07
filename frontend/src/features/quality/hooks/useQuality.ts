import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '../../../api/client';

// Re-export vendors from procurement so quality pages don't need a cross-module import
export { useVendors } from '../../procurement/hooks/useProcurement';

// ============================================================================
// PAYLOAD INTERFACES
// ============================================================================

export interface QualityInspectionPayload {
    inspection_type: string;
    inspection_date: string;
    reference_type?: string;
    reference_number?: string;
    status?: string;
    inspector?: number | null;
    goods_received_note?: number | null;
    production_order?: number | null;
    item?: number | null;
    notes?: string;
}

export interface InspectionLinePayload {
    parameter: string;
    result: string;
    specification?: string;
    measurement?: number | null;
    notes?: string;
}

export interface NonConformancePayload {
    title: string;
    description: string;
    severity: string;
    status?: string;
    related_inspection?: number | null;
    source_type?: string;
    source_id?: number | null;
    root_cause?: string;
    corrective_action?: string;
    preventive_action?: string;
    assigned_to?: number | null;
    closed_date?: string | null;
    notes?: string;
}

export interface CustomerComplaintPayload {
    customer_name: string;
    subject: string;
    description: string;
    customer_email?: string;
    customer_phone?: string;
    status?: string;
    related_sales_order?: string;
    related_ncr?: number | null;
    resolution?: string;
    resolution_date?: string | null;
    notes?: string;
}

export interface QualityChecklistPayload {
    name: string;
    checklist_type: string;
    description?: string;
    is_active?: boolean;
}

export interface CalibrationRecordPayload {
    equipment_name: string;
    equipment_type: string;
    manufacturer?: string;
    model_number?: string;
    serial_number?: string;
    last_calibration_date?: string | null;
    next_calibration_date?: string | null;
    calibration_interval_months?: number;
    status?: string;
    notes?: string;
}

export interface SupplierQualityPayload {
    vendor: number;
    evaluation_date: string;
    quality_score: number;
    delivery_score: number;
    rating: string;
    comments?: string;
    next_evaluation_date?: string | null;
}

const STALE_TIME = 5 * 60 * 1000;

// ============================================================================
// QUALITY INSPECTIONS
// ============================================================================

export const useQualityInspections = (filters = {}) => {
    return useQuery({
        queryKey: ['quality-inspections', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/quality/inspections/', { params: filters });
            return data;
        },
        staleTime: STALE_TIME,
    });
};

export const useQualityInspection = (id: number) => {
    return useQuery({
        queryKey: ['quality-inspection', id],
        queryFn: async () => {
            const { data } = await apiClient.get(`/quality/inspections/${id}/`);
            return data;
        },
        enabled: !!id,
        staleTime: STALE_TIME,
    });
};

export const useCreateQualityInspection = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (payload: QualityInspectionPayload) => {
            const { data } = await apiClient.post('/quality/inspections/', payload);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['quality-inspections'] });
        },
    });
};

export const useUpdateQualityInspection = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, payload }: { id: number; payload: Partial<QualityInspectionPayload> }) => {
            const { data } = await apiClient.patch(`/quality/inspections/${id}/`, payload);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['quality-inspections'] });
        },
    });
};

export const useCompleteInspection = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            const { data } = await apiClient.post(`/quality/inspections/${id}/complete/`);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['quality-inspections'] });
        },
    });
};

export const useAcceptGRNInspection = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            const { data } = await apiClient.post(`/quality/inspections/${id}/accept_grn/`);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['quality-inspections'] });
            queryClient.invalidateQueries({ queryKey: ['grns'] });
            queryClient.invalidateQueries({ queryKey: ['journals'] });
            queryClient.invalidateQueries({ queryKey: ['gl-balances'] });
        },
    });
};

export const useRejectGRNInspection = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, notes }: { id: number; notes?: string }) => {
            const { data } = await apiClient.post(`/quality/inspections/${id}/reject_grn/`, { notes });
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['quality-inspections'] });
            queryClient.invalidateQueries({ queryKey: ['non-conformances'] });
        },
    });
};

export const usePostQualityInspectionToGL = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            const { data } = await apiClient.post(`/quality/inspections/${id}/post_to_gl/`);
            return data;
        },
        onSuccess: () => {
            // post_quality_inspection posts Dr QC Expense / Cr Inventory
            // → inventory balance and valuation change on the CR side
            queryClient.invalidateQueries({ queryKey: ['quality-inspections'] });
            queryClient.invalidateQueries({ queryKey: ['journals'] });
            queryClient.invalidateQueries({ queryKey: ['gl-balances'] });
            queryClient.invalidateQueries({ queryKey: ['inventory-stock'] });
            queryClient.invalidateQueries({ queryKey: ['inventory-valuation'] });
            queryClient.invalidateQueries({ queryKey: ['stock-movements'] });
        },
    });
};

export const useAddInspectionLine = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ inspectionId, payload }: { inspectionId: number; payload: InspectionLinePayload }) => {
            const { data } = await apiClient.post(`/quality/inspections/${inspectionId}/add_line/`, payload);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['quality-inspections'] });
        },
    });
};

// ============================================================================
// NON-CONFORMANCES
// ============================================================================

export const useNonConformances = (filters = {}) => {
    return useQuery({
        queryKey: ['non-conformances', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/quality/non-conformances/', { params: filters });
            return data;
        },
        staleTime: STALE_TIME,
    });
};

export const useCreateNonConformance = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (payload: NonConformancePayload) => {
            const { data } = await apiClient.post('/quality/non-conformances/', payload);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['non-conformances'] });
        },
    });
};

export const useCloseNonConformance = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, closed_date }: { id: number; closed_date?: string }) => {
            const { data } = await apiClient.post(`/quality/non-conformances/${id}/close/`, { closed_date });
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['non-conformances'] });
        },
    });
};

export const usePostNonConformanceToGL = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            const { data } = await apiClient.post(`/quality/non-conformances/${id}/post_to_gl/`);
            return data;
        },
        onSuccess: () => {
            // post_non_conformance posts Dr Scrap Expense / Cr Inventory
            // → both inventory balance and valuation drop on the CR side
            queryClient.invalidateQueries({ queryKey: ['non-conformances'] });
            queryClient.invalidateQueries({ queryKey: ['journals'] });
            queryClient.invalidateQueries({ queryKey: ['gl-balances'] });
            queryClient.invalidateQueries({ queryKey: ['inventory-stock'] });
            queryClient.invalidateQueries({ queryKey: ['inventory-valuation'] });
            queryClient.invalidateQueries({ queryKey: ['stock-movements'] });
        },
    });
};

// ============================================================================
// CUSTOMER COMPLAINTS
// ============================================================================

export const useCustomerComplaints = (filters = {}) => {
    return useQuery({
        queryKey: ['customer-complaints', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/quality/complaints/', { params: filters });
            return data;
        },
        staleTime: STALE_TIME,
    });
};

export const useCreateCustomerComplaint = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (payload: CustomerComplaintPayload) => {
            const { data } = await apiClient.post('/quality/complaints/', payload);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['customer-complaints'] });
        },
    });
};

export const useUpdateCustomerComplaint = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, payload }: { id: number; payload: Partial<CustomerComplaintPayload> }) => {
            const { data } = await apiClient.patch(`/quality/complaints/${id}/`, payload);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['customer-complaints'] });
        },
    });
};

// ============================================================================
// QUALITY CHECKLISTS
// ============================================================================

export const useQualityChecklists = (filters = {}) => {
    return useQuery({
        queryKey: ['quality-checklists', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/quality/checklists/', { params: filters });
            return data;
        },
        staleTime: STALE_TIME,
    });
};

export const useCreateQualityChecklist = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (payload: QualityChecklistPayload) => {
            const { data } = await apiClient.post('/quality/checklists/', payload);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['quality-checklists'] });
        },
    });
};

// ============================================================================
// CALIBRATION RECORDS
// ============================================================================

export const useCalibrationRecords = (filters = {}) => {
    return useQuery({
        queryKey: ['calibration-records', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/quality/calibrations/', { params: filters });
            return data;
        },
        staleTime: STALE_TIME,
    });
};

export const useDueOverdueCalibrations = () => {
    return useQuery({
        queryKey: ['calibration-due-overdue'],
        queryFn: async () => {
            const { data } = await apiClient.get('/quality/calibrations/due_overdue/');
            return data;
        },
        staleTime: STALE_TIME,
    });
};

export const useCreateCalibrationRecord = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (payload: CalibrationRecordPayload) => {
            const { data } = await apiClient.post('/quality/calibrations/', payload);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['calibration-records'] });
        },
    });
};

export const useCalibrateEquipment = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            const { data } = await apiClient.post(`/quality/calibrations/${id}/calibrate/`);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['calibration-records'] });
            queryClient.invalidateQueries({ queryKey: ['calibration-due-overdue'] });
        },
    });
};

// ============================================================================
// SUPPLIER QUALITY
// ============================================================================

export const useSupplierQuality = (filters = {}) => {
    return useQuery({
        queryKey: ['supplier-quality', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/quality/supplier-quality/', { params: filters });
            return data;
        },
        staleTime: STALE_TIME,
    });
};

export const useCreateSupplierQuality = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (payload: SupplierQualityPayload) => {
            const { data } = await apiClient.post('/quality/supplier-quality/', payload);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['supplier-quality'] });
        },
    });
};

export const useUpdateSupplierQuality = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, payload }: { id: number; payload: Partial<SupplierQualityPayload> }) => {
            const { data } = await apiClient.patch(`/quality/supplier-quality/${id}/`, payload);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['supplier-quality'] });
        },
    });
};
