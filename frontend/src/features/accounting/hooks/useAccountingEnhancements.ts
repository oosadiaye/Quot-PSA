import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '../../../api/client';
import { invalidateLedgerCaches } from './invalidateLedger';

const DEFAULT_STALE_TIME = 5 * 60 * 1000; // 5 minutes

// ============================================================================
// FORM DATA INTERFACES
// ============================================================================

interface CurrencyFormData {
    code: string;
    name: string;
    symbol: string;
    exchange_rate: string;
    is_base_currency?: boolean;
    is_active?: boolean;
}

interface ExchangeRateFormData {
    from_currency: number;
    to_currency: number;
    rate_date: string;
    rate_valid_from?: string;
    rate_valid_to?: string | null;
    exchange_rate: string;
}

interface ExchangeRateFilters {
    from_currency?: number;
    to_currency?: number;
    rate_date_after?: string;
    rate_date_before?: string;
}

interface CurrencyDefaultsPayload {
    default_currency_1?: number | null;
    default_currency_2?: number | null;
    default_currency_3?: number | null;
    default_currency_4?: number | null;
    default_currency_5?: number | null;
}

interface InvoiceLineFormData {
    account: number;
    description?: string;
    amount: string | number;
    tax_code?: number | null;
    withholding_tax?: number | null;
}

interface VendorInvoiceFormData {
    vendor: number;
    invoice_number: string;
    invoice_date: string;
    due_date: string;
    total_amount: string;
    account: number;
    mda?: number;
    fund?: number;
    function?: number;
    program?: number;
    geo?: number;
    lines?: InvoiceLineFormData[];
}

interface PaymentFormData {
    vendor?: number;
    payment_date: string;
    total_amount: string;
    payment_method: string;
    bank_account?: number;
    reference_number?: string;
}

interface CustomerInvoiceFormData {
    customer: number;
    invoice_number: string;
    invoice_date: string;
    due_date: string;
    total_amount: string;
    account: number;
    mda?: number;
    fund?: number;
    function?: number;
    program?: number;
    geo?: number;
    lines?: InvoiceLineFormData[];
}

interface ReceiptFormData {
    customer?: number;
    receipt_date: string;
    total_amount: string;
    payment_method: string;
    bank_account?: number;
    reference_number?: string;
    // Advance / downpayment fields
    is_advance?: boolean;
    advance_type?: 'Customer Advance' | 'Customer Deposit' | '';
    currency?: number;
    // Linked sales order (optional — for downpayment context)
    sales_order?: number;
}

export interface FixedAssetFormData {
    asset_number: string;
    name: string;
    description?: string;
    asset_category: string;                     // enum on the model (Building, Equipment, Vehicle, IT, Furniture, Land)
    acquisition_date: string;
    acquisition_cost: string;
    salvage_value?: string;
    useful_life_years: number;
    depreciation_method: string;

    // GL accounts (all optional — filled from Asset Category defaults by the backend when blank)
    asset_account?: number | null;
    depreciation_expense_account?: number | null;
    accumulated_depreciation_account?: number | null;

    // Dimensions (mda + fund REQUIRED when dimensions feature-flag is on)
    mda?: number | null;
    fund?: number | null;
    function?: number | null;
    program?: number | null;
    geo?: number | null;

    status?: string;
}

interface AssetCategoryFormData {
    name: string;
    code: string;
    is_active?: boolean;
    depreciation_method: string;
    default_life_years: number;
    residual_value_type?: string;
    residual_value?: string | number;
    cost_account?: number | string | null;
    accumulated_depreciation_account?: number | string | null;
    depreciation_expense_account?: number | string | null;
}

interface TaxCodeFormData {
    code: string;
    name: string;
    tax_type: string;
    direction: string;
    rate: string;
    tax_account: number;
    is_active?: boolean;
    description?: string;
}

interface WithholdingTaxFormData {
    code: string;
    name: string;
    income_type: string;
    rate: string;
    withholding_account: number;
    is_active?: boolean;
}

// ============================================================================
// CURRENCY HOOKS
// ============================================================================

export const useCurrencies = () => {
    return useQuery({
        queryKey: ['currencies'],
        queryFn: async () => {
            const { data } = await apiClient.get('/accounting/currencies/');
            return data.results;
        },
        staleTime: DEFAULT_STALE_TIME,
        retry: false,
    });
};

