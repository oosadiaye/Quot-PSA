import { useRef, useState } from 'react';
import { ScanLine, Upload, FileText, X, Loader2, Sparkles, AlertTriangle } from 'lucide-react';
import apiClient from '../../../api/client';
import logger from '../../../utils/logger';

// ───────────────────────────────────────────────────────────────────────────
// AiScanModal — upload a supplier invoice (image or PDF), have the tenant's
// configured AI extraction model read it, and create a Draft VendorInvoice
// the operator then reviews. Posts to /accounting/vendor-invoices/scan-extract/.
// ───────────────────────────────────────────────────────────────────────────

interface ScanResult {
    invoice_id: number;
    invoice_number: string;
    matched_vendor: string | null;
    warnings?: string[];
    ai?: { model_id?: string; cost_usd?: string; pages?: number };
}

interface AiScanModalProps {
    onClose: () => void;
    onCreated: (invoiceId: number, result: ScanResult) => void;
}

const ACCEPT = 'image/png,image/jpeg,image/webp,application/pdf';

export default function AiScanModal({ onClose, onCreated }: AiScanModalProps) {
    const inputRef = useRef<HTMLInputElement>(null);
    const [file, setFile] = useState<File | null>(null);
    const [dragging, setDragging] = useState(false);
    const [scanning, setScanning] = useState(false);
    const [error, setError] = useState<string>('');
    const [notEnabled, setNotEnabled] = useState(false);

    const pick = (f: File | null | undefined) => {
        setError('');
        setNotEnabled(false);
        if (!f) return;
        const ok = f.type.startsWith('image/') || f.type === 'application/pdf'
            || /\.(png|jpe?g|webp|pdf)$/i.test(f.name);
        if (!ok) { setError('Unsupported file. Upload a PNG/JPG/WebP image or a PDF.'); return; }
        if (f.size > 15 * 1024 * 1024) { setError('File is larger than the 15 MB limit.'); return; }
        setFile(f);
    };

    const scan = async () => {
        if (!file) return;
        setScanning(true);
        setError('');
        setNotEnabled(false);
        try {
            const fd = new FormData();
            fd.append('file', file);
            const res = await apiClient.post('/accounting/vendor-invoices/scan-extract/', fd, {
                headers: { 'Content-Type': 'multipart/form-data' },
            });
            onCreated(res.data.invoice_id, res.data as ScanResult);
        } catch (err: any) {
            logger.error('AI invoice scan failed:', err);
            const data = err?.response?.data;
            if (data?.code === 'AI_NOT_ENABLED') setNotEnabled(true);
            setError(data?.error || err?.message || 'Scan failed. Please try again.');
        } finally {
            setScanning(false);
        }
    };

    const fmtSize = (n: number) => n < 1024 * 1024 ? `${(n / 1024).toFixed(0)} KB` : `${(n / 1024 / 1024).toFixed(1)} MB`;

    return (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(15,23,42,0.55)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 9999, padding: '1rem' }} onClick={onClose}>
            <div style={{ background: 'var(--color-surface)', borderRadius: 12, padding: '1.5rem', maxWidth: 560, width: '100%', boxShadow: '0 25px 60px rgba(0,0,0,0.3)' }} onClick={(e) => e.stopPropagation()}>
                {/* Header */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1rem' }}>
                    <div>
                        <h3 style={{ margin: 0, fontSize: 'var(--text-lg)', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                            <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 30, height: 30, borderRadius: 8, background: 'linear-gradient(135deg,#4f46e5,#7c3aed)', color: '#fff' }}>
                                <ScanLine size={17} />
                            </span>
                            Scan invoice with AI
                        </h3>
                        <p style={{ margin: '0.35rem 0 0', fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>
                            Upload a supplier invoice image or PDF — the details are read out and a <strong>Draft</strong> invoice is created for you to review.
                        </p>
                    </div>
                    <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-muted)' }}><X size={20} /></button>
                </div>

                {/* Drop / pick area */}
                <div
                    onClick={() => !scanning && inputRef.current?.click()}
                    onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
                    onDragLeave={() => setDragging(false)}
                    onDrop={(e) => { e.preventDefault(); setDragging(false); pick(e.dataTransfer.files?.[0]); }}
                    style={{
                        border: `2px dashed ${dragging ? '#4f46e5' : 'var(--color-border)'}`,
                        borderRadius: 10, padding: '1.75rem 1rem', textAlign: 'center',
                        cursor: scanning ? 'default' : 'pointer', marginBottom: '0.9rem',
                        background: dragging ? 'rgba(79,70,229,0.05)' : 'rgba(148,163,184,0.04)',
                        transition: 'border-color 0.15s, background 0.15s',
                    }}
                >
                    <input ref={inputRef} type="file" accept={ACCEPT} style={{ display: 'none' }} onChange={(e) => pick(e.target.files?.[0])} />
                    {file ? (
                        <div style={{ display: 'inline-flex', alignItems: 'center', gap: '0.6rem' }}>
                            <FileText size={22} color="#4f46e5" />
                            <div style={{ textAlign: 'left' }}>
                                <div style={{ fontWeight: 600, fontSize: 'var(--text-sm)' }}>{file.name}</div>
                                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>{fmtSize(file.size)} · click to replace</div>
                            </div>
                        </div>
                    ) : (
                        <div style={{ color: 'var(--color-text-muted)' }}>
                            <Upload size={26} style={{ margin: '0 auto 0.4rem', opacity: 0.6 }} />
                            <div style={{ fontWeight: 600, fontSize: 'var(--text-sm)', color: 'var(--color-text)' }}>Drop an invoice here, or click to choose</div>
                            <div style={{ fontSize: 'var(--text-xs)', marginTop: 2 }}>PNG, JPG, WebP or PDF · up to 15 MB</div>
                        </div>
                    )}
                </div>

                {/* Error / not-enabled */}
                {error && (
                    <div style={{ display: 'flex', gap: '0.5rem', padding: '0.7rem 0.9rem', marginBottom: '0.9rem', borderRadius: 8, background: '#fef2f2', border: '1px solid #fecaca', color: '#991b1b', fontSize: 'var(--text-sm)' }}>
                        <AlertTriangle size={16} style={{ flexShrink: 0, marginTop: 1 }} />
                        <div>
                            {error}
                            {notEnabled && (
                                <div style={{ marginTop: 4, fontSize: 'var(--text-xs)' }}>
                                    Enable “Document extraction” for your organisation in <a href="/settings/ai" style={{ color: '#991b1b', fontWeight: 600 }}>AI settings</a>.
                                </div>
                            )}
                        </div>
                    </div>
                )}

                {/* Data-policy note */}
                <p style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', fontSize: '0.7rem', color: 'var(--color-text-muted)', marginBottom: '1rem' }}>
                    <Sparkles size={12} /> The document is sent to your organisation’s configured AI provider for reading. Every scan is logged.
                </p>

                {/* Footer */}
                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.6rem' }}>
                    <button onClick={onClose} disabled={scanning} className="btn btn-outline" style={{ padding: '0.5rem 1rem' }}>Cancel</button>
                    <button onClick={scan} disabled={!file || scanning} className="btn btn-primary" style={{ padding: '0.5rem 1.1rem', display: 'inline-flex', alignItems: 'center', gap: '0.4rem', opacity: (!file || scanning) ? 0.6 : 1 }}>
                        {scanning ? <><Loader2 size={16} className="spin" /> Reading invoice…</> : <><ScanLine size={16} /> Scan &amp; create draft</>}
                    </button>
                </div>

                <style>{`@keyframes aiscan-spin { to { transform: rotate(360deg); } } .spin { animation: aiscan-spin 0.8s linear infinite; }`}</style>
            </div>
        </div>
    );
}
