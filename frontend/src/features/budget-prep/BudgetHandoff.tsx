import { useMemo, useState } from 'react';
import { message } from 'antd';
import { useCurrency } from '../../context/CurrencyContext';
import {
  handoffError, useAdoptActuals, useAdoptionPreview, useIncorporate, useSubmissions,
  type AdoptionBasis, type SubmissionRow,
} from './useBudgetHandoff';

const STAGES: Record<string, string> = {
  draft: 'Draft', submitted: 'Submitted to Budget Office', in_review: 'Under Review',
  revised: 'Revision Requested', incorporated: 'Incorporated / Adopted', rejected: 'Rejected',
};
const BASES: { value: AdoptionBasis; label: string; hint: string }[] = [
  { value: 'outturn', label: 'Last year’s actual spending', hint: 'What was really spent, from the books.' },
  { value: 'appropriation', label: 'Last year’s approved budget', hint: 'The final approved figure after amendments.' },
  { value: 'run_rate', label: 'Spending so far, annualised', hint: 'Spending to date scaled up to a full year.' },
];
const EDITABLE = ['draft', 'revised'];

const card: React.CSSProperties = { background: '#fff', border: '1px solid #e2e8f0', borderRadius: 14, padding: '16px 18px', minWidth: 0 };
const label: React.CSSProperties = { fontSize: 12, fontWeight: 600, color: '#475569', display: 'block', marginBottom: 4 };
const input: React.CSSProperties = { width: '100%', padding: '9px 11px', borderRadius: 8, border: '1px solid #cbd5e1', fontSize: 14, boxSizing: 'border-box' };
const btn: React.CSSProperties = { padding: '8px 14px', borderRadius: 8, border: '1px solid #cbd5e1', background: '#fff', color: '#242a88', fontWeight: 600, fontSize: 13, cursor: 'pointer' };
const primary: React.CSSProperties = { ...btn, background: 'linear-gradient(135deg, #242a88, #2e35a0)', color: '#fff', border: 'none' };
const errorBox: React.CSSProperties = { background: '#fef2f2', border: '1px solid #fecaca', color: '#991b1b', borderRadius: 8, padding: '8px 12px', fontSize: 13 };
const heading: React.CSSProperties = { fontSize: 11, fontWeight: 700, letterSpacing: '.06em', textTransform: 'uppercase', color: '#64748b', marginBottom: 8 };

/**
 * Budget preparation actions: seed a draft submission from last year's actuals, then hand an incorporated one to
 * Budget & Appropriation as draft appropriations. Sits above the generic register, which stays the place to edit rows.
 */
