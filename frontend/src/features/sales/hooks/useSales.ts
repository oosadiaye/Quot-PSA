import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '../../../api/client';

// ============================================================================
// SHARED ACCOUNTING LOOKUP (used by sales forms for GL selection)
// ============================================================================

/**
 * Returns accounts whose reconciliation_type is 'accounts_receivable'.
 * These are the only accounts valid for AR configuration on CustomerCategory.
 */
export const useARAccounts = () => {
    return useQuery({
        queryKey: ['accounts-ar'],
        queryFn: async () => {
            const { data } = await apiClient.get('/accounting/accounts/', {
                params: { reconciliation_type: 'accounts_receivable', is_active: true },
            });
            return data.results ?? data;
        },
        staleTime: 10 * 60 * 1000,
    });
};

const STALE_TIME = 5 * 60 * 1000;

// ============================================================================
// CUSTOMER CATEGORY HOOKS
// ============================================================================

export const useCustomerCategories = () => {
    return useQuery({
        queryKey: ['customer-categories'],
        queryFn: async () => {
            const { data } = await apiClient.get('/sales/customer-categories/');
            return data.results ?? data;
        },
        staleTime: STALE_TIME,
    });
};

export const useCreateCustomerCategory = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (payload: any) => {
            const { data } = await apiClient.post('/sales/customer-categories/', payload);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['customer-categories'] });
        },
    });
};

export const useUpdateCustomerCategory = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, data }: { id: number; data: any }) => {
            const { data: result } = await apiClient.patch(`/sales/customer-categories/${id}/`, data);
            return result;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['customer-categories'] });
        },
    });
};

export const useDeleteCustomerCategory = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            await apiClient.delete(`/sales/customer-categories/${id}/`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['customer-categories'] });
        },
    });
};


// ============================================================================
// CUSTOMER HOOKS
// ============================================================================

export const useCustomers = (filters = {}) => {
    return useQuery({
        queryKey: ['customers', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/sales/customers/', { params: filters });
            return data.results;
        },
        staleTime: STALE_TIME,
    });
};

export const useCustomer = (id?: number) => {
    return useQuery({
        queryKey: ['customer', id],
        queryFn: async () => {
            if (!id || isNaN(id)) return null;
            const { data } = await apiClient.get(`/sales/customers/${id}/`);
            return data;
        },
        enabled: Boolean(id) && !isNaN(id as number),
        staleTime: STALE_TIME,
    });
};

export const useCreateCustomer = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (customerData: any) => {
            const { data } = await apiClient.post('/sales/customers/', customerData);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['customers'] });
        },
    });
};

export const useUpdateCustomer = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, data }: { id: number; data: any }) => {
            const { data: result } = await apiClient.patch(`/sales/customers/${id}/`, data);
            return result;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['customers'] });
        },
    });
};

export const useDeleteCustomer = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            await apiClient.delete(`/sales/customers/${id}/`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['customers'] });
        },
    });
};

export const useUpdateCustomerCreditLimit = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, credit_limit }: { id: number; credit_limit: number }) => {
            const { data } = await apiClient.patch(`/sales/customers/${id}/`, { credit_limit });
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['customers'] });
        },
    });
};

// ============================================================================
// LEAD HOOKS
// ============================================================================

export const useLeads = (filters = {}) => {
    return useQuery({
        queryKey: ['leads', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/sales/leads/', { params: filters });
            return data.results ?? data;
        },
        staleTime: STALE_TIME,
    });
};

export const useCreateLead = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (leadData: any) => {
            const { data } = await apiClient.post('/sales/leads/', leadData);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['leads'] });
        },
    });
};

export const useUpdateLead = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, data }: { id: number; data: any }) => {
            const { data: result } = await apiClient.patch(`/sales/leads/${id}/`, data);
            return result;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['leads'] });
        },
    });
};

export const useDeleteLead = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            await apiClient.delete(`/sales/leads/${id}/`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['leads'] });
        },
    });
};

