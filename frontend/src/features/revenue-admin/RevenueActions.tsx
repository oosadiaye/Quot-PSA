import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { message } from 'antd';
import apiClient from '../../api/client';
import { ReferenceField } from '../_base/ReferenceField';
import type { EntityField } from '../_base/types';
import '../_base/crud.css';
import './revenue-actions.css';

interface Draft { id: number; label: string; amount?: string }
type Tab = 'assessment' | 'billingRun' | 'demandNotice' | 'taxClearanceCertificate';

const naira = (v: string) => `₦${Number(v).toLocaleString('en-NG', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const apiError = (e: unknown) => (e as { response?: { data?: { error?: string; detail?: string } } })?.response?.data?.error
  ?? (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Something went wrong. Try again.';
const taxpayerField: EntityField = { name: 'taxpayer', label: 'Taxpayer', type: 'integer', reference: { module: 'revenue_admin', entity: 'taxpayer' } };

/** Lists the draft records of one kind, each with a button that runs its action. */
function DraftList({ tab, title, queryPath, params, actionPath, verb, describe }: {
  tab: Tab; title: string; queryPath: string; params: Record<string, string>; actionPath: (id: number) => string; verb: string;
  describe: (row: Record<string, unknown>) => Draft;
}) {
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const drafts = useQuery({
    queryKey: ['revenue-actions', tab],
    queryFn: async (): Promise<Draft[]> => {
      const { data } = await apiClient.get(queryPath, { params });
      return ((data.results ?? data ?? []) as Record<string, unknown>[]).map(describe);
    },
  });
  const run = useMutation({
    mutationFn: async (id: number) => (await apiClient.post(actionPath(id), {})).data,
    onSuccess: () => { setError(null); message.success(`${verb} done.`); void qc.invalidateQueries(); },
    onError: (e) => setError(apiError(e)),
  });
  const rows = drafts.data ?? [];
  return (
    <section className="ra-card" data-testid={`ra-${tab}`} aria-label={title}>
      <h3>{title}</h3>
      {error && <div className="ra-error" role="alert">{error}</div>}
      {rows.length === 0 ? <p className="ra-hint">Nothing waiting.</p> : (
        <ul className="ra-list">
          {rows.map((r) => (
            <li key={r.id}>
              <span>{r.label}{r.amount ? <b> {naira(r.amount)}</b> : null}</span>
              <button type="button" className="ef-btn ef-btn-primary" data-testid={`ra-${tab}-run`} disabled={run.isPending} onClick={() => run.mutate(r.id)}>{verb}</button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function AgeingCard() {
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const age = useMutation({
    mutationFn: async () => (await apiClient.post('/revenue-admin/demand-notices/update-ageing/', {})).data as { notices_marked_overdue: number; arrears_aged: number },
    onSuccess: (r) => { setError(null); message.success(`${r.notices_marked_overdue} notice(s) marked overdue; ${r.arrears_aged} arrears aged.`); void qc.invalidateQueries(); },
    onError: (e) => setError(apiError(e)),
  });
  return (
    <section className="ra-card" data-testid="ra-demandNotice" aria-label="Ageing">
      <h3>Ageing</h3>
      {error && <div className="ra-error" role="alert">{error}</div>}
      <p className="ra-hint">Marks unpaid notices past their due date overdue and refreshes the age of unsettled arrears.</p>
      <button type="button" className="ef-btn ef-btn-primary" data-testid="ra-ageing-run" disabled={age.isPending} onClick={() => age.mutate()}>Update ageing</button>
    </section>
  );
}

function ClearanceCard() {
  const qc = useQueryClient();
  const [taxpayer, setTaxpayer] = useState<number | ''>('');
  const [year, setYear] = useState(String(new Date().getFullYear()));
  const [error, setError] = useState<string | null>(null);
  const issue = useMutation({
    mutationFn: async () => (await apiClient.post('/revenue-admin/clearance-certificates/issue/', { taxpayer, fiscal_year: Number(year) })).data as { certificate_number: string },
    onSuccess: (r) => { setError(null); message.success(`Certificate ${r.certificate_number} issued.`); void qc.invalidateQueries(); },
    onError: (e) => setError(apiError(e)),
  });
  return (
    <section className="ra-card" data-testid="ra-taxClearanceCertificate" aria-label="Issue a clearance certificate">
      <h3>Issue a clearance certificate</h3>
      {error && <div className="ra-error" role="alert" data-testid="ra-clearance-error">{error}</div>}
      <div className="ra-form">
        <label htmlFor="ra-taxpayer-input">Taxpayer</label>
        <ReferenceField field={taxpayerField} id="ra-taxpayer-input" value={taxpayer} onChange={setTaxpayer} />
        <label htmlFor="ra-year">Fiscal year</label>
        <input id="ra-year" inputMode="numeric" value={year} onChange={(e) => setYear(e.target.value)} />
      </div>
      <p className="ra-hint">A certificate is issued only when the taxpayer has no unsettled arrears and no unpaid notice past its due date.</p>
      <button type="button" className="ef-btn ef-btn-primary" data-testid="ra-clearance-run" disabled={taxpayer === '' || !/^\d{4}$/.test(year) || issue.isPending} onClick={() => issue.mutate()}>Issue certificate</button>
    </section>
  );
}

/** The actions of the revenue lifecycle, shown above the register they belong to. */
export default function RevenueActions({ tab }: { tab: string }) {
  if (tab === 'assessment') {
    return <DraftList tab="assessment" title="Draft assessments to issue" queryPath="/revenue-admin/assessments/" params={{ status: 'draft' }}
      actionPath={(id) => `/revenue-admin/assessments/${id}/issue/`} verb="Issue"
      describe={(r) => ({ id: r.id as number, label: `Assessment ${r.id} · ${r.fiscal_year}`, amount: String(r.assessed_amount ?? '0') })} />;
  }
  if (tab === 'billingRun') {
    return <DraftList tab="billingRun" title="Billing runs to process" queryPath="/revenue-admin/billing-runs/" params={{ status: 'draft' }}
      actionPath={(id) => `/revenue-admin/billing-runs/${id}/process/`} verb="Process"
      describe={(r) => ({ id: r.id as number, label: `${(r.cycle as string) || 'Billing run'} · ${r.fiscal_year}` })} />;
  }
  if (tab === 'demandNotice') return <AgeingCard />;
  if (tab === 'taxClearanceCertificate') return <ClearanceCard />;
  return null;
}
