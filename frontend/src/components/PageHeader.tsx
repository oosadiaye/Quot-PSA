import React from 'react';
import BackButton from './BackButton';
import { useIsMobile } from '../design';

interface PageHeaderProps {
    title: string;
    subtitle?: string;
    icon?: React.ReactNode;
    actions?: React.ReactNode;
    backButton?: boolean;
    onBack?: () => void;
}

/**
 * Responsive page header used across every authenticated page.
 *
 * Desktop: title + subtitle on left, actions inline on right.
 * Mobile:  title stacks above actions, actions wrap to full-width row.
 *          Title font scales down and padding tightens.
 */
const PageHeader: React.FC<PageHeaderProps> = ({
    title,
    subtitle,
    icon,
    actions,
    backButton = true,
    onBack,
}) => {
    const isMobile = useIsMobile();

    return (
        <header
            style={{
                background: 'linear-gradient(135deg, #242a88 0%, #1e2480 100%)',
                padding: isMobile ? '18px 20px' : '24px 32px',
                borderRadius: 14,
                marginBottom: isMobile ? '1.25rem' : '2rem',
                color: 'white',
                display: 'flex',
                flexDirection: isMobile ? 'column' : 'row',
                justifyContent: 'space-between',
                alignItems: isMobile ? 'stretch' : 'center',
                gap: isMobile ? 16 : 12,
            }}
        >
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4, minWidth: 0 }}>
                {backButton && (
                    <div onClick={onBack} style={{ marginBottom: 4 }}>
                        <BackButton light />
                    </div>
                )}
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
                    {icon}
                    <h1
                        style={{
                            fontSize: isMobile ? 18 : 22,
                            fontWeight: 700,
                            color: 'white',
                            margin: 0,
                            letterSpacing: '-0.01em',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                        }}
                    >
                        {title}
                    </h1>
                </div>
                {subtitle && (
                    <p
                        style={{
                            fontSize: isMobile ? 13 : 14,
                            color: 'rgba(255,255,255,0.7)',
                            margin: 0,
                            marginTop: 2,
                        }}
                    >
                        {subtitle}
                    </p>
                )}
            </div>
            {actions && (
                <div
                    style={{
                        display: 'flex',
                        gap: '0.75rem',
                        alignItems: 'center',
                        flexWrap: 'wrap',
                        justifyContent: isMobile ? 'flex-start' : 'flex-end',
                    }}
                >
                    {actions}
                </div>
            )}
        </header>
    );
};

export default PageHeader;
