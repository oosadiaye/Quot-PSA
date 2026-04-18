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
import { useState, useMemo, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Save, AlertCircle, FileText, Info, Paperclip, X, Search, Building2, MapPin, Target, Layers, CheckCircle2 } from 'lucide-react';
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

    // Two-step picker state — simpler than a flat list when tenants have
    // many appropriations. User picks an MDA that has a budget, then a GL /
    // economic code that exists on that MDA.
    const [mdaInput, setMdaInput] = useState('');           // raw text typed
    const [selectedMdaCode, setSelectedMdaCode] = useState(''); // resolved MDA administrative_code
    const [glInput, setGlInput] = useState('');             // raw text typed
    const [selectedGlCode, setSelectedGlCode] = useState(''); // resolved economic_code

    const [form, setForm] = useState({
        appropriation: '', quarter: '', amount_released: '',
        release_date: new Date().toISOString().split('T')[0],
        authority_reference: '', notes: '',
    });

    // ── Derived data for the two-step picker ──────────────────────
    // 1. Unique MDAs that have at least one appropriation
    const mdasWithBudget = useMemo(() => {
        if (!appropriations) return [];
        const seen = new Map<string, { code: string; name: string }>();
        for (const a of appropriations as any[]) {
            const key = a.administrative_code || '';
            if (key && !seen.has(key)) {
                seen.set(key, { code: key, name: a.administrative_name || '' });
            }
        }
        return [...seen.values()].sort((a, b) => a.code.localeCompare(b.code));
    }, [appropriations]);

    // 2. Economic codes that exist under the selected MDA
    const glsOnSelectedMda = useMemo(() => {
        if (!appropriations || !selectedMdaCode) return [];
        const seen = new Map<string, { code: string; name: string }>();
        for (const a of appropriations as any[]) {
            if (a.administrative_code !== selectedMdaCode) continue;
            const key = a.economic_code || '';
            if (key && !seen.has(key)) {
                seen.set(key, { code: key, name: a.economic_name || '' });
            }
        }
        return [...seen.values()].sort((a, b) => a.code.localeCompare(b.code));
    }, [appropriations, selectedMdaCode]);

    // 3. Appropriation rows matching the chosen MDA + GL (may be >1 if different
    //    fund sources or fiscal years exist for the same combination)
    const matchingAppropriations = useMemo(() => {
        if (!appropriations || !selectedMdaCode || !selectedGlCode) return [];
        return (appropriations as any[]).filter(a =>
            a.administrative_code === selectedMdaCode &&
            a.economic_code === selectedGlCode,
        );
    }, [appropriations, selectedMdaCode, selectedGlCode]);

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

    // When the picker resolves to exactly one appropriation, auto-select it
    // on the form. When it resolves to zero or many, clear the selection so
    // the summary panel + downstream fields reflect the ambiguity.
    useEffect(() => {
        if (matchingAppropriations.length === 1) {
            const appId = String(matchingAppropriations[0].id);
            if (form.appropriation !== appId) {
                handleAppropriationChange(appId);
            }
        } else if (matchingAppropriations.length === 0 && form.appropriation) {
            setForm(prev => ({ ...prev, appropriation: '' }));
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [matchingAppropriations]);

    // Resolver helpers: map typed text / datalist value back to MDA code + GL code
    const resolveMda = (value: string) => {
        setMdaInput(value);
        // Accept either "<code> — <name>" (datalist shape) or plain code or partial name
        const match = mdasWithBudget.find(m =>
            value === m.code ||
            value === `${m.code} — ${m.name}` ||
            value.toLowerCase() === m.name.toLowerCase(),
        );
        setSelectedMdaCode(match ? match.code : '');
        // Reset the GL when MDA changes
        if (!match || match.code !== selectedMdaCode) {
            setGlInput('');
            setSelectedGlCode('');
        }
    };
    const resolveGl = (value: string) => {
        setGlInput(value);
        const match = glsOnSelectedMda.find(g =>
            value === g.code ||
            value === `${g.code} — ${g.name}` ||
            value.toLowerCase() === g.name.toLowerCase(),
        );
        setSelectedGlCode(match ? match.code : '');
    };

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
                                    <h3 style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)', margin: '0 0 0.75rem 0', display: 'flex', alignItems: 'center', gap: '6px' }}>
                                        <FileText size={14} /> Select Appropriation
                                    </h3>
                                    <p style={{ fontSize: 11, color: '#94a3b8', margin: '0 0 14px', lineHeight: 1.5 }}>
                                        Type or select your MDA, then choose the economic code (GL) you're releasing cash for.
                                        Both must already have a budget appropriation.
                                    </p>

                                    {/* ── Step 1: MDA picker ──────────────────────────── */}
                                    <label style={lblStyle}>Step 1 · MDA *</label>
                                    <div style={{ position: 'relative' }}>
                                        <Building2 size={14} style={{
                                            position: 'absolute', left: 10, top: '50%',
                                            transform: 'translateY(-50%)', color: '#94a3b8', pointerEvents: 'none',
                                        }} />
                                        <input
                                            type="text"
                                            list="mda-with-budget-list"
                                            value={mdaInput}
                                            onChange={e => resolveMda(e.target.value)}
                                            placeholder={mdasWithBudget.length
                                                ? `Type or pick from ${mdasWithBudget.length} MDA${mdasWithBudget.length === 1 ? '' : 's'} with a budget…`
                                                : 'No MDA has any appropriation yet'}
                                            disabled={mdasWithBudget.length === 0}
                                            style={{
                                                ...inputStyle, paddingLeft: '2rem',
                                                borderColor: selectedMdaCode ? '#22c55e' : '#e2e8f0',
                                            }}
                                        />
                                        <datalist id="mda-with-budget-list">
                                            {mdasWithBudget.map(m => (
                                                <option key={m.code} value={`${m.code} — ${m.name}`} />
                                            ))}
                                        </datalist>
                                    </div>
                                    {selectedMdaCode && (
                                        <div style={{ fontSize: 10, color: '#16a34a', marginTop: 4, display: 'flex', alignItems: 'center', gap: 4 }}>
                                            <CheckCircle2 size={11} /> MDA resolved: <span style={{ fontFamily: 'monospace' }}>{selectedMdaCode}</span>
                                            &nbsp;·&nbsp; {glsOnSelectedMda.length} budget line{glsOnSelectedMda.length === 1 ? '' : 's'} available
                                        </div>
                                    )}
                                    {mdaInput && !selectedMdaCode && mdasWithBudget.length > 0 && (
                                        <div style={{ fontSize: 10, color: '#c2410c', marginTop: 4 }}>
                                            Keep typing or pick from the dropdown. "{mdaInput}" doesn't match any MDA with a budget.
                                        </div>
                                    )}

                                    {/* ── Step 2: GL / Economic code picker ───────────── */}
                                    <div style={{ marginTop: 14 }}>
                                        <label style={lblStyle}>Step 2 · Economic Code (GL) *</label>
                                        <div style={{ position: 'relative' }}>
                                            <Target size={14} style={{
                                                position: 'absolute', left: 10, top: '50%',
                                                transform: 'translateY(-50%)', color: '#94a3b8', pointerEvents: 'none',
                                            }} />
                                            <input
                                                type="text"
                                                list="gl-on-mda-list"
                                                value={glInput}
                                                onChange={e => resolveGl(e.target.value)}
                                                placeholder={
                                                    !selectedMdaCode ? 'Pick an MDA first' :
                                                    glsOnSelectedMda.length === 0 ? 'No budget lines on this MDA' :
                                                    `Type or pick from ${glsOnSelectedMda.length} economic code${glsOnSelectedMda.length === 1 ? '' : 's'}…`
                                                }
                                                disabled={!selectedMdaCode || glsOnSelectedMda.length === 0}
                                                style={{
                                                    ...inputStyle, paddingLeft: '2rem',
                                                    borderColor: selectedGlCode ? '#22c55e' : '#e2e8f0',
                                                }}
                                            />
                                            <datalist id="gl-on-mda-list">
                                                {glsOnSelectedMda.map(g => (
                                                    <option key={g.code} value={`${g.code} — ${g.name}`} />
                                                ))}
                                            </datalist>
                                        </div>
                                    </div>

                                    {/* ── Resolver status ──────────────────────────────── *
                                     * Banner fires when the user has picked an MDA AND typed
                                     * a GL, but either (a) the GL text doesn't resolve to any
                                     * real code on this MDA, or (b) the resolved GL+MDA pair
                                     * still has no matching appropriation row.
                                     */}
                                    {selectedMdaCode && glInput.trim() && (!selectedGlCode || matchingAppropriations.length === 0) && (
                                        <div style={{
                                            marginTop: 12, padding: '10px 12px', borderRadius: 8,
                                            background: '#fef2f2', border: '1px solid #fecaca',
                                            color: '#b91c1c', fontSize: 12, display: 'flex', alignItems: 'flex-start', gap: 6,
                                        }}>
                                            <AlertCircle size={14} style={{ flexShrink: 0, marginTop: 1 }} />
                                            <div>
                                                <strong>No Budget Appropriation Line for this GL.</strong>
                                                <div style={{ fontSize: 11, color: '#991b1b', marginTop: 2, lineHeight: 1.5 }}>
                                                    {selectedGlCode ? (
                                                        <>No appropriation exists for MDA <code style={{ fontFamily: 'monospace' }}>{selectedMdaCode}</code>
                                                            &nbsp;+ Economic Code <code style={{ fontFamily: 'monospace' }}>{selectedGlCode}</code>.
                                                            Create the appropriation first, then come back to raise the warrant.</>
                                                    ) : (
                                                        <>"{glInput}" doesn't match any economic code with a budget on MDA
                                                            &nbsp;<code style={{ fontFamily: 'monospace' }}>{selectedMdaCode}</code>.
                                                            Pick one from the dropdown — this MDA has {glsOnSelectedMda.length} budget
                                                            line{glsOnSelectedMda.length === 1 ? '' : 's'} available.</>
                                                    )}
                                                </div>
                                            </div>
                                        </div>
                                    )}

                                    {matchingAppropriations.length > 1 && (
                                        <div style={{ marginTop: 12 }}>
                                            <div style={{
                                                fontSize: 11, color: '#b45309', marginBottom: 6, fontWeight: 600,
                                                display: 'flex', alignItems: 'center', gap: 4,
                                            }}>
                                                <Info size={12} /> {matchingAppropriations.length} matches — pick one:
                                            </div>
                                            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                                                {matchingAppropriations.map((a: any) => (
                                                    <button
                                                        key={a.id}
                                                        type="button"
                                                        onClick={() => handleAppropriationChange(String(a.id))}
                                                        style={{
                                                            textAlign: 'left', padding: '8px 10px', borderRadius: 6,
                                                            border: form.appropriation === String(a.id) ? '2px solid #22c55e' : '1.5px solid #e2e8f0',
                                                            background: form.appropriation === String(a.id) ? '#f0fdf4' : '#fff',
                                                            cursor: 'pointer', fontSize: 12,
                                                        }}
                                                    >
                                                        <div style={{ fontWeight: 600 }}>
                                                            Fund {a.fund_code} — {a.fund_name}
                                                        </div>
                                                        <div style={{ color: '#64748b', fontSize: 11 }}>
                                                            FY {a.fiscal_year_display || a.fiscal_year}
                                                            &nbsp;·&nbsp; Approved {fmtNGN(a.amount_approved)}
                                                            &nbsp;·&nbsp; Available {fmtNGN(a.available_balance)}
                                                        </div>
                                                    </button>
                                                ))}
                                            </div>
                                        </div>
                                    )}

                                    {/* Hidden input keeps the required attribute on form submission */}
                                    <input type="hidden" value={form.appropriation} required readOnly />
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
                                            {/* Full NCoA segment breakdown — all six dimensions that
                                                were coded on this appropriation at enactment time.
                                                Mirrors the Budget Appropriation Entry form so the user
                                                can verify they're warranting the right budget line. */}
                                            <div style={{
                                                fontSize: 10, color: '#64748b', textTransform: 'uppercase',
                                                fontWeight: 700, letterSpacing: '0.04em', marginTop: 4,
                                                paddingBottom: 6, borderBottom: '1px solid #e2e8f0',
                                                display: 'flex', alignItems: 'center', gap: 4,
                                            }}>
                                                <Layers size={11} /> NCoA Segment Breakdown
                                            </div>
                                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                                                <div>
                                                    <div style={{ fontSize: 10, color: '#64748b', textTransform: 'uppercase', fontWeight: 600, display: 'flex', alignItems: 'center', gap: 4 }}>
                                                        <Building2 size={10} /> MDA (Administrative)
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
                                                <div>
                                                    <div style={{ fontSize: 10, color: '#64748b', textTransform: 'uppercase', fontWeight: 600, display: 'flex', alignItems: 'center', gap: 4 }}>
                                                        <Target size={10} /> Function (COFOG)
                                                    </div>
                                                    <div style={{ fontSize: 12, fontWeight: 600, color: '#1e293b', marginTop: 2 }}>
                                                        {selectedApp.functional_code ? (
                                                            <>
                                                                <span style={{ fontFamily: 'monospace', color: '#64748b' }}>{selectedApp.functional_code}</span>{' '}
                                                                {selectedApp.functional_name}
                                                            </>
                                                        ) : <span style={{ color: '#cbd5e1', fontStyle: 'italic' }}>Not coded</span>}
                                                    </div>
                                                </div>
                                                <div>
                                                    <div style={{ fontSize: 10, color: '#64748b', textTransform: 'uppercase', fontWeight: 600 }}>Programme</div>
                                                    <div style={{ fontSize: 12, fontWeight: 600, color: '#1e293b', marginTop: 2 }}>
                                                        {selectedApp.programme_code ? (
                                                            <>
                                                                <span style={{ fontFamily: 'monospace', color: '#64748b' }}>{selectedApp.programme_code}</span>{' '}
                                                                {selectedApp.programme_name}
                                                            </>
                                                        ) : <span style={{ color: '#cbd5e1', fontStyle: 'italic' }}>Not coded</span>}
                                                    </div>
                                                </div>
                                                <div style={{ gridColumn: '1 / -1' }}>
                                                    <div style={{ fontSize: 10, color: '#64748b', textTransform: 'uppercase', fontWeight: 600, display: 'flex', alignItems: 'center', gap: 4 }}>
                                                        <MapPin size={10} /> Geographic (LGA / Zone)
                                                    </div>
                                                    <div style={{ fontSize: 12, fontWeight: 600, color: '#1e293b', marginTop: 2 }}>
                                                        {selectedApp.geographic_code ? (
                                                            <>
                                                                <span style={{ fontFamily: 'monospace', color: '#64748b' }}>{selectedApp.geographic_code}</span>{' '}
                                                                {selectedApp.geographic_name}
                                                            </>
                                                        ) : <span style={{ color: '#cbd5e1', fontStyle: 'italic' }}>Statewide (no zone coded)</span>}
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
