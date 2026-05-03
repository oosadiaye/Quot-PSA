/**
 * Government IFMIS Page Definitions — Quot PSE
 * Each page wraps GenericListPage with appropriate column configuration.
 * Includes Create/Action buttons for data entry.
 */
import { useRef, useState, useEffect, useMemo } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useQueryClient, useMutation, useQuery } from '@tanstack/react-query';
import { Plus, Download, Upload, RefreshCw, FileDown, CheckCircle2, AlertCircle, BookOpen, Trash2 } from 'lucide-react';
import GenericListPage from '../../components/GenericListPage';
import Sidebar from '../../components/Sidebar';
import SearchableSelect from '../../components/SearchableSelect';
import { downloadNCoATemplate, useNCoABulkImport, type NCoASegmentType, type BulkImportResult } from '../../hooks/useNCoAImportExport';
import { useNCoASegments, useFiscalYears } from '../../hooks/useGovForms';
import apiClient from '../../api/client';

/** Helper to make icon elements for buttons */
const icon = (Icon: typeof Plus) => <Icon size={15} />;

/** Banner shown after a bulk import completes */
function ImportResultBanner({ result, onDismiss }: { result: BulkImportResult; onDismiss: () => void }) {
    const hasErrors = result.errors.length > 0;
    return (
        <div style={{
            margin: '0 0 16px', padding: '14px 20px', borderRadius: 8,
            background: hasErrors ? '#fff3cd' : '#d4edda',
            border: `1px solid ${hasErrors ? '#ffc107' : '#28a745'}`,
            display: 'flex', gap: 12, alignItems: 'flex-start',
        }}>
            {hasErrors
                ? <AlertCircle size={20} color="#856404" style={{ flexShrink: 0, marginTop: 2 }} />
                : <CheckCircle2 size={20} color="#155724" style={{ flexShrink: 0, marginTop: 2 }} />}
            <div style={{ flex: 1 }}>
                <strong>{result.created} created, {result.updated} updated, {result.skipped} skipped</strong>
                {hasErrors && (
                    <ul style={{ margin: '6px 0 0', paddingLeft: 20, fontSize: 13, color: '#856404' }}>
                        {result.errors.slice(0, 5).map((e, i) => <li key={i}>{e}</li>)}
                        {result.errors.length > 5 && <li>...and {result.errors.length - 5} more</li>}
                    </ul>
                )}
            </div>
            <button onClick={onDismiss} style={{
                background: 'none', border: 'none', cursor: 'pointer', fontSize: 18, color: '#666',
            }}>&times;</button>
        </div>
    );
}

/** Reusable wrapper for NCoA segment pages with Template/Import/Add buttons */
function NCoASegmentPage({
    title, subtitle, endpoint, columns, segmentType, addLabel, addPath,
    enableDelete = false,
}: {
    title: string;
    subtitle: string;
    endpoint: string;
    columns: { key: string; label: string; width?: string }[];
    segmentType: NCoASegmentType;
    addLabel: string;
    addPath: string;
    /**
     * Surface per-row + bulk Delete actions. Off by default so existing
     * segments (Administrative, Economic, …) keep their current UX; opt in
     * per segment as needed. The backend's ``on_delete=PROTECT`` rules
     * remain the ultimate guard against orphaning composite NCoA codes.
     */
    enableDelete?: boolean;
}) {
    const nav = useNavigate();
    const qc = useQueryClient();
    const fileRef = useRef<HTMLInputElement>(null);
    const [importResult, setImportResult] = useState<BulkImportResult | null>(null);
    const importMutation = useNCoABulkImport(segmentType);

    const handleImportFile = (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;
        importMutation.mutate(file, {
            onSuccess: (data) => setImportResult(data),
        });
        e.target.value = '';
    };

    /**
     * Per-row delete with code echo-back confirmation.
     *
     * Two-step confirm prevents muscle-memory wipes on rows that may be
     * referenced by composite NCoA codes / appropriations / GL postings.
     * PROTECT errors from the backend surface as friendly alerts.
     */
    const handleDeleteRow = async (item: Record<string, unknown>) => {
        const code = String(item.code ?? '');
        const name = String(item.name ?? '');
        const id = item.id;
        const first = window.confirm(
            `Delete ${title} "${name}" (${code})?\n\n` +
            `This cannot be undone. Segments referenced by NCoA composite codes, ` +
            `appropriations, or posted journals cannot be deleted — deactivate them ` +
            `instead (set Active = false).`
        );
        if (!first) return;
        const typed = window.prompt(`Type the code (${code}) to confirm deletion:`);
        if (typed?.trim() !== code) {
            if (typed !== null) window.alert('Code did not match — deletion cancelled.');
            return;
        }
        try {
            await apiClient.delete(`${endpoint}${id}/`);
            qc.invalidateQueries({ queryKey: ['generic-list', endpoint] });
            qc.invalidateQueries({ queryKey: ['ncoa-segments-all'] });
        } catch (err: unknown) {
            const e = err as { response?: { data?: { detail?: string; error?: string } }; message?: string };
            const msg =
                e?.response?.data?.detail ||
                e?.response?.data?.error ||
                e?.message ||
                'Delete failed. The segment may be referenced by other records.';
            window.alert(`Could not delete: ${msg}`);
        }
    };

    /**
     * Bulk-delete handler — same echo-back semantics scaled for multi-row.
     * Single ``DELETE`` confirmation phrase ("DELETE") rather than a per-row
     * code echo because typing 50 codes is impractical. PROTECT failures are
     * collected and shown together at the end.
     */
    const handleBulkDelete = async (items: Record<string, unknown>[]) => {
        if (items.length === 0) return;
        const codes = items.map(it => String(it.code ?? '')).filter(Boolean);
        const preview = codes.slice(0, 5).join(', ') + (codes.length > 5 ? `, +${codes.length - 5} more` : '');
        const first = window.confirm(
            `Delete ${items.length} ${title} record${items.length === 1 ? '' : 's'}?\n\n` +
            `Codes: ${preview}\n\n` +
            `Records referenced by NCoA codes / appropriations / journals will be skipped.`
        );
        if (!first) return;
        const typed = window.prompt(`Type DELETE to confirm removing ${items.length} record${items.length === 1 ? '' : 's'}:`);
        if (typed?.trim().toUpperCase() !== 'DELETE') {
            if (typed !== null) window.alert('Confirmation phrase did not match — bulk delete cancelled.');
            return;
        }
        const failures: Array<{ code: string; reason: string }> = [];
        for (const item of items) {
            try {
                await apiClient.delete(`${endpoint}${item.id}/`);
            } catch (err: unknown) {
                const e = err as { response?: { data?: { detail?: string; error?: string } }; message?: string };
                failures.push({
                    code: String(item.code ?? item.id),
                    reason: e?.response?.data?.detail || e?.response?.data?.error || e?.message || 'Unknown error',
                });
            }
        }
        qc.invalidateQueries({ queryKey: ['generic-list', endpoint] });
        qc.invalidateQueries({ queryKey: ['ncoa-segments-all'] });
        if (failures.length > 0) {
            const lines = failures.map(f => `  • ${f.code}: ${f.reason}`).join('\n');
            const ok = items.length - failures.length;
            window.alert(
                `${ok} of ${items.length} record${items.length === 1 ? '' : 's'} deleted.\n\n` +
                `Could not delete:\n${lines}`
            );
        }
    };

    return (
        <>
            <input
                ref={fileRef} type="file" accept=".csv,.xlsx"
                style={{ display: 'none' }} onChange={handleImportFile}
            />
            {importResult && (
                <div style={{ marginLeft: 260, paddingTop: 16, paddingRight: 24 }}>
                    <ImportResultBanner result={importResult} onDismiss={() => setImportResult(null)} />
                </div>
            )}
            <GenericListPage
                title={title}
                subtitle={subtitle}
                endpoint={endpoint}
                columns={columns}
                actions={[
                    {
                        label: 'Template',
                        onClick: () => downloadNCoATemplate(segmentType),
                        variant: 'secondary',
                        icon: icon(FileDown),
                    },
                    {
                        label: importMutation.isPending ? 'Importing...' : 'Import',
                        onClick: () => fileRef.current?.click(),
                        variant: 'secondary',
                        icon: icon(Upload),
                    },
                    {
                        label: addLabel,
                        onClick: () => nav(addPath),
                        variant: 'primary',
                        icon: icon(Plus),
                    },
                ]}
                bulkActions={enableDelete ? [
                    {
                        label: 'Delete Selected',
                        icon: <Trash2 size={14} />,
                        variant: 'danger',
                        onClick: handleBulkDelete,
                    },
                ] : undefined}
                rowActions={{
                    onEdit: (item) => nav(`/accounting/ncoa/${segmentType}/${item.id}/edit`),
                    ...(enableDelete ? { onDelete: handleDeleteRow } : {}),
                }}
            />
        </>
    );
}

