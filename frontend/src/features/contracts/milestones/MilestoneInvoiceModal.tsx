/**
 * MilestoneInvoiceModal — coding-line editor + "Post Invoice" for a COMPLETED
 * milestone (the milestone-as-invoice flow that replaces "Convert to IPC").
 *
 * The backend `post-invoice` action takes NO body — it posts the accrual
 * (DR expense per coding line / CR vendor-AP) from the milestone's *persisted*
 * `MilestoneInvoiceLine` rows and requires at least one. So this editor is a
 * server-side CRUD: each "Add line" POSTs immediately (`useCreateMilestoneLine`),
 * the running list comes from `useMilestoneLines`, and "Post Invoice" is disabled
 * until ≥1 line is saved. Lines are edit-locked (403) once the milestone flips
 * to INVOICED, so this modal is only opened at COMPLETED.
 */
import { useMemo, useState } from 'react';
import { Modal, App as AntApp } from 'antd';
import { Plus, Trash2 } from 'lucide-react';
import SearchableSelect from '../../../components/SearchableSelect';
import { makeAccountSearch } from '../../accounting/hooks/useAccountSearch';
import { makeAppropriationSearch } from '../hooks/useAppropriationSearch';
import {
  useMilestoneLines, useCreateMilestoneLine, useDeleteMilestoneLine,
  usePostMilestoneInvoice,
} from '../hooks/useContracts';
import { formatServiceError } from '../utils/errors';

interface MilestoneInvoiceModalProps {
  milestone: {
    id: number;
    milestone_number: number;
    description: string;
    scheduled_value: string | number;
  };
  contractId: number;
  /** Contract's default appropriation — seeds each new line's picker. */
  defaultAppropriation?: number | null;
  defaultAppropriationLabel?: string | null;
  formatCurrency: (n: number) => string;
  onClose: () => void;
  onPosted: (result: { invoice_number?: string; total_amount?: string }) => void;
}

