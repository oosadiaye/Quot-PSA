import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '../../../api/client';

const STALE_TIME = 5 * 60 * 1000;

// ============================================================================
// DASHBOARD HOOKS
// ============================================================================

export const useHRMDashboard = () => {
    return useQuery({
        queryKey: ['hrm-dashboard'],
        queryFn: async () => {
            const { data } = await apiClient.get('/hrm/dashboard/');
            return data;
        },
        staleTime: STALE_TIME,
    });
};

export const useAttendanceToday = () => {
    return useQuery({
        queryKey: ['hrm-attendance-today'],
        queryFn: async () => {
            const { data } = await apiClient.get('/hrm/attendances/today_summary/');
            return data;
        },
        staleTime: 60000,
    });
};

// ============================================================================
// DEPARTMENT HOOKS
// ============================================================================

export const useDepartments = (filters = {}) => {
    return useQuery({
        queryKey: ['hrm-departments', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/hrm/departments/', { params: filters });
            return data;
        },
        staleTime: STALE_TIME,
    });
};

export const useDepartment = (id: number) => {
    return useQuery({
        queryKey: ['hrm-department', id],
        queryFn: async () => {
            const { data } = await apiClient.get(`/hrm/departments/${id}/`);
            return data;
        },
        staleTime: STALE_TIME,
    });
};

export const useCreateDepartment = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (data: any) => {
            const { data: result } = await apiClient.post('/hrm/departments/', data);
            return result;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['hrm-departments'] });
        },
    });
};

export const useUpdateDepartment = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, data }: { id: number; data: any }) => {
            const { data: result } = await apiClient.patch(`/hrm/departments/${id}/`, data);
            return result;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['hrm-departments'] });
        },
    });
};

export const useDeleteDepartment = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            await apiClient.delete(`/hrm/departments/${id}/`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['hrm-departments'] });
        },
    });
};

// ============================================================================
// POSITION HOOKS
// ============================================================================

export const usePositions = (filters = {}) => {
    return useQuery({
        queryKey: ['hrm-positions', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/hrm/positions/', { params: filters });
            return data;
        },
        staleTime: STALE_TIME,
    });
};

export const usePosition = (id: number) => {
    return useQuery({
        queryKey: ['hrm-position', id],
        queryFn: async () => {
            const { data } = await apiClient.get(`/hrm/positions/${id}/`);
            return data;
        },
        staleTime: STALE_TIME,
    });
};

export const useCreatePosition = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (data: any) => {
            const { data: result } = await apiClient.post('/hrm/positions/', data);
            return result;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['hrm-positions'] });
        },
    });
};

export const useUpdatePosition = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, data }: { id: number; data: any }) => {
            const { data: result } = await apiClient.patch(`/hrm/positions/${id}/`, data);
            return result;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['hrm-positions'] });
        },
    });
};

export const useDeletePosition = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            await apiClient.delete(`/hrm/positions/${id}/`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['hrm-positions'] });
        },
    });
};

// ============================================================================
// EMPLOYEE HOOKS
// ============================================================================

export const useEmployees = (filters = {}) => {
    return useQuery({
        queryKey: ['hrm-employees', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/hrm/employees/', { params: filters });
            return data;
        },
        staleTime: STALE_TIME,
    });
};

export const useEmployee = (id: number) => {
    return useQuery({
        queryKey: ['hrm-employee', id],
        queryFn: async () => {
            const { data } = await apiClient.get(`/hrm/employees/${id}/`);
            return data;
        },
        staleTime: STALE_TIME,
    });
};

export const useCreateEmployee = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (data: any) => {
            const { data: result } = await apiClient.post('/hrm/employees/', data);
            return result;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['hrm-employees'] });
        },
    });
};

export const useUpdateEmployee = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, data }: { id: number; data: any }) => {
            const { data: result } = await apiClient.patch(`/hrm/employees/${id}/`, data);
            return result;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['hrm-employees'] });
        },
    });
};

export const useDeleteEmployee = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            await apiClient.delete(`/hrm/employees/${id}/`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['hrm-employees'] });
        },
    });
};

// ============================================================================
// LEAVE HOOKS
// ============================================================================

export const useLeaveTypes = () => {
    return useQuery({
        queryKey: ['hrm-leave-types'],
        queryFn: async () => {
            const { data } = await apiClient.get('/hrm/leave-types/');
            return data;
        },
        staleTime: STALE_TIME,
    });
};

export const useLeaveRequests = (filters = {}) => {
    return useQuery({
        queryKey: ['hrm-leave-requests', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/hrm/leave-requests/', { params: filters });
            return data;
        },
        staleTime: STALE_TIME,
    });
};

export const useLeaveRequest = (id: number) => {
    return useQuery({
        queryKey: ['hrm-leave-request', id],
        queryFn: async () => {
            const { data } = await apiClient.get(`/hrm/leave-requests/${id}/`);
            return data;
        },
        staleTime: STALE_TIME,
    });
};

