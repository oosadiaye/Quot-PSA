/**
 * Shared error panel for IPSAS report pages.
 *
 * Decodes the Axios error and tells the user *why* the report is blank,
 * with an actionable next step (log in, pick a tenant, check seed data).
 */
import { AlertTriangle, LogIn, Database, ServerCrash } from 'lucide-react';

interface AxiosLike {
    response?: {
        status?: number;
        data?: { detail?: string; error?: string };
    };
    message?: string;
}

interface ReportErrorProps {
    error: unknown;
    endpoint: string;
}

export default function ReportError({ error, endpoint }: ReportErrorProps) {
    const err = error as AxiosLike;
    const status = err?.response?.status;
    const serverMsg = err?.response?.data?.detail || err?.response?.data?.error;
    const fallback = err?.message || 'Unknown error';

    let icon: typeof AlertTriangle = AlertTriangle;
    let title = 'Could not load report';
    let hint = 'An unexpected error occurred. Check the browser console.';
    let color = '#dc2626';

    if (status === 401 || status === 403) {
        icon = LogIn;
        title = 'Sign-in required';
        hint = 'Your session has expired or you are not signed in. Log in again to view this report.';
        color = '#d97706';
    } else if (status === 404) {
        icon = Database;
        const tenantDomain = typeof window === 'undefined'
            ? null
            : (localStorage.getItem('tenantDomain') || sessionStorage.getItem('tenantDomain'));

        if (!tenantDomain || tenantDomain === 'null' || tenantDomain === 'undefined') {
            title = 'No tenant selected';
            hint = (
                'You are signed in to the platform (public) schema, which has no '
                + 'accounting data. Please log out and sign in to a specific tenant '
                + '(e.g. Delta State Government) to view this report.'
            );
        } else {
            title = 'Report not found for tenant';
            hint = (
                `The API endpoint is not available for tenant "${tenantDomain}". `
                + 'This usually means the tenant has not been migrated yet, or the '
                + 'accounting app is not installed in this schema.'
            );
        }
        color = '#1e40af';
    } else if (status && status >= 500) {
        icon = ServerCrash;
        title = 'Server error';
        hint = serverMsg || 'The backend returned an error while building the report.';
        color = '#dc2626';
    }

    const Icon = icon;

    return (
        <div style={{
            background: '#fff',
            border: `2px solid ${color}33`,
            borderRadius: 12,
            padding: '32px 28px',
            maxWidth: 640,
            margin: '24px auto',
            display: 'flex',
            gap: 16,
            alignItems: 'flex-start',
        }}>
            <Icon size={40} style={{ color, flexShrink: 0, marginTop: 2 }} />
            <div style={{ flex: 1 }}>
                <div style={{
                    fontSize: 18, fontWeight: 800, color: '#1e293b',
                    marginBottom: 4,
                }}>
                    {title}
                </div>
                <div style={{ fontSize: 14, color: '#475569', lineHeight: 1.6 }}>
                    {hint}
                </div>
                <div style={{
                    marginTop: 14,
                    padding: '10px 12px',
                    background: '#f8fafc',
                    borderRadius: 6,
                    fontSize: 12,
                    fontFamily: 'monospace',
                    color: '#64748b',
                    border: '1px solid #e8ecf1',
                }}>
                    <div><strong>Endpoint:</strong> <code>{endpoint}</code></div>
                    {status !== undefined && (
                        <div><strong>HTTP status:</strong> {status}</div>
                    )}
                    {serverMsg && (
                        <div><strong>Message:</strong> {serverMsg}</div>
                    )}
                    {!status && !serverMsg && (
                        <div><strong>Details:</strong> {fallback}</div>
                    )}
                </div>
            </div>
        </div>
    );
}
