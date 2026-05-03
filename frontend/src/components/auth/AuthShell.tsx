/**
 * AuthShell — single source of truth for every unauthenticated page.
 *
 * Purpose:
 * Before this component existed, Login / ForgotPassword / ResetPassword each
 * inlined ~200 lines of a 50/50 brand-panel + form-panel layout with
 * duplicated gradients, logos, feature lists, and responsive fallbacks. This
 * component encapsulates that chrome so every auth surface is visually
 * identical, responsive, and branding-aware from one file.
 *
 * Layout:
 *   - Desktop (lg+): 50/50 split — gradient brand panel on left, form on right
 *   - Tablet (md):   55/45 split — compact brand panel
 *   - Mobile:        single column — compact brand lockup above the form
 *
 * Design tokens: references CSS variables from design-tokens.css so re-theming
 * the primary palette automatically propagates through the auth flow.
 */
import React from 'react';
import { Building2, Shield } from 'lucide-react';
import { useBranding } from '../../context/BrandingContext';
import { useIsMobile, useIsTablet } from '../../design';

interface AuthShellProps {
    /** Right-panel headline, e.g. "Welcome back" */
    title: string;
    /** Small caption under the title */
    subtitle?: string;
    /** Left brand-panel sub-headline. Defaults to branding.tagline. */
    brandTagline?: string;
    /** Optional feature callout rendered inside the brand panel (icons list). */
    brandContent?: React.ReactNode;
    /** Form / content body */
    children: React.ReactNode;
    /** Rendered under the form (e.g. "Don't have an account?"). */
    footer?: React.ReactNode;
    /** Toggle the "256-bit SSL · SOC 2" trust badge at the bottom. */
    showTrustBadge?: boolean;
}

