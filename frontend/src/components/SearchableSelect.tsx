/**
 * SearchableSelect — Type-to-search dropdown for Quot PSE forms.
 *
 * Replaces standard <select> with a searchable combobox:
 * - Click to open full list
 * - Type to filter options
 * - Click an option to select
 * - Shows selected value in the input
 *
 * Architecture: the <input> is ALWAYS mounted — we never swap between a
 * "display div" and a "search input" because that conditional render
 * unmounts/remounts the input every time ``open`` flips, which drops
 * focus and freezes typing whenever any parent event briefly toggles
 * the dropdown. With a single always-mounted input the cursor stays
 * put through every parent re-render, debounced fetch, and prefill
 * effect that runs while the user is typing.
 */
import { useState, useRef, useEffect, useMemo, useLayoutEffect } from 'react';
import { createPortal } from 'react-dom';
import { Search, ChevronDown, X } from 'lucide-react';

interface Option {
    value: string;
    label: string;
    sublabel?: string;
    /**
     * Compact label shown in the closed/selected state. Defaults to
     * ``label``. Use this when ``label`` carries the full descriptive
     * text (good for the dropdown panel) but the selected display
     * needs to be terse to fit a tight column (e.g. line-item table
     * cells where horizontal space is precious).
     */
    selectedLabel?: string;
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
    const menuRef = useRef<HTMLDivElement>(null);
    // Anchor rect drives the portal-rendered menu's position. Tracked
    // in viewport coordinates because the menu is mounted on
    // ``document.body`` to escape any ``overflow: auto`` clipping
    // ancestor (a table wrapper, a dialog, a card with ``overflow:
    // hidden``). Recomputed on open + on scroll/resize so the menu
    // follows the trigger if the user scrolls while it's open.
    const [rect, setRect] = useState<DOMRect | null>(null);

    // Find selected option label
    const selectedOption = options.find(o => o.value === value);

    // Recompute the anchor rect whenever the menu is open. ``layout``
    // effect timing avoids a one-frame flash at the wrong position
    // before the browser paints the first frame.
    useLayoutEffect(() => {
        if (!open || !ref.current) return;
        const update = () => {
            if (ref.current) setRect(ref.current.getBoundingClientRect());
        };
        update();
        window.addEventListener('scroll', update, true); // capture: catch scrolls in any ancestor
        window.addEventListener('resize', update);
        return () => {
            window.removeEventListener('scroll', update, true);
            window.removeEventListener('resize', update);
        };
    }, [open]);

