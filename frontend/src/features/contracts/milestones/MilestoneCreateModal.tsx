/**
 * MilestoneCreateModal — create a contract milestone WITH its GL/budget coding.
 *
 * Centralised-AP model: a milestone carries its coding lines from creation
 * (adopted from the contract), so approving it posts the AP invoice directly
 * (DR expense per line / CR vendor-AP) and it shows in the AP register at once.
 *
 * The form mirrors the invoice-creation UI (`VendorInvoiceForm`): milestone
 * fields on top, then a coding grid (Account · Appropriation · Description ·
 * Amount) whose total must reconcile to the Scheduled Value. The first coding
 * row is pre-filled from the contract's GL (NCoA economic) account + budget
 * appropriation; the amount defaults to the Scheduled Value.
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { Modal, App as AntApp } from 'antd';
import { Plus, Trash2 } from 'lucide-react';
import SearchableSelect from '../../../components/SearchableSelect';
import AmountInput from '../../../components/AmountInput';
import { makeAccountSearch } from '../../accounting/hooks/useAccountSearch';
import { makeAppropriationSearch } from '../hooks/useAppropriationSearch';
import { useCreateMilestone, useUpdateMilestone, type MilestoneLine } from '../hooks/useContracts';
import { formatServiceError } from '../utils/errors';

interface CodingLine {
  uid: number;
  account: string;
  appropriation: string;
  description: string;
  amount: string;
  // Seed options so a pre-filled (defaulted) picker shows its label before the
  // user opens it; user-picked values are remembered by SearchableSelect itself.
  accountSeed?: { value: string; label: string };
  apprSeed?: { value: string; label: string };
}

interface MilestoneLike {
  id?: number;
  scheduled_value: string | number;
  percentage_weight: string | number;
}

/** The milestone being edited (subset used to seed the form). */
interface EditMilestone {
  id: number;
  milestone_number: number;
  description: string;
  scheduled_value: string | number;
  percentage_weight: string | number;
  target_date: string | null;
  notes?: string;
  lines?: MilestoneLine[];
}

interface MilestoneCreateModalProps {
  // Loosely typed — mirrors ContractDetail's untyped contract payload.
  contract: any;
  contractId: number;
  ceiling: number;
  milestones: MilestoneLike[];
  formatCurrency: (n: number) => string;
  onClose: () => void;
  onCreated: (milestoneNumber: number) => void;
  /** When set, the modal edits this milestone (PATCH) instead of creating. */
  editMilestone?: EditMilestone;
}

let _uid = 0;
const nextUid = () => (_uid += 1);

