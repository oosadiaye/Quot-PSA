import { useMemo, useState } from 'react';
import { message } from 'antd';
import { useCurrency } from '../../context/CurrencyContext';
import {
  handoffError, useAdoptActuals, useAdoptionPreview, useCeilingCheck, useIncorporate, useSeedCalendar, useSubmissions,
  useSubmitSubmission, useSupplementaryReport, useUpcomingMilestones, type AdoptionBasis, type MilestoneRow, type SubmissionRow,
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
const TYPE_LABEL: Record<string, string> = { personnel: 'Personnel', overhead: 'Overheads', capital: 'Capital' };
const MILESTONE_STYLE: Record<MilestoneRow['status'], { label: string; color: string }> = {
  completed: { label: 'Done', color: '#166534' },
  overdue: { label: 'Overdue', color: '#991b1b' },
  due_soon: { label: 'Due soon', color: '#92400e' },
  upcoming: { label: 'Upcoming', color: '#475569' },
};
const ddmmyyyy = (iso: string) => iso.slice(0, 10).split('-').reverse().join('/');

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
  const ceiling = useCeilingCheck(id);
  const supplementaryReport = useSupplementaryReport(submission?.fiscal_year ?? null);
  const submit = useSubmitSubmission();
  const [reason, setReason] = useState('');
  const milestones = useUpcomingMilestones(30);
  const seedCalendar = useSeedCalendar();
  const [anchor, setAnchor] = useState('');
  const [needAnchor, setNeedAnchor] = useState(false);

  if (!submission) return null;
  const editable = EDITABLE.includes(submission.stage);
  const isSupplementary = submission.kind === 'supplementary';
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

  const overCeiling = ceiling.data ? !ceiling.data.ok : false;
  const runSubmit = async () => {
    setError(null);
    try {
      await submit.mutateAsync({ id: submission.id, override_reason: reason });
      message.success(overCeiling ? 'Submitted over the ceiling, with your reason recorded for the reviewer' : 'Submitted to the Budget Office');
      setReason('');
    } catch (e) { setError(handoffError(e)); }
  };

  const runSeed = async () => {
    setError(null);
    try {
      const r = await seedCalendar.mutateAsync({ fiscal_year: submission.fiscal_year, ...(anchor ? { anchor_date: anchor } : {}) });
      message.success(r.created ? `Added ${r.created} standard step(s) for ${submission.fiscal_year}` : `The ${submission.fiscal_year} calendar already has every standard step`);
      setNeedAnchor(false);
    } catch (e) {
      setNeedAnchor(true);
      setError(handoffError(e));
    }
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
              <option key={s.id} value={s.id}>{s.mda_name} – {s.fiscal_year}{s.kind === 'supplementary' ? ' (supplementary)' : ''}</option>
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

      <div data-testid="bh-calendar">
        <div style={heading}>Budget calendar: coming up</div>
        {(milestones.data ?? []).length === 0 ? (
          <p data-testid="bh-calendar-empty" style={{ fontSize: 13, color: '#64748b', margin: '0 0 8px' }}>
            Nothing is overdue or due in the next 30 days.
          </p>
        ) : (
          <ul style={{ listStyle: 'none', margin: '0 0 8px', padding: 0, display: 'grid', gap: 4 }}>
            {(milestones.data ?? []).slice(0, 5).map((m) => (
              <li key={m.id} data-testid="bh-milestone" style={{ display: 'flex', gap: 10, alignItems: 'baseline', fontSize: 13, color: '#334155' }}>
                <span style={{ fontWeight: 700, color: MILESTONE_STYLE[m.status].color, minWidth: 70 }}>{MILESTONE_STYLE[m.status].label}</span>
                <span style={{ flex: 1 }}>{m.fiscal_year}: {m.name}</span>
                <span style={{ fontVariantNumeric: 'tabular-nums' }}>{ddmmyyyy(m.due_date)}</span>
              </li>
            ))}
          </ul>
        )}
        <div style={{ display: 'flex', gap: 8, alignItems: 'end', flexWrap: 'wrap' }}>
          {needAnchor && (
            <div>
              <label style={label} htmlFor="bh-anchor">Date the {submission.fiscal_year} call circular is issued</label>
              <input id="bh-anchor" data-testid="bh-anchor" type="date" style={{ ...input, width: 190 }} value={anchor}
                onChange={(e) => setAnchor(e.target.value)} />
            </div>
          )}
          <button type="button" style={btn} data-testid="bh-seed" disabled={seedCalendar.isPending} onClick={runSeed}>
            Set up the standard {submission.fiscal_year} calendar
          </button>
        </div>
      </div>

      {isSupplementary && (
        <div data-testid="bh-supplementary-note" style={{ fontSize: 13, color: '#334155' }}>
          <div style={heading}>Supplementary budget</div>
          <p style={{ margin: '0 0 6px' }}>
            This is a separate request. Choose the economic code for each line yourself; the original MDA ceilings do not apply.
            It becomes supplementary appropriations on hand-over and goes through the normal approval and enactment steps.
          </p>
          <p data-testid="bh-justification" style={{ margin: 0 }}>
            <strong>Justification: </strong>{submission.justification.trim() || 'None yet. Add it on the submission before submitting.'}
          </p>
        </div>
      )}
      <div data-testid="bh-ceiling">
        <div style={heading}>{isSupplementary ? 'Send to the Budget Office' : 'Against the MDA ceiling'}</div>
        {!isSupplementary && ceiling.data && !ceiling.data.has_ceiling && (
          <p data-testid="bh-no-ceiling" style={{ fontSize: 13, color: '#64748b', margin: 0 }}>
            No ceiling has been set for this MDA and year, so there is nothing to check against.
          </p>
        )}
        {!isSupplementary && ceiling.data?.has_ceiling && (
          <table data-no-tools style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13, fontVariantNumeric: 'tabular-nums' }}>
            <thead>
              <tr style={{ textAlign: 'left', color: '#64748b' }}>
                <th style={{ padding: '4px 8px 4px 0' }}>Type</th>
                <th style={{ textAlign: 'right' }}>Proposed</th>
                <th style={{ textAlign: 'right' }}>Ceiling</th>
                <th style={{ textAlign: 'right' }}>Over by</th>
              </tr>
            </thead>
            <tbody>
              {ceiling.data.rows.map((r) => (
                <tr key={r.line_type} data-testid={`bh-ceiling-${r.line_type}`}
                  style={{ color: Number(r.over_by) > 0 ? '#991b1b' : '#334155', fontWeight: Number(r.over_by) > 0 ? 700 : 400 }}>
                  <td style={{ padding: '4px 8px 4px 0' }}>{TYPE_LABEL[r.line_type]}</td>
                  <td style={{ textAlign: 'right' }}>{money(r.proposed)}</td>
                  <td style={{ textAlign: 'right' }}>{r.ceiling === null ? 'none set' : money(r.ceiling)}</td>
                  <td style={{ textAlign: 'right' }}>{Number(r.over_by) > 0 ? money(r.over_by) : '–'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {editable && (
          <div style={{ display: 'grid', gap: 8, marginTop: 10 }}>
            {!isSupplementary && overCeiling && (
              <div>
                <label style={label} htmlFor="bh-reason">This is over the ceiling. Why is it needed? (required to submit)</label>
                <textarea id="bh-reason" data-testid="bh-reason" style={{ ...input, minHeight: 64, resize: 'vertical' }} value={reason}
                  onChange={(e) => setReason(e.target.value)} />
              </div>
            )}
            <div>
              <button type="button" style={primary} data-testid="bh-submit"
                disabled={submit.isPending || (!isSupplementary && overCeiling && reason.trim() === '')} onClick={runSubmit}>
                {submit.isPending ? 'Submitting…' : !isSupplementary && overCeiling ? 'Submit over ceiling' : 'Submit to Budget Office'}
              </button>
            </div>
          </div>
        )}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 16 }}>
        <div>
          <div style={heading}>Start from last year’s figures</div>
          {isSupplementary ? (
            <p data-testid="bh-adopt-original-only" style={{ fontSize: 13, color: '#64748b', margin: 0 }}>
              This applies to the original budget. Enter the supplementary lines directly.
            </p>
          ) : !editable ? (
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

      <div data-testid="bh-supplementary-report">
        <div style={heading}>Supplementary budgets in {submission.fiscal_year}</div>
        {(supplementaryReport.data?.rows ?? []).length === 0 ? (
          <p data-testid="bh-supplementary-empty" style={{ fontSize: 13, color: '#64748b', margin: 0 }}>
            No supplementary appropriations for {submission.fiscal_year} yet.
          </p>
        ) : (
          <table data-no-tools style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13, fontVariantNumeric: 'tabular-nums' }}>
            <thead>
              <tr style={{ textAlign: 'left', color: '#64748b' }}>
                <th style={{ padding: '4px 8px 4px 0' }}>MDA</th>
                <th style={{ textAlign: 'right' }}>Lines</th>
                <th style={{ textAlign: 'right' }}>Total</th>
                <th style={{ textAlign: 'right' }}>Draft</th>
                <th style={{ textAlign: 'right' }}>With legislature</th>
                <th style={{ textAlign: 'right' }}>Enacted</th>
                <th style={{ textAlign: 'right' }}>% of original</th>
              </tr>
            </thead>
            <tbody>
              {supplementaryReport.data!.rows.map((r) => (
                <tr key={r.mda} data-testid="bh-supplementary-row" style={{ color: '#334155' }}>
                  <td style={{ padding: '4px 8px 4px 0' }}>{r.mda}</td>
                  <td style={{ textAlign: 'right' }}>{r.lines}</td>
                  <td style={{ textAlign: 'right', fontWeight: 700 }}>{money(r.total)}</td>
                  <td style={{ textAlign: 'right' }}>{money(r.draft)}</td>
                  <td style={{ textAlign: 'right' }}>{money(r.before_legislature)}</td>
                  <td style={{ textAlign: 'right' }}>{money(r.enacted)}</td>
                  <td style={{ textAlign: 'right' }}>{r.percent_of_original === null ? 'n/a' : `${r.percent_of_original}%`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  );
}