/* ── Budget & Appropriation ────────────────────────────── */

/**
 * Appropriations — single-page SAP-Fiori-style line-item view.
 *
 * Replaces the old two-step navigation (rollup → drilldown). One screen
 * with two type-ahead filters at the top:
 *
 *   • Fiscal Year — defaults to the active FY (status='Open' && is_active),
 *                   falls back to most recent open year, finally most recent.
 *   • MDA         — optional. When empty, shows all MDAs for the FY.
 *
 * KPI strip (Approved / Expended / Available / Execution Rate) summarises
 * whatever the filters currently scope to.
 *
 * Table styling mimics SAP Fiori line-item reports — dense grid with
 * uppercase column headers, multi-line cells where a code + descriptive
 * label coexist (e.g. Programme cell shows code on top, MDA name below),
 * monetary columns right-aligned with semantic colour (red expended,
 * green available, neutral approved), status pill column at the end.
 *
 * Click a row → navigate to the appropriation detail/edit page.
 * Bulk-delete (Draft-only) lives in the contextual action bar.
 */
export const AppropriationList = () => {
    const nav = useNavigate();
    const fileRef = useRef<HTMLInputElement>(null);
    const qc = useQueryClient();
    const [importResult, setImportResult] = useState<BulkImportResult | null>(null);
    const [isImporting, setIsImporting] = useState(false);

    // Filter state.
    //  • filterFyId holds the FY's *id* (not 4-digit year) so we can pass
    //    it straight to the backend's filterset_fields=['fiscal_year'].
    //  • filterMdaId is the AdministrativeSegment FK id.
    // Both empty = unfiltered (whole tenant). Initial values can come from
    // ?mda=... / ?fy=... URL params (legacy redirect compatibility).
    const initialUrlParams = useMemo(() => new URLSearchParams(window.location.search), []);
    const [filterMdaId, setFilterMdaId] = useState<string>(initialUrlParams.get('mda') || '');
    const [filterFyId, setFilterFyId] = useState<string>(initialUrlParams.get('fy') || '');


    // NCoA Administrative Segments for the MDA filter dropdown.
    const { data: segments } = useNCoASegments();
    const mdaOptions = useMemo(() => (segments?.administrative ?? []).map((m: any) => ({
        value: String(m.id),
        label: `${m.code} — ${m.name}`,
        sublabel: m.code,
    })), [segments]);

    // Fiscal years for the FY filter.
    const { data: fiscalYears = [] } = useFiscalYears();
    type FY = { id: number; year: number; name?: string; status?: string; is_active?: boolean };
    const fyList = (fiscalYears as FY[]) || [];
    const fyOptions = useMemo(() => fyList.map(fy => ({
        value: String(fy.id),
        label: fy.name || `FY ${fy.year}`,
        sublabel: String(fy.year),
    })), [fyList]);

    // Default to the currently-active FY the moment the FY list loads.
    // Priority: is_active=true → status='Open' → most recent year.
    useEffect(() => {
        if (filterFyId || fyList.length === 0) return;
        const active = fyList.find(fy => fy.is_active)
            || fyList.find(fy => fy.status === 'Open')
            || [...fyList].sort((a, b) => b.year - a.year)[0];
        if (active) setFilterFyId(String(active.id));
    }, [fyList, filterFyId]);

    // Selected FY — used in the subtitle to confirm which year is in scope.
    const selectedFy = useMemo(() => fyList.find(fy => String(fy.id) === filterFyId), [fyList, filterFyId]);

    // This page is the *rollup* view only. One row per MDA. Clicking a row
    // deep-links to the existing AppropriationDetail page (image #2 in the
    // design), which renders the MDA-level KPI strip + every line under that
    // MDA/FY. No second "detail-mode" pane lives here — the flow is two
    // pages: this rollup → AppropriationDetail.
    const rollupEndpoint = useMemo(() => {
        const params = new URLSearchParams();
        if (filterFyId) params.set('fiscal_year', filterFyId);
        if (filterMdaId) params.set('administrative', filterMdaId);
        // The viewset's pagination class caps responses at PAGE_SIZE=20
        // unless overridden. The rollup view is meant to show every MDA
        // in one screen so we ask for plenty of room — capped server-side
        // by max_page_size=10000 as a safety belt.
        params.set('page_size', '5000');
        return `/budget/appropriations/by-mda/?${params.toString()}`;
    }, [filterFyId, filterMdaId]);

    // Rollup row shape mirrors what `AppropriationViewSet.by_mda` returns.
    type RollupRow = {
        id: string;                     // composite "<mda_id>-<fy_id>"
        mda_id: number;
        mda_code?: string;
        mda_name?: string;
        fiscal_year_id?: number;
        fiscal_year_label?: string;
        appropriation_count: number;
        amount_approved: string | number;
        total_expended: string | number;
        available_balance: string | number;
        execution_rate: string | number;
        sample_appropriation_id?: number;
        status?: string;
        dominant_status?: string;
        status_counts?: Record<string, number>;
        draft_count?: number;
        all_draft?: boolean;
        draft_appropriation_ids?: number[];
        approvable_appropriation_ids?: number[];
        activatable_appropriation_ids?: number[];
    };
    const { data: rollupData, isLoading } = useQuery({
        queryKey: ['appropriations-rollup', filterFyId, filterMdaId],
        queryFn: async () => {
            const res = await apiClient.get(rollupEndpoint);
            return (res.data?.results || res.data || []) as RollupRow[];
        },
        staleTime: 30_000,
    });
    const rollupRows = rollupData ?? [];

    // Bulk-delete selection — keyed by composite rollup id ("<mda>-<fy>")
    // so the same MDA can be selected for different FYs without collision.
    const [selectedRollupIds, setSelectedRollupIds] = useState<Set<string>>(new Set());
    useEffect(() => { setSelectedRollupIds(new Set()); }, [filterFyId, filterMdaId]);

    // Eligibility per action — we keep separate buckets so the bulk-bar
    // buttons can stay enabled/disabled independently based on what's
    // actually transitionable in the current selection.
    const selectedRows = useMemo(
        () => rollupRows.filter(r => selectedRollupIds.has(r.id)),
        [rollupRows, selectedRollupIds],
    );
    const selectedDraftIds = useMemo(
        () => selectedRows.flatMap(r => r.draft_appropriation_ids ?? []),
        [selectedRows],
    );
    const selectedApprovableIds = useMemo(
        () => selectedRows.flatMap(r => r.approvable_appropriation_ids ?? []),
        [selectedRows],
    );
    const selectedActivatableIds = useMemo(
        () => selectedRows.flatMap(r => r.activatable_appropriation_ids ?? []),
        [selectedRows],
    );

    // Any row that has at least one transitionable line is selectable.
    // (A fully-Closed MDA, for instance, has nothing to act on.)
    const isRowActionable = (r: RollupRow): boolean => Boolean(
        (r.draft_appropriation_ids?.length ?? 0)
        + (r.approvable_appropriation_ids?.length ?? 0)
        + (r.activatable_appropriation_ids?.length ?? 0)
    );
    const actionableRows = useMemo(
        () => rollupRows.filter(isRowActionable),
        [rollupRows],
    );
    const allActionableSelected = actionableRows.length > 0
        && actionableRows.every(r => selectedRollupIds.has(r.id));
    const toggleAllActionable = () => {
        if (allActionableSelected) setSelectedRollupIds(new Set());
        else setSelectedRollupIds(new Set(actionableRows.map(r => r.id)));
    };
    const toggleOneRollup = (id: string) => {
        setSelectedRollupIds(prev => {
            const next = new Set(prev);
            if (next.has(id)) next.delete(id); else next.add(id);
            return next;
        });
    };

    /**
     * Generic bulk-action runner. Collects the right id bucket for the
     * action, fires the server endpoint, surfaces transitioned/skipped
     * counts, and refreshes the rollup. Returns void; UX handled inline.
     */
    type BulkActionConfig = {
        endpoint: string;
        ids: number[];
        verb: 'delete' | 'approve' | 'activate';
        confirmPhrase: 'DELETE' | 'APPROVE' | 'ACTIVATE';
        successKey: 'deleted' | 'transitioned';
    };
    const runBulkAction = async (cfg: BulkActionConfig) => {
        if (selectedRows.length === 0) return;
        if (cfg.ids.length === 0) {
            window.alert(`No lines eligible to ${cfg.verb} in the selection.`);
            return;
        }
        const mdaList = selectedRows.map(r => r.mda_name || r.mda_code || `#${r.mda_id}`).slice(0, 5).join(', ');
        const more = selectedRows.length > 5 ? `, +${selectedRows.length - 5} more` : '';
        const verbCap = cfg.verb.charAt(0).toUpperCase() + cfg.verb.slice(1);
        const undoNote = cfg.verb === 'delete' ? 'This cannot be undone.\n\n' : '';
        const eligibilityNote = cfg.verb === 'delete'
            ? 'Only Draft lines are eligible.'
            : cfg.verb === 'approve'
                ? 'Only Draft and Submitted lines will be transitioned to Approved.'
                : 'Only Approved and Submitted lines will be transitioned to Active.';
        const first = window.confirm(
            `${verbCap} draft budget across ${selectedRows.length} MDA${selectedRows.length === 1 ? '' : 's'}?\n\n` +
            `MDAs: ${mdaList}${more}\n` +
            `Eligible lines: ${cfg.ids.length}\n\n` +
            `${eligibilityNote}\n${undoNote}`
        );
        if (!first) return;
        const typed = window.prompt(`Type ${cfg.confirmPhrase} to confirm ${cfg.verb} on ${cfg.ids.length} line${cfg.ids.length === 1 ? '' : 's'}:`);
        if (typed?.trim().toUpperCase() !== cfg.confirmPhrase) {
            if (typed !== null) window.alert('Confirmation phrase did not match — cancelled.');
            return;
        }
        try {
            const res = await apiClient.post(cfg.endpoint, { ids: cfg.ids });
            const data = res.data as Record<string, unknown> & {
                skipped?: number;
                skipped_details?: Array<{ id: number; code: string; status: string }>;
            };
            qc.invalidateQueries({ queryKey: ['appropriations-rollup'] });
            qc.invalidateQueries({ queryKey: ['generic-list'] });
            setSelectedRollupIds(new Set());
            const successCount = Number(data[cfg.successKey] ?? 0);
            const skipped = Number(data.skipped ?? 0);
            const past = cfg.verb === 'delete' ? 'deleted'
                : cfg.verb === 'approve' ? 'approved' : 'activated';
            if (skipped > 0) {
                const lines = (data.skipped_details ?? []).slice(0, 8).map(d => `  • ${d.code || `#${d.id}`} (${d.status})`).join('\n');
                window.alert(`${successCount} line${successCount === 1 ? '' : 's'} ${past}.\n${skipped} skipped (ineligible status):\n${lines}`);
            } else {
                window.alert(`${successCount} line${successCount === 1 ? '' : 's'} ${past} across ${selectedRows.length} MDA${selectedRows.length === 1 ? '' : 's'}.`);
            }
        } catch (err: unknown) {
            const e = err as { response?: { data?: { detail?: string; error?: string } }; message?: string };
            window.alert(`Could not ${cfg.verb}: ${e?.response?.data?.detail || e?.response?.data?.error || e?.message || 'Bulk action failed.'}`);
        }
    };
    const handleBulkDeleteMdaDrafts = () => runBulkAction({
        endpoint: '/budget/appropriations/bulk-delete/',
        ids: selectedDraftIds,
        verb: 'delete',
        confirmPhrase: 'DELETE',
        successKey: 'deleted',
    });
    const handleBulkApprove = () => runBulkAction({
        endpoint: '/budget/appropriations/bulk-approve/',
        ids: selectedApprovableIds,
        verb: 'approve',
        confirmPhrase: 'APPROVE',
        successKey: 'transitioned',
    });
    const handleBulkActivate = () => runBulkAction({
        endpoint: '/budget/appropriations/bulk-activate/',
        ids: selectedActivatableIds,
        verb: 'activate',
        confirmPhrase: 'ACTIVATE',
        successKey: 'transitioned',
    });

    // KPI strip: sum the rollup rows. The backend has already summed lines
    // per MDA, so this is a sum-of-sums across whatever MDAs match.
    const totals = useMemo(() => {
        const num = (v: unknown) => Number(v ?? 0) || 0;
        const approved = rollupRows.reduce((s, r) => s + num(r.amount_approved), 0);
        const expended = rollupRows.reduce((s, r) => s + num(r.total_expended), 0);
        const available = approved - expended;
        const execRate = approved > 0 ? (expended / approved) * 100 : 0;
        return { approved, expended, available, execRate };
    }, [rollupRows]);

    // Naira formatter — locale en-NG so thousand separators match Nigerian
    // convention. Two decimals always shown for kobo precision.
    const fmtNaira = (v: number) => `₦${v.toLocaleString('en-NG', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

    // Status pill colour map. Draft = neutral grey; everything else gets a
    // semantic tint so an auditor can scan the column at a glance.
    const statusStyle = (s: string): { bg: string; fg: string } => {
        const k = (s || '').toUpperCase();
        if (k === 'DRAFT') return { bg: '#f1f5f9', fg: '#475569' };
        if (k === 'PENDING') return { bg: '#fef3c7', fg: '#92400e' };
        if (k === 'APPROVED') return { bg: '#dbeafe', fg: '#1e40af' };
        if (k === 'ACTIVE') return { bg: '#dcfce7', fg: '#166534' };
        if (k === 'CLOSED') return { bg: '#fee2e2', fg: '#991b1b' };
        if (k === 'REVISED') return { bg: '#ede9fe', fg: '#5b21b6' };
        return { bg: '#f1f5f9', fg: '#475569' };
    };

    // Download the CSV template from the backend (single source of truth —
    // never hardcode template content on the frontend, that's where drift
    // creeps in. See ChartOfAccounts.tsx history for the precedent.)
    const handleTemplate = async () => {
        try {
            const res = await apiClient.get('/budget/appropriations/import-template/', {
                responseType: 'blob',
            });
            const url = window.URL.createObjectURL(new Blob([res.data], { type: 'text/csv' }));
            const a = document.createElement('a');
            a.href = url;
            a.download = 'appropriation_import_template.csv';
            a.click();
            window.URL.revokeObjectURL(url);
        } catch {
            window.alert('Could not download the template. Check your connection and try again.');
        }
    };

    const handleExport = async () => {
        try {
            const res = await apiClient.get('/budget/appropriations/export/', {
                responseType: 'blob',
            });
            const url = window.URL.createObjectURL(new Blob([res.data], { type: 'text/csv' }));
            const a = document.createElement('a');
            a.href = url;
            a.download = 'appropriations_export.csv';
            a.click();
            window.URL.revokeObjectURL(url);
        } catch {
            window.alert('Failed to export appropriations.');
        }
    };

    const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;
        setIsImporting(true);
        setImportResult(null);
        try {
            const fd = new FormData();
            fd.append('file', file);
            // Same Content-Type override pattern as every other bulk import in
            // this codebase — without it, axios JSON-serialises the FormData
            // and the backend's request.FILES is empty.
            const res = await apiClient.post(
                '/budget/appropriations/bulk-import/',
                fd,
                { headers: { 'Content-Type': 'multipart/form-data' } },
            );
            setImportResult(res.data);
            qc.invalidateQueries({ queryKey: ['generic-list'] });
        } catch (err: any) {
            setImportResult({
                success: false,
                created: 0,
                skipped: 0,
                errors: [err.response?.data?.error || 'Import failed. Check the file format.'],
            });
        } finally {
            setIsImporting(false);
            if (fileRef.current) fileRef.current.value = '';
        }
    };

    // Click handler — deep-link from a rollup row to the existing
    // AppropriationDetail page. Prefers the `sample_appropriation_id`
    // included in the rollup payload (one round trip on first paint, zero
    // on click). When the backend hasn't been rolled with that field yet
    // (older deployment), we fall back to fetching the first matching
    // appropriation id at click-time so the click still works.
    const onRollupRowClick = async (r: RollupRow) => {
        if (r.sample_appropriation_id) {
            nav(`/budget/appropriations/${r.sample_appropriation_id}`);
            return;
        }
        // Defensive fallback for backends that pre-date sample_appropriation_id.
        try {
            const params = new URLSearchParams();
            params.set('administrative', String(r.mda_id));
            if (r.fiscal_year_id) params.set('fiscal_year', String(r.fiscal_year_id));
            params.set('page_size', '1');
            params.set('ordering', 'id');
            const res = await apiClient.get(`/budget/appropriations/?${params.toString()}`);
            const first = (res.data?.results || res.data || [])[0];
            if (first?.id) {
                nav(`/budget/appropriations/${first.id}`);
                return;
            }
            window.alert('No appropriation lines found under this MDA — cannot open detail.');
        } catch (err) {
            window.alert('Could not open the MDA details. Try refreshing the page.');
        }
    };

    // Page title — this page is *always* the by-MDA rollup, so the title
    // stays "All MDAs". The MDA filter dropdown only narrows the rollup; it
    // doesn't change the page identity. The selected-MDA name appears on
    // the detail page (AppropriationDetail), not here.
    const pageTitle = 'NCoA Budget Classification — All MDAs';
    const pageSubtitle = selectedFy
        ? `Fiscal Year ${selectedFy.year}${selectedFy.is_active ? ' · Active' : ''}`
        : 'No fiscal year selected';

    return (
        <>
            <Sidebar />
            <input ref={fileRef} type="file" accept=".csv,.xlsx" style={{ display: 'none' }} onChange={handleImport} />

            <div style={{ marginLeft: 260, padding: '20px 24px 32px' }}>
                {importResult && (
                    <ImportResultBanner result={importResult} onDismiss={() => setImportResult(null)} />
                )}

                {/* ── Header: title + filters + actions ───────────── */}
                <div style={{
                    display: 'flex', gap: 24, alignItems: 'flex-end', flexWrap: 'wrap',
                    marginBottom: 20,
                }}>
                    <div style={{ flex: '1 1 320px', minWidth: 280 }}>
                        <h1 style={{
                            fontSize: 22, fontWeight: 700, color: '#0f172a',
                            margin: 0, lineHeight: 1.2,
                        }}>
                            {pageTitle}
                        </h1>
                        <p style={{ margin: '4px 0 0', fontSize: 13, color: '#64748b' }}>
                            {pageSubtitle}
                        </p>
                    </div>

                    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                        <button onClick={handleTemplate} style={toolbarBtnStyle}>
                            <FileDown size={14} /> Template
                        </button>
                        <button onClick={() => fileRef.current?.click()} disabled={isImporting} style={toolbarBtnStyle}>
                            <Upload size={14} /> {isImporting ? 'Importing…' : 'Import'}
                        </button>
                        <button onClick={handleExport} style={toolbarBtnStyle}>
                            <Download size={14} /> Export
                        </button>
                        <button onClick={() => nav('/budget/appropriations/new')} style={{ ...toolbarBtnStyle, background: '#1e3a8a', color: '#fff', border: 'none' }}>
                            <Plus size={14} /> New Appropriation
                        </button>
                    </div>
                </div>

                {/* ── Filter strip ──────────────────────────────── */}
                <div style={{
                    background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 10,
                    padding: '14px 18px', marginBottom: 18,
                    display: 'flex', gap: 16, flexWrap: 'wrap', alignItems: 'flex-end',
                }}>
                    <div style={{ minWidth: 220, flex: '0 1 220px' }}>
                        <label style={filterLabelStyle}>Fiscal Year</label>
                        <SearchableSelect
                            options={fyOptions}
                            value={filterFyId}
                            onChange={(v) => setFilterFyId(v)}
                            placeholder="Select fiscal year…"
                        />
                    </div>
                    <div style={{ minWidth: 320, flex: '1 1 320px' }}>
                        <label style={filterLabelStyle}>MDA</label>
                        <SearchableSelect
                            options={mdaOptions}
                            value={filterMdaId}
                            onChange={(v) => setFilterMdaId(v)}
                            placeholder="All MDAs — type to filter…"
                        />
                    </div>
                    {filterMdaId && (
                        <button
                            type="button"
                            onClick={() => setFilterMdaId('')}
                            style={{
                                padding: '0.55rem 1rem',
                                background: '#fff', color: '#475569',
                                border: '1px solid #cbd5e1', borderRadius: 8,
                                fontSize: 13, fontWeight: 600, cursor: 'pointer',
                            }}
                        >
                            Clear MDA
                        </button>
                    )}
                </div>

                {/* ── KPI strip ─────────────────────────────────── */}
                <div style={{
                    display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
                    gap: 12, marginBottom: 18,
                }}>
                    <KpiCard label="Approved" value={fmtNaira(totals.approved)} accent="#1e3a8a" />
                    <KpiCard label="Expended" value={fmtNaira(totals.expended)} accent="#b91c1c" />
                    <KpiCard label="Available" value={fmtNaira(totals.available)} accent="#15803d" />
                    <KpiCard label="Execution Rate" value={`${totals.execRate.toFixed(1)}%`} accent="#7c3aed" />
                </div>

                {/* ── Bulk action bar ──────────────────────────
                    Three actions, gated independently:
                      • Delete    — needs at least one Draft line in selection
                      • Approve   — needs at least one Draft / Submitted line
                      • Activate  — needs at least one Approved / Submitted line
                    Buttons that have nothing to act on are disabled with
                    a tooltip explaining why. */}
                {selectedRollupIds.size > 0 && (
                    <div style={{
                        background: '#f8fafc', border: '1px solid #cbd5e1', borderRadius: 8,
                        padding: '10px 14px', marginBottom: 12,
                        display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap',
                    }}>
                        <span style={{ fontSize: 13, color: '#0f172a', fontWeight: 600 }}>
                            {selectedRollupIds.size} MDA budget{selectedRollupIds.size === 1 ? '' : 's'} selected
                            <span style={{ fontWeight: 400, color: '#64748b', marginLeft: 8 }}>
                                ({selectedDraftIds.length} Draft · {selectedApprovableIds.length} Approvable · {selectedActivatableIds.length} Activatable)
                            </span>
                        </span>
                        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                            <button
                                onClick={() => setSelectedRollupIds(new Set())}
                                style={{ ...toolbarBtnStyle, padding: '0.4rem 0.8rem' }}
                            >
                                Clear selection
                            </button>
                            <button
                                onClick={handleBulkApprove}
                                disabled={selectedApprovableIds.length === 0}
                                title={selectedApprovableIds.length === 0
                                    ? 'No Draft or Submitted lines in selection'
                                    : `Approve ${selectedApprovableIds.length} line${selectedApprovableIds.length === 1 ? '' : 's'}`}
                                style={{
                                    ...toolbarBtnStyle, padding: '0.4rem 0.8rem',
                                    background: selectedApprovableIds.length === 0 ? '#e2e8f0' : '#2563eb',
                                    color: selectedApprovableIds.length === 0 ? '#94a3b8' : '#fff',
                                    border: 'none',
                                    cursor: selectedApprovableIds.length === 0 ? 'not-allowed' : 'pointer',
                                }}
                            >
                                <CheckCircle2 size={13} /> Approve
                            </button>
                            <button
                                onClick={handleBulkActivate}
                                disabled={selectedActivatableIds.length === 0}
                                title={selectedActivatableIds.length === 0
                                    ? 'No Approved or Submitted lines in selection'
                                    : `Activate ${selectedActivatableIds.length} line${selectedActivatableIds.length === 1 ? '' : 's'}`}
                                style={{
                                    ...toolbarBtnStyle, padding: '0.4rem 0.8rem',
                                    background: selectedActivatableIds.length === 0 ? '#e2e8f0' : '#15803d',
                                    color: selectedActivatableIds.length === 0 ? '#94a3b8' : '#fff',
                                    border: 'none',
                                    cursor: selectedActivatableIds.length === 0 ? 'not-allowed' : 'pointer',
                                }}
                            >
                                <CheckCircle2 size={13} /> Activate
                            </button>
                            <button
                                onClick={handleBulkDeleteMdaDrafts}
                                disabled={selectedDraftIds.length === 0}
                                title={selectedDraftIds.length === 0
                                    ? 'No Draft lines in selection'
                                    : `Delete ${selectedDraftIds.length} draft line${selectedDraftIds.length === 1 ? '' : 's'}`}
                                style={{
                                    ...toolbarBtnStyle, padding: '0.4rem 0.8rem',
                                    background: selectedDraftIds.length === 0 ? '#e2e8f0' : '#dc2626',
                                    color: selectedDraftIds.length === 0 ? '#94a3b8' : '#fff',
                                    border: 'none',
                                    cursor: selectedDraftIds.length === 0 ? 'not-allowed' : 'pointer',
                                }}
                            >
                                <Trash2 size={13} /> Delete Drafts
                            </button>
                        </div>
                    </div>
                )}

                {/* ── Rollup table card ───────────────────────── */}
                <div style={{
                    background: '#fff', border: '1px solid #e2e8f0', borderRadius: 10,
                    overflow: 'hidden', boxShadow: '0 1px 2px rgba(15, 23, 42, 0.04)',
                }}>
                    <div style={{
                        padding: '14px 18px', borderBottom: '1px solid #e2e8f0',
                        background: '#fff', fontSize: 14, fontWeight: 600, color: '#0f172a',
                    }}>
                        Budget by MDA
                        <span style={{ fontSize: 12, color: '#64748b', fontWeight: 400, marginLeft: 8 }}>
                            ({rollupRows.length} {rollupRows.length === 1 ? 'MDA' : 'MDAs'})
                        </span>
                    </div>

                    <div style={{ overflowX: 'auto' }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                            <thead>
                                <tr style={{ background: '#f8fafc', borderBottom: '1px solid #e2e8f0' }}>
                                    <th style={{ ...thStyle, width: 36 }}>
                                        <input
                                            type="checkbox"
                                            checked={allActionableSelected}
                                            onChange={toggleAllActionable}
                                            disabled={actionableRows.length === 0}
                                            title={actionableRows.length === 0
                                                ? 'No actionable MDAs to select'
                                                : `Select all ${actionableRows.length} actionable MDA${actionableRows.length === 1 ? '' : 's'}`}
                                            aria-label="Select all actionable MDA rollups"
                                        />
                                    </th>
                                    <th style={thStyle}>Fiscal Year</th>
                                    <th style={thStyle}>MDA Code</th>
                                    <th style={thStyle}>MDA Name</th>
                                    <th style={{ ...thStyle, textAlign: 'right' }}># Lines</th>
                                    <th style={{ ...thStyle, textAlign: 'right' }}>Total Approved</th>
                                    <th style={{ ...thStyle, textAlign: 'right' }}>Expended</th>
                                    <th style={{ ...thStyle, textAlign: 'right' }}>Available</th>
                                    <th style={{ ...thStyle, textAlign: 'right' }}>Exec %</th>
                                    <th style={{ ...thStyle, textAlign: 'center' }}>Status</th>
                                </tr>
                            </thead>
                            <tbody>
                                {isLoading && (
                                    <tr><td colSpan={10} style={{ padding: 32, textAlign: 'center', color: '#64748b' }}>Loading…</td></tr>
                                )}
                                {!isLoading && rollupRows.length === 0 && (
                                    <tr><td colSpan={10} style={{ padding: 32, textAlign: 'center', color: '#64748b' }}>
                                        No appropriations found for the selected fiscal year.
                                    </td></tr>
                                )}
                                {rollupRows.map((r) => {
                                    const approved = Number(r.amount_approved ?? 0) || 0;
                                    const expended = Number(r.total_expended ?? 0) || 0;
                                    const available = Number(r.available_balance ?? approved - expended) || 0;
                                    const exec = Number(r.execution_rate ?? 0) || 0;
                                    // Trust the backend-computed rollup status. Falls back gracefully
                                    // for backends that pre-date the status_counts field.
                                    const rollupStatus = (r.status || (expended > 0 ? 'ACTIVE' : 'DRAFT')).toUpperCase();
                                    const sStyle = statusStyle(rollupStatus);
                                    const rowActionable = isRowActionable(r);
                                    const isSelected = selectedRollupIds.has(r.id);
                                    const label = rollupStatus === 'MIXED'
                                        ? 'Mixed'
                                        : rollupStatus.charAt(0) + rollupStatus.slice(1).toLowerCase();
                                    return (
                                        <tr
                                            key={r.id}
                                            onClick={() => onRollupRowClick(r)}
                                            style={{
                                                borderBottom: '1px solid #f1f5f9',
                                                cursor: 'pointer',
                                                background: isSelected ? '#fef2f2' : '#fff',
                                                transition: 'background 80ms ease',
                                            }}
                                            onMouseEnter={(e) => { if (!isSelected) (e.currentTarget as HTMLElement).style.background = '#f8fafc'; }}
                                            onMouseLeave={(e) => { if (!isSelected) (e.currentTarget as HTMLElement).style.background = '#fff'; }}
                                        >
                                            <td style={{ ...tdStyle, width: 36 }} onClick={(e) => e.stopPropagation()}>
                                                <input
                                                    type="checkbox"
                                                    checked={isSelected}
                                                    onChange={() => toggleOneRollup(r.id)}
                                                    disabled={!rowActionable}
                                                    title={rowActionable
                                                        ? 'Select this MDA for bulk approve / activate / delete'
                                                        : 'No actionable lines in this MDA (everything is Closed or empty)'}
                                                    aria-label={`Select MDA ${r.mda_code}`}
                                                />
                                            </td>
                                            <td style={tdStyle}>{r.fiscal_year_label || '—'}</td>
                                            <td style={tdStyle}>
                                                <span style={{ color: '#1e40af', fontWeight: 600 }}>{r.mda_code || '—'}</span>
                                            </td>
                                            <td style={tdStyle}>{r.mda_name || '—'}</td>
                                            <td style={{ ...tdStyle, textAlign: 'right', fontVariantNumeric: 'tabular-nums', color: '#475569' }}>
                                                {r.appropriation_count}
                                            </td>
                                            <td style={{ ...tdStyle, textAlign: 'right', fontVariantNumeric: 'tabular-nums', color: '#0f172a', fontWeight: 600 }}>
                                                {fmtNaira(approved)}
                                            </td>
                                            <td style={{ ...tdStyle, textAlign: 'right', fontVariantNumeric: 'tabular-nums', color: expended > 0 ? '#dc2626' : '#94a3b8' }}>
                                                {fmtNaira(expended)}
                                            </td>
                                            <td style={{ ...tdStyle, textAlign: 'right', fontVariantNumeric: 'tabular-nums', color: '#15803d', fontWeight: 600 }}>
                                                {fmtNaira(available)}
                                            </td>
                                            <td style={{ ...tdStyle, textAlign: 'right', fontVariantNumeric: 'tabular-nums', color: '#475569' }}>
                                                {exec.toFixed(1)}%
                                            </td>
                                            <td style={{ ...tdStyle, textAlign: 'center' }}>
                                                <span style={{
                                                    display: 'inline-block', padding: '3px 10px',
                                                    fontSize: 11, fontWeight: 600,
                                                    borderRadius: 999,
                                                    background: sStyle.bg, color: sStyle.fg,
                                                }}>
                                                    {label}
                                                </span>
                                            </td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </>
    );
};

/* ── Shared inline styles for the SAP-Fiori table ───────── */
const toolbarBtnStyle: React.CSSProperties = {
    display: 'inline-flex', alignItems: 'center', gap: 6,
    padding: '0.55rem 1.1rem',
    background: '#fff', color: '#0f172a',
    border: '1px solid #cbd5e1', borderRadius: 8,
    fontSize: 13, fontWeight: 600, cursor: 'pointer',
    boxShadow: '0 1px 2px rgba(15, 23, 42, 0.04)',
};
const filterLabelStyle: React.CSSProperties = {
    display: 'block', fontSize: 11, fontWeight: 700,
    color: '#64748b', textTransform: 'uppercase',
    letterSpacing: '0.05em', marginBottom: 6,
};
const thStyle: React.CSSProperties = {
    padding: '11px 12px', textAlign: 'left',
    fontSize: 11, fontWeight: 700, letterSpacing: '0.04em',
    textTransform: 'uppercase', color: '#475569',
    whiteSpace: 'nowrap',
};
const tdStyle: React.CSSProperties = {
    padding: '10px 12px', verticalAlign: 'top',
    color: '#0f172a',
};

function KpiCard({ label, value, accent }: { label: string; value: string; accent: string }) {
    return (
        <div style={{
            background: '#fff', border: '1px solid #e2e8f0', borderRadius: 10,
            padding: '12px 16px',
            borderLeft: `3px solid ${accent}`,
        }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                {label}
            </div>
            <div style={{ fontSize: 18, fontWeight: 700, color: '#0f172a', marginTop: 4, fontVariantNumeric: 'tabular-nums' }}>
                {value}
            </div>
        </div>
    );
}

/**
 * Backward-compat shim. The /budget/appropriations/by-mda/:mda_id route
 * has been folded into the single Fiori-style AppropriationList page —
 * old bookmarks just redirect there with the MDA pre-selected.
 */
export const AppropriationListByMda = () => {
    const nav = useNavigate();
    const { mda_id } = useParams<{ mda_id: string }>();
    useEffect(() => {
        // Carry FY context through if the legacy URL had it.
        const fy = new URLSearchParams(window.location.search).get('fiscal_year') || '';
        const params = new URLSearchParams();
        if (mda_id) params.set('mda', mda_id);
        if (fy) params.set('fy', fy);
        nav(`/budget/appropriations${params.toString() ? `?${params.toString()}` : ''}`, { replace: true });
    }, [mda_id, nav]);
    return null;
};

export const RevenueBudgetList = () => {
    const nav = useNavigate();
    const fileRef = useRef<HTMLInputElement>(null);
    const [importResult, setImportResult] = useState<BulkImportResult | null>(null);
    const [copyMsg, setCopyMsg] = useState('');

    const handleTemplate = async () => {
        try {
            const res = await apiClient.get('/budget/revenue-budgets/import-template/', { responseType: 'blob' });
            const url = window.URL.createObjectURL(new Blob([res.data], { type: 'text/csv' }));
            const a = document.createElement('a'); a.href = url; a.download = 'revenue_budget_template.csv';
            document.body.appendChild(a); a.click(); a.remove(); window.URL.revokeObjectURL(url);
        } catch { /* ignore */ }
    };

    const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0]; if (!file) return;
        const fd = new FormData(); fd.append('file', file);
        try {
            const res = await apiClient.post('/budget/revenue-budgets/bulk-import/', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
            setImportResult(res.data);
        } catch { /* ignore */ }
        e.target.value = '';
    };

    const handleCopyPriorYear = async () => {
        // Get the latest fiscal year to copy into
        try {
            const fyRes = await apiClient.get('/accounting/fiscal-years/', { params: { status: 'Open', ordering: '-year' } });
            const years = fyRes.data?.results || fyRes.data || [];
            if (years.length === 0) { setCopyMsg('No open fiscal year found'); return; }
            const targetFy = years[0];
            const res = await apiClient.post('/budget/revenue-budgets/copy-from-prior-year/', {
                target_fiscal_year_id: targetFy.id,
            });
            setCopyMsg(`${res.data.created} targets copied from FY${res.data.source_year} as DRAFT`);
            setTimeout(() => setCopyMsg(''), 5000);
        } catch (err: any) {
            setCopyMsg(err?.response?.data?.error || 'Failed to copy');
            setTimeout(() => setCopyMsg(''), 5000);
        }
    };

    return (
        <>
            <input ref={fileRef} type="file" accept=".csv,.xlsx" style={{ display: 'none' }} onChange={handleImport} />
            {importResult && (
                <div style={{ marginLeft: 260, paddingTop: 16, paddingRight: 24 }}>
                    <ImportResultBanner result={importResult} onDismiss={() => setImportResult(null)} />
                </div>
            )}
            {copyMsg && (
                <div style={{ marginLeft: 260, paddingTop: 16, paddingRight: 24 }}>
                    <div style={{ background: '#dcfce7', border: '1px solid #86efac', borderRadius: 8, padding: '10px 16px', fontSize: 13, color: '#166534' }}>
                        {copyMsg}
                    </div>
                </div>
            )}
            <GenericListPage
                title="Revenue Budget (Targets)"
                subtitle="Statistical revenue targets by MDA — no enforcement, for performance tracking only"
                endpoint="/budget/revenue-budgets/"
                columns={[
                    { key: 'administrative_name', label: 'MDA' },
                    {
                        key: 'economic_code',
                        label: 'Revenue Account',
                        render: (r) => {
                            const code = (r.economic_code as string) || '';
                            const name = (r.economic_name as string) || '';
                            return code && name ? `${code} — ${name}` : (code || name || '—');
                        },
                    },
                    { key: 'fund_name', label: 'Fund' },
                    { key: 'estimated_amount', label: 'Target', format: 'currency' },
                    { key: 'actual_collected', label: 'Actual', format: 'currency' },
                    { key: 'variance', label: 'Variance', format: 'currency' },
                    { key: 'performance_rate', label: 'Performance', format: 'percent' },
                    { key: 'status', label: 'Status', format: 'status' },
                ]}
                actions={[
                    { label: 'Template', onClick: handleTemplate, variant: 'secondary', icon: icon(FileDown) },
                    { label: 'Import', onClick: () => fileRef.current?.click(), variant: 'secondary', icon: icon(Upload) },
                    { label: 'Copy Prior Year', onClick: handleCopyPriorYear, variant: 'secondary', icon: icon(RefreshCw) },
                    { label: 'New Revenue Target', onClick: () => nav('/budget/revenue-budget/new'), variant: 'primary', icon: icon(Plus) },
                ]}
            />
        </>
    );
};

export const WarrantList = () => {
    const nav = useNavigate();
    return (
        <GenericListPage
            title="Warrants / AIE (Authority to Incur Expenditure)"
            subtitle="Quarterly cash release authority — click a row to release or view details"
            endpoint="/budget/warrants/"
            columns={[
                { key: 'appropriation_mda', label: 'MDA' },
                { key: 'appropriation_account', label: 'Economic Code' },
                { key: 'quarter', label: 'Quarter', width: '80px' },
                { key: 'amount_released', label: 'Amount Released', format: 'currency' },
                { key: 'release_date', label: 'Release Date', format: 'date' },
                { key: 'authority_reference', label: 'AIE Reference' },
                { key: 'status', label: 'Status', format: 'status' },
            ]}
            actions={[
                { label: 'New AIE / Warrant', onClick: () => nav('/budget/warrants/new'), variant: 'primary', icon: icon(Plus) },
            ]}
            onRowClick={(item) => nav(`/budget/warrants/${item.id}`)}
        />
    );
};

/* ── Treasury & TSA ────────────────────────────────────── */

export const TSAAccountList = () => {
    const nav = useNavigate();
    const qc = useQueryClient();

    /**
     * Delete a TSA account. Treasury data is heavily referenced
     * (payments, transfers, bank reconciliations) so the backend's
     * on_delete=PROTECT will often reject deletions — the error
     * message surfaces to the user so they understand why.
     *
     * A two-step confirm with the account number echoed back protects
     * against accidental deletion: the user has to read the number off
     * the row and type it back, which stops muscle-memory double-clicks.
     */
    const handleDelete = async (item: Record<string, unknown>) => {
        const accountNumber = String(item.account_number ?? '');
        const accountName = String(item.account_name ?? '');
        const id = item.id;
        const first = window.confirm(
            `Delete TSA account "${accountName}" (${accountNumber})?\n\n` +
            `This cannot be undone. TSA accounts referenced by posted ` +
            `payments or transfers cannot be deleted — deactivate them ` +
            `instead (set Active = false).`
        );
        if (!first) return;

        // Echo-back step: user must type the account number to confirm.
        const typed = window.prompt(
            `Type the account number (${accountNumber}) to confirm deletion:`
        );
        if (typed?.trim() !== accountNumber) {
            if (typed !== null) {
                window.alert('Account number did not match — deletion cancelled.');
            }
            return;
        }

        try {
            await apiClient.delete(`/accounting/tsa-accounts/${id}/`);
            // Invalidate the list cache so the UI refreshes immediately.
            qc.invalidateQueries({ queryKey: ['generic-list', '/accounting/tsa-accounts/'] });
        } catch (err: unknown) {
            // Surface PROTECT errors (referenced rows) or permission errors.
            const e = err as { response?: { data?: { detail?: string; error?: string } }; message?: string };
            const msg =
                e?.response?.data?.detail ||
                e?.response?.data?.error ||
                e?.message ||
                'Delete failed. The account may be referenced by other records.';
            window.alert(`Could not delete: ${msg}`);
        }
    };

    /**
     * Bulk-delete handler for the contextual action bar.
     *
     * Two-step confirm scaled for multi-row: first a count confirm, then a
     * type-DELETE echo-back. PROTECT errors on individual rows are collected
     * and surfaced together so the user can see which accounts couldn't be
     * removed (likely because they're referenced by posted transactions).
     */
    const handleBulkDelete = async (items: Record<string, unknown>[]) => {
        if (items.length === 0) return;
        const numbers = items.map(it => String(it.account_number ?? '')).filter(Boolean);
        const preview = numbers.slice(0, 5).join(', ') + (numbers.length > 5 ? `, +${numbers.length - 5} more` : '');
        const first = window.confirm(
            `Delete ${items.length} TSA account${items.length === 1 ? '' : 's'}?\n\n` +
            `Accounts: ${preview}\n\n` +
            `This cannot be undone. Accounts referenced by posted payments ` +
            `or transfers will be skipped (deactivate them instead).`
        );
        if (!first) return;
        const typed = window.prompt(`Type DELETE to confirm removing ${items.length} account${items.length === 1 ? '' : 's'}:`);
        if (typed?.trim().toUpperCase() !== 'DELETE') {
            if (typed !== null) {
                window.alert('Confirmation phrase did not match — bulk delete cancelled.');
            }
            return;
        }

        const failures: Array<{ accountNumber: string; reason: string }> = [];
        for (const item of items) {
            try {
                await apiClient.delete(`/accounting/tsa-accounts/${item.id}/`);
            } catch (err: unknown) {
                const e = err as { response?: { data?: { detail?: string; error?: string } }; message?: string };
                failures.push({
                    accountNumber: String(item.account_number ?? item.id),
                    reason: e?.response?.data?.detail || e?.response?.data?.error || e?.message || 'Unknown error',
                });
            }
        }
        qc.invalidateQueries({ queryKey: ['generic-list', '/accounting/tsa-accounts/'] });

        if (failures.length > 0) {
            const lines = failures.map(f => `  • ${f.accountNumber}: ${f.reason}`).join('\n');
            const ok = items.length - failures.length;
            window.alert(
                `${ok} of ${items.length} account${items.length === 1 ? '' : 's'} deleted.\n\n` +
                `Could not delete:\n${lines}`
            );
        }
    };

    return (
        <GenericListPage
            title="TSA Accounts"
            subtitle="Treasury Single Account structure -- Main TSA, sub-accounts, and zero-balance accounts"
            endpoint="/accounting/tsa-accounts/"
            columns={[
                { key: 'account_number', label: 'Account No.', width: '150px' },
                { key: 'account_name', label: 'Account Name' },
                { key: 'account_type', label: 'Type' },
                { key: 'bank', label: 'Bank' },
                { key: 'mda_name', label: 'MDA' },
                { key: 'current_balance', label: 'Balance', format: 'currency' },
                { key: 'is_active', label: 'Active' },
            ]}
            actions={[
                { label: 'Add TSA Account', onClick: () => nav('/accounting/tsa-accounts/new'), variant: 'primary', icon: icon(Plus) },
            ]}
            bulkActions={[
                {
                    label: 'Delete Selected',
                    icon: <Trash2 size={14} />,
                    variant: 'danger',
                    onClick: handleBulkDelete,
                },
            ]}
            rowActions={{
                // "View Ledger" opens a bank-statement view of this TSA's
                // postings — credits from RevenueCollection + debits from
                // PaymentInstruction, ordered chronologically with running
                // balance. Mirrors a real bank statement for audit teams.
                custom: [
                    {
                        label: 'View Ledger',
                        icon: <BookOpen size={14} />,
                        onClick: (item) => nav(`/accounting/tsa-accounts/${item.id}/ledger`),
                        color: '#0f766e',
                    },
                ],
                onEdit: (item) => nav(`/accounting/tsa-accounts/${item.id}/edit`),
                onDelete: handleDelete,
            }}
        />
    );
};

export const PaymentVoucherList = () => {
    const nav = useNavigate();
    return (
        <GenericListPage
            title="Payment Vouchers"
            subtitle="Government payment vouchers -- approved and processed via TSA"
            endpoint="/accounting/payment-vouchers/"
            columns={[
                { key: 'voucher_number', label: 'PV Number', width: '130px' },
                { key: 'payment_type', label: 'Type' },
                { key: 'payee_name', label: 'Payee' },
                { key: 'gross_amount', label: 'Gross', format: 'currency' },
                { key: 'wht_amount', label: 'WHT', format: 'currency' },
                { key: 'net_amount', label: 'Net', format: 'currency' },
                { key: 'status', label: 'Status', format: 'status' },
            ]}
            actions={[
                { label: 'New Payment Voucher', onClick: () => nav('/accounting/payment-vouchers/new'), variant: 'primary', icon: icon(Plus) },
            ]}
            onRowClick={(item) => nav(`/accounting/payment-vouchers/${item.id}`)}
        />
    );
};

export const PaymentInstructionList = () => (
    <GenericListPage
        title="Payment Instructions"
        subtitle="Electronic payment instructions sent to CBN/bank for TSA settlement"
        endpoint="/accounting/payment-instructions/"
        columns={[
            { key: 'voucher_number', label: 'PV Ref' },
            { key: 'beneficiary_name', label: 'Beneficiary' },
            { key: 'beneficiary_bank', label: 'Bank' },
            { key: 'amount', label: 'Amount', format: 'currency' },
            { key: 'batch_reference', label: 'Batch Ref' },
            { key: 'bank_reference', label: 'Bank Ref' },
            { key: 'status', label: 'Status', format: 'status' },
        ]}
    />
);

/* ── Revenue (IGR) ─────────────────────────────────────── */

export const RevenueHeadList = () => {
    const nav = useNavigate();
    return (
        <GenericListPage
            title="Revenue Heads"
            subtitle="IGR revenue classification -- maps to NCoA economic segment"
            endpoint="/accounting/revenue-heads/"
            columns={[
                { key: 'code', label: 'Code', width: '120px' },
                { key: 'name', label: 'Revenue Head' },
                { key: 'revenue_type', label: 'Type' },
                {
                    key: 'economic_code',
                    label: 'NCoA Economic',
                    render: (r) => {
                        const code = (r.economic_code as string) || '';
                        // Revenue heads expose the NCoA economic as a plain
                        // code string; fall back to the human label if the
                        // join populated it.
                        const name = (r.economic_name as string)
                            || (r.ncoa_economic_name as string)
                            || '';
                        return code && name ? `${code} — ${name}` : (code || name || '—');
                    },
                },
                { key: 'collection_mda_name', label: 'Collecting MDA' },
                { key: 'is_active', label: 'Active' },
            ]}
            actions={[
                { label: 'Add Revenue Head', onClick: () => nav('/accounting/revenue-heads/new'), variant: 'primary', icon: icon(Plus) },
            ]}
        />
    );
};

export const RevenueCollectionList = () => {
    const nav = useNavigate();
    const fileRef = useRef<HTMLInputElement>(null);
    const [importResult, setImportResult] = useState<BulkImportResult | null>(null);

    const handleTemplate = async () => {
        try {
            const res = await apiClient.get('/accounting/revenue-collections/import-template/', { responseType: 'blob' });
            const url = window.URL.createObjectURL(new Blob([res.data], { type: 'text/csv' }));
            const a = document.createElement('a'); a.href = url; a.download = 'revenue_collection_template.csv';
            document.body.appendChild(a); a.click(); a.remove(); window.URL.revokeObjectURL(url);
        } catch { /* ignore */ }
    };

    const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0]; if (!file) return;
        const fd = new FormData(); fd.append('file', file);
        try {
            const res = await apiClient.post('/accounting/revenue-collections/bulk-import/', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
            setImportResult(res.data);
        } catch { /* ignore */ }
        e.target.value = '';
    };

    return (
        <>
            <input ref={fileRef} type="file" accept=".csv,.xlsx" style={{ display: 'none' }} onChange={handleImport} />
            {importResult && (
                <div style={{ marginLeft: 260, paddingTop: 16, paddingRight: 24 }}>
                    <ImportResultBanner result={importResult} onDismiss={() => setImportResult(null)} />
                </div>
            )}
            <GenericListPage
                title="Revenue Collections (IGR)"
                subtitle="Internally Generated Revenue — journal-style double-entry receipts"
                endpoint="/accounting/revenue-collections/"
                columns={[
                    { key: 'receipt_number', label: 'Receipt No.', width: '130px' },
                    { key: 'revenue_head_name', label: 'Revenue Head' },
                    { key: 'payer_name', label: 'Payer' },
                    { key: 'amount', label: 'Amount', format: 'currency' },
                    { key: 'collection_date', label: 'Date', format: 'date' },
                    { key: 'collection_channel', label: 'Channel' },
                    { key: 'status', label: 'Status', format: 'status' },
                ]}
                actions={[
                    { label: 'Template', onClick: handleTemplate, variant: 'secondary', icon: icon(FileDown) },
                    { label: 'Import', onClick: () => fileRef.current?.click(), variant: 'secondary', icon: icon(Upload) },
                    { label: 'New Revenue Entry', onClick: () => nav('/accounting/revenue-collections/new'), variant: 'primary', icon: icon(Plus) },
                ]}
                onRowClick={(item) => nav(`/accounting/revenue-collections/${item.id}`)}
            />
        </>
    );
};

/* ── NCoA Segments ─────────────────────────────────────── */

export const NCoAEconomicList = () => {
    const qc = useQueryClient();

    // One-time backfill — walks every legacy Account and creates/updates
    // the matching EconomicSegment. After this runs once, the post_save
    // signal in accounting.signals.coa_to_ncoa keeps them in lockstep
    // automatically — every subsequent CoA edit / import / API create
    // also writes the NCoA layer in the same transaction.
    const syncFromCoA = useMutation({
        mutationFn: async () => {
            const res = await apiClient.post('/accounting/ncoa/economic/sync-from-coa/');
            return res.data as {
                created: number;
                updated: number;
                skipped: number;
                skipped_details: Array<{ id: number; code?: string; reason: string }>;
                total: number;
            };
        },
        onSuccess: (data) => {
            qc.invalidateQueries({ queryKey: ['generic-list'] });
            qc.invalidateQueries({ queryKey: ['ncoa-segments-all'] });
            const head = `Sync complete — created ${data.created}, updated ${data.updated}, skipped ${data.skipped}.`;
            const details = data.skipped > 0
                ? '\n\nSkipped:\n' + data.skipped_details
                    .slice(0, 5)
                    .map(s => `  • Account id ${s.id}${s.code ? ` (${s.code})` : ''}: ${s.reason}`)
                    .join('\n')
                    + (data.skipped_details.length > 5 ? `\n  …and ${data.skipped_details.length - 5} more` : '')
                : '';
            alert(head + details);
        },
        onError: (err: any) => {
            alert(err?.response?.data?.error || err?.response?.data?.detail || 'Sync failed.');
        },
    });

    return (
        <GenericListPage
            title="NCoA Economic Segment"
            subtitle="The hub segment -- account classification (Revenue, Expenditure, Assets, Liabilities). Mirrors the Chart of Accounts: every CoA save automatically updates this list."
            endpoint="/accounting/ncoa/economic/"
            actions={[
                {
                    label: syncFromCoA.isPending ? 'Syncing…' : 'Sync from Chart of Accounts',
                    onClick: () => syncFromCoA.mutate(),
                    variant: 'primary',
                    icon: icon(RefreshCw),
                },
            ]}
            columns={[
                { key: 'code', label: 'Code', width: '100px' },
                { key: 'name', label: 'Account Name' },
                { key: 'account_type_label', label: 'Type' },
                { key: 'is_posting_level', label: 'Posting' },
                { key: 'is_control_account', label: 'Control' },
                { key: 'normal_balance', label: 'Balance' },
                { key: 'is_active', label: 'Active' },
            ]}
        />
    );
};

export const NCoAAdminList = () => (
    <NCoASegmentPage
        title="NCoA Administrative Segment (MDA)"
        subtitle="Ministry, Department, Agency hierarchy"
        endpoint="/accounting/ncoa/administrative/"
        segmentType="administrative"
        addLabel="Add MDA"
        addPath="/accounting/ncoa/administrative/new"
        enableDelete
        columns={[
            { key: 'code', label: 'Code', width: '120px' },
            { key: 'name', label: 'MDA Name' },
            { key: 'level', label: 'Level' },
            { key: 'sector_code', label: 'Sector' },
            { key: 'mda_type', label: 'MDA Type' },
            { key: 'is_active', label: 'Active' },
        ]}
    />
);

export const NCoAFunctionalList = () => (
    <NCoASegmentPage
        title="NCoA Functional Segment (COFOG)"
        subtitle="UN Classification of Functions of Government"
        endpoint="/accounting/ncoa/functional/"
        segmentType="functional"
        addLabel="Add Function"
        addPath="/accounting/ncoa/functional/new"
        enableDelete
        columns={[
            { key: 'code', label: 'Code', width: '80px' },
            { key: 'name', label: 'Function' },
            { key: 'division_code', label: 'Division' },
            { key: 'is_active', label: 'Active' },
        ]}
    />
);

export const NCoAProgrammeList = () => (
    <NCoASegmentPage
        title="NCoA Programme Segment"
        subtitle="Policy, programme, and capital project classification"
        endpoint="/accounting/ncoa/programme/"
        segmentType="programme"
        addLabel="Add Programme"
        addPath="/accounting/ncoa/programme/new"
        enableDelete
        columns={[
            { key: 'code', label: 'Code', width: '150px' },
            { key: 'name', label: 'Programme' },
            { key: 'policy_code', label: 'Policy' },
            { key: 'is_capital', label: 'Capital' },
            { key: 'is_active', label: 'Active' },
        ]}
    />
);

export const NCoAFundList = () => (
    <NCoASegmentPage
        title="NCoA Fund Segment"
        subtitle="Source of government funding"
        endpoint="/accounting/ncoa/fund/"
        segmentType="fund"
        addLabel="Add Fund"
        addPath="/accounting/ncoa/fund/new"
        enableDelete
        columns={[
            { key: 'code', label: 'Code', width: '80px' },
            { key: 'name', label: 'Fund Source' },
            { key: 'main_fund_code', label: 'Main Fund' },
            { key: 'is_restricted', label: 'Restricted' },
            { key: 'is_active', label: 'Active' },
        ]}
    />
);

export const NCoAGeoList = () => (
    <NCoASegmentPage
        title="NCoA Geographic Segment"
        subtitle="Location of government transactions -- zones, states, LGAs"
        endpoint="/accounting/ncoa/geographic/"
        segmentType="geographic"
        addLabel="Add Location"
        addPath="/accounting/ncoa/geographic/new"
        enableDelete
        columns={[
            { key: 'code', label: 'Code', width: '100px' },
            { key: 'name', label: 'Location' },
            { key: 'is_active', label: 'Active' },
        ]}
    />
);

export const NCoACodeList = () => (
    <GenericListPage
        title="NCoA Composite Codes"
        subtitle="Full 52-digit NCoA codes -- the financial DNA of government transactions"
        endpoint="/accounting/ncoa/codes/"
        columns={[
            { key: 'full_code', label: 'NCoA Code' },
            { key: 'account_name', label: 'Account' },
            { key: 'mda_name', label: 'MDA' },
            { key: 'fund_code', label: 'Fund' },
            { key: 'is_active', label: 'Active' },
        ]}
    />
);

/* ── Procurement BPP ───────────────────────────────────── */

export const ProcurementThresholdList = () => (
    <GenericListPage
        title="BPP Procurement Thresholds"
        subtitle="Approval authority levels per the Public Procurement Act"
        endpoint="/procurement/thresholds/"
        columns={[
            { key: 'category', label: 'Category' },
            { key: 'authority_level', label: 'Authority' },
            { key: 'min_amount', label: 'Min Amount', format: 'currency' },
            { key: 'max_amount', label: 'Max Amount', format: 'currency' },
            { key: 'requires_bpp_no', label: 'NOC Required' },
            { key: 'is_active', label: 'Active' },
        ]}
    />
);

export const NoObjectionList = () => {
    const nav = useNavigate();
    return (
        <GenericListPage
            title="Certificates of No Objection"
            subtitle="BPP No Objection Certificates for procurement above threshold"
            endpoint="/procurement/no-objection/"
            columns={[
                { key: 'certificate_number', label: 'Certificate No.' },
                { key: 'purchase_order_number', label: 'PO Reference' },
                { key: 'authority_level', label: 'Authority' },
                { key: 'amount_covered', label: 'Amount', format: 'currency' },
                { key: 'issued_date', label: 'Issued', format: 'date' },
                { key: 'expiry_date', label: 'Expires', format: 'date' },
                { key: 'is_valid', label: 'Valid' },
            ]}
            actions={[
                { label: 'Add NOC', onClick: () => nav('/procurement/no-objection/new'), variant: 'primary', icon: icon(Plus) },
            ]}
        />
    );
};