export const useCreateCurrency = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (currencyData: CurrencyFormData) => {
            const { data } = await apiClient.post('/accounting/currencies/', currencyData);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['currencies'] });
        },
    });
};

export const useUpdateCurrency = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, ...currencyData }: CurrencyFormData & { id: number }) => {
            const { data } = await apiClient.put(`/accounting/currencies/${id}/`, currencyData);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['currencies'] });
        },
    });
};

export const useDeleteCurrency = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            await apiClient.delete(`/accounting/currencies/${id}/`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['currencies'] });
        },
    });
};

// ============================================================================
// EXCHANGE RATE HOOKS
// ============================================================================

export const useExchangeRates = (filters: ExchangeRateFilters = {}) => {
    return useQuery({
        queryKey: ['exchange-rates', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/accounting/exchange-rates/', { params: filters });
            return data.results;
        },
        staleTime: DEFAULT_STALE_TIME,
        retry: false,
    });
};

export const useCreateExchangeRate = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (rateData: ExchangeRateFormData) => {
            const { data } = await apiClient.post('/accounting/exchange-rates/', rateData);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['exchange-rates'] });
        },
    });
};

export const useUpdateExchangeRate = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, ...rateData }: ExchangeRateFormData & { id: number }) => {
            const { data } = await apiClient.patch(`/accounting/exchange-rates/${id}/`, rateData);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['exchange-rates'] });
        },
    });
};

export const useDeleteExchangeRate = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            await apiClient.delete(`/accounting/exchange-rates/${id}/`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['exchange-rates'] });
        },
    });
};

// ── Exchange Rate Import / Export helpers ──────────────────────────────────

export const downloadExchangeRateTemplate = async () => {
    const { data } = await apiClient.get('/accounting/exchange-rates/import-template/', { responseType: 'blob' });
    const url = URL.createObjectURL(data);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'exchange_rate_import_template.csv';
    a.click();
    URL.revokeObjectURL(url);
};

export const exportExchangeRates = async () => {
    const { data } = await apiClient.get('/accounting/exchange-rates/export/', { responseType: 'blob' });
    const url = URL.createObjectURL(data);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'exchange_rates_export.csv';
    a.click();
    URL.revokeObjectURL(url);
};

export const useBulkImportExchangeRates = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (file: File) => {
            const formData = new FormData();
            formData.append('file', file);
            const { data } = await apiClient.post('/accounting/exchange-rates/bulk-import/', formData);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['exchange-rates'] });
        },
    });
};

// ============================================================================
// DEFAULT CURRENCY HOOKS
// ============================================================================

export const useDefaultCurrencies = () => {
    return useQuery({
        queryKey: ['currency-defaults'],
        queryFn: async () => {
            const { data } = await apiClient.get('/accounting/currencies/defaults/');
            return data;
        },
        staleTime: DEFAULT_STALE_TIME,
        retry: false,
    });
};

export const useSaveDefaultCurrencies = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (defaults: CurrencyDefaultsPayload) => {
            const { data } = await apiClient.put('/accounting/currencies/defaults/', defaults);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['currency-defaults'] });
            queryClient.invalidateQueries({ queryKey: ['accounting-settings'] });
        },
    });
};

export const useConvertCurrency = () => {
    return useMutation({
        mutationFn: async (params: { amount: number; from_currency: string; to_currency: string; date?: string }) => {
            const { data } = await apiClient.post('/accounting/currencies/convert/', params);
            return data;
        },
    });
};

// ============================================================================
// ACCOUNTS PAYABLE HOOKS
// ============================================================================

export const useVendorInvoices = (filters = {}) => {
    return useQuery({
        queryKey: ['vendor-invoices', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/accounting/vendor-invoices/', { params: filters });
            return data.results;
        },
        staleTime: DEFAULT_STALE_TIME,
        retry: false,
    });
};

export const useCreateVendorInvoice = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (invoiceData: VendorInvoiceFormData | FormData) => {
            const { data } = await apiClient.post('/accounting/vendor-invoices/', invoiceData);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['vendor-invoices'] });
        },
    });
};

/**
 * Full update of a Draft vendor invoice (header + lines).
 * Backend (payables.py) rejects with 400 if status !== 'Draft'.
 */
export const useUpdateVendorInvoice = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, payload }: { id: number; payload: VendorInvoiceFormData | FormData }) => {
            const { data } = await apiClient.put(`/accounting/vendor-invoices/${id}/`, payload);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['vendor-invoices'] });
            queryClient.invalidateQueries({ queryKey: ['vendor-invoice-detail'] });
        },
    });
};