export const useCreateLeaveRequest = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (data: any) => {
            const { data: result } = await apiClient.post('/hrm/leave-requests/', data);
            return result;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['hrm-leave-requests'] });
        },
    });
};

export const useApproveLeave = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            const { data } = await apiClient.post(`/hrm/leave-requests/${id}/approve/`);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['hrm-leave-requests'] });
        },
    });
};

export const useRejectLeave = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, comment }: { id: number; comment: string }) => {
            const { data } = await apiClient.post(`/hrm/leave-requests/${id}/reject/`, { comment });
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['hrm-leave-requests'] });
        },
    });
};

export const usePendingLeaveCount = () => {
    return useQuery({
        queryKey: ['hrm-pending-leave-count'],
        queryFn: async () => {
            const { data } = await apiClient.get('/hrm/leave-requests/pending_count/');
            return data;
        },
        staleTime: 30000,
    });
};

// ============================================================================
// ATTENDANCE HOOKS
// ============================================================================

export const useAttendances = (filters = {}) => {
    return useQuery({
        queryKey: ['hrm-attendances', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/hrm/attendances/', { params: filters });
            return data;
        },
        staleTime: STALE_TIME,
    });
};

export const useCreateAttendance = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (data: any) => {
            const { data: result } = await apiClient.post('/hrm/attendances/', data);
            return result;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['hrm-attendances'] });
        },
    });
};

// ============================================================================
// HOLIDAY HOOKS
// ============================================================================

export const useHolidays = (filters = {}) => {
    return useQuery({
        queryKey: ['hrm-holidays', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/hrm/holidays/', { params: filters });
            return data;
        },
        staleTime: STALE_TIME,
    });
};

export const useCreateHoliday = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (data: any) => {
            const { data: result } = await apiClient.post('/hrm/holidays/', data);
            return result;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['hrm-holidays'] });
        },
    });
};

export const useUpdateHoliday = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, data }: { id: number; data: any }) => {
            const { data: result } = await apiClient.patch(`/hrm/holidays/${id}/`, data);
            return result;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['hrm-holidays'] });
        },
    });
};

export const useDeleteHoliday = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            await apiClient.delete(`/hrm/holidays/${id}/`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['hrm-holidays'] });
        },
    });
};

// ============================================================================
// RECRUITMENT HOOKS
// ============================================================================

export const useJobPosts = (filters = {}) => {
    return useQuery({
        queryKey: ['hrm-job-posts', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/hrm/job-posts/', { params: filters });
            return data;
        },
        staleTime: STALE_TIME,
    });
};

export const useCreateJobPost = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (data: any) => {
            const { data: result } = await apiClient.post('/hrm/job-posts/', data);
            return result;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['hrm-job-posts'] });
        },
    });
};

export const useCandidates = (filters = {}) => {
    return useQuery({
        queryKey: ['hrm-candidates', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/hrm/candidates/', { params: filters });
            return data;
        },
        staleTime: STALE_TIME,
    });
};

export const useCreateCandidate = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (data: any) => {
            const { data: result } = await apiClient.post('/hrm/candidates/', data);
            return result;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['hrm-candidates'] });
        },
    });
};

export const useUpdateCandidate = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, data }: { id: number; data: any }) => {
            const { data: result } = await apiClient.patch(`/hrm/candidates/${id}/`, data);
            return result;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['hrm-candidates'] });
        },
    });
};

// ============================================================================
// PAYROLL HOOKS
// ============================================================================

export const usePayrollRuns = (filters = {}) => {
    return useQuery({
        queryKey: ['hrm-payroll-runs', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/hrm/payroll-runs/', { params: filters });
            return data;
        },
        staleTime: STALE_TIME,
    });
};

export const useCreatePayrollRun = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (data: any) => {
            const { data: result } = await apiClient.post('/hrm/payroll-runs/', data);
            return result;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['hrm-payroll-runs'] });
        },
    });
};

export const useUpdatePayrollRun = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, data }: { id: number; data: any }) => {
            const { data: result } = await apiClient.patch(`/hrm/payroll-runs/${id}/`, data);
            return result;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['hrm-payroll-runs'] });
        },
    });
};

export const useProcessPayroll = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            const { data } = await apiClient.post(`/hrm/payroll-runs/${id}/process/`);
            return data;
        },
        onSuccess: () => {
            // Processing calculates payslips and gross/net figures
            queryClient.invalidateQueries({ queryKey: ['hrm-payroll-runs'] });
            queryClient.invalidateQueries({ queryKey: ['hrm-payslips'] });
        },
    });
};

export const useApprovePayroll = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            const { data } = await apiClient.post(`/hrm/payroll-runs/${id}/approve/`);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['hrm-payroll-runs'] });
        },
    });
};

