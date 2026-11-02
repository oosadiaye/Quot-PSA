import { useMemo, useState } from 'react';
import { Modal, message } from 'antd';
import AmountInput from '../../components/AmountInput';
import SearchableSelect from '../../components/SearchableSelect';
import { useCurrency } from '../../context/CurrencyContext';
import { useDimensions } from '../accounting/hooks/useJournal';
import {
  debtError, useBankAccounts, useClassifications, useCoupons, useDrawdown, useDrawdowns, useInstruments, usePayCoupon,
  usePosition, useReclassify, useSaveMapping, useStandardAccounts, type DebtInstrumentRow,
} from './useDebtGl';

type Coded = { id: number | string; code?: string; name?: string; account_type?: string };

const todayISO = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
};
const ddmmyyyy = (iso?: string) => (iso ? iso.slice(0, 10).split('-').reverse().join('/') : '');

const card: React.CSSProperties = { background: '#fff', border: '1px solid #e2e8f0', borderRadius: 14, padding: '16px 18px', minWidth: 0 };
const label: React.CSSProperties = { fontSize: 12, fontWeight: 600, color: '#475569', display: 'block', marginBottom: 4 };
const input: React.CSSProperties = { width: '100%', padding: '9px 11px', borderRadius: 8, border: '1px solid #cbd5e1', fontSize: 14, boxSizing: 'border-box' };
const btn: React.CSSProperties = { padding: '8px 14px', borderRadius: 8, border: '1px solid #cbd5e1', background: '#fff', color: '#242a88', fontWeight: 600, fontSize: 13, cursor: 'pointer' };
const primary: React.CSSProperties = { ...btn, background: 'linear-gradient(135deg, #242a88, #2e35a0)', color: '#fff', border: 'none' };

function Stat({ title, value, note, testId }: { title: string; value: string; note?: string; testId: string }) {
  return (
    <div style={card} data-testid={testId}>
      <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '.06em', textTransform: 'uppercase', color: '#64748b' }}>{title}</div>
      <div style={{ fontSize: 22, fontWeight: 700, color: '#0f172a', fontVariantNumeric: 'tabular-nums', margin: '4px 0' }}>{value}</div>
      {note && <div style={{ fontSize: 12, color: '#64748b' }}>{note}</div>}
    </div>
  );
}

/**
 * Debt on the books: pick an instrument, see how much is owed split between non-current and current liabilities,
 * map it to the chart of accounts and a bank account, record drawdowns, reclassify the current portion and pay coupons.
 */
