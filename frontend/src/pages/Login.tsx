import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Building2, Eye, EyeOff, ChevronRight, Shield, Monitor, BarChart3, Globe } from 'lucide-react';
import apiClient from '../api/client';
import { useAuth } from '../context/AuthContext';
import AuthShell from '../components/auth/AuthShell';
import { FormField } from '../components/forms';

interface TenantInfo {
    id: number;
    name: string;
    schema_name: string;
    domain: string | null;
    role: string;
}

const FeatureList: React.FC = () => (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20, maxWidth: 380 }}>
        {(
            [
                { icon: Shield, text: 'Enterprise-grade security with role-based access control' },
                { icon: Monitor, text: 'Multi-tenant architecture for scalable deployments' },
                { icon: BarChart3, text: 'Real-time analytics and financial reporting' },
                { icon: Globe, text: '12+ integrated modules — Accounting to Quality' },
            ] as const
        ).map((f, i) => (
            <div
                key={i}
                style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 16,
                    color: 'rgba(255,255,255,0.85)',
                    fontSize: 15,
                }}
            >
                <div
                    style={{
                        width: 44,
                        height: 44,
                        background: 'rgba(255,255,255,0.12)',
                        borderRadius: 12,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        flexShrink: 0,
                    }}
                >
                    <f.icon size={22} style={{ color: 'rgba(255,255,255,0.9)' }} />
                </div>
                <span>{f.text}</span>
            </div>
        ))}
    </div>
);

const roleLabel = (role: string): string => {
    const labels: Record<string, string> = {
        admin: 'Admin',
        manager: 'Manager',
        user: 'User',
        viewer: 'Viewer',
    };
    return labels[role] || role;
};

