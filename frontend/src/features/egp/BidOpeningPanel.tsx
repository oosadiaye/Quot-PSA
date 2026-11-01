import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { message } from 'antd';
import apiClient from '../../api/client';
import { ReferenceField } from '../_base/ReferenceField';
import type { EntityField } from '../_base/types';
import '../_base/crud.css';
import './bid-opening.css';

interface Tender { id: number; reference: string; title: string; status: string; closing_date: string | null }
interface BidRow {
  id: number; bidder: string; status: string; submitted_at: string; receipt: string; sealed: boolean; note: string;
  contents: { price: string; completion_days: number; validity_days: number; technical_note: string } | null;
}
interface Bids { opened: boolean; bids: BidRow[] }
interface Ranked { bid: number; bidder: string; status: string; note: string; price: string; completion_days: number; score: string | null }
interface AwardRow { id: number; award_amount: string; purchase_order: number | null }

const today = () => new Date().toISOString().slice(0, 10);
const naira = (v: string) => `₦${Number(v).toLocaleString('en-NG', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const when = (iso: string) => new Date(iso).toLocaleString('en-GB', { dateStyle: 'short', timeStyle: 'short' });
const apiError = (e: unknown) => (e as { response?: { data?: { error?: string; detail?: string } } })?.response?.data?.error
  ?? (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Something went wrong. Try again.';
const STATUS_WORD: Record<string, string> = { opened: 'Opened', responsive: 'Responsive', non_responsive: 'Not responsive', disqualified: 'Disqualified' };

/** The things an order is charged to. Each is looked up by searching, because a government has hundreds of MDAs and locations. */
const CHARGE_FIELDS: { key: 'mda' | 'fund' | 'function' | 'program' | 'geo' | 'account'; label: string; entity: string }[] = [
  { key: 'mda', label: 'MDA', entity: 'mda' },
  { key: 'fund', label: 'Fund', entity: 'fund' },
  { key: 'function', label: 'Function', entity: 'function' },
  { key: 'program', label: 'Programme', entity: 'program' },
  { key: 'geo', label: 'Location', entity: 'geo' },
  { key: 'account', label: 'Expense account', entity: 'account' },
];
const asField = (c: (typeof CHARGE_FIELDS)[number]): EntityField => ({ name: c.key, label: c.label, type: 'integer', reference: { module: 'accounting', entity: c.entity } });

/** Rule on each opened bid, see them ranked, and award the tender to a responsive one: that raises a draft purchase order. */
function Evaluation({ tender }: { tender: Tender }) {
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [ruling, setRuling] = useState<{ bid: number; status: string } | null>(null);
  const [note, setNote] = useState('');
  const [pick, setPick] = useState('');
  const [dims, setDims] = useState<Record<string, number | ''>>({ mda: '', fund: '', function: '', program: '', geo: '', account: '' });
  const ranking = useQuery({ queryKey: ['egp', 'ranking', tender.id], queryFn: async (): Promise<Ranked[]> => (await apiClient.get(`/egp/tenders/${tender.id}/ranking/`)).data });
  const awards = useQuery({
    queryKey: ['egp', 'award', tender.id],
    queryFn: async (): Promise<AwardRow[]> => { const { data } = await apiClient.get('/egp/awards/', { params: { tender: tender.id } }); return data.results ?? data ?? []; },
  });
  const refresh = () => { void qc.invalidateQueries({ queryKey: ['egp'] }); };
  const assess = useMutation({
    mutationFn: async (v: { bid: number; status: string; note: string }) => (await apiClient.post(`/egp/bids/${v.bid}/assess/`, { status: v.status, note: v.note })).data,
    onSuccess: () => { setError(null); setRuling(null); setNote(''); refresh(); },
    onError: (e) => setError(apiError(e)),
  });
  const award = useMutation({
    mutationFn: async () => (await apiClient.post(`/egp/tenders/${tender.id}/award/`, { bid: Number(pick), ...dims })).data,
    onSuccess: (r: { po_number: string }) => { setError(null); message.success(`Awarded. Draft order ${r.po_number} raised.`); refresh(); },
    onError: (e) => setError(apiError(e)),
  });

  const rows = ranking.data ?? [];
  const awarded = (awards.data ?? [])[0];
  const responsive = rows.filter((r) => r.status === 'responsive');
  const ready = !!pick && Object.values(dims).every((v) => v !== '');

  return (
    <div className="bo-eval" data-testid="bo-eval">
      {error && <div className="bo-error" role="alert" data-testid="bo-eval-error">{error}</div>}
      {rows.length === 0 ? <p className="bo-hint">No bids were opened.</p> : (
        <div className="bo-scroll"><table className="bo-table" aria-label={`Ranking of bids on ${tender.reference}`}>
          <thead><tr><th scope="col">Bidder</th><th scope="col">Ruling</th><th scope="col" className="num">Price</th><th scope="col" className="num">Days</th><th scope="col" className="num">Score</th><th scope="col"><span className="sr-only">Rule</span></th></tr></thead>
          <tbody>{rows.map((r) => (
            <tr key={r.bid} data-testid="bo-ranked">
              <td><b>{r.bidder}</b>{r.note && <><br /><span className="bo-hint">{r.note}</span></>}</td>
              <td><span className={`bo-pill ${r.status === 'responsive' ? 'open' : r.status === 'opened' ? 'sealed' : 'out'}`}>{STATUS_WORD[r.status] ?? r.status}</span></td>
              <td className="num">{naira(r.price)}</td><td className="num">{r.completion_days}</td><td className="num">{r.score ?? '–'}</td>
              <td>
                {awarded ? null : ruling?.bid === r.bid ? (
                  <div className="bo-field" style={{ minWidth: 200 }}>
                    <label htmlFor={`bo-note-${r.bid}`}>Reason</label>
                    <input id={`bo-note-${r.bid}`} data-testid="bo-note" value={note} onChange={(e) => setNote(e.target.value)} />
                    <div className="bo-actions">
                      <button type="button" className="ef-btn ef-btn-primary" data-testid="bo-rule-confirm" disabled={!note.trim() || assess.isPending}
                        onClick={() => assess.mutate({ bid: r.bid, status: ruling.status, note })}>Confirm</button>
                      <button type="button" className="ef-btn" onClick={() => { setRuling(null); setNote(''); }}>Cancel</button>
                    </div>
                  </div>
                ) : (
                  <div className="bo-actions">
                    {r.status !== 'responsive' && <button type="button" className="ef-btn" data-testid={`bo-responsive-${r.bid}`} disabled={assess.isPending} onClick={() => assess.mutate({ bid: r.bid, status: 'responsive', note: '' })}>Responsive</button>}
                    {r.status !== 'non_responsive' && <button type="button" className="ef-btn" data-testid={`bo-nonresp-${r.bid}`} onClick={() => setRuling({ bid: r.bid, status: 'non_responsive' })}>Not responsive</button>}
                    {r.status !== 'disqualified' && <button type="button" className="ef-btn" data-testid={`bo-disq-${r.bid}`} onClick={() => setRuling({ bid: r.bid, status: 'disqualified' })}>Disqualify</button>}
                  </div>
                )}
              </td>
            </tr>
          ))}</tbody>
        </table></div>
      )}

      {awarded ? (
        <div className="bo-done" data-testid="bo-awarded">Awarded for {naira(awarded.award_amount)}. A draft purchase order was raised; it goes through the usual order approval before any money is committed.</div>
      ) : responsive.length > 0 && (
        <div className="bo-open">
          <h4>Award the tender</h4>
          <p className="bo-hint">Awarding raises a draft purchase order for the supplier at its bid price. Say what the order is charged to.</p>
          <div className="bo-field"><label htmlFor="bo-pick">Winning bid</label>
            <select id="bo-pick" data-testid="bo-pick" value={pick} onChange={(e) => setPick(e.target.value)}>
              <option value="">Choose…</option>
              {responsive.map((r) => <option key={r.bid} value={r.bid}>{r.bidder} · {naira(r.price)}</option>)}
            </select></div>
          <div className="bo-grid">
            {CHARGE_FIELDS.map((c) => (
              <div className="bo-field" key={c.key} data-testid={`bo-${c.key}`}>
                <label htmlFor={`bo-${c.key}-input`}>{c.label}</label>
                <ReferenceField field={asField(c)} id={`bo-${c.key}-input`} value={dims[c.key]} onChange={(v) => setDims((d) => ({ ...d, [c.key]: v }))} />
              </div>
            ))}
          </div>
          <button type="button" className="ef-btn ef-btn-primary" data-testid="bo-award" disabled={!ready || award.isPending} onClick={() => award.mutate()}>
            {award.isPending ? 'Awarding…' : 'Award and raise the draft order'}
          </button>
        </div>
      )}
    </div>
  );
}

function TenderBids({ tender }: { tender: Tender }) {
  const qc = useQueryClient();
  const [attendance, setAttendance] = useState('');
  const [minutes, setMinutes] = useState('');
  const [error, setError] = useState<string | null>(null);
  const bids = useQuery({ queryKey: ['egp', 'bids', tender.id], queryFn: async (): Promise<Bids> => (await apiClient.get(`/egp/tenders/${tender.id}/bids/`)).data });
  const open = useMutation({
    mutationFn: async () => (await apiClient.post(`/egp/tenders/${tender.id}/open-bids/`, { attendance: attendance.split('\n'), minutes })).data,
    onSuccess: () => { setError(null); message.success('The bids are opened'); void qc.invalidateQueries({ queryKey: ['egp'] }); void qc.invalidateQueries({ queryKey: ['egp-tenders'] }); },
    onError: (e) => setError(apiError(e)),
  });
  const closed = !!tender.closing_date && tender.closing_date < today();
  const data = bids.data;

  return (
    <div className="bo-detail" data-testid={`bo-detail-${tender.reference}`}>
      {bids.isLoading ? <p className="bo-hint" aria-busy="true">Loading the bids…</p> : (data?.bids.length ?? 0) === 0 ? (
        <p className="bo-hint">No bids were received.</p>
      ) : !data!.opened ? (
        <div className="bo-scroll"><table className="bo-table" aria-label={`Bids on ${tender.reference}`}>
          <thead><tr><th scope="col">Bidder</th><th scope="col">Received</th><th scope="col">Status</th><th scope="col">Receipt</th></tr></thead>
          <tbody>{data!.bids.map((b) => (
            <tr key={b.id} data-testid="bo-bid">
              <td><b>{b.bidder}</b></td><td>{when(b.submitted_at)}</td>
              <td><span className="bo-pill sealed">{b.status === 'withdrawn' ? 'Withdrawn' : 'Sealed'}</span></td>
              <td><code title={b.receipt}>{b.receipt.slice(0, 10)}</code></td>
            </tr>
          ))}</tbody>
        </table></div>
      ) : null}

      {data && !data.opened && (data.bids.length > 0 || closed) && (
        closed ? (
          <div className="bo-open">
            <h4>Open the bids</h4>
            <p className="bo-hint">Bids are opened in front of witnesses. Once opened, every bid can be read and none can be changed.</p>
            {error && <div className="bo-error" role="alert" data-testid="bo-error">{error}</div>}
            <div className="bo-field"><label htmlFor={`bo-att-${tender.id}`}>Who is present (one name per line)</label>
              <textarea id={`bo-att-${tender.id}`} data-testid="bo-attendance" rows={3} value={attendance} onChange={(e) => setAttendance(e.target.value)} /></div>
            <div className="bo-field"><label htmlFor={`bo-min-${tender.id}`}>Minutes (optional)</label>
              <textarea id={`bo-min-${tender.id}`} rows={2} value={minutes} onChange={(e) => setMinutes(e.target.value)} /></div>
            <button type="button" className="ef-btn ef-btn-primary" data-testid="bo-open" disabled={!attendance.trim() || open.isPending} onClick={() => open.mutate()}>
              {open.isPending ? 'Opening…' : 'Open the bids'}
            </button>
          </div>
        ) : <p className="bo-hint" data-testid="bo-wait">Bids can be opened after the closing date, {tender.closing_date ?? 'which has not been set'}.</p>
      )}
      {data?.opened && <><p className="bo-hint" data-testid="bo-opened">The bids were opened.</p><Evaluation tender={tender} /></>}
    </div>
  );
}

/**
 * Who has bid on each tender, the recorded opening that releases the bids, and then the evaluation: ruling on each bid,
 * ranking them, and awarding the tender. The office sees who bid and when from the start, but not what a bid says until an
 * approver opens the tender's bids after its closing date.
 */
export default function BidOpeningPanel() {
  const [expanded, setExpanded] = useState<number | null>(null);
  const tenders = useQuery({
    queryKey: ['egp-tenders'],
    queryFn: async (): Promise<Tender[]> => {
      const { data } = await apiClient.get('/egp/tenders/', { params: { page_size: 50 } });
      return ((data.results ?? data) as Tender[]).filter((t) => t.status === 'published' || t.status === 'closed');
    },
  });
  if (tenders.isLoading || (tenders.data ?? []).length === 0) return null;

  return (
    <section className="bo" aria-labelledby="bo-title" data-testid="bo-panel">
      <h3 id="bo-title">Bids, opening and award</h3>
      <p className="bo-hint">Tenders that are open to bids or have closed.</p>
      <ul className="bo-list">
        {tenders.data!.map((t) => (
          <li key={t.id} data-testid={`bo-tender-${t.reference}`}>
            <div className="bo-row">
              <div><b>{t.reference}</b> · {t.title}<br /><span className="bo-hint">{t.status === 'published' ? 'Open to bids' : 'Closed'}{t.closing_date ? `, closes ${t.closing_date}` : ''}</span></div>
              <button type="button" className="ef-btn" data-testid={`bo-toggle-${t.reference}`} aria-expanded={expanded === t.id}
                onClick={() => setExpanded(expanded === t.id ? null : t.id)}>{expanded === t.id ? 'Hide' : 'Bids'}</button>
            </div>
            {expanded === t.id && <TenderBids tender={t} />}
          </li>
        ))}
      </ul>
    </section>
  );
}
