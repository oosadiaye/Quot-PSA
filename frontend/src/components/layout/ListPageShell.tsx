/**
 * ListPageShell — responsive page wrapper for every authenticated list /
 * index / dashboard page. Handles sidebar offset, safe-area padding on
 * mobile (to clear the top bar / hamburger), background colour, and
 * consistent page padding driven by design-token `spaceFor(bp)`.
 *
 * Replaces the repetitive:
 *   <div style={{ background: '#f1f5f9', minHeight: '100vh' }}>
 *     <Sidebar />
 *     <div style={{ marginLeft: '260px', padding: '32px' }}>...</div>
 *   </div>
 *
 * Usage:
 *   <ListPageShell>
 *     <PageHeader title="Contracts" ... />
 *     <FilterBar>...</FilterBar>
 *     <SectionCard>...</SectionCard>
 *   </ListPageShell>
 */
import type { ReactNode } from 'react';
import Sidebar from '../Sidebar';
import { useBreakpoint, spaceFor, useIsMobile } from '../../design';

interface ListPageShellProps {
    children: ReactNode;
    /** Optional max content width (desktop). Default: unbounded. */
    maxWidth?: number;
    /** Optional page title rendered above children. */
    title?: ReactNode;
    /** Optional page subtitle rendered below the title. */
    subtitle?: ReactNode;
}

const ListPageShell = ({ children, maxWidth, title, subtitle }: ListPageShellProps) => {
    const bp = useBreakpoint();
    const space = spaceFor(bp);
    const isMobile = useIsMobile();

    return (
        <div
            style={{
                background: '#f1f5f9',
                minHeight: '100vh',
                color: '#0b1320',
            }}
        >
            <Sidebar />
            <main
                style={{
                    marginLeft: isMobile ? 0 : 260,
                    paddingTop: isMobile ? 56 + space.page : space.page,
                    paddingLeft: space.page,
                    paddingRight: space.page,
                    paddingBottom: space.page + 24,
                    minHeight: '100vh',
                }}
            >
                <div
                    style={{
                        maxWidth: maxWidth ?? '100%',
                        margin: maxWidth ? '0 auto' : undefined,
                    }}
                >
                    {(title || subtitle) && (
                        <div style={{ marginBottom: 24 }}>
                            {title && (
                                <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700, color: '#0b1320' }}>
                                    {title}
                                </h1>
                            )}
                            {subtitle && (
                                <p style={{ margin: '4px 0 0', fontSize: 13, color: '#64748b' }}>
                                    {subtitle}
                                </p>
                            )}
                        </div>
                    )}
                    {children}
                </div>
            </main>
        </div>
    );
};

export default ListPageShell;