export default function BudgetHandoff() {
  const { formatCurrency } = useCurrency();
  const money = (v: string | number | undefined) => formatCurrency(Number(v ?? 0));
  const { data: submissions = [] } = useSubmissions();
  const [picked, setPicked] = useState<number | null>(null);
  const submission: SubmissionRow | undefined = useMemo(
    () => submissions.find((s) => s.id === picked) ?? submissions[0], [submissions, picked]);
  const id = submission?.id ?? null;

  const [basis, setBasis] = useState<AdoptionBasis>('outturn');
  const [growth, setGrowth] = useState('0');
  const [previewing, setPreviewing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const preview = useAdoptionPreview(id, basis, previewing);
  const adopt = useAdoptActuals();
  const incorporate = useIncorporate();

  if (!submission) return null;
  const editable = EDITABLE.includes(submission.stage);
  const canHandOff = submission.stage === 'incorporated';
  const growthNumber = Number(growth);
  const growthValid = growth.trim() !== '' && Number.isFinite(growthNumber);
  const previewError = previewing && preview.isError ? handoffError(preview.error) : null;

  const runAdopt = async () => {
    setError(null);
    try {
      const r = await adopt.mutateAsync({ id: submission.id, basis, growth_pct: growthNumber });
      message.success(`Adopted ${r.created} line(s) from ${r.source_year}: ${money(r.total_proposed)} proposed`);
      setPreviewing(false);
    } catch (e) { setError(handoffError(e)); }
  };

  const runHandOff = async () => {
    setError(null);
    try {
      const r = await incorporate.mutateAsync({ id: submission.id });
      message.success(`Handed to Budget: ${r.created} created, ${r.updated} updated as draft appropriations for ${r.fiscal_year}`);
    } catch (e) { setError(handoffError(e)); }
  };

  return (
    <section data-testid="budget-handoff" style={{ ...card, marginBottom: 16, display: 'grid', gap: 16 }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'end' }}>
        <div style={{ flex: '1 1 260px' }}>
          <label style={label} htmlFor="bh-submission">Submission</label>
          <select id="bh-submission" data-testid="bh-submission" style={input} value={submission.id}
            onChange={(e) => { setPicked(Number(e.target.value)); setPreviewing(false); setError(null); }}>
            {submissions.map((s) => (
              <option key={s.id} value={s.id}>{s.mda_name} – {s.fiscal_year}</option>
            ))}
          </select>
        </div>
        <div data-testid="bh-stage" style={{ fontSize: 13, color: '#334155' }}>
          <span style={{ ...label, display: 'block' }}>Stage</span>{STAGES[submission.stage] ?? submission.stage}
        </div>
        <div data-testid="bh-totals" style={{ fontSize: 13, color: '#334155' }}>
          <span style={{ ...label, display: 'block' }}>Proposed so far</span>
          {money(Number(submission.total_personnel) + Number(submission.total_overhead) + Number(submission.total_capital))}
        </div>
      </div>

      {error && <div role="alert" data-testid="bh-error" style={errorBox}>{error}</div>}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 16 }}>
        <div>
          <div style={heading}>Start from last year’s figures</div>
          {!editable ? (
            <p data-testid="bh-adopt-locked" style={{ fontSize: 13, color: '#64748b', margin: 0 }}>
              Figures can only be adopted while the submission is a draft or sent back for revision.
            </p>
          ) : (
            <div style={{ display: 'grid', gap: 10 }}>
              <div>
                <label style={label} htmlFor="bh-basis">Base the proposal on</label>
                <select id="bh-basis" data-testid="bh-basis" style={input} value={basis}
                  onChange={(e) => { setBasis(e.target.value as AdoptionBasis); setPreviewing(false); }}>
                  {BASES.map((b) => <option key={b.value} value={b.value}>{b.label}</option>)}
                </select>
                <div style={{ fontSize: 12, color: '#64748b', marginTop: 4 }}>{BASES.find((b) => b.value === basis)?.hint}</div>
              </div>
              <div>
                <label style={label} htmlFor="bh-growth">Growth or policy adjustment (%)</label>
                <input id="bh-growth" data-testid="bh-growth" style={input} inputMode="decimal" value={growth}
                  onChange={(e) => setGrowth(e.target.value)} />
                {!growthValid && <div style={{ fontSize: 12, color: '#991b1b', marginTop: 4 }}>Enter a number, for example 5 or -2.5.</div>}
              </div>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                <button type="button" style={btn} data-testid="bh-preview" onClick={() => { setError(null); setPreviewing(true); }}>
                  Preview baseline
                </button>
                <button type="button" style={primary} data-testid="bh-adopt" disabled={!growthValid || adopt.isPending} onClick={runAdopt}>
                  {adopt.isPending ? 'Adopting…' : 'Adopt into submission'}
                </button>
              </div>
              {previewError && <div role="alert" data-testid="bh-preview-error" style={errorBox}>{previewError}</div>}
              {previewing && preview.data && (
                <div data-testid="bh-preview-result" style={{ fontSize: 13, color: '#334155' }}>
                  <strong>{money(preview.data.total)}</strong> from {preview.data.source_year} across {preview.data.rows.length} line(s)
                  {growthValid && growthNumber !== 0 && <> → about <strong>{money(Number(preview.data.total) * (1 + growthNumber / 100))}</strong> after {growthNumber}%</>}
                </div>
              )}
            </div>
          )}
        </div>

        <div>
          <div style={heading}>Hand over to Budget &amp; Appropriation</div>
          <p style={{ fontSize: 13, color: '#475569', margin: '0 0 10px' }}>
            Creates draft appropriations from the lines of an incorporated submission. They then follow the usual approval and
            activation steps in Budget. Running it again refreshes the drafts; once any has moved past draft it is refused.
          </p>
          <button type="button" style={primary} data-testid="bh-handoff" disabled={!canHandOff || incorporate.isPending} onClick={runHandOff}>
            {incorporate.isPending ? 'Handing over…' : 'Hand over as draft appropriations'}
          </button>
          {!canHandOff && (
            <div data-testid="bh-handoff-locked" style={{ fontSize: 12, color: '#64748b', marginTop: 6 }}>
              Available once the submission is incorporated.
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