export const useMarkPayrollPaid = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            const { data } = await apiClient.post(`/hrm/payroll-runs/${id}/mark_paid/`);
            return data;
        },
        onSuccess: () => {
            // mark_paid posts Dr Payroll Liability / Cr Bank to GL
            queryClient.invalidateQueries({ queryKey: ['hrm-payroll-runs'] });
            queryClient.invalidateQueries({ queryKey: ['hrm-payslips'] });
            queryClient.invalidateQueries({ queryKey: ['journals'] });
            queryClient.invalidateQueries({ queryKey: ['gl-balances'] });
            // Bank account balance changes — invalidate bank/cash views
            queryClient.invalidateQueries({ queryKey: ['bank-accounts'] });
            queryClient.invalidateQueries({ queryKey: ['bank-transactions'] });
        },
    });
};

export const usePostPayrollToGL = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            const { data } = await apiClient.post(`/hrm/payroll-runs/${id}/post_to_gl/`);
            return data;
        },
        onSuccess: () => {
            // post_to_gl runs post_payroll_run() → Dr Salary Expense / Cr Payroll Liability
            queryClient.invalidateQueries({ queryKey: ['hrm-payroll-runs'] });
            queryClient.invalidateQueries({ queryKey: ['journals'] });
            queryClient.invalidateQueries({ queryKey: ['gl-balances'] });
        },
    });
};

export const useReversePayroll = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, reason }: { id: number; reason?: string }) => {
            const { data } = await apiClient.post(`/hrm/payroll-runs/${id}/reverse/`, { reason });
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['hrm-payroll-runs'] });
            queryClient.invalidateQueries({ queryKey: ['journals'] });
            queryClient.invalidateQueries({ queryKey: ['gl-balances'] });
        },
    });
};

export const usePayslips = (filters = {}) => {
    return useQuery({
        queryKey: ['hrm-payslips', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/hrm/payslips/', { params: filters });
            return data;
        },
        staleTime: STALE_TIME,
    });
};

// ============================================================================
// PERFORMANCE HOOKS
// ============================================================================

export const usePerformanceCycles = (filters = {}) => {
    return useQuery({
        queryKey: ['hrm-performance-cycles', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/hrm/performance-cycles/', { params: filters });
            return data;
        },
        staleTime: STALE_TIME,
    });
};

export const usePerformanceReviews = (filters = {}) => {
    return useQuery({
        queryKey: ['hrm-performance-reviews', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/hrm/performance-reviews/', { params: filters });
            return data;
        },
        staleTime: STALE_TIME,
    });
};

export const useCreatePerformanceReview = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (data: any) => {
            const { data: result } = await apiClient.post('/hrm/performance-reviews/', data);
            return result;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['hrm-performance-reviews'] });
        },
    });
};

// ============================================================================
// TRAINING HOOKS
// ============================================================================

export const useTrainingPrograms = (filters = {}) => {
    return useQuery({
        queryKey: ['hrm-training-programs', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/hrm/training-programs/', { params: filters });
            return data;
        },
        staleTime: STALE_TIME,
    });
};

export const useCreateTrainingProgram = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (data: any) => {
            const { data: result } = await apiClient.post('/hrm/training-programs/', data);
            return result;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['hrm-training-programs'] });
        },
    });
};

export const useSkills = (filters = {}) => {
    return useQuery({
        queryKey: ['hrm-skills', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/hrm/skills/', { params: filters });
            return data;
        },
        staleTime: STALE_TIME,
    });
};

// ============================================================================
// POLICY HOOKS
// ============================================================================

export const usePolicies = (filters = {}) => {
    return useQuery({
        queryKey: ['hrm-policies', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/hrm/policies/', { params: filters });
            return data;
        },
        staleTime: STALE_TIME,
    });
};

export const useCreatePolicy = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (data: any) => {
            const { data: result } = await apiClient.post('/hrm/policies/', data);
            return result;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['hrm-policies'] });
        },
    });
};

// ============================================================================
// COMPLIANCE HOOKS
// ============================================================================

export const useComplianceRecords = (filters = {}) => {
    return useQuery({
        queryKey: ['hrm-compliance', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/hrm/compliance-records/', { params: filters });
            return data;
        },
        staleTime: STALE_TIME,
    });
};

// ============================================================================
// EXIT MANAGEMENT HOOKS
// ============================================================================

export const useExitRequests = (filters = {}) => {
    return useQuery({
        queryKey: ['hrm-exit-requests', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/hrm/exit-requests/', { params: filters });
            return data;
        },
        staleTime: STALE_TIME,
    });
};

export const useCreateExitRequest = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (data: any) => {
            const { data: result } = await apiClient.post('/hrm/exit-requests/', data);
            return result;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['hrm-exit-requests'] });
        },
    });
};
