import { useEffect, type CSSProperties, type ReactNode } from 'react';
import { X } from 'lucide-react';

interface Props {
    title: string;
    subtitle?: string;
    onClose: () => void;
    children: ReactNode;
    footer?: ReactNode;
    width?: number;
}

/** A plain dialog: closes on Escape and on the backdrop, sits above the app shell (sidebar, chat) and below nothing. */
export default function ModalShell({ title, subtitle, onClose, children, footer, width = 720 }: Props) {
    useEffect(() => {
        const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, [onClose]);

    return (
        <div className="cash-modal-backdrop" role="presentation" onMouseDown={e => { if (e.target === e.currentTarget) onClose(); }}>
            <section className="cash-modal" data-no-tools role="dialog" aria-modal="true" aria-label={title} style={{ maxWidth: width }} data-testid="cash-modal">
                <header className="cash-modal-head">
                    <div>
                        <h2>{title}</h2>
                        {subtitle && <p>{subtitle}</p>}
                    </div>
                    <button type="button" className="cash-icon-btn" onClick={onClose} aria-label="Close"><X size={18} /></button>
                </header>
                <div className="cash-modal-body">{children}</div>
                {footer && <footer className="cash-modal-foot">{footer}</footer>}
            </section>
        </div>
    );
}

export function Field({ label, error, children, style }: { label: string; error?: string; children: ReactNode; style?: CSSProperties }) {
    return (
        <label className="cash-field" style={style}>
            <span>{label}</span>
            {children}
            {error && <small className="cash-field-error" role="alert">{error}</small>}
        </label>
    );
}

export function ErrorLine({ message }: { message: string }) {
    if (!message) return null;
    return <div className="cash-error" role="alert" data-testid="cash-error">{message}</div>;
}
