/**
 * IPSAS 1 — Notes to the Financial Statements — Quot PSE
 * Route: /accounting/ipsas/notes
 *
 * Renders the machine-readable notes pack produced by
 * IPSASReportService.notes_to_financial_statements — a numbered list of
 * notes covering accounting policies, PPE, receivables/payables aging,
 * borrowings, provisions (IPSAS 19), IPSAS 33 transition, IPSAS 39
 * pensions, and IPSAS 42 social benefits.
 *
 * The ``data`` payload on each note is a dict — we auto-render it as a
 * two-column key/value table so new notes added to the service don't
 * require a frontend change.
 */
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Printer, FileText } from 'lucide-react';
import Sidebar from '../../../components/Sidebar';
import apiClient from '../../../api/client';
import ReportError from './ReportError';
import ExportExcelButton from './ExportExcelButton';

interface Note {
    number: number;
    title:  string;
    body:   string;
    data:   Record<string, unknown> | null;
}

interface NotesResponse {
    title: string;
    standard: string;
    fiscal_year: number;
    currency: string;
    notes: Note[];
}

const fmtNGN = (v: number | string): string => {
    const n = typeof v === 'string' ? parseFloat(v) : v;
    return 'NGN ' + (Number.isFinite(n) ? n : 0).toLocaleString('en-NG', {
        minimumFractionDigits: 2, maximumFractionDigits: 2,
    });
};

const prettify = (k: string): string =>
    k.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());

/** Heuristic: render a value as currency if the key hints at money. */
const looksLikeMoney = (key: string): boolean => {
    const k = key.toLowerCase();
    return (
        k.includes('amount') || k.includes('total') || k.includes('balance') ||
        k.includes('cost') || k.includes('value') || k.includes('liability') ||
        k.includes('asset') || k.includes('expense') || k.includes('revenue') ||
        k.includes('payable') || k.includes('receivable') || k.includes('debt') ||
        k.endsWith('_ngn') || k === 'opening' || k === 'closing'
    );
};

function renderScalar(key: string, value: unknown): string {
    if (value === null || value === undefined) return '—';
    if (typeof value === 'boolean') return value ? 'Yes' : 'No';
    if (typeof value === 'number' && looksLikeMoney(key)) return fmtNGN(value);
    if (typeof value === 'string') {
        const n = parseFloat(value);
        if (Number.isFinite(n) && looksLikeMoney(key)) return fmtNGN(value);
        return value;
    }
    if (typeof value === 'number') return value.toLocaleString('en-NG');
    return String(value);
}

interface NoteDataBlockProps {
    data: Record<string, unknown>;
}

