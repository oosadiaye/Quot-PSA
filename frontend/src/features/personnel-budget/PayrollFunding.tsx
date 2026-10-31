import { useMemo, useState } from 'react';
import { message } from 'antd';
import { useCurrency } from '../../context/CurrencyContext';
import {
  fundingError, isModuleOffError, useFundRun, useFundingSuggestions, usePayrollRuns, useRunBinding,
  type FundingCandidate, type PayrollRunRow,
} from './usePayrollFunding';

const card: React.CSSProperties = { background: '#fff', border: '1px solid #e2e8f0', borderRadius: 14, padding: '16px 18px', minWidth: 0 };
const label: React.CSSProperties = { fontSize: 12, fontWeight: 600, color: '#475569', display: 'block', marginBottom: 4 };
const input: React.CSSProperties = { width: '100%', padding: '9px 11px', borderRadius: 8, border: '1px solid #cbd5e1', fontSize: 14, boxSizing: 'border-box' };
const primary: React.CSSProperties = { padding: '7px 12px', borderRadius: 8, border: 'none', background: 'linear-gradient(135deg, #242a88, #2e35a0)', color: '#fff', fontWeight: 600, fontSize: 13, cursor: 'pointer' };
const errorBox: React.CSSProperties = { background: '#fef2f2', border: '1px solid #fecaca', color: '#991b1b', borderRadius: 8, padding: '8px 12px', fontSize: 13 };
const heading: React.CSSProperties = { fontSize: 11, fontWeight: 700, letterSpacing: '.06em', textTransform: 'uppercase', color: '#64748b', marginBottom: 8 };

/**
 * Which appropriation pays for a payroll run. Suggests active personnel lines for the run's year, those with enough
 * balance first, and binds the run to the one the officer picks; the payroll gate then checks that line when the run posts.
 */
export default function PayrollFunding() {
  const { formatCurrency } = useCurrency();
  const money = (v: string | number | undefined) => formatCurrency(Number(v ?? 0));
  const runs = usePayrollRuns();
  const [picked, setPicked] = useState<number | null>(null);
  const run: PayrollRunRow | undefined = useMemo(
    () => (runs.data ?? []).find((r) => r.id === picked) ?? (runs.data ?? [])[0], [runs.data, picked]);
  const runId = run?.id ?? null;
  const suggestions = useFundingSuggestions(runId);
  const binding = useRunBinding(runId);
  const fund = useFundRun();
  const [error, setError] = useState<string | null>(null);

  if (runs.isLoading) return null;
  if (runs.isError) {
    return (
      <section data-testid="payroll-funding" style={{ ...card, marginBottom: 16, fontSize: 13, color: '#64748b' }}>
        <div style={heading}>Fund a payroll run</div>
        {isModuleOffError(runs.error)
          ? 'Payroll runs belong to the HR module, which is not available here, so there is nothing to fund yet.'
          : 'Payroll runs could not be loaded. Please refresh.'}
      </section>
    );
  }
  if (!run) {
    return (
      <section data-testid="payroll-funding" style={{ ...card, marginBottom: 16, fontSize: 13, color: '#64748b' }}>
        <div style={heading}>Fund a payroll run</div>
        <span data-testid="pf-none">No open payroll runs need funding.</span>
      </section>
    );
  }

  const boundTo = binding.data?.appropriation_line ?? null;
  const choose = async (c: FundingCandidate) => {
    setError(null);
    try {
      await fund.mutateAsync({ runId: run.id, appropriationId: c.id, existingBindingId: binding.data?.id });
      message.success(`${run.run_number} is funded from ${c.economic_code} ${c.economic_name}`);
    } catch (e) { setError(fundingError(e)); }
  };

  return (
    <section data-testid="payroll-funding" style={{ ...card, marginBottom: 16, display: 'grid', gap: 12 }}>
      <div style={heading}>Fund a payroll run</div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'end' }}>
        <div style={{ flex: '1 1 280px' }}>
          <label style={label} htmlFor="pf-run">Payroll run</label>
          <select id="pf-run" data-testid="pf-run" style={input} value={run.id}
            onChange={(e) => { setPicked(Number(e.target.value)); setError(null); }}>
            {(runs.data ?? []).map((r) => (
              <option key={r.id} value={r.id}>{r.run_number} – {r.period_name} – {money(r.total_gross)}</option>
            ))}
          </select>
        </div>
        <div data-testid="pf-status" style={{ fontSize: 13, color: '#334155' }}>
          <span style={{ ...label, display: 'block' }}>Funding</span>
          {boundTo ? 'Funded' : 'Not yet funded'}
        </div>
      </div>

      {error && <div role="alert" data-testid="pf-error" style={errorBox}>{error}</div>}

      {suggestions.isError ? (
        <div role="alert" data-testid="pf-suggest-error" style={errorBox}>{fundingError(suggestions.error)}</div>
      ) : (suggestions.data?.candidates ?? []).length === 0 ? (
        <p data-testid="pf-no-lines" style={{ fontSize: 13, color: '#64748b', margin: 0 }}>
          No active personnel appropriations were found for this run’s year. Enact one in Budget &amp; Appropriation first.
        </p>
      ) : (
        <table data-no-tools style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13, fontVariantNumeric: 'tabular-nums' }}>
          <thead>
            <tr style={{ textAlign: 'left', color: '#64748b' }}>
              <th style={{ padding: '4px 8px 4px 0' }}>MDA</th>
              <th>Line</th>
              <th style={{ textAlign: 'right' }}>Approved</th>
              <th style={{ textAlign: 'right' }}>Available</th>
              <th>Covers this run</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {suggestions.data!.candidates.map((c) => (
              <tr key={c.id} data-testid="pf-candidate" style={{ color: '#334155', background: c.id === boundTo ? '#eef2ff' : undefined }}>
                <td style={{ padding: '4px 8px 4px 0' }}>{c.mda}</td>
                <td>{c.economic_code} {c.economic_name}</td>
                <td style={{ textAlign: 'right' }}>{money(c.approved)}</td>
                <td style={{ textAlign: 'right' }}>{money(c.available)}</td>
                <td style={{ color: c.covers ? '#166534' : '#991b1b', fontWeight: 600 }}>{c.covers ? 'Yes' : 'No, short'}</td>
                <td style={{ textAlign: 'right' }}>
                  {c.id === boundTo
                    ? <span data-testid="pf-current" style={{ fontWeight: 600, color: '#242a88' }}>Current</span>
                    : <button type="button" style={primary} data-testid="pf-fund" disabled={fund.isPending} onClick={() => choose(c)}>
                      {boundTo ? 'Switch to this line' : 'Fund from this line'}
                    </button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
