import type { ReactNode } from 'react';

interface PortalPageHeaderProps {
  title: string;
  subtitle?: string;
  icon?: ReactNode;
  actions?: ReactNode;
}

export default function PortalPageHeader({ title, subtitle, icon, actions }: PortalPageHeaderProps) {
  return (
    <div
      style={{
        background: 'linear-gradient(135deg, #242a88 0%, #2e35a0 100%)',
        color: '#ffffff',
        padding: '22px 26px',
        borderRadius: 14,
        boxShadow: '0 8px 26px rgba(36, 42, 136, 0.22)',
        marginBottom: 24,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 16,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
        {icon && (
          <div
            style={{
              width: 44,
              height: 44,
              borderRadius: 11,
              background: 'rgba(255,255,255,0.16)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            {icon}
          </div>
        )}
        <div>
          <div style={{ fontSize: 20, fontWeight: 700, letterSpacing: '-0.2px' }}>{title}</div>
          {subtitle && (
            <div style={{ fontSize: 13, opacity: 0.82, marginTop: 2 }}>{subtitle}</div>
          )}
        </div>
      </div>
      {actions && <div>{actions}</div>}
    </div>
  );
}