export default function DebtPosition() {
  const { formatCurrency } = useCurrency();
  const money = (v: string | number | undefined) => formatCurrency(Number(v ?? 0));
  const { data: instruments = [] } = useInstruments();
  const [picked, setPicked] = useState<number | null>(null);
  const instrument: DebtInstrumentRow | undefined = useMemo(
    () => instruments.find((i) => i.id === picked) ?? instruments[0], [instruments, picked]);
  const id = instrument?.id ?? null;
  const { data: pos } = usePosition(id);
  const { data: coupons = [] } = useCoupons(id);
  const { data: drawdowns = [] } = useDrawdowns(id);
  const { data: classifications = [] } = useClassifications(id);
  const { data: banks = [] } = useBankAccounts();
  const { data: dims } = useDimensions();

  const standard = useStandardAccounts();
  const saveMapping = useSaveMapping();
  const drawdown = useDrawdown();
  const reclassify = useReclassify();
  const payCoupon = usePayCoupon();

  const [dialog, setDialog] = useState<null | 'mapping' | 'drawdown' | 'reclassify' | { pay: number }>(null);
  const [error, setError] = useState('');
  const [form, setForm] = useState<Record<string, string>>({});
  const set = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }));

  const accounts = (dims?.accounts ?? []) as Coded[];
  const options = (kind: string) =>
    accounts.filter((a) => (a.account_type ?? kind) === kind)
      .map((a) => ({ value: String(a.id), label: `${a.code} - ${a.name ?? ''}` }));
  const bankOptions = banks.map((b) => ({ value: String(b.id), label: b.account_name || b.name || `Bank ${b.id}` }));

  const open = (d: typeof dialog, init: Record<string, string> = {}) => { setError(''); setForm(init); setDialog(d); };
  const run = async (work: () => Promise<unknown>, done: string) => {
    try { await work(); message.success(done); setDialog(null); } catch (e) { setError(debtError(e)); }
  };

  const mapped = !!instrument?.liability_account;
  const unpaid = coupons.filter((c) => c.status !== 'paid' && c.status !== 'closed');

  if (!instrument) {
    return (
      <div style={{ ...card, marginBottom: 16 }} data-testid="debt-gl-empty">
        Add a debt instrument in the register below to put it on the general ledger.
      </div>
    );
  }

  return (
    <section aria-label="Debt on the general ledger" style={{ marginBottom: 24, display: 'grid', gap: 14 }} data-testid="debt-gl">
      <div style={{ ...card, display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'end', justifyContent: 'space-between' }}>
        <div style={{ minWidth: 280, flex: 1 }}>
          <label style={label}>Instrument</label>
          <select style={input} value={instrument.id} data-testid="debt-gl-instrument" onChange={(e) => setPicked(Number(e.target.value))}>
            {instruments.map((i) => <option key={i.id} value={i.id}>{i.instrument_number} - {i.creditor} ({i.status})</option>)}
          </select>
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button type="button" style={btn} data-testid="debt-gl-standard"
            onClick={() => run(() => standard.mutateAsync(instrument.id), 'Standard accounts applied.')}>Use standard accounts</button>
          <button type="button" style={btn} data-testid="debt-gl-mapping" onClick={() => open('mapping', {
            liability: String(instrument.liability_account ?? ''), current: String(instrument.current_portion_account ?? ''),
            interest: String(instrument.interest_expense_account ?? ''), fee: String(instrument.fee_expense_account ?? ''),
            bank: String(instrument.bank_account ?? ''),
          })}>Edit GL mapping</button>
          <button type="button" style={primary} data-testid="debt-gl-drawdown" disabled={!mapped}
            title={mapped ? '' : 'Set the GL mapping first'}
            onClick={() => open('drawdown', { amount: '', date: todayISO(), bank: String(instrument.bank_account ?? ''), reference: '' })}>Record drawdown</button>
          <button type="button" style={primary} data-testid="debt-gl-reclassify" disabled={!mapped}
            title={mapped ? '' : 'Set the GL mapping first'}
            onClick={() => open('reclassify', { as_of: todayISO() })}>Reclassify current portion</button>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: 12 }}>
        <Stat testId="debt-stat-facility" title="Facility" value={money(pos?.facility ?? instrument.principal_amount)} note="Agreed amount" />
        <Stat testId="debt-stat-drawn" title="Drawn" value={money(pos?.drawn ?? instrument.drawn_amount)} note="Received so far" />
        <Stat testId="debt-stat-outstanding" title="Outstanding" value={money(pos?.outstanding_principal ?? instrument.outstanding_principal)} note="Drawn less principal repaid" />
        <Stat testId="debt-stat-noncurrent" title="Non-current liability" value={money(pos?.non_current_portion)} note="Due after twelve months" />
        <Stat testId="debt-stat-current" title="Current portion" value={money(pos?.current_portion)}
          note={pos && Number(pos.reclassification_needed) !== 0 ? `${money(pos.reclassification_needed)} still to reclassify` : 'Up to date'} />
        <Stat testId="debt-stat-due" title="Due in 12 months" value={money(pos?.due_within_12_months)} note={`From ${ddmmyyyy(pos?.as_of)}`} />
      </div>

      <div style={{ ...card, fontSize: 13 }} data-testid="debt-gl-accounts">
        <strong>Posts to</strong>{' '}
        {mapped ? (
          <>
            non-current liability <b>{instrument.liability_account_name}</b>, current portion <b>{instrument.current_portion_account_name}</b>,
            interest <b>{instrument.interest_expense_account_name || 'not set'}</b>, paid from <b>{instrument.bank_account_name || 'a bank account chosen at payment'}</b>.
          </>
        ) : (
          <span>Nothing yet. Choose "Use standard accounts" to map this instrument to the chart of accounts.</span>
        )}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 14 }}>
        <div style={card}>
          <h3 style={{ margin: '0 0 8px', fontSize: 15 }}>Coupons to pay</h3>
          {unpaid.length === 0 ? <p style={{ margin: 0, color: '#64748b', fontSize: 13 }}>No unpaid coupons.</p> : (
            <table style={{ width: '100%', fontSize: 13, borderCollapse: 'collapse' }} data-no-tools data-testid="debt-gl-coupons">
              <thead><tr><th align="left">Due</th><th align="right">Principal</th><th align="right">Interest and fees</th><th /></tr></thead>
              <tbody>
                {unpaid.map((c) => (
                  <tr key={c.id} data-testid="debt-gl-coupon">
                    <td>{ddmmyyyy(c.due_date)}</td>
                    <td align="right">{money(c.principal_amount)}</td>
                    <td align="right">{money(Number(c.interest_amount) + Number(c.commitment_fee))}</td>
                    <td align="right">
                      <button type="button" style={btn} disabled={!mapped} data-testid="debt-gl-pay"
                        onClick={() => open({ pay: c.id }, { bank: String(instrument.bank_account ?? ''), date: todayISO() })}>Pay</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
        <div style={card}>
          <h3 style={{ margin: '0 0 8px', fontSize: 15 }}>Drawdowns and classifications</h3>
          <table style={{ width: '100%', fontSize: 13, borderCollapse: 'collapse' }} data-no-tools data-testid="debt-gl-history">
            <tbody>
              {drawdowns.map((d) => (
                <tr key={`d${d.id}`}><td>{ddmmyyyy(d.drawdown_date)}</td><td>Drawdown into {d.bank_account_name}</td><td align="right">{money(d.amount)}</td><td>{d.journal_number}</td></tr>
              ))}
              {classifications.map((c) => (
                <tr key={`c${c.id}`}><td>{ddmmyyyy(c.as_of)}</td><td>Current portion set to {money(c.current_portion)}</td><td align="right">{money(c.adjustment)}</td><td>{c.journal_number}</td></tr>
              ))}
              {drawdowns.length + classifications.length === 0 && <tr><td colSpan={4} style={{ color: '#64748b' }}>Nothing posted yet.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>

      <Modal title={`GL mapping: ${instrument.instrument_number}`} open={dialog === 'mapping'} onCancel={() => setDialog(null)} footer={null} destroyOnClose>
        <div style={{ display: 'grid', gap: 12 }} data-testid="debt-gl-mapping-form">
          {([['liability', 'Non-current liability (long-term borrowings)', 'Liability'], ['current', 'Current portion of long-term borrowings', 'Liability'],
             ['interest', 'Interest expense', 'Expense'], ['fee', 'Fee expense (blank uses interest)', 'Expense']] as const).map(([key, text, kind]) => (
            <div key={key}><label style={label}>{text}</label>
              <SearchableSelect options={options(kind)} value={form[key] ?? ''} onChange={(v) => set(key, v)} placeholder="Search by code or name" /></div>
          ))}
          <div><label style={label}>Default bank account</label>
            <SearchableSelect options={bankOptions} value={form.bank ?? ''} onChange={(v) => set('bank', v)} placeholder="Bank account" /></div>
          {error && <div role="alert" style={{ color: '#b91c1c', fontSize: 13 }}>{error}</div>}
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
            <button type="button" style={btn} onClick={() => setDialog(null)}>Cancel</button>
            <button type="button" style={primary} data-testid="debt-gl-mapping-save" onClick={() => run(() => saveMapping.mutateAsync({
              id: instrument.id, body: {
                liability_account: form.liability ? Number(form.liability) : null, current_portion_account: form.current ? Number(form.current) : null,
                interest_expense_account: form.interest ? Number(form.interest) : null, fee_expense_account: form.fee ? Number(form.fee) : null,
                bank_account: form.bank ? Number(form.bank) : null } }), 'GL mapping saved.')}>Save mapping</button>
          </div>
        </div>
      </Modal>

      <Modal title={`Record drawdown: ${instrument.instrument_number}`} open={dialog === 'drawdown'} onCancel={() => setDialog(null)} footer={null} destroyOnClose>
        <div style={{ display: 'grid', gap: 12 }} data-testid="debt-gl-drawdown-form">
          <div><label style={label}>Amount received</label><AmountInput value={form.amount ?? ''} onChange={(v) => set('amount', v)} aria-label="Drawdown amount" /></div>
          <div><label style={label}>Received into bank account</label>
            <SearchableSelect options={bankOptions} value={form.bank ?? ''} onChange={(v) => set('bank', v)} placeholder="Bank account" /></div>
          <div><label style={label}>Date</label><input style={input} type="date" value={form.date ?? ''} onChange={(e) => set('date', e.target.value)} aria-label="Drawdown date" /></div>
          <div><label style={label}>Reference (optional)</label><input style={input} value={form.reference ?? ''} onChange={(e) => set('reference', e.target.value)} aria-label="Drawdown reference" /></div>
          <p style={{ margin: 0, fontSize: 12, color: '#64748b' }}>Debits the bank account and credits the non-current liability.</p>
          {error && <div role="alert" style={{ color: '#b91c1c', fontSize: 13 }} data-testid="debt-gl-error">{error}</div>}
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
            <button type="button" style={btn} onClick={() => setDialog(null)}>Cancel</button>
            <button type="button" style={primary} data-testid="debt-gl-drawdown-save" onClick={() => run(() => drawdown.mutateAsync({
              id: instrument.id, body: { amount: form.amount, bank_account: form.bank ? Number(form.bank) : null, drawdown_date: form.date, reference: form.reference } }),
              'Drawdown posted.')}>Post drawdown</button>
          </div>
        </div>
      </Modal>

      <Modal title="Reclassify the current portion" open={dialog === 'reclassify'} onCancel={() => setDialog(null)} footer={null} destroyOnClose>
        <div style={{ display: 'grid', gap: 12 }} data-testid="debt-gl-reclassify-form">
          <div><label style={label}>As at</label><input style={input} type="date" value={form.as_of ?? ''} onChange={(e) => set('as_of', e.target.value)} aria-label="Classification date" /></div>
          <p style={{ margin: 0, fontSize: 12, color: '#64748b' }}>
            Principal due within twelve months of this date moves from the non-current liability to current liabilities, so the Statement of Financial Position shows each correctly.
          </p>
          {error && <div role="alert" style={{ color: '#b91c1c', fontSize: 13 }} data-testid="debt-gl-error">{error}</div>}
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
            <button type="button" style={btn} onClick={() => setDialog(null)}>Cancel</button>
            <button type="button" style={primary} data-testid="debt-gl-reclassify-save"
              onClick={() => run(() => reclassify.mutateAsync({ id: instrument.id, as_of: form.as_of }), 'Current portion updated.')}>Post reclassification</button>
          </div>
        </div>
      </Modal>

      <Modal title="Pay coupon" open={typeof dialog === 'object' && dialog !== null} onCancel={() => setDialog(null)} footer={null} destroyOnClose>
        <div style={{ display: 'grid', gap: 12 }} data-testid="debt-gl-pay-form">
          <div><label style={label}>Pay from bank account</label>
            <SearchableSelect options={bankOptions} value={form.bank ?? ''} onChange={(v) => set('bank', v)} placeholder="Bank account" /></div>
          <div><label style={label}>Payment date</label><input style={input} type="date" value={form.date ?? ''} onChange={(e) => set('date', e.target.value)} aria-label="Payment date" /></div>
          <p style={{ margin: 0, fontSize: 12, color: '#64748b' }}>
            Principal reduces the liability (current portion first). Interest and fees are expenses. The bank account is credited.
          </p>
          {error && <div role="alert" style={{ color: '#b91c1c', fontSize: 13 }} data-testid="debt-gl-error">{error}</div>}
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
            <button type="button" style={btn} onClick={() => setDialog(null)}>Cancel</button>
            <button type="button" style={primary} data-testid="debt-gl-pay-save" onClick={() => {
              if (typeof dialog !== 'object' || dialog === null) return;
              void run(() => payCoupon.mutateAsync({ id: dialog.pay, body: { bank_account: form.bank ? Number(form.bank) : null, paid_date: form.date } }), 'Coupon paid and posted.');
            }}>Pay and post</button>
          </div>
        </div>
      </Modal>
    </section>
  );
}
