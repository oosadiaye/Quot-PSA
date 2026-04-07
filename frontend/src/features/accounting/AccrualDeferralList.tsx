import { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
    useAccruals, useDeferrals,
    useCreateAccrual, useCreateDeferral,
    usePostAccrual, useReverseAccrual, useDeleteAccrual,
    useRecognizeDeferral, useDeleteDeferral,
} from './hooks/useAccrualDeferral';
import AccountingLayout from './AccountingLayout';
import { useCurrency } from '../../context/CurrencyContext';
import {
    Plus, Play, Undo2, Trash2, Edit2, Clock, CheckCircle2, X,
    AlertTriangle, RotateCcw, TrendingDown, TrendingUp, Layers,
    ChevronRight, ChevronDown, Download, Upload, FileSpreadsheet,
} from 'lucide-react';

// ─── types ─────────────────────────────────────────────────────────────────
type ConfirmAction =
    | { type: 'post'; id: number; name: string }
    | { type: 'reverse'; id: number; name: string }
    | { type: 'recognize'; id: number; name: string }
    | { type: 'delete_accrual'; id: number; name: string }
    | { type: 'delete_deferral'; id: number; name: string }
    | null;

// ─── helpers ────────────────────────────────────────────────────────────────
const badge = (label: string, bg: string, color: string) => (
    <span style={{ background: bg, color, padding: '2px 8px', borderRadius: '99px', fontSize: '11px', fontWeight: 700, whiteSpace: 'nowrap' }}>
        {label}
    </span>
);

const accrualStatusBadge = (a: any) => {
    if (a.is_reversed) return badge('Reversed', '#f1f5f9', '#64748b');
    if (a.is_posted) return badge('Posted', '#dcfce7', '#16a34a');
    return badge('Draft', '#fef9c3', '#ca8a04');
};

const deferralStatusBadge = (d: any) => {
    if (d.is_fully_recognized) return badge('Complete', '#f1f5f9', '#64748b');
    if (!d.is_active) return badge('Inactive', '#fee2e2', '#dc2626');
    return badge('Active', '#dcfce7', '#16a34a');
};

const accrualTypeBadge = (type: string) =>
    type === 'expense'
        ? badge('Expense', 'rgba(239,68,68,0.1)', '#ef4444')
        : badge('Revenue', 'rgba(16,185,129,0.1)', '#10b981');

const deferralTypeBadge = (type: string) =>
    type === 'prepaid_expense'
        ? badge('Prepaid', 'rgba(36,113,163,0.1)', '#2471a3')
        : badge('Deferred Rev.', 'rgba(168,85,247,0.1)', '#a855f7');

const ProgressBar = ({ current, total }: { current: number; total: number }) => {
    const pct = total > 0 ? Math.min(100, (current / total) * 100) : 0;
    return (
        <div style={{ background: '#f1f5f9', borderRadius: '4px', height: '5px', width: '80px', overflow: 'hidden', display: 'inline-block', verticalAlign: 'middle', marginLeft: '6px' }}>
            <div style={{ width: `${pct}%`, height: '100%', background: pct >= 100 ? '#94a3b8' : '#4f46e5', borderRadius: '4px', transition: 'width 0.3s' }} />
        </div>
    );
};

// ─── Stat card ──────────────────────────────────────────────────────────────
const Stat = ({ label, value, sub, color }: { label: string; value: string | number; sub?: string; color?: string }) => (
    <div style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: '12px', padding: '16px 20px' }}>
        <div style={{ fontSize: '11px', fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '6px' }}>{label}</div>
        <div style={{ fontSize: '22px', fontWeight: 800, color: color || '#1e293b', lineHeight: 1 }}>{value}</div>
        {sub && <div style={{ fontSize: '11px', color: '#94a3b8', marginTop: '4px' }}>{sub}</div>}
    </div>
);

// ─── Table styles ────────────────────────────────────────────────────────────
const th: React.CSSProperties = {
    padding: '10px 14px', textAlign: 'left', fontSize: '11px', fontWeight: 700,
    color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.05em',
    borderBottom: '1.5px solid #e2e8f0', whiteSpace: 'nowrap', background: '#f8fafc',
};
const td: React.CSSProperties = { padding: '11px 14px', fontSize: '13px', color: '#374151', borderBottom: '1px solid #f1f5f9', whiteSpace: 'nowrap' };
const iconBtn = (color = '#94a3b8'): React.CSSProperties => ({
    background: 'none', border: 'none', cursor: 'pointer', padding: '4px 6px',
    borderRadius: '6px', color, display: 'inline-flex', alignItems: 'center',
});