// ============================================================================
// OPPORTUNITY HOOKS
// ============================================================================

export const useOpportunities = (filters = {}) => {
    return useQuery({
        queryKey: ['opportunities', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/sales/opportunities/', { params: filters });
            return data.results ?? data;
        },
        staleTime: STALE_TIME,
    });
};

export const useCreateOpportunity = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (oppData: any) => {
            const { data } = await apiClient.post('/sales/opportunities/', oppData);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['opportunities'] });
            queryClient.invalidateQueries({ queryKey: ['sales-forecast'] });
        },
    });
};

export const useUpdateOpportunity = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, data }: { id: number; data: any }) => {
            const { data: result } = await apiClient.patch(`/sales/opportunities/${id}/`, data);
            return result;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['opportunities'] });
            queryClient.invalidateQueries({ queryKey: ['sales-forecast'] });
        },
    });
};

export const useDeleteOpportunity = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            await apiClient.delete(`/sales/opportunities/${id}/`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['opportunities'] });
            queryClient.invalidateQueries({ queryKey: ['sales-forecast'] });
        },
    });
};

export const useSalesForecast = () => {
    return useQuery({
        queryKey: ['sales-forecast'],
        queryFn: async () => {
            const { data } = await apiClient.get('/sales/opportunities/forecast/');
            return data;
        },
        staleTime: STALE_TIME,
    });
};

export const useSalesAnalytics = () => {
    return useQuery({
        queryKey: ['sales-analytics'],
        queryFn: async () => {
            const { data } = await apiClient.get('/sales/analytics/summary/');
            return data;
        },
        staleTime: STALE_TIME,
    });
};

// ============================================================================
// QUOTATION HOOKS
// ============================================================================

export const useQuotations = (filters = {}) => {
    return useQuery({
        queryKey: ['quotations', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/sales/quotations/', { params: filters });
            return data.results ?? data;
        },
        staleTime: STALE_TIME,
    });
};

export const useQuotation = (id?: number) => {
    return useQuery({
        queryKey: ['quotation', id],
        queryFn: async () => {
            if (!id || isNaN(id)) return null;
            const { data } = await apiClient.get(`/sales/quotations/${id}/`);
            return data;
        },
        enabled: Boolean(id) && !isNaN(id as number),
        staleTime: STALE_TIME,
    });
};

export const useCreateQuotation = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (quoteData: any) => {
            const { data } = await apiClient.post('/sales/quotations/', quoteData);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['quotations'] });
        },
    });
};

export const useUpdateQuotation = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, data }: { id: number; data: any }) => {
            const { data: result } = await apiClient.patch(`/sales/quotations/${id}/`, data);
            return result;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['quotations'] });
        },
    });
};

export const useDeleteQuotation = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            await apiClient.delete(`/sales/quotations/${id}/`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['quotations'] });
        },
    });
};

export const useSendQuotation = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            const { data } = await apiClient.post(`/sales/quotations/${id}/send_quotation/`);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['quotations'] });
        },
    });
};

export const useConvertQuotationToOrder = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            const { data } = await apiClient.post(`/sales/quotations/${id}/convert_to_order/`);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['quotations'] });
            queryClient.invalidateQueries({ queryKey: ['sales-orders'] });
        },
    });
};

// ============================================================================
// SALES ORDER HOOKS
// ============================================================================

export const useSalesOrders = (filters = {}) => {
    return useQuery({
        queryKey: ['sales-orders', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/sales/orders/', { params: filters });
            return data.results ?? data;
        },
        staleTime: STALE_TIME,
    });
};

export const useSalesOrder = (id?: number) => {
    return useQuery({
        queryKey: ['sales-order', id],
        queryFn: async () => {
            if (!id || isNaN(id)) return null;
            const { data } = await apiClient.get(`/sales/orders/${id}/`);
            return data;
        },
        enabled: Boolean(id) && !isNaN(id as number),
        staleTime: STALE_TIME,
    });
};