export default function MilestoneCreateModal({
  contract, contractId, ceiling, milestones, formatCurrency, onClose, onCreated,
  editMilestone,
}: MilestoneCreateModalProps) {
  const { message } = AntApp.useApp();
  const isEdit = !!editMilestone;
  const createMut = useCreateMilestone();
  const updateMut = useUpdateMilestone();
  const pending = isEdit ? updateMut.isPending : createMut.isPending;

  const accountSearch = useMemo(() => makeAccountSearch({ postableOnly: true }), []);
  const apprSearch = useMemo(() => makeAppropriationSearch(), []);

  // Contract defaults for the first coding row.
  const defaultAccountSeed = useMemo(() => {
    const id = contract?.ncoa_code_economic_id;
    if (id == null) return undefined;
    const code = contract?.ncoa_economic_code;
    const name = contract?.ncoa_economic_name;
    return {
      value: String(id),
      label: code ? `${code}${name ? ' — ' + name : ''}` : `Account #${id}`,
    };
  }, [contract]);
  const defaultApprSeed = useMemo(() => {
    const id = contract?.appropriation;
    if (id == null) return undefined;
    return { value: String(id), label: contract?.appropriation_label || `Appropriation #${id}` };
  }, [contract]);

  const [description, setDescription] = useState(editMilestone?.description ?? '');
  const [scheduledValue, setScheduledValue] = useState(
    editMilestone ? String(editMilestone.scheduled_value ?? '') : '',
  );
  const [weight, setWeight] = useState(
    editMilestone ? String(editMilestone.percentage_weight ?? '') : '',
  );
  const [targetDate, setTargetDate] = useState(editMilestone?.target_date ?? '');
  const [notes, setNotes] = useState(editMilestone?.notes ?? '');
  const [lines, setLines] = useState<CodingLine[]>(() => {
    const existing = editMilestone?.lines ?? [];
    if (existing.length) {
      // Edit mode with coding — seed each row (incl. picker labels) from it.
      return existing.map((l) => ({
        uid: nextUid(),
        account: l.account != null ? String(l.account) : '',
        appropriation: l.appropriation != null ? String(l.appropriation) : '',
        description: l.description ?? '',
        amount: String(l.amount ?? ''),
        accountSeed: l.account != null
          ? { value: String(l.account), label: l.account_code ? `${l.account_code}${l.account_name ? ' — ' + l.account_name : ''}` : `Account #${l.account}` }
          : undefined,
        apprSeed: l.appropriation != null
          ? { value: String(l.appropriation), label: l.appropriation_code || l.appropriation_name || `Appropriation #${l.appropriation}` }
          : undefined,
      }));
    }
    // Create, or edit a milestone that has no coding yet → default from contract.
    return [{
      uid: nextUid(),
      account: defaultAccountSeed?.value ?? '',
      appropriation: defaultApprSeed?.value ?? '',
      description: '',
      amount: '',
      accountSeed: defaultAccountSeed,
      apprSeed: defaultApprSeed,
    }];
  });

  // Auto-fill weight from Scheduled Value ÷ Contract Sum (override-able after).
  // Skip the first run in edit mode so the milestone's stored weight survives.
  const autoWeightReady = useRef(!isEdit);
  useEffect(() => {
    if (!autoWeightReady.current) { autoWeightReady.current = true; return; }
    const v = Number(scheduledValue);
    if (ceiling > 0 && v > 0) setWeight(((v / ceiling) * 100).toFixed(3));
  }, [scheduledValue, ceiling]);

  // Keep a single coding line's amount synced to the Scheduled Value — the
  // common case is one line = the whole milestone. Once the user adds a second
  // line they own the split.
  useEffect(() => {
    setLines((prev) => (prev.length === 1 ? [{ ...prev[0], amount: scheduledValue }] : prev));
  }, [scheduledValue]);

  // ── Aggregate preview ──────────────────────────────────────────────
  // In edit mode exclude the milestone being edited, so "existing" reflects
  // the OTHER milestones and the overflow check compares against them.
  const totals = useMemo(() => {
    const others = isEdit
      ? milestones.filter((m) => m.id !== editMilestone!.id)
      : milestones;
    const totalValue = others.reduce((s, m) => s + (parseFloat(String(m.scheduled_value || 0)) || 0), 0);
    const totalWeight = others.reduce((s, m) => s + (parseFloat(String(m.percentage_weight || 0)) || 0), 0);
    return {
      totalValue, totalWeight,
      remainingValue: Math.max(0, ceiling - totalValue),
      remainingWeight: Math.max(0, 100 - totalWeight),
    };
  }, [milestones, ceiling, isEdit, editMilestone]);

  const liveValue = Number(scheduledValue) || 0;
  const liveWeight = Number(weight) || 0;
  const projectedValue = totals.totalValue + liveValue;
  const projectedWeight = totals.totalWeight + liveWeight;
  const valueOverflow = ceiling > 0 && projectedValue > ceiling;
  const weightOverflow = projectedWeight > 100;

  const codingTotal = useMemo(
    () => lines.reduce((s, l) => s + (parseFloat(l.amount || '0') || 0), 0),
    [lines],
  );
  const codingReconciles = Math.abs(codingTotal - liveValue) < 0.01 && liveValue > 0;

  const setLine = (uid: number, patch: Partial<CodingLine>) =>
    setLines((prev) => prev.map((l) => (l.uid === uid ? { ...l, ...patch } : l)));
  const addLine = () =>
    setLines((prev) => [...prev, { uid: nextUid(), account: '', appropriation: '', description: '', amount: '' }]);
  const removeLine = (uid: number) =>
    setLines((prev) => (prev.length <= 1 ? prev : prev.filter((l) => l.uid !== uid)));

  const milestoneNumber = isEdit ? editMilestone!.milestone_number : milestones.length + 1;

  const canSubmit =
    description.trim() !== '' &&
    liveValue > 0 &&
    targetDate !== '' &&
    lines.every((l) => l.account && Number(l.amount) > 0) &&
    codingReconciles &&
    !valueOverflow && !weightOverflow;

  const handleSubmit = async () => {
    if (!canSubmit) {
      if (!codingReconciles) {
        message.warning('Coding lines must total the Scheduled Value.');
      } else {
        message.warning('Complete the required fields first.');
      }
      return;
    }
    const linePayload = lines.map((l) => ({
      account: Number(l.account),
      appropriation: l.appropriation ? Number(l.appropriation) : null,
      description: l.description.trim(),
      amount: l.amount,
    }));
    try {
      if (isEdit) {
        await updateMut.mutateAsync({
          id: editMilestone!.id,
          contractId,
          patch: {
            description: description.trim(),
            scheduled_value: scheduledValue,
            percentage_weight: weight,
            target_date: targetDate,
            notes: notes.trim(),
            lines: linePayload,
          },
        });
      } else {
        await createMut.mutateAsync({
          contract: contractId,
          milestone_number: milestoneNumber,
          description: description.trim(),
          scheduled_value: scheduledValue,
          percentage_weight: weight,
          target_date: targetDate,
          notes: notes.trim(),
          lines: linePayload,
        });
      }
      onCreated(milestoneNumber);
      onClose();
    } catch (e) {
      message.error(formatServiceError(e, isEdit ? 'Failed to save milestone' : 'Failed to add milestone'));
    }
  };

  return (
    <Modal
      open
      onCancel={onClose}
      width={860}
      title={`${isEdit ? 'Edit' : 'New'} Milestone #${milestoneNumber} — Contract ${contract?.contract_number ?? `#${contractId}`}`}
      okText={pending ? 'Saving…' : (isEdit ? 'Save changes' : `Add Milestone #${milestoneNumber}`)}
      okButtonProps={{ disabled: !canSubmit, loading: pending }}
      onOk={handleSubmit}
      cancelButtonProps={{ disabled: pending }}
      destroyOnHidden
    >
      <p style={{ color: '#64748b', fontSize: 12, marginBottom: 12 }}>
        Milestones are physical contractual checkpoints. When achieved, an approved
        milestone posts its coding as a vendor invoice into the AP register for payment.
      </p>

      {/* Aggregate preview */}
      <div style={{
        background: valueOverflow || weightOverflow ? '#fef2f2' : '#f0f9ff',
        border: `1px solid ${valueOverflow || weightOverflow ? '#fecaca' : '#bae6fd'}`,
        borderRadius: 8, padding: '0.6rem 0.9rem', marginBottom: 16, fontSize: 12,
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
          <span><strong>Existing:</strong> {formatCurrency(totals.totalValue)} · {totals.totalWeight.toFixed(1)}%</span>
          <span><strong>Remaining:</strong> {formatCurrency(totals.remainingValue)} · {totals.remainingWeight.toFixed(1)}%</span>
        </div>
        {(liveValue > 0 || liveWeight > 0) && (
          <div style={{
            marginTop: 6, paddingTop: 6,
            borderTop: `1px solid ${valueOverflow || weightOverflow ? '#fecaca' : '#bae6fd'}`,
            color: valueOverflow || weightOverflow ? '#b91c1c' : '#0369a1', fontWeight: 600,
          }}>
            <strong>After adding:</strong> {formatCurrency(projectedValue)}
            {' · '}Weight {projectedWeight.toFixed(1)}%
            {valueOverflow && <div style={{ marginTop: 4, fontSize: 11 }}>⚠ Exceeds contract sum {formatCurrency(ceiling)} by {formatCurrency(projectedValue - ceiling)}</div>}
            {weightOverflow && <div style={{ marginTop: 4, fontSize: 11 }}>⚠ Exceeds 100% weight cap by {(projectedWeight - 100).toFixed(2)}%</div>}
          </div>
        )}
      </div>

      {/* Milestone fields */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 4 }}>
        <label style={fieldLabel}>
          Description <span style={req}>*</span>
          <input value={description} onChange={(e) => setDescription(e.target.value)}
            placeholder="e.g. Foundation work complete" style={textInput} />
        </label>
        <label style={fieldLabel}>
          Scheduled Value (₦) <span style={req}>*</span>
          <AmountInput value={scheduledValue} onChange={setScheduledValue} style={textInput} />
        </label>
        <label style={fieldLabel}>
          Percentage Weight (%) <span style={req}>*</span>
          <input type="number" min="0" max="100" step="0.001" value={weight}
            onChange={(e) => setWeight(e.target.value)} style={textInput} />
          <span style={hint}>Auto-filled from Scheduled Value — edit for a risk weight.</span>
        </label>
        <label style={fieldLabel}>
          Target Date <span style={req}>*</span>
          <input type="date" value={targetDate} onChange={(e) => setTargetDate(e.target.value)}
            min={contract?.contract_start_date || undefined}
            max={contract?.contract_end_date || undefined}
            style={textInput} />
        </label>
      </div>

      {/* Coding grid */}
      <div style={{ marginTop: 14 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 6 }}>
          <span style={{ fontSize: 12, fontWeight: 700, color: '#334155' }}>GL / Budget coding</span>
          <span style={{ fontSize: 11, color: '#94a3b8' }}>DR expense per line · CR vendor-AP on approval</span>
        </div>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
          <thead>
            <tr style={{ textAlign: 'left', color: '#64748b', borderBottom: '1.5px solid #e2e8f0' }}>
              <th style={{ ...thCell, width: '30%' }}>Account (GL)</th>
              <th style={{ ...thCell, width: '26%' }}>Appropriation</th>
              <th style={thCell}>Description</th>
              <th style={{ ...thCell, width: 120, textAlign: 'right' }}>Amount</th>
              <th style={{ ...thCell, width: 30 }} />
            </tr>
          </thead>
          <tbody>
            {lines.map((l) => (
              <tr key={l.uid} style={{ borderBottom: '1px solid #f1f5f9' }}>
                <td style={tdCell}>
                  <SearchableSelect
                    value={l.account}
                    onChange={(v) => setLine(l.uid, { account: v })}
                    onSearch={accountSearch}
                    options={l.accountSeed ? [l.accountSeed] : []}
                    placeholder="Search GL accounts…"
                  />
                </td>
                <td style={tdCell}>
                  <SearchableSelect
                    value={l.appropriation}
                    onChange={(v) => setLine(l.uid, { appropriation: v })}
                    onSearch={apprSearch}
                    options={l.apprSeed ? [l.apprSeed] : []}
                    placeholder="Optional"
                  />
                </td>
                <td style={tdCell}>
                  <input value={l.description} onChange={(e) => setLine(l.uid, { description: e.target.value })}
                    placeholder="Line note" style={textInput} />
                </td>
                <td style={tdCell}>
                  <AmountInput value={l.amount} onChange={(v) => setLine(l.uid, { amount: v })}
                    style={{ ...textInput, textAlign: 'right' }} />
                </td>
                <td style={{ ...tdCell, textAlign: 'center' }}>
                  <button type="button" onClick={() => removeLine(l.uid)} disabled={lines.length <= 1}
                    title="Remove line" style={{ ...iconBtn, opacity: lines.length <= 1 ? 0.3 : 1 }}>
                    <Trash2 size={13} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr style={{ borderTop: '2px solid #e2e8f0', fontWeight: 700 }}>
              <td style={tdCell} colSpan={3}>
                <button type="button" onClick={addLine} style={addBtn}><Plus size={13} /> Add line</button>
              </td>
              <td style={{ ...tdCell, textAlign: 'right', fontFamily: 'monospace', color: codingReconciles ? '#047857' : '#b91c1c' }}>
                {formatCurrency(codingTotal)}
              </td>
              <td style={tdCell} />
            </tr>
          </tfoot>
        </table>
        <div style={{ marginTop: 4, fontSize: 11.5, color: codingReconciles ? '#047857' : '#b45309' }}>
          {codingReconciles
            ? '✓ Coding reconciles to the Scheduled Value.'
            : `Coding total must equal the Scheduled Value (${formatCurrency(liveValue)}).`}
        </div>
      </div>

      <label style={{ ...fieldLabel, marginTop: 12 }}>
        Notes (optional)
        <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2}
          style={{ ...textInput, resize: 'vertical' }} />
      </label>
    </Modal>
  );
}

const fieldLabel: React.CSSProperties = {
  display: 'flex', flexDirection: 'column', gap: 4,
  fontSize: 11, fontWeight: 600, color: '#475569',
};
const req: React.CSSProperties = { color: '#dc2626' };
const hint: React.CSSProperties = { fontSize: 10.5, fontWeight: 400, color: '#94a3b8' };
const textInput: React.CSSProperties = {
  width: '100%', padding: '0.5rem 0.625rem', borderRadius: 6,
  border: '2.5px solid #e2e8f0', fontSize: 12, outline: 'none',
  fontFamily: 'inherit', boxSizing: 'border-box',
};
const thCell: React.CSSProperties = { padding: '6px 8px', fontWeight: 600 };
const tdCell: React.CSSProperties = { padding: '5px 8px', color: '#334155', verticalAlign: 'top' };
const iconBtn: React.CSSProperties = {
  background: 'none', border: 'none', cursor: 'pointer', color: '#dc2626', padding: 2, display: 'inline-flex',
};
const addBtn: React.CSSProperties = {
  display: 'inline-flex', alignItems: 'center', gap: 5, background: '#eef2ff',
  color: '#4338ca', border: '1px solid #c7d2fe', borderRadius: 6,
  padding: '0.35rem 0.7rem', fontSize: 11.5, fontWeight: 600, cursor: 'pointer',
};
