import { useMemo, useState } from 'react';
import { message } from 'antd';
import { useCurrency } from '../../../context/CurrencyContext';
import type { BannerContext } from '../../_base/ModuleCrudPage';
import '../../_base/crud.css';
import './mtef.css';
import MtefPolicy from './MtefPolicy';
import MtefScenario from './MtefScenario';
import {
  CEILING_LABEL, EXPENDITURE_ROWS, FINANCING_ROWS, MTEF_STATUS_LABEL, RATIO_ROWS, REVENUE_ROWS, STATUS_MARK, STATUS_WORD, ruleSlug,
  type MoneyRow,
} from './mtefLayout';
import { fetchProjection, mtefError, useApprove, useFramework, useReopen, useRollForward, type Finding, type YearView } from './useMtef';

const validYear = (n: number) => Number.isInteger(n) && n > 1990 && n < 2200;

/** An action awaiting the officer's reason: approving a framework that breaks a rule, or reopening an approved one. */
type Pending = { kind: 'approve' | 'reopen'; year: YearView; why: string };

/**
 * The Medium Term Expenditure Framework for a budget year and the two after it: the resource envelope by source,
 * expenditure by category, financing, the macro assumptions, and each fiscal rule's verdict, with the means to roll
 * the framework forward, test it against shocks, and approve it. Editing a year opens the usual form.
 */
