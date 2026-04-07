import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '../../../api/client';

// ============================================================================
// PAYLOAD INTERFACES
// ============================================================================

export interface ApprovalGroupPayload {
    name: string;
    description?: string;
    members: number[];
    min_amount?: number;
    max_amount?: number;
    is_active?: boolean;
}

export interface ApprovalTemplateStepPayload {
    group: number;
    sequence: number;
}

export interface ApprovalTemplatePayload {
    name: string;
    description?: string;
    content_type: number | string;
    approval_type?: string;
    steps?: ApprovalTemplateStepPayload[];
    is_active?: boolean;
}

export interface ApprovalPayload {
    content_type: number;
    object_id: number;
    title: string;
    description?: string;
    amount?: number;
    status?: string;
    current_step?: number;
    total_steps?: number;
    requested_by?: number;
    template?: number;
}

export interface WorkflowDefinitionPayload {
    name: string;
    target_model: number;
    is_active?: boolean;
}

const STALE_TIME = 5 * 60 * 1000;

// ============================================================================
// APPROVAL GROUP HOOKS
// ============================================================================

export const useApprovalGroups = (filters = {}) => {
    return useQuery({
        queryKey: ['approval-groups', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/workflow/approval-groups/', { params: filters });
            return data;
        },
        staleTime: STALE_TIME,
    });
};

export const useApprovalGroup = (id?: number) => {
    return useQuery({
        queryKey: ['approval-group', id],
        queryFn: async () => {
            if (!id || isNaN(id)) return null;
            const { data } = await apiClient.get(`/workflow/approval-groups/${id}/`);
            return data;
        },
        enabled: Boolean(id) && !isNaN(id),
        staleTime: STALE_TIME,
    });
};

export const useCreateApprovalGroup = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (payload: ApprovalGroupPayload) => {
            const { data } = await apiClient.post('/workflow/approval-groups/', payload);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['approval-groups'] });
        },
    });
};

export const useUpdateApprovalGroup = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, data }: { id: number; data: Partial<ApprovalGroupPayload> }) => {
            const { data: result } = await apiClient.patch(`/workflow/approval-groups/${id}/`, data);
            return result;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['approval-groups'] });
        },
    });
};

export const useDeleteApprovalGroup = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            await apiClient.delete(`/workflow/approval-groups/${id}/`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['approval-groups'] });
        },
    });
};

// ============================================================================
// APPROVAL TEMPLATE HOOKS
// ============================================================================

export const useApprovalTemplates = (filters = {}) => {
    return useQuery({
        queryKey: ['approval-templates', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/workflow/approval-templates/', { params: filters });
            return data;
        },
        staleTime: STALE_TIME,
    });
};

export const useApprovalTemplate = (id?: number) => {
    return useQuery({
        queryKey: ['approval-template', id],
        queryFn: async () => {
            if (!id || isNaN(id)) return null;
            const { data } = await apiClient.get(`/workflow/approval-templates/${id}/`);
            return data;
        },
        enabled: Boolean(id) && !isNaN(id),
        staleTime: STALE_TIME,
    });
};

export const useCreateApprovalTemplate = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (payload: ApprovalTemplatePayload) => {
            const { data } = await apiClient.post('/workflow/approval-templates/', payload);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['approval-templates'] });
        },
    });
};

export const useUpdateApprovalTemplate = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, data }: { id: number; data: Partial<ApprovalTemplatePayload> }) => {
            const { data: result } = await apiClient.patch(`/workflow/approval-templates/${id}/`, data);
            return result;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['approval-templates'] });
        },
    });
};

export const useDeleteApprovalTemplate = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            await apiClient.delete(`/workflow/approval-templates/${id}/`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['approval-templates'] });
        },
    });
};

// ============================================================================
// APPROVAL HOOKS
// ============================================================================

export const useApprovals = (filters = {}) => {
    return useQuery({
        queryKey: ['approvals', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/workflow/approvals/', { params: filters });
            return data;
        },
        staleTime: STALE_TIME,
    });
};

export const useApproval = (id?: number) => {
    return useQuery({
        queryKey: ['approval', id],
        queryFn: async () => {
            if (!id || isNaN(id)) return null;
            const { data } = await apiClient.get(`/workflow/approvals/${id}/`);
            return data;
        },
        enabled: Boolean(id) && !isNaN(id),
        staleTime: STALE_TIME,
    });
};

export const useCreateApproval = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (payload: ApprovalPayload) => {
            const { data } = await apiClient.post('/workflow/approvals/', payload);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['approvals'] });
        },
    });
};

