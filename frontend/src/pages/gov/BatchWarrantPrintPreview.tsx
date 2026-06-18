/**
 * BatchWarrantPrintPreview — composite printout for a Smart-Create
 * batch: one document covering N warrants that all belong to the same
 * MDA / quarter / authority reference.
 *
 * Route: /budget/warrants/print-batch?ids=1,2,3
 *
 * Why this page exists separately from /budget/warrants/:id/print:
 *   • The single-warrant route loads one warrant by primary key.
 *   • Smart Create's "batch" mode emits N warrants and the operator
 *     wants ONE printout grouping all of them. Rather than mutate the
 *     schema (one Warrant row per appropriation+quarter is the audit-
 *     friendly invariant we want to keep), we let the URL carry the
 *     grouping: a comma-separated list of warrant IDs to fetch and
 *     render as one document via the shared <WarrantPrintLayout/>.
 *
 * If the IDs span multiple MDAs the page still renders, but each line
 * row will show its own economic code and the body paragraph will
 * correctly read "approved appropriation lines" (plural). In practice
 * Smart Create only emits batches that share an MDA, so this is a
 * defence-in-depth fallback rather than a feature.
 */
import { useEffect, useMemo } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useQueries, useQuery } from '@tanstack/react-query';
import { Printer, ArrowLeft } from 'lucide-react';

import apiClient from '../../api/client';
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
    amount_released: string;
    release_date: string;
    authority_reference: string;
    notes: string;
    appropriation_mda?: string;
    appropriation_account?: string;
    appropriation_economic_code?: string;
    appropriation_amount_approved?: string;
}