export default function MilestoneInvoiceModal({
  milestone, contractId, defaultAppropriation, defaultAppropriationLabel,
  formatCurrency, onClose, onPosted,
}: MilestoneInvoiceModalProps) {
  const { message } = AntApp.useApp();
  const { data: lines = [], isLoading } = useMilestoneLines(milestone.id);
  const createLine = useCreateMilestoneLine();
  const deleteLine = useDeleteMilestoneLine();
  const postInvoice = usePostMilestoneInvoice();

  // Server-side pickers (memoised so SearchableSelect's debounce doesn't
  // re-subscribe every render).
  const accountSearch = useMemo(() => makeAccountSearch({ postableOnly: true }), []);
  const apprSearch = useMemo(() => makeAppropriationSearch(), []);
  // Seed option so the defaulted appropriation shows its label before the
  // user opens the picker (the FK id alone would render blank).
  const apprSeed = useMemo(
    () => (defaultAppropriation != null
      ? [{ value: String(defaultAppropriation), label: defaultAppropriationLabel || `Appropriation #${defaultAppropriation}` }]
      : []),
    [defaultAppropriation, defaultAppropriationLabel],
  );

  const defaultApprValue = defaultAppropriation != null ? String(defaultAppropriation) : '';
  // Draft line — appropriation defaults to the contract's, and resets back to
  // it after each add so the common case is one keystroke per line.
  const [account, setAccount] = useState('');
  const [appropriation, setAppropriation] = useState(defaultApprValue);
  const [description, setDescription] = useState('');
  const [amount, setAmount] = useState('');

  const total = lines.reduce((s, l) => s + (parseFloat(String(l.amount || 0)) || 0), 0);
  const scheduled = Number(milestone.scheduled_value || 0);
  const canPost = lines.length > 0 && !postInvoice.isPending;

  const handleAdd = async () => {
    if (!account) { message.warning('Pick an account for the line.'); return; }
    const amt = Number(amount);
    if (!amt || amt <= 0) { message.warning('Enter a line amount greater than zero.'); return; }
    try {
      await createLine.mutateAsync({
        milestone: milestone.id,
        account: Number(account),
        appropriation: appropriation ? Number(appropriation) : null,
        description: description.trim(),
        amount: String(amount),
        contractId,
      });
      setAccount('');
      setDescription('');
      setAmount('');
      setAppropriation(defaultApprValue);
    } catch (e) {
      message.error(formatServiceError(e, 'Failed to add line'));
    }
  };

  const handleDelete = async (lineId: number) => {
    try {
      await deleteLine.mutateAsync({ lineId, milestoneId: milestone.id, contractId });
    } catch (e) {
      message.error(formatServiceError(e, 'Failed to remove line'));
    }
  };

  const handlePost = async () => {
    try {
      const { data } = await postInvoice.mutateAsync({ milestoneId: milestone.id, contractId });
      onPosted(data);
      onClose();
    } catch (e) {
      message.error(formatServiceError(e, 'Failed to post invoice'));
    }
  };

  return (
    <Modal
      open
      onCancel={onClose}
      width={760}
      title={`Post Invoice — Milestone #${milestone.milestone_number}`}
      okText={postInvoice.isPending ? 'Posting…' : 'Post Invoice'}
      okButtonProps={{ disabled: !canPost, loading: postInvoice.isPending }}
      onOk={handlePost}
      cancelButtonProps={{ disabled: postInvoice.isPending }}
    >
      <div style={{ marginBottom: 12, fontSize: 13, color: '#475569' }}>
        {milestone.description}
        <div style={{ marginTop: 4 }}>
          Scheduled value:{' '}
          <strong style={{ fontFamily: 'monospace', color: '#0f172a' }}>{formatCurrency(scheduled)}</strong>
          <span style={{ marginLeft: 12, color: '#94a3b8' }}>
            Coding lines set the accrual — they need not equal the scheduled value.
          </span>
        </div>
      </div>

      {/* Saved lines */}
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
        <thead>
          <tr style={{ textAlign: 'left', color: '#64748b', borderBottom: '1.5px solid #e2e8f0' }}>
            <th style={thCell}>Account</th>
            <th style={thCell}>Appropriation</th>
            <th style={thCell}>Description</th>
            <th style={{ ...thCell, textAlign: 'right' }}>Amount</th>
            <th style={{ ...thCell, width: 32 }} />
          </tr>
        </thead>
        <tbody>
          {isLoading ? (
            <tr><td colSpan={5} style={{ ...tdCell, color: '#94a3b8' }}>Loading lines…</td></tr>
          ) : lines.length === 0 ? (
            <tr><td colSpan={5} style={{ ...tdCell, color: '#94a3b8', fontStyle: 'italic' }}>No coding lines yet — add at least one below.</td></tr>
          ) : (
            lines.map((l) => (
              <tr key={l.id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                <td style={tdCell}>
                  <span style={{ fontFamily: 'monospace', color: '#0f172a' }}>{l.account_code || '—'}</span>
                  {l.account_name && <span style={{ color: '#94a3b8', marginLeft: 6 }}>{l.account_name}</span>}
                </td>
                <td style={tdCell}>{l.appropriation_code || l.appropriation_name || '—'}</td>
                <td style={tdCell}>{l.description || '—'}</td>
                <td style={{ ...tdCell, textAlign: 'right', fontFamily: 'monospace' }}>{formatCurrency(Number(l.amount || 0))}</td>
                <td style={{ ...tdCell, textAlign: 'center' }}>
                  <button
                    type="button"
                    onClick={() => handleDelete(l.id)}
                    disabled={deleteLine.isPending}
                    title="Remove line"
                    style={iconBtn}
                  >
                    <Trash2 size={13} />
                  </button>
                </td>
              </tr>
            ))
          )}
        </tbody>
        {lines.length > 0 && (
          <tfoot>
            <tr style={{ borderTop: '2px solid #e2e8f0', fontWeight: 700 }}>
              <td style={tdCell} colSpan={3}>Total ({lines.length} line{lines.length === 1 ? '' : 's'})</td>
              <td style={{ ...tdCell, textAlign: 'right', fontFamily: 'monospace' }}>{formatCurrency(total)}</td>
              <td style={tdCell} />
            </tr>
          </tfoot>
        )}
      </table>

      {/* Draft-line editor */}
      <div style={{ marginTop: 14, padding: 12, background: '#f8fafc', borderRadius: 8, border: '1px solid #e2e8f0' }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
          <label style={fieldLabel}>
            Account <span style={{ color: '#dc2626' }}>*</span>
            <SearchableSelect
              value={account}
              onChange={setAccount}
              onSearch={accountSearch}
              options={[]}
              placeholder="Search postable accounts…"
            />
          </label>
          <label style={fieldLabel}>
            Appropriation
            <SearchableSelect
              value={appropriation}
              onChange={setAppropriation}
              onSearch={apprSearch}
              options={apprSeed}
              placeholder="Default: contract appropriation"
            />
          </label>
          <label style={fieldLabel}>
            Description
            <input
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="e.g. Substructure works"
              style={textInput}
            />
          </label>
          <label style={fieldLabel}>
            Amount (₦) <span style={{ color: '#dc2626' }}>*</span>
            <input
              type="number"
              min="0"
              step="0.01"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder="0.00"
              style={{ ...textInput, textAlign: 'right', fontFamily: 'monospace' }}
            />
          </label>
        </div>
        <div style={{ marginTop: 10, textAlign: 'right' }}>
          <button
            type="button"
            onClick={handleAdd}
            disabled={createLine.isPending}
            style={addBtn}
          >
            <Plus size={14} /> {createLine.isPending ? 'Adding…' : 'Add line'}
          </button>
        </div>
      </div>

      <p style={{ marginTop: 12, marginBottom: 0, fontSize: 11.5, color: '#64748b' }}>
        Posting raises a vendor invoice and its accrual journal (DR expense per line /
        CR vendor-AP), withholds retention as a per-invoice lien, and moves the milestone
        to <strong>INVOICED</strong>. This cannot be undone from here.
      </p>
    </Modal>
  );
}

const thCell: React.CSSProperties = { padding: '6px 8px', fontWeight: 600 };
const tdCell: React.CSSProperties = { padding: '6px 8px', color: '#334155', verticalAlign: 'top' };
const fieldLabel: React.CSSProperties = {
  display: 'flex', flexDirection: 'column', gap: 4,
  fontSize: 11, fontWeight: 600, color: '#475569',
};
const textInput: React.CSSProperties = {
  width: '100%', padding: '0.5rem 0.625rem', borderRadius: 6,
  border: '2.5px solid #e2e8f0', fontSize: 12, outline: 'none',
  fontFamily: 'inherit', boxSizing: 'border-box',
};
const iconBtn: React.CSSProperties = {
  background: 'none', border: 'none', cursor: 'pointer',
  color: '#dc2626', padding: 2, display: 'inline-flex',
};
const addBtn: React.CSSProperties = {
  display: 'inline-flex', alignItems: 'center', gap: 6,
  background: '#191e6a', color: '#fff', border: 'none', borderRadius: 6,
  padding: '0.45rem 0.9rem', fontSize: 12, fontWeight: 600, cursor: 'pointer',
};