export const useCreateSalesOrder = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (orderData: any) => {
            const { data } = await apiClient.post('/sales/orders/', orderData);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['sales-orders'] });
        },
    });
};

export const useUpdateSalesOrder = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, data }: { id: number; data: any }) => {
            const { data: result } = await apiClient.patch(`/sales/orders/${id}/`, data);
            return result;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['sales-orders'] });
        },
    });
};

export const useDeleteSalesOrder = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            await apiClient.delete(`/sales/orders/${id}/`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['sales-orders'] });
        },
    });
};

export const useApproveSalesOrder = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            const { data } = await apiClient.post(`/sales/orders/${id}/approve_order/`);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['sales-orders'] });
        },
    });
};

export const useRejectSalesOrder = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, reason }: { id: number; reason: string }) => {
            const { data } = await apiClient.post(`/sales/orders/${id}/reject_order/`, { reason });
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['sales-orders'] });
        },
    });
};

export const usePostSalesOrder = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            const { data } = await apiClient.post(`/sales/orders/${id}/post_order/`);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['sales-orders'] });
            queryClient.invalidateQueries({ queryKey: ['journals'] });
            queryClient.invalidateQueries({ queryKey: ['customers'] });
            // SO posting creates a draft CustomerInvoice and updates customer.balance
            queryClient.invalidateQueries({ queryKey: ['customer-invoices'] });
            queryClient.invalidateQueries({ queryKey: ['customer-ledger'] });
        },
    });
};

// ============================================================================
// DELIVERY NOTE HOOKS
// ============================================================================

export const useDeliveryNotes = (filters = {}) => {
    return useQuery({
        queryKey: ['delivery-notes', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/sales/delivery-notes/', { params: filters });
            return data;
        },
        staleTime: STALE_TIME,
    });
};

export const useCreateDeliveryNote = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (dnData: any) => {
            const { data } = await apiClient.post('/sales/delivery-notes/', dnData);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['delivery-notes'] });
        },
    });
};

export const useUpdateDeliveryNote = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, data }: { id: number; data: any }) => {
            const { data: result } = await apiClient.patch(`/sales/delivery-notes/${id}/`, data);
            return result;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['delivery-notes'] });
        },
    });
};

// ============================================================================
// CUSTOMER LEDGER HOOK
// ============================================================================

export const useCustomerLedger = (params: Record<string, any> = {}) => {
    return useQuery({
        queryKey: ['customer-ledger', params],
        queryFn: async () => {
            const { data } = await apiClient.get('/accounting/customer-ledger/', { params });
            return data;
        },
        enabled: !!params.customer,
        staleTime: 2 * 60 * 1000,
    });
};

export const usePostDeliveryNote = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, warehouse_id }: { id: number; warehouse_id: number }) => {
            const { data } = await apiClient.post(`/sales/delivery-notes/${id}/post_delivery/`, { warehouse_id });
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['delivery-notes'] });
            queryClient.invalidateQueries({ queryKey: ['sales-orders'] });
            queryClient.invalidateQueries({ queryKey: ['items'] });
            queryClient.invalidateQueries({ queryKey: ['stock-movements'] });
            queryClient.invalidateQueries({ queryKey: ['inventory-stocks'] });
            // Prefix-match clears all ['inventory-stock', itemId] cached entries too
            queryClient.invalidateQueries({ queryKey: ['inventory-stock'] });
            queryClient.invalidateQueries({ queryKey: ['journals'] });
            // Delivery posting creates AR journal and updates customer invoice status
            queryClient.invalidateQueries({ queryKey: ['customer-invoices'] });
            queryClient.invalidateQueries({ queryKey: ['customer-ledger'] });
            queryClient.invalidateQueries({ queryKey: ['inventory-valuation'] });
        },
    });
};

// ============================================================================
// SALES RETURN HOOKS
// ============================================================================

export const useSalesReturns = (filters = {}) => {
    return useQuery({
        queryKey: ['sales-returns', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/sales/returns/', { params: filters });
            return data.results ?? data;
        },
        staleTime: STALE_TIME,
    });
};

