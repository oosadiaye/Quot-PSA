/**
 * SectionCard — white card matching the Quot PSE glassmorphism theme.
 * Rounded, subtle indigo-tinted border, soft shadow, token-driven padding.
 *
 * Use for: wrapping tables, form sections, stat groups, etc.
 *
 * Optional `title` + `actions` slot provide a consistent card header bar.
 */
import type { ReactNode } from 'react';
import { useBreakpoint, spaceFor } from '../../design';

interface SectionCardProps {
    children: ReactNode;
    title?: ReactNode;
    subtitle?: ReactNode;
    actions?: ReactNode;
    /** Remove internal padding — useful when wrapping a full-bleed table. */
    flush?: boolean;
    /** Bottom margin between stacked cards. */
    marginBottom?: number;
    style?: React.CSSProperties;
}

const SectionCard = ({
    children,
    title,
    subtitle,
    actions,
    flush = false,
    marginBottom = 16,
    style,
}: SectionCardProps) => {
    const bp = useBreakpoint();
    const space = spaceFor(bp);

    return (
        <section
            style={{
                background: 'var(--color-surface)',
                border: '1px solid var(--color-border)',
                borderRadius: 14,
                boxShadow: '0 1px 3px rgba(15,23,42,0.04)',
                overflow: 'hidden',
                marginBottom,
                ...style,
            }}
        >
            {(title || actions) && (
                <header
                    style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        gap: 12,
                        padding: `${space.card - 4}px ${space.card}px`,
                        borderBottom: '1px solid var(--color-border)',
                        background: 'var(--color-surface-hover)',
                    }}
                >
                    <div style={{ minWidth: 0 }}>
                        {title && (
                            <div
                                style={{
                                    fontSize: 14,
                                    fontWeight: 700,
                                    color: 'var(--color-text)',
                                    letterSpacing: '-0.005em',
                                }}
                            >
                                {title}
                            </div>
                        )}
                        {subtitle && (
                            <div style={{ fontSize: 12.5, color: 'var(--color-text-muted)', marginTop: 2 }}>
                                {subtitle}
                            </div>
                        )}
                    </div>
                    {actions && <div style={{ display: 'flex', gap: 8 }}>{actions}</div>}
                </header>
            )}
            <div style={{ padding: flush ? 0 : space.card }}>{children}</div>
        </section>
    );
};

export default SectionCard;