export default function BatchWarrantPrintPreview() {
    const navigate = useNavigate();
    const [params] = useSearchParams();

    // Parse and de-dupe IDs so the same warrant doesn't get rendered
    // twice if a stale link slips through.
    const ids = useMemo(() => {
        const raw = params.get('ids') || '';
        return [...new Set(raw.split(',').map(s => s.trim()).filter(Boolean))];
    }, [params]);

    // ── Fetch every warrant in parallel via useQueries. Each call is
    //    a normal /budget/warrants/:id/ GET that the existing serializer
    //    already serves with the appropriation snapshot fields needed
    //    for the print layout.
    const warrantQueries = useQueries({
        queries: ids.map(id => ({
            queryKey: ['warrant-print', id],
            queryFn: async () => {
                const { data } = await apiClient.get(`/budget/warrants/${id}/`);
                return data as WarrantData;
            },
        })),
    });

    const { data: settings, isLoading: settingsLoading } =
        useQuery<WarrantPrintSettings>({
            queryKey: ['warrant-printout-settings'],
            queryFn: async () => {
                const { data } = await apiClient.get(
                    '/budget/warrant-printout-settings/current/',
                );
                return data;
            },
        });

    const allLoaded = warrantQueries.every(q => !q.isLoading);
    const warrants = warrantQueries
        .map(q => q.data)
        .filter((w): w is WarrantData => !!w);

    // Set the document title so saved-PDF filenames are useful — the
    // batch reference (shared across rows in batch mode) is the
    // most operator-friendly identifier.
    useEffect(() => {
        if (warrants.length) {
            const ref = warrants[0].authority_reference || `Batch-${warrants.length}`;
            document.title = `Warrant Batch ${ref} — Print Preview`;
        }
        return () => { document.title = 'Quot PSE'; };
    }, [warrants]);

    if (ids.length === 0) {
        return (
            <div style={{ padding: 60, textAlign: 'center', color: '#64748b' }}>
                <p>No warrant IDs were specified in the URL.</p>
                <button
                    onClick={() => navigate('/budget/warrants')}
                    style={{ marginTop: 12, padding: '8px 16px', cursor: 'pointer' }}
                >
                    Back to warrants
                </button>
            </div>
        );
    }

    if (!allLoaded || settingsLoading || !settings) {
        return (
            <div style={{ padding: 60, textAlign: 'center', color: '#64748b' }}>
                Loading {ids.length} warrant{ids.length === 1 ? '' : 's'}…
            </div>
        );
    }

    if (warrants.length === 0) {
        return (
            <div style={{ padding: 60, textAlign: 'center', color: '#dc2626' }}>
                None of the requested warrants could be loaded.
            </div>
        );
    }

    // ── Compose the single-document layout. The first warrant's
    //    metadata seeds the header (release date, MDA, quarter); each
    //    warrant becomes one line in the table.
    const head = warrants[0];
    // Shared reference falls back to a synthesised one when missing —
    // prefer the date range for new batches; quarter remains a legacy
    // fallback for historical print operations.
    const sharedRef = head.authority_reference
        || (head.effective_from && head.effective_to
            ? `BATCH/${head.effective_from}-${head.effective_to}/${head.appropriation_mda || ''}`
            : `BATCH/${head.quarter ? 'Q' + head.quarter : 'W' + head.id}/${head.appropriation_mda || ''}`);

    const lines: WarrantPrintLine[] = warrants.map(w => ({
        economic_code: w.appropriation_economic_code,
        economic_name: w.appropriation_account,
        amount_released: w.amount_released,
        appropriation_amount_approved: w.appropriation_amount_approved,
        notes: w.notes,
    }));

    // Concatenate per-line notes when several rows have any — they
    // print into the body_notes block under the lines table.
    const combinedNotes = warrants
        .filter(w => w.notes && w.notes.trim())
        .map(w => `${w.appropriation_economic_code}: ${w.notes}`)
        .join(' · ');

    const handlePrint = () => window.print();

    return (
        <>
            {/* Print stylesheet — same A4 page setup the single-warrant
                page uses; toolbar hidden when printing. */}
            <style>{`
                @page { size: A4 portrait; margin: 18mm; }
                @media print {
                    .no-print { display: none !important; }
                    body { background: white !important; }
                    .print-page {
                        box-shadow: none !important;
                        border: none !important;
                        margin: 0 !important;
                    }
                }
                @media screen { body { background: #e2e8f0; } }
            `}</style>

            <div className="no-print" style={{
                position: 'sticky', top: 0, zIndex: 10,
                background: '#0f172a', color: 'white',
                padding: '10px 24px',
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                gap: 12, fontFamily: "'Inter', -apple-system, sans-serif",
            }}>
                <button
                    onClick={() => navigate('/budget/warrants')}
                    style={toolbarBtn}
                >
                    <ArrowLeft size={14} /> Back to warrants
                </button>
                <div style={{ fontSize: 13, color: '#cbd5e1' }}>
                    <strong style={{ color: 'white' }}>Batch printout</strong>
                    {' · '}{warrants.length} warrant{warrants.length === 1 ? '' : 's'} merged into one document
                </div>
                <button
                    onClick={handlePrint}
                    style={{
                        ...toolbarBtn,
                        background: '#1e40af', border: 'none',
                        fontWeight: 700,
                    }}
                >
                    <Printer size={14} /> Print Batch
                </button>
            </div>

            <div className="print-page" style={{
                maxWidth: 794, margin: '24px auto',
                background: 'white',
                boxShadow: '0 8px 32px rgba(15, 23, 42, 0.12)',
            }}>
                <WarrantPrintLayout
                    settings={settings}
                    warrant_number={sharedRef}
                    effective_from={head.effective_from || undefined}
                    effective_to={head.effective_to || undefined}
                    quarter={head.quarter || undefined}
                    effective_status={head.effective_status}
                    release_date={head.release_date}
                    mda_name={head.appropriation_mda || 'designated MDA'}
                    lines={lines}
                    body_notes={combinedNotes || undefined}
                    mode="print"
                />
            </div>
        </>
    );
}

const toolbarBtn: React.CSSProperties = {
    display: 'flex', alignItems: 'center', gap: 6,
    padding: '7px 14px', border: '1px solid #334155',
    background: '#1e293b', color: 'white',
    borderRadius: 6, fontSize: 13, fontWeight: 600,
    cursor: 'pointer',
};
