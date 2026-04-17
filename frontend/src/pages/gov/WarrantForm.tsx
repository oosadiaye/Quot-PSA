/**
 * Warrant (AIE) Create Form — Quot PSE
 * Route: /budget/warrants/new
 *
 * Creates a government Warrant / Authority to Incur Expenditure (AIE):
 * - Select appropriation (shows MDA, account, available balance)
 * - Set quarter, amount, release date
 * - Enter authority reference (AIE letter number from Budget Office)
 *
 * The warrant is created as PENDING. The Budget Office releases it via
 * the release action, which triggers notifications to MDA + AG.
 */
import { useState, useMemo, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Save, AlertCircle, FileText, Info, Paperclip, X, Search, Building2 } from 'lucide-react';
import Sidebar from '../../components/Sidebar';
import PageHeader from '../../components/PageHeader';
import '../../features/accounting/styles/glassmorphism.css';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import {
    useAppropriationsList,
} from '../../hooks/useGovForms';
import apiClient from '../../api/client';

const selectStyle: React.CSSProperties = {
    width: '100%', padding: '0.5rem 0.625rem', borderRadius: '6px',
    border: '2.5px solid var(--color-border)', background: 'var(--color-surface)',
    color: 'var(--color-text)', fontSize: 'var(--text-xs)',
};
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

const QUARTERS = [
    ['1', 'Q1 — January to March'],
    ['2', 'Q2 — April to June'],
    ['3', 'Q3 — July to September'],
    ['4', 'Q4 — October to December'],
];

