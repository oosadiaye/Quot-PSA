/**
 * DocumentPrintLayout
 * ===================
 * One A4 page for an official procurement document: tenant letterhead (logo + name from
 * BrandingContext), a title block, a key/value details grid, the body, and signature lines.
 * A screen toolbar offers Back and Print; it never prints.
 *
 * While printing, everything outside `.doc-print` is hidden, so the app shell never leaks onto paper.
 */
import type { ReactNode } from 'react';
import { ArrowLeft, Printer } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import BrandedPrintHeader from './BrandedPrintHeader';
import LoadingScreen from '../common/LoadingScreen';

export interface DetailField {
    label: string;
    value: ReactNode;
}

interface Props {
    /** "Purchase Order", "Goods Received Note", ... */
    title: string;
    /** The document's own number, shown large under the title. */
    number: string;
    status?: string;
    details: DetailField[];
    /** Role names for the signature lines, in order. */
    signatories: string[];
    children: ReactNode;
    isLoading?: boolean;
    error?: boolean;
}

const css = `
.doc-screen { position: fixed; inset: 0; z-index: 1000; overflow: auto; background: #e2e8f0; padding: 16px; }
.doc-toolbar { max-width: 210mm; margin: 0 auto 12px; display: flex; gap: 8px; }
.doc-toolbar button { display: inline-flex; align-items: center; gap: 6px; padding: 8px 14px; border-radius: 8px; border: 1px solid #cbd5e1; background: #fff; font: inherit; font-size: 13px; font-weight: 600; cursor: pointer; }
.doc-toolbar button.primary { background: #064e3b; color: #fff; border-color: #064e3b; }
.doc-print { max-width: 210mm; min-height: 297mm; margin: 0 auto; background: #fff; color: #0f172a; padding: 14mm; box-sizing: border-box; box-shadow: 0 2px 12px rgba(0,0,0,.15); font-family: 'Helvetica Neue', Arial, sans-serif; font-size: 12px; }
.doc-title { text-align: center; margin: 14px 0 10px; }
.doc-title h1 { margin: 0; font-size: 18px; letter-spacing: 2px; text-transform: uppercase; }
.doc-title .num { font-size: 15px; font-weight: 700; margin-top: 2px; }
.doc-title .st { display: inline-block; margin-top: 4px; padding: 1px 10px; border: 1px solid #064e3b; border-radius: 10px; font-size: 10px; text-transform: uppercase; color: #064e3b; }
.doc-details { display: grid; grid-template-columns: 1fr 1fr; gap: 4px 24px; margin: 10px 0 14px; }
.doc-details div { display: flex; gap: 6px; border-bottom: 1px dotted #cbd5e1; padding: 2px 0; }
.doc-details dt { color: #475569; min-width: 38%; }
.doc-details dd { margin: 0; font-weight: 600; }
.doc-table { width: 100%; border-collapse: collapse; margin: 6px 0 10px; }
.doc-table th { background: #f1f5f9; text-align: left; font-size: 11px; padding: 5px 6px; border: 1px solid #94a3b8; }
.doc-table td { padding: 5px 6px; border: 1px solid #cbd5e1; vertical-align: top; }
.doc-table .r { text-align: right; font-variant-numeric: tabular-nums; }
.doc-table tfoot td { font-weight: 700; background: #f8fafc; }
.doc-note { margin: 8px 0; white-space: pre-wrap; }
.doc-note b { display: block; font-size: 11px; color: #475569; text-transform: uppercase; }
.doc-sigs { display: grid; grid-template-columns: repeat(var(--sig-cols, 3), 1fr); gap: 20px; margin-top: 36px; }
.doc-sig { padding-top: 34px; border-top: 1px solid #0f172a; font-size: 11px; text-align: center; }
.doc-sig small { display: block; color: #64748b; margin-top: 2px; }
.doc-foot { margin-top: 18px; font-size: 9px; color: #64748b; text-align: center; }
@media print {
  body * { visibility: hidden; }
  .doc-print, .doc-print * { visibility: visible; }
  .doc-screen { position: static; background: #fff; padding: 0; overflow: visible; }
  .doc-print { position: absolute; left: 0; top: 0; width: 100%; box-shadow: none; padding: 0; min-height: 0; }
  .doc-toolbar { display: none !important; }
  @page { size: A4; margin: 12mm; }
}
`;

export default function DocumentPrintLayout({ title, number, status, details, signatories, children, isLoading, error }: Props) {
    const navigate = useNavigate();
    if (isLoading) return <LoadingScreen />;
    return (
        <div className="doc-screen">
            <style>{css}</style>
            <div className="doc-toolbar">
                <button type="button" onClick={() => navigate(-1)}><ArrowLeft size={14} /> Back</button>
                <button type="button" className="primary" data-testid="doc-print" onClick={() => window.print()} disabled={error}>
                    <Printer size={14} /> Print
                </button>
            </div>
            <article className="doc-print" data-testid="doc-print-page" data-no-tools>
                {error ? <p>This document could not be loaded.</p> : (
                    <>
                        <BrandedPrintHeader />
                        <div className="doc-title">
                            <h1>{title}</h1>
                            <div className="num">{number}</div>
                            {status && <span className="st">{status}</span>}
                        </div>
                        <dl className="doc-details">
                            {details.filter(d => d.value !== null && d.value !== undefined && d.value !== '').map(d => (
                                <div key={d.label}><dt>{d.label}</dt><dd>{d.value}</dd></div>
                            ))}
                        </dl>
                        {children}
                        <div className="doc-sigs" style={{ ['--sig-cols' as string]: Math.min(signatories.length, 4) }}>
                            {signatories.map(role => (
                                <div key={role} className="doc-sig">{role}<small>Name · Signature · Date</small></div>
                            ))}
                        </div>
                        <div className="doc-foot">Computer-generated document. Valid only with the required signatures.</div>
                    </>
                )}
            </article>
        </div>
    );
}
