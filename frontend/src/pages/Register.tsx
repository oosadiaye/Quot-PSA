import React, { useState, useMemo } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Eye, EyeOff, Shield, CheckCircle, XCircle, Check, Package, ChevronDown } from 'lucide-react';
import apiClient from '../api/client';
import { useBranding } from '../context/BrandingContext';
import { useModulePricing, type ModulePricingItem } from '../hooks/useModulePricing';

const BUSINESS_CATEGORIES = [
    { value: 'agriculture', label: 'Agriculture & Farming' },
    { value: 'manufacturing', label: 'Manufacturing' },
    { value: 'construction', label: 'Construction' },
    { value: 'trading', label: 'Trading & Distribution' },
    { value: 'healthcare', label: 'Healthcare' },
    { value: 'education', label: 'Education' },
    { value: 'technology', label: 'Technology / IT Services' },
    { value: 'hospitality', label: 'Hospitality / Food & Beverage' },
    { value: 'mining', label: 'Mining & Extractive Industries' },
    { value: 'logistics', label: 'Transportation & Logistics' },
    { value: 'real_estate', label: 'Real Estate & Property' },
    { value: 'nonprofit', label: 'Non-Profit / NGO' },
    { value: 'government', label: 'Government / Public Sector' },
    { value: 'retail', label: 'Retail' },
    { value: 'energy', label: 'Energy & Utilities' },
    { value: 'other', label: 'General / Other' },
] as const;

const MODULE_LABELS: Record<string, string> = {
    accounting: 'Accounting', sales: 'Sales', procurement: 'Procurement',
    inventory: 'Inventory', hrm: 'Human Resources', budget: 'Budget Management',
    production: 'Production', quality: 'Quality', service: 'Service',
    dimensions: 'Dimensions', workflow: 'Workflow',
};

