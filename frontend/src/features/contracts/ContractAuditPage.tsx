/**
 * ContractAuditPage — the full activity log for one contract, reached from the
 * "View All Audit Logs" button on the contract detail page (was a 404 route).
 *
 * Data: GET /contracts/contracts/{id}/activity/ (useContractActivity) — every
 * core.AuditLog entry on the contract AND its sub-objects, newest-first, each
 * with the actor (username).
 */
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { formatDate } from '@/utils/date';
import { useContract, useContractActivity } from './hooks/useContracts';

const ACTION: Record<string, string> = {
  CREATE: 'Created', UPDATE: 'Updated', DELETE: 'Deleted', POST: 'Posted',
  UNPOST: 'Unposted', APPROVE: 'Approved', REJECT: 'Rejected', CANCEL: 'Cancelled',
  VOID: 'Voided', CLOSE: 'Closed', OPEN: 'Opened', LOCK: 'Locked', UNLOCK: 'Unlocked',
  EXPORT: 'Exported', IMPORT: 'Imported',
};
const MODEL: Record<string, string> = {
  contract: 'Contract', milestoneschedule: 'Milestone',
  interimpaymentcertificate: 'IPC', contractvariation: 'Variation',
  mobilizationpayment: 'Mobilization', retentionrelease: 'Retention Release',
  contractyearplan: 'Year Plan',
};

export default function ContractAuditPage() {
  const { id } = useParams<{ id: string }>();
  const cid = Number(id);
  const navigate = useNavigate();
  const { data: contract } = useContract(cid);
  const { data: activity, isLoading } = useContractActivity(cid, 200);

  return (
    <div style={{ padding: '1.5rem', maxWidth: 1040, margin: '0 auto' }}>
      <button
        onClick={() => navigate(`/contracts/${cid}`)}
        style={{ display: 'inline-flex', alignItems: 'center', gap: 6, background: 'none', border: 'none', color: '#4f46e5', cursor: 'pointer', fontSize: 13, marginBottom: 12 }}
      >
        <ArrowLeft size={16} /> Back to contract
      </button>
      <h1 style={{ fontSize: 20, fontWeight: 800, color: '#0f172a', margin: '0 0 4px' }}>Activity Log</h1>
      <p style={{ color: '#64748b', fontSize: 13, margin: '0 0 16px' }}>
        {contract?.contract_number ?? `Contract #${cid}`} — every action on the contract and its
        milestones, IPCs, variations, mobilization and retention, with who performed it.
      </p>
      <div style={{ border: '1px solid #e2e8f0', borderRadius: 10, overflow: 'hidden', background: '#fff' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ background: '#f8fafc', textAlign: 'left' }}>
              {['When', 'Action', 'Type', 'Detail', 'Status', 'By'].map((h) => (
                <th key={h} style={{ padding: '10px 14px', fontSize: 11, fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.04em', borderBottom: '1px solid #e2e8f0' }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr><td colSpan={6} style={{ padding: '2rem', textAlign: 'center', color: '#94a3b8' }}>Loading…</td></tr>
            )}
            {!isLoading && (!activity || activity.length === 0) && (
              <tr><td colSpan={6} style={{ padding: '2rem', textAlign: 'center', color: '#94a3b8' }}>No activity recorded yet</td></tr>
            )}
            {activity?.map((a) => (
              <tr key={a.id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                <td style={{ padding: '9px 14px', color: '#475569', whiteSpace: 'nowrap' }}>{formatDate(a.timestamp)}</td>
                <td style={{ padding: '9px 14px', fontWeight: 700, color: '#0f172a' }}>{ACTION[a.action] ?? a.action}</td>
                <td style={{ padding: '9px 14px', color: '#475569' }}>{MODEL[a.model_name] ?? a.model_name}</td>
                <td style={{ padding: '9px 14px', color: '#475569' }}>{a.object_repr || '—'}</td>
                <td style={{ padding: '9px 14px', color: '#475569' }}>
                  {a.old_status || a.new_status ? `${a.old_status || '—'} → ${a.new_status || '—'}` : '—'}
                </td>
                <td style={{ padding: '9px 14px', color: '#4f46e5', fontWeight: 600 }}>{a.username || 'System'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
