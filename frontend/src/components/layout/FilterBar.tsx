/**
 * FilterBar — horizontal row of search + filter controls + trailing
 * action buttons that wraps cleanly on mobile.
 *
 * Desktop: filters on the left (flex-grow), actions on the right.
 * Mobile:  stacks to a column; action buttons span full width.
 *
 * Sits inside a `SectionCard` or just above one.
 */
import { ReactNode } from 'react';
import { useIsMobile } from '../../design';

interface FilterBarProps {
    children: ReactNode;
    actions?: ReactNode;
    /** If true, renders with a subtle card chrome (bg + border). */
    embedded?: boolean;
    /** Bottom spacing. Default: 16. */
    marginBottom?: number;
}

const FilterBar = ({ children, actions, embedded = false, marginBottom = 16 }: FilterBarProps) => {
    const isMobile = useIsMobile();

    const chrome: React.CSSProperties = embedded
        ? {
              background: '#ffffff',
              border: '1px solid rgba(26,35,126,0.08)',
              borderRadius: 12,
              padding: isMobile ? 12 : 16,
              boxShadow: '0 1px 2px rgba(15,23,42,0.03)',
          }
        : {};

    return (
        <div
            style={{
                display: 'flex',
                flexDirection: isMobile ? 'column' : 'row',
                alignItems: isMobile ? 'stretch' : 'center',
                justifyContent: 'space-between',
                gap: 12,
                marginBottom,
                flexWrap: 'wrap',
                ...chrome,
            }}
        >
            <div
                style={{
                    display: 'flex',
                    flexDirection: isMobile ? 'column' : 'row',
                    alignItems: isMobile ? 'stretch' : 'center',
                    gap: 10,
                    flexWrap: 'wrap',
                    flex: 1,
                    minWidth: 0,
                }}
            >
                {children}
            </div>
            {actions && (
                <div
                    style={{
                        display: 'flex',
                        flexDirection: isMobile ? 'column' : 'row',
                        alignItems: isMobile ? 'stretch' : 'center',
                        gap: 8,
                        flexShrink: 0,
                    }}
                >
                    {actions}
                </div>
            )}
        </div>
    );
};

export default FilterBar;