export const useSubmitApproval = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, comment }: { id: number; comment?: string }) => {
            const { data } = await apiClient.post(`/workflow/approvals/${id}/submit/`, { comment });
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['approvals'] });
        },
    });
};

export const useApproveApproval = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, comment }: { id: number; comment?: string }) => {
            const { data } = await apiClient.post(`/workflow/approvals/${id}/approve/`, { comment });
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['approvals'] });
            // Approval may change status of the related entity (GRN, PO, PR, etc.)
            queryClient.invalidateQueries({ queryKey: ['grns'] });
            queryClient.invalidateQueries({ queryKey: ['purchase-orders'] });
            queryClient.invalidateQueries({ queryKey: ['purchase-requests'] });
        },
    });
};

export const useRejectApproval = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, comment }: { id: number; comment?: string }) => {
            const { data } = await apiClient.post(`/workflow/approvals/${id}/reject/`, { comment });
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['approvals'] });
            queryClient.invalidateQueries({ queryKey: ['grns'] });
            queryClient.invalidateQueries({ queryKey: ['purchase-orders'] });
            queryClient.invalidateQueries({ queryKey: ['purchase-requests'] });
        },
    });
};

export const useCancelApproval = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, comment }: { id: number; comment?: string }) => {
            const { data } = await apiClient.post(`/workflow/approvals/${id}/cancel/`, { comment });
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['approvals'] });
            queryClient.invalidateQueries({ queryKey: ['grns'] });
            queryClient.invalidateQueries({ queryKey: ['purchase-orders'] });
            queryClient.invalidateQueries({ queryKey: ['purchase-requests'] });
        },
    });
};

export const useMyPendingApprovals = () => {
    return useQuery({
        queryKey: ['approvals', 'my-pending'],
        queryFn: async () => {
            const { data } = await apiClient.get('/workflow/approvals/my_pending/');
            return data;
        },
        staleTime: STALE_TIME,
    });
};

export const usePendingApprovalCount = () => {
    return useQuery({
        queryKey: ['approvals', 'pending-count'],
        queryFn: async () => {
            const { data } = await apiClient.get('/workflow/approvals/pending_count/');
            return data;
        },
        staleTime: STALE_TIME,
    });
};

// ============================================================================
// APPROVAL LOG HOOKS
// ============================================================================

export const useApprovalLogs = (filters = {}) => {
    return useQuery({
        queryKey: ['approval-logs', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/workflow/approval-logs/', { params: filters });
            return data;
        },
        staleTime: STALE_TIME,
    });
};

// ============================================================================
// WORKFLOW DEFINITION HOOKS (Legacy)
// ============================================================================

export const useWorkflowDefinitions = (filters = {}) => {
    return useQuery({
        queryKey: ['workflow-definitions', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/workflow/definitions/', { params: filters });
            return data;
        },
        staleTime: STALE_TIME,
    });
};

export const useCreateWorkflowDefinition = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (payload: WorkflowDefinitionPayload) => {
            const { data } = await apiClient.post('/workflow/definitions/', payload);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['workflow-definitions'] });
        },
    });
};

// ============================================================================
// WORKFLOW INSTANCE HOOKS (Legacy)
// ============================================================================

export const useWorkflowInstances = (filters = {}) => {
    return useQuery({
        queryKey: ['workflow-instances', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/workflow/instances/', { params: filters });
            return data;
        },
        staleTime: STALE_TIME,
    });
};

export const useProcessWorkflowAction = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, action, comment, user_display }: { id: number; action: string; comment?: string; user_display?: string }) => {
            const { data } = await apiClient.post(`/workflow/instances/${id}/process_action/`, { action, comment, user_display });
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['workflow-instances'] });
        },
    });
};

// ============================================================================
// CONTENT TYPES & SEED DEFAULTS
// ============================================================================

export const useContentTypes = () => {
    return useQuery({
        queryKey: ['approval-content-types'],
        queryFn: async () => {
            const { data } = await apiClient.get('/workflow/approval-templates/content_types/');
            return data;
        },
        staleTime: 30 * 60 * 1000, // 30 minutes — rarely changes
    });
};

export const useSeedDefaultTemplates = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async () => {
            const { data } = await apiClient.post('/workflow/approval-templates/seed_defaults/');
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['approval-templates'] });
            queryClient.invalidateQueries({ queryKey: ['approval-groups'] });
        },
    });
};

// ============================================================================
// SUBMIT FOR APPROVAL (any module)
// ============================================================================

export const useSubmitForApproval = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (payload: {
            content_type: string;
            object_id: number;
            title: string;
            description?: string;
            amount?: number;
            comment?: string;
        }) => {
            const { data } = await apiClient.post('/workflow/approvals/submit_new/', payload);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['approvals'] });
        },
    });
};
