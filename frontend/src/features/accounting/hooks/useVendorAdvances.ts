/**
 * Vendor Advance Special-GL hooks.
 *
 * Backed by /api/v1/accounting/vendor-advances/ — the central ledger
 * the popup uses to gate AP / PV / IPC posting against vendors with
 * uncleared advances.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import apiClient from '../../../api/client';

const BASE = '/accounting/vendor-advances/';

export interface VendorAdvance {
    id: number;
    vendor: number;
    vendor_name?: string;
    vendor_code?: string;
    recon_account: number;
    recon_account_code?: string;
    recon_account_name?: string;
    source_type: 'MOBILIZATION' | 'PO_DOWNPAYMENT' | 'AP_DOWNPAYMENT' | 'OTHER';
    source_id?: number | null;
    reference: string;
    amount_paid: string;
    amount_recovered: string;
    amount_outstanding: string;
    status: 'OUTSTANDING' | 'PARTIAL' | 'CLEARED';
    posting_date: string;
    disbursement_journal?: number | null;
    disbursement_journal_reference?: string;
    notes?: string;
    clearances?: VendorAdvanceClearance[];
    created_at?: string;
    updated_at?: string;
}

export interface VendorAdvanceClearance {
    id: number;
    amount: string;
    posting_date: string;
    cleared_against_type?: string;
    cleared_against_id?: number | null;
    cleared_against_reference?: string;
    notes?: string;
    clearing_journal?: number | null;
    journal_reference?: string;
    created_at?: string;
}

export interface OutstandingForVendorResponse {
    vendor_id: number;
    vendor_name: string;
    outstanding_total: string;
    open_advances: VendorAdvance[];
}

/**
 * Compact summary used by the popup. Keyed on vendor id; query is
 * idempotent and inexpensive (one indexed lookup), so callers can
 * mount it freely on any surface that posts against a vendor.
 *
 * Returns ``null`` when ``vendorId`` is falsy so the popup component
 * can render conditionally without a wrapper guard.
 */
export const useOutstandingAdvancesForVendor = (vendorId: number | null | undefined) => {
    return useQuery<OutstandingForVendorResponse | null>({
        queryKey: ['vendor-advances-outstanding', vendorId ?? null],
        queryFn: async () => {
            if (!vendorId) return null;
            const { data } = await apiClient.get(`${BASE}outstanding-for-vendor/`, {
                params: { vendor: vendorId },
            });
            return data;
        },
        enabled: !!vendorId,
        staleTime: 30 * 1000,
    });
};

/**
 * Full list — used by the contract detail page's advance panel and
 * the vendor ledger drill-down.
 */
export const useVendorAdvances = (filters: Record<string, any> = {}) => {
    return useQuery<VendorAdvance[]>({
        queryKey: ['vendor-advances-list', filters],
        queryFn: async () => {
            const { data } = await apiClient.get(BASE, { params: filters });
            return Array.isArray(data) ? data : (data?.results ?? []);
        },
        staleTime: 30 * 1000,
    });
};

/**
 * Single advance with embedded clearance history.
 */
export const useVendorAdvance = (id: number | null | undefined) => {
    return useQuery<VendorAdvance | null>({
        queryKey: ['vendor-advance', id],
        queryFn: async () => {
            if (!id) return null;
            const { data } = await apiClient.get(`${BASE}${id}/`);
            return data;
        },
        enabled: !!id,
    });
};

/**
 * POST /accounting/vendor-advances/{id}/clear/
 *
 * The "Clear Advance" mutation — posts the F-54-equivalent journal
 * (DR Real-AP / CR Vendor-Advance recon) and bumps the advance's
 * recovered counter under row lock.
 */
export const useClearVendorAdvance = () => {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: async ({
            id,
            amount,
            posting_date,
            cleared_against_type,
            cleared_against_id,
            cleared_against_reference,
            notes,
        }: {
            id: number;
            amount: string | number;
            posting_date?: string;
            cleared_against_type?: string;
            cleared_against_id?: number | null;
            cleared_against_reference?: string;
            notes?: string;
        }) => {
            const { data } = await apiClient.post(`${BASE}${id}/clear/`, {
                amount,
                posting_date,
                cleared_against_type,
                cleared_against_id,
                cleared_against_reference,
                notes,
            });
            return data;
        },
        onSuccess: (data) => {
            // Refresh: advance list, single advance, outstanding-for-vendor.
            qc.invalidateQueries({ queryKey: ['vendor-advances-list'] });
            qc.invalidateQueries({ queryKey: ['vendor-advance', data?.id] });
            if (data?.vendor) {
                qc.invalidateQueries({
                    queryKey: ['vendor-advances-outstanding', data.vendor],
                });
            }
            // Cross-module invalidation: clearance posts a journal so
            // any GL drill-down may need refreshing.
            qc.invalidateQueries({ queryKey: ['journals'] });
            qc.invalidateQueries({ queryKey: ['vendor-ledger'] });
        },
    });
};
