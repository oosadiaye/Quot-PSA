/**
 * useCustomers hook — replacement for the deleted sales module hook.
 * Fetches customer data from the accounting AR endpoints.
 *
 * In the public sector context, "customers" are revenue payers
 * (taxpayers, fee payers, government debtors).
 */
import { useQuery } from '@tanstack/react-query';
import apiClient from '../../../api/client';

interface Customer {
    id: number;
    name: string;
    customer_code?: string;
    email?: string;
    phone?: string;
    address?: string;
    credit_limit?: number;
    outstanding_balance?: number;
    is_active?: boolean;
}

export function useCustomers() {
    return useQuery<Customer[]>({
        queryKey: ['customers'],
        queryFn: async () => {
            const res = await apiClient.get('/accounting/customer-invoices/', {
                params: { page_size: 9999 },
            });
            const data = res.data;
            return Array.isArray(data) ? data : Array.isArray(data?.results) ? data.results : [];
        },
        staleTime: 5 * 60 * 1000,
    });
}
