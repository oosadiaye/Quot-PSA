import { useState, useEffect } from 'react';
import { Hash, Sprout, Save, Loader2 } from 'lucide-react';
import PageHeader from '../../components/PageHeader';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '../../api/client';
import SettingsLayout from './SettingsLayout';
import GlassCard from '../accounting/components/shared/GlassCard';
import '../accounting/styles/glassmorphism.css';

interface AccountingSettingsData {
    id: number;
    account_code_digits: number;
    is_digit_enforcement_active: boolean;
}

interface SeedResult {
    success: boolean;
    created: number;
    skipped: number;
    total_seed: number;
}

const SETTINGS_URL = '/accounting/settings/';
const SEED_URL = '/accounting/settings/seed-coa/';

export default function AccountingSettingsPage() {
    const queryClient = useQueryClient();
    const [digits, setDigits] = useState(8);
    const [enforced, setEnforced] = useState(false);
    const [saveMsg, setSaveMsg] = useState('');
    const [seedResult, setSeedResult] = useState<SeedResult | null>(null);

    const { data: settings, isLoading } = useQuery<AccountingSettingsData>({
        queryKey: ['accounting-settings'],
        queryFn: async () => {
            const res = await apiClient.get(SETTINGS_URL);
            return res.data;
        },
    });

    useEffect(() => {
        if (settings) {
            setDigits(settings.account_code_digits);
            setEnforced(settings.is_digit_enforcement_active);
        }
    }, [settings]);

    const saveMutation = useMutation({
        mutationFn: async () => {
            const res = await apiClient.put(SETTINGS_URL, {
                account_code_digits: digits,
                is_digit_enforcement_active: enforced,
            });
            return res.data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['accounting-settings'] });
            setSaveMsg('Settings saved successfully.');
            setTimeout(() => setSaveMsg(''), 3000);
        },
        onError: () => {
            setSaveMsg('Failed to save settings.');
            setTimeout(() => setSaveMsg(''), 3000);
        },
    });

    const seedMutation = useMutation({
        mutationFn: async () => {
            const res = await apiClient.post(SEED_URL);
            return res.data as SeedResult;
        },
        onSuccess: (data) => {
            setSeedResult(data);
            queryClient.invalidateQueries({ queryKey: ['accounts'] });
        },
        onError: () => {
            setSeedResult(null);
        },
    });

    const previewCodes = [
        { prefix: '1', label: 'Assets', example: '1' + '001'.padEnd(digits - 1, '0').slice(0, digits - 1) },
        { prefix: '2', label: 'Liabilities', example: '2' + '001'.padEnd(digits - 1, '0').slice(0, digits - 1) },
        { prefix: '3', label: 'Equity', example: '3' + '001'.padEnd(digits - 1, '0').slice(0, digits - 1) },
        { prefix: '4', label: 'Income', example: '4' + '001'.padEnd(digits - 1, '0').slice(0, digits - 1) },
        { prefix: '5', label: 'COGS / Production', example: '5' + '001'.padEnd(digits - 1, '0').slice(0, digits - 1) },
        { prefix: '6', label: 'General Expenses', example: '6' + '001'.padEnd(digits - 1, '0').slice(0, digits - 1) },
    ];

    if (isLoading) {
        return (
            <SettingsLayout>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '300px' }}>
                    <Loader2 size={32} className="animate-spin" style={{ color: 'var(--color-primary)' }} />
                </div>
            </SettingsLayout>
        );
    }

    return (
        <SettingsLayout>
            <PageHeader
                title="Chart of Account Settings"
                subtitle="Configure chart of accounts structure and digit enforcement for this tenant."
                icon={<Hash size={22} color="white" />}
                backButton={false}
            />

            {/* CoA Digit Controller */}
            <GlassCard style={{ marginBottom: '1.5rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1.25rem' }}>
                    <Hash size={20} style={{ color: '#2471a3' }} />
                    <h2 style={{ fontSize: 'var(--text-lg)', fontWeight: 600 }}>Digit Controller</h2>
                </div>

                <p style={{ color: 'var(--color-text-muted)', fontSize: 'var(--text-sm)', marginBottom: '1.5rem', lineHeight: 1.6 }}>
                    Set the strict number of digits for all account codes. When enforcement is active,
                    new accounts must have exactly the selected number of digits.
                </p>

                <div style={{ display: 'flex', gap: '2rem', flexWrap: 'wrap', marginBottom: '1.5rem' }}>
                    <div>
                        <label style={{ display: 'block', fontSize: 'var(--text-xs)', fontWeight: 600, marginBottom: '0.5rem', color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                            Account Code Digits
                        </label>
                        <select
                            className="glass-input"
                            value={digits}
                            onChange={(e) => setDigits(Number(e.target.value))}
                            style={{ width: '120px', padding: '0.5rem 0.75rem', fontSize: 'var(--text-sm)' }}
                        >
                            {[4, 5, 6, 7, 8, 9, 10].map((d) => (
                                <option key={d} value={d}>{d} digits</option>
                            ))}
                        </select>
                    </div>

                    <div>
                        <label style={{ display: 'block', fontSize: 'var(--text-xs)', fontWeight: 600, marginBottom: '0.5rem', color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                            Digit Enforcement
                        </label>
                        <div
                            onClick={() => setEnforced(!enforced)}
                            style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', cursor: 'pointer', userSelect: 'none' }}
                        >
                            <div style={{
                                width: '44px', height: '24px', borderRadius: '12px',
                                background: enforced ? '#2471a3' : 'var(--color-border)',
                                transition: 'background 0.2s', position: 'relative',
                            }}>
                                <div style={{
                                    width: '18px', height: '18px', borderRadius: '50%', background: 'white',
                                    position: 'absolute', top: '3px', left: enforced ? '23px' : '3px',
                                    transition: 'left 0.2s', boxShadow: '0 1px 3px rgba(0,0,0,0.2)',
                                }} />
                            </div>
                            <span style={{ fontSize: 'var(--text-sm)', fontWeight: 500, color: enforced ? '#2471a3' : 'var(--color-text-muted)' }}>
                                {enforced ? 'Active' : 'Inactive'}
                            </span>
                        </div>
                    </div>
                </div>

                <div style={{ marginBottom: '1.5rem' }}>
                    <label style={{ display: 'block', fontSize: 'var(--text-xs)', fontWeight: 600, marginBottom: '0.5rem', color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                        Code Preview ({digits} digits)
                    </label>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: '0.5rem' }}>
                        {previewCodes.map((p) => (
                            <div key={p.prefix} style={{
                                padding: '0.5rem 0.75rem', borderRadius: '8px',
                                background: 'var(--color-background)', border: '1px solid var(--color-border)', fontSize: 'var(--text-xs)',
                            }}>
                                <span style={{ fontWeight: 600, color: '#2471a3' }}>{p.prefix}xxx</span>
                                <span style={{ color: 'var(--color-text-muted)', margin: '0 0.5rem' }}>&rarr;</span>
                                <span style={{ fontFamily: 'monospace' }}>{p.example}</span>
                                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', marginTop: '0.15rem' }}>{p.label}</div>
                            </div>
                        ))}
                    </div>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                    <button
                        className="btn-primary"
                        onClick={() => saveMutation.mutate()}
                        disabled={saveMutation.isPending}
                        style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}
                    >
                        {saveMutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
                        Save Settings
                    </button>
                    {saveMsg && (
                        <span style={{ fontSize: 'var(--text-sm)', fontWeight: 500, color: saveMsg.includes('success') ? 'var(--color-success)' : '#ef4444' }}>
                            {saveMsg}
                        </span>
                    )}
                </div>
            </GlassCard>

            {/* Auto-Seed CoA */}
            <GlassCard>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1.25rem' }}>
                    <Sprout size={20} style={{ color: '#10b981' }} />
                    <h2 style={{ fontSize: 'var(--text-lg)', fontWeight: 600 }}>Auto-Seed Default Chart of Accounts</h2>
                </div>

                <p style={{ color: 'var(--color-text-muted)', fontSize: 'var(--text-sm)', marginBottom: '1rem', lineHeight: 1.6 }}>
                    Generate a standard set of ~28 default accounts based on the current digit count setting.
                </p>
                <ul style={{ color: 'var(--color-text-muted)', fontSize: 'var(--text-sm)', marginBottom: '1.5rem', paddingLeft: '1.25rem', lineHeight: 1.8 }}>
                    <li><strong>1-series:</strong> Assets</li>
                    <li><strong>2-series:</strong> Liabilities</li>
                    <li><strong>3-series:</strong> Equity</li>
                    <li><strong>4-series:</strong> Income</li>
                    <li><strong>5-series:</strong> COGS / Production Expenses</li>
                    <li><strong>6-series:</strong> General Expenses</li>
                </ul>

                <p style={{ color: 'var(--color-text-muted)', fontSize: 'var(--text-xs)', marginBottom: '1.5rem' }}>
                    Existing account codes will be skipped — this operation is safe to run multiple times.
                </p>

                <button
                    className="btn-glass"
                    onClick={() => seedMutation.mutate()}
                    disabled={seedMutation.isPending}
                    style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', borderColor: '#10b981', color: '#10b981' }}
                >
                    {seedMutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <Sprout size={16} />}
                    Seed Default Accounts
                </button>

                {seedResult && (
                    <GlassCard style={{ marginTop: '1rem', background: seedResult.created > 0 ? 'rgba(16, 185, 129, 0.08)' : 'rgba(245, 158, 11, 0.08)' }}>
                        <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600, marginBottom: '0.5rem' }}>
                            {seedResult.created > 0 ? 'Accounts Created Successfully' : 'All Accounts Already Exist'}
                        </div>
                        <div style={{ display: 'flex', gap: '2rem', fontSize: 'var(--text-sm)' }}>
                            <div><span style={{ color: 'var(--color-text-muted)' }}>Created: </span><strong style={{ color: '#10b981' }}>{seedResult.created}</strong></div>
                            <div><span style={{ color: 'var(--color-text-muted)' }}>Skipped: </span><strong style={{ color: '#f59e0b' }}>{seedResult.skipped}</strong></div>
                            <div><span style={{ color: 'var(--color-text-muted)' }}>Total Seed: </span><strong>{seedResult.total_seed}</strong></div>
                        </div>
                    </GlassCard>
                )}
            </GlassCard>
        </SettingsLayout>
    );
}
