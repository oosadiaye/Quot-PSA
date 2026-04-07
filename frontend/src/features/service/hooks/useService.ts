import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '../../../api/client';
import type {
    ServiceTicket, ServiceAsset, Technician, WorkOrder, WorkOrderMaterial,
    CitizenRequest, ServiceMetric, MaintenanceSchedule, ServiceDashboardStats,
    PaginatedResponse,
} from '../types';

const STALE_TIME = 5 * 60 * 1000;

// ── Query Hooks ──

export const useServiceTickets = (filters: Record<string, string> = {}) => {
    return useQuery<PaginatedResponse<ServiceTicket>>({
        queryKey: ['service-tickets', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/service/tickets/', { params: filters });
            return data;
        },
        staleTime: STALE_TIME,
    });
};

export const useServiceTicket = (id: number | string) => {
    return useQuery<ServiceTicket>({
        queryKey: ['service-ticket', id],
        queryFn: async () => {
            const { data } = await apiClient.get(`/service/tickets/${id}/`);
            return data;
        },
        staleTime: STALE_TIME,
        enabled: !!id,
    });
};

export const useServiceAssets = () => {
    return useQuery<PaginatedResponse<ServiceAsset>>({
        queryKey: ['service-assets'],
        queryFn: async () => {
            const { data } = await apiClient.get('/service/assets/');
            return data;
        },
        staleTime: STALE_TIME,
    });
};

export const useTechnicians = () => {
    return useQuery<PaginatedResponse<Technician>>({
        queryKey: ['service-technicians'],
        queryFn: async () => {
            const { data } = await apiClient.get('/service/technicians/');
            return data;
        },
        staleTime: STALE_TIME,
    });
};

export const useWorkOrders = (filters: Record<string, string> = {}) => {
    return useQuery<PaginatedResponse<WorkOrder>>({
        queryKey: ['service-work-orders', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/service/work-orders/', { params: filters });
            return data;
        },
        staleTime: STALE_TIME,
    });
};

export const useWorkOrder = (id: number | string) => {
    return useQuery<WorkOrder>({
        queryKey: ['service-work-order', id],
        queryFn: async () => {
            const { data } = await apiClient.get(`/service/work-orders/${id}/`);
            return data;
        },
        staleTime: STALE_TIME,
        enabled: !!id,
    });
};

export const useCitizenRequests = (filters: Record<string, string> = {}) => {
    return useQuery<PaginatedResponse<CitizenRequest>>({
        queryKey: ['service-citizen-requests', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/service/citizen-requests/', { params: filters });
            return data;
        },
        staleTime: STALE_TIME,
    });
};

export const useServiceMetrics = (filters: Record<string, string> = {}) => {
    return useQuery<PaginatedResponse<ServiceMetric>>({
        queryKey: ['service-metrics', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/service/metrics/', { params: filters });
            return data;
        },
        staleTime: STALE_TIME,
    });
};

export const useServiceDashboard = () => {
    return useQuery<ServiceDashboardStats>({
        queryKey: ['service-dashboard'],
        queryFn: async () => {
            const { data } = await apiClient.get('/service/metrics/dashboard/');
            return data;
        },
        staleTime: STALE_TIME,
    });
};

export const useMaintenanceSchedules = () => {
    return useQuery<PaginatedResponse<MaintenanceSchedule>>({
        queryKey: ['service-schedules'],
        queryFn: async () => {
            const { data } = await apiClient.get('/service/schedules/');
            return data;
        },
        staleTime: STALE_TIME,
    });
};

// ── Mutation Hooks ──

export const useResolveTicket = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            const { data } = await apiClient.post(`/service/tickets/${id}/resolve_ticket/`);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['service-tickets'] });
            queryClient.invalidateQueries({ queryKey: ['service-ticket'] });
        },
    });
};

export const useCreateTicket = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (payload: Partial<ServiceTicket>) => {
            const { data } = await apiClient.post('/service/tickets/', payload);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['service-tickets'] });
        },
    });
};

export const useUpdateTicket = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, ...payload }: { id: number } & Partial<ServiceTicket>) => {
            const { data } = await apiClient.patch(`/service/tickets/${id}/`, payload);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['service-tickets'] });
            queryClient.invalidateQueries({ queryKey: ['service-ticket'] });
        },
    });
};

export const useAssignTechnician = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, technician_id }: { id: number; technician_id: number }) => {
            const { data } = await apiClient.post(`/service/tickets/${id}/assign_technician/`, { technician_id });
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['service-tickets'] });
            queryClient.invalidateQueries({ queryKey: ['service-ticket'] });
        },
    });
};

