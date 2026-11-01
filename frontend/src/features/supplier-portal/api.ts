import apiClient from '../../api/client';

export interface BankChange {
  id: number;
  bank_name: string;
  bank_account_number: string;
  bank_sort_code: string;
  status: 'pending' | 'approved' | 'rejected';
  reason: string;
  created_at: string;
  decided_at: string | null;
}

export interface SupplierProfile {
  name: string;
  code: string;
  tax_id: string;
  email: string;
  phone: string;
  address: string;
  registration_number: string;
  registration_status: string;
  expiry_date: string | null;
  bank_name: string;
  bank_account_masked: string;
  bank_sort_code: string;
  pending_bank_change: BankChange | null;
}

export interface OrderSummary {
  id: number;
  po_number: string;
  order_date: string;
  expected_delivery_date: string | null;
  status: string;
  total_amount: string | number;
  acknowledged_at: string | null;
}

export interface OrderLine {
  description: string;
  quantity: string | number;
  quantity_received: string | number;
  unit_price: string | number;
  total_price: string | number;
}

export interface OrderDetail extends OrderSummary {
  delivery_address: string;
  payment_terms: string;
  terms_and_conditions: string;
  lines: OrderLine[];
}

export interface InvoiceRow {
  id: number;
  invoice_number: string;
  invoice_date: string;
  due_date: string;
  total_amount: string | number;
  paid_amount: string | number;
  status: string;
}

export interface PaymentRow {
  id: number;
  payment_number: string;
  payment_date: string;
  total_amount: string | number;
  status: string;
}

const BASE = '/supplier-portal';

export const supplierApi = {
  profile: async (): Promise<SupplierProfile> => (await apiClient.get(`${BASE}/me/`)).data,
  updateProfile: async (body: Partial<Pick<SupplierProfile, 'email' | 'phone' | 'address'>>): Promise<SupplierProfile> =>
    (await apiClient.patch(`${BASE}/me/`, body)).data,
  orders: async (): Promise<OrderSummary[]> => (await apiClient.get(`${BASE}/orders/`)).data,
  order: async (id: number): Promise<OrderDetail> => (await apiClient.get(`${BASE}/orders/${id}/`)).data,
  acknowledge: async (id: number, note: string): Promise<OrderSummary> =>
    (await apiClient.post(`${BASE}/orders/${id}/acknowledge/`, { note })).data,
  invoices: async (): Promise<InvoiceRow[]> => (await apiClient.get(`${BASE}/invoices/`)).data,
  payments: async (): Promise<PaymentRow[]> => (await apiClient.get(`${BASE}/payments/`)).data,
  bankChanges: async (): Promise<BankChange[]> => (await apiClient.get(`${BASE}/bank-changes/`)).data,
  requestBankChange: async (body: { bank_name: string; bank_account_number: string; bank_sort_code: string }): Promise<BankChange> =>
    (await apiClient.post(`${BASE}/bank-changes/`, body)).data,
};

/** The message a supplier should read for a failed call. */
export function portalError(e: unknown): string {
  const data = (e as { response?: { data?: Record<string, unknown> } })?.response?.data;
  if (data) {
    if (typeof data.error === 'string') return data.error;
    const first = Object.values(data)[0];
    if (Array.isArray(first) && typeof first[0] === 'string') return first[0];
    if (typeof first === 'string') return first;
  }
  return 'Something went wrong. Try again, and tell the procurement office if it keeps happening.';
}
