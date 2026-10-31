import { useState } from 'react';
import { message } from 'antd';
import { useCurrency } from '../../context/CurrencyContext';
import {
  PAGE_SIZE, planningError, useGenerate, useRecommendationAction, useRecommendations,
  type GenerationSummary, type RecommendationRow,
} from './useWarrantPlanning';

const STATUS_LABEL: Record<RecommendationRow['status'], { label: string; color: string }> = {
  proposed: { label: 'Proposed', color: '#92400e' },
  accepted: { label: 'Accepted', color: '#1e40af' },
  converted: { label: 'Warrant issued', color: '#166534' },
  rejected: { label: 'Rejected', color: '#64748b' },
};
const ddmmyyyy = (iso: string | null) => (iso ? iso.slice(0, 10).split('-').reverse().join('/') : '');

const card: React.CSSProperties = { background: '#fff', border: '1px solid #e2e8f0', borderRadius: 14, padding: '16px 18px', minWidth: 0 };
const label: React.CSSProperties = { fontSize: 12, fontWeight: 600, color: '#475569', display: 'block', marginBottom: 4 };
const input: React.CSSProperties = { width: '100%', padding: '9px 11px', borderRadius: 8, border: '1px solid #cbd5e1', fontSize: 14, boxSizing: 'border-box' };
const btn: React.CSSProperties = { padding: '7px 12px', borderRadius: 8, border: '1px solid #cbd5e1', background: '#fff', color: '#242a88', fontWeight: 600, fontSize: 13, cursor: 'pointer' };
const primary: React.CSSProperties = { ...btn, background: 'linear-gradient(135deg, #242a88, #2e35a0)', color: '#fff', border: 'none' };
const errorBox: React.CSSProperties = { background: '#fef2f2', border: '1px solid #fecaca', color: '#991b1b', borderRadius: 8, padding: '8px 12px', fontSize: 13 };
const heading: React.CSSProperties = { fontSize: 11, fontWeight: 700, letterSpacing: '.06em', textTransform: 'uppercase', color: '#64748b', marginBottom: 8 };

/**
 * Warrant planning: propose the cash release for a quarter from each active appropriation's phased budget, then accept,
 * reject, or issue each one. Recommendations are advice; a warrant is only created when the officer issues one with the
 * reference of the warrant letter, and it then follows Budget's normal release steps.
 */
