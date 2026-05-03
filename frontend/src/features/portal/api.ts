import apiClient from '../../api/client';

export interface PortalEmployee {
  id: number;
  employee_number: string;
  full_name: string;
  email: string;
  personal_info: Record<string, unknown>;
  department: string | null;
  position: string | null;
  employee_type: string;
  hire_date: string;
  confirmation_date: string | null;
  status: string;
  emergency_contact_name: string;
  emergency_contact_phone: string;
  emergency_contact_relation: string;
  bank_name: string;
  bank_account_last4: string;
}

export interface PortalPayslipLine {
  id: number;
  period_label: string;
  period_start: string;
  period_end: string;
  payment_date: string;
  run_number: string;
  run_status: string;
  basic_salary: string;
  gross_salary: string;
  total_deductions: string;
  net_salary: string;
  earnings?: Array<{ name: string; amount: string }>;
  deductions?: Array<{ name: string; amount: string }>;
  tax_deduction?: string;
  pension_deduction?: string;
  other_deductions?: string;
  overtime_hours?: string;
  overtime_amount?: string;
}

export interface PortalLeaveBalance {
  id: number;
  leave_type: string;
  leave_type_id: number;
  year: number;
  allocated: number;
  taken: number;
  balance: number;
}

export interface PortalLeaveRequest {
  id: number;
  leave_type: string;
  leave_type_id: number;
  start_date: string;
  end_date: string;
  total_days: string;
  reason: string;
  status: 'Draft' | 'Pending' | 'Approved' | 'Rejected' | 'Cancelled';
  comments: string;
  approved_date: string | null;
  created_at?: string;
}

export interface PortalDashboard {
  employee: PortalEmployee;
  latest_payslip: PortalPayslipLine | null;
  leave_balances: PortalLeaveBalance[];
  pending_leave_requests: number;
  upcoming_leave: PortalLeaveRequest | null;
}

export interface LeaveRequestCreate {
  leave_type_id: number;
  start_date: string;
  end_date: string;
  reason: string;
}

export interface ProfilePatch {
  emergency_contact_name?: string;
  emergency_contact_phone?: string;
  emergency_contact_relation?: string;
  personal_info?: Record<string, unknown>;
}

export const portalApi = {
  getDashboard: (): Promise<PortalDashboard> =>
    apiClient.get<PortalDashboard>('/my/dashboard').then((r) => r.data),

  getProfile: (): Promise<PortalEmployee> =>
    apiClient.get<PortalEmployee>('/my/profile').then((r) => r.data),

  updateProfile: (patch: ProfilePatch): Promise<PortalEmployee> =>
    apiClient.patch<PortalEmployee>('/my/profile', patch).then((r) => r.data),

  getPayslips: (): Promise<{ results: PortalPayslipLine[] }> =>
    apiClient
      .get<{ results: PortalPayslipLine[] }>('/my/payslips')
      .then((r) => r.data),

  getPayslip: (id: number): Promise<PortalPayslipLine> =>
    apiClient.get<PortalPayslipLine>(`/my/payslips/${id}`).then((r) => r.data),

  downloadPayslipPdf: async (id: number, filenameHint: string): Promise<void> => {
    const response = await apiClient.get(`/my/payslips/${id}/pdf`, {
      responseType: 'blob',
    });
    const blob = new Blob([response.data as BlobPart], { type: 'application/pdf' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filenameHint;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  },

  getLeaveTypes: (): Promise<{
    results: Array<{ id: number; name: string; code: string; max_days_per_year: number; is_paid: boolean }>;
  }> => apiClient.get('/my/leave/types').then((r) => r.data),

  getLeaveBalances: (year?: number): Promise<{ year: number; results: PortalLeaveBalance[] }> =>
    apiClient
      .get('/my/leave/balances', { params: year ? { year } : undefined })
      .then((r) => r.data),

  getLeaveRequests: (): Promise<{ results: PortalLeaveRequest[] }> =>
    apiClient.get<{ results: PortalLeaveRequest[] }>('/my/leave/requests').then((r) => r.data),

  createLeaveRequest: (payload: LeaveRequestCreate): Promise<PortalLeaveRequest> =>
    apiClient.post<PortalLeaveRequest>('/my/leave/requests', payload).then((r) => r.data),

  cancelLeaveRequest: (id: number): Promise<PortalLeaveRequest> =>
    apiClient
      .post<PortalLeaveRequest>(`/my/leave/requests/${id}/cancel`, {})
      .then((r) => r.data),

  // -- Documents -----------------------------------------------------------
  getDocuments: (): Promise<{ results: PortalDocument[] }> =>
    apiClient.get<{ results: PortalDocument[] }>('/my/documents').then((r) => r.data),

  uploadDocument: async (payload: DocumentUpload): Promise<PortalDocument> => {
    const form = new FormData();
    form.append('file', payload.file);
    form.append('category', payload.category);
    if (payload.title) form.append('title', payload.title);
    if (payload.issued_on) form.append('issued_on', payload.issued_on);
    if (payload.expires_on) form.append('expires_on', payload.expires_on);
    const response = await apiClient.post<PortalDocument>('/my/documents', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  },

  deleteDocument: (id: number): Promise<void> =>
    apiClient.delete(`/my/documents/${id}`).then(() => undefined),

  // -- Verification --------------------------------------------------------
  getVerificationCycles: (): Promise<{ results: PortalVerificationSubmission[] }> =>
    apiClient
      .get<{ results: PortalVerificationSubmission[] }>('/my/verification/cycles')
      .then((r) => r.data),

  submitVerification: (
    cycleId: number,
    payload: VerificationSubmitPayload,
  ): Promise<PortalVerificationSubmission> =>
    apiClient
      .post<PortalVerificationSubmission>(
        `/my/verification/cycles/${cycleId}/submit`,
        payload,
      )
      .then((r) => r.data),
};

// ---------------------------------------------------------------------------
// Documents & Verification types
// ---------------------------------------------------------------------------

export type DocumentCategory =
  | 'national_id'
  | 'passport'
  | 'drivers_license'
  | 'nin_proof'
  | 'bvn_proof'
  | 'academic_certificate'
  | 'professional_cert'
  | 'appointment_letter'
  | 'confirmation_letter'
  | 'pension_letter'
  | 'marriage_certificate'
  | 'birth_certificate'
  | 'medical_report'
  | 'other';

export type DocumentStatus = 'uploaded' | 'verified' | 'rejected';

export interface PortalDocument {
  id: number;
  category: DocumentCategory;
  category_label: string;
  title: string;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  issued_on: string | null;
  expires_on: string | null;
  status: DocumentStatus;
  hr_notes: string;
  uploaded_at: string;
  verified_at: string | null;
  download_url: string | null;
}

export interface DocumentUpload {
  file: File;
  category: DocumentCategory;
  title?: string;
  issued_on?: string;
  expires_on?: string;
}

export interface PortalVerificationCycle {
  id: number;
  name: string;
  period_type: string;
  period_label: string;
  start_date: string;
  deadline: string;
  status: 'draft' | 'active' | 'closed';
  instructions: string;
}

export interface PortalVerificationSubmission {
  id: number;
  cycle: PortalVerificationCycle;
  status: 'pending' | 'submitted' | 'verified' | 'rejected';
  submitted_at: string | null;
  verified_at: string | null;
  employee_attestation: Record<string, unknown>;
  hr_notes: string;
  rejection_reason: string;
  document_ids: number[];
}

export interface VerificationSubmitPayload {
  attestation: {
    confirm_accurate: boolean;
    notes?: string;
  };
  document_ids?: number[];
}
