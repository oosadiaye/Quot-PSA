import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { CalendarDays, Plus, X } from 'lucide-react';
import PortalLayout from '../PortalLayout';
import PortalPageHeader from '../components/PortalPageHeader';
import { portalApi, type LeaveRequestCreate } from '../api';

const STATUS_COLORS: Record<string, { bg: string; fg: string }> = {
  Draft: { bg: '#f1f5f9', fg: '#475569' },
  Pending: { bg: '#fef3c7', fg: '#92400e' },
  Approved: { bg: '#dcfce7', fg: '#15803d' },
  Rejected: { bg: '#fee2e2', fg: '#b91c1c' },
  Cancelled: { bg: '#e2e8f0', fg: '#64748b' },
};

export default function MyLeave() {
  const qc = useQueryClient();
  const [isFormOpen, setFormOpen] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [form, setForm] = useState<LeaveRequestCreate>({
    leave_type_id: 0,
    start_date: '',
    end_date: '',
    reason: '',
  });

  const balances = useQuery({ queryKey: ['portal-leave-balances'], queryFn: () => portalApi.getLeaveBalances() });
  const requests = useQuery({ queryKey: ['portal-leave-requests'], queryFn: portalApi.getLeaveRequests });
  const types = useQuery({ queryKey: ['portal-leave-types'], queryFn: portalApi.getLeaveTypes });

  const createMut = useMutation({
    mutationFn: portalApi.createLeaveRequest,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['portal-leave-requests'] });
      qc.invalidateQueries({ queryKey: ['portal-dashboard'] });
      setFormOpen(false);
      setForm({ leave_type_id: 0, start_date: '', end_date: '', reason: '' });
    },
    onError: (err: unknown) => {
      const message =
        err instanceof Error ? err.message : 'Failed to submit leave request.';
      setFormError(message);
    },
  });

  const cancelMut = useMutation({
    mutationFn: portalApi.cancelLeaveRequest,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['portal-leave-requests'] }),
  });

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    if (!form.leave_type_id) return setFormError('Select a leave type.');
    if (!form.start_date || !form.end_date) return setFormError('Pick your leave dates.');
    if (form.end_date < form.start_date) return setFormError('End date cannot be before start date.');
    if (!form.reason.trim()) return setFormError('Please give a short reason for your leave.');
    createMut.mutate(form);
  };

  return (
    <PortalLayout>
      <PortalPageHeader
        title="My Leave"
        subtitle="Request time off and track your balances"
        icon={<CalendarDays size={20} color="#ffffff" />}
        actions={
          <button
            onClick={() => {
              setFormError(null);
              setFormOpen(true);
            }}
            style={{
              background: 'rgba(255,255,255,0.18)',
              color: '#ffffff',
              border: '1px solid rgba(255,255,255,0.38)',
              padding: '8px 14px',
              borderRadius: 9,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              fontSize: 13,
              fontWeight: 600,
            }}
          >
            <Plus size={15} />
            New Request
          </button>
        }
      />

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 14, marginBottom: 22 }}>
        {balances.data?.results.map((b) => (
          <div
            key={b.id}
            style={{
              background: '#ffffff',
              border: '1px solid #e2e8f0',
              borderRadius: 12,
              padding: 16,
            }}
          >
            <div style={{ fontSize: 12, fontWeight: 600, color: '#64748b', textTransform: 'uppercase', letterSpacing: 0.5 }}>
              {b.leave_type}
            </div>
            <div style={{ fontSize: 26, fontWeight: 700, color: '#0f172a', marginTop: 4 }}>
              {b.balance} <span style={{ fontSize: 13, color: '#94a3b8', fontWeight: 500 }}>/ {b.allocated} days</span>
            </div>
            <div style={{ marginTop: 8, fontSize: 12, color: '#64748b' }}>
              {b.taken} day(s) taken · {b.year}
            </div>
          </div>
        ))}
        {!balances.isLoading && balances.data?.results.length === 0 && (
          <div style={{ color: '#94a3b8', fontSize: 14 }}>No leave balances configured yet.</div>
        )}
      </div>

      <div style={{ background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: 12, overflow: 'hidden' }}>
        <header
          style={{
            padding: '14px 20px',
            borderBottom: '1px solid #e2e8f0',
            fontSize: 13,
            fontWeight: 600,
            color: '#475569',
          }}
        >
          Leave Requests
        </header>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ background: '#f8fafc' }}>
              <Th>Type</Th>
              <Th>From</Th>
              <Th>To</Th>
              <Th>Days</Th>
              <Th>Status</Th>
              <Th>Reason</Th>
              <Th>Actions</Th>
            </tr>
          </thead>
          <tbody>
            {requests.isLoading && (
              <tr>
                <td colSpan={7} style={{ padding: 20, color: '#94a3b8', textAlign: 'center' }}>
                  Loading…
                </td>
              </tr>
            )}
            {requests.data?.results.length === 0 && (
              <tr>
                <td colSpan={7} style={{ padding: 22, color: '#94a3b8', textAlign: 'center', fontSize: 14 }}>
                  No leave requests yet. Click <strong>New Request</strong> to submit your first one.
                </td>
              </tr>
            )}
            {requests.data?.results.map((r) => {
              const color = STATUS_COLORS[r.status] ?? STATUS_COLORS.Draft;
              const canCancel = r.status === 'Pending' || r.status === 'Draft';
              return (
                <tr key={r.id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                  <Td strong>{r.leave_type}</Td>
                  <Td>{new Date(r.start_date).toLocaleDateString()}</Td>
                  <Td>{new Date(r.end_date).toLocaleDateString()}</Td>
                  <Td>{r.total_days}</Td>
                  <Td>
                    <span
                      style={{
                        background: color.bg,
                        color: color.fg,
                        padding: '3px 9px',
                        borderRadius: 999,
                        fontSize: 11,
                        fontWeight: 700,
                        textTransform: 'uppercase',
                        letterSpacing: 0.4,
                      }}
                    >
                      {r.status}
                    </span>
                  </Td>
                  <Td>{r.reason}</Td>
                  <Td>
                    {canCancel && (
                      <button
                        onClick={() => cancelMut.mutate(r.id)}
                        disabled={cancelMut.isPending}
                        style={{
                          background: 'transparent',
                          color: '#b91c1c',
                          border: '1px solid #fecaca',
                          padding: '4px 9px',
                          borderRadius: 6,
                          cursor: 'pointer',
                          fontSize: 12,
                        }}
                      >
                        Cancel
                      </button>
                    )}
                  </Td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {isFormOpen && (
        <div
          onClick={() => setFormOpen(false)}
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(15, 23, 42, 0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 50,
          }}
        >
          <form
            onClick={(e) => e.stopPropagation()}
            onSubmit={submit}
            style={{
              background: '#ffffff',
              borderRadius: 14,
              padding: 24,
              width: 480,
              maxWidth: '95%',
              boxShadow: '0 30px 60px rgba(0,0,0,0.25)',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 18 }}>
              <div style={{ fontSize: 17, fontWeight: 700, color: '#0f172a' }}>New Leave Request</div>
              <button
                type="button"
                onClick={() => setFormOpen(false)}
                style={{ background: 'transparent', border: 0, color: '#64748b', cursor: 'pointer' }}
              >
                <X size={18} />
              </button>
            </div>

            {formError && (
              <div
                style={{
                  background: '#fef2f2',
                  color: '#b91c1c',
                  border: '1px solid #fecaca',
                  padding: '8px 12px',
                  borderRadius: 8,
                  fontSize: 13,
                  marginBottom: 14,
                }}
              >
                {formError}
              </div>
            )}

            <Field label="Leave Type">
              <select
                value={form.leave_type_id || ''}
                onChange={(e) => setForm({ ...form, leave_type_id: Number(e.target.value) })}
                style={inputStyle}
              >
                <option value="">Select leave type</option>
                {types.data?.results.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name} {t.is_paid ? '(Paid)' : '(Unpaid)'}
                  </option>
                ))}
              </select>
            </Field>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <Field label="Start Date">
                <input
                  type="date"
                  value={form.start_date}
                  onChange={(e) => setForm({ ...form, start_date: e.target.value })}
                  style={inputStyle}
                />
              </Field>
              <Field label="End Date">
                <input
                  type="date"
                  value={form.end_date}
                  onChange={(e) => setForm({ ...form, end_date: e.target.value })}
                  style={inputStyle}
                />
              </Field>
            </div>

            <Field label="Reason">
              <textarea
                value={form.reason}
                onChange={(e) => setForm({ ...form, reason: e.target.value })}
                rows={3}
                style={{ ...inputStyle, resize: 'vertical', fontFamily: 'inherit' }}
                placeholder="Briefly describe the reason for leave"
              />
            </Field>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 18 }}>
              <button
                type="button"
                onClick={() => setFormOpen(false)}
                style={{
                  background: 'transparent',
                  border: '1px solid #e2e8f0',
                  padding: '9px 16px',
                  borderRadius: 8,
                  cursor: 'pointer',
                  fontSize: 13,
                  color: '#475569',
                }}
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={createMut.isPending}
                style={{
                  background: 'linear-gradient(135deg, #242a88, #2e35a0)',
                  color: '#ffffff',
                  border: 0,
                  padding: '9px 18px',
                  borderRadius: 8,
                  cursor: 'pointer',
                  fontSize: 13,
                  fontWeight: 600,
                  opacity: createMut.isPending ? 0.6 : 1,
                }}
              >
                {createMut.isPending ? 'Submitting…' : 'Submit Request'}
              </button>
            </div>
          </form>
        </div>
      )}
    </PortalLayout>
  );
}

const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: '9px 11px',
  border: '1px solid #e2e8f0',
  borderRadius: 8,
  fontSize: 13,
  color: '#0f172a',
  outline: 'none',
  background: '#ffffff',
};

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label style={{ display: 'block', marginBottom: 12 }}>
      <div style={{ fontSize: 12, fontWeight: 600, color: '#475569', marginBottom: 5 }}>{label}</div>
      {children}
    </label>
  );
}

function Th({ children }: { children: React.ReactNode }) {
  return (
    <th
      style={{
        textAlign: 'left',
        padding: '10px 16px',
        fontSize: 11,
        fontWeight: 700,
        color: '#475569',
        textTransform: 'uppercase',
        letterSpacing: 0.5,
      }}
    >
      {children}
    </th>
  );
}

function Td({ children, strong }: { children: React.ReactNode; strong?: boolean }) {
  return (
    <td
      style={{
        padding: '11px 16px',
        fontSize: 13,
        color: strong ? '#0f172a' : '#475569',
        fontWeight: strong ? 600 : 400,
      }}
    >
      {children}
    </td>
  );
}