function NoteDataBlock({ data }: NoteDataBlockProps) {
    const entries = Object.entries(data);
    if (entries.length === 0) return null;

    return (
        <div style={{ marginTop: 12 }}>
            {entries.map(([key, value]) => {
                // Array of rows → render as table
                if (Array.isArray(value)) {
                    if (value.length === 0) {
                        return (
                            <div key={key} style={{ marginTop: 10 }}>
                                <div style={{
                                    fontSize: 12, fontWeight: 700, color: '#64748b',
                                    textTransform: 'uppercase', marginBottom: 4,
                                }}>
                                    {prettify(key)}
                                </div>
                                <div style={{ fontSize: 13, color: '#94a3b8' }}>No records.</div>
                            </div>
                        );
                    }
                    const first = value[0] as Record<string, unknown>;
                    const cols = typeof first === 'object' && first !== null
                        ? Object.keys(first) : ['value'];
                    return (
                        <div key={key} style={{ marginTop: 12 }}>
                            <div style={{
                                fontSize: 12, fontWeight: 700, color: '#64748b',
                                textTransform: 'uppercase', marginBottom: 6,
                            }}>
                                {prettify(key)}
                            </div>
                            <div style={{ overflowX: 'auto' }}>
                                <table style={{
                                    width: '100%', borderCollapse: 'collapse',
                                    background: '#f8fafc', borderRadius: 6,
                                }}>
                                    <thead>
                                        <tr style={{ borderBottom: '1px solid #e8ecf1' }}>
                                            {cols.map(c => (
                                                <th key={c} style={{
                                                    padding: '8px 10px',
                                                    fontSize: 11, fontWeight: 700, color: '#64748b',
                                                    textTransform: 'uppercase',
                                                    textAlign: looksLikeMoney(c) ? 'right' : 'left',
                                                }}>
                                                    {prettify(c)}
                                                </th>
                                            ))}
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {(value as Array<Record<string, unknown>>).map((row, i) => (
                                            <tr key={i} style={{ borderBottom: '1px solid #eef2f7' }}>
                                                {cols.map(c => (
                                                    <td key={c} style={{
                                                        padding: '8px 10px', fontSize: 13,
                                                        textAlign: looksLikeMoney(c) ? 'right' : 'left',
                                                        fontFamily: looksLikeMoney(c) ? 'monospace' : undefined,
                                                    }}>
                                                        {renderScalar(c, row[c])}
                                                    </td>
                                                ))}
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    );
                }
                // Nested object → recursive render
                if (value !== null && typeof value === 'object') {
                    return (
                        <div key={key} style={{ marginTop: 12 }}>
                            <div style={{
                                fontSize: 12, fontWeight: 700, color: '#64748b',
                                textTransform: 'uppercase', marginBottom: 4,
                            }}>
                                {prettify(key)}
                            </div>
                            <div style={{ paddingLeft: 12 }}>
                                <NoteDataBlock data={value as Record<string, unknown>} />
                            </div>
                        </div>
                    );
                }
                // Scalar key/value row
                return (
                    <div key={key} style={{
                        display: 'flex', justifyContent: 'space-between',
                        padding: '6px 0', borderBottom: '1px solid #f1f5f9',
                    }}>
                        <span style={{ fontSize: 13, color: '#475569' }}>{prettify(key)}</span>
                        <span style={{
                            fontSize: 13, fontWeight: 600,
                            fontFamily: looksLikeMoney(key) ? 'monospace' : undefined,
                            color: '#1e293b',
                        }}>
                            {renderScalar(key, value)}
                        </span>
                    </div>
                );
            })}
        </div>
    );
}

export default function NotesToFinancialStatementsReport() {
    const [fy, setFy] = useState<number>(new Date().getFullYear());

    const { data, isLoading, error } = useQuery<NotesResponse>({
        queryKey: ['ipsas-notes', fy],
        queryFn: async () => {
            const res = await apiClient.get('/accounting/ipsas/notes/', {
                params: { fiscal_year: fy },
            });
            return res.data;
        },
        retry: false,
    });

    return (
        <div style={{ background: '#f1f5f9', minHeight: '100vh' }}>
            <Sidebar />
            <main className="ipsas-report" style={{ marginLeft: '260px', padding: '32px' }}>
                <div style={{
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    marginBottom: '24px',
                }}>
                    <div>
                        <h1 style={{
                            fontSize: '24px', fontWeight: 800, color: '#1e293b', margin: 0,
                            display: 'flex', alignItems: 'center', gap: 10,
                        }}>
                            <FileText size={22} /> Notes to the Financial Statements
                        </h1>
                        <p style={{ color: '#64748b', fontSize: '14px', margin: '4px 0 0' }}>
                            IPSAS 1 — Minimum Disclosure Notes Pack
                        </p>
                    </div>
                    <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
                        <select
                            value={fy}
                            onChange={e => setFy(parseInt(e.target.value))}
                            style={{
                                padding: '8px 12px', borderRadius: '8px',
                                border: '1px solid #e2e8f0', fontSize: '14px',
                            }}
                        >
                            {[2024, 2025, 2026, 2027].map(y => (
                                <option key={y} value={y}>FY {y}</option>
                            ))}
                        </select>
                        <button
                            onClick={() => window.print()}
                            style={{
                                display: 'flex', alignItems: 'center', gap: '6px',
                                padding: '8px 16px', borderRadius: '8px',
                                border: '1px solid #e2e8f0', background: '#fff',
                                cursor: 'pointer', fontSize: '14px',
                            }}
                        >
                            <Printer size={16} /> Print
                        </button>
                        <ExportExcelButton
                            endpoint="/accounting/ipsas/notes/"
                            params={{ fiscal_year: fy }}
                            filename={`notes-${fy}.xlsx`}
                        />
                    </div>
                </div>

                {isLoading ? (
                    <div style={{ textAlign: 'center', padding: '40px', color: '#94a3b8' }}>
                        Loading...
                    </div>
                ) : error ? (
                    <ReportError error={error} endpoint="/accounting/ipsas/notes/" />
                ) : data ? (
                    <div style={{ maxWidth: '960px' }}>
                        {(data.notes ?? []).map(note => (
                            <div
                                key={note.number}
                                style={{
                                    background: '#fff', borderRadius: '12px',
                                    border: '1px solid #e8ecf1', padding: '24px',
                                    marginBottom: '16px',
                                }}
                            >
                                <div style={{
                                    display: 'flex', alignItems: 'baseline', gap: 10,
                                    marginBottom: 10,
                                }}>
                                    <span style={{
                                        fontSize: 12, fontWeight: 700,
                                        background: '#1e4d8c', color: '#fff',
                                        padding: '3px 10px', borderRadius: 4,
                                        letterSpacing: '0.5px',
                                    }}>
                                        NOTE {note.number}
                                    </span>
                                    <h3 style={{
                                        margin: 0, fontSize: 17, fontWeight: 800,
                                        color: '#1e293b',
                                    }}>
                                        {note.title}
                                    </h3>
                                </div>

                                {note.body && (
                                    <p style={{
                                        fontSize: 13, lineHeight: 1.65,
                                        color: '#475569', whiteSpace: 'pre-line',
                                        margin: '0 0 6px',
                                    }}>
                                        {note.body}
                                    </p>
                                )}

                                {note.data && <NoteDataBlock data={note.data} />}
                            </div>
                        ))}
                        {(!data.notes || data.notes.length === 0) && (
                            <div style={{ textAlign: 'center', padding: '40px', color: '#94a3b8' }}>
                                No disclosure notes available for FY {fy}.
                            </div>
                        )}
                    </div>
                ) : null}

                <div style={{
                    textAlign: 'center', padding: '20px 0',
                    color: '#94a3b8', fontSize: '11px',
                }}>
                    Quot PSE IFMIS — IPSAS 1 Notes Pack
                </div>
            </main>
        </div>
    );
}
