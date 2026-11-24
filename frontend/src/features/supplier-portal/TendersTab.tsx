import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { formatDate } from '../../utils/date';
import { portalError, supplierApi, type OpenTender } from './api';

function BidForm({ tender, onDone }: { tender: OpenTender; onDone: () => void }) {
  const qc = useQueryClient();
  const [form, setForm] = useState({ price: '', completion_days: '', validity_days: '90', technical_note: '' });
  const set = (name: keyof typeof form, value: string) => setForm((f) => ({ ...f, [name]: value }));
  const send = useMutation({
    mutationFn: () => supplierApi.placeBid(tender.id, {
      price: form.price, completion_days: Number(form.completion_days), validity_days: Number(form.validity_days), technical_note: form.technical_note,
    }),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['supplier'] }); onDone(); },
  });
  const valid = Number(form.price) > 0 && Number(form.completion_days) > 0 && Number(form.validity_days) > 0;
  const id = (n: string) => `sp-bid-${tender.id}-${n}`;

  return (
    <div className="sp-bidform" data-testid="sp-bid-form">
      <p className="sp-sub">Your bid is sealed when you send it: nobody, including the procurement office, can read it until the bids are opened after {tender.closing_date ? formatDate(tender.closing_date) : 'the closing date'}. You can change or withdraw it until then.</p>
      {send.isError && <div className="sp-alert bad" role="alert" data-testid="sp-bid-error">{portalError(send.error)}</div>}
      <div className="sp-grid">
        <div className="sp-field"><label htmlFor={id('price')}>Your price (₦)</label>
          <input id={id('price')} inputMode="decimal" value={form.price} onChange={(e) => set('price', e.target.value.replace(/[^\d.]/g, ''))} /></div>
        <div className="sp-field"><label htmlFor={id('days')}>Completion time (days)</label>
          <input id={id('days')} inputMode="numeric" value={form.completion_days} onChange={(e) => set('completion_days', e.target.value.replace(/\D/g, ''))} /></div>
        <div className="sp-field"><label htmlFor={id('valid')}>Your offer stays valid for (days)</label>
          <input id={id('valid')} inputMode="numeric" value={form.validity_days} onChange={(e) => set('validity_days', e.target.value.replace(/\D/g, ''))} /></div>
      </div>
      <div className="sp-field"><label htmlFor={id('note')}>Technical approach (optional)</label>
        <textarea id={id('note')} rows={3} maxLength={4000} value={form.technical_note} onChange={(e) => set('technical_note', e.target.value)} /></div>
      <div className="sp-actions">
        <button type="button" className="sp-btn primary" data-testid="sp-bid-send" disabled={!valid || send.isPending} onClick={() => send.mutate()}>
          {send.isPending ? 'Sealing…' : tender.my_bid ? 'Replace my bid' : 'Seal and send my bid'}
        </button>
        <button type="button" className="sp-btn" onClick={onDone}>Cancel</button>
      </div>
    </div>
  );
}

/**
 * Tenders open for bids, and the supplier's own bids. Registration as a bidder comes first; a bid is sealed on sending and
 * gives a receipt. Only the supplier's own bids are ever shown, and never what any bid says.
 */
export default function TendersTab() {
  const qc = useQueryClient();
  const tenders = useQuery({ queryKey: ['supplier', 'tenders'], queryFn: supplierApi.tenders });
  const [bidding, setBidding] = useState<number | null>(null);
  const [categories, setCategories] = useState('');
  const register = useMutation({
    mutationFn: () => supplierApi.requestRegistration(categories.split(',')),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['supplier', 'tenders'] }); },
  });
  const withdraw = useMutation({
    mutationFn: (bidId: number) => supplierApi.withdrawBid(bidId),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['supplier'] }); },
  });

  if (tenders.isLoading) return <p className="sp-sub" aria-busy="true">Loading tenders…</p>;
  if (tenders.isError || !tenders.data) return <div className="sp-alert bad" role="alert">{portalError(tenders.error)}</div>;
  const d = tenders.data;

  return (
    <>
      <section className="sp-card" aria-labelledby="sp-bidder">
        <h2 id="sp-bidder">Your bidder registration</h2>
        {d.eligible ? (
          <div className="sp-alert ok" role="status" data-testid="sp-eligible">You are registered and may bid on the tenders below.</div>
        ) : d.registration_status === 'none' ? (
          <>
            <p className="sp-sub">{d.reason} Tell the procurement office what you supply; they will check your documents and decide.</p>
            {register.isError && <div className="sp-alert bad" role="alert">{portalError(register.error)}</div>}
            <div className="sp-field" style={{ maxWidth: 480 }}><label htmlFor="sp-cats">What you supply (separate with commas)</label>
              <input id="sp-cats" value={categories} onChange={(e) => setCategories(e.target.value)} placeholder="For example: civil works, office supplies" /></div>
            <button type="button" className="sp-btn primary" data-testid="sp-register-bidder" disabled={!categories.trim() || register.isPending} onClick={() => register.mutate()}>
              {register.isPending ? 'Sending…' : 'Ask to be registered as a bidder'}
            </button>
          </>
        ) : (
          <div className="sp-alert warn" role="status" data-testid="sp-not-eligible">{d.reason}</div>
        )}
      </section>

      <section className="sp-card" aria-labelledby="sp-open-tenders">
        <h2 id="sp-open-tenders">Tenders open for bids</h2>
        {d.tenders.length === 0 ? (
          <div className="sp-empty" data-testid="sp-empty"><h3>No tenders are open</h3><p>Tenders published by the government appear here until they close.</p></div>
        ) : d.tenders.map((t) => (
          <article key={t.id} className="sp-tender" data-testid={`sp-tender-${t.reference}`}>
            <div className="sp-bar" style={{ alignItems: 'center' }}>
              <div>
                <h3 style={{ margin: 0, fontSize: 15 }}>{t.reference} · {t.title}</h3>
                <p className="sp-hint" style={{ margin: '2px 0 0' }}>{t.method}{t.category ? ` · ${t.category}` : ''} · closes {t.closing_date ? formatDate(t.closing_date) : 'date not set'}</p>
              </div>
              {t.my_bid ? <span className={`sp-pill ${t.my_bid.status === 'withdrawn' ? '' : 'ok'}`} data-testid="sp-my-bid-status">{t.my_bid.status === 'submitted' ? 'Your bid is sealed' : t.my_bid.status}</span> : null}
            </div>
            {t.description && <p className="sp-sub" style={{ marginTop: 10 }}>{t.description}</p>}
            {t.my_bid && t.my_bid.status !== 'withdrawn' && <p className="sp-hint" data-testid="sp-receipt">Receipt {t.my_bid.receipt.slice(0, 16)}… · sent {formatDate(t.my_bid.submitted_at)}</p>}
            {bidding === t.id ? <BidForm tender={t} onDone={() => setBidding(null)} /> : (
              <div className="sp-actions">
                <button type="button" className="sp-btn primary" data-testid={`sp-bid-open-${t.reference}`} disabled={!d.eligible} onClick={() => setBidding(t.id)}>
                  {t.my_bid && t.my_bid.status === 'submitted' ? 'Change my bid' : 'Bid on this tender'}
                </button>
                {t.my_bid?.status === 'submitted' && (
                  <button type="button" className="sp-btn" data-testid={`sp-bid-withdraw-${t.reference}`} disabled={withdraw.isPending} onClick={() => withdraw.mutate(t.my_bid!.id)}>Withdraw my bid</button>
                )}
              </div>
            )}
          </article>
        ))}
      </section>
    </>
  );
}
