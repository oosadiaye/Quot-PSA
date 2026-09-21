/**
 * Cheque Register — posted outgoing payments and the cheques issued against
 * them. Select one or more posted payment lines that aren't yet on a cheque,
 * click "Create Cheque", enter the cheque number + date, and one cheque is
 * recorded covering them. The line list is intentionally lean; the cheque
 * captures the payment detail (vendor, amount, reference).
 */
import { useMemo, useState } from 'react';
import { BookOpen, Search, Plus } from 'lucide-react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { formatDate } from '@/utils/date';
import { usePayments } from '../hooks/useAccountingEnhancements';
import apiClient from '../../../api/client';
import AccountingLayout from '../AccountingLayout';
import PageHeader from '../../../components/PageHeader';
import { useCurrency } from '../../../context/CurrencyContext';

interface PostedPaymentRow {
    id: number;
    payment_number: string;
    vendor_name?: string;
    is_advance?: boolean;
    advance_type?: string;
    payment_date: string;
    total_amount: string;
    cheque_number?: string;
    status: string;
}

const th: React.CSSProperties = {
    padding: '10px 14px', textAlign: 'left', fontWeight: 700, color: '#64748b',
    fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.05em',
    borderBottom: '1px solid #e2e8f0', whiteSpace: 'nowrap',
};
const td: React.CSSProperties = { padding: '11px 14px', color: '#374151' };

const todayISO = () => new Date().toISOString().slice(0, 10);

