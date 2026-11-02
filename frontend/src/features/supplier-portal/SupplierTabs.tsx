import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { formatDate } from '../../utils/date';
import {
  portalError, supplierApi,
  type BankChange, type InvoiceRow, type OrderSummary, type PaymentRow, type SupplierProfile,
} from './api';

export const naira = (v: string | number | null | undefined) =>
  v === null || v === undefined || v === '' ? '–' : `₦${Number(v).toLocaleString('en-NG', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

const REGISTRATION: Record<string, { word: string; tone: 'ok' | 'warn' | 'bad' }> = {
  ACTIVE: { word: 'Registration valid', tone: 'ok' },
  NO_EXPIRY: { word: 'Registration valid', tone: 'ok' },
  EXPIRED: { word: 'Registration expired', tone: 'bad' },
  BLOCKED: { word: 'Registration blocked', tone: 'bad' },
  PENDING_ACTIVATION: { word: 'Registration pending', tone: 'warn' },
};

function Empty({ title, children }: { title: string; children: string }) {
  return <div className="sp-empty" data-testid="sp-empty"><h3>{title}</h3><p>{children}</p></div>;
}

function Table({ head, children, label }: { head: { text: string; num?: boolean }[]; children: React.ReactNode; label: string }) {
  return (
    <div className="sp-table-wrap">
      <table className="sp-table" aria-label={label}>
        <thead><tr>{head.map((h) => <th key={h.text} scope="col" className={h.num ? 'num' : undefined}>{h.text}</th>)}</tr></thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

// ── overview and contact details ──────────────────────────────────────────────────────────────────────────────

export function OverviewTab({ profile }: { profile: SupplierProfile }) {
  const qc = useQueryClient();
  const [draft, setDraft] = useState({ email: profile.email, phone: profile.phone, address: profile.address });
  const [saved, setSaved] = useState(false);
  const save = useMutation({
    mutationFn: () => supplierApi.updateProfile(draft),
    onSuccess: () => { setSaved(true); void qc.invalidateQueries({ queryKey: ['supplier', 'profile'] }); },
  });
  const status = REGISTRATION[profile.registration_status] ?? { word: profile.registration_status, tone: 'warn' as const };
  const change = (name: keyof typeof draft, value: string) => { setSaved(false); setDraft((d) => ({ ...d, [name]: value })); };

  return (
    <>
      <section className="sp-card" aria-labelledby="sp-reg">
        <h2 id="sp-reg">Your registration</h2>
        <p className="sp-sub">As held by the procurement office. To correct anything here other than your contact details, write to them.</p>
        <dl className="sp-grid">
          <div className="sp-fact"><dt>Status</dt><dd><span className={`sp-pill ${status.tone}`} data-testid="sp-reg-status">{status.word}</span></dd></div>
          <div className="sp-fact"><dt>Registration number</dt><dd>{profile.registration_number || '–'}</dd></div>
          <div className="sp-fact"><dt>Valid until</dt><dd>{profile.expiry_date ? formatDate(profile.expiry_date) : '–'}</dd></div>
          <div className="sp-fact"><dt>Tax ID</dt><dd>{profile.tax_id || '–'}</dd></div>
        </dl>
      </section>

      <section className="sp-card" aria-labelledby="sp-contact">
        <h2 id="sp-contact">Contact details</h2>
        <p className="sp-sub">The procurement office uses these to reach you about orders and payments.</p>
        {save.isError && <div className="sp-alert bad" role="alert">{portalError(save.error)}</div>}
        {saved && <div className="sp-alert ok" role="status" data-testid="sp-saved">Your contact details are saved.</div>}
        <div className="sp-grid">
          <div className="sp-field"><label htmlFor="sp-email">Email</label>
            <input id="sp-email" type="email" value={draft.email} onChange={(e) => change('email', e.target.value)} /></div>
          <div className="sp-field"><label htmlFor="sp-phone">Phone</label>
            <input id="sp-phone" value={draft.phone} onChange={(e) => change('phone', e.target.value)} /></div>
        </div>
        <div className="sp-field"><label htmlFor="sp-address">Address</label>
          <textarea id="sp-address" rows={3} value={draft.address} onChange={(e) => change('address', e.target.value)} /></div>
        <button type="button" className="sp-btn primary" data-testid="sp-save-contact" disabled={save.isPending} onClick={() => save.mutate()}>
          {save.isPending ? 'Saving…' : 'Save contact details'}
        </button>
      </section>
    </>
  );
}

// ── orders ─────────────────────────────────────────────────────────────────────────────────────────────────────

function OrderDetail({ id, onBack }: { id: number; onBack: () => void }) {
  const qc = useQueryClient();
  const [note, setNote] = useState('');
  const order = useQuery({ queryKey: ['supplier', 'order', id], queryFn: () => supplierApi.order(id) });
  const ack = useMutation({
    mutationFn: () => supplierApi.acknowledge(id, note),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['supplier'] }); },
  });
  if (order.isLoading) return <p className="sp-sub" aria-busy="true">Loading the order…</p>;
  if (order.isError || !order.data) return <div className="sp-alert bad" role="alert">{portalError(order.error)}</div>;
  const o = order.data;
  return (
    <section className="sp-card" aria-labelledby="sp-order-title" data-testid="sp-order-detail">
      <button type="button" className="sp-link" onClick={onBack}>← All orders</button>
      <h2 id="sp-order-title" style={{ marginTop: 12 }}>Order {o.po_number}</h2>
      <dl className="sp-grid" style={{ margin: '14px 0 18px' }}>
        <div className="sp-fact"><dt>Ordered</dt><dd>{formatDate(o.order_date)}</dd></div>
        <div className="sp-fact"><dt>Delivery due</dt><dd>{o.expected_delivery_date ? formatDate(o.expected_delivery_date) : '–'}</dd></div>
        <div className="sp-fact"><dt>Payment terms</dt><dd>{o.payment_terms.replace('_', ' ')}</dd></div>
        <div className="sp-fact"><dt>Total</dt><dd>{naira(o.total_amount)}</dd></div>
      </dl>
      {o.delivery_address && <p className="sp-sub">Deliver to: {o.delivery_address}</p>}
      <Table label={`Lines of order ${o.po_number}`} head={[{ text: 'Description' }, { text: 'Quantity', num: true }, { text: 'Received', num: true }, { text: 'Unit price', num: true }, { text: 'Total', num: true }]}>
        {o.lines.map((l, i) => (
          <tr key={i}><td>{l.description}</td><td className="num">{Number(l.quantity)}</td><td className="num">{Number(l.quantity_received)}</td>
            <td className="num">{naira(l.unit_price)}</td><td className="num">{naira(l.total_price)}</td></tr>
        ))}
      </Table>
      {o.terms_and_conditions && <p className="sp-sub" style={{ marginTop: 14 }}>{o.terms_and_conditions}</p>}
      <div style={{ marginTop: 18 }}>
        {o.acknowledged_at ? (
          <div className="sp-alert ok" role="status" data-testid="sp-acknowledged">You acknowledged this order on {formatDate(o.acknowledged_at)}.</div>
        ) : o.status === 'Closed' ? null : (
          <>
            {ack.isError && <div className="sp-alert bad" role="alert">{portalError(ack.error)}</div>}
            <div className="sp-field"><label htmlFor="sp-ack-note">Note to the procurement office (optional)</label>
              <input id="sp-ack-note" value={note} maxLength={300} onChange={(e) => setNote(e.target.value)} placeholder="For example: will deliver by Friday" /></div>
            <button type="button" className="sp-btn primary" data-testid="sp-acknowledge" disabled={ack.isPending} onClick={() => ack.mutate()}>
              {ack.isPending ? 'Sending…' : 'Acknowledge this order'}
            </button>
          </>
        )}
      </div>
    </section>
  );
}

export function OrdersTab() {
  const [open, setOpen] = useState<number | null>(null);
  const orders = useQuery({ queryKey: ['supplier', 'orders'], queryFn: supplierApi.orders });
  if (open !== null) return <OrderDetail id={open} onBack={() => setOpen(null)} />;
  if (orders.isLoading) return <p className="sp-sub" aria-busy="true">Loading your orders…</p>;
  if (orders.isError) return <div className="sp-alert bad" role="alert">{portalError(orders.error)}</div>;
  const rows: OrderSummary[] = orders.data ?? [];
  if (rows.length === 0) return <section className="sp-card"><Empty title="No orders yet">Approved purchase orders from the government appear here.</Empty></section>;
  return (
    <Table label="Your purchase orders" head={[{ text: 'Order' }, { text: 'Date' }, { text: 'Delivery due' }, { text: 'Total', num: true }, { text: 'Status' }, { text: '' }]}>
      {rows.map((o) => (
        <tr key={o.id} data-testid="sp-order-row">
          <td><b>{o.po_number}</b></td><td>{formatDate(o.order_date)}</td><td>{o.expected_delivery_date ? formatDate(o.expected_delivery_date) : '–'}</td>
          <td className="num">{naira(o.total_amount)}</td>
          <td>{o.acknowledged_at ? <span className="sp-pill ok">Acknowledged</span> : <span className="sp-pill warn">Needs your acknowledgement</span>}</td>
          <td><button type="button" className="sp-link" onClick={() => setOpen(o.id)} aria-label={`Open order ${o.po_number}`}>Open</button></td>
        </tr>
      ))}
    </Table>
  );
}

// ── invoices and payments ──────────────────────────────────────────────────────────────────────────────────────

export function InvoicesTab() {
  const q = useQuery({ queryKey: ['supplier', 'invoices'], queryFn: supplierApi.invoices });
  if (q.isLoading) return <p className="sp-sub" aria-busy="true">Loading your invoices…</p>;
  if (q.isError) return <div className="sp-alert bad" role="alert">{portalError(q.error)}</div>;
  const rows: InvoiceRow[] = q.data ?? [];
  if (rows.length === 0) return <section className="sp-card"><Empty title="No invoices yet">Invoices recorded against your orders appear here, with how much has been paid.</Empty></section>;
  return (
    <Table label="Your invoices" head={[{ text: 'Invoice' }, { text: 'Date' }, { text: 'Due' }, { text: 'Amount', num: true }, { text: 'Paid', num: true }, { text: 'Status' }]}>
      {rows.map((i) => (
        <tr key={i.id}><td><b>{i.invoice_number}</b></td><td>{formatDate(i.invoice_date)}</td><td>{formatDate(i.due_date)}</td>
          <td className="num">{naira(i.total_amount)}</td><td className="num">{naira(i.paid_amount)}</td><td><span className="sp-pill">{i.status}</span></td></tr>
      ))}
    </Table>
  );
}

export function PaymentsTab() {
  const q = useQuery({ queryKey: ['supplier', 'payments'], queryFn: supplierApi.payments });
  if (q.isLoading) return <p className="sp-sub" aria-busy="true">Loading your payments…</p>;
  if (q.isError) return <div className="sp-alert bad" role="alert">{portalError(q.error)}</div>;
  const rows: PaymentRow[] = q.data ?? [];
  if (rows.length === 0) return <section className="sp-card"><Empty title="No payments yet">Payments made to you appear here once they are posted.</Empty></section>;
  return (
    <Table label="Payments made to you" head={[{ text: 'Payment' }, { text: 'Date' }, { text: 'Amount', num: true }, { text: 'Status' }]}>
      {rows.map((p) => (
        <tr key={p.id}><td><b>{p.payment_number}</b></td><td>{formatDate(p.payment_date)}</td><td className="num">{naira(p.total_amount)}</td><td><span className="sp-pill ok">{p.status}</span></td></tr>
      ))}
    </Table>
  );
}

// ── bank details ───────────────────────────────────────────────────────────────────────────────────────────────

const changeTone = (s: BankChange['status']) => (s === 'approved' ? 'ok' : s === 'rejected' ? 'bad' : 'warn');
const changeWord = (s: BankChange['status']) => (s === 'approved' ? 'Approved' : s === 'rejected' ? 'Rejected' : 'Waiting for approval');

export function BankTab({ profile }: { profile: SupplierProfile }) {
  const qc = useQueryClient();
  const [form, setForm] = useState({ bank_name: '', bank_account_number: '', bank_sort_code: '' });
  const history = useQuery({ queryKey: ['supplier', 'bank-changes'], queryFn: supplierApi.bankChanges });
  const send = useMutation({
    mutationFn: () => supplierApi.requestBankChange(form),
    onSuccess: () => { setForm({ bank_name: '', bank_account_number: '', bank_sort_code: '' }); void qc.invalidateQueries({ queryKey: ['supplier'] }); },
  });
  const waiting = !!profile.pending_bank_change;
  const valid = form.bank_name.trim() !== '' && /^\d{10}$/.test(form.bank_account_number.trim());
  const set = (name: keyof typeof form, value: string) => setForm((f) => ({ ...f, [name]: value }));

  return (
    <>
      <section className="sp-card" aria-labelledby="sp-bank">
        <h2 id="sp-bank">Where you are paid</h2>
        <p className="sp-sub">Payments go to this account. For your protection the full number is never shown here.</p>
        <dl className="sp-grid">
          <div className="sp-fact"><dt>Bank</dt><dd>{profile.bank_name || 'Not set'}</dd></div>
          <div className="sp-fact"><dt>Account number</dt><dd data-testid="sp-bank-masked">{profile.bank_account_masked || 'Not set'}</dd></div>
          <div className="sp-fact"><dt>Sort code</dt><dd>{profile.bank_sort_code || '–'}</dd></div>
        </dl>
      </section>

      <section className="sp-card" aria-labelledby="sp-bank-change">
        <h2 id="sp-bank-change">Change your bank details</h2>
        {waiting ? (
          <div className="sp-alert warn" role="status" data-testid="sp-bank-waiting">
            You asked to change to {profile.pending_bank_change!.bank_name}. The procurement office has to approve it before anything changes.
          </div>
        ) : (
          <>
            <p className="sp-sub">A change takes effect only after the procurement office approves it. Check the account number carefully.</p>
            {send.isError && <div className="sp-alert bad" role="alert" data-testid="sp-bank-error">{portalError(send.error)}</div>}
            <div className="sp-grid">
              <div className="sp-field"><label htmlFor="sp-bank-name">Bank name</label>
                <input id="sp-bank-name" value={form.bank_name} onChange={(e) => set('bank_name', e.target.value)} /></div>
              <div className="sp-field"><label htmlFor="sp-bank-acct">Account number (10 digits)</label>
                <input id="sp-bank-acct" inputMode="numeric" maxLength={10} value={form.bank_account_number}
                  onChange={(e) => set('bank_account_number', e.target.value.replace(/\D/g, ''))} /></div>
              <div className="sp-field"><label htmlFor="sp-bank-sort">Sort code (optional)</label>
                <input id="sp-bank-sort" value={form.bank_sort_code} onChange={(e) => set('bank_sort_code', e.target.value)} /></div>
            </div>
            <button type="button" className="sp-btn primary" data-testid="sp-bank-send" disabled={!valid || send.isPending} onClick={() => send.mutate()}>
              {send.isPending ? 'Sending…' : 'Ask for this change'}
            </button>
          </>
        )}
      </section>

      {(history.data?.length ?? 0) > 0 && (
        <section className="sp-card" aria-labelledby="sp-bank-history">
          <h2 id="sp-bank-history">Your requests</h2>
          <Table label="Bank change requests" head={[{ text: 'Asked' }, { text: 'Bank' }, { text: 'Status' }, { text: 'Note' }]}>
            {history.data!.map((c) => (
              <tr key={c.id}><td>{formatDate(c.created_at)}</td><td>{c.bank_name}</td>
                <td><span className={`sp-pill ${changeTone(c.status)}`}>{changeWord(c.status)}</span></td><td>{c.reason || '–'}</td></tr>
            ))}
          </Table>
        </section>
      )}
    </>
  );
}
