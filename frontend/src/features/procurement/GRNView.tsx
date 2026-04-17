/**
 * GoodsReceivedNote Detail View — read-only with Post / Cancel actions.
 * Route: /procurement/grn/:id
 */
import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
    Package, FileText, CheckCircle, XCircle, AlertTriangle,
    Building2, Truck, Calendar, User, Layers, ArrowLeft,
} from 'lucide-react';
import { useGRN, usePostGRN, useCancelGRN } from './hooks/useProcurement';
import { useCurrency } from '../../context/CurrencyContext';
import { safeMultiply } from '../accounting/utils/currency';
import AccountingLayout from '../accounting/AccountingLayout';
import PageHeader from '../../components/PageHeader';
import LoadingScreen from '../../components/common/LoadingScreen';
import '../accounting/styles/glassmorphism.css';

const statusConfig: Record<string, { bg: string; color: string; border: string }> = {
    Draft:     { bg: '#f1f5f9', color: '#475569', border: '#cbd5e1' },
    Received:  { bg: '#dbeafe', color: '#1d4ed8', border: '#93c5fd' },
    'On Hold': { bg: '#fef3c7', color: '#a16207', border: '#fde68a' },
    Posted:    { bg: '#dcfce7', color: '#15803d', border: '#86efac' },
    Cancelled: { bg: '#fee2e2', color: '#b91c1c', border: '#fecaca' },
};

interface GRNLine {
    id: number;
    po_line: number;
    item_description: string;
    quantity_received: string;
    batch_number: string;
    expiry_date: string | null;
    // unit price comes from po_line on the backend; we read it via po_line lookup
}

interface POLine {
    id: number;
    item_description: string;
    unit_price: string;
}

