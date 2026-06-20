/**
 * PaymentReconciliationQueue — H2 follow-up operator surface (WS6).
 *
 * Renders the queue of unresolved ``PaymentCascadeFailure`` rows so
 * AP/finance operators can triage and close them out. Each row
 * represents a payment whose cash leg committed but whose downstream
 * IPC mark_paid cascade failed — so the GL and the IPC sub-ledger
 * disagree about whether the IPC has been paid.
 *
 * The backend hard-blocks contract closure until every linked
 * cascade failure on that contract's IPCs is resolved, so this page
 * is on the critical path for end-of-contract workflows.
 */
import { useMemo, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useFocusTrap } from '../../../hooks/useFocusTrap';
import {
  RefreshCw, CheckCircle2, AlertTriangle, X, Clock, FileText,
} from 'lucide-react';
import apiClient from '../../../api/client';
import AccountingLayout from '../AccountingLayout';
import PageHeader from '../../../components/PageHeader';
import StatusBadge from '../components/shared/StatusBadge';
import '../styles/glassmorphism.css';

// ─── Domain types ───────────────────────────────────────────────────────────
// Mirrors PaymentCascadeFailureSerializer in
// accounting/serializers.py. Numeric / decimal fields arrive as strings
// from DRF; the cascade-failure model has no decimals so this isn't
// a concern here.

interface CascadeFailureRow {
  id: number;
  payment: number;
  payment_number: string;
  ipc: number | null;
  ipc_reference: string | null;
  error_class: string;
  error_message: string;
  // Backend stores arbitrary JSON; we narrow to a Record for safe
  // property access. Unknown shape per row — render as text.
  error_context: Record<string, unknown>;
  created_at: string;
  resolved: boolean;
  resolved_at: string | null;
  resolved_by: number | null;
  resolved_by_username: string | null;
  resolution_note: string;
  is_resolvable: boolean;
}

interface QueueSummary {
  pending_count: number;
  oldest_pending_at: string | null;
}

interface ResolvePayload {
  id: number;
  resolution_note: string;
}

// ─── Style tokens ───────────────────────────────────────────────────────────
const inp: React.CSSProperties = {
  width: '100%', padding: '8px 12px', border: '2.5px solid #d1d5db',
  borderRadius: '8px', fontSize: '14px', outline: 'none',
  background: '#fafbfc', color: '#1e293b', boxSizing: 'border-box',
};

// ─── Hooks (TanStack Query) ─────────────────────────────────────────────────

function useCascadeFailures(showResolved: boolean) {
  return useQuery<CascadeFailureRow[]>({
    queryKey: ['payment-cascade-failures', { showResolved }],
    queryFn: async () => {
      const { data } = await apiClient.get('/accounting/payment-cascade-failures/', {
        params: showResolved ? {} : { resolved: false },
      });
      // DRF paginated responses wrap rows in ``results``; the
      // PaymentCascadeFailureViewSet uses the default paginator. Guard
      // for both shapes so the page renders whether the project ships
      // pagination on by default or not.
      if (Array.isArray(data)) {
        return data as CascadeFailureRow[];
      }
      if (data && typeof data === 'object' && Array.isArray((data as { results?: unknown }).results)) {
        return (data as { results: CascadeFailureRow[] }).results;
      }
      return [];
    },
  });
}

function useQueueSummary() {
  return useQuery<QueueSummary>({
    queryKey: ['payment-cascade-failures', 'queue_summary'],
    queryFn: async () => {
      const { data } = await apiClient.get<QueueSummary>(
        '/accounting/payment-cascade-failures/queue_summary/',
      );
      return data;
    },
    refetchInterval: 60_000,  // dashboard widget polls minutely
  });
}

function useResolveFailure() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, resolution_note }: ResolvePayload) => {
      const { data } = await apiClient.post<CascadeFailureRow>(
        `/accounting/payment-cascade-failures/${id}/resolve/`,
        { resolution_note },
      );
      return data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['payment-cascade-failures'] });
    },
  });
}

// ─── Resolve modal ──────────────────────────────────────────────────────────

interface ResolveModalProps {
  failure: CascadeFailureRow;
  onClose: () => void;
}

