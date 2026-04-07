import { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
    useAccrual, useDeferral,
    useCreateAccrual, useUpdateAccrual,
    useCreateDeferral, useUpdateDeferral,
    useBudgetPeriods,
} from './hooks/useAccrualDeferral';
import { useCurrency } from '../../context/CurrencyContext';
import AccountingLayout from './AccountingLayout';
import PageHeader from '../../components/PageHeader';
import { Save, X, ArrowRightLeft } from 'lucide-react';
import LoadingScreen from '../../components/common/LoadingScreen';

// Simple account selector — pulls from a generic accounts endpoint
import { useQuery } from '@tanstack/react-query';
import apiClient from '../../api/client';

const useAccounts = () => useQuery({
    queryKey: ['accounts-select'],
    queryFn: async () => {
        const { data } = await apiClient.get('/accounting/accounts/', { params: { is_active: true, page_size: 500 } });
        return data.results || data;
    },
    staleTime: 5 * 60 * 1000,
});

const inp: React.CSSProperties = {
    width: '100%', padding: '9px 12px', border: '1.5px solid var(--color-border, #e2e8f0)',
    borderRadius: '8px', fontSize: '13px', boxSizing: 'border-box',
    background: 'var(--color-surface, #fff)', color: 'var(--color-text, #1e293b)',
};
const sel: React.CSSProperties = { ...inp };
const lbl: React.CSSProperties = {
    display: 'block', marginBottom: '5px', fontSize: '11px',
    fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.04em',
};