/** Single vendor invoice fetch for hydrating the edit form. */
export const useVendorInvoiceDetail = (id: number | null) => {
    return useQuery({
        queryKey: ['vendor-invoice-detail', id],
        queryFn: async () => {
            const { data } = await apiClient.get(`/accounting/vendor-invoices/${id}/`);
            return data;
        },
        enabled: !!id,
    });
};

export const useApproveVendorInvoice = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (invoiceId: number) => {
            const { data } = await apiClient.post(`/accounting/vendor-invoices/${invoiceId}/approve_invoice/`);
            return data;
        },
        onSuccess: () => {
            // approve_invoice posts a GL journal — every report and
            // balance derived from the GL must refresh on next paint.
            queryClient.invalidateQueries({ queryKey: ['vendor-invoices'] });
            invalidateLedgerCaches(queryClient);
        },
    });
};

/**
 * Auto-create a draft Payment Voucher from a vendor invoice. Returns
 * ``{invoice, payment_voucher: {id, voucher_number, ...}}`` so the
 * caller can navigate straight to the new PV detail page.
 *
 * Idempotent: re-calling for the same invoice returns the existing
 * linked PV instead of creating a duplicate.
 */
export const useCreateDraftVoucherFromInvoice = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ invoiceId }: { invoiceId: number }) => {
            const { data } = await apiClient.post(
                `/accounting/vendor-invoices/${invoiceId}/create-draft-voucher/`,
                {},
            );
            return data as {
                invoice: { id: number; invoice_number: string; status: string };
                payment_voucher: {
                    id: number; voucher_number: string; status: string;
                    gross_amount: string; net_amount: string;
                };
            };
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['vendor-invoices'] });
            queryClient.invalidateQueries({ queryKey: ['payment-vouchers'] });
            queryClient.invalidateQueries({ queryKey: ['generic-list', '/accounting/payment-vouchers/'] });
        },
    });
};

/**
 * Same factory, but reached via an InvoiceMatching (verification) row.
 * Backend resolves the linked vendor invoice and delegates to the
 * shared :func:`create_draft_voucher_from_invoice`.
 */
export const useCreateDraftVoucherFromMatching = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ matchingId }: { matchingId: number }) => {
            const { data } = await apiClient.post(
                `/procurement/invoice-matching/${matchingId}/create-draft-voucher/`,
                {},
            );
            return data as {
                invoice_matching: { id: number; verification_number: string; status: string };
                payment_voucher: {
                    id: number; voucher_number: string; status: string;
                    gross_amount: string; net_amount: string;
                };
            };
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['invoice-matchings'] });
            queryClient.invalidateQueries({ queryKey: ['payment-vouchers'] });
            queryClient.invalidateQueries({ queryKey: ['generic-list', '/accounting/payment-vouchers/'] });
        },
    });
};

export const usePostCreditMemo = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (invoiceId: number) => {
            const { data } = await apiClient.post(`/accounting/vendor-invoices/${invoiceId}/post_credit_memo/`);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['vendor-invoices'] });
            invalidateLedgerCaches(queryClient);
        },
    });
};

export const usePayments = (filters = {}) => {
    return useQuery({
        queryKey: ['payments', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/accounting/payments/', { params: filters });
            return data.results;
        },
        staleTime: DEFAULT_STALE_TIME,
        retry: false,
    });
};

export const useCreatePayment = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (paymentData: PaymentFormData) => {
            const { data } = await apiClient.post('/accounting/payments/', paymentData);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['payments'] });
            queryClient.invalidateQueries({ queryKey: ['vendor-invoices'] });
        },
    });
};

export const usePostPayment = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (paymentId: number) => {
            const { data } = await apiClient.post(`/accounting/payments/${paymentId}/post_payment/`);
            return data;
        },
        onSuccess: () => {
            // Posting a Payment triggers a cascade that flips the
            // linked PV → PAID, the source VendorInvoice → Paid, the
            // verification's vendor_invoice_status, and any contract
            // IPC linked through the PV → PAID. Invalidate every list
            // / detail surface that renders these so the UI mirrors
            // the new state on the next paint.
            queryClient.invalidateQueries({ queryKey: ['payments'] });
            queryClient.invalidateQueries({ queryKey: ['vendor-invoices'] });
            queryClient.invalidateQueries({ queryKey: ['payment-vouchers'] });
            queryClient.invalidateQueries({ queryKey: ['payment-voucher-detail'] });
            queryClient.invalidateQueries({ queryKey: ['ipcs'] });
            queryClient.invalidateQueries({ queryKey: ['ipc'] });
            queryClient.invalidateQueries({ queryKey: ['contract-balance'] });
            queryClient.invalidateQueries({ queryKey: ['invoice-matchings'] });
            invalidateLedgerCaches(queryClient);
        },
    });
};