function ResolveModal({ failure, onClose }: ResolveModalProps) {
  const [note, setNote] = useState<string>('');
  const [submitError, setSubmitError] = useState<string>('');
  const focusRef = useFocusTrap(true, onClose);
  const resolve = useResolveFailure();

  const minNoteLength = 10;
  const noteLengthValid = note.trim().length >= minNoteLength;
  const canSubmit = noteLengthValid && !resolve.isPending;

  const handleSubmit = async (): Promise<void> => {
    if (!canSubmit) {
      return;
    }
    setSubmitError('');
    try {
      await resolve.mutateAsync({ id: failure.id, resolution_note: note.trim() });
      onClose();
    } catch (err: unknown) {
      if (err instanceof Error) {
        setSubmitError(err.message);
      } else {
        setSubmitError('Failed to resolve. Try again.');
      }
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="resolve-modal-title"
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
        zIndex: 999, display: 'flex', alignItems: 'center',
        justifyContent: 'center', padding: '24px',
      }}
    >
      <div
        ref={focusRef}
        style={{
          background: '#fff', borderRadius: '12px', maxWidth: '640px',
          width: '100%', padding: '24px', boxShadow: '0 25px 50px -12px rgba(0,0,0,0.25)',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '16px' }}>
          <h2 id="resolve-modal-title" style={{ margin: 0, fontSize: '18px', fontWeight: 600 }}>
            Resolve cascade failure #{failure.id}
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            style={{ background: 'none', border: 'none', cursor: 'pointer' }}
          >
            <X size={20} />
          </button>
        </div>

        <div style={{ marginBottom: '16px', fontSize: '14px', color: '#475569' }}>
          <div><strong>Payment:</strong> {failure.payment_number}</div>
          <div><strong>IPC:</strong> {failure.ipc_reference ?? '—'}</div>
          <div><strong>Error:</strong> {failure.error_class}</div>
          <div style={{ marginTop: '8px', padding: '8px', background: '#fef2f2', borderRadius: '6px' }}>
            {failure.error_message}
          </div>
        </div>

        <label htmlFor="resolution-note" style={{ display: 'block', fontWeight: 600, marginBottom: '4px' }}>
          Resolution note <span style={{ color: '#dc2626' }}>*</span>
        </label>
        <p style={{ fontSize: '12px', color: '#64748b', margin: '0 0 8px' }}>
          What did you do to resolve the underlying issue? Minimum {minNoteLength} characters; auditable.
        </p>
        <textarea
          id="resolution-note"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          rows={4}
          style={{ ...inp, fontFamily: 'inherit', resize: 'vertical' }}
          placeholder="e.g. SoD reconfigured for MDA-A; manually re-ran mark_paid for IPC-2026-014; confirmed ContractBalance updated."
        />
        <div style={{ fontSize: '12px', color: noteLengthValid ? '#16a34a' : '#94a3b8', marginTop: '4px' }}>
          {note.trim().length}/{minNoteLength}+ characters
        </div>

        {submitError && (
          <div style={{ marginTop: '12px', padding: '8px', background: '#fef2f2', color: '#991b1b', borderRadius: '6px', fontSize: '13px' }}>
            <AlertTriangle size={14} style={{ marginRight: '6px', verticalAlign: 'middle' }} />
            {submitError}
          </div>
        )}

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', marginTop: '20px' }}>
          <button
            type="button"
            onClick={onClose}
            style={{
              padding: '8px 16px', border: '1.5px solid #d1d5db',
              borderRadius: '8px', background: '#fff', cursor: 'pointer',
            }}
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={!canSubmit}
            style={{
              padding: '8px 16px', border: 'none', borderRadius: '8px',
              background: canSubmit ? '#16a34a' : '#94a3b8',
              color: '#fff', cursor: canSubmit ? 'pointer' : 'not-allowed',
              fontWeight: 600,
            }}
          >
            <CheckCircle2 size={14} style={{ marginRight: '6px', verticalAlign: 'middle' }} />
            {resolve.isPending ? 'Resolving…' : 'Mark resolved'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Failure row ────────────────────────────────────────────────────────────

interface FailureRowProps {
  row: CascadeFailureRow;
  onResolveClick: (failure: CascadeFailureRow) => void;
}

function FailureRow({ row, onResolveClick }: FailureRowProps) {
  const actionRequired = useMemo<string>(() => {
    const action = row.error_context?.action_required;
    return typeof action === 'string' ? action : '';
  }, [row.error_context]);

  return (
    <tr
      style={{
        borderTop: '1px solid #e5e7eb',
        background: row.resolved ? '#f8fafc' : '#fff',
      }}
    >
      <td style={{ padding: '12px' }}>{row.id}</td>
      <td style={{ padding: '12px' }}>{row.payment_number}</td>
      <td style={{ padding: '12px' }}>{row.ipc_reference ?? '—'}</td>
      <td style={{ padding: '12px' }}>
        <StatusBadge status={row.error_class} variant="warning" />
      </td>
      <td style={{ padding: '12px', fontSize: '13px', maxWidth: '420px' }}>
        <div style={{ marginBottom: '4px' }}>{row.error_message}</div>
        {actionRequired && (
          <div style={{ color: '#475569', fontSize: '12px', fontStyle: 'italic' }}>
            <FileText size={12} style={{ verticalAlign: 'middle', marginRight: '4px' }} />
            {actionRequired}
          </div>
        )}
      </td>
      <td style={{ padding: '12px', fontSize: '12px', color: '#64748b' }}>
        {new Date(row.created_at).toLocaleString('en-GB')}
      </td>
      <td style={{ padding: '12px' }}>
        {row.resolved ? (
          <StatusBadge status="Resolved" variant="success" />
        ) : (
          <StatusBadge status="Pending" variant="warning" />
        )}
      </td>
      <td style={{ padding: '12px' }}>
        {!row.resolved && row.is_resolvable && (
          <button
            type="button"
            onClick={() => onResolveClick(row)}
            style={{
              padding: '6px 12px', border: 'none', borderRadius: '6px',
              background: '#16a34a', color: '#fff', fontSize: '13px',
              fontWeight: 600, cursor: 'pointer',
            }}
          >
            Resolve
          </button>
        )}
        {!row.resolved && !row.is_resolvable && (
          <span style={{ fontSize: '12px', color: '#94a3b8' }}>
            (no permission)
          </span>
        )}
        {row.resolved && row.resolved_by_username && (
          <span style={{ fontSize: '12px', color: '#64748b' }}>
            by {row.resolved_by_username}
          </span>
        )}
      </td>
    </tr>
  );
}

// ─── Page ───────────────────────────────────────────────────────────────────

export default function PaymentReconciliationQueue() {
  const [showResolved, setShowResolved] = useState<boolean>(false);
  const [resolving, setResolving] = useState<CascadeFailureRow | null>(null);

  const failuresQ = useCascadeFailures(showResolved);
  const summaryQ = useQueueSummary();

  return (
    <AccountingLayout>
      <PageHeader
        title="Payment reconciliation queue"
        subtitle="Cascade failures from posted payments — reconcile before contract closure"
      />

      {/* Dashboard widget */}
      <div
        style={{
          display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
          gap: '16px', marginBottom: '24px',
        }}
      >
        <div style={{ padding: '16px', background: '#fff', borderRadius: '12px', boxShadow: '0 1px 3px rgba(0,0,0,0.05)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#dc2626' }}>
            <AlertTriangle size={18} />
            <span style={{ fontSize: '13px', fontWeight: 600 }}>Pending</span>
          </div>
          <div style={{ fontSize: '32px', fontWeight: 700, marginTop: '4px' }}>
            {summaryQ.data?.pending_count ?? '—'}
          </div>
        </div>
        <div style={{ padding: '16px', background: '#fff', borderRadius: '12px', boxShadow: '0 1px 3px rgba(0,0,0,0.05)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#64748b' }}>
            <Clock size={18} />
            <span style={{ fontSize: '13px', fontWeight: 600 }}>Oldest pending</span>
          </div>
          <div style={{ fontSize: '16px', fontWeight: 600, marginTop: '8px' }}>
            {summaryQ.data?.oldest_pending_at
              ? new Date(summaryQ.data.oldest_pending_at).toLocaleString('en-GB')
              : 'No pending failures'}
          </div>
        </div>
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
        <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '14px' }}>
          <input
            type="checkbox"
            checked={showResolved}
            onChange={(e) => setShowResolved(e.target.checked)}
          />
          Include resolved
        </label>
        <button
          type="button"
          onClick={() => failuresQ.refetch()}
          aria-label="Refresh"
          style={{
            padding: '8px 12px', border: '1.5px solid #d1d5db',
            borderRadius: '8px', background: '#fff', cursor: 'pointer',
            display: 'flex', alignItems: 'center', gap: '6px',
          }}
        >
          <RefreshCw size={14} /> Refresh
        </button>
      </div>

      {failuresQ.isLoading && (
        <div style={{ padding: '24px', textAlign: 'center', color: '#64748b' }}>
          Loading…
        </div>
      )}

      {failuresQ.isError && (
        <div
          role="alert"
          style={{ padding: '16px', background: '#fef2f2', color: '#991b1b', borderRadius: '8px', marginBottom: '12px' }}
        >
          <AlertTriangle size={16} style={{ verticalAlign: 'middle', marginRight: '6px' }} />
          Failed to load reconciliation queue.
        </div>
      )}

      {failuresQ.data && failuresQ.data.length === 0 && (
        <div style={{ padding: '24px', textAlign: 'center', color: '#16a34a', background: '#f0fdf4', borderRadius: '8px' }}>
          <CheckCircle2 size={20} style={{ verticalAlign: 'middle', marginRight: '8px' }} />
          Queue is clear. No {showResolved ? '' : 'pending '}cascade failures.
        </div>
      )}

      {failuresQ.data && failuresQ.data.length > 0 && (
        <div style={{ background: '#fff', borderRadius: '12px', overflow: 'hidden', boxShadow: '0 1px 3px rgba(0,0,0,0.05)' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead style={{ background: '#f8fafc' }}>
              <tr style={{ textAlign: 'left', fontSize: '13px', color: '#475569' }}>
                <th style={{ padding: '12px' }}>ID</th>
                <th style={{ padding: '12px' }}>Payment</th>
                <th style={{ padding: '12px' }}>IPC</th>
                <th style={{ padding: '12px' }}>Error</th>
                <th style={{ padding: '12px' }}>Detail</th>
                <th style={{ padding: '12px' }}>Created</th>
                <th style={{ padding: '12px' }}>Status</th>
                <th style={{ padding: '12px' }}>Action</th>
              </tr>
            </thead>
            <tbody>
              {failuresQ.data.map((row) => (
                <FailureRow key={row.id} row={row} onResolveClick={setResolving} />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {resolving && (
        <ResolveModal failure={resolving} onClose={() => setResolving(null)} />
      )}
    </AccountingLayout>
  );
}