const AccrualDeferralForm = () => {
    const navigate = useNavigate();
    const { id, type } = useParams();
    const { formatCurrency: fmt } = useCurrency();
    const isEdit = Boolean(id);
    const isAccrual = (type || 'accrual') === 'accrual';

    const { data: accrual, isLoading: aLoading } = useAccrual(Number(id), isEdit && isAccrual);
    const { data: deferral, isLoading: dLoading } = useDeferral(Number(id), isEdit && !isAccrual);
    const { data: periods = [] } = useBudgetPeriods();
    const { data: accounts = [] } = useAccounts();

    const createAccrual = useCreateAccrual();
    const updateAccrual = useUpdateAccrual();
    const createDeferral = useCreateDeferral();
    const updateDeferral = useUpdateDeferral();

    const isLoading = isEdit && (aLoading || dLoading);
    const isPending = createAccrual.isPending || updateAccrual.isPending || createDeferral.isPending || updateDeferral.isPending;
    const [apiError, setApiError] = useState('');

    // ─── Accrual form state ────────────────────────────────────────────────────
    const [aForm, setAForm] = useState({
        name: '', accrual_type: 'expense', account: '', counterpart_account: '',
        amount: '', period: '', posting_date: new Date().toISOString().split('T')[0],
        reversal_date: '', auto_reverse: true, auto_reverse_on_month_start: true,
        use_default_dates: false, description: '', source_document: '',
    });

    // ─── Deferral form state ───────────────────────────────────────────────────
    const [dForm, setDForm] = useState({
        name: '', deferral_type: 'prepaid_expense', account: '', counterpart_account: '',
        original_amount: '', recognition_amount: '', start_date: new Date().toISOString().split('T')[0],
        recognition_periods: '12', auto_recognize: true, auto_recognize_on_month_start: true,
        description: '', source_document: '',
    });

    useEffect(() => {
        if (!isEdit || isLoading) return;
        if (isAccrual && accrual) {
            setAForm({
                name: accrual.name || '',
                accrual_type: accrual.accrual_type || 'expense',
                account: accrual.account?.toString() || '',
                counterpart_account: accrual.counterpart_account?.toString() || '',
                amount: accrual.amount || '',
                period: accrual.period?.toString() || '',
                posting_date: accrual.posting_date || '',
                reversal_date: accrual.reversal_date || '',
                auto_reverse: accrual.auto_reverse ?? true,
                auto_reverse_on_month_start: accrual.auto_reverse_on_month_start ?? true,
                use_default_dates: accrual.use_default_dates ?? false,
                description: accrual.description || '',
                source_document: accrual.source_document || '',
            });
        } else if (!isAccrual && deferral) {
            setDForm({
                name: deferral.name || '',
                deferral_type: deferral.deferral_type || 'prepaid_expense',
                account: deferral.account?.toString() || '',
                counterpart_account: deferral.counterpart_account?.toString() || '',
                original_amount: deferral.original_amount || '',
                recognition_amount: deferral.recognition_amount || '',
                start_date: deferral.start_date || '',
                recognition_periods: deferral.recognition_periods?.toString() || '12',
                auto_recognize: deferral.auto_recognize ?? true,
                auto_recognize_on_month_start: deferral.auto_recognize_on_month_start ?? true,
                description: deferral.description || '',
                source_document: deferral.source_document || '',
            });
        }
    }, [isEdit, isLoading, accrual, deferral, isAccrual]);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setApiError('');
        try {
            if (isAccrual) {
                const payload: any = { ...aForm };
                if (!payload.period) delete payload.period;
                if (!payload.reversal_date) delete payload.reversal_date;
                if (!payload.account) delete payload.account;
                if (!payload.counterpart_account) delete payload.counterpart_account;
                if (isEdit) await updateAccrual.mutateAsync({ id: Number(id), data: payload });
                else await createAccrual.mutateAsync(payload);
            } else {
                const payload: any = { ...dForm };
                if (!payload.account) delete payload.account;
                if (!payload.counterpart_account) delete payload.counterpart_account;
                if (isEdit) await updateDeferral.mutateAsync({ id: Number(id), data: payload });
                else await createDeferral.mutateAsync(payload);
            }
            navigate('/accounting/accruals-deferrals');
        } catch (err: any) {
            const d = err?.response?.data;
            const msg = d?.detail || (d && typeof d === 'object' ? Object.values(d).flat().join(' ') : null) || 'Save failed.';
            setApiError(String(msg));
        }
    };

    if (isEdit && isLoading) return <LoadingScreen message="Loading…" />;

    const sectionHd: React.CSSProperties = {
        fontSize: '12px', fontWeight: 700, color: '#64748b',
        textTransform: 'uppercase', letterSpacing: '0.06em',
        borderBottom: '1.5px solid #e2e8f0', paddingBottom: '8px', marginBottom: '18px',
    };
    const card: React.CSSProperties = {
        background: '#fff', border: '1px solid #e2e8f0', borderRadius: '14px',
        padding: '24px', marginBottom: '20px',
    };
    const grid2: React.CSSProperties = { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px' };
    const grid3: React.CSSProperties = { display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '14px' };
    const chkRow: React.CSSProperties = { display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '13px', color: '#374151' };

    return (
        <AccountingLayout>
            <form onSubmit={handleSubmit}>
                <PageHeader
                    title={isEdit
                        ? `Edit ${isAccrual ? 'Accrual' : 'Deferral'}`
                        : `New ${isAccrual ? 'Accrual' : 'Deferral'}`}
                    subtitle={isAccrual
                        ? 'Record an expense or revenue accrual with optional auto-reversal'
                        : 'Record a prepaid expense or deferred revenue with periodic recognition schedule'}
                    icon={<ArrowRightLeft size={22} />}
                    actions={
                        <div style={{ display: 'flex', gap: '10px' }}>
                            <button type="button" onClick={() => navigate('/accounting/accruals-deferrals')}
                                style={{ padding: '9px 18px', border: '1.5px solid #d1d5db', borderRadius: '8px', background: '#fff', cursor: 'pointer', fontSize: '13px', fontWeight: 600 }}>
                                <X size={15} style={{ verticalAlign: 'middle', marginRight: '4px' }} />Cancel
                            </button>
                            <button type="submit" disabled={isPending}
                                style={{ padding: '9px 20px', border: 'none', borderRadius: '8px', background: 'var(--color-primary, #4f46e5)', color: '#fff', cursor: 'pointer', fontSize: '13px', fontWeight: 600 }}>
                                <Save size={15} style={{ verticalAlign: 'middle', marginRight: '4px' }} />
                                {isPending ? 'Saving…' : isEdit ? 'Update' : 'Create'}
                            </button>
                        </div>
                    }
                />

                {apiError && (
                    <div style={{ background: '#fee2e2', border: '1px solid #fca5a5', borderRadius: '8px', padding: '12px 16px', marginBottom: '16px', color: '#991b1b', fontSize: '13px' }}>
                        {apiError}
                    </div>
                )}

                {/* ─── Basic Info ─── */}
                <div style={card}>
                    <div style={sectionHd}>Basic Information</div>
                    {isAccrual ? (
                        <>
                            <div style={grid3}>
                                <div>
                                    <label style={lbl}>Name *</label>
                                    <input style={inp} required value={aForm.name} onChange={e => setAForm(p => ({ ...p, name: e.target.value }))} placeholder="e.g. March Rent Accrual" />
                                </div>
                                <div>
                                    <label style={lbl}>Type</label>
                                    <select style={sel} value={aForm.accrual_type} onChange={e => setAForm(p => ({ ...p, accrual_type: e.target.value }))}>
                                        <option value="expense">Expense Accrual</option>
                                        <option value="revenue">Revenue Accrual</option>
                                    </select>
                                </div>
                                <div>
                                    <label style={lbl}>Amount *</label>
                                    <input style={inp} type="number" step="0.01" required value={aForm.amount} onChange={e => setAForm(p => ({ ...p, amount: e.target.value }))} placeholder="0.00" />
                                    {aForm.amount && <div style={{ fontSize: '11px', color: '#94a3b8', marginTop: '3px' }}>{fmt(parseFloat(aForm.amount || '0'))}</div>}
                                </div>
                            </div>
                            <div style={{ ...grid2, marginTop: '14px' }}>
                                <div>
                                    <label style={lbl}>{aForm.accrual_type === 'expense' ? 'Expense Account' : 'Revenue Account'} (Dr)</label>
                                    <select style={sel} value={aForm.account} onChange={e => setAForm(p => ({ ...p, account: e.target.value }))}>
                                        <option value="">— Select Account —</option>
                                        {(accounts as any[]).map((a: any) => <option key={a.id} value={a.id}>{a.code} – {a.name}</option>)}
                                    </select>
                                </div>
                                <div>
                                    <label style={lbl}>{aForm.accrual_type === 'expense' ? 'Accrued Liability Account' : 'Accrued Receivable Account'} (Cr)</label>
                                    <select style={sel} value={aForm.counterpart_account} onChange={e => setAForm(p => ({ ...p, counterpart_account: e.target.value }))}>
                                        <option value="">— Select Account —</option>
                                        {(accounts as any[]).map((a: any) => <option key={a.id} value={a.id}>{a.code} – {a.name}</option>)}
                                    </select>
                                </div>
                            </div>
                            <div style={{ ...grid3, marginTop: '14px' }}>
                                <div>
                                    <label style={lbl}>Fiscal Period</label>
                                    <select style={sel} value={aForm.period} onChange={e => setAForm(p => ({ ...p, period: e.target.value }))}>
                                        <option value="">— Select Period —</option>
                                        {(periods as any[]).map((p: any) => <option key={p.id} value={p.id}>FY{p.fiscal_year} – {p.period_type} {p.period_number}</option>)}
                                    </select>
                                </div>
                                <div>
                                    <label style={lbl}>Posting Date *</label>
                                    <input style={inp} type="date" required value={aForm.posting_date} onChange={e => setAForm(p => ({ ...p, posting_date: e.target.value }))} />
                                </div>
                                <div>
                                    <label style={lbl}>Reversal Date</label>
                                    <input style={inp} type="date" value={aForm.reversal_date} onChange={e => setAForm(p => ({ ...p, reversal_date: e.target.value }))} />
                                </div>
                            </div>
                            <div style={{ marginTop: '14px' }}>
                                <label style={lbl}>Description</label>
                                <input style={inp} value={aForm.description} onChange={e => setAForm(p => ({ ...p, description: e.target.value }))} placeholder="Brief description of this accrual" />
                            </div>
                            <div style={{ marginTop: '14px' }}>
                                <label style={lbl}>Source Document</label>
                                <input style={inp} value={aForm.source_document} onChange={e => setAForm(p => ({ ...p, source_document: e.target.value }))} placeholder="e.g. Invoice #INV-2024-001" />
                            </div>
                        </>
                    ) : (
                        <>
                            <div style={grid3}>
                                <div>
                                    <label style={lbl}>Name *</label>
                                    <input style={inp} required value={dForm.name} onChange={e => setDForm(p => ({ ...p, name: e.target.value }))} placeholder="e.g. Prepaid Insurance" />
                                </div>
                                <div>
                                    <label style={lbl}>Type</label>
                                    <select style={sel} value={dForm.deferral_type} onChange={e => setDForm(p => ({ ...p, deferral_type: e.target.value }))}>
                                        <option value="prepaid_expense">Prepaid Expense</option>
                                        <option value="deferred_revenue">Deferred Revenue</option>
                                    </select>
                                </div>
                                <div>
                                    <label style={lbl}>Original Amount *</label>
                                    <input style={inp} type="number" step="0.01" required value={dForm.original_amount} onChange={e => setDForm(p => ({ ...p, original_amount: e.target.value }))} placeholder="0.00" />
                                    {dForm.original_amount && <div style={{ fontSize: '11px', color: '#94a3b8', marginTop: '3px' }}>{fmt(parseFloat(dForm.original_amount || '0'))}</div>}
                                </div>
                            </div>
                            <div style={{ ...grid3, marginTop: '14px' }}>
                                <div>
                                    <label style={lbl}>Recognition Periods</label>
                                    <input style={inp} type="number" min="1" value={dForm.recognition_periods} onChange={e => setDForm(p => ({ ...p, recognition_periods: e.target.value }))} />
                                </div>
                                <div>
                                    <label style={lbl}>Amount Per Period</label>
                                    <input style={inp} type="number" step="0.01" value={dForm.recognition_amount} onChange={e => setDForm(p => ({ ...p, recognition_amount: e.target.value }))} placeholder="Auto-calculated if blank" />
                                    {dForm.recognition_periods && dForm.original_amount && !dForm.recognition_amount && (
                                        <div style={{ fontSize: '11px', color: '#64748b', marginTop: '3px' }}>
                                            ≈ {fmt(parseFloat(dForm.original_amount || '0') / parseFloat(dForm.recognition_periods || '1'))} / period
                                        </div>
                                    )}
                                </div>
                                <div>
                                    <label style={lbl}>Start Date *</label>
                                    <input style={inp} type="date" required value={dForm.start_date} onChange={e => setDForm(p => ({ ...p, start_date: e.target.value }))} />
                                </div>
                            </div>
                            <div style={{ ...grid2, marginTop: '14px' }}>
                                <div>
                                    <label style={lbl}>{dForm.deferral_type === 'prepaid_expense' ? 'Prepaid Asset Account (Cr on recognition)' : 'Deferred Revenue Account (Dr on recognition)'}</label>
                                    <select style={sel} value={dForm.account} onChange={e => setDForm(p => ({ ...p, account: e.target.value }))}>
                                        <option value="">— Select Account —</option>
                                        {(accounts as any[]).map((a: any) => <option key={a.id} value={a.id}>{a.code} – {a.name}</option>)}
                                    </select>
                                </div>
                                <div>
                                    <label style={lbl}>{dForm.deferral_type === 'prepaid_expense' ? 'Expense Account (Dr on recognition)' : 'Revenue Account (Cr on recognition)'}</label>
                                    <select style={sel} value={dForm.counterpart_account} onChange={e => setDForm(p => ({ ...p, counterpart_account: e.target.value }))}>
                                        <option value="">— Select Account —</option>
                                        {(accounts as any[]).map((a: any) => <option key={a.id} value={a.id}>{a.code} – {a.name}</option>)}
                                    </select>
                                </div>
                            </div>
                            <div style={{ marginTop: '14px' }}>
                                <label style={lbl}>Description</label>
                                <input style={inp} value={dForm.description} onChange={e => setDForm(p => ({ ...p, description: e.target.value }))} placeholder="Brief description of this deferral" />
                            </div>
                            <div style={{ marginTop: '14px' }}>
                                <label style={lbl}>Source Document</label>
                                <input style={inp} value={dForm.source_document} onChange={e => setDForm(p => ({ ...p, source_document: e.target.value }))} placeholder="e.g. Contract #CTR-2024-001" />
                            </div>
                        </>
                    )}
                </div>

                {/* ─── Options ─── */}
                <div style={card}>
                    <div style={sectionHd}>Auto-Processing Options</div>
                    {isAccrual ? (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                            <label style={chkRow}>
                                <input type="checkbox" checked={aForm.auto_reverse} onChange={e => setAForm(p => ({ ...p, auto_reverse: e.target.checked }))} />
                                Auto-reverse in next period
                            </label>
                            <label style={chkRow}>
                                <input type="checkbox" checked={aForm.auto_reverse_on_month_start} onChange={e => setAForm(p => ({ ...p, auto_reverse_on_month_start: e.target.checked }))} />
                                Auto-reverse on 1st of next month
                            </label>
                            <label style={chkRow}>
                                <input type="checkbox" checked={aForm.use_default_dates} onChange={e => setAForm(p => ({ ...p, use_default_dates: e.target.checked }))} />
                                Use default dates (posting = month-end, reversal = 1st of next month)
                            </label>
                        </div>
                    ) : (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                            <label style={chkRow}>
                                <input type="checkbox" checked={dForm.auto_recognize} onChange={e => setDForm(p => ({ ...p, auto_recognize: e.target.checked }))} />
                                Auto-recognize each period
                            </label>
                            <label style={chkRow}>
                                <input type="checkbox" checked={dForm.auto_recognize_on_month_start} onChange={e => setDForm(p => ({ ...p, auto_recognize_on_month_start: e.target.checked }))} />
                                Auto-recognize on 1st of each month
                            </label>
                        </div>
                    )}
                </div>
            </form>
        </AccountingLayout>
    );
};

export default AccrualDeferralForm;
