/**
 * Virement (Budget Transfer) — Quot PSE
 * Route: /budget/virements/new
 *
 * Move approved budget between two existing Appropriation lines within
 * the same fiscal year. The source must have enough available balance
 * (approved − committed − expended − direct disbursements). No net
 * change to the total envelope, so only administrative sign-off is
 * needed (not legislative).
 */
import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
    X, AlertCircle, ArrowLeftRight, ArrowRight, CheckCircle2, Send, Info,
} from 'lucide-react';
import apiClient from '../../api/client';
import Sidebar from '../../components/Sidebar';
import PageHeader from '../../components/PageHeader';
import SearchableSelect from '../../components/SearchableSelect';
import { useAppropriationsList } from '../../hooks/useGovForms';
import '../../features/accounting/styles/glassmorphism.css';

interface AppropriationRow {
    id: number;
    status: string;
    fiscal_year: number;
    administrative: number;
    administrative_code: string;
    administrative_name: string;
    economic: number;
    economic_code: string;
    economic_name: string;
    fund: number;
    fund_code: string;
    fund_name: string;
    amount_approved: string;
    available_balance: string;
    total_committed: string;
    total_expended: string;
}

function fmtNGN(v: string | number | null | undefined): string {
    const n = typeof v === 'string' ? parseFloat(v) : (v ?? 0);
    if (!Number.isFinite(n)) return '0.00';
    return n.toLocaleString('en-NG', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export default function VirementForm() {
    const navigate = useNavigate();
    const qc = useQueryClient();
    const { data: appropriations = [] } = useAppropriationsList();

    const [fromId, setFromId] = useState<string>('');
    const [toId, setToId] = useState<string>('');
    const [amount, setAmount] = useState<string>('');
    const [reason, setReason] = useState<string>('');
    const [formError, setFormError] = useState('');
    const [saveSuccess, setSaveSuccess] = useState('');

    const from: AppropriationRow | undefined = useMemo(
        () => (appropriations as AppropriationRow[]).find(a => String(a.id) === fromId),
        [appropriations, fromId],
    );
    const to: AppropriationRow | undefined = useMemo(
        () => (appropriations as AppropriationRow[]).find(a => String(a.id) === toId),
        [appropriations, toId],
    );

    // When source is chosen, restrict targets to the SAME fiscal year (virement
    // cannot cross fiscal years — that's a Supplementary, not a virement).
    const targetOptions = useMemo(() => {
        if (!from) return appropriations as AppropriationRow[];
        return (appropriations as AppropriationRow[]).filter(
            a => a.id !== from.id && a.fiscal_year === from.fiscal_year,
        );
    }, [appropriations, from]);

    const amountNum = parseFloat(amount) || 0;
    const fromAvailable = parseFloat(from?.available_balance || '0');
    const overDraw = amountNum > 0 && amountNum > fromAvailable;

    const createVirement = useMutation({
        mutationFn: async (payload: Record<string, any>) => {
            const { data } = await apiClient.post('/budget/virements/', payload);
            return data;
        },
    });

    const submitVirement = useMutation({
        mutationFn: async (id: number) => {
            const { data } = await apiClient.post(`/budget/virements/${id}/submit/`);
            return data;
        },
    });

    const approveVirement = useMutation({
        mutationFn: async (id: number) => {
            const { data } = await apiClient.post(`/budget/virements/${id}/approve/`);
            return data;
        },
    });

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setFormError(''); setSaveSuccess('');

        if (!from || !to) { setFormError('Source and target appropriation are required.'); return; }
        if (from.id === to.id) { setFormError('Source and target must be different.'); return; }
        if (from.fiscal_year !== to.fiscal_year) {
            setFormError('Virement must be within the same fiscal year.');
            return;
        }
        if (amountNum <= 0) { setFormError('Amount must be positive.'); return; }
        if (overDraw) {
            setFormError(`Source has only NGN ${fmtNGN(fromAvailable)} available.`);
            return;
        }
        if (!reason.trim() || reason.trim().length < 10) {
            setFormError('Please provide a business justification (at least 10 characters).');
            return;
        }

        try {
            const created = await createVirement.mutateAsync({
                from_appropriation: from.id,
                to_appropriation: to.id,
                amount: amount,
                reason: reason,
            });
            await submitVirement.mutateAsync(created.id);
            await approveVirement.mutateAsync(created.id);
            qc.invalidateQueries({ queryKey: ['appropriations-dropdown'] });
            setSaveSuccess(
                `Virement ${created.reference_number} applied: NGN ${fmtNGN(amount)} ` +
                `transferred from ${from.administrative_code}/${from.economic_code} ` +
                `to ${to.administrative_code}/${to.economic_code}.`,
            );
            setTimeout(() => navigate('/budget/appropriations'), 2500);
        } catch (err: any) {
            const d = err.response?.data;
            const msg = d?.detail
                || d?.non_field_errors?.[0]
                || d?.amount?.[0]
                || d?.to_appropriation?.[0]
                || JSON.stringify(d)
                || 'Virement failed';
            setFormError(msg);
        }
    };

    const labelStyle: React.CSSProperties = {
        display: 'block', marginBottom: '0.5rem', fontSize: 'var(--text-xs)',
        fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)',
    };
    const helpStyle: React.CSSProperties = {
        fontSize: '11px', color: 'var(--color-text-muted)', marginTop: '4px',
    };

    const fromOpts = (appropriations as AppropriationRow[])
        .filter(a => a.status === 'ACTIVE')
        .map(a => ({
            value: String(a.id),
            label: `${a.administrative_code}/${a.economic_code}/${a.fund_code}`,
            sublabel: `${a.economic_name} — available NGN ${fmtNGN(a.available_balance)}`,
        }));
    const toOpts = targetOptions
        .filter(a => a.status === 'ACTIVE')
        .map(a => ({
            value: String(a.id),
            label: `${a.administrative_code}/${a.economic_code}/${a.fund_code}`,
            sublabel: `${a.economic_name} — current NGN ${fmtNGN(a.amount_approved)}`,
        }));

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }}>
              <form onSubmit={handleSubmit}>
                <PageHeader
                    title="Virement (Budget Transfer)"
                    subtitle="Transfer approved budget between two Appropriation lines within the same fiscal year"
                    icon={<ArrowLeftRight size={22} />}
                    backButton={true}
                    actions={
                        <>
                            <button type="button" className="btn btn-outline" onClick={() => navigate(-1)}>
                                <X size={18} /> Cancel
                            </button>
                            <button
                                type="submit"
                                className="btn btn-primary"
                                disabled={
                                    createVirement.isPending
                                    || submitVirement.isPending
                                    || approveVirement.isPending
                                    || !from || !to || !amount || overDraw
                                }
                            >
                                <Send size={18} /> Submit & Apply Virement
                            </button>
                        </>
                    }
                />

                {formError && (
                    <div style={{
                        padding: '0.75rem 1rem', borderRadius: '8px', marginBottom: '1rem',
                        background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.25)',
                        color: '#b91c1c', fontSize: 'var(--text-sm)',
                        display: 'flex', alignItems: 'flex-start', gap: '0.5rem',
                    }}>
                        <AlertCircle size={15} style={{ marginTop: 2, flexShrink: 0 }} /> {formError}
                    </div>
                )}
                {saveSuccess && (
                    <div style={{
                        padding: '0.75rem 1rem', borderRadius: '8px', marginBottom: '1rem',
                        background: 'rgba(34,197,94,0.08)', border: '1px solid rgba(34,197,94,0.25)',
                        color: '#166534', fontSize: 'var(--text-sm)',
                        display: 'flex', alignItems: 'center', gap: '0.5rem',
                    }}>
                        <CheckCircle2 size={15} /> {saveSuccess}
                    </div>
                )}

                <div className="glass-card" style={{
                    padding: '0.75rem 1rem', marginBottom: '1rem',
                    background: 'rgba(59,130,246,0.06)', border: '1px solid rgba(59,130,246,0.2)',
                    color: '#1e40af', fontSize: 'var(--text-sm)',
                    display: 'flex', alignItems: 'flex-start', gap: '0.5rem',
                }}>
                    <Info size={15} style={{ marginTop: 2 }} />
                    <div>
                        Virement moves approved budget between lines <b>within the same fiscal year</b>.
                        The source's ceiling drops, the target's rises — the total envelope is
                        unchanged. Source <b>available balance</b> (approved − committed − expended)
                        must cover the transfer amount.
                    </div>
                </div>

                {/* From / To pickers */}
                    <div className="card" style={{ marginBottom: '1.5rem' }}>
                        <h3 style={{ marginBottom: '1.5rem' }}>Transfer Lines</h3>
                        <div style={{
                            display: 'grid', gridTemplateColumns: '1fr 60px 1fr',
                            gap: '1rem', alignItems: 'end',
                        }}>
                            <div>
                                <label style={labelStyle}>From Appropriation<span className="required-mark"> *</span></label>
                                <SearchableSelect
                                    options={fromOpts}
                                    value={fromId}
                                    onChange={v => { setFromId(v); if (v === toId) setToId(''); }}
                                    placeholder="Pick source appropriation..."
                                />
                                {from && (
                                    <div style={{
                                        marginTop: '0.5rem', padding: '0.5rem 0.75rem',
                                        background: 'var(--color-surface-muted, rgba(0,0,0,0.03))',
                                        borderRadius: '6px', fontSize: 'var(--text-xs)',
                                        lineHeight: 1.5,
                                    }}>
                                        <div style={{ color: 'var(--color-text-muted)' }}>{from.economic_name}</div>
                                        <div>FY <b>{from.fiscal_year}</b> • Approved <b>NGN {fmtNGN(from.amount_approved)}</b></div>
                                        <div>Committed NGN {fmtNGN(from.total_committed)} • Expended NGN {fmtNGN(from.total_expended)}</div>
                                        <div style={{
                                            marginTop: '0.25rem', fontWeight: 600,
                                            color: fromAvailable > 0 ? '#166534' : '#b91c1c',
                                        }}>
                                            Available: NGN {fmtNGN(fromAvailable)}
                                        </div>
                                    </div>
                                )}
                            </div>

                            <div style={{
                                textAlign: 'center', padding: '0 0 0.5rem 0',
                                color: 'var(--color-primary)',
                            }}>
                                <ArrowRight size={28} />
                            </div>

                            <div>
                                <label style={labelStyle}>To Appropriation<span className="required-mark"> *</span></label>
                                <SearchableSelect
                                    options={toOpts}
                                    value={toId}
                                    onChange={setToId}
                                    placeholder={from ? 'Pick target appropriation...' : 'Pick source first'}
                                />
                                {to && (
                                    <div style={{
                                        marginTop: '0.5rem', padding: '0.5rem 0.75rem',
                                        background: 'var(--color-surface-muted, rgba(0,0,0,0.03))',
                                        borderRadius: '6px', fontSize: 'var(--text-xs)',
                                        lineHeight: 1.5,
                                    }}>
                                        <div style={{ color: 'var(--color-text-muted)' }}>{to.economic_name}</div>
                                        <div>FY <b>{to.fiscal_year}</b> • Current approved <b>NGN {fmtNGN(to.amount_approved)}</b></div>
                                        <div>Committed NGN {fmtNGN(to.total_committed)} • Expended NGN {fmtNGN(to.total_expended)}</div>
                                        {amountNum > 0 && !overDraw && (
                                            <div style={{ marginTop: '0.25rem', fontWeight: 600, color: '#166534' }}>
                                                After virement: NGN {fmtNGN(parseFloat(to.amount_approved) + amountNum)}
                                            </div>
                                        )}
                                    </div>
                                )}
                            </div>
                        </div>
                    </div>

                    {/* Amount + reason */}
                    <div className="card" style={{ marginBottom: '1.5rem' }}>
                        <h3 style={{ marginBottom: '1.5rem' }}>Amount & Justification</h3>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: '1.5rem' }}>
                            <div>
                                <label style={labelStyle}>Amount (NGN)<span className="required-mark"> *</span></label>
                                <input
                                    type="number" step="0.01" min="0"
                                    className="input"
                                    value={amount}
                                    onChange={e => setAmount(e.target.value)}
                                    style={{
                                        textAlign: 'right',
                                        borderColor: overDraw ? '#ef4444' : undefined,
                                    }}
                                    placeholder="0.00"
                                />
                                {overDraw && (
                                    <p style={{ ...helpStyle, color: '#b91c1c' }}>
                                        Exceeds available NGN {fmtNGN(fromAvailable)}
                                    </p>
                                )}
                            </div>
                            <div>
                                <label style={labelStyle}>Reason / Justification<span className="required-mark"> *</span></label>
                                <textarea
                                    className="input"
                                    value={reason}
                                    onChange={e => setReason(e.target.value)}
                                    placeholder="Business justification — required for audit (minimum 10 characters)."
                                    style={{ minHeight: 80, resize: 'vertical', width: '100%' }}
                                />
                            </div>
                        </div>
                    </div>
              </form>
            </main>
        </div>
    );
}