export const useSalesReturn = (id?: number) => {
    return useQuery({
        queryKey: ['sales-return', id],
        queryFn: async () => {
            if (!id || isNaN(id)) return null;
            const { data } = await apiClient.get(`/sales/returns/${id}/`);
            return data;
        },
        enabled: Boolean(id) && !isNaN(id as number),
        staleTime: STALE_TIME,
    });
};

export const useCreateSalesReturn = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (payload: any) => {
            const { data } = await apiClient.post('/sales/returns/', payload);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['sales-returns'] });
            queryClient.invalidateQueries({ queryKey: ['sales-orders'] });
        },
    });
};

export const useUpdateSalesReturn = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, data }: { id: number; data: any }) => {
            const { data: result } = await apiClient.patch(`/sales/returns/${id}/`, data);
            return result;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['sales-returns'] });
        },
    });
};

export const useApproveSalesReturn = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            const { data } = await apiClient.post(`/sales/returns/${id}/approve/`);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['sales-returns'] });
        },
    });
};

export const useProcessSalesReturn = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            const { data } = await apiClient.post(`/sales/returns/${id}/process/`);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['sales-returns'] });
            queryClient.invalidateQueries({ queryKey: ['sales-orders'] });
            // Restores inventory + posts GL reversal
            queryClient.invalidateQueries({ queryKey: ['stock-movements'] });
            queryClient.invalidateQueries({ queryKey: ['inventory-stocks'] });
            queryClient.invalidateQueries({ queryKey: ['inventory-stock'] });
            queryClient.invalidateQueries({ queryKey: ['inventory-valuation'] });
            queryClient.invalidateQueries({ queryKey: ['journals'] });
            queryClient.invalidateQueries({ queryKey: ['customers'] });
            queryClient.invalidateQueries({ queryKey: ['customer-ledger'] });
            queryClient.invalidateQueries({ queryKey: ['customer-invoices'] });
        },
    });
};

// ============================================================================
// CREDIT NOTE HOOKS
// ============================================================================

export const useCreditNotes = (filters = {}) => {
    return useQuery({
        queryKey: ['credit-notes', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/sales/credit-notes/', { params: filters });
            return data.results ?? data;
        },
        staleTime: STALE_TIME,
    });
};

export const useCreditNote = (id?: number) => {
    return useQuery({
        queryKey: ['credit-note', id],
        queryFn: async () => {
            if (!id || isNaN(id)) return null;
            const { data } = await apiClient.get(`/sales/credit-notes/${id}/`);
            return data;
        },
        enabled: Boolean(id) && !isNaN(id as number),
        staleTime: STALE_TIME,
    });
};

export const useCreateCreditNote = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (payload: any) => {
            const { data } = await apiClient.post('/sales/credit-notes/', payload);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['credit-notes'] });
            queryClient.invalidateQueries({ queryKey: ['sales-returns'] });
        },
    });
};

export const useUpdateCreditNote = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, data }: { id: number; data: any }) => {
            const { data: result } = await apiClient.patch(`/sales/credit-notes/${id}/`, data);
            return result;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['credit-notes'] });
        },
    });
};

export const useApproveCreditNote = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            const { data } = await apiClient.post(`/sales/credit-notes/${id}/approve/`);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['credit-notes'] });
        },
    });
};

export const useApplyCreditNote = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            const { data } = await apiClient.post(`/sales/credit-notes/${id}/apply/`);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['credit-notes'] });
            // Applying a credit note posts GL (DR Revenue / CR AR) + reduces customer balance
            queryClient.invalidateQueries({ queryKey: ['journals'] });
            queryClient.invalidateQueries({ queryKey: ['customers'] });
            queryClient.invalidateQueries({ queryKey: ['customer-ledger'] });
            queryClient.invalidateQueries({ queryKey: ['customer-invoices'] });
        },
    });
};