    // Close on outside click — also has to consider clicks inside the
    // portal-rendered menu, which is NOT a DOM descendant of ``ref``.
    // Plus an ESC-key listener so keyboard users can dismiss the
    // dropdown without leaving the input.
    useEffect(() => {
        const mouseHandler = (e: MouseEvent) => {
            const target = e.target as Node;
            const insideTrigger = ref.current?.contains(target);
            const insideMenu = menuRef.current?.contains(target);
            if (!insideTrigger && !insideMenu) setOpen(false);
        };
        const keyHandler = (e: KeyboardEvent) => {
            if (e.key === 'Escape') setOpen(false);
        };
        document.addEventListener('mousedown', mouseHandler);
        document.addEventListener('keydown', keyHandler);
        return () => {
            document.removeEventListener('mousedown', mouseHandler);
            document.removeEventListener('keydown', keyHandler);
        };
    }, []);

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
        // Move focus back to the trigger so keyboard flow is preserved
        // (Tab from here goes to the next form field, not back through
        // the now-closed dropdown).
        inputRef.current?.blur();
    };

    const handleClear = (e: React.MouseEvent) => {
        e.stopPropagation();
        onChange('');
        setSearch('');
        // Reopen so the user can immediately pick a different value
        // without a second click; refocus the input for typing.
        setOpen(true);
        setTimeout(() => inputRef.current?.focus(), 0);
    };

    // Open + select-all on focus so the user can replace the text by
    // typing immediately, mirroring the standard combobox UX.
    const handleFocus = () => {
        setOpen(true);
        // Select existing search text so the next keystroke replaces it
        inputRef.current?.select();
    };

    // The input's displayed value depends on focus state:
    //   • While the user is searching (open + has typed): show ``search``
    //   • When closed: show the compact selected label, or empty string
    //   • When open + empty search: show empty so the placeholder shows
    const displayValue = open
        ? search
        : (selectedOption ? (selectedOption.selectedLabel ?? selectedOption.label) : '');

    const baseStyle: React.CSSProperties = {
        width: '100%', padding: '0.5rem 0.625rem', borderRadius: '6px',
        border: open
            ? '2.5px solid var(--primary, #191e6a)'
            : '2.5px solid var(--color-border, #e2e8f0)',
        background: 'var(--color-surface, #fff)',
        color: selectedOption || open
            ? 'var(--color-text, #0f172a)'
            : 'var(--color-text-muted, #94a3b8)',
        fontSize: 'var(--text-xs, 0.75rem)',
        outline: 'none',
        paddingLeft: open ? '1.75rem' : '0.625rem',
        paddingRight: '2.5rem',
        ...style,
    };

    return (
        <div ref={ref} style={{ position: 'relative' }}>
            {open && (
                <Search
                    size={13}
                    style={{
                        position: 'absolute', left: 8, top: '50%',
                        transform: 'translateY(-50%)',
                        color: 'var(--color-text-muted)',
                        pointerEvents: 'none',
                    }}
                />
            )}
            <input
                ref={inputRef}
                type="text"
                value={displayValue}
                onChange={e => {
                    if (!open) setOpen(true);
                    setSearch(e.target.value);
                }}
                onFocus={handleFocus}
                onClick={() => setOpen(true)}
                onKeyDown={e => {
                    if (e.key === 'Enter' && filtered.length === 1) {
                        e.preventDefault();
                        handleSelect(filtered[0].value);
                    } else if (e.key === 'Tab' || e.key === 'Escape') {
                        setOpen(false);
                    } else if (!open) {
                        setOpen(true);
                    }
                }}
                placeholder={selectedOption ? '' : placeholder}
                title={selectedOption ? selectedOption.label : ''}
                autoComplete="off"
                style={baseStyle}
            />
            {/* Right-side cluster — clear (when value picked) + chevron. */}
            <div style={{
                position: 'absolute', right: 8, top: '50%',
                transform: 'translateY(-50%)',
                display: 'flex', alignItems: 'center', gap: 2,
                pointerEvents: 'none',
            }}>
                {value && (
                    <button
                        type="button"
                        onMouseDown={handleClear}
                        title="Clear selection"
                        style={{
                            background: 'none', border: 'none', cursor: 'pointer',
                            color: 'var(--color-text-muted)', padding: 0,
                            display: 'flex', pointerEvents: 'auto',
                        }}
                    >
                        <X size={12} />
                    </button>
                )}
                <ChevronDown size={13} style={{ color: 'var(--color-text-muted)' }} />
            </div>

            {/* Dropdown — rendered via portal to ``document.body`` so it
                escapes any ancestor with ``overflow: auto/hidden`` (e.g.
                horizontally-scrolling tables, glass-card containers).
                Position is computed from the trigger's viewport rect
                each frame the menu is open. */}
            {open && rect && createPortal(
                <div
                    ref={menuRef}
                    style={{
                        position: 'fixed',
                        top: rect.bottom + 2,
                        left: rect.left,
                        width: rect.width,
                        zIndex: 9999,
                        background: 'var(--color-surface, #fff)',
                        border: '1.5px solid var(--color-border, #e2e8f0)',
                        borderRadius: '6px',
                        boxShadow: '0 4px 16px rgba(0,0,0,0.18)',
                        maxHeight: 240, overflowY: 'auto',
                    }}
                >
                    {filtered.length === 0 ? (
                        <div style={{ padding: '0.75rem', textAlign: 'center', color: 'var(--color-text-muted, #94a3b8)', fontSize: 'var(--text-xs, 0.75rem)' }}>
                            No matches found
                        </div>
                    ) : (
                        filtered.map(opt => (
                            <button
                                key={opt.value}
                                type="button"
                                // ``onMouseDown`` with ``preventDefault`` keeps
                                // focus in the input — without this, clicking
                                // the option blurs the input first, the close
                                // logic fires, and the click can register on a
                                // moved DOM node.
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
                                    <div style={{ fontSize: '0.65rem', color: 'var(--color-text-muted, #94a3b8)', marginTop: 1 }}>{opt.sublabel}</div>
                                )}
                            </button>
                        ))
                    )}
                </div>,
                document.body,
            )}

            {/* Hidden input for form validation */}
            {required && <input type="text" required value={value} onChange={() => {}} style={{ position: 'absolute', opacity: 0, height: 0, width: 0, pointerEvents: 'none' }} tabIndex={-1} />}
        </div>
    );
}
