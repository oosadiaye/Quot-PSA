import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { formatDate } from '../../utils/date';
import { portalError, supplierApi, type ItemChoice, type PriceProposal } from './api';
import { naira } from './SupplierTabs';

const tone = (s: PriceProposal['status']) => (s === 'approved' ? 'ok' : s === 'rejected' ? 'bad' : 'warn');
const word = (s: PriceProposal['status']) => (s === 'approved' ? 'Approved' : s === 'rejected' ? 'Rejected' : 'Waiting for approval');

function Grid({ label, head, children }: { label: string; head: { text: string; num?: boolean }[]; children: React.ReactNode }) {
  return (
    <div className="sp-table-wrap">
      <table className="sp-table" aria-label={label}>
        <thead><tr>{head.map((h) => <th key={h.text} scope="col" className={h.num ? 'num' : undefined}>{h.text}</th>)}</tr></thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

/**
 * The supplier's catalogue: the prices the government has accepted from it, and a form to propose a new one. A proposal
 * changes nothing until the procurement office accepts it.
 */
export default function CatalogueTab() {
  const qc = useQueryClient();
  const prices = useQuery({ queryKey: ['supplier', 'catalogue'], queryFn: supplierApi.catalogue });
  const proposals = useQuery({ queryKey: ['supplier', 'proposals'], queryFn: supplierApi.proposals });
  const [search, setSearch] = useState('');
  const [chosen, setChosen] = useState<ItemChoice | null>(null);
  const [price, setPrice] = useState('');
  const [spec, setSpec] = useState('');
  const found = useQuery({
    queryKey: ['supplier', 'item-search', search],
    queryFn: () => supplierApi.searchItems(search),
    enabled: search.trim().length >= 2 && !chosen,
  });
  const send = useMutation({
    mutationFn: () => supplierApi.propose({ item: chosen!.id, proposed_price: price, specification: spec }),
    onSuccess: () => {
      setChosen(null); setSearch(''); setPrice(''); setSpec('');
      void qc.invalidateQueries({ queryKey: ['supplier'] });
    },
  });
  const valid = !!chosen && Number(price) > 0;

  return (
    <>
      <section className="sp-card" aria-labelledby="sp-cat-now">
        <h2 id="sp-cat-now">Your prices in force</h2>
        <p className="sp-sub">The prices the government has accepted from you. Orders can be priced from these.</p>
        {prices.isLoading ? <p className="sp-sub" aria-busy="true">Loading…</p> : (prices.data ?? []).length === 0 ? (
          <div className="sp-empty" data-testid="sp-empty"><h3>No prices yet</h3><p>Propose a price below. Once the procurement office accepts it, it appears here.</p></div>
        ) : (
          <Grid label="Your catalogue prices" head={[{ text: 'Item' }, { text: 'Price', num: true }, { text: 'Since' }, { text: 'Specification' }]}>
            {prices.data!.map((p) => (
              <tr key={p.id} data-testid="sp-price-row">
                <td><b>{p.item_name}</b><br /><span className="sp-hint">{p.item_code}</span></td>
                <td className="num">{naira(p.unit_price)}</td><td>{formatDate(p.effective_date)}</td><td>{p.specification || '–'}</td>
              </tr>
            ))}
          </Grid>
        )}
      </section>

      <section className="sp-card" aria-labelledby="sp-cat-new">
        <h2 id="sp-cat-new">Propose a price</h2>
        <p className="sp-sub">A price takes effect only after the procurement office accepts it. You can have one proposal waiting for each item.</p>
        {send.isError && <div className="sp-alert bad" role="alert" data-testid="sp-cat-error">{portalError(send.error)}</div>}
        <div className="sp-field">
          <label htmlFor="sp-cat-item">Item</label>
          {chosen ? (
            <div>
              <b data-testid="sp-cat-chosen">{chosen.name}</b> <span className="sp-hint">({chosen.code}, per {chosen.unit})</span>{' '}
              <button type="button" className="sp-link" onClick={() => { setChosen(null); setSearch(''); }}>Change</button>
            </div>
          ) : (
            <>
              <input id="sp-cat-item" type="search" value={search} placeholder="Type at least two letters of the item name"
                onChange={(e) => setSearch(e.target.value)} />
              {search.trim().length >= 2 && !found.isLoading && (found.data ?? []).length === 0 && (
                <p className="sp-hint">No item matches “{search.trim()}”.</p>
              )}
              {(found.data ?? []).length > 0 && (
                <ul className="sp-choices" aria-label="Matching items">
                  {found.data!.map((i) => (
                    <li key={i.id}>
                      <button type="button" className="sp-link" data-testid={`sp-cat-pick-${i.code}`} onClick={() => setChosen(i)}>{i.name}</button>{' '}
                      <span className="sp-hint">{i.code}</span>
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}
        </div>
        <div className="sp-grid">
          <div className="sp-field">
            <label htmlFor="sp-cat-price">Price per unit (₦)</label>
            <input id="sp-cat-price" inputMode="decimal" value={price} onChange={(e) => setPrice(e.target.value.replace(/[^\d.]/g, ''))} />
          </div>
          <div className="sp-field">
            <label htmlFor="sp-cat-spec">Specification (optional)</label>
            <input id="sp-cat-spec" value={spec} onChange={(e) => setSpec(e.target.value)} />
          </div>
        </div>
        <button type="button" className="sp-btn primary" data-testid="sp-cat-send" disabled={!valid || send.isPending} onClick={() => send.mutate()}>
          {send.isPending ? 'Sending…' : 'Propose this price'}
        </button>
      </section>

      {(proposals.data?.length ?? 0) > 0 && (
        <section className="sp-card" aria-labelledby="sp-cat-hist">
          <h2 id="sp-cat-hist">Your proposals</h2>
          <Grid label="Price proposals" head={[{ text: 'Item' }, { text: 'Proposed', num: true }, { text: 'Replaces', num: true }, { text: 'Status' }, { text: 'Note' }]}>
            {proposals.data!.map((p) => (
              <tr key={p.id} data-testid="sp-proposal-row">
                <td>{p.item_name}</td><td className="num">{naira(p.proposed_price)}</td><td className="num">{naira(p.current_price)}</td>
                <td><span className={`sp-pill ${tone(p.status)}`}>{word(p.status)}</span></td><td>{p.reason || '–'}</td>
              </tr>
            ))}
          </Grid>
        </section>
      )}
    </>
  );
}
