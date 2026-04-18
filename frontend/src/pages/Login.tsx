import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Building2, Eye, EyeOff, ChevronRight, Shield, Monitor, BarChart3, Globe } from 'lucide-react';
import apiClient from '../api/client';
import { useAuth } from '../context/AuthContext';
import { useBranding } from '../context/BrandingContext';

interface TenantInfo {
    id: number;
    name: string;
    schema_name: string;
    domain: string | null;
    role: string;
}

const Login = () => {
    const { branding } = useBranding();
    const [identifier, setIdentifier] = useState(() => localStorage.getItem('rememberedUser') || '');
    const [password, setPassword] = useState('');
    const [rememberMe, setRememberMe] = useState(() => !!localStorage.getItem('rememberedUser'));
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);
    const navigate = useNavigate();

    const [step, setStep] = useState<'credentials' | 'tenant'>('credentials');
    const [tenants, setTenants] = useState<TenantInfo[]>([]);
    const [selectingTenant, setSelectingTenant] = useState(false);
    const [showPassword, setShowPassword] = useState(false);
    const { setAuthData, setTenantData, logout } = useAuth();

    const handleLogin = async (e: React.FormEvent) => {
        e.preventDefault();
        setError('');
        setLoading(true);

        try {
            const response = await apiClient.post('/core/auth/login/', {
                // Backend accepts email or username in this field
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
                // Account exists but no tenant role yet (e.g. registered from a
                // domain that couldn't be resolved, or manually created account)
                setError(
                    'Your account is not assigned to any organisation. ' +
                    'Please contact your administrator to be granted access.'
                );
                logout();
                return;
            } else if (userTenants.length === 1) {
                await selectTenantAndNavigate(userTenants[0]);
            } else {
                setTenants(userTenants);
                setStep('tenant');
            }
        } catch (err: any) {
            setError(err.response?.data?.error || err.message || 'Login failed. Please check your credentials.');
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

            const { domain, tenant_name, role, permissions } = response.data;
            
            setTenantData({
                id: tenant.id,
                name: tenant_name,
                domain,
                role: role || tenant.role,
            }, permissions || []);

            // Redirect to setup wizard if tenant setup is incomplete (admin first login)
            if (response.data.setup_required) {
                navigate('/setup');
            } else {
                navigate('/dashboard');
            }
        } catch (err: any) {
            setError(err.response?.data?.error || 'Failed to select tenant.');
        } finally {
            setSelectingTenant(false);
        }
    };

    const roleLabel = (role: string) => {
        const labels: Record<string, string> = {
            admin: 'Admin',
            manager: 'Manager',
            user: 'User',
            viewer: 'Viewer',
        };
        return labels[role] || role;
    };

    // ── Brand Panel (shared between both steps) ─────────────────────

    const BrandPanel = () => (
        <div className="auth-brand-panel" style={{
            width: '50%', minHeight: '100vh',
            background: 'linear-gradient(135deg, #242a88 0%, #1e2480 50%, #2e35a0 100%)',
            display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center',
            padding: '60px', position: 'relative', overflow: 'hidden'
        }}>
            {/* Decorative circles */}
            <div style={{
                position: 'absolute', top: '-100px', right: '-100px',
                width: '500px', height: '500px', borderRadius: '50%',
                background: 'rgba(255,255,255,0.04)'
            }} />
            <div style={{
                position: 'absolute', bottom: '-150px', left: '-150px',
                width: '600px', height: '600px', borderRadius: '50%',
                background: 'rgba(255,255,255,0.03)'
            }} />

            {/* Logo */}
            <div style={{
                width: '72px', height: '72px', background: 'white',
                borderRadius: '18px', display: 'flex', alignItems: 'center', justifyContent: 'center',
                marginBottom: '28px', boxShadow: '0 8px 32px rgba(0,0,0,0.15)',
                overflow: 'hidden',
            }}>
                {branding.logo ? (
                    <img src={branding.logo} alt={branding.name} style={{ width: '100%', height: '100%', objectFit: 'contain' }} />
                ) : (
                    <svg viewBox="0 0 40 40" fill="none" width="40" height="40">
                        <rect x="4" y="8" width="14" height="14" rx="3" fill="#242a88"/>
                        <rect x="22" y="8" width="14" height="14" rx="3" fill="#2e35a0"/>
                        <rect x="4" y="26" width="14" height="6" rx="3" fill="#2e35a0" opacity="0.6"/>
                        <rect x="22" y="26" width="14" height="6" rx="3" fill="#242a88" opacity="0.6"/>
                    </svg>
                )}
            </div>

            <div style={{ fontSize: '42px', fontWeight: 800, color: 'white', letterSpacing: '-1px', marginBottom: '12px' }}>
                {branding.name}
            </div>
            <div style={{
                fontSize: '17px', color: 'rgba(255,255,255,0.75)', textAlign: 'center',
                lineHeight: 1.6, marginBottom: '56px'
            }}>
                {branding.tagline || 'Enterprise Resource Planning\nBuilt for modern organizations'}
            </div>

            {/* Features */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '20px', maxWidth: '380px' }}>
                {[
                    { icon: Shield, text: 'Enterprise-grade security with role-based access control' },
                    { icon: Monitor, text: 'Multi-tenant architecture for scalable deployments' },
                    { icon: BarChart3, text: 'Real-time analytics and financial reporting' },
                    { icon: Globe, text: '12+ integrated modules — Accounting to Quality' },
                ].map((f, i) => (
                    <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '16px', color: 'rgba(255,255,255,0.85)', fontSize: '15px' }}>
                        <div style={{
                            width: '44px', height: '44px', background: 'rgba(255,255,255,0.12)',
                            borderRadius: '12px', display: 'flex', alignItems: 'center', justifyContent: 'center',
                            flexShrink: 0
                        }}>
                            <f.icon size={22} style={{ color: 'rgba(255,255,255,0.9)' }} />
                        </div>
                        <span>{f.text}</span>
                    </div>
                ))}
            </div>
        </div>
    );

    // ── Tenant selection step ──────────────────────────────────────

    if (step === 'tenant') {
        return (
            <div style={{ display: 'flex', minHeight: '100vh' }}>
                <BrandPanel />
                <div className="auth-form-panel" style={{
                    width: '50%', minHeight: '100vh', display: 'flex',
                    flexDirection: 'column', justifyContent: 'center', alignItems: 'center',
                    padding: '60px', background: 'white'
                }}>
                    <div style={{ width: '100%', maxWidth: '420px' }}>
                        <div style={{ marginBottom: '36px', textAlign: 'center' }}>
                            <div style={{
                                width: '64px', height: '64px', background: 'linear-gradient(135deg, #242a88, #2e35a0)',
                                borderRadius: '16px', display: 'flex', alignItems: 'center', justifyContent: 'center',
                                margin: '0 auto 16px', color: 'white'
                            }}>
                                <Building2 size={32} />
                            </div>
                            <h2 style={{ fontSize: '28px', fontWeight: 700, color: '#0f172a', marginBottom: '8px' }}>
                                Select Organization
                            </h2>
                            <p style={{ fontSize: '15px', color: '#64748b' }}>
                                Choose which organization to work with
                            </p>
                        </div>

                        {error && (
                            <div style={{
                                padding: '12px 16px', background: '#fef2f2', color: '#dc2626',
                                borderRadius: '10px', marginBottom: '16px', fontSize: '14px',
                                border: '1px solid #fecaca'
                            }}>
                                {error}
                            </div>
                        )}

                        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                            {tenants.map((tenant) => (
                                <button
                                    key={tenant.id}
                                    onClick={() => selectTenantAndNavigate(tenant)}
                                    disabled={selectingTenant}
                                    style={{
                                        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                                        padding: '16px', border: '1.5px solid #e2e8f0', borderRadius: '12px',
                                        background: 'white', cursor: selectingTenant ? 'wait' : 'pointer',
                                        width: '100%', textAlign: 'left', transition: 'all 0.2s',
                                        fontFamily: 'inherit'
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
                                    <div>
                                        <div style={{ fontWeight: 600, fontSize: '15px', color: '#0f172a' }}>
                                            {tenant.name}
                                        </div>
                                        <div style={{ fontSize: '13px', color: '#64748b', marginTop: '2px' }}>
                                            {roleLabel(tenant.role)}
                                        </div>
                                    </div>
                                    <ChevronRight size={18} style={{ color: '#94a3b8' }} />
                                </button>
                            ))}
                        </div>

                        <button
                            onClick={() => {
                                logout();
                                setStep('credentials');
                                setTenants([]);
                            }}
                            style={{
                                marginTop: '24px', background: 'none', border: 'none',
                                color: '#64748b', cursor: 'pointer', fontSize: '14px',
                                width: '100%', textAlign: 'center', fontFamily: 'inherit'
                            }}
                        >
                            Sign in as a different user
                        </button>
                    </div>
                </div>
            </div>
        );
    }

    // ── Credentials step ───────────────────────────────────────────

    return (
        <div style={{ display: 'flex', minHeight: '100vh' }}>
            <BrandPanel />
            <div style={{
                width: '50%', minHeight: '100vh', display: 'flex',
                flexDirection: 'column', justifyContent: 'center', alignItems: 'center',
                padding: '60px', background: 'white'
            }}>
                <div style={{ width: '100%', maxWidth: '420px' }}>
                    <div style={{ marginBottom: '36px' }}>
                        <h2 style={{ fontSize: '28px', fontWeight: 700, color: '#0f172a', marginBottom: '8px' }}>
                            Welcome back
                        </h2>
                        <p style={{ fontSize: '15px', color: '#64748b' }}>
                            Sign in to your account to continue
                        </p>
                    </div>

                    {error && (
                        <div style={{
                            padding: '12px 16px', background: '#fef2f2', color: '#dc2626',
                            borderRadius: '10px', marginBottom: '16px', fontSize: '14px',
                            border: '1px solid #fecaca'
                        }}>
                            {error}
                        </div>
                    )}

                    <form onSubmit={handleLogin} style={{ display: 'flex', flexDirection: 'column', gap: '22px' }}>
                        <div>
                            <label style={{
                                display: 'block', fontSize: '13px', fontWeight: 600, color: '#475569',
                                marginBottom: '8px', textTransform: 'uppercase', letterSpacing: '0.5px'
                            }}>
                                Username or Email
                            </label>
                            <input
                                type="text"
                                placeholder="Enter your username or email"
                                value={identifier}
                                onChange={(e) => setIdentifier(e.target.value)}
                                autoComplete="username"
                                required
                                style={{
                                    width: '100%', padding: '14px 16px', border: '1.5px solid #e2e8f0',
                                    borderRadius: '12px', fontSize: '15px', background: '#f8fafc',
                                    outline: 'none', color: '#1e293b', fontFamily: 'inherit',
                                    transition: 'all 0.2s'
                                }}
                                onFocus={(e) => {
                                    e.target.style.borderColor = '#2e35a0';
                                    e.target.style.background = 'white';
                                    e.target.style.boxShadow = '0 0 0 3px rgba(36,42,136,0.1)';
                                }}
                                onBlur={(e) => {
                                    e.target.style.borderColor = '#e2e8f0';
                                    e.target.style.background = '#f8fafc';
                                    e.target.style.boxShadow = 'none';
                                }}
                            />
                        </div>

                        <div>
                            <label style={{
                                display: 'block', fontSize: '13px', fontWeight: 600, color: '#475569',
                                marginBottom: '8px', textTransform: 'uppercase', letterSpacing: '0.5px'
                            }}>
                                Password
                            </label>
                            <div style={{ position: 'relative' }}>
                                <input
                                    type={showPassword ? 'text' : 'password'}
                                    placeholder="Enter your password"
                                    value={password}
                                    onChange={(e) => setPassword(e.target.value)}
                                    required
                                    style={{
                                        width: '100%', padding: '14px 46px 14px 16px', border: '1.5px solid #e2e8f0',
                                        borderRadius: '12px', fontSize: '15px', background: '#f8fafc',
                                        outline: 'none', color: '#1e293b', fontFamily: 'inherit',
                                        transition: 'all 0.2s'
                                    }}
                                    onFocus={(e) => {
                                        e.target.style.borderColor = '#2e35a0';
                                        e.target.style.background = 'white';
                                        e.target.style.boxShadow = '0 0 0 3px rgba(36,42,136,0.1)';
                                    }}
                                    onBlur={(e) => {
                                        e.target.style.borderColor = '#e2e8f0';
                                        e.target.style.background = '#f8fafc';
                                        e.target.style.boxShadow = 'none';
                                    }}
                                />
                                <button
                                    type="button"
                                    onClick={() => setShowPassword(!showPassword)}
                                    style={{
                                        position: 'absolute', right: '14px', top: '50%', transform: 'translateY(-50%)',
                                        background: 'none', border: 'none', cursor: 'pointer', padding: '4px',
                                        color: '#94a3b8', display: 'flex', alignItems: 'center'
                                    }}
                                >
                                    {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                                </button>
                            </div>
                        </div>

                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '14px', color: '#64748b', cursor: 'pointer' }}>
                                <input
                                    type="checkbox"
                                    checked={rememberMe}
                                    onChange={(e) => setRememberMe(e.target.checked)}
                                    style={{ width: '16px', height: '16px', accentColor: '#2e35a0' }}
                                />
                                Remember me
                            </label>
                            <a href="/forgot-password" style={{ fontSize: '14px', color: '#2e35a0', textDecoration: 'none', fontWeight: 500 }}>
                                Forgot password?
                            </a>
                        </div>

                        <button
                            type="submit"
                            disabled={loading}
                            style={{
                                width: '100%', padding: '15px',
                                background: 'linear-gradient(135deg, #242a88, #2e35a0)',
                                color: 'white', border: 'none', borderRadius: '12px',
                                fontSize: '16px', fontWeight: 600, fontFamily: 'inherit',
                                cursor: loading ? 'wait' : 'pointer', letterSpacing: '0.3px',
                                boxShadow: '0 4px 14px rgba(36,42,136,0.3)',
                                transition: 'all 0.2s'
                            }}
                        >
                            {loading ? 'Signing in...' : 'Sign In'}
                        </button>
                    </form>

                    <div style={{ textAlign: 'center', marginTop: '32px', fontSize: '14px', color: '#64748b' }}>
                        Don't have an account?{' '}
                        <a href="/register" style={{ color: '#2e35a0', textDecoration: 'none', fontWeight: 600 }}>
                            Create Account
                        </a>
                    </div>

                    <div style={{
                        display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px',
                        marginTop: '24px', fontSize: '12px', color: '#94a3b8'
                    }}>
                        <Shield size={14} style={{ color: '#94a3b8' }} />
                        256-bit SSL encrypted &middot; SOC 2 Compliant
                    </div>
                </div>
            </div>
        </div>
    );
};

export default Login;
