/**
 * TSA Bank Transfer Form — Quot PSE
 * Route: /accounting/tsa-accounts/transfer
 *
 * Atomic transfer of cash between two Treasury Single Accounts.
 *
 * Backend posts a balanced JV (DR target.gl_cash_account /
 * CR source.gl_cash_account) via IPSASJournalService.post_journal so
 * the chokepoint (assert_balanced + invalidate_period_reports +
 * GLBalance roll-up) fires; F()-updates both TreasuryAccount.current_balance
 * rows under select_for_update in pk-order. The frontend's job is to
 * collect the inputs, validate against the source balance, post once,
 * and surface the resulting journal reference + new balances.
 */
import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { Save, ArrowRightLeft, AlertCircle, Wallet } from 'lucide-react';

import Sidebar from '../../components/Sidebar';
import PageHeader from '../../components/PageHeader';
import SearchableSelect from '../../components/SearchableSelect';
import apiClient from '../../api/client';
import { useTSAAccounts } from '../../hooks/useGovForms';
import '../../features/accounting/styles/glassmorphism.css';

// Reuse the same field styling as TSAAccountForm for visual continuity.
const inputStyle: React.CSSProperties = {
    width: '100%', padding: '0.5rem 0.625rem', borderRadius: '6px',
    border: '2.5px solid var(--color-border)', background: 'var(--color-surface)',
    color: 'var(--color-text)', fontSize: 'var(--text-xs)',
};
const lblStyle: React.CSSProperties = {
    display: 'block', fontSize: '0.65rem', fontWeight: 600,
    color: 'var(--color-text-muted)', marginBottom: '0.25rem',
    textTransform: 'uppercase' as const, letterSpacing: '0.04em',
};

interface TSAOption {
    id: number;
    account_number: string;
    account_name: string;
    account_type: string;
    current_balance: string | number;
    is_active: boolean;
    gl_cash_account: number | null;
}

interface TransferResponse {
    status: string;
    journal_id: number;
    journal_reference: string;
    source: { id: number; account_number: string; current_balance: string };
    target: { id: number; account_number: string; current_balance: string };
    amount: string;
}

const NGN = (value: string | number | null | undefined): string => {
    const n = Number(value ?? 0);
    if (!Number.isFinite(n)) return '—';
    return new Intl.NumberFormat('en-NG', {
        style: 'currency',
        currency: 'NGN',
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    }).format(n);
};

const todayISO = (): string => {
    const d = new Date();
    return [
        d.getFullYear(),
        String(d.getMonth() + 1).padStart(2, '0'),
        String(d.getDate()).padStart(2, '0'),
    ].join('-');
};