export const useDeletePayment = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (paymentId: number) => {
            await apiClient.delete(`/accounting/payments/${paymentId}/`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['payments'] });
            queryClient.invalidateQueries({ queryKey: ['vendor-invoices'] });
        },
    });
};

export const useCreatePaymentAllocation = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (data: { payment: number; invoice: number; amount: string }) => {
            const res = await apiClient.post('/accounting/payment-allocations/', data);
            return res.data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['payments'] });
            queryClient.invalidateQueries({ queryKey: ['vendor-invoices'] });
        },
    });
};

// ============================================================================
// ACCOUNTS RECEIVABLE HOOKS
// ============================================================================

export const useCustomerInvoices = (filters = {}) => {
    return useQuery({
        queryKey: ['customer-invoices', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/accounting/customer-invoices/', { params: filters });
            return data.results;
        },
        staleTime: DEFAULT_STALE_TIME,
        retry: false,
    });
};

export const useCreateCustomerInvoice = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (invoiceData: CustomerInvoiceFormData) => {
            const { data } = await apiClient.post('/accounting/customer-invoices/', invoiceData);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['customer-invoices'] });
        },
    });
};

export const useSendCustomerInvoice = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (invoiceId: number) => {
            const { data } = await apiClient.post(`/accounting/customer-invoices/${invoiceId}/send_invoice/`);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['customer-invoices'] });
        },
    });
};

export const useDeleteCustomerInvoice = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (invoiceId: number) => {
            await apiClient.delete(`/accounting/customer-invoices/${invoiceId}/`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['customer-invoices'] });
        },
    });
};

export const usePostCustomerCreditMemo = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (invoiceId: number) => {
            const { data } = await apiClient.post(`/accounting/customer-invoices/${invoiceId}/post_credit_memo/`);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['customer-invoices'] });
            invalidateLedgerCaches(queryClient);
        },
    });
};

export const useReceipts = (filters = {}) => {
    return useQuery({
        queryKey: ['receipts', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/accounting/receipts/', { params: filters });
            return data.results;
        },
        staleTime: DEFAULT_STALE_TIME,
        retry: false,
    });
};

export const useCreateReceipt = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (receiptData: ReceiptFormData) => {
            const { data } = await apiClient.post('/accounting/receipts/', receiptData);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['receipts'] });
            queryClient.invalidateQueries({ queryKey: ['customer-invoices'] });
        },
    });
};

export const usePostReceipt = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (receiptId: number) => {
            const { data } = await apiClient.post(`/accounting/receipts/${receiptId}/post_receipt/`);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['receipts'] });
            queryClient.invalidateQueries({ queryKey: ['customer-invoices'] });
            invalidateLedgerCaches(queryClient);
        },
    });
};

export const useDeleteReceipt = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (receiptId: number) => {
            await apiClient.delete(`/accounting/receipts/${receiptId}/`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['receipts'] });
        },
    });
};

export const useCreateReceiptAllocation = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (payload: { receipt: number; invoice: number; amount: string }) => {
            const { data } = await apiClient.post('/accounting/receipt-allocations/', payload);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['receipts'] });
            queryClient.invalidateQueries({ queryKey: ['customer-invoices'] });
        },
    });
};

export const useAccountingSettings = () => {
    return useQuery({
        queryKey: ['accounting-settings'],
        queryFn: async () => {
            const { data } = await apiClient.get('/accounting/settings/');
            return data;
        },
        staleTime: DEFAULT_STALE_TIME,
    });
};

export const useUpdateAccountingSettings = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (payload: Record<string, any>) => {
            const { data } = await apiClient.patch('/accounting/settings/', payload);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['accounting-settings'] });
        },
    });
};

// ============================================================================
// FIXED ASSETS HOOKS
// ============================================================================

export const useFixedAssets = (filters = {}) => {
    return useQuery({
        queryKey: ['fixed-assets', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/accounting/fixed-assets/', { params: filters });
            return data.results;
        },
        staleTime: DEFAULT_STALE_TIME,
        retry: false,
    });
};

