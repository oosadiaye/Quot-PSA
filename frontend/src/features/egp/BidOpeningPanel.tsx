import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { message } from 'antd';
import apiClient from '../../api/client';
import '../_base/crud.css';
import './bid-opening.css';

interface Tender { id: number; reference: string; title: string; status: string; closing_date: string | null }
interface BidRow {
  id: number; bidder: string; status: string; submitted_at: string; receipt: string; sealed: boolean;
  contents: { price: string; completion_days: number; validity_days: number; technical_note: string } | null;
}
interface Bids { opened: boolean; bids: BidRow[] }

const today = () => new Date().toISOString().slice(0, 10);
const naira = (v: string) => `₦${Number(v).toLocaleString('en-NG', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const when = (iso: string) => new Date(iso).toLocaleString('en-GB', { dateStyle: 'short', timeStyle: 'short' });
const apiError = (e: unknown) => (e as { response?: { data?: { error?: string; detail?: string } } })?.response?.data?.error
  ?? (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Something went wrong. Try again.';

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
      ) : (
        <div className="bo-scroll"><table className="bo-table" aria-label={`Bids on ${tender.reference}`}>
          <thead><tr><th scope="col">Bidder</th><th scope="col">Received</th><th scope="col">Status</th><th scope="col" className="num">Price</th><th scope="col" className="num">Days</th><th scope="col">Receipt</th></tr></thead>
          <tbody>{data!.bids.map((b) => (
            <tr key={b.id} data-testid="bo-bid">
              <td><b>{b.bidder}</b></td><td>{when(b.submitted_at)}</td>
              <td><span className={`bo-pill ${b.sealed ? 'sealed' : 'open'}`}>{b.sealed ? 'Sealed' : b.status.replace('_', ' ')}</span></td>
              <td className="num">{b.contents ? naira(b.contents.price) : '–'}</td>
              <td className="num">{b.contents ? b.contents.completion_days : '–'}</td>
              <td><code title={b.receipt}>{b.receipt.slice(0, 10)}</code></td>
            </tr>
          ))}</tbody>
        </table></div>
      )}

      {data && !data.opened && (
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
      {data?.opened && <p className="bo-hint" data-testid="bo-opened">The bids were opened.</p>}
    </div>
  );
}

/**
 * Who has bid on each tender, and the recorded opening that releases the bids. The office sees who bid and when from the
 * start, but not what a bid says: that is sealed until an approver opens the tender's bids after its closing date.
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
      <h3 id="bo-title">Bids and opening</h3>
      <p className="bo-hint">Tenders that are open to bids or have closed.</p>
      <ul className="bo-list">
        {tenders.data!.map((t) => (
          <li key={t.id} data-testid={`bo-tender-${t.reference}`}>
            <div className="bo-row">
              <div><b>{t.reference}</b> · {t.title}<br /><span className="bo-hint">{t.status === 'published' ? 'Open to bids' : 'Closed'}{t.closing_date ? `, closes ${t.closing_date}` : ''}</span></div>
              <button type="button" className="ef-btn" data-testid={`bo-toggle-${t.reference}`} aria-expanded={expanded === t.id}
                onClick={() => setExpanded(expanded === t.id ? null : t.id)}>{expanded === t.id ? 'Hide bids' : 'Bids'}</button>
            </div>
            {expanded === t.id && <TenderBids tender={t} />}
          </li>
        ))}
      </ul>
    </section>
  );
}