export default function TSATransferForm() {
    const navigate = useNavigate();
    const qc = useQueryClient();

    const { data: tsaAccountsRaw, isLoading: tsaLoading } = useTSAAccounts();
    const tsaAccounts = useMemo<TSAOption[]>(
        () => (Array.isArray(tsaAccountsRaw) ? tsaAccountsRaw : []),
        [tsaAccountsRaw],
    );

    const [form, setForm] = useState({
        source_tsa_id: '',
        target_tsa_id: '',
        amount: '',
        transfer_date: todayISO(),
        narration: '',
    });
    const [submitting, setSubmitting] = useState(false);
    const [formError, setFormError] = useState('');
    const [result, setResult] = useState<TransferResponse | null>(null);

    const sourceTSA = useMemo(
        () => tsaAccounts.find(t => String(t.id) === form.source_tsa_id) || null,
        [tsaAccounts, form.source_tsa_id],
    );
    const targetTSA = useMemo(
        () => tsaAccounts.find(t => String(t.id) === form.target_tsa_id) || null,
        [tsaAccounts, form.target_tsa_id],
    );

    // Source & target dropdowns are mutually exclusive — picking one
    // hides it from the other so a user can't accidentally route a
    // transfer to/from the same account (the backend rejects it too,
    // but failing client-side is friendlier).
    const sourceOptions = useMemo(
        () =>
            tsaAccounts
                .filter(t => t.is_active && String(t.id) !== form.target_tsa_id)
                .map(t => ({
                    value: String(t.id),
                    label: `${t.account_number} — ${t.account_name} (${t.account_type})`,
                })),
        [tsaAccounts, form.target_tsa_id],
    );
    const targetOptions = useMemo(
        () =>
            tsaAccounts
                .filter(t => t.is_active && String(t.id) !== form.source_tsa_id)
                .map(t => ({
                    value: String(t.id),
                    label: `${t.account_number} — ${t.account_name} (${t.account_type})`,
                })),
        [tsaAccounts, form.source_tsa_id],
    );

    const set = (field: keyof typeof form, value: string): void => {
        setForm(prev => ({ ...prev, [field]: value }));
        // Clear stale post-submit state when the user edits inputs.
        if (formError) setFormError('');
        if (result) setResult(null);
    };

    const amountValue = useMemo(() => {
        if (!form.amount) return null;
        const n = Number(form.amount);
        return Number.isFinite(n) ? n : null;
    }, [form.amount]);

    const sourceBalance = useMemo(() => {
        if (!sourceTSA) return null;
        const n = Number(sourceTSA.current_balance ?? 0);
        return Number.isFinite(n) ? n : 0;
    }, [sourceTSA]);

    const insufficientFunds = useMemo(
        () =>
            sourceBalance !== null &&
            amountValue !== null &&
            amountValue > sourceBalance,
        [sourceBalance, amountValue],
    );

    const missingGL = useMemo(
        () => Boolean(
            (sourceTSA && !sourceTSA.gl_cash_account) ||
            (targetTSA && !targetTSA.gl_cash_account)
        ),
        [sourceTSA, targetTSA],
    );

    const canSubmit =
        Boolean(form.source_tsa_id) &&
        Boolean(form.target_tsa_id) &&
        amountValue !== null &&
        amountValue > 0 &&
        !insufficientFunds &&
        !missingGL &&
        !submitting;

    const handleSubmit = async (e: React.FormEvent): Promise<void> => {
        e.preventDefault();
        setFormError('');
        setResult(null);

        if (!canSubmit) return;

        setSubmitting(true);
        try {
            const payload = {
                source_tsa_id: Number(form.source_tsa_id),
                target_tsa_id: Number(form.target_tsa_id),
                amount: form.amount, // backend coerces via Decimal(str(...))
                transfer_date: form.transfer_date || undefined,
                narration: form.narration || undefined,
            };
            const { data } = await apiClient.post<TransferResponse>(
                '/accounting/tsa-accounts/transfer/',
                payload,
            );
            setResult(data);

            // Bust caches so the TSA list and any cash-position widgets
            // refresh with the new balances. Also invalidate dropdown
            // cache used by useTSAAccounts so subsequent forms see the
            // updated current_balance values.
            qc.invalidateQueries({ queryKey: ['generic-list', '/accounting/tsa-accounts/'] });
            qc.invalidateQueries({ queryKey: ['tsa-accounts-dropdown'] });
            qc.invalidateQueries({ queryKey: ['ipsas-tsa-cash-full'] });

            // Reset only the inputs that should not be reused for a
            // back-to-back transfer; keep date so a sequence of
            // transfers on the same day is one click each.
            setForm(prev => ({
                ...prev,
                source_tsa_id: '',
                target_tsa_id: '',
                amount: '',
                narration: '',
            }));
        } catch (err: unknown) {
            const e = err as {
                response?: { data?: { error?: string; detail?: string } };
                message?: string;
            };
            setFormError(
                e?.response?.data?.error ||
                e?.response?.data?.detail ||
                e?.message ||
                'Transfer failed.',
            );
        } finally {
            setSubmitting(false);
        }
    };

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }}>
                <div style={{ maxWidth: '760px' }}>
                    <PageHeader
                        title="TSA Bank Transfer"
                        subtitle="Move cash between two Treasury Single Accounts. Posts a balanced JV in real time."
                        icon={<ArrowRightLeft size={22} />}
                    />

                    {/* Result banner — shown after a successful post */}
                    {result && (
                        <div
                            role="status"
                            style={{
                                margin: '1rem 0 1.5rem',
                                padding: '0.875rem 1rem',
                                borderRadius: 8,
                                background: 'var(--color-success-bg, #e8f5e9)',
                                border: '1px solid var(--color-success-border, #66bb6a)',
                                color: 'var(--color-success-text, #1b5e20)',
                            }}
                        >
                            <div style={{ fontWeight: 600, marginBottom: 4 }}>
                                Transfer posted — Journal {result.journal_reference}
                            </div>
                            <div style={{ fontSize: '0.85rem' }}>
                                <div>
                                    Source <strong>{result.source.account_number}</strong>{' '}
                                    new balance: <strong>{NGN(result.source.current_balance)}</strong>
                                </div>
                                <div>
                                    Target <strong>{result.target.account_number}</strong>{' '}
                                    new balance: <strong>{NGN(result.target.current_balance)}</strong>
                                </div>
                            </div>
                        </div>
                    )}

                    {/* Error banner */}
                    {formError && (
                        <div
                            role="alert"
                            style={{
                                margin: '1rem 0 1.5rem',
                                padding: '0.875rem 1rem',
                                borderRadius: 8,
                                background: 'var(--color-danger-bg, #ffebee)',
                                border: '1px solid var(--color-danger-border, #ef5350)',
                                color: 'var(--color-danger-text, #b71c1c)',
                                display: 'flex',
                                alignItems: 'flex-start',
                                gap: '0.5rem',
                            }}
                        >
                            <AlertCircle size={16} style={{ flexShrink: 0, marginTop: 2 }} />
                            <div>{formError}</div>
                        </div>
                    )}

                    <form onSubmit={handleSubmit} className="glass-card" style={{ padding: '1.5rem' }}>
                        <div
                            style={{
                                display: 'grid',
                                gridTemplateColumns: '1fr 1fr',
                                gap: '1rem 1.25rem',
                            }}
                        >
                            {/* Source TSA */}
                            <div>
                                <label style={lblStyle}>From TSA Account *</label>
                                <SearchableSelect
                                    value={form.source_tsa_id}
                                    onChange={(v) => set('source_tsa_id', v)}
                                    options={sourceOptions}
                                    placeholder={tsaLoading ? 'Loading…' : 'Select source TSA'}
                                />
                                {sourceTSA && (
                                    <div
                                        style={{
                                            marginTop: '0.4rem',
                                            fontSize: '0.7rem',
                                            color: 'var(--color-text-muted)',
                                            display: 'flex',
                                            alignItems: 'center',
                                            gap: 4,
                                        }}
                                    >
                                        <Wallet size={12} />
                                        <span>
                                            Balance:{' '}
                                            <strong style={{ color: 'var(--color-text)' }}>
                                                {NGN(sourceTSA.current_balance)}
                                            </strong>
                                        </span>
                                    </div>
                                )}
                            </div>

                            {/* Target TSA */}
                            <div>
                                <label style={lblStyle}>To TSA Account *</label>
                                <SearchableSelect
                                    value={form.target_tsa_id}
                                    onChange={(v) => set('target_tsa_id', v)}
                                    options={targetOptions}
                                    placeholder={tsaLoading ? 'Loading…' : 'Select target TSA'}
                                />
                                {targetTSA && (
                                    <div
                                        style={{
                                            marginTop: '0.4rem',
                                            fontSize: '0.7rem',
                                            color: 'var(--color-text-muted)',
                                            display: 'flex',
                                            alignItems: 'center',
                                            gap: 4,
                                        }}
                                    >
                                        <Wallet size={12} />
                                        <span>
                                            Balance:{' '}
                                            <strong style={{ color: 'var(--color-text)' }}>
                                                {NGN(targetTSA.current_balance)}
                                            </strong>
                                        </span>
                                    </div>
                                )}
                            </div>

                            {/* Amount */}
                            <div>
                                <label style={lblStyle}>Amount (NGN) *</label>
                                <input
                                    type="number"
                                    inputMode="decimal"
                                    min="0.01"
                                    step="0.01"
                                    value={form.amount}
                                    onChange={(e) => set('amount', e.target.value)}
                                    placeholder="0.00"
                                    style={{
                                        ...inputStyle,
                                        borderColor: insufficientFunds
                                            ? 'var(--color-danger-border, #ef5350)'
                                            : inputStyle.border?.toString().split(' ').pop(),
                                    }}
                                />
                                {insufficientFunds && (
                                    <div
                                        style={{
                                            marginTop: '0.35rem',
                                            fontSize: '0.7rem',
                                            color: 'var(--color-danger-text, #b71c1c)',
                                        }}
                                    >
                                        Exceeds source balance by{' '}
                                        {NGN((amountValue ?? 0) - (sourceBalance ?? 0))}
                                    </div>
                                )}
                            </div>

                            {/* Transfer Date */}
                            <div>
                                <label style={lblStyle}>Transfer Date</label>
                                <input
                                    type="date"
                                    value={form.transfer_date}
                                    onChange={(e) => set('transfer_date', e.target.value)}
                                    style={inputStyle}
                                />
                            </div>

                            {/* Narration — full width */}
                            <div style={{ gridColumn: '1 / -1' }}>
                                <label style={lblStyle}>Narration</label>
                                <input
                                    type="text"
                                    value={form.narration}
                                    onChange={(e) => set('narration', e.target.value)}
                                    placeholder="Optional — e.g. Top-up for MoH Q2 warrant"
                                    maxLength={255}
                                    style={inputStyle}
                                />
                            </div>
                        </div>

                        {/* Pre-submit warnings */}
                        {missingGL && (
                            <div
                                style={{
                                    marginTop: '1rem',
                                    padding: '0.75rem',
                                    borderRadius: 6,
                                    background: 'var(--color-warning-bg, #fff8e1)',
                                    border: '1px solid var(--color-warning-border, #ffb300)',
                                    color: 'var(--color-warning-text, #6d4c00)',
                                    fontSize: '0.75rem',
                                }}
                            >
                                One or both selected TSAs have no GL Cash Account configured —
                                the transfer journal cannot be posted. Edit the TSA records to
                                assign a gl_cash_account before transferring.
                            </div>
                        )}

                        <div
                            style={{
                                marginTop: '1.5rem',
                                display: 'flex',
                                gap: '0.5rem',
                                justifyContent: 'flex-end',
                            }}
                        >
                            <button
                                type="button"
                                className="btn btn-secondary"
                                onClick={() => navigate('/accounting/tsa-accounts')}
                                disabled={submitting}
                            >
                                Cancel
                            </button>
                            <button
                                type="submit"
                                className="btn btn-primary"
                                disabled={!canSubmit}
                                style={{
                                    display: 'inline-flex',
                                    alignItems: 'center',
                                    gap: '0.4rem',
                                }}
                            >
                                <Save size={14} />
                                {submitting ? 'Posting…' : 'Post Transfer'}
                            </button>
                        </div>
                    </form>
                </div>
            </main>
        </div>
    );
}
