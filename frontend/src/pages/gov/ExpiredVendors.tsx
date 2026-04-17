/**
 * Expired Suppliers + Renewal Invoice — Quot PSE
 * Route: /procurement/vendors-expired
 *
 * Shows expired vendors. Generate renewal invoices with TSA bank details.
 * Confirm payment → GL entry (DR TSA, CR Revenue) → vendor renewed.
 */
import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Clock, RefreshCw, AlertTriangle, FileText, CheckCircle2, X, RotateCcw } from 'lucide-react';
import Sidebar from '../../components/Sidebar';
import PageHeader from '../../components/PageHeader';
import '../../features/accounting/styles/glassmorphism.css';
import apiClient from '../../api/client';
import { useFiscalYears, useTSAAccounts } from '../../hooks/useGovForms';

const lblStyle: React.CSSProperties = {
    display: 'block', fontSize: '0.65rem', fontWeight: 600,
    color: 'var(--color-text-muted)', marginBottom: '0.25rem',
    textTransform: 'uppercase' as const, letterSpacing: '0.04em',
};
const inputStyle: React.CSSProperties = {
    width: '100%', padding: '0.5rem 0.625rem', borderRadius: '6px',
    border: '2.5px solid var(--color-border)', background: 'var(--color-surface)',
    color: 'var(--color-text)', fontSize: 'var(--text-xs)',
};
const selectStyle: React.CSSProperties = { ...inputStyle, appearance: 'auto' as never };

const fmtNGN = (v: number | string): string => {
    const num = typeof v === 'string' ? parseFloat(v) : v;
    return '\u20A6' + (isNaN(num) ? 0 : num).toLocaleString('en-NG', { minimumFractionDigits: 2 });
};