export const useCreateFixedAsset = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (assetData: FixedAssetFormData) => {
            const { data } = await apiClient.post('/accounting/fixed-assets/', assetData);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['fixed-assets'] });
        },
    });
};

export const useCalculateDepreciation = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ assetId, period_date }: { assetId: number; period_date: string }) => {
            const { data } = await apiClient.post(`/accounting/fixed-assets/${assetId}/calculate_depreciation/`, { period_date });
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['fixed-assets'] });
        },
    });
};

export const usePostDepreciation = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ assetId, period_date }: { assetId: number; period_date: string }) => {
            const { data } = await apiClient.post(
                `/accounting/fixed-assets/${assetId}/post_depreciation/`,
                { period_date }
            );
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['fixed-assets'] });
            invalidateLedgerCaches(queryClient);
        },
    });
};

export const useBulkDepreciation = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (payload: { period_date: string; asset_ids?: number[]; simulate: boolean }) => {
            const { data } = await apiClient.post('/accounting/fixed-assets/bulk-depreciation/', payload);
            return data;
        },
        onSuccess: (data: any) => {
            if (data.mode === 'posted') {
                queryClient.invalidateQueries({ queryKey: ['fixed-assets'] });
                invalidateLedgerCaches(queryClient);
            }
        },
    });
};

// ============================================================================
// DEPRECIATION RUN SCHEDULE — monthly auto-depreciation
// ============================================================================

export interface DepreciationSchedule {
    id: number;
    is_active: boolean;
    day_of_month: number;
    last_run_at: string | null;
    last_run_period_date: string | null;
    last_run_assets_posted: number;
    last_run_total_amount: string;
    last_run_skipped: number;
    last_run_error: string;
    next_run_date: string | null;
    created_at: string;
    updated_at: string;
}

/** Return the single (or first) schedule row on this tenant.
 *  Typical deployment is one schedule per tenant. */
export const useDepreciationSchedule = () => {
    return useQuery<DepreciationSchedule | null>({
        queryKey: ['depreciation-schedule'],
        queryFn: async () => {
            const { data } = await apiClient.get('/accounting/depreciation-schedules/', {
                params: { page_size: 1 },
            });
            const list = Array.isArray(data) ? data : (data?.results || []);
            return list.length ? list[0] : null;
        },
        staleTime: 30_000,
    });
};

export const useSaveDepreciationSchedule = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (payload: { id?: number; is_active: boolean; day_of_month: number }) => {
            if (payload.id) {
                const { data } = await apiClient.patch(
                    `/accounting/depreciation-schedules/${payload.id}/`,
                    { is_active: payload.is_active, day_of_month: payload.day_of_month },
                );
                return data;
            }
            const { data } = await apiClient.post(
                '/accounting/depreciation-schedules/',
                { is_active: payload.is_active, day_of_month: payload.day_of_month },
            );
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['depreciation-schedule'] });
        },
    });
};

export const useRunScheduleNow = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (payload: { id: number; simulate: boolean; period_date?: string }) => {
            const { data } = await apiClient.post(
                `/accounting/depreciation-schedules/${payload.id}/run-now/`,
                {
                    simulate: payload.simulate,
                    ...(payload.period_date ? { period_date: payload.period_date } : {}),
                },
            );
            return data;
        },
        onSuccess: (data: any) => {
            if (data?.mode === 'posted') {
                queryClient.invalidateQueries({ queryKey: ['fixed-assets'] });
                invalidateLedgerCaches(queryClient);
            }
            queryClient.invalidateQueries({ queryKey: ['depreciation-schedule'] });
        },
    });
};

// ============================================================================
// ASSET CATEGORY HOOKS
// ============================================================================

export const useAssetCategories = (filters: Record<string, unknown> = {}) => {
    return useQuery({
        queryKey: ['asset-categories', filters],
        queryFn: async () => {
            // Fetch the full catalogue in one call. Without an explicit
            // page_size, DRF defaults to PAGE_SIZE=20 — the AssetCategories
            // page does *client-side* pagination + search, so it needs the
            // whole list up-front. Otherwise search "finds nothing" the
            // moment a matching row sits past row 20, and the page
            // selector can never advance past page 1. Cap is enforced
            // server-side by AccountingPagination.max_page_size=10000.
            const { data } = await apiClient.get('/accounting/asset-categories/', {
                params: { page_size: 10000, ...filters },
            });
            // Tolerate both paginated `{results}` and plain-array shapes.
            return Array.isArray(data) ? data : (data?.results ?? []);
        },
        staleTime: DEFAULT_STALE_TIME,
        retry: false,
    });
};