export const useCreateWorkOrder = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (payload: Partial<WorkOrder>) => {
            const { data } = await apiClient.post('/service/work-orders/', payload);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['service-work-orders'] });
        },
    });
};

export const useUpdateWorkOrder = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, ...payload }: { id: number } & Partial<WorkOrder>) => {
            const { data } = await apiClient.patch(`/service/work-orders/${id}/`, payload);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['service-work-orders'] });
            queryClient.invalidateQueries({ queryKey: ['service-work-order'] });
        },
    });
};

export const useCompleteWorkOrder = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            const { data } = await apiClient.post(`/service/work-orders/${id}/complete/`);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['service-work-orders'] });
            queryClient.invalidateQueries({ queryKey: ['service-work-order'] });
        },
    });
};

export const useAddWorkOrderMaterial = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ workOrderId, ...payload }: { workOrderId: number } & Partial<WorkOrderMaterial>) => {
            const { data } = await apiClient.post(`/service/work-orders/${workOrderId}/add_material/`, payload);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['service-work-orders'] });
            queryClient.invalidateQueries({ queryKey: ['service-work-order'] });
        },
    });
};

export const useDeleteWorkOrderMaterial = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            const { data } = await apiClient.delete(`/service/work-order-materials/${id}/`);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['service-work-orders'] });
            queryClient.invalidateQueries({ queryKey: ['service-work-order'] });
        },
    });
};

export const usePostWorkOrderToGL = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            const { data } = await apiClient.post(`/service/work-orders/${id}/post_to_gl/`);
            return data;
        },
        onSuccess: () => {
            // post_to_gl posts Dr Service Expense / Cr Service Revenue
            queryClient.invalidateQueries({ queryKey: ['service-work-orders'] });
            queryClient.invalidateQueries({ queryKey: ['service-work-order'] });
            queryClient.invalidateQueries({ queryKey: ['journals'] });
            queryClient.invalidateQueries({ queryKey: ['gl-balances'] });
        },
    });
};

export const usePostServiceTicketToGL = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            const { data } = await apiClient.post(`/service/tickets/${id}/post_to_gl/`);
            return data;
        },
        onSuccess: () => {
            // post_to_gl posts Dr AR / Cr Service Revenue
            queryClient.invalidateQueries({ queryKey: ['service-tickets'] });
            queryClient.invalidateQueries({ queryKey: ['service-ticket'] });
            queryClient.invalidateQueries({ queryKey: ['journals'] });
            queryClient.invalidateQueries({ queryKey: ['gl-balances'] });
            queryClient.invalidateQueries({ queryKey: ['customer-invoices'] });
            queryClient.invalidateQueries({ queryKey: ['customer-ledger'] });
        },
    });
};

export const useCreateServiceAsset = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (payload: Partial<ServiceAsset>) => {
            const { data } = await apiClient.post('/service/assets/', payload);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['service-assets'] });
        },
    });
};

export const useUpdateServiceAsset = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, ...payload }: { id: number } & Partial<ServiceAsset>) => {
            const { data } = await apiClient.patch(`/service/assets/${id}/`, payload);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['service-assets'] });
        },
    });
};

export const useCreateTechnician = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (payload: Partial<Technician>) => {
            const { data } = await apiClient.post('/service/technicians/', payload);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['service-technicians'] });
        },
    });
};

export const useUpdateTechnician = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, ...payload }: { id: number } & Partial<Technician>) => {
            const { data } = await apiClient.patch(`/service/technicians/${id}/`, payload);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['service-technicians'] });
        },
    });
};

export const useAcknowledgeCitizenRequest = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            const { data } = await apiClient.post(`/service/citizen-requests/${id}/acknowledge/`);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['service-citizen-requests'] });
        },
    });
};

export const useConvertToTicket = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            const { data } = await apiClient.post(`/service/citizen-requests/${id}/convert_to_ticket/`);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['service-citizen-requests'] });
            queryClient.invalidateQueries({ queryKey: ['service-tickets'] });
        },
    });
};

export const useGenerateMetrics = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (period: string) => {
            const { data } = await apiClient.post('/service/metrics/generate_metrics/', { period });
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['service-metrics'] });
            queryClient.invalidateQueries({ queryKey: ['service-dashboard'] });
        },
    });
};

export const useCreateSchedule = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (payload: Partial<MaintenanceSchedule>) => {
            const { data } = await apiClient.post('/service/schedules/', payload);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['service-schedules'] });
        },
    });
};

export const useGenerateTicketFromSchedule = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            const { data } = await apiClient.post(`/service/schedules/${id}/generate_ticket/`);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['service-tickets'] });
            queryClient.invalidateQueries({ queryKey: ['service-schedules'] });
        },
    });
};
