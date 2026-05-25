/**
 * BrandedPrintHeader
 * ==================
 * Shared letterhead block used by every printable / exportable
 * document in the application — IPSAS reports, warrant printouts,
 * payment vouchers, etc.
 *
 * Reads tenant branding from ``BrandingContext`` (a single React
 * Query that the whole app shares, so swapping logos in
 * ``/settings/branding`` updates every document live without a
 * page reload).
 *
 * Composition decisions:
 *   • Logo on the left, identity column centred.
 *   • Address + contacts printed under the organisation name in
 *     small italic to mimic a corporate letterhead.
 *   • A 3-double rule (``border-bottom: 3px double``) below the
 *     header is the standard public-sector "official document"
 *     visual cue — different from the single rule used inside
 *     report tables.
 *
 * Caller may override:
 *   • ``logoOverrideUrl`` — when a screen has a more specific logo
 *     (e.g. state coat of arms on warrant) the override wins; the
 *     branding logo only kicks in if the override is null/blank.
 *   • ``subtitle`` — a single line below the name (e.g. "Ministry
 *     of Finance" on a warrant).
 *   • ``ruleColor`` — the double-rule colour, defaulting to a
 *     dark forest green that matches the existing warrant printout.
 */
import React from 'react';
import { useBranding } from '../../context/BrandingContext';

export interface BrandedPrintHeaderProps {
    /** Falls back to the branding logo from BrandingContext when null. */
    logoOverrideUrl?: string | null;
    /** Single line under the org name (e.g. "Ministry of Finance"). */
    subtitle?: string;
    /** Hex / CSS colour for the bottom double rule. */
    ruleColor?: string;
    /** Use a smaller layout (single line) for tight pages. */
    compact?: boolean;
}

export default function BrandedPrintHeader({
    logoOverrideUrl,
    subtitle,
    ruleColor = '#064e3b',
    compact = false,
}: BrandedPrintHeaderProps) {
    const { branding } = useBranding();
    const logoUrl = logoOverrideUrl ?? branding.logo ?? null;

    // Compose a single-line address from the branding fields, dropping
    // empties so we don't render "Lagos, , Nigeria, ".
    const addressLine = [
        branding.address,
        branding.city,
        branding.state,
        branding.country,
        branding.postal_code,
    ].filter(Boolean).join(', ');

    // Compose a contact line — phone · email · website — same filter
    // pattern so missing fields just disappear.
    const contactLine = [
        branding.phone,
        branding.email,
        branding.website,
    ].filter(Boolean).join('  ·  ');

    if (compact) {
        return (
            <header style={{
                display: 'flex', alignItems: 'center', gap: 12,
                paddingBottom: 8,
                borderBottom: `2px solid ${ruleColor}`,
            }}>
                {logoUrl && (
                    <img
                        src={logoUrl}
                        alt={branding.name || 'Organisation logo'}
                        style={{ height: 36, width: 'auto' }}
                    />
                )}
                <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{
                        fontSize: 14, fontWeight: 700, color: '#0f172a',
                        letterSpacing: 0.4, textTransform: 'uppercase',
                    }}>
                        {branding.name}
                    </div>
                    {subtitle && (
                        <div style={{ fontSize: 11, color: '#475569' }}>
                            {subtitle}
                        </div>
                    )}
                </div>
            </header>
        );
    }

    return (
        <header style={{
            display: 'flex', alignItems: 'center', gap: 18,
            paddingBottom: 14,
            borderBottom: `3px double ${ruleColor}`,
        }}>
            {logoUrl ? (
                <img
                    src={logoUrl}
                    alt={branding.name || 'Organisation logo'}
                    style={{
                        height: 84, width: 'auto', maxWidth: 120,
                        objectFit: 'contain',
                    }}
                />
            ) : (
                // Placeholder ring when no logo is configured — better
                // than blank whitespace and cues the operator to upload
                // one in /settings/branding.
                <div style={{
                    height: 84, width: 84, borderRadius: '50%',
                    border: `2px solid ${ruleColor}`,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontSize: 10, color: ruleColor, textAlign: 'center',
                    lineHeight: 1.2, padding: 4,
                }}>
                    UPLOAD<br />LOGO IN<br />SETTINGS
                </div>
            )}
            <div style={{ flex: 1, textAlign: 'center', minWidth: 0 }}>
                <div style={{
                    fontSize: 22, fontWeight: 700,
                    letterSpacing: 2, textTransform: 'uppercase',
                    color: ruleColor,
                    lineHeight: 1.2,
                }}>
                    {branding.name}
                </div>
                {subtitle && (
                    <div style={{
                        fontSize: 16, fontWeight: 600,
                        marginTop: 4, color: '#0f172a',
                    }}>
                        {subtitle}
                    </div>
                )}
                {branding.tagline && (
                    <div style={{
                        fontSize: 11, color: '#475569',
                        marginTop: 2, fontStyle: 'italic',
                    }}>
                        {branding.tagline}
                    </div>
                )}
                {addressLine && (
                    <div style={{
                        fontSize: 11, color: '#475569', marginTop: 4,
                    }}>
                        {addressLine}
                    </div>
                )}
                {contactLine && (
                    <div style={{
                        fontSize: 10, color: '#64748b', marginTop: 2,
                        fontFamily: "'Helvetica Neue', sans-serif",
                    }}>
                        {contactLine}
                    </div>
                )}
            </div>
        </header>
    );
}
