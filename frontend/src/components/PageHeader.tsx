import React from 'react';
import BackButton from './BackButton';

interface PageHeaderProps {
    title: string;
    subtitle?: string;
    icon?: React.ReactNode;
    actions?: React.ReactNode;
    backButton?: boolean;
    onBack?: () => void;
}

const PageHeader: React.FC<PageHeaderProps> = ({
    title,
    subtitle,
    icon,
    actions,
    backButton = true,
    onBack,
}) => {
    return (
        <header style={{
            background: 'linear-gradient(135deg, #242a88 0%, #1e2480 100%)',
            padding: '24px 32px',
            borderRadius: '14px',
            marginBottom: '2rem',
            color: 'white',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
        }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                {backButton && (
                    <div onClick={onBack} style={{ marginBottom: '4px' }}>
                        <BackButton light />
                    </div>
                )}
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    {icon}
                    <h1 style={{
                        fontSize: '22px', fontWeight: 700,
                        color: 'white', margin: 0,
                        letterSpacing: '-0.01em',
                    }}>
                        {title}
                    </h1>
                </div>
                {subtitle && (
                    <p style={{
                        fontSize: '14px',
                        color: 'rgba(255,255,255,0.7)',
                        margin: 0,
                        marginTop: '2px',
                    }}>
                        {subtitle}
                    </p>
                )}
            </div>
            {actions && (
                <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
                    {actions}
                </div>
            )}
        </header>
    );
};

export default PageHeader;
