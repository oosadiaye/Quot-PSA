/**
 * Shared filter bar for performance-report pages.
 *
 * Renders a single text input that does case-insensitive "contains"
 * matching against code OR name in the parent component. Purely
 * presentational — the parent owns the filtering logic via useMemo so
 * the filter is reflected in the table body *and* footer row counts.
 */
import { Search } from 'lucide-react';

interface FilterBarProps {
    value: string;
    onChange: (v: string) => void;
    placeholder: string;
    total: number;
    visible: number;
}

export default function FilterBar({ value, onChange, placeholder, total, visible }: FilterBarProps) {
    return (
        <div style={{
            background: '#fff', borderRadius: 12, border: '1px solid #e8ecf1',
            padding: '12px 16px', marginBottom: 20, display: 'flex', alignItems: 'center', gap: 10,
        }}>
            <Search size={16} style={{ color: '#94a3b8' }} />
            <input
                type="text"
                value={value}
                onChange={e => onChange(e.target.value)}
                placeholder={placeholder}
                style={{
                    flex: 1, padding: '8px 10px', border: '1px solid #e2e8f0',
                    borderRadius: 8, fontSize: 14, outline: 'none',
                }}
            />
            {value && (
                <button
                    onClick={() => onChange('')}
                    style={{
                        padding: '6px 10px', border: '1px solid #e2e8f0', borderRadius: 8,
                        background: '#fff', cursor: 'pointer', fontSize: 12, color: '#64748b',
                    }}
                >
                    Clear
                </button>
            )}
            <div style={{ fontSize: 12, color: '#64748b', whiteSpace: 'nowrap' }}>
                {total > 0 ? `${visible} of ${total} row${total === 1 ? '' : 's'}` : ''}
            </div>
        </div>
    );
}