export default function WarrantPlanning() {
  const { formatCurrency } = useCurrency();
  const money = (v: string | number | undefined) => formatCurrency(Number(v ?? 0));
  const [year, setYear] = useState(String(new Date().getFullYear()));
  const [quarter, setQuarter] = useState(String(Math.floor(new Date().getMonth() / 3) + 1));
  const [cash, setCash] = useState('');
  const [summary, setSummary] = useState<GenerationSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [issuing, setIssuing] = useState<number | null>(null);
  const [reference, setReference] = useState('');
  const [page, setPage] = useState(1);

  const yearNumber = Number(year);
  const yearValid = Number.isInteger(yearNumber) && yearNumber > 1990 && yearNumber < 2200;
  const cashValid = cash.trim() === '' || Number.isFinite(Number(cash));
  const recs = useRecommendations(yearValid ? yearNumber : 0, Number(quarter), page);
  const generate = useGenerate();
  const act = useRecommendationAction();
  const rows = yearValid ? recs.data?.rows ?? [] : [];
  const total = yearValid ? recs.data?.count ?? 0 : 0;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const runGenerate = async () => {
    setError(null);
    try {
      const r = await generate.mutateAsync({
        fiscal_year: yearNumber, quarter: Number(quarter), ...(cash.trim() ? { available_cash: cash.trim() } : {}),
      });
      setSummary(r);
      setPage(1);
      message.success(r.created ? `Proposed ${r.created} release(s) totalling ${money(r.total)}` : 'Nothing further to propose for this quarter');
    } catch (e) { setSummary(null); setError(planningError(e)); }
  };

  const run = async (row: RecommendationRow, action: 'accept' | 'reject' | 'convert', body?: Record<string, string>, done?: string) => {
    setError(null);
    try {
      await act.mutateAsync({ id: row.id, action, body });
      if (done) message.success(done);
      setIssuing(null);
      setReference('');
    } catch (e) { setError(planningError(e)); }
  };

  return (
    <section data-testid="warrant-planning" style={{ ...card, marginBottom: 16, display: 'grid', gap: 12 }}>
      <div style={heading}>Warrant planning</div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'end' }}>
        <div style={{ width: 110 }}>
          <label style={label} htmlFor="wp-year">Fiscal year</label>
          <input id="wp-year" data-testid="wp-year" style={input} inputMode="numeric" value={year} onChange={(e) => { setYear(e.target.value); setPage(1); }} />
        </div>
        <div style={{ width: 110 }}>
          <label style={label} htmlFor="wp-quarter">Quarter</label>
          <select id="wp-quarter" data-testid="wp-quarter" style={input} value={quarter} onChange={(e) => { setQuarter(e.target.value); setPage(1); }}>
            {[1, 2, 3, 4].map((q) => <option key={q} value={q}>Q{q}</option>)}
          </select>
        </div>
        <div style={{ flex: '1 1 220px' }}>
          <label style={label} htmlFor="wp-cash">Cash available to release (optional)</label>
          <input id="wp-cash" data-testid="wp-cash" style={input} inputMode="decimal" placeholder="Leave blank for no limit" value={cash}
            onChange={(e) => setCash(e.target.value)} />
          {!cashValid && <div style={{ fontSize: 12, color: '#991b1b', marginTop: 4 }}>Enter a number, for example 250000000.</div>}
        </div>
        <button type="button" style={primary} data-testid="wp-generate" disabled={!yearValid || !cashValid || generate.isPending} onClick={runGenerate}>
          {generate.isPending ? 'Working…' : 'Propose releases'}
        </button>
      </div>

      {error && <div role="alert" data-testid="wp-error" style={errorBox}>{error}</div>}
      {summary && (
        <div data-testid="wp-summary" style={{ fontSize: 13, color: '#334155' }}>
          Proposed {summary.created} release(s) totalling <strong>{money(summary.total)}</strong>
          {summary.scaled_to !== null && <> — scaled down to fit {money(summary.scaled_to)} of cash</>}.
          {summary.skipped.length > 0 && <> {summary.skipped.length} line(s) skipped: {[...new Set(summary.skipped.map((s) => s.reason))].join('; ')}.</>}
        </div>
      )}

      {rows.length === 0 ? (
        <p data-testid="wp-empty" style={{ fontSize: 13, color: '#64748b', margin: 0 }}>
          No recommendations for Q{quarter} {year} yet. Propose releases to see them here.
        </p>
      ) : (
        <table data-no-tools style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13, fontVariantNumeric: 'tabular-nums' }}>
          <thead>
            <tr style={{ textAlign: 'left', color: '#64748b' }}>
              <th style={{ padding: '4px 8px 4px 0' }}>MDA</th>
              <th>Window</th>
              <th style={{ textAlign: 'right' }}>Proposed</th>
              <th>Status</th>
              <th>Basis</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} data-testid="wp-row" style={{ color: '#334155', verticalAlign: 'top' }}>
                <td style={{ padding: '4px 8px 4px 0' }}>{r.mda_name}</td>
                <td>{ddmmyyyy(r.effective_from)} – {ddmmyyyy(r.effective_to)}</td>
                <td style={{ textAlign: 'right', fontWeight: 700 }}>{money(r.proposed_amount)}</td>
                <td style={{ color: STATUS_LABEL[r.status].color, fontWeight: 600 }}>{STATUS_LABEL[r.status].label}</td>
                <td style={{ maxWidth: 360, fontSize: 12, color: '#64748b' }}>{r.rationale}</td>
                <td style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
                  {(r.status === 'proposed' || r.status === 'accepted') && issuing !== r.id && (
                    <span style={{ display: 'inline-flex', gap: 6 }}>
                      {r.status === 'proposed' && <button type="button" style={btn} data-testid="wp-accept" onClick={() => run(r, 'accept')}>Accept</button>}
                      <button type="button" style={primary} data-testid="wp-issue" onClick={() => { setIssuing(r.id); setError(null); }}>Issue warrant</button>
                      <button type="button" style={btn} data-testid="wp-reject" onClick={() => run(r, 'reject', {}, 'Recommendation rejected')}>Reject</button>
                    </span>
                  )}
                  {issuing === r.id && (
                    <span style={{ display: 'inline-flex', gap: 6, alignItems: 'center' }}>
                      <input data-testid="wp-reference" style={{ ...input, width: 190 }} placeholder="Warrant letter reference" value={reference}
                        onChange={(e) => setReference(e.target.value)} />
                      <button type="button" style={primary} data-testid="wp-confirm" disabled={reference.trim() === '' || act.isPending}
                        onClick={() => run(r, 'convert', { authority_reference: reference.trim() }, 'Warrant issued as pending release')}>Confirm</button>
                      <button type="button" style={btn} onClick={() => { setIssuing(null); setReference(''); }}>Cancel</button>
                    </span>
                  )}
                  {r.status === 'converted' && <span data-testid="wp-issued" style={{ color: '#166534' }}>Warrant #{r.warrant}</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {total > PAGE_SIZE && (
        <div data-testid="wp-pager" style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 13, color: '#475569' }}>
          <button type="button" style={btn} data-testid="wp-prev" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</button>
          <span data-testid="wp-range">Showing {(page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, total)} of {total}</span>
          <button type="button" style={btn} data-testid="wp-next" disabled={page >= pages} onClick={() => setPage(page + 1)}>Next</button>
        </div>
      )}
    </section>
  );
}
