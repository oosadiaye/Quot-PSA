/**
 * Organization Switcher — Quot PSE
 *
 * Dropdown in the sidebar allowing users to switch between their assigned
 * organizations (MDAs). Fetches org list from /core/organizations/my/ and
 * switches via /core/organizations/switch/.
 *
 * In UNIFIED mode: shows tenant name (no switching needed).
 * In SEPARATED mode: shows active org with role badge + dropdown to switch.
 */
import { useState, useEffect, useRef } from 'react';
import { Building2, ChevronDown, Shield, Landmark, Eye, LayoutGrid } from 'lucide-react';
import { useAuth, type OrganizationInfo } from '../context/AuthContext';
import apiClient from '../api/client';

const ROLE_CONFIG: Record<string, { label: string; color: string; bg: string; Icon: typeof Shield }> = {
    MDA:              { label: 'MDA',      color: '#1e40af', bg: '#dbeafe', Icon: Building2 },
    BUDGET_AUTHORITY: { label: 'Budget',   color: '#166534', bg: '#dcfce7', Icon: Landmark },
    FINANCE_AUTHORITY:{ label: 'Finance',  color: '#6b21a8', bg: '#f3e8ff', Icon: LayoutGrid },
    AUDIT_AUTHORITY:  { label: 'Audit',    color: '#c2410c', bg: '#ffedd5', Icon: Eye },
};

export default function OrganizationSwitcher() {
    const {
        tenantInfo, activeOrganization, userOrganizations, mdaIsolationMode,
        setActiveOrganization, setOrganizationList,
    } = useAuth();
    const [open, setOpen] = useState(false);
    const [loading, setLoading] = useState(false);
    const ref = useRef<HTMLDivElement>(null);

    // Close dropdown on outside click
    useEffect(() => {
        const handler = (e: MouseEvent) => {
            if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
        };
        document.addEventListener('mousedown', handler);
        return () => document.removeEventListener('mousedown', handler);
    }, []);

    // Fetch organizations on mount
    useEffect(() => {
        const fetchOrgs = async () => {
            try {
                const res = await apiClient.get('/core/organizations/my/');
                const data = res.data;
                const orgs: OrganizationInfo[] = data.organizations || [];
                setOrganizationList(orgs, data.mda_isolation_mode || 'UNIFIED');

                // Auto-select default org if none active
                if (!activeOrganization && orgs.length > 0) {
                    const defaultOrg = orgs.find((o: OrganizationInfo) => o.is_default) || orgs[0];
                    await handleSwitch(defaultOrg);
                }
            } catch {
                // Org API not available yet or user has no assignments — safe to ignore
            }
        };
        fetchOrgs();
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const handleSwitch = async (org: OrganizationInfo) => {
        setLoading(true);
        try {
            await apiClient.post('/core/organizations/switch/', { organization_id: org.id });
            setActiveOrganization(org);
            setOpen(false);
            // Reload page data with new org context
            window.location.reload();
        } catch {
            // Silently handle — user will see no change
        } finally {
            setLoading(false);
        }
    };

    // UNIFIED mode or no orgs: show simple tenant name
    if (mdaIsolationMode === 'UNIFIED' && userOrganizations.length === 0) {
        return (
            <div style={{
                padding: '10px 16px', margin: '0 12px 8px', borderRadius: 8,
                background: 'rgba(255,255,255,0.08)', color: 'rgba(255,255,255,0.9)',
                display: 'flex', alignItems: 'center', gap: 8, fontSize: 13,
            }}>
                <Building2 size={16} />
                <span style={{ fontWeight: 500 }}>{tenantInfo?.name || 'No Organization'}</span>
            </div>
        );
    }

    const roleConfig = activeOrganization
        ? (ROLE_CONFIG[activeOrganization.org_role] || ROLE_CONFIG.MDA)
        : ROLE_CONFIG.MDA;

    return (
        <div ref={ref} style={{ margin: '0 12px 8px', position: 'relative' }}>
            {/* Active org button */}
            <button
                onClick={() => setOpen(!open)}
                style={{
                    width: '100%', padding: '10px 12px', borderRadius: 8,
                    background: 'rgba(255,255,255,0.1)', border: '1px solid rgba(255,255,255,0.15)',
                    color: '#fff', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8,
                    textAlign: 'left',
                }}
            >
                <roleConfig.Icon size={16} style={{ flexShrink: 0 }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        {activeOrganization?.short_name || activeOrganization?.name || 'Select Organization'}
                    </div>
                    <div style={{ fontSize: 10, opacity: 0.7 }}>
                        <span style={{
                            display: 'inline-block', padding: '1px 6px', borderRadius: 4,
                            background: roleConfig.bg, color: roleConfig.color, fontWeight: 600,
                        }}>
                            {roleConfig.label}
                        </span>
                    </div>
                </div>
                <ChevronDown size={14} style={{ opacity: 0.6, flexShrink: 0, transform: open ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }} />
            </button>

            {/* Dropdown */}
            {open && (
                <div style={{
                    position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 50,
                    marginTop: 4, background: '#1e293b', border: '1px solid #334155',
                    borderRadius: 8, boxShadow: '0 8px 24px rgba(0,0,0,0.3)',
                    maxHeight: 320, overflowY: 'auto',
                }}>
                    {userOrganizations.map((org) => {
                        const rc = ROLE_CONFIG[org.org_role] || ROLE_CONFIG.MDA;
                        const isActive = activeOrganization?.id === org.id;
                        return (
                            <button
                                key={org.id}
                                onClick={() => !isActive && handleSwitch(org)}
                                disabled={loading}
                                style={{
                                    width: '100%', padding: '10px 12px', border: 'none',
                                    background: isActive ? 'rgba(255,255,255,0.12)' : 'transparent',
                                    color: '#fff', cursor: isActive ? 'default' : 'pointer',
                                    display: 'flex', alignItems: 'center', gap: 8, textAlign: 'left',
                                    borderBottom: '1px solid rgba(255,255,255,0.05)',
                                }}
                            >
                                <rc.Icon size={14} style={{ flexShrink: 0, opacity: 0.7 }} />
                                <div style={{ flex: 1, minWidth: 0 }}>
                                    <div style={{ fontSize: 12, fontWeight: isActive ? 700 : 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                                        {org.name}
                                    </div>
                                    <span style={{
                                        display: 'inline-block', padding: '0 5px', borderRadius: 3,
                                        background: rc.bg, color: rc.color, fontSize: 9, fontWeight: 600,
                                    }}>
                                        {rc.label}
                                    </span>
                                </div>
                                {isActive && <span style={{ fontSize: 10, opacity: 0.5 }}>Active</span>}
                            </button>
                        );
                    })}
                </div>
            )}
        </div>
    );
}