export default function ExpiredVendors() {
    const [search, setSearch] = useState('');
    const [selected, setSelected] = useState<Set<number>>(new Set());
    const [msg, setMsg] = useState('');
    const [invoiceModal, setInvoiceModal] = useState<any>(null); // vendor being invoiced
    const [generatedInvoice, setGeneratedInvoice] = useState<any>(null);
    const [invoiceForm, setInvoiceForm] = useState({ amount: '', tsa_account_id: '', fiscal_year_id: '', notes: '' });
    const [paymentRef, setPaymentRef] = useState('');
    const qc = useQueryClient();
    const { data: fiscalYears } = useFiscalYears();
    const { data: tsaAccounts } = useTSAAccounts();

    // Check if invoice gate is enabled
    const { data: invoiceGate } = useQuery({
        queryKey: ['vendor-invoice-gate'],
        queryFn: async () => {
            const res = await apiClient.get('/procurement/vendors/invoice_gate_status/');
            return res.data as { enabled: boolean };
        },
    });
    const invoiceGateEnabled = invoiceGate?.enabled ?? true;

    const { data: vendors = [], isLoading } = useQuery({
        queryKey: ['vendors-expired', search],
        queryFn: async () => {
            const res = await apiClient.get('/procurement/vendors/expired/', { params: search ? { search } : {} });
            return Array.isArray(res.data) ? res.data : res.data?.results || [];
        },
    });

    const toggleSelect = (id: number) => setSelected(prev => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });
    const toggleAll = () => selected.size === vendors.length ? setSelected(new Set()) : setSelected(new Set(vendors.map((v: any) => v.id)));

    const flash = (m: string) => { setMsg(m); setTimeout(() => setMsg(''), 5000); };

    // Direct renew (no invoice — when gate is disabled)
    const handleDirectRenew = async (vendorId: number) => {
        try {
            const res = await apiClient.post(`/procurement/vendors/${vendorId}/direct_renew/`);
            flash(res.data.status || 'Vendor renewed');
            qc.invalidateQueries({ queryKey: ['vendors-expired'] });
            qc.invalidateQueries({ queryKey: ['vendors'] });
        } catch (err: any) { flash(err?.response?.data?.error || 'Failed to renew'); }
    };

    // Mass direct renew
    const handleMassDirectRenew = async () => {
        let renewed = 0;
        for (const id of selected) {
            try {
                await apiClient.post(`/procurement/vendors/${id}/direct_renew/`);
                renewed++;
            } catch { /* skip */ }
        }
        flash(`${renewed} vendor(s) renewed`);
        setSelected(new Set());
        qc.invalidateQueries({ queryKey: ['vendors-expired'] });
        qc.invalidateQueries({ queryKey: ['vendors'] });
    };

    // Generate renewal invoice
    const handleGenerateInvoice = async () => {
        if (!invoiceForm.amount || !invoiceForm.tsa_account_id || !invoiceForm.fiscal_year_id) return;
        try {
            const res = await apiClient.post(`/procurement/vendors/${invoiceModal.id}/generate_renewal_invoice/`, invoiceForm);
            setGeneratedInvoice(res.data);
            flash('Renewal invoice generated');
        } catch (err: any) { flash(err?.response?.data?.error || 'Failed'); }
    };

    // Confirm payment — accepts invoice+vendorId directly to avoid stale-state bug
    const handleConfirmPayment = async (invoice: any, vendorId: number) => {
        if (!paymentRef) return;
        try {
            const res = await apiClient.post(`/procurement/vendors/${vendorId}/confirm_renewal_payment/`, {
                invoice_id: invoice.id, payment_reference: paymentRef,
            });
            flash(res.data.status || 'Payment confirmed');
            setPaymentRef(''); setGeneratedInvoice(null); setInvoiceModal(null);
            qc.invalidateQueries({ queryKey: ['vendors-expired'] });
            qc.invalidateQueries({ queryKey: ['vendors'] });
        } catch (err: any) { flash(err?.response?.data?.error || 'Failed'); }
    };

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }}>
                <PageHeader title="Expired Suppliers" subtitle="Generate renewal invoices, confirm payment, and re-activate vendors" icon={<Clock size={22} />} />

                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem', gap: '1rem' }}>
                    <input type="text" placeholder="Search expired vendors..." value={search} onChange={e => setSearch(e.target.value)}
                        style={{ flex: 1, maxWidth: 400, ...inputStyle }} />
                </div>

                {msg && (
                    <div style={{ padding: '0.75rem 1rem', borderRadius: '8px', marginBottom: '1rem', background: 'rgba(34,197,94,0.08)', border: '1px solid rgba(34,197,94,0.2)', color: '#166534', fontSize: 'var(--text-sm)' }}>{msg}</div>
                )}

                {vendors.length > 0 && (
                    <div style={{ padding: '0.5rem 0.75rem', borderRadius: '6px', marginBottom: '1rem', background: '#fffbeb', border: '1px solid #fde68a', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.5rem', fontSize: 'var(--text-xs)', color: '#92400e' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                            <AlertTriangle size={14} />
                            {invoiceGateEnabled
                                ? 'These vendors cannot receive POs or PVs until renewed. Generate a renewal invoice and confirm payment.'
                                : 'These vendors cannot receive POs or PVs until renewed. Click Renew to re-activate for 1 year.'}
                        </div>
                        {!invoiceGateEnabled && selected.size > 0 && (
                            <button onClick={handleMassDirectRenew}
                                style={{ padding: '0.3rem 0.7rem', borderRadius: '6px', border: 'none', cursor: 'pointer', fontSize: 'var(--text-xs)', fontWeight: 600, background: '#166534', color: '#fff', whiteSpace: 'nowrap', display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                                <RotateCcw size={12} /> Renew Selected ({selected.size})
                            </button>
                        )}
                    </div>
                )}

                <div className="glass-card" style={{ overflow: 'hidden' }}>
                    {isLoading ? (
                        <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>Loading...</div>
                    ) : vendors.length === 0 ? (
                        <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>No expired vendors found.</div>
                    ) : (
                        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                            <thead>
                                <tr style={{ borderBottom: '2px solid var(--color-border)' }}>
                                    <th style={{ padding: '0.75rem 0.5rem', width: '40px', textAlign: 'center' }}>
                                        <input type="checkbox" checked={selected.size === vendors.length && vendors.length > 0} onChange={toggleAll} style={{ cursor: 'pointer', width: 16, height: 16 }} />
                                    </th>
                                    {['Code', 'Vendor Name', 'Expiry Date', 'Status', 'Actions'].map(h => (
                                        <th key={h} style={{ padding: '0.75rem', textAlign: 'left', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>{h}</th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody>
                                {vendors.map((v: any) => (
                                    <tr key={v.id} style={{ borderBottom: '1px solid var(--color-border)', background: selected.has(v.id) ? 'rgba(25,30,106,0.03)' : '' }}>
                                        <td style={{ padding: '0.75rem 0.5rem', textAlign: 'center' }}>
                                            <input type="checkbox" checked={selected.has(v.id)} onChange={() => toggleSelect(v.id)} style={{ cursor: 'pointer', width: 16, height: 16 }} />
                                        </td>
                                        <td style={{ padding: '0.75rem', fontSize: 'var(--text-sm)', fontFamily: 'monospace' }}>{v.code}</td>
                                        <td style={{ padding: '0.75rem', fontSize: 'var(--text-sm)', fontWeight: 500 }}>{v.name}</td>
                                        <td style={{ padding: '0.75rem', fontSize: 'var(--text-sm)', color: '#dc2626', fontWeight: 600 }}>{v.expiry_date || '\u2014'}</td>
                                        <td style={{ padding: '0.75rem' }}>
                                            <span style={{ padding: '0.2rem 0.5rem', borderRadius: '12px', fontSize: '0.65rem', fontWeight: 600, background: '#fef2f2', color: '#dc2626', border: '1px solid #fecaca' }}>EXPIRED</span>
                                        </td>
                                        <td style={{ padding: '0.75rem' }}>
                                            {invoiceGateEnabled ? (
                                                <button onClick={() => { setInvoiceModal(v); setGeneratedInvoice(null); setInvoiceForm({ amount: '', tsa_account_id: '', fiscal_year_id: '', notes: '' }); }}
                                                    style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', padding: '0.3rem 0.6rem', borderRadius: '6px', border: 'none', cursor: 'pointer', fontSize: 'var(--text-xs)', fontWeight: 600, background: 'linear-gradient(135deg, var(--primary, #191e6a), var(--primary-dark, #0f1240))', color: '#fff' }}>
                                                    <FileText size={12} /> Generate Invoice
                                                </button>
                                            ) : (
                                                <button onClick={() => handleDirectRenew(v.id)}
                                                    style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', padding: '0.3rem 0.6rem', borderRadius: '6px', border: 'none', cursor: 'pointer', fontSize: 'var(--text-xs)', fontWeight: 600, background: '#166534', color: '#fff' }}>
                                                    <RotateCcw size={12} /> Renew
                                                </button>
                                            )}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    )}
                </div>

                {/* ── Invoice Generation Modal ───────────────────────── */}
                {invoiceModal && !generatedInvoice && (
                    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', zIndex: 100, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        <div className="glass-card" style={{ padding: '1.5rem', width: '100%', maxWidth: 500 }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
                                <h3 style={{ fontSize: 'var(--text-base)', fontWeight: 700, margin: 0 }}>Generate Renewal Invoice</h3>
                                <button onClick={() => setInvoiceModal(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-muted)' }}><X size={18} /></button>
                            </div>
                            <p style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)', marginBottom: '1rem' }}>
                                Vendor: <strong>{invoiceModal.name}</strong> ({invoiceModal.code})
                            </p>
                            <div style={{ display: 'grid', gap: '0.75rem' }}>
                                <div>
                                    <label style={lblStyle}>Renewal Fee (NGN) *</label>
                                    <input style={{ ...inputStyle, fontSize: 'var(--text-base)', fontWeight: 700 }} type="number" step="0.01" min="0.01"
                                        value={invoiceForm.amount} onChange={e => setInvoiceForm(f => ({ ...f, amount: e.target.value }))} placeholder="e.g. 50000" />
                                </div>
                                <div>
                                    <label style={lblStyle}>TSA Bank Account (pay into) *</label>
                                    <select style={selectStyle} value={invoiceForm.tsa_account_id} onChange={e => setInvoiceForm(f => ({ ...f, tsa_account_id: e.target.value }))}>
                                        <option value="">Select TSA account...</option>
                                        {(tsaAccounts || []).map((a: any) => <option key={a.id} value={a.id}>{a.account_number} — {a.account_name} ({a.bank})</option>)}
                                    </select>
                                </div>
                                <div>
                                    <label style={lblStyle}>Fiscal Year *</label>
                                    <select style={selectStyle} value={invoiceForm.fiscal_year_id} onChange={e => setInvoiceForm(f => ({ ...f, fiscal_year_id: e.target.value }))}>
                                        <option value="">Select year...</option>
                                        {(fiscalYears || []).map((fy: any) => <option key={fy.id} value={fy.id}>{fy.name || `FY ${fy.year}`}</option>)}
                                    </select>
                                </div>
                                <div>
                                    <label style={lblStyle}>Notes</label>
                                    <textarea style={{ ...inputStyle, minHeight: 50 }} value={invoiceForm.notes} onChange={e => setInvoiceForm(f => ({ ...f, notes: e.target.value }))} placeholder="Optional notes..." />
                                </div>
                            </div>
                            <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end', marginTop: '1rem' }}>
                                <button onClick={() => setInvoiceModal(null)} className="glass-button" style={{ padding: '0.5rem 1rem', borderRadius: '6px', border: '1px solid var(--color-border)', background: 'var(--color-surface)', cursor: 'pointer', fontSize: 'var(--text-sm)' }}>Cancel</button>
                                <button onClick={handleGenerateInvoice} disabled={!invoiceForm.amount || !invoiceForm.tsa_account_id || !invoiceForm.fiscal_year_id}
                                    style={{ padding: '0.5rem 1.25rem', borderRadius: '6px', border: 'none', cursor: 'pointer', fontSize: 'var(--text-sm)', fontWeight: 600, background: 'linear-gradient(135deg, var(--primary, #191e6a), var(--primary-dark, #0f1240))', color: '#fff', opacity: (!invoiceForm.amount || !invoiceForm.tsa_account_id || !invoiceForm.fiscal_year_id) ? 0.5 : 1 }}>
                                    <FileText size={14} style={{ verticalAlign: 'middle', marginRight: 4 }} /> Generate Invoice
                                </button>
                            </div>
                        </div>
                    </div>
                )}

                {/* ── Generated Invoice Preview + Confirm Payment ──── */}
                {generatedInvoice && (
                    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', zIndex: 100, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        <div className="glass-card" style={{ padding: '1.5rem', width: '100%', maxWidth: 550 }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
                                <h3 style={{ fontSize: 'var(--text-base)', fontWeight: 700, margin: 0 }}>Renewal Invoice</h3>
                                <button onClick={() => { setGeneratedInvoice(null); setInvoiceModal(null); }} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-muted)' }}><X size={18} /></button>
                            </div>

                            {/* Invoice Details */}
                            <div style={{ background: 'var(--color-surface, #f8fafc)', border: '1px solid var(--color-border)', borderRadius: '8px', padding: '1rem', marginBottom: '1rem' }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.75rem' }}>
                                    <div>
                                        <div style={{ fontSize: '0.6rem', color: 'var(--color-text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>Invoice Number</div>
                                        <div style={{ fontSize: 'var(--text-base)', fontWeight: 700 }}>{generatedInvoice.invoice_number}</div>
                                    </div>
                                    <div style={{ textAlign: 'right' }}>
                                        <div style={{ fontSize: '0.6rem', color: 'var(--color-text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>Amount</div>
                                        <div style={{ fontSize: 'var(--text-lg)', fontWeight: 700, color: 'var(--primary, #191e6a)' }}>{fmtNGN(generatedInvoice.amount)}</div>
                                    </div>
                                </div>
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem', fontSize: 'var(--text-xs)' }}>
                                    <div><span style={{ color: 'var(--color-text-muted)' }}>Vendor:</span> <strong>{generatedInvoice.vendor_name}</strong></div>
                                    <div><span style={{ color: 'var(--color-text-muted)' }}>Fiscal Year:</span> {generatedInvoice.fiscal_year}</div>
                                    <div><span style={{ color: 'var(--color-text-muted)' }}>Date:</span> {generatedInvoice.invoice_date}</div>
                                    <div><span style={{ color: 'var(--color-text-muted)' }}>Due:</span> {generatedInvoice.due_date}</div>
                                </div>

                                <div style={{ marginTop: '0.75rem', padding: '0.625rem', borderRadius: '6px', background: 'rgba(25,30,106,0.04)', border: '1px solid rgba(25,30,106,0.1)' }}>
                                    <div style={{ fontSize: '0.6rem', color: 'var(--color-text-muted)', textTransform: 'uppercase', fontWeight: 600, marginBottom: '0.3rem' }}>Pay To (TSA Bank Account)</div>
                                    <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600 }}>{generatedInvoice.tsa_account_name}</div>
                                    <div style={{ fontSize: 'var(--text-sm)' }}>Account: <strong>{generatedInvoice.tsa_account_number}</strong></div>
                                    <div style={{ fontSize: 'var(--text-sm)' }}>Bank: {generatedInvoice.tsa_bank}</div>
                                </div>
                            </div>

                            {/* Payment Confirmation */}
                            <div style={{ borderTop: '1px solid var(--color-border)', paddingTop: '1rem' }}>
                                <h4 style={{ fontSize: 'var(--text-sm)', fontWeight: 600, margin: '0 0 0.5rem 0' }}>Confirm Payment</h4>
                                <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', margin: '0 0 0.75rem 0' }}>
                                    After vendor pays, enter the payment receipt number below to confirm and renew.
                                </p>
                                <div style={{ display: 'flex', gap: '0.5rem' }}>
                                    <input style={{ ...inputStyle, flex: 1 }} placeholder="Payment receipt / teller number"
                                        value={paymentRef} onChange={e => setPaymentRef(e.target.value)} />
                                    <button onClick={() => handleConfirmPayment(generatedInvoice, invoiceModal?.id)}
                                        disabled={!paymentRef}
                                        style={{ padding: '0.5rem 1rem', borderRadius: '6px', border: 'none', cursor: 'pointer', fontSize: 'var(--text-sm)', fontWeight: 600, background: '#166534', color: '#fff', display: 'flex', alignItems: 'center', gap: '0.3rem', opacity: paymentRef ? 1 : 0.5 }}>
                                        <CheckCircle2 size={14} /> Confirm Payment
                                    </button>
                                </div>
                                <p style={{ fontSize: '0.6rem', color: 'var(--color-text-muted)', marginTop: '0.5rem' }}>
                                    GL Entry: DR TSA Cash {fmtNGN(generatedInvoice.amount)} | CR Revenue (Registration Fees) {fmtNGN(generatedInvoice.amount)}
                                </p>
                            </div>
                        </div>
                    </div>
                )}
            </main>
        </div>
    );
}
