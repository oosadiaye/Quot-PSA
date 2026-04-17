/**
 * SearchableSelect — Type-to-search dropdown for Quot PSE forms.
 *
 * Replaces standard <select> with a searchable combobox:
 * - Click to open full list
 * - Type to filter options
 * - Click an option to select
 * - Shows selected value in the input
 */
import { useState, useRef, useEffect, useMemo } from 'react';
import { Search, ChevronDown, X } from 'lucide-react';

interface Option {
    value: string;
    label: string;
    sublabel?: string;
}

interface SearchableSelectProps {
    options: Option[];
    value: string;
    onChange: (value: string) => void;
    placeholder?: string;
    required?: boolean;
    style?: React.CSSProperties;
}

export default function SearchableSelect({
    options, value, onChange, placeholder = 'Search or select...', required, style,
}: SearchableSelectProps) {
    const [open, setOpen] = useState(false);
    const [search, setSearch] = useState('');
    const ref = useRef<HTMLDivElement>(null);
    const inputRef = useRef<HTMLInputElement>(null);

    // Close on outside click
    useEffect(() => {
        const handler = (e: MouseEvent) => {
            if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
        };
        document.addEventListener('mousedown', handler);
        return () => document.removeEventListener('mousedown', handler);
    }, []);

    // Find selected option label
    const selectedOption = options.find(o => o.value === value);

    // Filter options by search
    const filtered = useMemo(() => {
        if (!search.trim()) return options;
        const q = search.toLowerCase();
        return options.filter(o =>
            o.label.toLowerCase().includes(q) ||
            (o.sublabel && o.sublabel.toLowerCase().includes(q)) ||
            o.value.toLowerCase().includes(q)
        );
    }, [options, search]);

    const handleSelect = (optValue: string) => {
        onChange(optValue);
        setSearch('');
        setOpen(false);
    };

    const handleClear = (e: React.MouseEvent) => {
        e.stopPropagation();
        onChange('');
        setSearch('');
    };

    const handleInputClick = () => {
        setOpen(true);
        setSearch('');
        setTimeout(() => inputRef.current?.focus(), 50);
    };

    const baseStyle: React.CSSProperties = {
        width: '100%', padding: '0.5rem 0.625rem', borderRadius: '6px',
        border: '2.5px solid var(--color-border, #e2e8f0)',
        background: 'var(--color-surface, #fff)',
        color: 'var(--color-text, #0f172a)',
        fontSize: 'var(--text-xs, 0.75rem)',
        ...style,
    };

    return (
        <div ref={ref} style={{ position: 'relative' }}>
            {/* Display field */}
            {!open ? (
                <div
                    onClick={handleInputClick}
                    style={{
                        ...baseStyle,
                        cursor: 'pointer',
                        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                        minHeight: '2.125rem',
                        color: selectedOption ? 'var(--color-text, #0f172a)' : 'var(--color-text-muted, #94a3b8)',
                    }}
                >
                    <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1 }}>
                        {selectedOption ? selectedOption.label : placeholder}
                    </span>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 2, flexShrink: 0 }}>
                        {value && (
                            <button type="button" onClick={handleClear} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-muted)', padding: 0, display: 'flex' }}>
                                <X size={12} />
                            </button>
                        )}
                        <ChevronDown size={13} style={{ color: 'var(--color-text-muted)' }} />
                    </div>
                </div>
            ) : (
                <div style={{ position: 'relative' }}>
                    <Search size={13} style={{ position: 'absolute', left: 8, top: '50%', transform: 'translateY(-50%)', color: 'var(--color-text-muted)' }} />
                    <input
                        ref={inputRef}
                        type="text"
                        value={search}
                        onChange={e => setSearch(e.target.value)}
                        onBlur={() => setTimeout(() => setOpen(false), 200)}
                        placeholder={placeholder}
                        autoFocus
                        style={{
                            ...baseStyle,
                            paddingLeft: '1.75rem',
                            borderColor: 'var(--primary, #191e6a)',
                            outline: 'none',
                        }}
                    />
                </div>
            )}

            {/* Dropdown */}
            {open && (
                <div style={{
                    position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 50,
                    marginTop: 2,
                    background: 'var(--color-surface, #fff)',
                    border: '1.5px solid var(--color-border, #e2e8f0)',
                    borderRadius: '6px',
                    boxShadow: '0 4px 16px rgba(0,0,0,0.08)',
                    maxHeight: 240, overflowY: 'auto',
                }}>
                    {filtered.length === 0 ? (
                        <div style={{ padding: '0.75rem', textAlign: 'center', color: 'var(--color-text-muted)', fontSize: 'var(--text-xs)' }}>
                            No matches found
                        </div>
                    ) : (
                        filtered.map(opt => (
                            <button
                                key={opt.value}
                                type="button"
                                onMouseDown={e => { e.preventDefault(); handleSelect(opt.value); }}
                                style={{
                                    width: '100%', padding: '0.4rem 0.625rem', border: 'none',
                                    background: opt.value === value ? 'rgba(25,30,106,0.06)' : 'transparent',
                                    cursor: 'pointer', textAlign: 'left',
                                    borderBottom: '1px solid var(--color-border, #f1f5f9)',
                                    fontSize: 'var(--text-xs, 0.75rem)',
                                    color: 'var(--color-text, #0f172a)',
                                }}
                            >
                                <div style={{ fontWeight: opt.value === value ? 600 : 400 }}>{opt.label}</div>
                                {opt.sublabel && (
                                    <div style={{ fontSize: '0.65rem', color: 'var(--color-text-muted)', marginTop: 1 }}>{opt.sublabel}</div>
                                )}
                            </button>
                        ))
                    )}
                </div>
            )}

            {/* Hidden input for form validation */}
            {required && <input type="text" required value={value} onChange={() => {}} style={{ position: 'absolute', opacity: 0, height: 0, width: 0, pointerEvents: 'none' }} tabIndex={-1} />}
        </div>
    );
}
