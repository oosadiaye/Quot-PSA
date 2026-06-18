/**
 * Warrant Print Preview — Quot PSE
 * Route: /budget/warrants/:id/print
 *
 * Composes the warrant data + the tenant's WarrantPrintoutSettings
 * (letterhead, 3 signatures, footer notes) into a print-ready A4
 * layout. The user prints with the browser's native dialog
 * (Ctrl+P / Cmd+P) to either physical paper or PDF.
 *
 * Why HTML print instead of server-side PDF generation:
 *   - No backend dependency (weasyprint, wkhtmltopdf) to install
 *   - Browser print dialog respects the user's paper size + margins
 *   - Renders identically across machines (CSS print media query)
 *   - Operator can preview + edit before printing
 *
 * The `@media print` rules below hide the toolbar, page background,
 * and any UI chrome — only the warrant card itself prints.
 */
import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Printer, ArrowLeft, Eye } from 'lucide-react';

import apiClient from '../../api/client';
import PdfPreviewModal from '../../components/PdfPreviewModal';
import WarrantPrintLayout from '../../components/warrant/WarrantPrintLayout';
import type {
    WarrantPrintLine, WarrantPrintSettings,
} from '../../components/warrant/WarrantPrintLayout';

interface WarrantData {
    id: number;
    quarter?: number | null;
    effective_from?: string | null;
    effective_to?: string | null;
    effective_status?: string;
    is_expired?: boolean;
    amount_released: string;
    release_date: string;
    authority_reference: string;
    status: string;
    notes: string;
    appropriation: number;
    appropriation_mda?: string;
    appropriation_account?: string;
    appropriation_economic_code?: string;
    appropriation_amount_approved?: string;
    appropriation_total_committed?: string;
    appropriation_total_expended?: string;
    appropriation_available_balance?: string;
}

/**
 * Local settings type extends the shared one with the reference PDF URL,
 * which is print-preview-only (the form-page preview doesn't need it).
 */
interface FullPrintoutSettings extends WarrantPrintSettings {
    reference_pdf_template_url: string | null;
}