export const useCreateAssetCategory = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (categoryData: AssetCategoryFormData) => {
            const { data } = await apiClient.post('/accounting/asset-categories/', categoryData);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['asset-categories'] });
        },
    });
};

export const useUpdateAssetCategory = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, ...categoryData }: AssetCategoryFormData & { id: number }) => {
            const { data } = await apiClient.put(`/accounting/asset-categories/${id}/`, categoryData);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['asset-categories'] });
        },
    });
};

export const useDeleteAssetCategory = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            await apiClient.delete(`/accounting/asset-categories/${id}/`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['asset-categories'] });
        },
    });
};

// ============================================================================
// TAX CODE HOOKS
// ============================================================================

export const useTaxCodes = (filters: Record<string, unknown> = {}) => {
    return useQuery({
        // 'v2' suffix busts any TanStack Query cache that was populated
        // before the response-shape hardening below — without it,
        // browsers that already loaded the page would keep serving the
        // (empty) prior result for up to staleTime regardless of the
        // new queryFn behaviour.
        queryKey: ['tax-codes', 'v2', filters],
        queryFn: async () => {
            // Explicit page_size defeats DRF's PAGE_SIZE=20 default;
            // tolerant unwrapper handles both paginated and array shapes
            // so the dropdown never silently shows zero options.
            const { data } = await apiClient.get('/accounting/tax-codes/', {
                params: { page_size: 10000, ...filters },
            });
            return Array.isArray(data) ? data : (data?.results ?? []);
        },
        staleTime: DEFAULT_STALE_TIME,
        // Reference-data dropdowns: always refetch on mount so
        // operators see the latest tax codes immediately after they're
        // added in Settings, without waiting for staleTime to expire.
        refetchOnMount: 'always',
        retry: false,
    });
};

export const useCreateTaxCode = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (taxCodeData: TaxCodeFormData) => {
            const { data } = await apiClient.post('/accounting/tax-codes/', taxCodeData);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['tax-codes'] });
        },
    });
};

export const useUpdateTaxCode = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, ...taxCodeData }: TaxCodeFormData & { id: number }) => {
            const { data } = await apiClient.put(`/accounting/tax-codes/${id}/`, taxCodeData);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['tax-codes'] });
        },
    });
};

export const useDeleteTaxCode = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            await apiClient.delete(`/accounting/tax-codes/${id}/`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['tax-codes'] });
        },
    });
};

// ============================================================================
// WITHHOLDING TAX HOOKS
// ============================================================================

export const useWithholdingTaxes = (filters: Record<string, unknown> = {}) => {
    return useQuery({
        // 'v2' suffix forces a refetch through the hardened code path
        // for clients that have stale empty results cached from prior
        // staleTime windows.
        queryKey: ['withholding-taxes', 'v2', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/accounting/withholding-taxes/', {
                params: { page_size: 10000, ...filters },
            });
            return Array.isArray(data) ? data : (data?.results ?? []);
        },
        staleTime: DEFAULT_STALE_TIME,
        refetchOnMount: 'always',
        retry: false,
    });
};

export const useCreateWithholdingTax = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (whtData: WithholdingTaxFormData) => {
            const { data } = await apiClient.post('/accounting/withholding-taxes/', whtData);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['withholding-taxes'] });
        },
    });
};

export const useUpdateWithholdingTax = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, ...whtData }: WithholdingTaxFormData & { id: number }) => {
            const { data } = await apiClient.put(`/accounting/withholding-taxes/${id}/`, whtData);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['withholding-taxes'] });
        },
    });
};

export const useDeleteWithholdingTax = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            await apiClient.delete(`/accounting/withholding-taxes/${id}/`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['withholding-taxes'] });
        },
    });
};

// ============================================================================
// GL BALANCE HOOKS (REPORTING)
// ============================================================================

