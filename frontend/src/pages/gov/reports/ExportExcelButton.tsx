/**
 * Shared "Export to Excel" button for IPSAS + performance reports.
 *
 * Every IPSAS report view on the backend already supports
 * ``?format=xlsx`` via serve_report(); the button simply appends that
 * parameter to the current endpoint + query string, downloads the
 * file as a blob (so auth headers are injected by the axios client),
 * and triggers a local download.
 *
 * Example:
 *     <ExportExcelButton
 *         endpoint="/accounting/ipsas/financial-position/"
 *         params={{ fiscal_year: fy }}
 *         filename={`sofp-${fy}.xlsx`}
 *     />
 */
import { useState } from 'react';
import { FileSpreadsheet, Loader2 } from 'lucide-react';
import apiClient from '../../../api/client';

interface ExportExcelButtonProps {
    endpoint: string;
    params?: Record<string, string | number | undefined | null>;
    filename?: string;
    label?: string;
}

export default function ExportExcelButton({
    endpoint,
    params = {},
    filename,
    label = 'Export Excel',
}: ExportExcelButtonProps) {
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const handleExport = async () => {
        setLoading(true);
        setError(null);
        try {
            // Drop undefined/null params so axios doesn't stringify them.
            const cleanParams: Record<string, string | number> = {};
            for (const [k, v] of Object.entries(params)) {
                if (v !== undefined && v !== null && v !== '') {
                    cleanParams[k] = v;
                }
            }
            cleanParams.format = 'xlsx';

            const response = await apiClient.get(endpoint, {
                params: cleanParams,
                responseType: 'blob',
            });

            // Prefer the server-suggested filename from
            // Content-Disposition; fall back to the caller's hint.
            const cd = response.headers['content-disposition'] as string | undefined;
            let suggestedName: string | undefined;
            if (cd) {
                const match = cd.match(/filename="?([^"]+)"?/i);
                if (match) suggestedName = match[1];
            }
            const finalName =
                suggestedName ?? filename ?? 'report.xlsx';

            const blob = new Blob([response.data], {
                type:
                    response.headers['content-type'] ||
                    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = finalName;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        } catch (err: unknown) {
            const msg = err instanceof Error ? err.message : 'Export failed';
            setError(msg);
            // Auto-clear after 4 seconds so the UI doesn't stay in an
            // error state indefinitely.
            setTimeout(() => setError(null), 4000);
        } finally {
            setLoading(false);
        }
    };

    return (
        <>
            <button
                onClick={handleExport}
                disabled={loading}
                title="Download as Excel (.xlsx)"
                style={{
                    display: 'flex', alignItems: 'center', gap: '6px',
                    padding: '8px 16px', borderRadius: '8px',
                    border: '1px solid #10b981',
                    background: loading ? '#d1fae5' : '#ecfdf5',
                    color: '#047857',
                    cursor: loading ? 'wait' : 'pointer',
                    fontSize: '14px', fontWeight: 600,
                    opacity: loading ? 0.8 : 1,
                }}
            >
                {loading
                    ? <Loader2 size={16} style={{ animation: 'spin 1s linear infinite' }} />
                    : <FileSpreadsheet size={16} />}
                {loading ? 'Preparing…' : label}
            </button>
            {error && (
                <div style={{
                    position: 'fixed', bottom: 24, right: 24,
                    background: '#fef2f2', border: '1px solid #fca5a5',
                    color: '#991b1b', padding: '10px 14px', borderRadius: 8,
                    fontSize: 13, zIndex: 9999, maxWidth: 360,
                    boxShadow: '0 4px 12px rgba(0,0,0,0.1)',
                }}>
                    Export failed: {error}
                </div>
            )}
            <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
        </>
    );
}
