import { useState } from 'react';
import { useCurrency } from '../../../context/CurrencyContext';
import { STATUS_MARK, STATUS_WORD, ruleSlug } from './mtefLayout';
import { mtefError, useScenario, type Scenario } from './useMtef';

const asNumber = (text: string) => (text.trim() === '' ? 0 : Number(text));
const valid = (text: string) => text.trim() === '' || Number.isFinite(Number(text));

/**
 * What if the oil price falls, IGR disappoints, or costs rise? Runs the framework against a shock without changing it,
 * and shows the balance, the verdict, and which fiscal rules the shock newly breaks.
 */
export default function MtefScenario({ baseYear }: { baseYear: number }) {
  const { formatCurrency } = useCurrency();
  const money = (v: string) => formatCurrency(Number(v));
  const run = useScenario();
  const [oil, setOil] = useState('-30');
  const [igr, setIgr] = useState('0');
  const [cost, setCost] = useState('0');
  const [result, setResult] = useState<Scenario | null>(null);
  const [error, setError] = useState<string | null>(null);
  const ok = valid(oil) && valid(igr) && valid(cost);

  const go = async () => {
    setError(null);
    try {
      setResult(await run.mutateAsync({ base_year: baseYear, oil_price_change_pct: asNumber(oil), igr_change_pct: asNumber(igr), cost_change_pct: asNumber(cost) }));
    } catch (e) { setResult(null); setError(mtefError(e)); }
  };

  const field = (id: string, label: string, value: string, set: (v: string) => void, hint: string) => (
    <div className="mtef-field">
      <label htmlFor={id}>{label}</label>
      <input id={id} data-testid={id} inputMode="decimal" value={value} aria-invalid={!valid(value) || undefined} onChange={(e) => set(e.target.value)} />
      <p className="mtef-sub" style={{ fontSize: 12, marginTop: 4 }}>{hint}</p>
    </div>
  );

  return (
    <div data-testid="mtef-scenario">
      <h3>Test the framework against a shock</h3>
      <p className="mtef-sub">Enter the change you want to test; nothing is saved. Use a minus sign for a fall.</p>
      <div className="mtef-grid3" style={{ marginTop: 12 }}>
        {field('mtef-oil', 'Oil price change (%)', oil, setOil, 'Moves the statutory allocation and VAT, by the oil sensitivity set for each year.')}
        {field('mtef-igr', 'IGR change (%)', igr, setIgr, 'Moves internally generated revenue.')}
        {field('mtef-cost', 'Cost change (%)', cost, setCost, 'Moves personnel, overhead and other recurrent spending.')}
      </div>
      <div style={{ marginTop: 12 }}>
        <button type="button" className="ef-btn" data-testid="mtef-scenario-run" disabled={!ok || run.isPending} onClick={go}>
          {run.isPending ? 'Running…' : 'Run scenario'}
        </button>
      </div>
      {error && <div className="mtef-error" role="alert" style={{ marginTop: 12 }}>{error}</div>}

      {result && (
        <div className="mtef-scroll" style={{ marginTop: 14 }}>
          <table className="mtef-table" data-no-tools data-testid="mtef-scenario-result" style={{ minWidth: 560 }}>
            <thead>
              <tr>
                <th scope="col"><span className="sr-only">Measure</span></th>
                {result.years.map((y) => <th scope="col" key={y.year}><div className="mtef-year">{y.year}</div></th>)}
              </tr>
            </thead>
            <tbody>
              <tr><td>Revenue after the shock</td>{result.years.map((y) => <td key={y.year}>{money(y.after.revenue)}</td>)}</tr>
              <tr><td>Expenditure after the shock</td>{result.years.map((y) => <td key={y.year}>{money(y.after.expenditure)}</td>)}</tr>
              <tr className="total">
                <td>Change in the fiscal balance</td>
                {result.years.map((y) => (
                  <td key={y.year} data-testid={`mtef-shock-change-${y.year}`} className={Number(y.balance_change) < 0 ? 'neg' : undefined}>{money(y.balance_change)}</td>
                ))}
              </tr>
              <tr><td>Unfinanced gap afterwards</td>{result.years.map((y) => <td key={y.year}>{money(y.after.unfinanced_gap)}</td>)}</tr>
              <tr>
                <td>Overall verdict</td>
                {result.years.map((y) => (
                  <td key={y.year}>
                    <span className={`mtef-pill ${y.overall}`} data-testid={`mtef-shock-verdict-${y.year}`}>
                      <span aria-hidden="true">{STATUS_MARK[y.overall]}</span> {STATUS_WORD[y.overall]}
                    </span>
                  </td>
                ))}
              </tr>
              <tr>
                <td>Rules the shock newly breaks</td>
                {result.years.map((y) => (
                  <td key={y.year} data-testid={`mtef-shock-new-${y.year}`}>
                    {y.newly_failing.length === 0 ? <span className="muted">None</span> : y.newly_failing.map((f) => (
                      <div key={f.rule} data-testid={`mtef-shock-new-${ruleSlug(f.rule)}-${y.year}`}>{f.rule}</div>
                    ))}
                  </td>
                ))}
              </tr>
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