export default function GRNView() {
    const { id } = useParams<{ id: string }>();
    const navigate = useNavigate();
    const { formatCurrency } = useCurrency();
    const [confirmAction, setConfirmAction] = useState<'post' | 'cancel' | null>(null);
    const [toast, setToast] = useState<{ msg: string; ok: boolean } | null>(null);

    const flash = (msg: string, ok = true) => {
        setToast({ msg, ok });
        setTimeout(() => setToast(null), 5000);
    };

    const grnId = id ? Number(id) : null;
    const { data: grn, isLoading, error } = useGRN(grnId);

    const postMutation = usePostGRN();
    const cancelMutation = useCancelGRN();

    const handleAction = (action: 'post' | 'cancel') => {
        if (!grnId) return;
        if (action === 'post') {
            postMutation.mutate(grnId, {
                onSuccess: (resp: any) => {
                    flash(
                        resp?.journal_number
                            ? `GRN posted. Journal: ${resp.journal_number}`
                            : 'GRN posted. Inventory updated.'
                    );
                },
                onError: (err: any) => {
                    flash(
                        err?.response?.data?.error
                            || err?.response?.data?.detail
                            || 'Failed to post GRN',
                        false,
                    );
                },
            });
        } else if (action === 'cancel') {
            cancelMutation.mutate(grnId, {
                onSuccess: () => flash('GRN cancelled.'),
                onError: (err: any) => {
                    flash(
                        err?.response?.data?.error
                            || err?.response?.data?.detail
                            || 'Failed to cancel GRN',
                        false,
                    );
                },
            });
        }
        setConfirmAction(null);
    };

    if (isLoading) return <AccountingLayout><LoadingScreen message="Loading GRN..." /></AccountingLayout>;

    if (error || !grn) {
        return (
            <AccountingLayout>
                <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                    <AlertTriangle size={32} style={{ marginBottom: '1rem' }} />
                    <p>Goods Received Note not found.</p>
                    <button className="btn btn-outline" onClick={() => navigate('/procurement/grn')} style={{ marginTop: '1rem' }}>
                        <ArrowLeft size={14} style={{ marginRight: '0.35rem' }} /> Back to GRN List
                    </button>
                </div>
            </AccountingLayout>
        );
    }

    // Build a po_line_id → unit_price map by reading the embedded GRN response.
    // The serializer doesn't bake unit_price into GRN lines, so we expose it
    // through the line's po_line FK if present (fallback: 0).
    const status = grn.status as string;
    const cfg = statusConfig[status] || statusConfig.Draft;
    const isPosted = status === 'Posted';
    const isCancelled = status === 'Cancelled';
    const canPost = ['Draft', 'Received', 'On Hold'].includes(status);
    const canCancel = !['Posted', 'Cancelled'].includes(status);

    // Lines come back with quantity_received as a string. The serializer
    // also bakes po_line into each GRN line as just the FK id — to render
    // unit price + line totals, we'd need a second fetch of the PO. For
    // the read-only view we render qty + batch + expiry; line-total math
    // is computed on the server during posting.
    const lines: GRNLine[] = (grn.lines as GRNLine[]) || [];
    const totalQty = lines.reduce(
        (s, l) => s + (parseFloat(l.quantity_received) || 0),
        0,
    );

    return (
        <AccountingLayout>
            <PageHeader
                title={`GRN ${grn.grn_number}`}
                subtitle={`Receipt against ${grn.po_number || 'Purchase Order'}`}
                icon={<Package size={22} />}
                onBack={() => navigate('/procurement/grn')}
                actions={
                    <div style={{ display: 'flex', gap: '0.5rem' }}>
                        {canPost && (
                            <button
                                onClick={() => setConfirmAction('post')}
                                disabled={postMutation.isPending}
                                style={{
                                    padding: '0.6rem 1.25rem', fontWeight: 600,
                                    borderRadius: '8px', cursor: 'pointer',
                                    background: '#22c55e', color: 'white',
                                    border: '1px solid rgba(255,255,255,0.25)',
                                    display: 'inline-flex', alignItems: 'center', gap: '0.4rem',
                                }}
                            >
                                <CheckCircle size={16} />
                                {postMutation.isPending ? 'Posting...' : 'Post GRN'}
                            </button>
                        )}
                        {canCancel && (
                            <button
                                onClick={() => setConfirmAction('cancel')}
                                disabled={cancelMutation.isPending}
                                style={{
                                    padding: '0.6rem 1.25rem', fontWeight: 600,
                                    borderRadius: '8px', cursor: 'pointer',
                                    background: 'rgba(255,255,255,0.18)', color: 'white',
                                    border: '1px solid rgba(255,255,255,0.25)',
                                    display: 'inline-flex', alignItems: 'center', gap: '0.4rem',
                                }}
                            >
                                <XCircle size={16} />
                                Cancel GRN
                            </button>
                        )}
                    </div>
                }
            />

            {/* Toast */}
            {toast && (
                <div style={{
                    padding: '0.75rem 1rem', marginBottom: '1.25rem', borderRadius: '8px',
                    background: toast.ok ? '#ecfdf5' : '#fef2f2',
                    border: `1px solid ${toast.ok ? '#a7f3d0' : '#fecaca'}`,
                    color: toast.ok ? '#065f46' : '#991b1b',
                    fontSize: 'var(--text-sm)', display: 'flex', alignItems: 'center', gap: '0.5rem',
                }}>
                    {toast.ok ? <CheckCircle size={16} /> : <AlertTriangle size={16} />}
                    {toast.msg}
                </div>
            )}

            {/* Confirm bar */}
            {confirmAction && (
                <div style={{
                    padding: '0.75rem 1rem', marginBottom: '1.25rem', borderRadius: '8px',
                    background: '#fffbeb', border: '1px solid #fde68a', color: '#92400e',
                    fontSize: 'var(--text-sm)', display: 'flex', alignItems: 'center', gap: '0.75rem',
                    justifyContent: 'space-between',
                }}>
                    <span>
                        {confirmAction === 'post'
                            ? 'Post this GRN? This will update inventory, create the GL journal, and flip the budget commitment to INVOICED.'
                            : 'Cancel this GRN? Any inventory and journal entries will be reversed if it was Posted.'}
                    </span>
                    <div style={{ display: 'flex', gap: '0.5rem' }}>
                        <button onClick={() => handleAction(confirmAction)}
                            style={{ background: '#dc2626', color: 'white', border: 'none', borderRadius: '6px', padding: '6px 14px', cursor: 'pointer', fontWeight: 600 }}>
                            Confirm
                        </button>
                        <button onClick={() => setConfirmAction(null)}
                            style={{ background: '#e2e8f0', border: 'none', borderRadius: '6px', padding: '6px 14px', cursor: 'pointer' }}>
                            No
                        </button>
                    </div>
                </div>
            )}

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: '1.5rem', alignItems: 'start' }}>

                {/* LEFT — main details */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>

                    {/* GRN header card */}
                    <div className="card" style={{ padding: '1.75rem' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '1rem' }}>
                            <div>
                                <div style={{
                                    display: 'inline-flex', alignItems: 'center', gap: '0.4rem',
                                    padding: '0.25rem 0.7rem', borderRadius: '999px',
                                    background: cfg.bg, color: cfg.color, border: `1px solid ${cfg.border}`,
                                    fontSize: 'var(--text-xs)', fontWeight: 700, marginBottom: '0.6rem',
                                }}>
                                    {isPosted ? <CheckCircle size={12} /> : isCancelled ? <XCircle size={12} /> : <FileText size={12} />}
                                    {status}
                                </div>
                                <h2 style={{ margin: 0, fontSize: 'var(--text-lg)', fontWeight: 700 }}>{grn.grn_number}</h2>
                                <p style={{ margin: '0.2rem 0 0', color: 'var(--color-text-muted)', fontSize: 'var(--text-sm)' }}>
                                    {grn.notes || 'No notes'}
                                </p>
                            </div>
                        </div>

                        <div style={{
                            display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '1rem',
                            marginTop: '1.5rem', paddingTop: '1.25rem', borderTop: '1px solid var(--color-border)',
                        }}>
                            <DetailRow icon={<FileText size={14} />} label="Purchase Order" value={grn.po_number} />
                            <DetailRow icon={<Calendar size={14} />} label="Received Date" value={grn.received_date ? new Date(grn.received_date).toLocaleDateString() : '—'} />
                            <DetailRow icon={<User size={14} />} label="Received By" value={grn.received_by || '—'} />
                            <DetailRow
                                icon={<Building2 size={14} />}
                                label="MDA (custodian)"
                                value={grn.mda_code ? `${grn.mda_code} — ${grn.mda_name || ''}` : (grn.mda_name || '—')}
                            />
                            <DetailRow icon={<Truck size={14} />} label="Resolved Warehouse" value={grn.warehouse_name || '—'} />
                            <DetailRow icon={<Layers size={14} />} label="Line count" value={lines.length} />
                        </div>
                    </div>

                    {/* Lines table */}
                    <div className="card" style={{ padding: '1.75rem' }}>
                        <h3 style={{ margin: '0 0 1rem', fontSize: 'var(--text-base)', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                            <Package size={16} color="#4f46e5" />
                            Receipt Lines
                        </h3>
                        {lines.length === 0 ? (
                            <p style={{ color: 'var(--color-text-muted)', fontSize: 'var(--text-sm)' }}>
                                No lines on this GRN.
                            </p>
                        ) : (
                            <div style={{ overflowX: 'auto' }}>
                                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--text-sm)' }}>
                                    <thead>
                                        <tr style={{ borderBottom: '2px solid var(--color-border)' }}>
                                            <th style={th}>Item</th>
                                            <th style={{ ...th, textAlign: 'right', width: 120 }}>Qty Received</th>
                                            <th style={{ ...th, width: 160 }}>Batch / Lot No.</th>
                                            <th style={{ ...th, width: 140 }}>Expiry</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {lines.map((line) => (
                                            <tr key={line.id} style={{ borderBottom: '1px solid var(--color-border)' }}>
                                                <td style={td}>{line.item_description || `PO line #${line.po_line}`}</td>
                                                <td style={{ ...td, textAlign: 'right', fontWeight: 600 }}>{line.quantity_received}</td>
                                                <td style={{ ...td, fontFamily: 'monospace', color: line.batch_number ? 'inherit' : '#94a3b8' }}>
                                                    {line.batch_number || '—'}
                                                </td>
                                                <td style={{ ...td, color: line.expiry_date ? 'inherit' : '#94a3b8' }}>
                                                    {line.expiry_date ? new Date(line.expiry_date).toLocaleDateString() : '—'}
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                    <tfoot>
                                        <tr>
                                            <td style={{ ...td, fontWeight: 700, borderTop: '2px solid var(--color-border)' }}>Total</td>
                                            <td style={{ ...td, textAlign: 'right', fontWeight: 700, borderTop: '2px solid var(--color-border)' }}>{totalQty}</td>
                                            <td colSpan={2} style={{ ...td, borderTop: '2px solid var(--color-border)' }} />
                                        </tr>
                                    </tfoot>
                                </table>
                            </div>
                        )}
                    </div>
                </div>

                {/* RIGHT — posting summary */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
                    <div style={{
                        borderRadius: '12px', padding: '1.75rem',
                        background: isPosted
                            ? 'linear-gradient(135deg, #059669 0%, #10b981 50%, #34d399 100%)'
                            : isCancelled
                                ? 'linear-gradient(135deg, #6b7280 0%, #9ca3af 100%)'
                                : 'linear-gradient(135deg, #4f46e5 0%, #6366f1 100%)',
                        color: '#fff',
                    }}>
                        <p style={{ fontSize: 'var(--text-xs)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: '0.35rem', opacity: 0.85 }}>
                            {isPosted ? 'Posted' : isCancelled ? 'Cancelled' : 'Pending Posting'}
                        </p>
                        <p style={{ fontSize: 'var(--text-2xl)', fontWeight: 800, marginBottom: '0.75rem' }}>
                            {totalQty}
                            <span style={{ fontSize: 'var(--text-sm)', opacity: 0.8, fontWeight: 500, marginLeft: '0.4rem' }}>units</span>
                        </p>
                        <p style={{ fontSize: 'var(--text-xs)', opacity: 0.9, lineHeight: 1.5 }}>
                            {isPosted
                                ? 'Inventory updated, GL journal booked, and the budget commitment is now INVOICED until payment lands.'
                                : isCancelled
                                    ? 'This GRN no longer affects inventory or the budget commitment.'
                                    : 'Click Post GRN above to update inventory, book the GL journal, and flip the commitment to INVOICED.'}
                        </p>
                    </div>

                    {/* What happens on Post */}
                    {!isPosted && !isCancelled && (
                        <div className="card" style={{ padding: '1.25rem' }}>
                            <h4 style={{ margin: '0 0 0.6rem', fontSize: 'var(--text-sm)', fontWeight: 700 }}>
                                What happens on Post
                            </h4>
                            <ul style={{ margin: 0, paddingLeft: '1.1rem', color: 'var(--color-text-muted)', fontSize: 'var(--text-xs)', lineHeight: 1.7 }}>
                                <li>Inventory ItemStock + ItemBatch updated</li>
                                <li>StockMovement (IN) recorded for each line</li>
                                <li>GL journal: DR Inventory / CR GR-IR Clearing</li>
                                <li>Budget commitment moved <strong>ACTIVE → INVOICED</strong></li>
                                <li>Draft VendorInvoice auto-created for AP review</li>
                                <li>If all lines fully received: PO auto-closes</li>
                            </ul>
                        </div>
                    )}
                </div>
            </div>
        </AccountingLayout>
    );
}

// ── Tiny presentational helpers ──────────────────────────────────────────────

const th: React.CSSProperties = {
    padding: '0.5rem 0.5rem 0.75rem', textAlign: 'left',
    fontSize: 'var(--text-xs)', fontWeight: 700, textTransform: 'uppercase',
    letterSpacing: '0.05em', color: 'var(--color-text-muted)', whiteSpace: 'nowrap',
};
const td: React.CSSProperties = {
    padding: '0.6rem 0.5rem', fontSize: 'var(--text-sm)',
};

function DetailRow({ icon, label, value }: { icon: React.ReactNode; label: string; value: string | number }) {
    return (
        <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', color: 'var(--color-text-muted)', fontSize: 'var(--text-xs)', marginBottom: '0.25rem', fontWeight: 600 }}>
                {icon}
                {label}
            </div>
            <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600 }}>
                {value}
            </div>
        </div>
    );
}

// Suppress unused-warning on a placeholder helper kept for future line totals.
void safeMultiply;