// ─── Main component ──────────────────────────────────────────────────────────
const AccrualDeferralList = () => {
    const { formatCurrency: fmt } = useCurrency();
    const navigate = useNavigate();

    const { data: rawAccruals = [], isLoading: aLoading } = useAccruals();
    const { data: rawDeferrals = [], isLoading: dLoading } = useDeferrals();

    const postAccrual = usePostAccrual();
    const reverseAccrual = useReverseAccrual();
    const deleteAccrual = useDeleteAccrual();
    const recognizeDeferral = useRecognizeDeferral();
    const deleteDeferral = useDeleteDeferral();

    const createAccrual = useCreateAccrual();
    const createDeferral = useCreateDeferral();

    const [tab, setTab] = useState<'accruals' | 'deferrals'>('accruals');
    const [typeFilter, setTypeFilter] = useState('all');
    const [statusFilter, setStatusFilter] = useState('all');
    const [confirm, setConfirm] = useState<ConfirmAction>(null);
    const [toast, setToast] = useState<{ msg: string; ok: boolean } | null>(null);
    const [actionsOpen, setActionsOpen] = useState(false);
    const [importing, setImporting] = useState(false);
    const actionsRef = useRef<HTMLDivElement>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);

    useEffect(() => {
        const handleClickOutside = (e: MouseEvent) => {
            if (actionsRef.current && !actionsRef.current.contains(e.target as Node)) setActionsOpen(false);
        };
        document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, []);

    const accruals: any[] = Array.isArray(rawAccruals) ? rawAccruals : [];
    const deferrals: any[] = Array.isArray(rawDeferrals) ? rawDeferrals : [];

    const flash = (msg: string, ok = true) => {
        setToast({ msg, ok });
        setTimeout(() => setToast(null), 3500);
    };

    const handleDownloadTemplate = () => {
        setActionsOpen(false);
        if (tab === 'accruals') {
            const headers = ['name', 'accrual_type', 'account', 'counterpart_account', 'amount', 'posting_date', 'reversal_date', 'auto_reverse', 'description'];
            const sample = ['Monthly rent accrual', 'expense', '50100000', '20100000', '150000.00', '2026-03-31', '2026-04-01', 'true', 'March rent accrual'];
            const csv = [headers.join(','), sample.join(',')].join('\n');
            const blob = new Blob([csv], { type: 'text/csv' });
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url; a.download = 'accrual_bulk_template.csv'; a.click();
            window.URL.revokeObjectURL(url);
        } else {
            const headers = ['name', 'deferral_type', 'account', 'counterpart_account', 'original_amount', 'start_date', 'recognition_periods', 'auto_recognize', 'description'];
            const sample = ['Annual insurance prepaid', 'prepaid_expense', '10300000', '50200000', '1200000.00', '2026-01-01', '12', 'true', 'Prepaid insurance 2026'];
            const csv = [headers.join(','), sample.join(',')].join('\n');
            const blob = new Blob([csv], { type: 'text/csv' });
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url; a.download = 'deferral_bulk_template.csv'; a.click();
            window.URL.revokeObjectURL(url);
        }
    };

    const handleExport = () => {
        setActionsOpen(false);
        const list = tab === 'accruals' ? accruals : deferrals;
        if (!list.length) return;
        let headers: string[];
        let rows: string[];
        if (tab === 'accruals') {
            headers = ['Code', 'Name', 'Type', 'Amount', 'Account', 'Posting Date', 'Reversal Date', 'Auto Reverse', 'Status'];
            rows = list.map((a: any) => [
                a.code, a.name, a.accrual_type, a.amount,
                a.account_code || '', a.posting_date || '', a.reversal_date || '',
                a.auto_reverse ? 'Yes' : 'No',
                a.is_reversed ? 'Reversed' : a.is_posted ? 'Posted' : 'Draft',
            ].map((v: any) => `"${String(v ?? '').replace(/"/g, '""')}"`).join(','));
        } else {
            headers = ['Code', 'Name', 'Type', 'Original Amount', 'Remaining', 'Periods', 'Current Period', 'Start Date', 'Auto Recognize', 'Status'];
            rows = list.map((d: any) => [
                d.code, d.name, d.deferral_type, d.original_amount, d.remaining_amount,
                d.recognition_periods, d.current_period, d.start_date || '',
                d.auto_recognize ? 'Yes' : 'No',
                d.is_fully_recognized ? 'Complete' : d.is_active ? 'Active' : 'Inactive',
            ].map((v: any) => `"${String(v ?? '').replace(/"/g, '""')}"`).join(','));
        }
        const csv = [headers.join(','), ...rows].join('\n');
        const blob = new Blob([csv], { type: 'text/csv' });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url; a.download = `${tab}_${new Date().toISOString().split('T')[0]}.csv`; a.click();
        window.URL.revokeObjectURL(url);
    };

    const handleImportCSV = async (e: React.ChangeEvent<HTMLInputElement>) => {
        setActionsOpen(false);
        const file = e.target.files?.[0];
        if (!file) return;
        setImporting(true);
        try {
            const text = await file.text();
            const lines = text.split('\n').map(l => l.trim()).filter(Boolean);
            if (lines.length < 2) { flash('CSV must have a header row and at least one data row.', false); return; }
            const headers = lines[0].split(',').map(h => h.trim().replace(/^"|"$/g, ''));
            let created = 0;
            let errors = 0;
            for (let i = 1; i < lines.length; i++) {
                const values = lines[i].split(',').map(v => v.trim().replace(/^"|"$/g, ''));
                const row: Record<string, any> = {};
                headers.forEach((h, idx) => { row[h] = values[idx] || ''; });
                try {
                    if (tab === 'accruals') {
                        await createAccrual.mutateAsync({
                            name: row.name,
                            accrual_type: row.accrual_type || 'expense',
                            account: Number(row.account) || undefined,
                            counterpart_account: Number(row.counterpart_account) || undefined,
                            amount: row.amount,
                            posting_date: row.posting_date || null,
                            reversal_date: row.reversal_date || null,
                            auto_reverse: row.auto_reverse === 'true' || row.auto_reverse === 'Yes',
                            description: row.description || '',
                        });
                    } else {
                        await createDeferral.mutateAsync({
                            name: row.name,
                            deferral_type: row.deferral_type || 'prepaid_expense',
                            account: Number(row.account) || undefined,
                            counterpart_account: Number(row.counterpart_account) || undefined,
                            original_amount: row.original_amount,
                            start_date: row.start_date || null,
                            recognition_periods: Number(row.recognition_periods) || 12,
                            auto_recognize: row.auto_recognize === 'true' || row.auto_recognize === 'Yes',
                            description: row.description || '',
                        });
                    }
                    created++;
                } catch { errors++; }
            }
            flash(`Imported ${created} ${tab}${errors > 0 ? `, ${errors} failed` : ''}.`, errors === 0);
        } catch (err) {
            flash('Failed to parse CSV file.', false);
        } finally {
            setImporting(false);
            if (fileInputRef.current) fileInputRef.current.value = '';
        }
    };

    const handleConfirm = async () => {
        if (!confirm) return;
        try {
            switch (confirm.type) {
                case 'post':
                    await postAccrual.mutateAsync(confirm.id);
                    flash(`Accrual "${confirm.name}" posted.`);
                    break;
                case 'reverse':
                    await reverseAccrual.mutateAsync(confirm.id);
                    flash(`Accrual "${confirm.name}" reversed.`);
                    break;
                case 'recognize':
                    await recognizeDeferral.mutateAsync(confirm.id);
                    flash(`Recognition entry created for "${confirm.name}".`);
                    break;
                case 'delete_accrual':
                    await deleteAccrual.mutateAsync(confirm.id);
                    flash(`Accrual deleted.`);
                    break;
                case 'delete_deferral':
                    await deleteDeferral.mutateAsync(confirm.id);
                    flash(`Deferral deleted.`);
                    break;
            }
        } catch (err: any) {
            const d = err?.response?.data;
            const msg = d?.error || d?.detail || 'Action failed.';
            flash(String(msg), false);
        }
        setConfirm(null);
    };

    const isPending = postAccrual.isPending || reverseAccrual.isPending || deleteAccrual.isPending
        || recognizeDeferral.isPending || deleteDeferral.isPending;

    // ─── Filtered lists ──────────────────────────────────────────────────────
    const filteredAccruals = accruals.filter(a => {
        if (typeFilter !== 'all' && a.accrual_type !== typeFilter) return false;
        if (statusFilter === 'draft') return !a.is_posted;
        if (statusFilter === 'posted') return a.is_posted && !a.is_reversed;
        if (statusFilter === 'reversed') return a.is_reversed;
        return true;
    });

    const filteredDeferrals = deferrals.filter(d => {
        if (typeFilter !== 'all' && d.deferral_type !== typeFilter) return false;
        if (statusFilter === 'active') return d.is_active && !d.is_fully_recognized;
        if (statusFilter === 'complete') return d.is_fully_recognized;
        if (statusFilter === 'inactive') return !d.is_active;
        return true;
    });

    // ─── Stats ───────────────────────────────────────────────────────────────
    const totalAccrualAmt = accruals.reduce((s, a) => s + parseFloat(a.amount || '0'), 0);
    const postedCount = accruals.filter(a => a.is_posted && !a.is_reversed).length;
    const pendingReversal = accruals.filter(a => a.is_posted && !a.is_reversed && a.auto_reverse).length;
    const activeDeferrals = deferrals.filter(d => d.is_active && !d.is_fully_recognized).length;
    const totalDeferralRemaining = deferrals.filter(d => d.is_active).reduce((s, d) => s + parseFloat(d.remaining_amount || '0'), 0);

    // ─── Confirm modal config ─────────────────────────────────────────────────
    const confirmConfig = confirm ? {
        post: { title: 'Post Accrual?', body: `Post "${confirm.name}" and create the journal entry in the GL?`, btn: 'Post', danger: false },
        reverse: { title: 'Reverse Accrual?', body: `Create a reversal journal entry for "${confirm.name}"?`, btn: 'Reverse', danger: false },
        recognize: { title: 'Recognize Now?', body: `Create a recognition journal entry for the next period of "${confirm.name}"?`, btn: 'Recognize', danger: false },
        delete_accrual: { title: 'Delete Accrual?', body: `Permanently delete "${confirm.name}"? This cannot be undone.`, btn: 'Delete', danger: true },
        delete_deferral: { title: 'Delete Deferral?', body: `Permanently delete "${confirm.name}"? This cannot be undone.`, btn: 'Delete', danger: true },
    }[confirm.type] : null;

    const tabBtn = (key: 'accruals' | 'deferrals', label: string) => (
        <button key={key} onClick={() => { setTab(key); setTypeFilter('all'); setStatusFilter('all'); }} style={{
            padding: '8px 20px', borderRadius: '8px', border: 'none', cursor: 'pointer', fontSize: '13px', fontWeight: 700,
            background: tab === key ? '#4f46e5' : '#f1f5f9',
            color: tab === key ? '#fff' : '#64748b',
            transition: 'all 0.15s',
        }}>{label}</button>
    );

    const selStyle: React.CSSProperties = { padding: '7px 10px', border: '1.5px solid #e2e8f0', borderRadius: '8px', fontSize: '12px', background: '#fff', color: '#374151', cursor: 'pointer' };

    return (
        <AccountingLayout>
            {/* ─── Toast ──────────────────────────────────────────────────── */}
            {toast && (
                <div style={{
                    position: 'fixed', top: '20px', right: '24px', zIndex: 1100,
                    background: toast.ok ? '#d1fae5' : '#fee2e2',
                    border: `1px solid ${toast.ok ? '#6ee7b7' : '#fca5a5'}`,
                    borderRadius: '10px', padding: '12px 18px', display: 'flex', alignItems: 'center', gap: '10px',
                    color: toast.ok ? '#065f46' : '#991b1b', boxShadow: '0 4px 24px rgba(0,0,0,0.12)',
                    fontSize: '13px', fontWeight: 500, maxWidth: '380px',
                }}>
                    {toast.ok ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />}
                    {toast.msg}
                    <button onClick={() => setToast(null)} style={{ marginLeft: 'auto', background: 'none', border: 'none', cursor: 'pointer', color: 'inherit' }}><X size={14} /></button>
                </div>
            )}

            {/* ─── Header ─────────────────────────────────────────────────── */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '24px' }}>
                <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '4px' }}>
                        <div style={{ width: 36, height: 36, borderRadius: '10px', background: 'rgba(79,70,229,0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                            <Clock size={18} color="#4f46e5" />
                        </div>
                        <h1 style={{ margin: 0, fontSize: '20px', fontWeight: 800, color: '#1e293b' }}>Accruals & Deferrals</h1>
                    </div>
                    <p style={{ margin: 0, fontSize: '13px', color: '#94a3b8', paddingLeft: '46px' }}>
                        Manage expense/revenue accruals and prepaid deferrals with auto-reversal
                    </p>
                </div>
                <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
                    {/* Actions Dropdown */}
                    <div ref={actionsRef} style={{ position: 'relative' }}>
                        <button onClick={() => setActionsOpen(!actionsOpen)} style={{
                            padding: '10px 16px', border: '1.5px solid #e2e8f0', borderRadius: '10px', background: '#fff',
                            color: '#374151', cursor: 'pointer', fontSize: '13px', fontWeight: 600,
                            display: 'flex', alignItems: 'center', gap: '6px',
                        }}>
                            Actions <ChevronDown size={14} style={{ transition: 'transform 0.2s', transform: actionsOpen ? 'rotate(180deg)' : '' }} />
                        </button>
                        {actionsOpen && (
                            <div style={{
                                position: 'absolute', right: 0, top: 'calc(100% + 6px)', minWidth: '230px',
                                background: '#fff', borderRadius: '10px', border: '1px solid #e2e8f0',
                                boxShadow: '0 8px 24px rgba(0,0,0,0.1)', zIndex: 50, overflow: 'hidden',
                            }}>
                                <button onClick={handleDownloadTemplate} style={{
                                    width: '100%', display: 'flex', alignItems: 'center', gap: '10px',
                                    padding: '11px 14px', background: 'none', border: 'none', cursor: 'pointer',
                                    fontSize: '13px', color: '#1e293b', transition: 'background 0.15s',
                                }}
                                    onMouseEnter={e => (e.currentTarget.style.background = '#f8fafc')}
                                    onMouseLeave={e => (e.currentTarget.style.background = 'none')}>
                                    <FileSpreadsheet size={15} color="#4f46e5" />
                                    <div style={{ textAlign: 'left' }}>
                                        <span style={{ fontWeight: 600, display: 'block' }}>Download Template</span>
                                        <span style={{ fontSize: '11px', color: '#94a3b8' }}>CSV for bulk {tab} import</span>
                                    </div>
                                </button>
                                <div style={{ height: '1px', background: '#e2e8f0' }} />
                                <button onClick={() => { setActionsOpen(false); fileInputRef.current?.click(); }} disabled={importing} style={{
                                    width: '100%', display: 'flex', alignItems: 'center', gap: '10px',
                                    padding: '11px 14px', background: 'none', border: 'none', cursor: 'pointer',
                                    fontSize: '13px', color: '#1e293b', transition: 'background 0.15s',
                                    opacity: importing ? 0.5 : 1,
                                }}
                                    onMouseEnter={e => (e.currentTarget.style.background = '#f8fafc')}
                                    onMouseLeave={e => (e.currentTarget.style.background = 'none')}>
                                    <Upload size={15} color="#4f46e5" />
                                    <div style={{ textAlign: 'left' }}>
                                        <span style={{ fontWeight: 600, display: 'block' }}>{importing ? 'Importing…' : 'Import CSV'}</span>
                                        <span style={{ fontSize: '11px', color: '#94a3b8' }}>Bulk create {tab} from file</span>
                                    </div>
                                </button>
                                <div style={{ height: '1px', background: '#e2e8f0' }} />
                                <button onClick={handleExport} style={{
                                    width: '100%', display: 'flex', alignItems: 'center', gap: '10px',
                                    padding: '11px 14px', background: 'none', border: 'none', cursor: 'pointer',
                                    fontSize: '13px', color: '#1e293b', transition: 'background 0.15s',
                                    opacity: (tab === 'accruals' ? accruals : deferrals).length ? 1 : 0.5,
                                    pointerEvents: (tab === 'accruals' ? accruals : deferrals).length ? 'auto' : 'none',
                                }}
                                    onMouseEnter={e => (e.currentTarget.style.background = '#f8fafc')}
                                    onMouseLeave={e => (e.currentTarget.style.background = 'none')}>
                                    <Download size={15} color="#4f46e5" />
                                    <div style={{ textAlign: 'left' }}>
                                        <span style={{ fontWeight: 600, display: 'block' }}>Export {tab === 'accruals' ? 'Accruals' : 'Deferrals'}</span>
                                        <span style={{ fontSize: '11px', color: '#94a3b8' }}>Download as CSV</span>
                                    </div>
                                </button>
                            </div>
                        )}
                    </div>
                    <input ref={fileInputRef} type="file" accept=".csv" style={{ display: 'none' }} onChange={handleImportCSV} />
                    <button onClick={() => navigate(`/accounting/accruals-deferrals/new/${tab === 'accruals' ? 'accrual' : 'deferral'}`)}
                        style={{ padding: '10px 18px', border: 'none', borderRadius: '10px', background: '#4f46e5', color: '#fff', cursor: 'pointer', fontSize: '13px', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '6px', boxShadow: '0 2px 8px rgba(79,70,229,0.25)' }}>
                        <Plus size={16} /> New {tab === 'accruals' ? 'Accrual' : 'Deferral'}
                    </button>
                </div>
            </div>

            {/* ─── Stats ──────────────────────────────────────────────────── */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '12px', marginBottom: '24px' }}>
                <Stat label="Total Accruals" value={accruals.length} sub={fmt(totalAccrualAmt)} />
                <Stat label="Posted" value={postedCount} color="#16a34a" />
                <Stat label="Pending Reversal" value={pendingReversal} color={pendingReversal > 0 ? '#d97706' : '#94a3b8'} />
                <Stat label="Active Deferrals" value={activeDeferrals} color="#4f46e5" />
                <Stat label="Remaining Balance" value={fmt(totalDeferralRemaining)} sub={`across ${deferrals.length} deferral${deferrals.length !== 1 ? 's' : ''}`} />
            </div>

            {/* ─── Tabs ───────────────────────────────────────────────────── */}
            <div style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: '14px', overflow: 'hidden' }}>
                {/* Tab bar + filters */}
                <div style={{ padding: '16px 20px', background: '#fafbfc', borderBottom: '1px solid #e2e8f0', display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
                    <div style={{ display: 'flex', gap: '6px' }}>
                        {tabBtn('accruals', `Accruals (${accruals.length})`)}
                        {tabBtn('deferrals', `Deferrals (${deferrals.length})`)}
                    </div>
                    <div style={{ marginLeft: 'auto', display: 'flex', gap: '8px', alignItems: 'center' }}>
                        <select style={selStyle} value={typeFilter} onChange={e => setTypeFilter(e.target.value)}>
                            <option value="all">All Types</option>
                            {tab === 'accruals' ? (
                                <>
                                    <option value="expense">Expense</option>
                                    <option value="revenue">Revenue</option>
                                </>
                            ) : (
                                <>
                                    <option value="prepaid_expense">Prepaid Expense</option>
                                    <option value="deferred_revenue">Deferred Revenue</option>
                                </>
                            )}
                        </select>
                        <select style={selStyle} value={statusFilter} onChange={e => setStatusFilter(e.target.value)}>
                            <option value="all">All Statuses</option>
                            {tab === 'accruals' ? (
                                <>
                                    <option value="draft">Draft</option>
                                    <option value="posted">Posted</option>
                                    <option value="reversed">Reversed</option>
                                </>
                            ) : (
                                <>
                                    <option value="active">Active</option>
                                    <option value="complete">Complete</option>
                                    <option value="inactive">Inactive</option>
                                </>
                            )}
                        </select>
                    </div>
                </div>

                {/* ─── Accruals tab ─────────────────────────────────────── */}
                {tab === 'accruals' && (
                    aLoading ? (
                        <div style={{ padding: '60px', textAlign: 'center', color: '#94a3b8' }}>Loading accruals…</div>
                    ) : filteredAccruals.length === 0 ? (
                        <div style={{ padding: '60px', textAlign: 'center', color: '#94a3b8' }}>
                            <TrendingUp size={40} color="#e2e8f0" style={{ marginBottom: '12px', display: 'block', margin: '0 auto 12px' }} />
                            <p style={{ margin: 0, fontSize: '13px' }}>No accruals found. <button onClick={() => navigate('/accounting/accruals-deferrals/new/accrual')} style={{ background: 'none', border: 'none', color: '#4f46e5', cursor: 'pointer', fontWeight: 600, fontSize: '13px' }}>Create one <ChevronRight size={12} style={{ verticalAlign: 'middle' }} /></button></p>
                        </div>
                    ) : (
                        <div style={{ overflowX: 'auto' }}>
                            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                                <thead>
                                    <tr>
                                        {['Code', 'Name', 'Type', 'Amount', 'Account', 'Posting Date', 'Reversal Date', 'Auto', 'Status', 'Actions'].map(h => (
                                            <th key={h} style={th}>{h}</th>
                                        ))}
                                    </tr>
                                </thead>
                                <tbody>
                                    {filteredAccruals.map((a: any) => (
                                        <tr key={a.id} style={{ transition: 'background 0.1s' }}
                                            onMouseEnter={e => (e.currentTarget.style.background = '#f8fafc')}
                                            onMouseLeave={e => (e.currentTarget.style.background = '')}>
                                            <td style={td}><span style={{ fontFamily: 'monospace', fontSize: '11px', color: '#64748b' }}>{a.code}</span></td>
                                            <td style={{ ...td, maxWidth: '180px', overflow: 'hidden', textOverflow: 'ellipsis', fontWeight: 600, color: '#1e293b' }}>{a.name}</td>
                                            <td style={td}>{accrualTypeBadge(a.accrual_type)}</td>
                                            <td style={{ ...td, textAlign: 'right', fontWeight: 700 }}>{fmt(parseFloat(a.amount || '0'))}</td>
                                            <td style={{ ...td, fontSize: '11px', color: '#64748b' }}>
                                                {a.account_code ? <span><span style={{ fontFamily: 'monospace' }}>{a.account_code}</span> {a.account_name}</span> : '—'}
                                            </td>
                                            <td style={td}>{a.posting_date || '—'}</td>
                                            <td style={td}>{a.reversal_date || '—'}</td>
                                            <td style={td}>{a.auto_reverse ? <span style={{ color: '#4f46e5', fontSize: '11px', fontWeight: 700 }}>Auto</span> : '—'}</td>
                                            <td style={td}>{accrualStatusBadge(a)}</td>
                                            <td style={{ ...td, whiteSpace: 'nowrap' }}>
                                                <div style={{ display: 'flex', gap: '2px' }}>
                                                    {!a.is_posted && (
                                                        <button title="Post" style={iconBtn('#16a34a')}
                                                            onClick={() => setConfirm({ type: 'post', id: a.id, name: a.name })}>
                                                            <Play size={14} />
                                                        </button>
                                                    )}
                                                    {a.is_posted && !a.is_reversed && (
                                                        <button title="Reverse" style={iconBtn('#d97706')}
                                                            onClick={() => setConfirm({ type: 'reverse', id: a.id, name: a.name })}>
                                                            <Undo2 size={14} />
                                                        </button>
                                                    )}
                                                    <button title="Edit" style={iconBtn('#64748b')}
                                                        onClick={() => navigate(`/accounting/accruals-deferrals/accrual/${a.id}`)}>
                                                        <Edit2 size={14} />
                                                    </button>
                                                    {!a.is_posted && (
                                                        <button title="Delete" style={iconBtn('#ef4444')}
                                                            onClick={() => setConfirm({ type: 'delete_accrual', id: a.id, name: a.name })}>
                                                            <Trash2 size={14} />
                                                        </button>
                                                    )}
                                                </div>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )
                )}

                {/* ─── Deferrals tab ────────────────────────────────────── */}
                {tab === 'deferrals' && (
                    dLoading ? (
                        <div style={{ padding: '60px', textAlign: 'center', color: '#94a3b8' }}>Loading deferrals…</div>
                    ) : filteredDeferrals.length === 0 ? (
                        <div style={{ padding: '60px', textAlign: 'center', color: '#94a3b8' }}>
                            <TrendingDown size={40} color="#e2e8f0" style={{ marginBottom: '12px', display: 'block', margin: '0 auto 12px' }} />
                            <p style={{ margin: 0, fontSize: '13px' }}>No deferrals found. <button onClick={() => navigate('/accounting/accruals-deferrals/new/deferral')} style={{ background: 'none', border: 'none', color: '#4f46e5', cursor: 'pointer', fontWeight: 600, fontSize: '13px' }}>Create one <ChevronRight size={12} style={{ verticalAlign: 'middle' }} /></button></p>
                        </div>
                    ) : (
                        <div style={{ overflowX: 'auto' }}>
                            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                                <thead>
                                    <tr>
                                        {['Code', 'Name', 'Type', 'Original', 'Remaining', 'Progress', 'Start Date', 'Auto', 'Status', 'Actions'].map(h => (
                                            <th key={h} style={th}>{h}</th>
                                        ))}
                                    </tr>
                                </thead>
                                <tbody>
                                    {filteredDeferrals.map((d: any) => {
                                        const original = parseFloat(d.original_amount || '0');
                                        const remaining = parseFloat(d.remaining_amount || '0');
                                        const recognized = original - remaining;
                                        const pct = original > 0 ? Math.round((recognized / original) * 100) : 0;
                                        return (
                                            <tr key={d.id}
                                                onMouseEnter={e => (e.currentTarget.style.background = '#f8fafc')}
                                                onMouseLeave={e => (e.currentTarget.style.background = '')}>
                                                <td style={td}><span style={{ fontFamily: 'monospace', fontSize: '11px', color: '#64748b' }}>{d.code}</span></td>
                                                <td style={{ ...td, maxWidth: '180px', overflow: 'hidden', textOverflow: 'ellipsis', fontWeight: 600, color: '#1e293b' }}>{d.name}</td>
                                                <td style={td}>{deferralTypeBadge(d.deferral_type)}</td>
                                                <td style={{ ...td, textAlign: 'right', fontWeight: 700 }}>{fmt(original)}</td>
                                                <td style={{ ...td, textAlign: 'right', color: remaining > 0 ? '#1e293b' : '#94a3b8' }}>{fmt(remaining)}</td>
                                                <td style={td}>
                                                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                                                        <span style={{ fontSize: '11px', color: '#64748b', fontWeight: 600, minWidth: '32px' }}>{pct}%</span>
                                                        <ProgressBar current={d.current_period} total={d.recognition_periods} />
                                                        <span style={{ fontSize: '11px', color: '#94a3b8' }}>{d.current_period}/{d.recognition_periods}</span>
                                                    </div>
                                                </td>
                                                <td style={td}>{d.start_date || '—'}</td>
                                                <td style={td}>{d.auto_recognize ? <span style={{ color: '#4f46e5', fontSize: '11px', fontWeight: 700 }}>Auto</span> : '—'}</td>
                                                <td style={td}>{deferralStatusBadge(d)}</td>
                                                <td style={{ ...td, whiteSpace: 'nowrap' }}>
                                                    <div style={{ display: 'flex', gap: '2px' }}>
                                                        {d.is_active && !d.is_fully_recognized && (
                                                            <button title="Recognize next period" style={iconBtn('#4f46e5')}
                                                                onClick={() => setConfirm({ type: 'recognize', id: d.id, name: d.name })}>
                                                                <RotateCcw size={14} />
                                                            </button>
                                                        )}
                                                        <button title="Edit" style={iconBtn('#64748b')}
                                                            onClick={() => navigate(`/accounting/accruals-deferrals/deferral/${d.id}`)}>
                                                            <Edit2 size={14} />
                                                        </button>
                                                        {!d.is_active || d.is_fully_recognized ? (
                                                            <button title="Delete" style={iconBtn('#ef4444')}
                                                                onClick={() => setConfirm({ type: 'delete_deferral', id: d.id, name: d.name })}>
                                                                <Trash2 size={14} />
                                                            </button>
                                                        ) : null}
                                                    </div>
                                                </td>
                                            </tr>
                                        );
                                    })}
                                </tbody>
                            </table>

                            {/* Deferral recognitions summary footer */}
                            <div style={{ padding: '12px 20px', background: '#fafbfc', borderTop: '1px solid #e2e8f0', display: 'flex', gap: '20px', fontSize: '12px', color: '#64748b' }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><Layers size={13} />{deferrals.length} total</div>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#16a34a' }}><CheckCircle2 size={13} />{deferrals.filter(d => d.is_fully_recognized).length} complete</div>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#4f46e5' }}><Clock size={13} />{activeDeferrals} active</div>
                                <div style={{ marginLeft: 'auto', fontWeight: 700, color: '#1e293b' }}>
                                    Total remaining: {fmt(totalDeferralRemaining)}
                                </div>
                            </div>
                        </div>
                    )
                )}
            </div>

            {/* ─── Confirm modal ──────────────────────────────────────────── */}
            {confirm && confirmConfig && (
                <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <div style={{ background: '#fff', borderRadius: '16px', padding: '28px', width: '420px', boxShadow: '0 25px 60px rgba(0,0,0,0.2)' }}>
                        <h3 style={{ margin: '0 0 10px', fontSize: '16px', fontWeight: 700, color: '#1e293b' }}>{confirmConfig.title}</h3>
                        <p style={{ margin: '0 0 24px', fontSize: '13px', color: '#64748b', lineHeight: 1.6 }}>{confirmConfig.body}</p>
                        <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
                            <button onClick={() => setConfirm(null)} style={{ padding: '9px 18px', borderRadius: '8px', border: '1.5px solid #d1d5db', background: '#fff', cursor: 'pointer', fontSize: '13px', fontWeight: 600 }}>Cancel</button>
                            <button onClick={handleConfirm} disabled={isPending} style={{
                                padding: '9px 20px', borderRadius: '8px', border: 'none', cursor: 'pointer', fontSize: '13px', fontWeight: 700,
                                background: confirmConfig.danger ? '#dc2626' : '#4f46e5', color: '#fff',
                                opacity: isPending ? 0.7 : 1,
                            }}>
                                {isPending ? 'Processing…' : confirmConfig.btn}
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </AccountingLayout>
    );
};

export default AccrualDeferralList;
