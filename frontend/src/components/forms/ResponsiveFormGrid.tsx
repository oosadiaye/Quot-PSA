/**
 * ResponsiveFormGrid — replace every `display: grid; gridTemplateColumns: '1fr 1fr 1fr'`
 * inline-styled form row in the ERP.
 *
 * Collapses progressively: desktop → tablet → mobile (single column).
 * This avoids the `!important` mobile overrides scattered through
 * `responsive.css`.
 */
import React from 'react';
import { useBreakpoint } from '../../design';

interface ResponsiveFormGridProps {
    /** Desktop columns. Defaults to 2. */
    columns?: number;
    /** Tablet (md) columns. Defaults to Math.min(desktop, 2). */
    tabletColumns?: number;
    /** Mobile columns. Defaults to 1. */
    mobileColumns?: number;
    /** Grid gap. Defaults to 16px. */
    gap?: number | string;
    children: React.ReactNode;
    style?: React.CSSProperties;
}

export const ResponsiveFormGrid: React.FC<ResponsiveFormGridProps> = ({
    columns = 2,
    tabletColumns,
    mobileColumns = 1,
    gap = 16,
    children,
    style,
}) => {
    const bp = useBreakpoint();
    const isMobile = bp === 'xs' || bp === 'sm';
    const isTablet = bp === 'md';

    const resolvedCols = isMobile
        ? mobileColumns
        : isTablet
            ? (tabletColumns ?? Math.min(columns, 2))
            : columns;

    return (
        <div
            style={{
                display: 'grid',
                gridTemplateColumns: `repeat(${resolvedCols}, minmax(0, 1fr))`,
                gap,
                ...style,
            }}
        >
            {children}
        </div>
    );
};

export default ResponsiveFormGrid;
