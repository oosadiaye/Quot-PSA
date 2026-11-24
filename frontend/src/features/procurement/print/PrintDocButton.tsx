import { Printer } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

interface Props {
    /** The document's print page, e.g. `/procurement/orders/12/print`. */
    to: string;
}

/** Header button that opens a document's branded print page. */
export default function PrintDocButton({ to }: Props) {
    const navigate = useNavigate();
    return (
        <button
            type="button" data-testid="print-doc" onClick={() => navigate(to)}
            style={{
                padding: '0.6rem 1.25rem', fontWeight: 600, borderRadius: '8px', cursor: 'pointer',
                background: 'rgba(255,255,255,0.18)', color: 'white', border: '1px solid rgba(255,255,255,0.3)',
                display: 'inline-flex', alignItems: 'center', gap: '0.4rem',
            }}
        >
            <Printer size={16} /> Print
        </button>
    );
}
