/**
 * PdfPreviewModal — embed a PDF preview inside the application
 * without navigating away.
 *
 * Why an iframe rather than PDF.js: every modern browser ships with
 * a built-in PDF viewer that handles `iframe[src=*.pdf]` natively
 * (Chrome, Edge, Firefox, Safari). Pulling in PDF.js would add ~500 KB
 * to the bundle for a viewer the browser already has — not worth it
 * for a settings-page preview that opens occasionally.
 *
 * Why we fetch the PDF and pipe it through a `blob:` URL rather than
 * pointing the iframe straight at the absolute media URL: the Django
 * backend sets `X_FRAME_OPTIONS = 'DENY'` globally (clickjacking
 * defence), which travels on every response including served media.
 * That header makes the browser refuse to render the PDF inside an
 * iframe — the modal would just go blank. A `blob:` URL is minted
 * client-side, is same-origin to the page, and `X-Frame-Options`
 * doesn't apply. As a side benefit, the fetch goes through `apiClient`
 * so the auth token + tenant header come along automatically, which
 * also future-proofs us against locking media down behind auth.
 *
 * Accessibility:
 *   • ESC closes the modal.
 *   • Backdrop click closes the modal.
 *   • Focus is moved to the close button on open so keyboard users
 *     can tab back into the app cleanly.
 *
 * Body scroll lock applied while the modal is open so the page
 * underneath doesn't drift when the user scrolls inside the iframe.
 */
import { useEffect, useRef, useState } from 'react';
import { X, Download, ExternalLink, AlertTriangle, Loader2 } from 'lucide-react';
import apiClient from '../api/client';

interface PdfPreviewModalProps {
    /** Absolute URL to the PDF. When null/empty, modal stays closed. */
    url: string | null;
    /** Heading shown in the modal header. */
    title?: string;
    /** Optional secondary line under the title (e.g. tenant name). */
    subtitle?: string;
    /** Called when the user requests a close (ESC, backdrop, X). */
    onClose: () => void;
}