const Register = () => {
    const { branding } = useBranding();
    const [searchParams] = useSearchParams();
    const isTenantSignup = searchParams.has('modules') || searchParams.has('billing') || searchParams.has('plan_id');
    const initialModules = searchParams.get('modules')?.split(',').filter(Boolean) || [];
    const initialBilling = (searchParams.get('billing') as 'monthly' | 'yearly') || 'monthly';
    const planId = searchParams.get('plan_id') || '';
    const planType = searchParams.get('plan_type') || '';
    const isFromPlan = !!planId;

    const { data: modulePricingData = [] } = useModulePricing();

    const [firstName, setFirstName] = useState('');
    const [lastName, setLastName] = useState('');
    const [username, setUsername] = useState('');
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [passwordConfirm, setPasswordConfirm] = useState('');
    const [organizationName, setOrganizationName] = useState('');
    const [selectedModules, setSelectedModules] = useState<Set<string>>(new Set(initialModules));
    const [billing, setBilling] = useState<'monthly' | 'yearly'>(initialBilling);
    const [businessCategory, setBusinessCategory] = useState('other');
    const [error, setError] = useState('');
    const [success, setSuccess] = useState('');
    const [loading, setLoading] = useState(false);
    const [showPassword, setShowPassword] = useState(false);
    const [showPasswordConfirm, setShowPasswordConfirm] = useState(false);
    const [agreedToTerms, setAgreedToTerms] = useState(false);
    // Track which fields have been touched so we only show errors after interaction
    const [touched, setTouched] = useState<Record<string, boolean>>({});
    const navigate = useNavigate();

    const toggleModule = (name: string) => {
        setSelectedModules(prev => {
            const next = new Set(prev);
            if (next.has(name)) next.delete(name);
            else next.add(name);
            return next;
        });
    };

    const selectedTotal = useMemo(() => {
        return modulePricingData
            .filter((m: ModulePricingItem) => selectedModules.has(m.module_name))
            .reduce((sum: number, m: ModulePricingItem) => sum + Number(billing === 'monthly' ? m.price_monthly : m.price_yearly), 0);
    }, [modulePricingData, selectedModules, billing]);

    // ── Field-level validation helpers ────────────────────────────────

    const emailValid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
    const usernameValid = /^[a-zA-Z0-9_]{3,}$/.test(username);
    const passwordsMatch = passwordConfirm.length > 0 && password === passwordConfirm;
    const passwordMismatch = touched.passwordConfirm && passwordConfirm.length > 0 && password !== passwordConfirm;

    const passwordRules = [
        { label: 'At least 8 characters', pass: password.length >= 8 },
        { label: 'One uppercase letter',  pass: /[A-Z]/.test(password) },
        { label: 'One number',            pass: /[0-9]/.test(password) },
        { label: 'One special character', pass: /[^A-Za-z0-9]/.test(password) },
    ];

    const getPasswordStrength = () => {
        if (!password) return { bars: 0, label: '', color: '' };
        const score = passwordRules.filter((r) => r.pass).length;
        if (score <= 1) return { bars: 1, label: 'Weak', color: '#ef4444' };
        if (score === 2) return { bars: 2, label: 'Fair', color: '#f59e0b' };
        if (score === 3) return { bars: 3, label: 'Good', color: '#22c55e' };
        return { bars: 4, label: 'Strong', color: '#22c55e' };
    };

    const strength = getPasswordStrength();

    const markTouched = (field: string) =>
        setTouched((prev) => ({ ...prev, [field]: true }));

    const handleRegister = async (e: React.FormEvent) => {
        e.preventDefault();
        setError('');
        setSuccess('');

        // Mark all fields touched to surface any remaining errors
        setTouched({ email: true, username: true, password: true, passwordConfirm: true });

        if (!usernameValid) {
            setError('Username must be at least 3 characters and contain only letters, numbers, or underscores.');
            return;
        }
        if (!emailValid) {
            setError('Please enter a valid email address.');
            return;
        }
        if (password !== passwordConfirm) {
            setError("Passwords don't match.");
            return;
        }
        if (passwordRules.filter((r) => r.pass).length < 3) {
            setError('Password is too weak. Please meet at least 3 of the 4 requirements shown.');
            return;
        }
        if (!agreedToTerms) {
            setError('You must agree to the Terms of Service and Privacy Policy.');
            return;
        }

        if (isTenantSignup && !organizationName.trim()) {
            setError('Organization name is required.');
            return;
        }
        if (isTenantSignup && !isFromPlan && selectedModules.size === 0) {
            setError('Please select at least one module.');
            return;
        }

        setLoading(true);
        try {
            if (isTenantSignup) {
                const payload: Record<string, unknown> = {
                    organization_name: organizationName.trim(),
                    admin_email: email,
                    admin_username: username,
                    admin_password: password,
                    first_name: firstName,
                    last_name: lastName,
                    selected_modules: Array.from(selectedModules),
                    billing_cycle: billing,
                    business_category: businessCategory,
                };
                if (planId) payload.plan_id = Number(planId);
                if (planType) payload.plan_type = planType;

                await apiClient.post('/superadmin/tenant/signup', payload);
                setSuccess('Organization created successfully! Redirecting you to sign in...');
            } else {
                await apiClient.post('/core/users/register/', {
                    username,
                    email,
                    password,
                    password_confirm: passwordConfirm,
                    first_name: firstName,
                    last_name: lastName,
                    tenant_domain: window.location.hostname,
                });
                setSuccess('Account created! Please check your email to verify your address, then sign in.');
            }
            // Redirect after a brief moment so the user can read the success message
            setTimeout(() => navigate('/login'), 3000);
        } catch (err: any) {
            const data = err.response?.data;
            if (data) {
                // DRF errors can be arrays, plain strings, or nested objects —
                // normalise defensively before joining.
                const messages = Object.entries(data)
                    .map(([field, msgs]) => {
                        const fieldLabel = field === 'non_field_errors' || field === 'error' ? '' : `${field}: `;
                        const msgStr = Array.isArray(msgs)
                            ? msgs.join(' ')
                            : typeof msgs === 'string'
                                ? msgs
                                : JSON.stringify(msgs);
                        return `${fieldLabel}${msgStr}`.trim();
                    })
                    .filter(Boolean)
                    .join('  ');
                setError(messages || 'Registration failed.');
            } else {
                setError(err.message || 'Registration failed.');
            }
        } finally {
            setLoading(false);
        }
    };

    const inputStyle: React.CSSProperties = {
        width: '100%', padding: '13px 16px', border: '2.5px solid #e2e8f0',
        borderRadius: '10px', fontSize: '14px', background: '#f8fafc',
        outline: 'none', color: '#1e293b', fontFamily: 'inherit', transition: 'all 0.2s'
    };

    const labelStyle: React.CSSProperties = {
        display: 'block', fontSize: '13px', fontWeight: 600, color: '#475569',
        marginBottom: '6px', textTransform: 'uppercase', letterSpacing: '0.5px'
    };

    const handleFocus = (e: React.FocusEvent<HTMLInputElement>) => {
        e.target.style.borderColor = '#2e35a0';
        e.target.style.background = 'white';
        e.target.style.boxShadow = '0 0 0 3px rgba(36,42,136,0.1)';
    };
    const handleBlur = (e: React.FocusEvent<HTMLInputElement>) => {
        e.target.style.borderColor = '#e2e8f0';
        e.target.style.background = '#f8fafc';
        e.target.style.boxShadow = 'none';
    };

    return (
        <div style={{ display: 'flex', minHeight: '100vh', fontFamily: "'Inter', sans-serif" }}>
            {/* Left Branding Panel */}
            <div style={{
                width: '45%', minHeight: '100vh',
                background: 'linear-gradient(160deg, #242a88 0%, #1e2480 50%, #2e35a0 100%)',
                display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center',
                padding: '60px', position: 'relative', overflow: 'hidden'
            }}>
                <div style={{
                    position: 'absolute', top: '60px', right: '-80px',
                    width: '300px', height: '300px',
                    border: '40px solid rgba(255,255,255,0.04)', borderRadius: '50%'
                }} />
                <div style={{
                    position: 'absolute', bottom: '40px', left: '-60px',
                    width: '250px', height: '250px',
                    border: '40px solid rgba(255,255,255,0.03)', borderRadius: '50%'
                }} />

                {/* Logo */}
                <div style={{
                    width: '64px', height: '64px', background: 'white',
                    borderRadius: '16px', display: 'flex', alignItems: 'center', justifyContent: 'center',
                    marginBottom: '24px', boxShadow: '0 8px 32px rgba(0,0,0,0.15)',
                    overflow: 'hidden',
                }}>
                    {branding.logo ? (
                        <img src={branding.logo} alt={branding.name} style={{ width: '100%', height: '100%', objectFit: 'contain' }} />
                    ) : (
                        <svg viewBox="0 0 40 40" fill="none" width="36" height="36">
                            <rect x="4" y="8" width="14" height="14" rx="3" fill="#242a88"/>
                            <rect x="22" y="8" width="14" height="14" rx="3" fill="#2e35a0"/>
                            <rect x="4" y="26" width="14" height="6" rx="3" fill="#2e35a0" opacity="0.6"/>
                            <rect x="22" y="26" width="14" height="6" rx="3" fill="#242a88" opacity="0.6"/>
                        </svg>
                    )}
                </div>

                <div style={{ fontSize: '36px', fontWeight: 800, color: 'white', letterSpacing: '-1px', marginBottom: '10px' }}>
                    {branding.name}
                </div>
                <div style={{ fontSize: '16px', color: 'rgba(255,255,255,0.7)', textAlign: 'center', lineHeight: 1.6, marginBottom: '48px' }}>
                    {branding.tagline || 'Join thousands of organizations\nalready managing smarter'}
                </div>

                {/* Testimonial */}
                <div style={{
                    background: 'rgba(255,255,255,0.1)', backdropFilter: 'blur(10px)',
                    border: '1px solid rgba(255,255,255,0.15)', borderRadius: '16px',
                    padding: '28px', maxWidth: '380px'
                }}>
                    <div style={{ fontSize: '15px', color: 'rgba(255,255,255,0.9)', lineHeight: 1.7, marginBottom: '20px', fontStyle: 'italic' }}>
                        "DTSG ERP transformed how we handle procurement and accounting. Our month-end close time dropped from 5 days to just 1."
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                        <div style={{
                            width: '40px', height: '40px', background: 'rgba(255,255,255,0.2)',
                            borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center',
                            fontSize: '16px', fontWeight: 700, color: 'white'
                        }}>JA</div>
                        <div>
                            <div style={{ fontSize: '14px', fontWeight: 600, color: 'white' }}>James Adeyemi</div>
                            <div style={{ fontSize: '12px', color: 'rgba(255,255,255,0.6)' }}>CFO, Meridian Industries</div>
                        </div>
                    </div>
                </div>

                {/* Trusted by */}
                <div style={{ marginTop: '40px', textAlign: 'center' }}>
                    <span style={{ fontSize: '11px', textTransform: 'uppercase', letterSpacing: '1.5px', color: 'rgba(255,255,255,0.4)', fontWeight: 600 }}>
                        Trusted by leading enterprises
                    </span>
                    <div style={{ display: 'flex', gap: '24px', marginTop: '16px', justifyContent: 'center' }}>
                        {['ACME', 'NEXUS', 'APEX'].map(name => (
                            <div key={name} style={{
                                width: '80px', height: '28px', background: 'rgba(255,255,255,0.12)',
                                borderRadius: '6px', display: 'flex', alignItems: 'center', justifyContent: 'center',
                                fontSize: '11px', fontWeight: 700, color: 'rgba(255,255,255,0.5)', letterSpacing: '1px'
                            }}>{name}</div>
                        ))}
                    </div>
                </div>
            </div>

            {/* Right Form Panel */}
            <div style={{
                width: '55%', minHeight: '100vh', display: 'flex',
                flexDirection: 'column', justifyContent: 'center', alignItems: 'center',
                padding: '40px 60px', background: 'white'
            }}>
                <div style={{ width: '100%', maxWidth: '480px' }}>
                    <div style={{ marginBottom: '32px' }}>
                        <h2 style={{ fontSize: '28px', fontWeight: 700, color: '#0f172a', marginBottom: '8px' }}>
                            {isTenantSignup ? 'Start your free trial' : 'Create your account'}
                        </h2>
                        <p style={{ fontSize: '15px', color: '#64748b' }}>
                            {isFromPlan
                                ? `Set up your organization — ${planType.charAt(0).toUpperCase() + planType.slice(1)} plan selected`
                                : isTenantSignup
                                ? 'Set up your organization and choose your modules'
                                : `Get started with ${branding.name} in minutes`}
                        </p>
                    </div>

                    {success && (
                        <div style={{
                            padding: '12px 16px', background: '#f0fdf4', color: '#16a34a',
                            borderRadius: '10px', marginBottom: '16px', fontSize: '14px',
                            border: '1px solid #bbf7d0', display: 'flex', alignItems: 'center', gap: '8px'
                        }}>
                            <CheckCircle size={16} />
                            {success}
                        </div>
                    )}
                    {error && (
                        <div style={{
                            padding: '12px 16px', background: '#fef2f2', color: '#dc2626',
                            borderRadius: '10px', marginBottom: '16px', fontSize: '14px',
                            border: '1px solid #fecaca'
                        }}>
                            {error}
                        </div>
                    )}

                    <form onSubmit={handleRegister}>
                        {/* ── Tenant signup fields ────────────────────── */}
                        {isTenantSignup && (
                            <>
                                <div style={{ marginBottom: '18px' }}>
                                    <label style={labelStyle}>Organization Name</label>
                                    <input type="text" placeholder="Your company or organization" value={organizationName}
                                        onChange={(e) => setOrganizationName(e.target.value)} required
                                        style={inputStyle} onFocus={handleFocus} onBlur={handleBlur} />
                                </div>

                                {/* Business Category */}
                                <div style={{ marginBottom: '18px' }}>
                                    <label style={labelStyle}>Industry / Business Category</label>
                                    <div style={{ position: 'relative' }}>
                                        <select
                                            value={businessCategory}
                                            onChange={(e) => setBusinessCategory(e.target.value)}
                                            style={{
                                                ...inputStyle,
                                                appearance: 'none',
                                                paddingRight: '40px',
                                                cursor: 'pointer',
                                            }}
                                        >
                                            {BUSINESS_CATEGORIES.map(cat => (
                                                <option key={cat.value} value={cat.value}>{cat.label}</option>
                                            ))}
                                        </select>
                                        <ChevronDown size={16} style={{
                                            position: 'absolute', right: '14px', top: '50%',
                                            transform: 'translateY(-50%)', pointerEvents: 'none', color: '#94a3b8',
                                        }} />
                                    </div>
                                    <p style={{ fontSize: '11px', color: '#94a3b8', marginTop: '4px' }}>
                                        Pre-populates your account with industry-specific templates (Chart of Accounts, BOMs, etc.)
                                    </p>
                                </div>

                                {/* Plan summary when coming from a plan */}
                                {isFromPlan && selectedModules.size > 0 && (
                                    <div style={{ marginBottom: '18px' }}>
                                        <label style={labelStyle}>Plan Includes</label>
                                        <div style={{
                                            padding: '12px 14px', borderRadius: 10,
                                            background: 'rgba(36,42,136,0.04)', border: '1.5px solid rgba(36,42,136,0.12)',
                                        }}>
                                            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                                                {Array.from(selectedModules).map(mod => (
                                                    <span key={mod} style={{
                                                        display: 'inline-flex', alignItems: 'center', gap: '4px',
                                                        padding: '4px 10px', borderRadius: 6,
                                                        background: 'rgba(36,42,136,0.08)', color: '#242a88',
                                                        fontSize: '11px', fontWeight: 600,
                                                    }}>
                                                        <Check size={10} strokeWidth={3} />
                                                        {MODULE_LABELS[mod] || mod.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase())}
                                                    </span>
                                                ))}
                                            </div>
                                            <div style={{ fontSize: '11px', color: '#64748b', marginTop: '8px' }}>
                                                {selectedModules.size} module{selectedModules.size !== 1 ? 's' : ''} &middot; {billing === 'yearly' ? 'Yearly' : 'Monthly'} billing
                                            </div>
                                        </div>
                                    </div>
                                )}

                                {/* Module selection — only show when building custom (not from plan) */}
                                {!isFromPlan && (
                                <div style={{ marginBottom: '18px' }}>
                                    <label style={labelStyle}>Selected Modules</label>
                                    <div style={{
                                        display: 'flex', gap: '6px', marginBottom: '10px',
                                    }}>
                                        <button type="button" onClick={() => setBilling('monthly')}
                                            style={{
                                                padding: '5px 14px', borderRadius: 6, border: 'none', cursor: 'pointer',
                                                background: billing === 'monthly' ? '#242a88' : '#e2e8f0',
                                                color: billing === 'monthly' ? '#fff' : '#475569',
                                                fontSize: '12px', fontWeight: 600, fontFamily: 'inherit',
                                            }}>Monthly</button>
                                        <button type="button" onClick={() => setBilling('yearly')}
                                            style={{
                                                padding: '5px 14px', borderRadius: 6, border: 'none', cursor: 'pointer',
                                                background: billing === 'yearly' ? '#242a88' : '#e2e8f0',
                                                color: billing === 'yearly' ? '#fff' : '#475569',
                                                fontSize: '12px', fontWeight: 600, fontFamily: 'inherit',
                                            }}>Yearly <span style={{ color: billing === 'yearly' ? '#93c5fd' : '#242a88', fontSize: '10px' }}>-20%</span></button>
                                    </div>
                                    <div style={{
                                        display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '8px',
                                        maxHeight: '200px', overflowY: 'auto', padding: '2px',
                                    }}>
                                        {(modulePricingData.length > 0
                                            ? modulePricingData.map((m: ModulePricingItem) => ({
                                                name: m.module_name, label: m.title,
                                                price: billing === 'monthly' ? m.price_monthly : m.price_yearly,
                                            }))
                                            : Object.entries(MODULE_LABELS).map(([name, label]) => ({
                                                name, label, price: '',
                                            }))
                                        ).map((mod) => {
                                            const selected = selectedModules.has(mod.name);
                                            return (
                                                <div key={mod.name} onClick={() => toggleModule(mod.name)}
                                                    style={{
                                                        display: 'flex', alignItems: 'center', gap: '8px',
                                                        padding: '8px 10px', borderRadius: 8, cursor: 'pointer',
                                                        background: selected ? 'rgba(36,42,136,0.06)' : '#f8fafc',
                                                        border: `1.5px solid ${selected ? '#242a88' : '#e2e8f0'}`,
                                                        transition: 'all 150ms ease',
                                                    }}>
                                                    <div style={{
                                                        width: 18, height: 18, borderRadius: 4, flexShrink: 0,
                                                        background: selected ? '#242a88' : '#e2e8f0',
                                                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                                                    }}>
                                                        {selected && <Check size={12} color="#fff" strokeWidth={3} />}
                                                    </div>
                                                    <div style={{ flex: 1, minWidth: 0 }}>
                                                        <div style={{ fontSize: '12px', fontWeight: 600, color: '#1e293b' }}>{mod.label}</div>
                                                        {mod.price && Number(mod.price) > 0 && (
                                                            <div style={{ fontSize: '11px', color: '#64748b' }}>${mod.price}/{billing === 'monthly' ? 'mo' : 'yr'}</div>
                                                        )}
                                                    </div>
                                                </div>
                                            );
                                        })}
                                    </div>
                                    {selectedModules.size > 0 && selectedTotal > 0 && (
                                        <div style={{
                                            marginTop: '8px', padding: '8px 12px', borderRadius: 8,
                                            background: 'rgba(36,42,136,0.04)', display: 'flex',
                                            justifyContent: 'space-between', alignItems: 'center',
                                        }}>
                                            <span style={{ fontSize: '12px', color: '#475569' }}>
                                                {selectedModules.size} module{selectedModules.size !== 1 ? 's' : ''}
                                            </span>
                                            <span style={{ fontSize: '14px', fontWeight: 700, color: '#242a88' }}>
                                                ${selectedTotal.toFixed(2)}/{billing === 'monthly' ? 'mo' : 'yr'}
                                            </span>
                                        </div>
                                    )}
                                </div>
                                )}
                            </>
                        )}

                        {/* Name row */}
                        <div style={{ display: 'flex', gap: '16px', marginBottom: '18px' }}>
                            <div style={{ flex: 1 }}>
                                <label style={labelStyle}>First Name</label>
                                <input type="text" placeholder="First name" value={firstName}
                                    onChange={(e) => setFirstName(e.target.value)}
                                    style={inputStyle} onFocus={handleFocus} onBlur={handleBlur} />
                            </div>
                            <div style={{ flex: 1 }}>
                                <label style={labelStyle}>Last Name</label>
                                <input type="text" placeholder="Last name" value={lastName}
                                    onChange={(e) => setLastName(e.target.value)}
                                    style={inputStyle} onFocus={handleFocus} onBlur={handleBlur} />
                            </div>
                        </div>

                        <div style={{ marginBottom: '18px' }}>
                            <label style={labelStyle}>Username</label>
                            <input type="text" placeholder="Choose a username (letters, numbers, _)" value={username}
                                onChange={(e) => setUsername(e.target.value.toLowerCase().replace(/\s/g, ''))} required
                                style={{
                                    ...inputStyle,
                                    borderColor: touched.username && username.length > 0
                                        ? (usernameValid ? '#22c55e' : '#ef4444')
                                        : undefined,
                                }}
                                onFocus={handleFocus}
                                onBlur={(e) => { handleBlur(e); markTouched('username'); }} />
                            {touched.username && username.length > 0 && !usernameValid && (
                                <p style={{ fontSize: '12px', color: '#ef4444', marginTop: '4px', display: 'flex', alignItems: 'center', gap: '4px' }}>
                                    <XCircle size={12} /> Min. 3 chars — letters, numbers, and underscores only.
                                </p>
                            )}
                        </div>

                        <div style={{ marginBottom: '18px' }}>
                            <label style={labelStyle}>Email Address</label>
                            <input type="email" placeholder="name@company.com" value={email}
                                onChange={(e) => setEmail(e.target.value)} required
                                style={{
                                    ...inputStyle,
                                    borderColor: touched.email && email.length > 0
                                        ? (emailValid ? '#22c55e' : '#ef4444')
                                        : undefined,
                                }}
                                onFocus={handleFocus}
                                onBlur={(e) => { handleBlur(e); markTouched('email'); }} />
                            {touched.email && email.length > 0 && !emailValid && (
                                <p style={{ fontSize: '12px', color: '#ef4444', marginTop: '4px', display: 'flex', alignItems: 'center', gap: '4px' }}>
                                    <XCircle size={12} /> Please enter a valid email address.
                                </p>
                            )}
                        </div>

                        <div style={{ marginBottom: '18px' }}>
                            <label style={labelStyle}>Password</label>
                            <div style={{ position: 'relative' }}>
                                <input type={showPassword ? 'text' : 'password'}
                                    placeholder="Create a strong password" value={password}
                                    onChange={(e) => setPassword(e.target.value)} required
                                    style={{ ...inputStyle, paddingRight: '46px' }}
                                    onFocus={handleFocus}
                                    onBlur={(e) => { handleBlur(e); markTouched('password'); }} />
                                <button type="button" onClick={() => setShowPassword(!showPassword)}
                                    style={{
                                        position: 'absolute', right: '14px', top: '50%', transform: 'translateY(-50%)',
                                        background: 'none', border: 'none', cursor: 'pointer', padding: '4px',
                                        color: '#94a3b8', display: 'flex', alignItems: 'center'
                                    }}>
                                    {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                                </button>
                            </div>
                            {password && (
                                <>
                                    {/* Strength bar */}
                                    <div style={{ marginTop: '8px', display: 'flex', gap: '4px', alignItems: 'center' }}>
                                        {[1, 2, 3, 4].map(i => (
                                            <div key={i} style={{
                                                height: '4px', flex: 1, borderRadius: '2px',
                                                background: i <= strength.bars ? strength.color : '#e2e8f0',
                                                transition: 'background 0.3s'
                                            }} />
                                        ))}
                                        <span style={{ fontSize: '11px', color: strength.color, fontWeight: 600, marginLeft: '8px', minWidth: '36px' }}>
                                            {strength.label}
                                        </span>
                                    </div>
                                    {/* Per-rule checklist */}
                                    <div style={{ marginTop: '8px', display: 'flex', flexWrap: 'wrap', gap: '4px 16px' }}>
                                        {passwordRules.map((rule) => (
                                            <span key={rule.label} style={{
                                                fontSize: '11px', display: 'flex', alignItems: 'center', gap: '4px',
                                                color: rule.pass ? '#22c55e' : '#94a3b8'
                                            }}>
                                                {rule.pass
                                                    ? <CheckCircle size={11} />
                                                    : <XCircle size={11} />}
                                                {rule.label}
                                            </span>
                                        ))}
                                    </div>
                                </>
                            )}
                        </div>

                        <div style={{ marginBottom: '18px' }}>
                            <label style={labelStyle}>Confirm Password</label>
                            <div style={{ position: 'relative' }}>
                                <input type={showPasswordConfirm ? 'text' : 'password'}
                                    placeholder="Confirm your password" value={passwordConfirm}
                                    onChange={(e) => setPasswordConfirm(e.target.value)} required
                                    style={{
                                        ...inputStyle, paddingRight: '46px',
                                        borderColor: touched.passwordConfirm && passwordConfirm.length > 0
                                            ? (passwordsMatch ? '#22c55e' : '#ef4444')
                                            : undefined,
                                    }}
                                    onFocus={handleFocus}
                                    onBlur={(e) => { handleBlur(e); markTouched('passwordConfirm'); }} />
                                <button type="button" onClick={() => setShowPasswordConfirm(!showPasswordConfirm)}
                                    style={{
                                        position: 'absolute', right: '14px', top: '50%', transform: 'translateY(-50%)',
                                        background: 'none', border: 'none', cursor: 'pointer', padding: '4px',
                                        color: '#94a3b8', display: 'flex', alignItems: 'center'
                                    }}>
                                    {showPasswordConfirm ? <EyeOff size={18} /> : <Eye size={18} />}
                                </button>
                            </div>
                            {passwordMismatch && (
                                <p style={{ fontSize: '12px', color: '#ef4444', marginTop: '4px', display: 'flex', alignItems: 'center', gap: '4px' }}>
                                    <XCircle size={12} /> Passwords don't match.
                                </p>
                            )}
                            {passwordsMatch && (
                                <p style={{ fontSize: '12px', color: '#22c55e', marginTop: '4px', display: 'flex', alignItems: 'center', gap: '4px' }}>
                                    <CheckCircle size={12} /> Passwords match.
                                </p>
                            )}
                        </div>

                        <label style={{
                            display: 'flex', alignItems: 'flex-start', gap: '10px',
                            margin: '20px 0 24px', fontSize: '13px', color: '#64748b', lineHeight: 1.5,
                            cursor: 'pointer'
                        }}>
                            <input type="checkbox" checked={agreedToTerms}
                                onChange={(e) => setAgreedToTerms(e.target.checked)}
                                style={{ width: '16px', height: '16px', marginTop: '2px', accentColor: '#2e35a0', flexShrink: 0 }} />
                            <span>
                                I agree to the <a href="#" style={{ color: '#2e35a0', textDecoration: 'none', fontWeight: 500 }}>Terms of Service</a> and{' '}
                                <a href="#" style={{ color: '#2e35a0', textDecoration: 'none', fontWeight: 500 }}>Privacy Policy</a>
                            </span>
                        </label>

                        <button type="submit" disabled={loading}
                            style={{
                                width: '100%', padding: '14px',
                                background: 'linear-gradient(135deg, #242a88, #2e35a0)',
                                color: 'white', border: 'none', borderRadius: '12px',
                                fontSize: '16px', fontWeight: 600, fontFamily: 'inherit',
                                cursor: loading ? 'wait' : 'pointer', letterSpacing: '0.3px',
                                boxShadow: '0 4px 14px rgba(36,42,136,0.3)'
                            }}>
                            {loading
                                ? (isTenantSignup ? 'Creating organization...' : 'Creating account...')
                                : (isTenantSignup ? 'Start Free Trial' : 'Create Account')}
                        </button>
                    </form>

                    <div style={{ textAlign: 'center', marginTop: '24px', fontSize: '14px', color: '#64748b' }}>
                        Already have an account?{' '}
                        <a href="/login" style={{ color: '#2e35a0', textDecoration: 'none', fontWeight: 600 }}>Sign In</a>
                    </div>

                    <div style={{
                        display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px',
                        marginTop: '20px', fontSize: '12px', color: '#94a3b8'
                    }}>
                        <Shield size={14} style={{ color: '#94a3b8' }} />
                        Your data is protected with enterprise-grade encryption
                    </div>
                </div>
            </div>
        </div>
    );
};

export default Register;