export default function MtefFramework({ openForm }: { openForm: BannerContext['openForm'] }) {
  const { formatCurrency } = useCurrency();
  const money = (v?: string | null) => (v === undefined || v === null ? '–' : formatCurrency(Number(v)));
  const [yearText, setYearText] = useState(String(new Date().getFullYear() + 1));
  const base = Number(yearText);
  const fw = useFramework(validYear(base) ? base : null);
  const roll = useRollForward();
  const approve = useApprove();
  const reopen = useReopen();
  const [pending, setPending] = useState<Pending | null>(null);
  const [reason, setReason] = useState('');
  const [error, setError] = useState<string | null>(null);

  const years = fw.data?.years ?? [];
  const present = years.filter((y) => !y.missing);
  const policy = fw.data?.policy;
  const baseRow = years[0];
  const rules = useMemo(() => Array.from(new Set(present.flatMap((y) => (y.findings ?? []).map((f) => f.rule)))), [present]);
  const attention = present.flatMap((y) => (y.findings ?? []).filter((f) => f.status !== 'pass').map((f) => ({ year: y.year, f })));
  const canRoll = !!baseRow && !baseRow.missing && years.some((y) => y.missing);

  const edit = async (y: YearView) => openForm('mtefProjection', y.id ? await fetchProjection(y.id) : null);
  const add = (year: number) => openForm('mtefProjection', null, {
    fiscal_year: year,
    ...(baseRow && !baseRow.missing && baseRow.assumptions ? {
      inflation_assumption: baseRow.assumptions.inflation, exchange_rate_assumption: baseRow.assumptions.exchange_rate,
      oil_price_assumption: baseRow.assumptions.oil_price ?? '', oil_sensitivity: baseRow.assumptions.oil_sensitivity,
    } : {}),
  });

  const doRoll = async () => {
    setError(null);
    try {
      const r = await roll.mutateAsync({ base_year: base });
      message.success(r.created.length ? `Rolled ${base} forward into ${r.created.join(' and ')}` : 'The outer years already exist');
    } catch (e) { setError(mtefError(e)); }
  };

  const doApprove = async (y: YearView, override?: string) => {
    setError(null);
    try {
      await approve.mutateAsync({ id: y.id!, override_reason: override });
      message.success(`The ${y.year} MTEF is approved`);
      setPending(null);
      setReason('');
    } catch (e) {
      const text = mtefError(e);
      if ((e as { response?: { status?: number } })?.response?.status === 400 && /fiscal rule/i.test(text)) setPending({ kind: 'approve', year: y, why: text });
      else setError(text);
    }
  };

  const doReopen = async (y: YearView) => {
    setError(null);
    try {
      await reopen.mutateAsync({ id: y.id!, reason });
      message.success(`The ${y.year} MTEF is open for changes again`);
      setPending(null);
      setReason('');
    } catch (e) { setError(mtefError(e)); }
  };

  const cells = (render: (y: YearView) => React.ReactNode, className?: (y: YearView) => string | undefined) =>
    years.map((y) => <td key={y.year} className={y.missing ? 'muted' : className?.(y)}>{y.missing ? '–' : render(y)}</td>);

  const moneyRows = (rows: MoneyRow[], source: 'revenue' | 'expenditure' | 'financing') =>
    rows.map((r) => (
      <tr key={r.key}>
        <td>{r.label}{r.note && <span className="note">{r.note}</span>}</td>
        {cells((y) => money(y[source]?.[r.key]))}
      </tr>
    ));

  return (
    <section className="mtef" data-testid="mtef-panel" aria-labelledby="mtef-title">
      <div className="mtef-bar">
        <div>
          <h3 id="mtef-title">Medium Term Expenditure Framework</h3>
          <p className="mtef-sub">
            The budget year and the two after it: what revenue is expected, how it is spent and financed, and whether the plan keeps
            to the government&rsquo;s fiscal rules. Approve it before MDA ceilings are issued.
          </p>
        </div>
        <div className="mtef-controls">
          <div className="mtef-field mtef-year-input">
            <label htmlFor="mtef-base-year">Budget year</label>
            <input id="mtef-base-year" data-testid="mtef-base-year" inputMode="numeric" value={yearText}
              aria-invalid={!validYear(base) || undefined} onChange={(e) => { setYearText(e.target.value); setError(null); setPending(null); }} />
          </div>
          <button type="button" className="ef-btn" data-testid="mtef-roll" disabled={!canRoll || roll.isPending} onClick={doRoll}
            title="Create the outer years from the budget year, growing each line by inflation">
            {roll.isPending ? 'Working…' : 'Roll forward'}
          </button>
        </div>
      </div>

      {error && <div className="mtef-error" role="alert" data-testid="mtef-error">{error}</div>}
      {!validYear(base) && <div className="mtef-error" role="alert">Enter a real budget year, for example {new Date().getFullYear() + 1}.</div>}

      {fw.isLoading && validYear(base) && <p className="mtef-sub" aria-busy="true">Loading the framework…</p>}

      {fw.data && (
        <>
          <div className="mtef-scroll">
            <table className="mtef-table" data-no-tools data-testid="mtef-table">
              <caption className="sr-only">Medium term expenditure framework for {base} to {base + 2}</caption>
              <thead>
                <tr>
                  <th scope="col"><span className="sr-only">Line</span></th>
                  {years.map((y) => (
                    <th scope="col" key={y.year} data-testid={`mtef-year-${y.year}`}>
                      <div className="mtef-year">{y.year}</div>
                      {y.missing ? (
                        <>
                          <span className="mtef-pill neutral">Not entered</span>
                          <div className="mtef-year-actions">
                            <button type="button" className="ef-btn" data-testid={`mtef-add-${y.year}`} onClick={() => add(y.year)}>Add {y.year}</button>
                          </div>
                        </>
                      ) : (
                        <>
                          <span className={`mtef-pill ${y.status === 'approved' ? 'approved' : 'neutral'}`} data-testid={`mtef-status-${y.year}`}>
                            {y.status === 'approved' ? '\u{1F512} ' : ''}{MTEF_STATUS_LABEL[y.status ?? 'draft']}
                          </span>
                          <div className="mtef-year-actions">
                            <button type="button" className="ef-btn" data-testid={`mtef-edit-${y.year}`} disabled={y.status === 'approved'}
                              title={y.status === 'approved' ? 'Approved: reopen it to change it' : undefined} onClick={() => edit(y)}>Edit</button>
                            {y.status === 'approved' ? (
                              <button type="button" className="ef-btn" data-testid={`mtef-reopen-${y.year}`}
                                onClick={() => { setPending({ kind: 'reopen', year: y, why: '' }); setReason(''); setError(null); }}>Reopen</button>
                            ) : (
                              <button type="button" className="ef-btn ef-btn-primary" data-testid={`mtef-approve-${y.year}`}
                                disabled={approve.isPending} onClick={() => doApprove(y)}>Approve</button>
                            )}
                          </div>
                        </>
                      )}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                <tr className="group"><td colSpan={4}>Assumptions</td></tr>
                <tr><td>Inflation</td>{cells((y) => `${y.assumptions?.inflation}%`)}</tr>
                <tr><td>Exchange rate<span className="note">per US dollar</span></td>{cells((y) => money(y.assumptions?.exchange_rate))}</tr>
                <tr><td>Oil price<span className="note">US dollars a barrel</span></td>{cells((y) => (y.assumptions?.oil_price ? Number(y.assumptions.oil_price).toLocaleString() : '–'))}</tr>

                <tr className="group"><td colSpan={4}>Revenue</td></tr>
                {moneyRows(REVENUE_ROWS, 'revenue')}
                <tr className="total"><td>Total revenue</td>{cells((y) => money(y.totals?.revenue))}</tr>

                <tr className="group"><td colSpan={4}>Expenditure</td></tr>
                {moneyRows(EXPENDITURE_ROWS, 'expenditure')}
                <tr className="total"><td>Total expenditure</td>{cells((y) => money(y.totals?.expenditure))}</tr>

                <tr className="group"><td colSpan={4}>Balance and financing</td></tr>
                <tr className="total" data-testid="mtef-balance-row">
                  <td>Fiscal balance<span className="note">surplus, or deficit shown negative</span></td>
                  {years.map((y) => (
                    <td key={y.year} data-testid={`mtef-balance-${y.year}`} className={y.missing ? 'muted' : Number(y.totals?.balance) < 0 ? 'neg' : undefined}>
                      {y.missing ? '–' : money(y.totals?.balance)}
                    </td>
                  ))}
                </tr>
                {moneyRows(FINANCING_ROWS, 'financing')}
                <tr className="total"><td>Total financing</td>{cells((y) => money(y.totals?.financing))}</tr>
                <tr className={years.some((y) => !y.missing && Number(y.totals?.unfinanced_gap) > 0) ? 'bad' : undefined}>
                  <td>Unfinanced gap</td>
                  {years.map((y) => (
                    <td key={y.year} data-testid={`mtef-gap-${y.year}`} className={y.missing ? 'muted' : undefined}>{y.missing ? '–' : money(y.totals?.unfinanced_gap)}</td>
                  ))}
                </tr>

                <tr className="group"><td colSpan={4}>Key ratios</td></tr>
                {RATIO_ROWS.map((r) => (
                  <tr key={r.key}>
                    <td>{r.label}{policy && <span className="note">{r.bound === 'max' ? 'limit' : 'floor'} {String(policy[r.limit])}%</span>}</td>
                    {cells((y) => (y.ratios?.[r.key] ? `${y.ratios[r.key]}%` : '–'))}
                  </tr>
                ))}

                <tr className="group"><td colSpan={4}>Fiscal rules</td></tr>
                {rules.map((rule) => (
                  <tr key={rule}>
                    <td>{rule}</td>
                    {years.map((y) => {
                      const f = y.findings?.find((x) => x.rule === rule);
                      return (
                        <td key={y.year} className={y.missing ? 'muted' : undefined}>
                          {y.missing || !f ? '–' : (
                            <span className={`mtef-pill ${f.status}`} title={f.message} data-testid={`mtef-rule-${ruleSlug(rule)}-${y.year}`}>
                              <span aria-hidden="true">{STATUS_MARK[f.status]}</span> {STATUS_WORD[f.status]}
                            </span>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {present.length === 0 && (
            <p className="mtef-sub" data-testid="mtef-empty">
              No framework has been entered for {base} to {base + 2} yet. Add {base} to begin, then roll it forward into the outer years.
            </p>
          )}

          {pending && (
            <div className="mtef-decision" role="group" aria-label={pending.kind === 'approve' ? 'Approve despite rule failures' : 'Reopen an approved framework'} data-testid="mtef-decision">
              <strong>{pending.kind === 'approve' ? `The ${pending.year.year} MTEF breaks a fiscal rule` : `Reopen the ${pending.year.year} MTEF`}</strong>
              <span>
                {pending.kind === 'approve'
                  ? `${pending.why} The reason you give is kept with the approval.`
                  : 'An approved framework is locked. Say why it is being reopened; the reason is kept on the record.'}
              </span>
              <label className="sr-only" htmlFor="mtef-reason">Reason</label>
              <textarea id="mtef-reason" data-testid="mtef-reason" value={reason} onChange={(e) => setReason(e.target.value)}
                placeholder={pending.kind === 'approve' ? 'Why is it right to approve this now?' : 'Why does it need to change?'} />
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                <button type="button" className="ef-btn ef-btn-primary" data-testid="mtef-decision-confirm"
                  disabled={reason.trim() === '' || approve.isPending || reopen.isPending}
                  onClick={() => (pending.kind === 'approve' ? doApprove(pending.year, reason) : doReopen(pending.year))}>
                  {pending.kind === 'approve' ? 'Approve anyway' : 'Reopen'}
                </button>
                <button type="button" className="ef-btn" onClick={() => { setPending(null); setReason(''); }}>Cancel</button>
              </div>
            </div>
          )}

          {present.length > 0 && (
            <div>
              <h3>What needs attention</h3>
              {attention.length === 0 ? (
                <p className="mtef-allgood" data-testid="mtef-allgood">Every fiscal rule is met for the years entered.</p>
              ) : (
                <ul className="mtef-attention" data-testid="mtef-attention" style={{ marginTop: 10 }}>
                  {attention.map(({ year, f }: { year: number; f: Finding }) => (
                    <li key={`${year}-${f.rule}`} className={f.status} data-testid="mtef-attention-item">
                      <b>{year} &middot; {f.rule}.</b> {f.message}
                    </li>
                  ))}
                </ul>
              )}
              {baseRow?.prior_outturn && (
                <p className="mtef-outturn" style={{ marginTop: 12 }} data-testid="mtef-outturn">
                  Last year&rsquo;s actual spending ({baseRow.prior_outturn.year}): <b>{money(baseRow.prior_outturn.total)}</b>, of which
                  personnel {money(baseRow.prior_outturn.personnel)}, overheads {money(baseRow.prior_outturn.overhead)}, capital {money(baseRow.prior_outturn.capital)}.
                </p>
              )}
            </div>
          )}

          {baseRow && !baseRow.missing && (baseRow.ceilings?.length ?? 0) > 0 && (
            <div>
              <h3>MDA ceilings against the {base} envelope</h3>
              <div className="mtef-scroll" style={{ marginTop: 10 }}>
                <table className="mtef-table" data-no-tools data-testid="mtef-ceilings" style={{ minWidth: 520 }}>
                  <thead>
                    <tr><th scope="col">Type</th><th scope="col">Envelope</th><th scope="col">Allocated to MDAs</th><th scope="col">Headroom</th></tr>
                  </thead>
                  <tbody>
                    {baseRow.ceilings!.map((c) => (
                      <tr key={c.type} className={c.over ? 'bad' : undefined} data-testid={`mtef-ceiling-${c.type}`}>
                        <td>{CEILING_LABEL[c.type]}</td><td>{money(c.envelope)}</td><td>{money(c.allocated)}</td>
                        <td>{c.over ? `Over by ${money(String(-Number(c.headroom)))}` : money(c.headroom)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {present.length > 0 && <MtefScenario baseYear={base} />}
        </>
      )}

      <details className="mtef-details">
        <summary>Fiscal rules and their limits</summary>
        <MtefPolicy />
      </details>
    </section>
  );
}
