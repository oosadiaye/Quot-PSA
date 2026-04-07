import { useState, useRef, useEffect } from 'react';
import { ChevronDown } from 'lucide-react';
import { useCurrencies } from '../../features/accounting/hooks/useAccountingEnhancements';

interface CurrencySelectorProps {
    value: string | null;
    onChange: (currencyCode: string | null) => void;
    label?: string;
    showSymbol?: boolean;
    style?: React.CSSProperties;
}

interface Currency {
    id: number;
    code: string;
    name: string;
    symbol: string;
    is_active: boolean;
}

export default function CurrencySelector({
    value,
    onChange,
    label = 'Currency',
    showSymbol = true,
    style,
}: CurrencySelectorProps) {
    const { data: currencies } = useCurrencies();
    const [open, setOpen] = useState(false);
    const ref = useRef<HTMLDivElement>(null);

    useEffect(() => {
        const handler = (e: MouseEvent) => {
            if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
        };
        document.addEventListener('mousedown', handler);
        return () => document.removeEventListener('mousedown', handler);
    }, []);

    const activeCurrencies = (currencies as Currency[] | undefined)?.filter((c) => c.is_active) || [];
    const selected = activeCurrencies.find((c) => c.code === value);

    return (
        <div ref={ref} style={{ position: 'relative', display: 'inline-block', ...style }}>
            {label && (
                <label style={{
                    display: 'block', fontSize: 'var(--text-xs)', fontWeight: 600, marginBottom: '0.25rem',
                    color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em',
                }}>
                    {label}
                </label>
            )}
            <button
                onClick={() => setOpen(!open)}
                style={{
                    display: 'flex', alignItems: 'center', gap: '0.5rem',
                    padding: '0.4rem 0.75rem', borderRadius: '6px',
                    border: '1px solid var(--color-border)', background: 'var(--color-surface)',
                    cursor: 'pointer', fontSize: 'var(--text-sm)', fontWeight: 500,
                    color: 'var(--color-text)', minWidth: '100px',
                }}
            >
                {selected ? (
                    <>
                        {showSymbol && <span style={{ fontWeight: 600 }}>{selected.symbol}</span>}
                        <span>{selected.code}</span>
                    </>
                ) : (
                    <span style={{ color: 'var(--color-text-muted)' }}>Select</span>
                )}
                <ChevronDown size={14} style={{ marginLeft: 'auto', opacity: 0.5 }} />
            </button>

            {open && (
                <div style={{
                    position: 'absolute', top: '100%', left: 0, zIndex: 50,
                    marginTop: '4px', minWidth: '180px', maxHeight: '240px', overflowY: 'auto',
                    background: 'var(--color-surface)', border: '1px solid var(--color-border)',
                    borderRadius: '8px', boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
                }}>
                    <div
                        onClick={() => { onChange(null); setOpen(false); }}
                        style={{
                            padding: '0.5rem 0.75rem', cursor: 'pointer', fontSize: 'var(--text-sm)',
                            color: 'var(--color-text-muted)', borderBottom: '1px solid var(--color-border)',
                        }}
                        onMouseOver={(e) => e.currentTarget.style.background = 'rgba(59,130,246,0.08)'}
                        onMouseOut={(e) => e.currentTarget.style.background = 'transparent'}
                    >
                        Default (no conversion)
                    </div>
                    {activeCurrencies.map((c) => (
                        <div
                            key={c.id}
                            onClick={() => { onChange(c.code); setOpen(false); }}
                            style={{
                                padding: '0.5rem 0.75rem', cursor: 'pointer', fontSize: 'var(--text-sm)',
                                display: 'flex', alignItems: 'center', gap: '0.5rem',
                                background: value === c.code ? 'rgba(59,130,246,0.1)' : 'transparent',
                                fontWeight: value === c.code ? 600 : 400,
                            }}
                            onMouseOver={(e) => e.currentTarget.style.background = 'rgba(59,130,246,0.08)'}
                            onMouseOut={(e) => e.currentTarget.style.background = value === c.code ? 'rgba(59,130,246,0.1)' : 'transparent'}
                        >
                            <span style={{ fontWeight: 600, minWidth: '20px' }}>{c.symbol}</span>
                            <span>{c.code}</span>
                            <span style={{ color: 'var(--color-text-muted)', fontSize: 'var(--text-xs)', marginLeft: 'auto' }}>{c.name}</span>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}
