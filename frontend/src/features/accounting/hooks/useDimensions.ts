import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '../../../api/client';

// ============================================================================
// TYPES
// ============================================================================

export interface Dimension {
    id: number;
    code: string;
    name: string;
    description?: string;
    is_active: boolean;
    created_at: string;
    updated_at: string;
}

export interface DimensionFormData {
    code: string;
    name: string;
    description?: string;
    is_active: boolean;
}

export interface BulkImportResult {
    success: boolean;
    created: number;
    updated: number;
    skipped: number;
    errors: string[];
}

export type DimensionType = 'funds' | 'functions' | 'programs' | 'geos';

// ============================================================================
// SHARED IMPORT/EXPORT HELPERS
// ============================================================================

export const downloadDimensionTemplate = async (type: DimensionType) => {
    const response = await apiClient.get(`/accounting/${type}/import-template/`, {
        responseType: 'blob',
    });
    const blob = new Blob([response.data], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${type}_import_template.csv`;
    a.click();
    window.URL.revokeObjectURL(url);
};

export const exportDimensions = async (type: DimensionType, format: 'csv' | 'xlsx' = 'csv') => {
    const response = await apiClient.get(`/accounting/${type}/export/`, {
        params: { format },
        responseType: 'blob',
    });
    const contentType = format === 'xlsx'
        ? 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        : 'text/csv';
    const blob = new Blob([response.data], { type: contentType });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${type}_export.${format}`;
    a.click();
    window.URL.revokeObjectURL(url);
};

export const useBulkImportDimension = (type: DimensionType) => {
    const queryClient = useQueryClient();

    return useMutation<BulkImportResult, Error, File>({
        mutationFn: async (file: File) => {
            const formData = new FormData();
            formData.append('file', file);
            const response = await apiClient.post(`/accounting/${type}/bulk-import/`, formData, {
                headers: { 'Content-Type': 'multipart/form-data' },
            });
            return response.data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: [type] });
        },
    });
};

// ============================================================================
// FUND HOOKS
// ============================================================================

export const useFunds = () => {
    return useQuery<Dimension[]>({
        queryKey: ['funds'],
        queryFn: async () => {
            const response = await apiClient.get('/accounting/funds/');
            return response.data.results;
        },
        staleTime: 5 * 60 * 1000, // 5 minutes
        gcTime: 10 * 60 * 1000, // 10 minutes
    });
};

export const useCreateFund = () => {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async (data: DimensionFormData) => {
            const response = await apiClient.post('/accounting/funds/', data);
            return response.data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['funds'] });
        },
    });
};

export const useUpdateFund = () => {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async ({ id, data }: { id: number; data: DimensionFormData }) => {
            const response = await apiClient.put(`/accounting/funds/${id}/`, data);
            return response.data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['funds'] });
        },
    });
};

export const useDeleteFund = () => {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async (id: number) => {
            await apiClient.delete(`/accounting/funds/${id}/`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['funds'] });
        },
    });
};

// ============================================================================
// FUNCTION HOOKS
// ============================================================================

export const useFunctions = () => {
    return useQuery<Dimension[]>({
        queryKey: ['functions'],
        queryFn: async () => {
            const response = await apiClient.get('/accounting/functions/');
            return response.data.results;
        },
        staleTime: 5 * 60 * 1000,
        gcTime: 10 * 60 * 1000,
    });
};

export const useCreateFunction = () => {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async (data: DimensionFormData) => {
            const response = await apiClient.post('/accounting/functions/', data);
            return response.data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['functions'] });
        },
    });
};

export const useUpdateFunction = () => {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async ({ id, data }: { id: number; data: DimensionFormData }) => {
            const response = await apiClient.put(`/accounting/functions/${id}/`, data);
            return response.data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['functions'] });
        },
    });
};

export const useDeleteFunction = () => {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async (id: number) => {
            await apiClient.delete(`/accounting/functions/${id}/`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['functions'] });
        },
    });
};

// ============================================================================
// PROGRAM HOOKS
// ============================================================================

export const usePrograms = () => {
    return useQuery<Dimension[]>({
        queryKey: ['programs'],
        queryFn: async () => {
            const response = await apiClient.get('/accounting/programs/');
            return response.data.results;
        },
        staleTime: 5 * 60 * 1000,
        gcTime: 10 * 60 * 1000,
    });
};

export const useCreateProgram = () => {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async (data: DimensionFormData) => {
            const response = await apiClient.post('/accounting/programs/', data);
            return response.data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['programs'] });
        },
    });
};

export const useUpdateProgram = () => {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async ({ id, data }: { id: number; data: DimensionFormData }) => {
            const response = await apiClient.put(`/accounting/programs/${id}/`, data);
            return response.data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['programs'] });
        },
    });
};

export const useDeleteProgram = () => {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async (id: number) => {
            await apiClient.delete(`/accounting/programs/${id}/`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['programs'] });
        },
    });
};

// ============================================================================
// GEO HOOKS
// ============================================================================

export const useGeos = () => {
    return useQuery<Dimension[]>({
        queryKey: ['geos'],
        queryFn: async () => {
            const response = await apiClient.get('/accounting/geos/');
            return response.data.results;
        },
        staleTime: 5 * 60 * 1000,
        gcTime: 10 * 60 * 1000,
    });
};

export const useCreateGeo = () => {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async (data: DimensionFormData) => {
            const response = await apiClient.post('/accounting/geos/', data);
            return response.data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['geos'] });
        },
    });
};

export const useUpdateGeo = () => {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async ({ id, data }: { id: number; data: DimensionFormData }) => {
            const response = await apiClient.put(`/accounting/geos/${id}/`, data);
            return response.data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['geos'] });
        },
    });
};

export const useDeleteGeo = () => {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async (id: number) => {
            await apiClient.delete(`/accounting/geos/${id}/`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['geos'] });
        },
    });
};