export default function PdfPreviewModal({
    url, title = 'PDF Preview', subtitle, onClose,
}: PdfPreviewModalProps) {
    const closeBtnRef = useRef<HTMLButtonElement>(null);
    const [blobUrl, setBlobUrl] = useState<string | null>(null);
    const [loadError, setLoadError] = useState<string | null>(null);
    const [loading, setLoading] = useState<boolean>(true);

    // ESC closes; lock body scroll while open.
    useEffect(() => {
        const onKey = (e: KeyboardEvent) => {
            if (e.key === 'Escape') onClose();
        };
        document.addEventListener('keydown', onKey);
        const prevOverflow = document.body.style.overflow;
        document.body.style.overflow = 'hidden';
        // Move focus to the close button so keyboard users land in
        // a sensible place. Skip if we're not actually mounted (url=null).
        closeBtnRef.current?.focus();
        return () => {
            document.removeEventListener('keydown', onKey);
            document.body.style.overflow = prevOverflow;
        };
    }, [onClose]);

    // Fetch the PDF as a blob and turn it into an in-memory `blob:` URL
    // for the iframe. See header comment for the X-Frame-Options reason
    // we don't just point the iframe straight at `url`.
    useEffect(() => {
        if (!url) return;
        let cancelled = false;
        let mintedUrl: string | null = null;
        setLoading(true);
        setLoadError(null);
        setBlobUrl(null);

        (async () => {
            try {
                // Use a raw axios instance via apiClient with `responseType: 'blob'`
                // and `baseURL: ''` override — the URL we got from the serializer
                // is already absolute (request.build_absolute_uri).
                const resp = await apiClient.get(url, {
                    baseURL: '',
                    responseType: 'blob',
                });
                if (cancelled) return;
                const blob = resp.data instanceof Blob
                    ? resp.data
                    : new Blob([resp.data], { type: 'application/pdf' });
                // Some servers respond with a generic content-type for FileField
                // downloads. Force `application/pdf` so the browser viewer
                // engages instead of offering a download.
                const pdfBlob = blob.type === 'application/pdf'
                    ? blob
                    : new Blob([blob], { type: 'application/pdf' });
                mintedUrl = URL.createObjectURL(pdfBlob);
                setBlobUrl(mintedUrl);
            } catch (e: unknown) {
                if (cancelled) return;
                const errObj = e as { response?: { status?: number }; message?: string };
                setLoadError(
                    errObj?.response?.status
                        ? `Failed to load PDF (HTTP ${errObj.response.status}).`
                        : errObj?.message || 'Failed to load PDF.',
                );
            } finally {
                if (!cancelled) setLoading(false);
            }
        })();

        return () => {
            cancelled = true;
            if (mintedUrl) URL.revokeObjectURL(mintedUrl);
        };
    }, [url]);

    if (!url) return null;

    const iframeSrc = blobUrl ? blobUrl + '#toolbar=1&view=FitH' : null;

    return (
        <div
            role="dialog"
            aria-modal="true"
            aria-label={title}
            onClick={onClose}
            style={{
                position: 'fixed', inset: 0, zIndex: 1000,
                background: 'rgba(15, 23, 42, 0.6)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                padding: 24,
                animation: 'pdf-modal-in 120ms ease-out',
            }}
        >
            <style>{`
                @keyframes pdf-modal-in {
                    from { opacity: 0; }
                    to   { opacity: 1; }
                }
            `}</style>
            <div
                onClick={(e) => e.stopPropagation()}
                style={{
                    background: '#fff', borderRadius: 12,
                    width: '100%', maxWidth: 1100,
                    height: 'min(880px, calc(100vh - 48px))',
                    display: 'flex', flexDirection: 'column',
                    boxShadow: '0 24px 64px rgba(15, 23, 42, 0.35)',
                    overflow: 'hidden',
                }}
            >
                {/* Header */}
                <div style={{
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    padding: '14px 18px', borderBottom: '1px solid #e2e8f0',
                    flexShrink: 0,
                }}>
                    <div>
                        <div style={{ fontSize: 15, fontWeight: 700, color: '#0f172a' }}>
                            {title}
                        </div>
                        {subtitle && (
                            <div style={{ fontSize: 12, color: '#64748b', marginTop: 2 }}>
                                {subtitle}
                            </div>
                        )}
                    </div>
                    <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                        <a
                            href={url}
                            target="_blank"
                            rel="noopener noreferrer"
                            style={btnSecondary}
                            title="Open in a new tab (full browser controls)"
                        >
                            <ExternalLink size={13} /> Open in new tab
                        </a>
                        <a
                            href={blobUrl ?? url}
                            download
                            style={btnSecondary}
                            title="Download to your computer"
                        >
                            <Download size={13} /> Download
                        </a>
                        <button
                            ref={closeBtnRef}
                            onClick={onClose}
                            aria-label="Close preview"
                            style={btnClose}
                        >
                            <X size={16} />
                        </button>
                    </div>
                </div>

                {/* Body — loader, error, or the native PDF viewer in an iframe.
                    See file header for why we use a blob: URL instead of the
                    raw media URL. */}
                {loading && (
                    <div style={fillCenter}>
                        <Loader2 size={28} color="#1e40af" className="pdf-spin" />
                        <div style={{ fontSize: 13, color: '#475569', marginTop: 10 }}>
                            Loading sample template…
                        </div>
                        <style>{`
                            .pdf-spin { animation: pdf-spin 800ms linear infinite; }
                            @keyframes pdf-spin {
                                from { transform: rotate(0deg); }
                                to   { transform: rotate(360deg); }
                            }
                        `}</style>
                    </div>
                )}
                {!loading && loadError && (
                    <div style={{ ...fillCenter, padding: 24, textAlign: 'center' }}>
                        <AlertTriangle size={28} color="#b91c1c" />
                        <div style={{ fontSize: 14, fontWeight: 600, color: '#0f172a', marginTop: 10 }}>
                            Couldn't load the PDF preview
                        </div>
                        <div style={{ fontSize: 13, color: '#64748b', marginTop: 4, maxWidth: 480 }}>
                            {loadError} You can still open it in a new tab using the
                            link above; the in-app viewer needs to fetch the file
                            through the API to bypass the iframe security header.
                        </div>
                    </div>
                )}
                {!loading && !loadError && iframeSrc && (
                    <iframe
                        src={iframeSrc}
                        title={title}
                        style={{
                            flex: 1, border: 'none', background: '#525659',
                        }}
                    />
                )}
            </div>
        </div>
    );
}

const btnSecondary: React.CSSProperties = {
    display: 'inline-flex', alignItems: 'center', gap: 5,
    padding: '6px 11px', borderRadius: 6,
    background: '#f1f5f9', border: '1px solid #cbd5e1',
    color: '#1e293b', fontSize: 12, fontWeight: 600,
    textDecoration: 'none', cursor: 'pointer',
};
const btnClose: React.CSSProperties = {
    display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
    width: 32, height: 32, borderRadius: 8,
    background: '#f1f5f9', border: '1px solid #cbd5e1',
    color: '#1e293b', cursor: 'pointer',
};
const fillCenter: React.CSSProperties = {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    background: '#f8fafc',
};
