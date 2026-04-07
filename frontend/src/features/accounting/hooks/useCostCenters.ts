import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '../../../api/client';

const API_BASE = '/accounting/cost-centers';

export interface CostCenter {
    id: number;
    name: string;
    code: string;
    center_type: 'Department' | 'Project' | 'Activity' | 'Location';
    parent: number | null;
    parent_name?: string;
    manager: number | null;
    manager_name?: string;
    is_active: boolean;
    gl_account: number | null;
    gl_account_name?: string;
    created_at?: string;
    updated_at?: string;
}

export interface CostCenterFormData {
    name: string;
    code: string;
    center_type: string;
    parent?: number | null;
    manager?: number | null;
    is_active: boolean;
    gl_account?: number | null;
}

// Fetch all cost centers
const fetchCostCenters = async (params?: { center_type?: string; is_active?: boolean; search?: string }): Promise<CostCenter[]> => {
    const queryParams = new URLSearchParams();
    if (params?.center_type) queryParams.append('center_type', params.center_type);
    if (params?.is_active !== undefined) queryParams.append('is_active', String(params.is_active));
    if (params?.search) queryParams.append('search', params.search);
    const { data } = await apiClient.get(`${API_BASE}/?${queryParams.toString()}`);
    return data.results ?? data;
};

// Fetch single cost center
const fetchCostCenter = async (id: number): Promise<CostCenter> => {
    const { data } = await apiClient.get(`${API_BASE}/${id}/`);
    return data;
};

// Create cost center
const createCostCenter = async (payload: CostCenterFormData): Promise<CostCenter> => {
    const { data } = await apiClient.post(`${API_BASE}/`, payload);
    return data;
};

// Update cost center
const updateCostCenter = async ({ id, ...payload }: CostCenterFormData & { id: number }): Promise<CostCenter> => {
    const { data } = await apiClient.put(`${API_BASE}/${id}/`, payload);
    return data;
};

// Delete cost center
const deleteCostCenter = async (id: number): Promise<void> => {
    await apiClient.delete(`${API_BASE}/${id}/`);
};

// Export cost centers to CSV
export const exportCostCenters = async () => {
    const { data } = await apiClient.get(`${API_BASE}/export/`, { responseType: 'blob' });
    return data;
};

// Download import template
export const downloadCostCenterTemplate = () => {
    const headers = ['code', 'name', 'center_type', 'parent_code', 'manager_name', 'gl_account_code', 'is_active'];
    const sampleData = [
        ['CC001', 'Sample Department', 'Department', '', '', '1000', 'true'],
        ['CC002', 'Sample Project', 'Project', '', '', '1100', 'true'],
    ];
    const csvContent = [headers, ...sampleData].map(row => row.join(',')).join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'cost_center_import_template.csv';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
};

// Import cost centers from CSV
export const importCostCenters = async (file: File): Promise<any> => {
    const formData = new FormData();
    formData.append('file', file);
    const { data } = await apiClient.post(`${API_BASE}/import/`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
    });
    return data;
};

/**
 * Hook for listing cost centers with optional filters
 */
export const useCostCenters = (params?: { center_type?: string; is_active?: boolean; search?: string }) => {
    return useQuery({
        queryKey: ['cost-centers', params],
        queryFn: () => fetchCostCenters(params),
        staleTime: 30000,
    });
};

/**
 * Hook for fetching a single cost center
 */
export const useCostCenter = (id: number | null) => {
    return useQuery({
        queryKey: ['cost-center', id],
        queryFn: () => fetchCostCenter(id!),
        enabled: !!id,
    });
};

/**
 * Hook for creating a cost center
 */
export const useCreateCostCenter = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: createCostCenter,
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['cost-centers'] });
        },
    });
};

/**
 * Hook for updating a cost center
 */
export const useUpdateCostCenter = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: updateCostCenter,
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['cost-centers'] });
        },
    });
};

/**
 * Hook for deleting a cost center
 */
export const useDeleteCostCenter = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: deleteCostCenter,
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['cost-centers'] });
        },
    });
};