const AuthShell: React.FC<AuthShellProps> = ({
    title,
    subtitle,
    brandTagline,
    brandContent,
    children,
    footer,
    showTrustBadge = true,
}) => {
    const { branding } = useBranding();
    const isMobile = useIsMobile();
    const isTablet = useIsTablet();
    const singleColumn = isMobile;

    const brandPanelWidth = isTablet ? '45%' : '50%';
    const formPanelWidth = isTablet ? '55%' : '50%';

    return (
        <div
            style={{
                display: 'flex',
                flexDirection: singleColumn ? 'column' : 'row',
                minHeight: '100vh',
                background: 'var(--color-bg-primary, #f8f9fb)',
            }}
        >
            {!singleColumn && (
                <aside
                    aria-label="Branding"
                    style={{
                        width: brandPanelWidth,
                        minHeight: '100vh',
                        background:
                            'linear-gradient(135deg, #242a88 0%, #1e2480 50%, #2e35a0 100%)',
                        display: 'flex',
                        flexDirection: 'column',
                        justifyContent: 'center',
                        alignItems: 'center',
                        padding: isTablet ? '40px' : '60px',
                        position: 'relative',
                        overflow: 'hidden',
                    }}
                >
                    {/* Decorative glassy circles */}
                    <div
                        aria-hidden
                        style={{
                            position: 'absolute',
                            top: '-100px',
                            right: '-100px',
                            width: '500px',
                            height: '500px',
                            borderRadius: '50%',
                            background: 'rgba(255,255,255,0.04)',
                        }}
                    />
                    <div
                        aria-hidden
                        style={{
                            position: 'absolute',
                            bottom: '-150px',
                            left: '-150px',
                            width: '600px',
                            height: '600px',
                            borderRadius: '50%',
                            background: 'rgba(255,255,255,0.03)',
                        }}
                    />

                    <BrandLogo size={72} />
                    <div
                        style={{
                            fontSize: isTablet ? '34px' : '42px',
                            fontWeight: 800,
                            color: 'white',
                            letterSpacing: '-1px',
                            marginBottom: '12px',
                            marginTop: '28px',
                        }}
                    >
                        {branding.name}
                    </div>
                    <div
                        style={{
                            fontSize: '17px',
                            color: 'rgba(255,255,255,0.75)',
                            textAlign: 'center',
                            lineHeight: 1.6,
                            marginBottom: '48px',
                            whiteSpace: 'pre-line',
                            maxWidth: 420,
                        }}
                    >
                        {brandTagline || branding.tagline || 'Public Sector Accounting\nBuilt on IPSAS & IFMIS'}
                    </div>

                    {brandContent}
                </aside>
            )}

            <main
                style={{
                    width: singleColumn ? '100%' : formPanelWidth,
                    minHeight: singleColumn ? 'auto' : '100vh',
                    flex: singleColumn ? '1 1 auto' : undefined,
                    display: 'flex',
                    flexDirection: 'column',
                    justifyContent: 'center',
                    alignItems: 'center',
                    padding: singleColumn ? '28px 20px' : isTablet ? '40px' : '60px',
                    background: 'white',
                }}
            >
                <div style={{ width: '100%', maxWidth: 440 }}>
                    {singleColumn && (
                        <div style={{ textAlign: 'center', marginBottom: '28px' }}>
                            <BrandLogo size={56} rounded={14} gradient />
                            <div
                                style={{
                                    fontFamily: "'Manrope', sans-serif",
                                    fontSize: '20px',
                                    fontWeight: 800,
                                    color: '#0f172a',
                                    marginTop: 10,
                                }}
                            >
                                {branding.name || 'Quot PSA'}
                            </div>
                            <div
                                style={{
                                    fontSize: '10px',
                                    color: '#008751',
                                    fontWeight: 700,
                                    letterSpacing: '0.8px',
                                    textTransform: 'uppercase',
                                    marginTop: 4,
                                }}
                            >
                                Nigeria Public-Sector IFMIS
                            </div>
                        </div>
                    )}

                    <div style={{ marginBottom: singleColumn ? 22 : 36 }}>
                        <h1
                            style={{
                                fontSize: singleColumn ? '24px' : '28px',
                                fontWeight: 700,
                                color: '#0f172a',
                                marginBottom: 8,
                                lineHeight: 1.2,
                            }}
                        >
                            {title}
                        </h1>
                        {subtitle && (
                            <p
                                style={{
                                    fontSize: singleColumn ? 14 : 15,
                                    color: '#64748b',
                                    margin: 0,
                                    lineHeight: 1.5,
                                }}
                            >
                                {subtitle}
                            </p>
                        )}
                    </div>

                    {children}

                    {footer && (
                        <div
                            style={{
                                textAlign: 'center',
                                marginTop: 28,
                                fontSize: 14,
                                color: '#64748b',
                            }}
                        >
                            {footer}
                        </div>
                    )}

                    {showTrustBadge && (
                        <div
                            style={{
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                gap: 6,
                                marginTop: 24,
                                fontSize: 12,
                                color: '#94a3b8',
                            }}
                        >
                            <Shield size={14} />
                            256-bit SSL encrypted · SOC 2 Compliant
                        </div>
                    )}
                </div>
            </main>
        </div>
    );
};

interface BrandLogoProps {
    size: number;
    rounded?: number;
    /** Use primary gradient background (for mobile lockup) rather than white card. */
    gradient?: boolean;
}

const BrandLogo: React.FC<BrandLogoProps> = ({ size, rounded = 18, gradient = false }) => {
    const { branding } = useBranding();
    return (
        <div
            style={{
                width: size,
                height: size,
                background: gradient
                    ? 'linear-gradient(135deg, #242a88, #2e35a0)'
                    : 'white',
                borderRadius: rounded,
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                boxShadow: gradient
                    ? '0 6px 20px rgba(36,42,136,0.25)'
                    : '0 8px 32px rgba(0,0,0,0.15)',
                color: 'white',
                overflow: 'hidden',
            }}
        >
            {branding.logo ? (
                <img
                    src={branding.logo}
                    alt={branding.name}
                    style={{ width: '100%', height: '100%', objectFit: 'contain' }}
                />
            ) : gradient ? (
                <Building2 size={Math.round(size * 0.5)} />
            ) : (
                <svg viewBox="0 0 40 40" fill="none" width={size * 0.55} height={size * 0.55}>
                    <rect x="4" y="8" width="14" height="14" rx="3" fill="#242a88" />
                    <rect x="22" y="8" width="14" height="14" rx="3" fill="#2e35a0" />
                    <rect x="4" y="26" width="14" height="6" rx="3" fill="#2e35a0" opacity="0.6" />
                    <rect x="22" y="26" width="14" height="6" rx="3" fill="#242a88" opacity="0.6" />
                </svg>
            )}
        </div>
    );
};

export default AuthShell;
