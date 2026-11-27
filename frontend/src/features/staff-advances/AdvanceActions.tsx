import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { message } from 'antd';
import apiClient from '../../api/client';
import '../_base/crud.css';
import './advance-actions.css';

type Row = Record<string, unknown>;

const naira = (v: unknown) => `₦${Number(v ?? 0).toLocaleString('en-NG', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const apiError = (e: unknown) => (e as { response?: { data?: { error?: string; detail?: string } } })?.response?.data?.error
  ?? (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Something went wrong. Try again.';

/** Posts to an action URL, refreshes every list on success and shows the server's reason on a refusal. */
function useAction(path: (id: number) => string, done: string) {
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const run = useMutation({
    mutationFn: async (v: { id: number; body?: Row }) => (await apiClient.post(path(v.id), v.body ?? {})).data,
    onSuccess: () => { setError(null); message.success(done); void qc.invalidateQueries(); },
    onError: (e) => setError(apiError(e)),
  });
  return { run, error };
}

function useRows(key: string, path: string) {
  return useQuery({
    queryKey: ['advance-actions', key],
    queryFn: async (): Promise<Row[]> => { const { data } = await apiClient.get(path, { params: { page_size: 100 } }); return data.results ?? data ?? []; },
  });
}

function Card({ title, testId, error, children }: { title: string; testId: string; error: string | null; children: React.ReactNode }) {
  return (
    <section className="aa-card" data-testid={testId} aria-label={title}>
      <h3>{title}</h3>
      {error && <div className="aa-error" role="alert" data-testid={`${testId}-error`}>{error}</div>}
      {children}
    </section>
  );
}

/** Advances not yet paid out, and paid advances still owing, with Disburse / Recover on each. */
function StaffAdvanceActions() {
  const advances = useRows('staffAdvance', '/staff-advances/staff-advances/');
  const disburse = useAction((id) => `/staff-advances/staff-advances/${id}/disburse/`, 'Advance disbursed.');
  const recover = useAction((id) => `/staff-advances/staff-advances/${id}/recover/`, 'Recovery posted.');
  const [amounts, setAmounts] = useState<Record<number, string>>({});
  const rows = advances.data ?? [];
  const waiting = rows.filter((r) => !r.journal);
  const owing = rows.filter((r) => r.journal && r.status !== 'CLEARED');
  return (
    <Card title="Disburse and recover advances" testId="aa-staffAdvance" error={disburse.error ?? recover.error}>
      {waiting.length === 0 && owing.length === 0 ? <p className="aa-hint">Nothing waiting.</p> : null}
      <ul className="aa-list">
        {waiting.map((r) => (
          <li key={String(r.id)}>
            <span>{String(r.reference || `Advance ${r.id}`)} · <b>{naira(r.amount)}</b> <i className="aa-pill">to disburse</i></span>
            <button type="button" className="ef-btn ef-btn-primary" data-testid="aa-disburse" disabled={disburse.run.isPending} onClick={() => disburse.run.mutate({ id: Number(r.id) })}>Disburse</button>
          </li>
        ))}
        {owing.map((r) => (
          <li key={String(r.id)}>
            <span>{String(r.reference || `Advance ${r.id}`)} · owing <b>{naira(r.outstanding)}</b></span>
            <span className="aa-inline">
              <input aria-label={`Recovery amount for ${r.reference || r.id}`} inputMode="decimal" placeholder="Amount" value={amounts[Number(r.id)] ?? ''}
                onChange={(e) => setAmounts((a) => ({ ...a, [Number(r.id)]: e.target.value }))} />
              <button type="button" className="ef-btn" data-testid="aa-recover" disabled={recover.run.isPending || !Number(amounts[Number(r.id)])}
                onClick={() => recover.run.mutate({ id: Number(r.id), body: { amount: amounts[Number(r.id)], notes: 'Recovered from the register' } })}>Recover</button>
            </span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

/** Each travel request with the one step its status allows. */
function TravelRequestActions() {
  const requests = useRows('travelRequest', '/staff-advances/travel-requests/');
  const submit = useAction((id) => `/staff-advances/travel-requests/${id}/submit/`, 'Request submitted.');
  const approve = useAction((id) => `/staff-advances/travel-requests/${id}/approve/`, 'Request approved.');
  const reject = useAction((id) => `/staff-advances/travel-requests/${id}/reject/`, 'Request rejected.');
  const advance = useAction((id) => `/staff-advances/travel-requests/${id}/advance/`, 'Advance paid.');
  const [reasons, setReasons] = useState<Record<number, string>>({});
  const open = (requests.data ?? []).filter((r) => ['draft', 'submitted', 'approved'].includes(String(r.status)));
  const error = submit.error ?? approve.error ?? reject.error ?? advance.error;
  return (
    <Card title="Travel requests awaiting a step" testId="aa-travelRequest" error={error}>
      {open.length === 0 ? <p className="aa-hint">Nothing waiting.</p> : (
        <ul className="aa-list">
          {open.map((r) => {
            const id = Number(r.id);
            return (
              <li key={id}>
                <span>{String(r.destination)} · <b>{naira(r.estimated_cost)}</b> <i className="aa-pill">{String(r.status)}</i></span>
                <span className="aa-inline">
                  {r.status === 'draft' && <button type="button" className="ef-btn ef-btn-primary" data-testid="aa-submit" onClick={() => submit.run.mutate({ id })}>Submit</button>}
                  {r.status === 'submitted' && (
                    <>
                      <button type="button" className="ef-btn ef-btn-primary" data-testid="aa-approve" onClick={() => approve.run.mutate({ id })}>Approve</button>
                      <input aria-label={`Reason for rejecting the trip to ${r.destination}`} placeholder="Reason to reject" value={reasons[id] ?? ''} onChange={(e) => setReasons((a) => ({ ...a, [id]: e.target.value }))} />
                      <button type="button" className="ef-btn" data-testid="aa-reject" disabled={!(reasons[id] ?? '').trim()} onClick={() => reject.run.mutate({ id, body: { reason: reasons[id] } })}>Reject</button>
                    </>
                  )}
                  {r.status === 'approved' && <button type="button" className="ef-btn ef-btn-primary" data-testid="aa-advance" onClick={() => advance.run.mutate({ id })}>Pay advance</button>}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}

/** Retirements not yet posted, for either an imprest or a trip. */
function RetirementActions({ kind }: { kind: 'imprestRetirement' | 'travelRetirement' }) {
  const imprest = kind === 'imprestRetirement';
  const base = imprest ? '/staff-advances/imprest-retirements/' : '/staff-advances/travel-retirements/';
  const rows = useRows(kind, base);
  const post = useAction((id) => `${base}${id}/post/`, 'Retirement posted.');
  const waiting = (rows.data ?? []).filter((r) => (imprest ? !r.journal : !r.retired));
  return (
    <Card title="Retirements to post" testId={`aa-${kind}`} error={post.error}>
      {waiting.length === 0 ? <p className="aa-hint">Nothing waiting.</p> : (
        <ul className="aa-list">
          {waiting.map((r) => (
            <li key={String(r.id)}>
              <span>Retirement {String(r.id)} · <b>{naira(r.amount)}</b>{!imprest && Number(r.balance_returned) > 0 ? <> + {naira(r.balance_returned)} returned</> : null}</span>
              <button type="button" className="ef-btn ef-btn-primary" data-testid="aa-post-retirement" disabled={post.run.isPending} onClick={() => post.run.mutate({ id: Number(r.id) })}>Post</button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

/** The workflow actions of Advances & Travel, shown above the register they belong to. */
export default function AdvanceActions({ tab }: { tab: string }) {
  if (tab === 'staffAdvance') return <StaffAdvanceActions />;
  if (tab === 'travelRequest') return <TravelRequestActions />;
  if (tab === 'imprestRetirement' || tab === 'travelRetirement') return <RetirementActions kind={tab} />;
  return null;
}