export const useGLBalances = (filters: Record<string, any> = {}) => {
    return useQuery({
        queryKey: ['gl-balances', filters],
        queryFn: async () => {
            // Two corrections vs the legacy call:
            //   1. Translate ``fiscal_period`` (the legacy frontend
            //      param name) to ``period`` so the backend
            //      ``filterset_fields = ['fiscal_year', 'period', ...]``
            //      actually applies the filter — previously it was
            //      silently dropped, so every page was the FY total
            //      paginated.
            //   2. Request the full page in one shot via
            //      ``page_size=10000`` (matches AccountingPagination's
            //      max). Without this, GLBalanceViewSet returns 20
            //      rows on the first page and the SPA computes
            //      totals over only that subset — unbalanced
            //      "partial-page" sums on the GL Reports screen.
            const { fiscal_period, period, page_size, ...rest } = filters;
            const params: Record<string, any> = { ...rest, page_size: page_size ?? 10000 };
            const periodValue = period ?? fiscal_period;
            if (periodValue !== undefined && periodValue !== null && periodValue !== '') {
                params.period = periodValue;
            }
            const { data } = await apiClient.get('/accounting/gl-balances/', { params });
            // Paginated response → ``results``; non-paginated → array.
            return Array.isArray(data) ? data : (data?.results ?? []);
        },
        staleTime: DEFAULT_STALE_TIME,
        retry: false,
    });
};

// ============================================================================
// PETTY CASH HOOKS
// ============================================================================

export const usePettyCashFunds = (filters: Record<string, any> = {}) => {
    return useQuery({
        queryKey: ['petty-cash-funds', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/accounting/petty-cash-funds/', { params: filters });
            return data.results || data;
        },
        staleTime: DEFAULT_STALE_TIME,
        retry: false,
    });
};

export const useCreatePettyCashFund = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (payload: any) => {
            const { data } = await apiClient.post('/accounting/petty-cash-funds/', payload);
            return data;
        },
        onSuccess: () => queryClient.invalidateQueries({ queryKey: ['petty-cash-funds'] }),
    });
};

export const useUpdatePettyCashFund = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, ...payload }: any) => {
            const { data } = await apiClient.patch(`/accounting/petty-cash-funds/${id}/`, payload);
            return data;
        },
        onSuccess: () => queryClient.invalidateQueries({ queryKey: ['petty-cash-funds'] }),
    });
};

export const usePettyCashVouchers = (filters: Record<string, any> = {}) => {
    return useQuery({
        queryKey: ['petty-cash-vouchers', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/accounting/petty-cash-vouchers/', { params: filters });
            return data.results || data;
        },
        staleTime: DEFAULT_STALE_TIME,
        retry: false,
    });
};

export const useCreatePettyCashVoucher = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (payload: any) => {
            const { data } = await apiClient.post('/accounting/petty-cash-vouchers/', payload);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['petty-cash-vouchers'] });
            queryClient.invalidateQueries({ queryKey: ['petty-cash-funds'] });
        },
    });
};

export const useApprovePettyCashVoucher = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (voucherId: number) => {
            const { data } = await apiClient.post(`/accounting/petty-cash-vouchers/${voucherId}/approve/`);
            return data;
        },
        onSuccess: () => queryClient.invalidateQueries({ queryKey: ['petty-cash-vouchers'] }),
    });
};

export const usePayPettyCashVoucher = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (voucherId: number) => {
            const { data } = await apiClient.post(`/accounting/petty-cash-vouchers/${voucherId}/pay/`);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['petty-cash-vouchers'] });
            queryClient.invalidateQueries({ queryKey: ['petty-cash-funds'] });
            invalidateLedgerCaches(queryClient);
        },
    });
};

export const usePettyCashReplenishments = (filters: Record<string, any> = {}) => {
    return useQuery({
        queryKey: ['petty-cash-replenishments', filters],
        queryFn: async () => {
            const { data } = await apiClient.get('/accounting/petty-cash-replenishments/', { params: filters });
            return data.results || data;
        },
        staleTime: DEFAULT_STALE_TIME,
        retry: false,
    });
};

export const useCreatePettyCashReplenishment = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (payload: any) => {
            const { data } = await apiClient.post('/accounting/petty-cash-replenishments/', payload);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['petty-cash-replenishments'] });
            queryClient.invalidateQueries({ queryKey: ['petty-cash-funds'] });
        },
    });
};

export const usePostPettyCashReplenishment = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            const { data } = await apiClient.post(`/accounting/petty-cash-replenishments/${id}/post_replenishment/`);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['petty-cash-replenishments'] });
            queryClient.invalidateQueries({ queryKey: ['petty-cash-funds'] });
            invalidateLedgerCaches(queryClient);
        },
    });
};
