import React, { useState, useRef, useMemo, useEffect } from 'react';
import SearchableSelect from '../../components/SearchableSelect';
import { useNavigate, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import apiClient from '../../api/client';
import {
    useDimensions, useCreateJournal, useUpdateJournal, useJournalDetail,
    useDownloadJournalTemplate, useBulkImportJournals,
} from './hooks/useJournal';
import { useMDAs } from './hooks/useBudgetDimensions';
import { useIsDimensionsEnabled } from '../../hooks/useTenantModules';
import { useCurrency } from '../../context/CurrencyContext';
import { useToast } from '../../context/ToastContext';
import { formatApiError } from '../../utils/apiError';
import { parsePostingError } from './utils/parsePostingError';
import AccountingLayout from './AccountingLayout';
import PageHeader from '../../components/PageHeader';
import { Save, X, Plus, Trash2, AlertCircle, Download, Upload, FileUp, ChevronDown, ChevronUp, CheckCircle } from 'lucide-react';
import LoadingScreen from '../../components/common/LoadingScreen';

/**
 * Fixed-asset dropdown source for journal lines. Used for depreciation
 * runs, disposal JVs, and cost-accumulation entries where the debit /
 * credit should be tagged to the specific asset — so the Asset Register
 * and Asset History reports can reconstruct the lifecycle from the GL.
 */
function useFixedAssets() {
    return useQuery<Array<{ id: number; asset_number: string; name: string }>>({
        queryKey: ['fixed-assets-dropdown'],
        queryFn: async () => {
            const { data } = await apiClient.get('/accounting/fixed-assets/', {
                params: { page_size: 9999 },
            });
            return Array.isArray(data) ? data : (data?.results || []);
        },
        staleTime: 5 * 60 * 1000,
    });
}

// Today's date as YYYY-MM-DD in the user's *local* timezone.
// `toISOString()` first converts to UTC, which can roll the day backwards
// for any user behind UTC, or for WAT users in the late-evening UTC window.
const todayLocalISO = (): string => {
    const d = new Date();
    const yyyy = d.getFullYear();
    const mm = String(d.getMonth() + 1).padStart(2, '0');
    const dd = String(d.getDate()).padStart(2, '0');
    return `${yyyy}-${mm}-${dd}`;
};

interface JournalLine {
    id: string;
    account: string;
    debit: number;
    credit: number;
    memo: string;
    asset?: string;
}

interface JournalPayload {
    posting_date: string;
    description: string;
    reference_number: string;
    status: string;
    lines: JournalLine[];
    mda?: string | null;
    fund?: string | null;
    function?: string | null;
    program?: string | null;
    geo?: string | null;
}

const JournalForm = () => {
    const navigate = useNavigate();
    // /accounting/new           → create mode
    // /accounting/journals/:id/edit → edit mode (Draft only; backend rejects Posted edits)
    const { id: idParam } = useParams<{ id?: string }>();
    const editingId = idParam ? Number(idParam) : null;
    const isEditMode = editingId !== null && !Number.isNaN(editingId);

    const { data: dims, isLoading: dimsLoading } = useDimensions();
    const { data: fixedAssets = [] } = useFixedAssets();
    const { isEnabled: dimensionsEnabled } = useIsDimensionsEnabled();
    const { formatCurrency } = useCurrency();
    const createJournal = useCreateJournal();
    const updateJournal = useUpdateJournal();
    const { data: existingJournal, isLoading: journalLoading } = useJournalDetail(isEditMode ? editingId : null);
    const downloadTemplate = useDownloadJournalTemplate();
    const bulkImport = useBulkImportJournals();
    // One-shot hydration guard — populating state only the first time the
    // journal data arrives prevents wiping the user's in-progress edits if
    // React Query refetches in the background.
    const [hydrated, setHydrated] = useState(false);
    const fileInputRef = useRef<HTMLInputElement>(null);
    const [formError, setFormError] = useState('');
    const [showImport, setShowImport] = useState(false);
    const { addToast } = useToast();
    const [importResult, setImportResult] = useState<{ created: number; skipped: number; errors: string[] } | null>(null);

    const [header, setHeader] = useState({
        posting_date: todayLocalISO(),
        description: '',
        reference_number: '',
        mda: '',
        fund: '',
        function: '',
        program: '',
        geo: '',
    });

    // MDA dropdown — required when dimensions are on. The backend
    // JournalHeaderSerializer enforces this; without an MDA, the
    // Appropriation lookup for budget control cannot resolve.
    const { data: mdas = [] } = useMDAs({ is_active: true });

    const [lines, setLines] = useState([
        { id: crypto.randomUUID(), account: '', debit: '0', credit: '0', memo: '', asset: '' },
        { id: crypto.randomUUID(), account: '', debit: '0', credit: '0', memo: '', asset: '' },
    ]);

    // Pre-sort dimension lists by code ascending and shape them for SearchableSelect.
    // Belt-and-braces: useDimensions also sorts accounts, but a stale React Query
    // cache (entries fetched before the hook upgrade) would otherwise display
    // unsorted; this guarantees order on every render.
    type Coded = { id: number | string; code?: string; name?: string };
    const toCodeOptions = (list: Coded[]) =>
        [...list]
            .sort((a, b) => (a.code ?? '').localeCompare(b.code ?? '', undefined, { numeric: true }))
            .map((x) => ({
                value: String(x.id),
                label: x.code ? `${x.code} — ${x.name ?? ''}` : (x.name ?? ''),
                sublabel: x.code ? x.name : undefined,
            }));

    const accountOptions  = useMemo(() => toCodeOptions((dims?.accounts ?? []) as Coded[]),  [dims?.accounts]);
    const fundOptions     = useMemo(() => toCodeOptions((dims?.funds ?? []) as Coded[]),     [dims?.funds]);
    const functionOptions = useMemo(() => toCodeOptions((dims?.functions ?? []) as Coded[]), [dims?.functions]);
    const programOptions  = useMemo(() => toCodeOptions((dims?.programs ?? []) as Coded[]),  [dims?.programs]);
    const geoOptions      = useMemo(() => toCodeOptions((dims?.geos ?? []) as Coded[]),      [dims?.geos]);
    const mdaOptions      = useMemo(() => toCodeOptions(mdas as Coded[]),                    [mdas]);
    // Fixed assets use `asset_number` as their code, not `code`.
    const assetOptions = useMemo(
        () =>
            [...(fixedAssets ?? [])]
                .sort((a, b) => (a.asset_number ?? '').localeCompare(b.asset_number ?? '', undefined, { numeric: true }))
                .map((a) => ({
                    value: String(a.id),
                    label: `${a.asset_number} — ${a.name}`,
                    sublabel: a.name,
                })),
        [fixedAssets],
    );

    // Edit-mode hydration — runs once when the journal detail finishes loading.
    // Posted/Approved entries are never editable: redirect back to the list.
    useEffect(() => {
        if (!isEditMode || hydrated || !existingJournal) return;
        if (existingJournal.status && existingJournal.status !== 'Draft') {
            navigate('/accounting', { replace: true });
            return;
        }
        setHeader({
            posting_date: existingJournal.posting_date || todayLocalISO(),
            description: existingJournal.description || '',
            reference_number: existingJournal.reference_number || '',
            mda: existingJournal.mda ? String(existingJournal.mda) : '',
            fund: existingJournal.fund ? String(existingJournal.fund) : '',
            function: existingJournal.function ? String(existingJournal.function) : '',
            program: existingJournal.program ? String(existingJournal.program) : '',
            geo: existingJournal.geo ? String(existingJournal.geo) : '',
        });
        const incoming = Array.isArray(existingJournal.lines) ? existingJournal.lines : [];
        setLines(
            incoming.length
                ? incoming.map((l: any) => ({
                      id: crypto.randomUUID(),
                      account: l.account ? String(l.account) : '',
                      debit: String(l.debit ?? '0'),
                      credit: String(l.credit ?? '0'),
                      memo: l.memo ?? '',
                      asset: l.asset ? String(l.asset) : '',
                  }))
                : [
                      { id: crypto.randomUUID(), account: '', debit: '0', credit: '0', memo: '', asset: '' },
                      { id: crypto.randomUUID(), account: '', debit: '0', credit: '0', memo: '', asset: '' },
                  ],
        );
        setHydrated(true);
    }, [isEditMode, hydrated, existingJournal, navigate]);

    const totalDebit = lines.reduce((sum, l) => sum + parseFloat(l.debit || '0'), 0);
    const totalCredit = lines.reduce((sum, l) => sum + parseFloat(l.credit || '0'), 0);
    const isBalanced = Math.abs(totalDebit - totalCredit) < 0.01 && totalDebit > 0;

    const addLine = () => setLines([...lines, { id: crypto.randomUUID(), account: '', debit: '0', credit: '0', memo: '', asset: '' }]);
    const removeLine = (index: number) => setLines(lines.filter((_, i) => i !== index));

    const updateLine = (index: number, field: string, value: string) => {
        const newLines = [...lines];
        (newLines[index] as any)[field] = value;
        setLines(newLines);
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!isBalanced) return;

        const payload: JournalPayload = {
            posting_date: header.posting_date,
            description: header.description,
            reference_number: header.reference_number,
            status: 'Draft',
            lines: lines.map(l => ({
                account: l.account,
                debit: parseFloat(l.debit),
                credit: parseFloat(l.credit),
                memo: l.memo,
                // Optional asset tag — omit when not selected so the
                // payload stays minimal for non-asset journals.
                ...(l.asset ? { asset: l.asset } : {}),
            })),
            ...(dimensionsEnabled ? {
                mda: header.mda || null,
                fund: header.fund || null,
                function: header.function || null,
                program: header.program || null,
                geo: header.geo || null,
            } : {}),
        };

        try {
            setFormError('');
            if (isEditMode && editingId !== null) {
                await updateJournal.mutateAsync({ id: editingId, payload: payload as Record<string, unknown> });
            } else {
                await createJournal.mutateAsync(payload);
            }
            navigate('/accounting');
        } catch (err: unknown) {
            // Try the structured-envelope parser first (catches budget /
            // warrant / period_closed errors with the right priority);
            // fall back to formatApiError for plain DRF field-level
            // validation errors so the user still sees "mda: required".
            const fallback = isEditMode ? 'Failed to update journal entry.' : 'Failed to create journal entry.';
            const structured = parsePostingError(err, '');
            const msg = structured || formatApiError(err, fallback);
            setFormError(msg);
            addToast(msg, 'error', 0);
        }
    };

    const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;
        setImportResult(null);
        try {
            const result = await bulkImport.mutateAsync(file);
            setImportResult(result);
        } catch (err: any) {
            const msg = err?.response?.data?.error || 'Import failed.';
            setImportResult({ created: 0, skipped: 0, errors: [msg] });
        }
        // Reset file input so same file can be re-uploaded
        if (fileInputRef.current) fileInputRef.current.value = '';
    };

    if (dimsLoading) return <AccountingLayout><div>Loading dimensions...</div></AccountingLayout>;
    if (isEditMode && (journalLoading || !hydrated)) {
        return <AccountingLayout><LoadingScreen message="Loading journal..." /></AccountingLayout>;
    }

    return (
        <AccountingLayout>
            <form onSubmit={handleSubmit}>
                <PageHeader
                    title={isEditMode ? `Edit Journal Entry${existingJournal?.reference_number ? ` — ${existingJournal.reference_number}` : ''}` : 'New Journal Entry'}
                    subtitle={isEditMode
                        ? 'Modify lines, GL accounts, amounts and dimensions. Posted journals cannot be edited — reverse them instead.'
                        : (dimensionsEnabled
                            ? 'Enter financial details with mandatory dimension tagging.'
                            : 'Enter financial details.')}
                    icon={<Save size={22} />}
                    actions={
                        <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                            {!isEditMode && (
                                <>
                                    <button
                                        type="button"
                                        className="btn btn-outline"
                                        onClick={() => downloadTemplate.mutate()}
                                        disabled={downloadTemplate.isPending}
                                        title="Download CSV template for bulk journal import"
                                    >
                                        <Download size={16} />
                                        {downloadTemplate.isPending ? 'Downloading...' : 'Download Template'}
                                    </button>
                                    <button
                                        type="button"
                                        className="btn btn-outline"
                                        onClick={() => { setShowImport(v => !v); setImportResult(null); }}
                                        title="Import multiple journals from a CSV or Excel file"
                                    >
                                        <Upload size={16} />
                                        Import Journals
                                        {showImport ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                                    </button>

                                    <div style={{ width: 1, height: 28, background: 'var(--border)' }} />
                                </>
                            )}

                            <button type="button" className="btn btn-outline" onClick={() => navigate('/accounting')}>
                                <X size={18} /> Cancel
                            </button>
                            <button type="submit" className="btn btn-primary" disabled={!isBalanced || createJournal.isPending || updateJournal.isPending}>
                                <Save size={18} /> {isEditMode ? 'Save Changes' : 'Save Draft'}
                            </button>
                        </div>
                    }
                />

                {/* ── Hidden file input ── */}
                <input
                    ref={fileInputRef}
                    type="file"
                    accept=".csv,.xlsx,.xls"
                    style={{ display: 'none' }}
                    onChange={handleImport}
                />

                {/* ── Collapsible import panel ── */}
                {showImport && (
                    <div className="card" style={{ marginBottom: '1.5rem', border: '1px dashed var(--border)' }}>
                        <div style={{ display: 'flex', gap: '1.5rem', alignItems: 'flex-start', flexWrap: 'wrap' }}>
                            <div style={{ flex: '1 1 280px', minWidth: 0 }}>
                                <p style={{ fontWeight: 600, marginBottom: '0.35rem', fontSize: 'var(--text-sm)' }}>
                                    Bulk Import from CSV / Excel
                                </p>
                                <p style={{ color: 'var(--text-muted)', fontSize: 'var(--text-xs)', margin: 0, lineHeight: 1.6 }}>
                                    Each row represents one journal line. Rows sharing the same <strong>reference_number</strong> are
                                    grouped into one journal entry. Required columns:&nbsp;
                                    <code>reference_number</code>, <code>posting_date</code>, <code>description</code>,&nbsp;
                                    <code>account_code</code>, <code>debit</code>, <code>credit</code>.
                                    Download the template above for a ready-to-fill example.
                                </p>
                            </div>
                            <button
                                type="button"
                                className="btn btn-primary"
                                onClick={() => fileInputRef.current?.click()}
                                disabled={bulkImport.isPending}
                                style={{ whiteSpace: 'nowrap', flexShrink: 0 }}
                            >
                                {bulkImport.isPending ? (
                                    <>Importing…</>
                                ) : (
                                    <><FileUp size={16} /> Choose File &amp; Import</>
                                )}
                            </button>
                        </div>

                        {/* ── Import result ── */}
                        {importResult && (
                            <div style={{ marginTop: '1rem', paddingTop: '1rem', borderTop: '1px solid var(--border)' }}>
                                {importResult.created > 0 && (
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--success, #16a34a)', fontSize: 'var(--text-sm)', marginBottom: '0.4rem' }}>
                                        <CheckCircle size={15} />
                                        <strong>{importResult.created}</strong> journal{importResult.created !== 1 ? 's' : ''} created successfully.
                                    </div>
                                )}
                                {importResult.skipped > 0 && (
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--warning, #d97706)', fontSize: 'var(--text-sm)', marginBottom: '0.4rem' }}>
                                        <AlertCircle size={15} />
                                        <strong>{importResult.skipped}</strong> row{importResult.skipped !== 1 ? 's' : ''} skipped (duplicate reference or invalid data).
                                    </div>
                                )}
                                {importResult.errors.length > 0 && (
                                    <div style={{ marginTop: '0.5rem' }}>
                                        <p style={{ fontWeight: 600, fontSize: 'var(--text-xs)', color: 'var(--error)', marginBottom: '0.35rem' }}>
                                            Errors ({importResult.errors.length}):
                                        </p>
                                        <ul style={{ margin: 0, paddingLeft: '1.25rem', fontSize: 'var(--text-xs)', color: 'var(--error)', lineHeight: 1.7 }}>
                                            {importResult.errors.map((e, i) => <li key={i}>{e}</li>)}
                                        </ul>
                                    </div>
                                )}
                                {importResult.created > 0 && importResult.errors.length === 0 && (
                                    <p style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)', margin: '0.4rem 0 0' }}>
                                        Import complete. <button type="button" style={{ background: 'none', border: 'none', color: 'var(--primary)', cursor: 'pointer', padding: 0, fontSize: 'inherit' }} onClick={() => navigate('/accounting')}>View in journal list →</button>
                                    </p>
                                )}
                            </div>
                        )}
                    </div>
                )}

                {formError && (
                    <div style={{ padding: '0.75rem 1rem', background: '#fee2e2', color: '#dc2626', borderRadius: '8px', marginBottom: '1.5rem', fontSize: 'var(--text-sm)' }}>
                        {formError}
                    </div>
                )}

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1.5rem', marginBottom: '2.5rem' }}>
                    <div className="card">
                        <label className="label">Posting Date<span className="required-mark"> *</span></label>
                        <input type="date" value={header.posting_date} onChange={e => setHeader({ ...header, posting_date: e.target.value })} required />
                    </div>
                    <div className="card">
                        <label className="label">Reference #<span className="required-mark"> *</span></label>
                        <input type="text" placeholder="e.g. JV-2024-001" value={header.reference_number} onChange={e => setHeader({ ...header, reference_number: e.target.value })} required />
                    </div>
                    <div className="card" style={{ gridColumn: 'span 2' }}>
                        <label className="label">Header Description<span className="required-mark"> *</span></label>
                        <input type="text" placeholder="Purpose of this entry" value={header.description} onChange={e => setHeader({ ...header, description: e.target.value })} required />
                    </div>
                </div>

                {dimensionsEnabled && (
                    <div className="card" style={{ marginBottom: '2.5rem' }}>
                        <h3 style={{ marginBottom: '1.25rem', fontSize: 'var(--text-base)' }}>Mandatory Dimensions</h3>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '1rem' }}>
                            <div>
                                <label className="label">MDA<span className="required-mark"> *</span></label>
                                <SearchableSelect
                                    options={mdaOptions}
                                    value={header.mda}
                                    onChange={(v) => setHeader({ ...header, mda: v })}
                                    placeholder="Search MDA…"
                                    required
                                />
                            </div>
                            <div>
                                <label className="label">Fund<span className="required-mark"> *</span></label>
                                <SearchableSelect
                                    options={fundOptions}
                                    value={header.fund}
                                    onChange={(v) => setHeader({ ...header, fund: v })}
                                    placeholder="Search Fund…"
                                    required
                                />
                            </div>
                            <div>
                                <label className="label">Function<span className="required-mark"> *</span></label>
                                <SearchableSelect
                                    options={functionOptions}
                                    value={header.function}
                                    onChange={(v) => setHeader({ ...header, function: v })}
                                    placeholder="Search Function…"
                                    required
                                />
                            </div>
                            <div>
                                <label className="label">Program<span className="required-mark"> *</span></label>
                                <SearchableSelect
                                    options={programOptions}
                                    value={header.program}
                                    onChange={(v) => setHeader({ ...header, program: v })}
                                    placeholder="Search Program…"
                                    required
                                />
                            </div>
                            <div>
                                <label className="label">Geography (Geo)<span className="required-mark"> *</span></label>
                                <SearchableSelect
                                    options={geoOptions}
                                    value={header.geo}
                                    onChange={(v) => setHeader({ ...header, geo: v })}
                                    placeholder="Search Geo…"
                                    required
                                />
                            </div>
                        </div>
                    </div>
                )}

                <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                    {/* Horizontal scroll on narrow viewports keeps the line columns
                        readable rather than squashing dropdowns into 40px cells. */}
                    <div style={{ overflowX: 'auto', WebkitOverflowScrolling: 'touch' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 760 }}>
                        <thead>
                            <tr style={{ background: 'var(--background)', textAlign: 'left' }}>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)' }}>GL Account</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', width: '150px' }}>Debit</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', width: '150px' }}>Credit</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)' }}>Memo</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', width: '220px' }} title="Tag this line to a Fixed Asset for depreciation / disposal / cost accumulation posting">
                                    Asset <span style={{ fontWeight: 400, color: 'var(--color-text-muted)' }}>(optional)</span>
                                </th>
                                <th style={{ padding: '1rem', width: '50px' }}></th>
                            </tr>
                        </thead>
                        <tbody>
                            {lines.map((line, idx) => (
                                <tr key={line.id} style={{ borderBottom: '1px solid var(--border)' }}>
                                    <td style={{ padding: '0.75rem' }}>
                                        <SearchableSelect
                                            options={accountOptions}
                                            value={line.account}
                                            onChange={(v) => updateLine(idx, 'account', v)}
                                            placeholder="Search code or name…"
                                            required
                                        />
                                    </td>
                                    <td style={{ padding: '0.75rem' }}>
                                        <input type="number" step="0.01" value={line.debit} onChange={e => updateLine(idx, 'debit', e.target.value)} />
                                    </td>
                                    <td style={{ padding: '0.75rem' }}>
                                        <input type="number" step="0.01" value={line.credit} onChange={e => updateLine(idx, 'credit', e.target.value)} />
                                    </td>
                                    <td style={{ padding: '0.75rem' }}>
                                        <input type="text" placeholder="Line memo" value={line.memo} onChange={e => updateLine(idx, 'memo', e.target.value)} />
                                    </td>
                                    <td style={{ padding: '0.75rem' }}>
                                        <SearchableSelect
                                            options={assetOptions}
                                            value={line.asset || ''}
                                            onChange={(v) => updateLine(idx, 'asset', v)}
                                            placeholder="— No asset —"
                                        />
                                    </td>
                                    <td style={{ padding: '0.75rem' }}>
                                        {lines.length > 2 && (
                                            <button type="button" onClick={() => removeLine(idx)} style={{ color: 'var(--error)', background: 'none', border: 'none', cursor: 'pointer' }}>
                                                <Trash2 size={18} />
                                            </button>
                                        )}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                        <tfoot>
                            <tr style={{ background: 'var(--surface)' }}>
                                <td style={{ padding: '1rem' }}>
                                    <button type="button" className="btn btn-outline" style={{ fontSize: 'var(--text-xs)' }} onClick={addLine}>
                                        <Plus size={14} /> Add Line
                                    </button>
                                </td>
                                <td style={{ padding: '1rem', fontWeight: 700, textAlign: 'right', borderTop: '2px solid var(--border)' }}>{formatCurrency(totalDebit)}</td>
                                <td style={{ padding: '1rem', fontWeight: 700, textAlign: 'right', borderTop: '2px solid var(--border)' }}>{formatCurrency(totalCredit)}</td>
                                <td colSpan={3} style={{ padding: '1rem' }}>
                                    {!isBalanced && totalDebit > 0 && (
                                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--error)', fontSize: 'var(--text-xs)' }}>
                                            <AlertCircle size={14} /> Entry is not balanced
                                        </div>
                                    )}
                                </td>
                            </tr>
                        </tfoot>
                    </table>
                    </div>
                </div>
            </form>
            <style>{`
                .label {
                    display: block; 
                    margin-bottom: 0.5rem; 
                    font-size: 0.75rem; 
                    font-weight: 600; 
                    text-transform: uppercase; 
                    color: var(--text-muted);
                }
            `}</style>
        </AccountingLayout>
    );
};

export default JournalForm;