export default function WarrantPrintPreview() {
    const { id } = useParams<{ id: string }>();
    const navigate = useNavigate();
    // Toggle for the in-app modal showing the agreed sample PDF
    // alongside the live HTML rendering — lets an operator visually
    // compare the two before sending the warrant for signature.
    const [referenceOpen, setReferenceOpen] = useState(false);

    const { data: warrant, isLoading: warrantLoading } = useQuery<WarrantData>({
        queryKey: ['warrant-print', id],
        queryFn: async () => {
            const res = await apiClient.get(`/budget/warrants/${id}/`);
            return res.data;
        },
        enabled: !!id,
    });
    const { data: settings, isLoading: settingsLoading } = useQuery<FullPrintoutSettings>({
        queryKey: ['warrant-printout-settings'],
        queryFn: async () => {
            const res = await apiClient.get('/budget/warrant-printout-settings/current/');
            return res.data;
        },
    });

    // Set the print page title to the warrant reference so saved-PDF
    // filenames default to something useful instead of "WarrantPrintPreview".
    useEffect(() => {
        if (warrant) {
            const ref = warrant.authority_reference
                || (warrant.effective_from && warrant.effective_to
                    ? `${warrant.effective_from}_${warrant.effective_to}`
                    : warrant.quarter ? `Q${warrant.quarter}` : `Warrant-${warrant.id}`);
            document.title = `Warrant ${ref} — Print Preview`;
        }
        return () => { document.title = 'Quot PSE'; };
    }, [warrant]);

    const handlePrint = () => window.print();

    if (warrantLoading || settingsLoading || !warrant || !settings) {
        return (
            <div style={{ padding: 60, textAlign: 'center', color: '#64748b' }}>
                Loading…
            </div>
        );
    }

    const fy = (warrant as any).appropriation_fiscal_year_label
        || (warrant as any).fiscal_year
        || '';

    // Period suffix prefers the explicit date range; fallback to the
    // legacy quarter for historical rows that pre-date the range refactor.
    const periodSuffix = warrant.effective_from && warrant.effective_to
        ? `${warrant.effective_from}_${warrant.effective_to}`
        : warrant.quarter ? `Q${warrant.quarter}` : `W${warrant.id}`;
    const warrantNumber = warrant.authority_reference
        || `WNT/${fy}/${periodSuffix}/${warrant.id}`;

    return (
        <>
            {/* Print stylesheet — hides UI chrome, sets A4 margins */}
            <style>{`
                @page {
                    size: A4 portrait;
                    margin: 18mm 18mm 18mm 18mm;
                }
                @media print {
                    .no-print { display: none !important; }
                    body { background: white !important; }
                    .print-page {
                        box-shadow: none !important;
                        border: none !important;
                        margin: 0 !important;
                    }
                }
                @media screen {
                    body { background: #e2e8f0; }
                }
            `}</style>

            {/* Toolbar — only on screen, hidden when printing */}
            <div className="no-print" style={{
                position: 'sticky', top: 0, zIndex: 10,
                background: '#0f172a', color: 'white',
                padding: '10px 24px',
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                gap: 12, fontFamily: "'Inter', -apple-system, sans-serif",
            }}>
                <button
                    onClick={() => navigate(-1)}
                    style={{
                        display: 'flex', alignItems: 'center', gap: 6,
                        padding: '7px 14px', border: '1px solid #334155',
                        background: '#1e293b', color: 'white',
                        borderRadius: 6, fontSize: 13, fontWeight: 600,
                        cursor: 'pointer',
                    }}
                >
                    <ArrowLeft size={14} /> Back
                </button>
                <div style={{ fontSize: 13, color: '#cbd5e1' }}>
                    Warrant Print Preview · Use <kbd style={kbd}>Ctrl+P</kbd> or click Print
                </div>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                    {/* Only surface the reference button when a sample
                        PDF has actually been uploaded — keeps the toolbar
                        from advertising a feature that has nothing behind it. */}
                    {settings.reference_pdf_template_url && (
                        <button
                            onClick={() => setReferenceOpen(true)}
                            title="Compare against the uploaded sample warrant template"
                            style={{
                                display: 'flex', alignItems: 'center', gap: 6,
                                padding: '7px 14px', border: '1px solid #334155',
                                background: '#1e293b', color: 'white',
                                borderRadius: 6, fontSize: 13, fontWeight: 600,
                                cursor: 'pointer',
                            }}
                        >
                            <Eye size={14} /> View Reference Sample
                        </button>
                    )}
                    <button
                        onClick={handlePrint}
                        style={{
                            display: 'flex', alignItems: 'center', gap: 6,
                            padding: '8px 16px', border: 'none',
                            background: '#1e40af', color: 'white',
                            borderRadius: 6, fontSize: 13, fontWeight: 700,
                            cursor: 'pointer',
                        }}
                    >
                        <Printer size={14} /> Print Warrant
                    </button>
                </div>
            </div>

            {/* The printable page — A4 width, white surface. The body
                comes from the shared <WarrantPrintLayout/> so the create
                form's preview panel and this print page render the
                same DOM by construction (any layout tweak lands in one
                place). */}
            <div className="print-page" style={{
                maxWidth: 794,
                margin: '24px auto',
                background: 'white',
                boxShadow: '0 8px 32px rgba(15, 23, 42, 0.12)',
            }}>
                <WarrantPrintLayout
                    settings={settings}
                    warrant_number={warrantNumber}
                    effective_from={warrant.effective_from || undefined}
                    effective_to={warrant.effective_to || undefined}
                    quarter={warrant.quarter || undefined}
                    effective_status={warrant.effective_status}
                    release_date={warrant.release_date}
                    mda_name={warrant.appropriation_mda || 'designated MDA'}
                    lines={[{
                        economic_code: warrant.appropriation_economic_code,
                        economic_name: warrant.appropriation_account,
                        amount_released: warrant.amount_released,
                        appropriation_amount_approved: warrant.appropriation_amount_approved,
                    } as WarrantPrintLine]}
                    body_notes={warrant.notes}
                    mode="print"
                />
            </div>

            {/* In-app preview of the agreed sample template — opens
                only on demand and uses the browser's native PDF viewer
                via iframe. Lives outside .print-page so the modal chrome
                never lands on a printed sheet. */}
            {referenceOpen && settings.reference_pdf_template_url && (
                <PdfPreviewModal
                    url={settings.reference_pdf_template_url}
                    title="Warrant Sample Template"
                    subtitle={`${settings.state_name || 'State'} · agreed reference layout`}
                    onClose={() => setReferenceOpen(false)}
                />
            )}
        </>
    );
}


// ─────────────────────────────────────────────────────────────────────
// Inline styles — only those that survive the move to the shared
// WarrantPrintLayout. The metaLabel/metaValue/td* styles all migrated
// into WarrantPrintLayout.tsx.
// ─────────────────────────────────────────────────────────────────────
const kbd: React.CSSProperties = {
    background: '#1e293b',
    border: '1px solid #475569',
    padding: '2px 6px',
    borderRadius: 3,
    fontSize: 11,
    fontFamily: 'monospace',
    color: '#e2e8f0',
};