export default function ChequeRegisterPage() {
    const { formatCurrency } = useCurrency();
    const queryClient = useQueryClient();
    const { data, isLoading } = usePayments({ status: 'Posted' });
    const [query, setQuery] = useState('');
    const [selected, setSelected] = useState<number[]>([]);
    const [showModal, setShowModal] = useState(false);
    const [chequeNumber, setChequeNumber] = useState('');
    const [chequeDate, setChequeDate] = useState(todayISO());
    const [note, setNote] = useState<{ msg: string; type: 'success' | 'error' } | null>(null);

    const flash = (msg: string, type: 'success' | 'error') => {
        setNote({ msg, type });
        setTimeout(() => setNote(null), 4000);
    };

    const rows = ((data as PostedPaymentRow[] | undefined) ?? [])
        .filter((p) => p.status === 'Posted');

    const filtered = useMemo(() => {
        const needle = query.trim().toLowerCase();
        if (!needle) return rows;
        return rows.filter((p) =>
            [p.payment_number, p.vendor_name, p.cheque_number]
                .some((v) => (v || '').toLowerCase().includes(needle)),
        );
    }, [rows, query]);

    const total = filtered.reduce((s, p) => s + (parseFloat(p.total_amount) || 0), 0);
    // Only payments not yet on a cheque are selectable for a new cheque.
    const selectableIds = filtered.filter((p) => !p.cheque_number).map((p) => p.id);
    const selectedRows = rows.filter((p) => selected.includes(p.id));
    const selectedTotal = selectedRows.reduce((s, p) => s + (parseFloat(p.total_amount) || 0), 0);

    const toggle = (id: number) =>
        setSelected((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
    const allSelected = selectableIds.length > 0 && selectableIds.every((id) => selected.includes(id));
    const toggleAll = () =>
        setSelected((prev) => (allSelected ? prev.filter((id) => !selectableIds.includes(id)) : Array.from(new Set([...prev, ...selectableIds]))));

    const createCheque = useMutation({
        mutationFn: async () => {
            const { data: res } = await apiClient.post('/accounting/checks/create-from-payments/', {
                check_number: chequeNumber.trim(),
                date_issued: chequeDate,
                payment_ids: selected,
            });
            return res;
        },
        onSuccess: (res) => {
            queryClient.invalidateQueries({ queryKey: ['payments'] });
            setShowModal(false);
            setSelected([]);
            setChequeNumber('');
            setChequeDate(todayISO());
            flash(`Cheque ${res?.check_number ?? ''} created for ${res?.payment_count ?? selected.length} payment(s).`, 'success');
        },
        onError: (err: unknown) => {
            const e = err as { response?: { data?: { error?: string } } };
            flash(e?.response?.data?.error || 'Failed to create cheque.', 'error');
        },
    });

    return (
        <AccountingLayout>
            <PageHeader
                title="Cheque Register"
                subtitle="Posted payments and the cheques issued against them"
            />

            {note && (
                <div style={{
                    padding: '10px 14px', borderRadius: '10px', marginBottom: '16px', fontSize: '13px',
                    background: note.type === 'success' ? '#dcfce7' : '#fee2e2',
                    color: note.type === 'success' ? '#166534' : '#991b1b',
                    border: `1px solid ${note.type === 'success' ? '#bbf7d0' : '#fecaca'}`,
                }}>{note.msg}</div>
            )}

            <div style={{
                background: '#fff', borderRadius: '16px', border: '1px solid #e2e8f0',
                boxShadow: '0 1px 6px rgba(0,0,0,0.04)', padding: '18px 20px',
            }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px', marginBottom: '16px', flexWrap: 'wrap' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <BookOpen size={18} color="#0f766e" />
                        <div>
                            <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 700, color: '#1e293b' }}>Posted Payments</h3>
                            <p style={{ margin: '2px 0 0', fontSize: '13px', color: '#64748b' }}>
                                {filtered.length} payment{filtered.length === 1 ? '' : 's'} · total {formatCurrency(String(total))}
                                {selected.length > 0 && ` · ${selected.length} selected (${formatCurrency(String(selectedTotal))})`}
                            </p>
                        </div>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
                        <div style={{ position: 'relative' }}>
                            <Search size={15} color="#94a3b8" style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)' }} />
                            <input
                                value={query}
                                onChange={(e) => setQuery(e.target.value)}
                                placeholder="Filter by #, vendor, cheque…"
                                aria-label="Filter posted payments"
                                style={{ padding: '8px 12px 8px 32px', border: '1px solid #e2e8f0', borderRadius: '9px', fontSize: '13px', minWidth: '240px', outline: 'none' }}
                            />
                        </div>
                        <button
                            disabled={selected.length === 0}
                            onClick={() => setShowModal(true)}
                            style={{
                                display: 'flex', alignItems: 'center', gap: '6px', padding: '9px 16px',
                                border: 'none', borderRadius: '9px', color: '#fff', fontSize: '13px', fontWeight: 600,
                                background: selected.length === 0 ? '#e2e8f0' : 'linear-gradient(135deg,#0d9488,#0f766e)',
                                cursor: selected.length === 0 ? 'not-allowed' : 'pointer',
                            }}>
                            <Plus size={15} /> Create Cheque ({selected.length})
                        </button>
                    </div>
                </div>

                {isLoading ? (
                    <div style={{ textAlign: 'center', padding: '40px', color: '#94a3b8' }}>Loading posted payments…</div>
                ) : !filtered.length ? (
                    <div style={{ textAlign: 'center', padding: '60px 20px', background: '#f8fafc', borderRadius: '12px', border: '2px dashed #e2e8f0' }}>
                        <BookOpen size={40} color="#cbd5e1" style={{ marginBottom: '12px' }} />
                        <p style={{ color: '#94a3b8', fontSize: '14px', margin: 0 }}>
                            {query ? 'No posted payments match your filter.' : 'No posted payments yet.'}
                        </p>
                    </div>
                ) : (
                    <div style={{ overflowX: 'auto' }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
                            <thead>
                                <tr style={{ background: '#f8fafc' }}>
                                    <th style={{ ...th, width: '32px' }}>
                                        <input type="checkbox" checked={allSelected} onChange={toggleAll}
                                            disabled={selectableIds.length === 0} aria-label="Select all unassigned payments" />
                                    </th>
                                    {['Payment #', 'Vendor', 'Amount', 'Date', 'Cheque #'].map((h) => (
                                        <th key={h} style={th}>{h}</th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody>
                                {filtered.map((p) => (
                                    <tr key={p.id} style={{ borderBottom: '1px solid #f1f5f9', background: selected.includes(p.id) ? '#f0fdfa' : undefined }}>
                                        <td style={{ ...td }}>
                                            <input
                                                type="checkbox"
                                                checked={selected.includes(p.id)}
                                                disabled={!!p.cheque_number}
                                                onChange={() => toggle(p.id)}
                                                aria-label={`Select ${p.payment_number} for a cheque`}
                                            />
                                        </td>
                                        <td style={{ ...td, fontWeight: 600, color: '#1e293b' }}>{p.payment_number}</td>
                                        <td style={td}>{p.vendor_name || '—'}</td>
                                        <td style={{ ...td, fontWeight: 700, color: '#dc2626', whiteSpace: 'nowrap' }}>{formatCurrency(p.total_amount)}</td>
                                        <td style={td}>{formatDate(p.payment_date)}</td>
                                        <td style={td}>
                                            {p.cheque_number
                                                ? <span style={{ fontFamily: 'monospace', fontWeight: 600, color: '#0f766e' }}>{p.cheque_number}</span>
                                                : <span style={{ color: '#cbd5e1' }}>—</span>}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                            <tfoot>
                                <tr style={{ borderTop: '2px solid #e2e8f0', background: '#f8fafc' }}>
                                    <td style={td} />
                                    <td style={{ ...td, fontWeight: 700 }} colSpan={2}>Total ({filtered.length})</td>
                                    <td style={{ ...td, fontWeight: 800, color: '#1e293b', whiteSpace: 'nowrap' }}>{formatCurrency(String(total))}</td>
                                    <td style={td} colSpan={2} />
                                </tr>
                            </tfoot>
                        </table>
                    </div>
                )}
            </div>

            {showModal && (
                <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <div role="dialog" aria-modal="true" style={{ background: '#fff', borderRadius: '16px', padding: '28px', width: 'min(520px, 94vw)', boxShadow: '0 24px 80px rgba(0,0,0,0.22)' }}>
                        <h3 style={{ margin: '0 0 4px', fontSize: '17px', fontWeight: 700, color: '#1e293b' }}>Create Cheque</h3>
                        <p style={{ margin: '0 0 18px', fontSize: '13px', color: '#64748b' }}>
                            One cheque for {selected.length} selected payment{selected.length === 1 ? '' : 's'} · {formatCurrency(String(selectedTotal))}
                        </p>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '20px' }}>
                            <div>
                                <label style={{ display: 'block', fontSize: '12px', color: '#64748b', marginBottom: '6px' }}>Cheque Number *</label>
                                <input value={chequeNumber} onChange={(e) => setChequeNumber(e.target.value)} placeholder="e.g. 000123"
                                    style={{ width: '100%', padding: '9px 12px', border: '1px solid #e2e8f0', borderRadius: '9px', fontSize: '14px', outline: 'none' }} />
                            </div>
                            <div>
                                <label style={{ display: 'block', fontSize: '12px', color: '#64748b', marginBottom: '6px' }}>Created Date *</label>
                                <input type="date" value={chequeDate} onChange={(e) => setChequeDate(e.target.value)}
                                    style={{ width: '100%', padding: '9px 12px', border: '1px solid #e2e8f0', borderRadius: '9px', fontSize: '14px', outline: 'none' }} />
                            </div>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
                            <button onClick={() => setShowModal(false)} disabled={createCheque.isPending}
                                style={{ padding: '9px 16px', border: '1px solid #e2e8f0', borderRadius: '9px', background: '#fff', color: '#475569', fontSize: '13px', fontWeight: 600, cursor: 'pointer' }}>
                                Cancel
                            </button>
                            <button
                                onClick={() => createCheque.mutate()}
                                disabled={!chequeNumber.trim() || !chequeDate || createCheque.isPending}
                                style={{
                                    padding: '9px 18px', border: 'none', borderRadius: '9px', color: '#fff', fontSize: '13px', fontWeight: 600,
                                    background: (!chequeNumber.trim() || createCheque.isPending) ? '#94a3b8' : 'linear-gradient(135deg,#0d9488,#0f766e)',
                                    cursor: (!chequeNumber.trim() || createCheque.isPending) ? 'not-allowed' : 'pointer',
                                }}>
                                {createCheque.isPending ? 'Creating…' : 'Create Cheque'}
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </AccountingLayout>
    );
}