const Login: React.FC = () => {
    const [identifier, setIdentifier] = useState<string>(
        () => localStorage.getItem('rememberedUser') || '',
    );
    const [password, setPassword] = useState('');
    const [rememberMe, setRememberMe] = useState<boolean>(
        () => !!localStorage.getItem('rememberedUser'),
    );
    // Pick up a one-shot "session expired" reason written by the axios 401
    // interceptor (see src/api/client.ts). Read once, then clear so the
    // message doesn't re-appear on subsequent logins.
    const [error, setError] = useState<string>(() => {
        try {
            const reason = sessionStorage.getItem('auth-expired-reason');
            if (reason) {
                sessionStorage.removeItem('auth-expired-reason');
                return reason;
            }
        } catch {
            /* storage disabled — non-fatal */
        }
        return '';
    });
    const [loading, setLoading] = useState(false);
    const [showPassword, setShowPassword] = useState(false);
    const navigate = useNavigate();

    const [step, setStep] = useState<'credentials' | 'tenant'>('credentials');
    const [tenants, setTenants] = useState<TenantInfo[]>([]);
    const [selectingTenant, setSelectingTenant] = useState(false);
    const { setAuthData, setTenantData, logout } = useAuth();

    const handleLogin = async (e: React.FormEvent) => {
        e.preventDefault();
        setError('');
        setLoading(true);
        try {
            const response = await apiClient.post('/core/auth/login/', {
                username: identifier,
                password,
            });
            const { token, user, tenants: userTenants } = response.data;
            setAuthData(user, token, rememberMe);

            if (user.is_superuser) {
                navigate('/superadmin');
                return;
            }

            if (!userTenants || userTenants.length === 0) {
                setError(
                    'Your account is not assigned to any organisation. ' +
                        'Please contact your administrator to be granted access.',
                );
                logout();
                return;
            } else if (userTenants.length === 1) {
                await selectTenantAndNavigate(userTenants[0]);
            } else {
                setTenants(userTenants);
                setStep('tenant');
            }
        } catch (err: unknown) {
            const msg =
                (err as { response?: { data?: { error?: string } }; message?: string })?.response
                    ?.data?.error ||
                (err as { message?: string })?.message ||
                'Login failed. Please check your credentials.';
            setError(msg);
        } finally {
            setLoading(false);
        }
    };

    const selectTenantAndNavigate = async (tenant: TenantInfo) => {
        setSelectingTenant(true);
        setError('');
        try {
            const response = await apiClient.post('/core/auth/select-tenant/', {
                tenant_id: tenant.id,
            });
            const { domain, tenant_name, role, permissions, redirect_url, setup_required } =
                response.data;
            setTenantData(
                { id: tenant.id, name: tenant_name, domain, role: role || tenant.role },
                permissions || [],
            );

            // Subdomain redirect: when the backend tells us the tenant
            // lives at a different hostname (``<slug>.erp.tryquot.com``),
            // navigate the browser there so subsequent requests come
            // from the tenant subdomain. Cookies, ``X-Tenant-Domain``
            // header, and visual context all flow from the URL after
            // that. We only redirect when the host actually differs —
            // otherwise an in-app SPA navigation is faster.
            //
            // Defensive guard against non-routable hosts (RFC 2606
            // reserved TLDs + .local + .example): if a stale primary
            // Domain row points at ``office_x.dtsg.test`` we'd DNS-fail
            // mid-login and strand the user. The backend now strips
            // such hosts from ``redirect_url``; this is the second
            // layer in case any caller / cached response leaks a
            // non-routable URL through.
            const NON_ROUTABLE_TLDS = ['.test', '.invalid', '.localhost', '.local', '.example'];
            const isNonRoutable = (host: string): boolean => {
                const h = host.toLowerCase();
                return NON_ROUTABLE_TLDS.some((suffix) => h.endsWith(suffix));
            };
            // If we're currently on localhost / 127.0.0.1, don't
            // cross-host redirect to a public host — the operator
            // is in a dev environment, the production subdomain
            // probably isn't pointed at their box, and they'd lose
            // their dev tooling. Header-based tenancy
            // (X-Tenant-Domain) keeps everything on localhost while
            // still scoping data to the right tenant.
            const currentHost = window.location.hostname.toLowerCase();
            const isDevHost = (
                currentHost === 'localhost'
                || currentHost === '127.0.0.1'
                || currentHost === '0.0.0.0'
                || currentHost.endsWith('.localhost')
            );

            const targetPath = setup_required ? '/setup' : '/dashboard';
            if (redirect_url) {
                try {
                    const target = new URL(redirect_url);
                    if (isNonRoutable(target.host)) {
                        // Skip the cross-host redirect; stay on the
                        // current origin and rely on the ``X-Tenant-
                        // Domain`` header in localStorage to scope
                        // requests to the tenant.
                    } else if (isDevHost) {
                        // Dev environment — never leave localhost
                        // for a public hostname. Same header-based
                        // fallback as the non-routable case.
                    } else if (target.host !== window.location.host) {
                        // Cross-host redirect: ``localStorage`` doesn't
                        // travel across origins, so we hand the auth
                        // token + tenant info to the destination via
                        // URL fragment. The fragment never reaches the
                        // server (browsers strip ``#...`` from HTTP
                        // requests) but the destination JS reads it on
                        // mount, copies into its own ``localStorage``,
                        // then strips the fragment from the URL bar
                        // via ``history.replaceState`` so the token
                        // doesn't sit in browser history.
                        const token =
                            localStorage.getItem('authToken') ??
                            sessionStorage.getItem('authToken');
                        const userJson =
                            localStorage.getItem('user') ??
                            sessionStorage.getItem('user');
                        target.pathname = targetPath;
                        const params = new URLSearchParams();
                        if (token) params.set('t', token);
                        if (userJson) params.set('u', btoa(unescape(encodeURIComponent(userJson))));
                        params.set('d', domain);
                        params.set('tn', tenant_name || '');
                        if (role) params.set('r', String(role));
                        if (permissions) params.set('p', btoa(JSON.stringify(permissions)));
                        target.hash = params.toString();
                        window.location.replace(target.toString());
                        return; // Don't fall through to navigate() below.
                    }
                } catch {
                    // Malformed redirect_url — fall through to in-app
                    // navigation. The header-based path still works.
                }
            }
            navigate(targetPath);
        } catch (err: unknown) {
            const msg =
                (err as { response?: { data?: { error?: string } } })?.response?.data?.error ||
                'Failed to select tenant.';
            setError(msg);
        } finally {
            setSelectingTenant(false);
        }
    };

    // ── Tenant selection step ──────────────────────────────────────
    if (step === 'tenant') {
        return (
            <AuthShell
                title="Select Organization"
                subtitle="Choose which organization to work with"
                brandContent={<FeatureList />}
                footer={
                    <button
                        onClick={() => {
                            logout();
                            setStep('credentials');
                            setTenants([]);
                        }}
                        style={{
                            background: 'none',
                            border: 'none',
                            color: '#64748b',
                            cursor: 'pointer',
                            fontSize: 14,
                            fontFamily: 'inherit',
                        }}
                    >
                        Sign in as a different user
                    </button>
                }
            >
                {error && (
                    <div
                        role="alert"
                        style={{
                            padding: '12px 16px',
                            background: '#fef2f2',
                            color: '#dc2626',
                            borderRadius: 10,
                            marginBottom: 16,
                            fontSize: 14,
                            border: '1px solid #fecaca',
                        }}
                    >
                        {error}
                    </div>
                )}

                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {tenants.map((tenant) => (
                        <button
                            key={tenant.id}
                            onClick={() => selectTenantAndNavigate(tenant)}
                            disabled={selectingTenant}
                            style={{
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'space-between',
                                padding: 16,
                                border: '1.5px solid #e2e8f0',
                                borderRadius: 12,
                                background: 'white',
                                cursor: selectingTenant ? 'wait' : 'pointer',
                                width: '100%',
                                textAlign: 'left',
                                transition: 'all 0.2s',
                                fontFamily: 'inherit',
                            }}
                            onMouseEnter={(e) => {
                                e.currentTarget.style.borderColor = '#2e35a0';
                                e.currentTarget.style.background = '#f0f7ff';
                            }}
                            onMouseLeave={(e) => {
                                e.currentTarget.style.borderColor = '#e2e8f0';
                                e.currentTarget.style.background = 'white';
                            }}
                        >
                            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                                <div
                                    style={{
                                        width: 40,
                                        height: 40,
                                        borderRadius: 10,
                                        background: 'linear-gradient(135deg, #242a88, #2e35a0)',
                                        color: 'white',
                                        display: 'flex',
                                        alignItems: 'center',
                                        justifyContent: 'center',
                                        flexShrink: 0,
                                    }}
                                >
                                    <Building2 size={20} />
                                </div>
                                <div>
                                    <div style={{ fontWeight: 600, fontSize: 15, color: '#0f172a' }}>
                                        {tenant.name}
                                    </div>
                                    <div style={{ fontSize: 13, color: '#64748b', marginTop: 2 }}>
                                        {roleLabel(tenant.role)}
                                    </div>
                                </div>
                            </div>
                            <ChevronRight size={18} style={{ color: '#94a3b8' }} />
                        </button>
                    ))}
                </div>
            </AuthShell>
        );
    }

    // ── Credentials step ───────────────────────────────────────────
    return (
        <AuthShell
            title="Welcome back"
            subtitle="Sign in to your account to continue"
            brandContent={<FeatureList />}
            footer={
                <>
                    Don't have an account?{' '}
                    <a
                        href="/register"
                        style={{ color: '#2e35a0', textDecoration: 'none', fontWeight: 600 }}
                    >
                        Create Account
                    </a>
                </>
            }
        >
            {error && (
                <div
                    role="alert"
                    style={{
                        padding: '12px 16px',
                        background: '#fef2f2',
                        color: '#dc2626',
                        borderRadius: 10,
                        marginBottom: 16,
                        fontSize: 14,
                        border: '1px solid #fecaca',
                    }}
                >
                    {error}
                </div>
            )}

            <form onSubmit={handleLogin} style={{ display: 'flex', flexDirection: 'column', gap: 22 }}>
                <FormField
                    label="Username or Email"
                    name="username"
                    type="text"
                    placeholder="Enter your username or email"
                    value={identifier}
                    onChange={setIdentifier}
                    autoComplete="username"
                    required
                />

                <FormField
                    label="Password"
                    name="password"
                    type={showPassword ? 'text' : 'password'}
                    placeholder="Enter your password"
                    value={password}
                    onChange={setPassword}
                    autoComplete="current-password"
                    required
                    rightAdornment={
                        <button
                            type="button"
                            onClick={() => setShowPassword(!showPassword)}
                            aria-label={showPassword ? 'Hide password' : 'Show password'}
                            style={{
                                background: 'none',
                                border: 'none',
                                cursor: 'pointer',
                                padding: 4,
                                color: '#94a3b8',
                                display: 'flex',
                                alignItems: 'center',
                            }}
                        >
                            {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                        </button>
                    }
                />

                <div
                    style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        flexWrap: 'wrap',
                        gap: 10,
                    }}
                >
                    <label
                        style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: 8,
                            fontSize: 14,
                            color: '#64748b',
                            cursor: 'pointer',
                            whiteSpace: 'nowrap',
                        }}
                    >
                        <input
                            type="checkbox"
                            checked={rememberMe}
                            onChange={(e) => setRememberMe(e.target.checked)}
                            style={{ width: 16, height: 16, accentColor: '#2e35a0' }}
                        />
                        Remember me
                    </label>
                    <a
                        href="/forgot-password"
                        style={{
                            fontSize: 14,
                            color: '#2e35a0',
                            textDecoration: 'none',
                            fontWeight: 500,
                            whiteSpace: 'nowrap',
                        }}
                    >
                        Forgot password?
                    </a>
                </div>

                <button
                    type="submit"
                    disabled={loading}
                    style={{
                        width: '100%',
                        padding: '15px',
                        minHeight: 48,
                        background: 'linear-gradient(135deg, #242a88, #2e35a0)',
                        color: 'white',
                        border: 'none',
                        borderRadius: 12,
                        fontSize: 16,
                        fontWeight: 600,
                        fontFamily: 'inherit',
                        cursor: loading ? 'wait' : 'pointer',
                        letterSpacing: '0.3px',
                        boxShadow: '0 4px 14px rgba(36,42,136,0.3)',
                        transition: 'all 0.2s',
                    }}
                >
                    {loading ? 'Signing in...' : 'Sign In'}
                </button>
            </form>
        </AuthShell>
    );
};

export default Login;
