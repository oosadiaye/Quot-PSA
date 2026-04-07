import { useState, useMemo } from 'react';
import { X, Link2, CheckCircle2, ArrowDownRight, ArrowUpRight } from 'lucide-react';
import { useVendorTransactionHistory } from './hooks/useProcurement';
import { useCurrency } from '../../context/CurrencyContext';
import { useFocusTrap } from '../../hooks/useFocusTrap';

interface TransactionRow {
    id: string;
    date: string;
    reference: string;
    type: string;
    description: string;
    debit: number;
    credit: number;
    status: string;
    sourceType: string;
}

interface Props {
    vendor: { id: number; name: string; code: string };
    onClose: () => void;
}

const VendorHistoryModal = ({ vendor, onClose }: Props) => {
    const dialogRef = useFocusTrap(true, onClose);
    const { data, isLoading } = useVendorTransactionHistory(vendor.id);
    const { formatCurrency } = useCurrency();
    const [selected, setSelected] = useState<Set<string>>(new Set());
    const [matched, setMatched] = useState<Set<string>>(new Set());

    const transactions: TransactionRow[] = useMemo(() => {
        if (!data) return [];
        const rows: TransactionRow[] = [];

        // Vendor Invoices → Credit
        (data.invoices || []).forEach((inv: any) => {
            rows.push({
                id: `inv-${inv.id}`,
                date: inv.invoice_date,
                reference: inv.invoice_number || inv.reference || '',
                type: 'Invoice',
                description: inv.description || `Invoice ${inv.invoice_number}`,
                debit: 0,
                credit: Number(inv.total_amount) || 0,
                status: inv.status,
                sourceType: 'invoice',
            });
        });

        // Payments → Debit
        (data.payments || []).forEach((pmt: any) => {
            rows.push({
                id: `pmt-${pmt.id}`,
                date: pmt.payment_date,
                reference: pmt.payment_number || pmt.reference_number || '',
                type: 'Payment',
                description: `${pmt.payment_method || ''} Payment ${pmt.payment_number}`,
                debit: Number(pmt.total_amount) || 0,
                credit: 0,
                status: pmt.status,
                sourceType: 'payment',
            });
        });

        // Purchase Returns → Debit (reduces AP)
        (data.returns || []).forEach((ret: any) => {
            rows.push({
                id: `ret-${ret.id}`,
                date: ret.return_date,
                reference: ret.return_number || `RET-${ret.id}`,
                type: 'Return',
                description: ret.reason || `Purchase Return`,
                debit: Number(ret.total_amount) || 0,
                credit: 0,
                status: ret.status,
                sourceType: 'return',
            });
        });

        // Sort by date descending
        rows.sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime());
        return rows;
    }, [data]);

    // Separate matched and unmatched
    const unmatchedRows = transactions.filter(t => !matched.has(t.id));
    const matchedRows = transactions.filter(t => matched.has(t.id));

    const totalDebit = transactions.reduce((s, t) => s + t.debit, 0);
    const totalCredit = transactions.reduce((s, t) => s + t.credit, 0);
    const balance = totalCredit - totalDebit;

    const selectedDebit = [...selected].reduce((s, id) => {
        const t = transactions.find(r => r.id === id);
        return s + (t?.debit || 0);
    }, 0);
    const selectedCredit = [...selected].reduce((s, id) => {
        const t = transactions.find(r => r.id === id);
        return s + (t?.credit || 0);
    }, 0);

    const toggleSelect = (id: string) => {
        const next = new Set(selected);
        if (next.has(id)) next.delete(id);
        else next.add(id);
        setSelected(next);
    };

    const handleMatch = () => {
        if (selected.size < 2) return;
        const next = new Set(matched);
        selected.forEach(id => next.add(id));
        setMatched(next);
        setSelected(new Set());
    };

    const typeColors: Record<string, { bg: string; color: string }> = {
        Invoice: { bg: 'rgba(239, 68, 68, 0.1)', color: '#ef4444' },
        Payment: { bg: 'rgba(34, 197, 94, 0.1)', color: '#22c55e' },
        Return: { bg: 'rgba(168, 85, 247, 0.1)', color: '#a855f7' },
    };

    const thStyle: React.CSSProperties = {
        padding: '0.625rem 0.75rem', fontSize: 'var(--text-xs)', fontWeight: 700,
        textTransform: 'uppercase', letterSpacing: '0.05em',
        color: 'var(--color-text-muted)', whiteSpace: 'nowrap',
        borderBottom: '2px solid var(--color-border)',
    };

    const tdStyle: React.CSSProperties = {
        padding: '0.625rem 0.75rem', fontSize: 'var(--text-sm)',
        color: 'var(--color-text)', borderBottom: '1px solid var(--color-border)',
    };

    const renderRow = (t: TransactionRow, isMatched: boolean) => {
        const tc = typeColors[t.type] || { bg: 'rgba(156,163,175,0.1)', color: '#6b7280' };
        return (
            <tr key={t.id} style={{
                opacity: isMatched ? 0.45 : 1,
                textDecoration: isMatched ? 'line-through' : 'none',
                background: selected.has(t.id) ? 'rgba(79, 70, 229, 0.06)' : undefined,
            }}>
                <td style={{ ...tdStyle, width: '36px', textAlign: 'center' }}>
                    {!isMatched && (
                        <input type="checkbox" checked={selected.has(t.id)}
                            onChange={() => toggleSelect(t.id)}
                            style={{ cursor: 'pointer', accentColor: '#4f46e5' }} />
                    )}
                    {isMatched && <CheckCircle2 size={14} color="#22c55e" />}
                </td>
                <td style={{ ...tdStyle, whiteSpace: 'nowrap' }}>
                    {new Date(t.date).toLocaleDateString()}
                </td>
                <td style={{ ...tdStyle, fontWeight: 600 }}>{t.reference}</td>
                <td style={tdStyle}>
                    <span style={{
                        padding: '0.15rem 0.5rem', borderRadius: '9999px', fontSize: 'var(--text-xs)',
                        fontWeight: 600, background: tc.bg, color: tc.color,
                    }}>
                        {t.type}
                    </span>
                </td>
                <td style={{ ...tdStyle, maxWidth: '220px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {t.description}
                </td>
                <td style={{ ...tdStyle, textAlign: 'right', fontWeight: t.debit > 0 ? 600 : 400, color: t.debit > 0 ? '#22c55e' : 'var(--color-text-muted)' }}>
                    {t.debit > 0 ? formatCurrency(t.debit) : '—'}
                </td>
                <td style={{ ...tdStyle, textAlign: 'right', fontWeight: t.credit > 0 ? 600 : 400, color: t.credit > 0 ? '#ef4444' : 'var(--color-text-muted)' }}>
                    {t.credit > 0 ? formatCurrency(t.credit) : '—'}
                </td>
                <td style={tdStyle}>
                    <span style={{
                        padding: '0.15rem 0.5rem', borderRadius: '9999px', fontSize: 'var(--text-xs)',
                        fontWeight: 600,
                        background: t.status === 'Posted' || t.status === 'Paid' ? 'rgba(34,197,94,0.1)' :
                            t.status === 'Void' ? 'rgba(239,68,68,0.1)' : 'rgba(156,163,175,0.1)',
                        color: t.status === 'Posted' || t.status === 'Paid' ? '#22c55e' :
                            t.status === 'Void' ? '#ef4444' : '#9ca3af',
                    }}>
                        {t.status}
                    </span>
                </td>
            </tr>
        );
    };

    return (
        <div style={{
            position: 'fixed', inset: 0, zIndex: 9999,
            background: 'rgba(0,0,0,0.5)', backdropFilter: 'blur(4px)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            padding: '2rem',
        }} onClick={onClose} role="presentation">
            <div
                ref={dialogRef}
                role="dialog"
                aria-modal="true"
                aria-label={`Transaction history for ${vendor.name}`}
                style={{
                    background: 'var(--color-surface, #fff)', borderRadius: '16px',
                    width: '100%', maxWidth: '1100px', maxHeight: '90vh',
                    display: 'flex', flexDirection: 'column',
                    boxShadow: '0 25px 50px rgba(0,0,0,0.25)',
                }}
                onClick={e => e.stopPropagation()}
            >

                {/* Header */}
                <div style={{
                    padding: '1.5rem 1.75rem', borderBottom: '1px solid var(--color-border)',
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                }}>
                    <div>
                        <h2 style={{ fontSize: 'var(--text-lg)', fontWeight: 700, color: 'var(--color-text)', margin: 0 }}>
                            Transaction History
                        </h2>
                        <p style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)', margin: '0.25rem 0 0' }}>
                            {vendor.name} <span style={{ fontWeight: 600, opacity: 0.7 }}>({vendor.code})</span>
                        </p>
                    </div>
                    <button onClick={onClose} style={{
                        background: 'none', border: 'none', cursor: 'pointer',
                        color: 'var(--color-text-muted)', padding: '0.5rem',
                    }}>
                        <X size={20} />
                    </button>
                </div>

                {/* Summary Cards */}
                <div style={{ padding: '1rem 1.75rem', display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '1rem' }}>
                    <div style={{
                        padding: '1rem', borderRadius: '10px',
                        background: 'rgba(34, 197, 94, 0.08)', border: '1px solid rgba(34, 197, 94, 0.2)',
                    }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.35rem' }}>
                            <ArrowDownRight size={16} color="#22c55e" />
                            <span style={{ fontSize: 'var(--text-xs)', fontWeight: 700, textTransform: 'uppercase', color: '#22c55e' }}>Total Debit</span>
                        </div>
                        <p style={{ fontSize: 'var(--text-lg)', fontWeight: 700, margin: 0, color: 'var(--color-text)' }}>
                            {formatCurrency(totalDebit)}
                        </p>
                    </div>
                    <div style={{
                        padding: '1rem', borderRadius: '10px',
                        background: 'rgba(239, 68, 68, 0.08)', border: '1px solid rgba(239, 68, 68, 0.2)',
                    }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.35rem' }}>
                            <ArrowUpRight size={16} color="#ef4444" />
                            <span style={{ fontSize: 'var(--text-xs)', fontWeight: 700, textTransform: 'uppercase', color: '#ef4444' }}>Total Credit</span>
                        </div>
                        <p style={{ fontSize: 'var(--text-lg)', fontWeight: 700, margin: 0, color: 'var(--color-text)' }}>
                            {formatCurrency(totalCredit)}
                        </p>
                    </div>
                    <div style={{
                        padding: '1rem', borderRadius: '10px',
                        background: balance > 0 ? 'rgba(239, 68, 68, 0.08)' : 'rgba(34, 197, 94, 0.08)',
                        border: `1px solid ${balance > 0 ? 'rgba(239, 68, 68, 0.2)' : 'rgba(34, 197, 94, 0.2)'}`,
                    }}>
                        <span style={{ fontSize: 'var(--text-xs)', fontWeight: 700, textTransform: 'uppercase', color: 'var(--color-text-muted)', display: 'block', marginBottom: '0.35rem' }}>
                            Balance (Cr - Dr)
                        </span>
                        <p style={{
                            fontSize: 'var(--text-lg)', fontWeight: 700, margin: 0,
                            color: balance > 0 ? '#ef4444' : '#22c55e',
                        }}>
                            {formatCurrency(Math.abs(balance))} {balance > 0 ? 'CR' : balance < 0 ? 'DR' : ''}
                        </p>
                    </div>
                </div>

                {/* Matching toolbar */}
                {selected.size > 0 && (
                    <div style={{
                        margin: '0 1.75rem', padding: '0.75rem 1rem', borderRadius: '8px',
                        background: 'rgba(79, 70, 229, 0.08)', border: '1px solid rgba(79, 70, 229, 0.2)',
                        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    }}>
                        <span style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text)' }}>
                            <strong>{selected.size}</strong> items selected
                            {selectedDebit > 0 && selectedCredit > 0 && (
                                <span style={{ marginLeft: '1rem', color: 'var(--color-text-muted)' }}>
                                    Dr: {formatCurrency(selectedDebit)} | Cr: {formatCurrency(selectedCredit)}
                                    {Math.abs(selectedDebit - selectedCredit) < 0.01 && (
                                        <span style={{ color: '#22c55e', fontWeight: 600, marginLeft: '0.5rem' }}>Balanced</span>
                                    )}
                                </span>
                            )}
                        </span>
                        <button onClick={handleMatch} disabled={selected.size < 2}
                            style={{
                                padding: '0.5rem 1rem', borderRadius: '8px', border: 'none',
                                background: '#4f46e5', color: '#fff', cursor: 'pointer',
                                fontWeight: 600, fontSize: 'var(--text-sm)',
                                display: 'flex', alignItems: 'center', gap: '0.35rem',
                                opacity: selected.size < 2 ? 0.5 : 1,
                            }}>
                            <Link2 size={14} /> Match Selected
                        </button>
                    </div>
                )}

                {/* Table */}
                <div style={{ flex: 1, overflow: 'auto', padding: '0 1.75rem 1.5rem', marginTop: '0.75rem' }}>
                    {isLoading ? (
                        <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                            Loading transactions...
                        </div>
                    ) : transactions.length === 0 ? (
                        <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                            No transactions found for this vendor.
                        </div>
                    ) : (
                        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                            <thead>
                                <tr>
                                    <th style={{ ...thStyle, width: '36px' }}></th>
                                    <th style={{ ...thStyle, textAlign: 'left' }}>Date</th>
                                    <th style={{ ...thStyle, textAlign: 'left' }}>Reference</th>
                                    <th style={{ ...thStyle, textAlign: 'left' }}>Type</th>
                                    <th style={{ ...thStyle, textAlign: 'left' }}>Description</th>
                                    <th style={{ ...thStyle, textAlign: 'right', color: '#22c55e' }}>Debit</th>
                                    <th style={{ ...thStyle, textAlign: 'right', color: '#ef4444' }}>Credit</th>
                                    <th style={{ ...thStyle, textAlign: 'left' }}>Status</th>
                                </tr>
                            </thead>
                            <tbody>
                                {unmatchedRows.map(t => renderRow(t, false))}
                                {matchedRows.length > 0 && (
                                    <tr>
                                        <td colSpan={8} style={{
                                            padding: '0.5rem 0.75rem', fontSize: 'var(--text-xs)', fontWeight: 700,
                                            textTransform: 'uppercase', letterSpacing: '0.05em',
                                            color: '#22c55e', background: 'rgba(34, 197, 94, 0.05)',
                                            borderBottom: '1px solid var(--color-border)',
                                        }}>
                                            <CheckCircle2 size={12} style={{ marginRight: '0.35rem', verticalAlign: 'middle' }} />
                                            Matched / Cleared ({matchedRows.length})
                                        </td>
                                    </tr>
                                )}
                                {matchedRows.map(t => renderRow(t, true))}
                            </tbody>
                            <tfoot>
                                <tr style={{ borderTop: '2px solid var(--color-border)' }}>
                                    <td colSpan={5} style={{ ...tdStyle, fontWeight: 700, textAlign: 'right', borderBottom: 'none' }}>
                                        Totals:
                                    </td>
                                    <td style={{ ...tdStyle, textAlign: 'right', fontWeight: 700, color: '#22c55e', borderBottom: 'none' }}>
                                        {formatCurrency(totalDebit)}
                                    </td>
                                    <td style={{ ...tdStyle, textAlign: 'right', fontWeight: 700, color: '#ef4444', borderBottom: 'none' }}>
                                        {formatCurrency(totalCredit)}
                                    </td>
                                    <td style={{ ...tdStyle, borderBottom: 'none' }}></td>
                                </tr>
                            </tfoot>
                        </table>
                    )}
                </div>
            </div>
        </div>
    );
};

export default VendorHistoryModal;
