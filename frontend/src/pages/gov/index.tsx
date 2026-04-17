/**
 * Government IFMIS Page Definitions — Quot PSE
 * Each page wraps GenericListPage with appropriate column configuration.
 * Includes Create/Action buttons for data entry.
 */
import { useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { Plus, Download, Upload, RefreshCw, FileDown, CheckCircle2, AlertCircle, BookOpen } from 'lucide-react';
import GenericListPage from '../../components/GenericListPage';
import { downloadNCoATemplate, useNCoABulkImport, type NCoASegmentType, type BulkImportResult } from '../../hooks/useNCoAImportExport';
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
}: {
    title: string;
    subtitle: string;
    endpoint: string;
    columns: { key: string; label: string; width?: string }[];
    segmentType: NCoASegmentType;
    addLabel: string;
    addPath: string;
}) {
    const nav = useNavigate();
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
                rowActions={{
                    onEdit: (item) => nav(`/accounting/ncoa/${segmentType}/${item.id}/edit`),
                }}
            />
        </>
    );
}

/* ── Budget & Appropriation ────────────────────────────── */

export const AppropriationList = () => {
    const nav = useNavigate();
    return (
        <GenericListPage
            title="Appropriations"
            subtitle="Legislative budget appropriations — click a row to view details and approve"
            endpoint="/budget/appropriations/"
            columns={[
                { key: 'fiscal_year_label', label: 'FY', width: '70px' },
                { key: 'administrative_name', label: 'MDA' },
                { key: 'economic_name', label: 'Economic Code' },
                { key: 'fund_name', label: 'Fund' },
                { key: 'amount_approved', label: 'Approved', format: 'currency' },
                { key: 'total_expended', label: 'Expended', format: 'currency' },
                { key: 'available_balance', label: 'Available', format: 'currency' },
                { key: 'execution_rate', label: 'Exec %', format: 'percent' },
                { key: 'status', label: 'Status', format: 'status' },
            ]}
            actions={[
                { label: 'New Appropriation', onClick: () => nav('/budget/appropriations/new'), variant: 'primary', icon: icon(Plus) },
            ]}
            onRowClick={(item) => nav(`/budget/appropriations/${item.id}`)}
        />
    );
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
                    { key: 'economic_name', label: 'Revenue Account' },
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
                { key: 'economic_code', label: 'NCoA Economic' },
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

export const NCoAEconomicList = () => (
    <GenericListPage
        title="NCoA Economic Segment"
        subtitle="The hub segment -- account classification (Revenue, Expenditure, Assets, Liabilities). These are synced as Chart of Accounts."
        endpoint="/accounting/ncoa/economic/"
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

export const NCoAAdminList = () => (
    <NCoASegmentPage
        title="NCoA Administrative Segment (MDA)"
        subtitle="Ministry, Department, Agency hierarchy"
        endpoint="/accounting/ncoa/administrative/"
        segmentType="administrative"
        addLabel="Add MDA"
        addPath="/accounting/ncoa/administrative/new"
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
        columns={[
            { key: 'code', label: 'Code', width: '100px' },
            { key: 'name', label: 'Location' },
            { key: 'zone_code', label: 'Zone' },
            { key: 'state_code', label: 'State' },
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