const fmtNGN = (v: number | string | undefined): string => {
    const num = typeof v === 'string' ? parseFloat(v) : (v || 0);
    if (isNaN(num)) return '\u20A60.00';
    return '\u20A6' + num.toLocaleString('en-NG', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
};

export default function WarrantForm() {
    const navigate = useNavigate();
    const qc = useQueryClient();
    const { data: appropriations } = useAppropriationsList();
    const fileInputRef = useRef<HTMLInputElement>(null);

    const [formError, setFormError] = useState('');
    const [attachmentFile, setAttachmentFile] = useState<File | null>(null);
    const [appFilter, setAppFilter] = useState('');
    const [form, setForm] = useState({
        appropriation: '', quarter: '', amount_released: '',
        release_date: new Date().toISOString().split('T')[0],
        authority_reference: '', notes: '',
    });

    // Filter appropriations by economic code, economic name, MDA name, or fund.
    // Lets the verifier type "23000000" or "Capital" to quickly find the right
    // budget line — critical because warrants are released against a SPECIFIC
    // economic code (Acquisition of Land, Personnel Costs, etc.), not against
    // the MDA as a whole.
    const filteredAppropriations = useMemo(() => {
        if (!appropriations) return [];
        const q = appFilter.trim().toLowerCase();
        if (!q) return appropriations;
        return appropriations.filter((a: any) => {
            const haystack = [
                a.economic_code, a.economic_name,
                a.administrative_code, a.administrative_name,
                a.fund_code, a.fund_name,
            ].filter(Boolean).join(' ').toLowerCase();
            return haystack.includes(q);
        });
    }, [appropriations, appFilter]);

    // Use custom mutation to handle FormData (file upload)
    const createWarrant = useMutation({
        mutationFn: async (formData: FormData) => {
            return apiClient.post('/budget/warrants/', formData, {
                headers: { 'Content-Type': 'multipart/form-data' },
            });
        },
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['generic-list'] });
            navigate('/budget/warrants');
        },
    });

    const set = (field: string, value: string) => setForm(prev => ({ ...prev, [field]: value }));

    // Selected appropriation details
    const selectedApp = useMemo(() => {
        if (!form.appropriation || !appropriations) return null;
        return appropriations.find((a: any) => String(a.id) === form.appropriation);
    }, [form.appropriation, appropriations]);

    // Auto-suggest authority reference when appropriation + quarter selected
    const suggestedRef = useMemo(() => {
        if (!selectedApp || !form.quarter) return '';
        const fy = selectedApp.fiscal_year_display || selectedApp.fiscal_year;
        const mdaCode = selectedApp.administrative_code || selectedApp.administrative_name?.substring(0, 10) || '';
        return `AIE/${fy}/Q${form.quarter}/${mdaCode}`;
    }, [selectedApp, form.quarter]);

    // Validate amount against unwarranted balance
    const unwarrantedBalance = selectedApp ? parseFloat(selectedApp.unwarranted_balance || selectedApp.available_balance || '0') : 0;
    const enteredAmount = parseFloat(form.amount_released) || 0;
    const exceedsBalance = enteredAmount > unwarrantedBalance && unwarrantedBalance > 0;

    const handleAppropriationChange = (value: string) => {
        set('appropriation', value);
        // Auto-fill authority reference suggestion
        if (value && form.quarter) {
            const app = appropriations?.find((a: any) => String(a.id) === value);
            if (app) {
                const fy = app.fiscal_year_display || app.fiscal_year;
                const code = app.administrative_code || '';
                set('authority_reference', `AIE/${fy}/Q${form.quarter}/${code}`);
            }
        }
    };

    const handleQuarterChange = (value: string) => {
        set('quarter', value);
        // Update authority reference with new quarter
        if (selectedApp && value) {
            const fy = selectedApp.fiscal_year_display || selectedApp.fiscal_year;
            const code = selectedApp.administrative_code || '';
            setForm(prev => ({ ...prev, quarter: value, authority_reference: `AIE/${fy}/Q${value}/${code}` }));
        }
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setFormError('');

        if (exceedsBalance) {
            setFormError(`Amount (${fmtNGN(enteredAmount)}) exceeds unwarranted balance (${fmtNGN(unwarrantedBalance)})`);
            return;
        }

        // Build FormData for multipart upload (file attachment)
        const fd = new FormData();
        fd.append('appropriation', form.appropriation);
        fd.append('quarter', form.quarter);
        fd.append('amount_released', form.amount_released);
        fd.append('release_date', form.release_date);
        fd.append('authority_reference', form.authority_reference);
        fd.append('status', 'PENDING');
        fd.append('notes', form.notes);
        if (attachmentFile) {
            fd.append('attachment', attachmentFile);
        }

        try {
            await createWarrant.mutateAsync(fd);
        } catch (err: any) {
            const d = err.response?.data;
            if (d?.detail) setFormError(d.detail);
            else if (d && typeof d === 'object') {
                const msgs = Object.entries(d).map(([k, v]) =>
                    `${k}: ${Array.isArray(v) ? v.join(', ') : v}`
                );
                setFormError(msgs.join(' | '));
            } else {
                setFormError(err.message || 'Failed to create Warrant');
            }
        }
    };

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }}>
                <div style={{ maxWidth: '900px' }}>
                    <PageHeader title="New Warrant (AIE)" subtitle="Authority to Incur Expenditure — quarterly cash release for an MDA" icon={<FileText size={22} />} />

                    {formError && (
                        <div style={{ padding: '10px 14px', borderRadius: '8px', marginBottom: '14px', background: '#fef2f2', border: '1px solid #fecaca', color: '#dc2626', display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px' }}>
                            <AlertCircle size={14} /> {formError}
                        </div>
                    )}

                    <form onSubmit={handleSubmit}>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                            {/* Left: Appropriation + Warrant Details */}
                            <div>
                                <div className="glass-card" style={{ padding: '1.25rem', marginBottom: '1rem' }}>
                                    <h3 style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)', margin: '0 0 1rem 0', display: 'flex', alignItems: 'center', gap: '6px' }}>
                                        <FileText size={14} /> Select Appropriation
                                    </h3>
                                    <label style={lblStyle}>
                                        Appropriation *{' '}
                                        <span style={{ fontWeight: 400, textTransform: 'none', color: '#94a3b8' }}>
                                            (MDA + Economic Code + Fund — warrants are released against this combination)
                                        </span>
                                    </label>

                                    {/* Filter input — search by economic code (e.g. "23000000"),
                                        economic name (e.g. "Capital"), MDA, or fund. Critical
                                        for finding the right line in tenants with many
                                        appropriations. */}
                                    <div style={{ position: 'relative', marginBottom: '0.5rem' }}>
                                        <Search size={14} style={{
                                            position: 'absolute', left: 10, top: '50%',
                                            transform: 'translateY(-50%)', color: '#94a3b8',
                                        }} />
                                        <input
                                            type="text"
                                            value={appFilter}
                                            onChange={e => setAppFilter(e.target.value)}
                                            placeholder="Filter by economic code, name, MDA, or fund…"
                                            style={{
                                                ...inputStyle,
                                                paddingLeft: '2rem',
                                                fontSize: '12px',
                                            }}
                                        />
                                    </div>

                                    <select
                                        style={{ ...selectStyle, fontFamily: 'monospace' }}
                                        required
                                        value={form.appropriation}
                                        onChange={e => handleAppropriationChange(e.target.value)}
                                        size={Math.min(8, Math.max(3, filteredAppropriations.length || 3))}
                                    >
                                        {filteredAppropriations.length === 0 && (
                                            <option value="" disabled>No appropriations match the filter</option>
                                        )}
                                        {filteredAppropriations.map((a: any) => (
                                            <option key={a.id} value={a.id}>
                                                {a.economic_code || '?'}
                                                {' — '}
                                                {a.economic_name || 'Unknown'}
                                                {' • '}
                                                {a.administrative_code || ''} {a.administrative_name || ''}
                                                {a.fund_code ? ` • Fund ${a.fund_code}` : ''}
                                                {' • '}
                                                {fmtNGN(a.amount_approved)}
                                            </option>
                                        ))}
                                    </select>
                                    <div style={{ marginTop: '0.4rem', fontSize: '10px', color: '#94a3b8', lineHeight: 1.5 }}>
                                        Showing {filteredAppropriations.length} of {(appropriations || []).length} appropriations
                                        {appFilter && <> &nbsp;•&nbsp; <button type="button" onClick={() => setAppFilter('')} style={{ background: 'none', border: 'none', color: '#4f46e5', cursor: 'pointer', padding: 0, fontSize: '10px', textDecoration: 'underline' }}>clear filter</button></>}
                                    </div>
                                </div>

                                <div className="glass-card" style={{ padding: '1.25rem', marginBottom: '1rem' }}>
                                    <h3 style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)', margin: '0 0 1rem 0' }}>Warrant Details</h3>
                                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                                        <div>
                                            <label style={lblStyle}>Quarter *</label>
                                            <select style={selectStyle} required value={form.quarter} onChange={e => handleQuarterChange(e.target.value)}>
                                                <option value="">Select quarter...</option>
                                                {QUARTERS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                                            </select>
                                        </div>
                                        <div>
                                            <label style={lblStyle}>Release Date *</label>
                                            <input style={inputStyle} type="date" required value={form.release_date} onChange={e => set('release_date', e.target.value)} />
                                        </div>
                                        <div style={{ gridColumn: '1 / -1' }}>
                                            <label style={lblStyle}>Amount Released (NGN) *</label>
                                            <input
                                                style={{
                                                    ...inputStyle,
                                                    fontSize: '18px', fontWeight: 700,
                                                    borderColor: exceedsBalance ? '#ef4444' : '#e2e8f0',
                                                }}
                                                type="number" step="0.01" min="0.01" required
                                                value={form.amount_released}
                                                onChange={e => set('amount_released', e.target.value)}
                                                placeholder="0.00"
                                            />
                                            {exceedsBalance && (
                                                <div style={{ color: '#ef4444', fontSize: 11, marginTop: 4 }}>
                                                    Exceeds unwarranted balance of {fmtNGN(unwarrantedBalance)}
                                                </div>
                                            )}
                                        </div>
                                        <div style={{ gridColumn: '1 / -1' }}>
                                            <label style={lblStyle}>
                                                AIE Reference Number *
                                                <span style={{ fontWeight: 400, textTransform: 'none', color: '#94a3b8' }}> (Budget Office letter number)</span>
                                            </label>
                                            <input style={inputStyle} required value={form.authority_reference} onChange={e => set('authority_reference', e.target.value)}
                                                placeholder={suggestedRef || 'e.g. AIE/2026/Q1/050200000000'} />
                                            {suggestedRef && !form.authority_reference && (
                                                <div style={{ fontSize: 10, color: '#94a3b8', marginTop: 3 }}>
                                                    Suggested: {suggestedRef}
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                    <div style={{ marginTop: '10px' }}>
                                        <label style={lblStyle}>Notes</label>
                                        <textarea style={{ ...inputStyle, minHeight: '50px', fontSize: 13 }} value={form.notes} onChange={e => set('notes', e.target.value)} placeholder="Additional notes..." />
                                    </div>

                                    {/* AIE Letter Attachment */}
                                    <div style={{ marginTop: '12px' }}>
                                        <label style={lblStyle}>
                                            <Paperclip size={11} style={{ marginRight: 4, verticalAlign: 'middle' }} />
                                            AIE Letter Attachment
                                            <span style={{ fontWeight: 400, textTransform: 'none', color: '#94a3b8' }}> (PDF or image of the signed letter)</span>
                                        </label>
                                        <input
                                            ref={fileInputRef}
                                            type="file"
                                            accept=".pdf,.jpg,.jpeg,.png,.doc,.docx"
                                            style={{ display: 'none' }}
                                            onChange={e => setAttachmentFile(e.target.files?.[0] || null)}
                                        />
                                        {attachmentFile ? (
                                            <div style={{
                                                display: 'flex', alignItems: 'center', gap: 8,
                                                padding: '8px 12px', borderRadius: 8,
                                                background: '#f0fdf4', border: '1px solid #86efac',
                                            }}>
                                                <Paperclip size={14} color="#166534" />
                                                <span style={{ fontSize: 13, color: '#166534', flex: 1 }}>
                                                    {attachmentFile.name}
                                                    <span style={{ color: '#94a3b8', marginLeft: 6 }}>
                                                        ({(attachmentFile.size / 1024).toFixed(0)} KB)
                                                    </span>
                                                </span>
                                                <button type="button" onClick={() => { setAttachmentFile(null); if (fileInputRef.current) fileInputRef.current.value = ''; }}
                                                    style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#ef4444', padding: 2 }}>
                                                    <X size={14} />
                                                </button>
                                            </div>
                                        ) : (
                                            <button type="button" onClick={() => fileInputRef.current?.click()}
                                                style={{
                                                    display: 'flex', alignItems: 'center', gap: 6,
                                                    padding: '8px 14px', borderRadius: 8,
                                                    border: '1.5px dashed #cbd5e1', background: '#f8fafc',
                                                    color: '#64748b', fontSize: 12, cursor: 'pointer', width: '100%',
                                                }}>
                                                <Paperclip size={13} />
                                                Click to attach AIE letter (PDF, JPG, PNG, DOC)
                                            </button>
                                        )}
                                    </div>
                                </div>
                            </div>

                            {/* Right: Appropriation Summary */}
                            <div>
                                {selectedApp ? (
                                    <div className="glass-card" style={{ padding: '1.25rem', marginBottom: '1rem', border: '2px solid #dbeafe' }}>
                                        <h3 style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: '#1e40af', margin: '0 0 1rem 0', display: 'flex', alignItems: 'center', gap: '6px' }}>
                                            <Info size={14} /> Appropriation Summary
                                        </h3>
                                        <div style={{ display: 'grid', gap: '10px' }}>
                                            {/* Economic Code surfaced as the primary identifier — this
                                                is the key that ties the warrant to PO/GRN/Invoice
                                                budget controls downstream. */}
                                            <div style={{
                                                background: 'linear-gradient(90deg, rgba(79,70,229,0.08) 0%, rgba(99,102,241,0.05) 100%)',
                                                border: '1px solid rgba(79,70,229,0.25)',
                                                borderRadius: 8, padding: '10px 12px',
                                            }}>
                                                <div style={{ fontSize: 10, color: '#4f46e5', textTransform: 'uppercase', fontWeight: 700, letterSpacing: '0.04em', marginBottom: 4 }}>
                                                    Economic Code (the line being warranted)
                                                </div>
                                                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                                    <span style={{ fontFamily: 'monospace', fontSize: 14, fontWeight: 700, color: '#4f46e5', background: 'white', padding: '3px 8px', borderRadius: 4 }}>
                                                        {selectedApp.economic_code || '?'}
                                                    </span>
                                                    <span style={{ fontSize: 13, color: '#1e293b' }}>{selectedApp.economic_name}</span>
                                                </div>
                                            </div>
                                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                                                <div>
                                                    <div style={{ fontSize: 10, color: '#64748b', textTransform: 'uppercase', fontWeight: 600, display: 'flex', alignItems: 'center', gap: 4 }}>
                                                        <Building2 size={10} /> MDA
                                                    </div>
                                                    <div style={{ fontSize: 12, fontWeight: 600, color: '#1e293b', marginTop: 2 }}>
                                                        <span style={{ fontFamily: 'monospace', color: '#64748b' }}>{selectedApp.administrative_code}</span>{' '}
                                                        {selectedApp.administrative_name}
                                                    </div>
                                                </div>
                                                <div>
                                                    <div style={{ fontSize: 10, color: '#64748b', textTransform: 'uppercase', fontWeight: 600 }}>Fund</div>
                                                    <div style={{ fontSize: 12, fontWeight: 600, color: '#1e293b', marginTop: 2 }}>
                                                        <span style={{ fontFamily: 'monospace', color: '#64748b' }}>{selectedApp.fund_code}</span>{' '}
                                                        {selectedApp.fund_name}
                                                    </div>
                                                </div>
                                            </div>
                                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                                                <div style={{ background: '#eff6ff', borderRadius: 8, padding: '10px 12px' }}>
                                                    <div style={{ fontSize: 10, color: '#1e40af', fontWeight: 600 }}>APPROVED</div>
                                                    <div style={{ fontSize: 16, fontWeight: 700, color: '#1e293b' }}>{fmtNGN(selectedApp.amount_approved)}</div>
                                                </div>
                                                <div style={{ background: '#f0fdf4', borderRadius: 8, padding: '10px 12px' }}>
                                                    <div style={{ fontSize: 10, color: '#166534', fontWeight: 600 }}>AVAILABLE</div>
                                                    <div style={{ fontSize: 16, fontWeight: 700, color: '#166534' }}>{fmtNGN(selectedApp.available_balance)}</div>
                                                </div>
                                            </div>
                                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                                                <div style={{ background: '#fff7ed', borderRadius: 8, padding: '10px 12px' }}>
                                                    <div style={{ fontSize: 10, color: '#c2410c', fontWeight: 600 }}>WARRANTS RELEASED</div>
                                                    <div style={{ fontSize: 14, fontWeight: 700, color: '#c2410c' }}>{fmtNGN(selectedApp.total_warrants_released)}</div>
                                                </div>
                                                <div style={{ background: '#fdf4ff', borderRadius: 8, padding: '10px 12px' }}>
                                                    <div style={{ fontSize: 10, color: '#6b21a8', fontWeight: 600 }}>EXPENDED</div>
                                                    <div style={{ fontSize: 14, fontWeight: 700, color: '#6b21a8' }}>{fmtNGN(selectedApp.total_expended)}</div>
                                                </div>
                                            </div>
                                            {selectedApp.execution_rate !== undefined && (
                                                <div>
                                                    <div style={{ fontSize: 10, color: '#64748b', fontWeight: 600, marginBottom: 4 }}>EXECUTION RATE</div>
                                                    <div style={{ background: '#e2e8f0', borderRadius: 6, height: 8, overflow: 'hidden' }}>
                                                        <div style={{
                                                            height: '100%', borderRadius: 6,
                                                            width: `${Math.min(parseFloat(selectedApp.execution_rate || '0'), 100)}%`,
                                                            background: parseFloat(selectedApp.execution_rate || '0') > 80 ? '#ef4444' : '#22c55e',
                                                        }} />
                                                    </div>
                                                    <div style={{ fontSize: 11, color: '#64748b', marginTop: 2 }}>
                                                        {parseFloat(selectedApp.execution_rate || '0').toFixed(1)}% of budget spent
                                                    </div>
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                ) : (
                                    <div className="glass-card" style={{ padding: '40px 20px', marginBottom: '1rem', textAlign: 'center' }}>
                                        <FileText size={32} color="#94a3b8" />
                                        <p style={{ color: '#94a3b8', fontSize: 13, marginTop: 12 }}>
                                            Select an appropriation to see its summary
                                        </p>
                                    </div>
                                )}

                                {/* Info box */}
                                <div className="glass-card" style={{ padding: '1.25rem', marginBottom: '1rem', background: '#fffbeb', border: '1px solid #fde68a' }}>
                                    <div style={{ fontSize: 12, color: '#92400e' }}>
                                        <strong>How AIE works:</strong>
                                        <ol style={{ margin: '8px 0 0', paddingLeft: 18, lineHeight: 1.6 }}>
                                            <li>Budget Office creates the warrant here (status: <strong>PENDING</strong>)</li>
                                            <li>Budget Commissioner reviews and <strong>releases</strong> it</li>
                                            <li>MDA accountant + AG are <strong>notified automatically</strong></li>
                                            <li>MDA can now raise PVs up to the released amount</li>
                                        </ol>
                                    </div>
                                </div>
                            </div>
                        </div>

                        {/* Submit Row */}
                        <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end', marginTop: '8px' }}>
                            <button type="button" onClick={() => navigate(-1)} className="glass-button" style={{
                                padding: '10px 20px', borderRadius: '8px', border: '1px solid var(--color-border)',
                                background: 'var(--color-surface)', color: 'var(--color-text)', fontSize: '13px', fontWeight: 600, cursor: 'pointer',
                            }}>
                                Cancel
                            </button>
                            <button type="submit" disabled={createWarrant.isPending || exceedsBalance} style={{
                                padding: '10px 24px', borderRadius: '8px', border: 'none',
                                background: exceedsBalance ? '#94a3b8' : 'linear-gradient(135deg, var(--primary, #191e6a) 0%, var(--primary-dark, #0f1240) 100%)', color: '#fff',
                                fontSize: '13px', fontWeight: 600, cursor: exceedsBalance ? 'not-allowed' : 'pointer',
                                display: 'flex', alignItems: 'center', gap: '6px',
                                opacity: createWarrant.isPending ? 0.7 : 1,
                                boxShadow: exceedsBalance ? 'none' : '0 4px 12px rgba(15, 18, 64, 0.3)',
                            }}>
                                <Save size={14} />
                                {createWarrant.isPending ? 'Creating...' : 'Create Warrant (PENDING)'}
                            </button>
                        </div>
                    </form>
                </div>
            </main>
        </div>
    );
}
