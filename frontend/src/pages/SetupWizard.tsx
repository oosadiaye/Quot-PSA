import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
    Building2, Mail, Phone, MapPin, Globe, FileText, Calendar,
    DollarSign, Clock, Users, TrendingUp, ChevronRight, ChevronLeft,
    Check, Loader2, Sparkles, Shield, BarChart3, Zap,
} from 'lucide-react';
import apiClient from '../api/client';
import { useBranding } from '../context/BrandingContext';

interface SetupProfile {
    company_name: string;
    company_email: string;
    company_phone: string;
    company_address: string;
    company_city: string;
    company_state: string;
    company_country: string;
    company_website: string;
    tax_id: string;
    registration_number: string;
    fiscal_year_start: number;
    default_currency: string;
    timezone: string;
    business_category: string;
    employee_count_range: string;
    annual_revenue_range: string;
    setup_completed: boolean;
    current_step: number;
    completed_steps: number[];
}

const STEPS = [
    {
        id: 0, title: 'Company Info', icon: Building2,
        description: 'Tell us about your organization',
        hint: 'This information will appear on invoices and official documents.',
        color: '#6366f1',
    },
    {
        id: 1, title: 'Contact & Location', icon: MapPin,
        description: 'Where are you located?',
        hint: 'Used for tax calculations, time zones, and correspondence.',
        color: '#0ea5e9',
    },
    {
        id: 2, title: 'Financial Settings', icon: DollarSign,
        description: 'Configure your accounting defaults',
        hint: 'Set your fiscal year, currency, and registration details.',
        color: '#10b981',
    },
    {
        id: 3, title: 'Organization Size', icon: Users,
        description: 'Help us personalize your experience',
        hint: 'We\'ll tailor module recommendations based on your organization scale.',
        color: '#f59e0b',
    },
];

const CURRENCIES = [
    'USD', 'EUR', 'GBP', 'NGN', 'GHS', 'KES', 'ZAR', 'CAD', 'AUD',
    'INR', 'JPY', 'CNY', 'BRL', 'AED', 'SAR',
];

const FISCAL_MONTHS = [
    { value: 1, label: 'January' }, { value: 2, label: 'February' },
    { value: 3, label: 'March' }, { value: 4, label: 'April' },
    { value: 5, label: 'May' }, { value: 6, label: 'June' },
    { value: 7, label: 'July' }, { value: 8, label: 'August' },
    { value: 9, label: 'September' }, { value: 10, label: 'October' },
    { value: 11, label: 'November' }, { value: 12, label: 'December' },
];

const EMPLOYEE_RANGES = ['1-10', '11-50', '51-200', '201-500', '500+'];
const REVENUE_RANGES = ['< $100K', '$100K - $500K', '$500K - $1M', '$1M - $5M', '$5M - $20M', '$20M+'];

const TIMEZONES = [
    'UTC', 'Africa/Lagos', 'Africa/Accra', 'Africa/Nairobi', 'Africa/Johannesburg',
    'America/New_York', 'America/Chicago', 'America/Los_Angeles', 'Europe/London',
    'Europe/Berlin', 'Asia/Dubai', 'Asia/Kolkata', 'Asia/Tokyo', 'Asia/Shanghai',
    'Australia/Sydney',
];

const BUSINESS_CATEGORIES = [
    { value: 'manufacturing', label: 'Manufacturing', icon: Zap },
    { value: 'retail', label: 'Retail & Commerce', icon: Building2 },
    { value: 'services', label: 'Professional Services', icon: Users },
    { value: 'technology', label: 'Technology', icon: Globe },
    { value: 'healthcare', label: 'Healthcare', icon: Shield },
    { value: 'finance', label: 'Finance & Banking', icon: BarChart3 },
    { value: 'education', label: 'Education', icon: FileText },
    { value: 'other', label: 'Other', icon: Sparkles },
];

// ── Sidebar Feature Cards ────────────────────────────────────
const FEATURES = [
    { icon: Shield, title: 'Enterprise Security', desc: 'Bank-grade encryption & RBAC' },
    { icon: BarChart3, title: 'Real-time Analytics', desc: 'Live dashboards & reports' },
    { icon: Zap, title: 'Workflow Automation', desc: 'Smart approval chains' },
];

const SetupWizard = () => {
    const { branding } = useBranding();
    const navigate = useNavigate();
    const [currentStep, setCurrentStep] = useState(0);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [completedSteps, setCompletedSteps] = useState<Set<number>>(new Set());
    const [profile, setProfile] = useState<SetupProfile>({
        company_name: '', company_email: '', company_phone: '',
        company_address: '', company_city: '', company_state: '',
        company_country: '', company_website: '', tax_id: '',
        registration_number: '', fiscal_year_start: 1, default_currency: 'USD',
        timezone: 'UTC', business_category: 'other', employee_count_range: '',
        annual_revenue_range: '', setup_completed: false, current_step: 0,
        completed_steps: [],
    });

    useEffect(() => { loadProfile(); }, []);

    const loadProfile = async () => {
        try {
            const res = await apiClient.get('/core/setup/profile/');
            setProfile(res.data);
            setCurrentStep(res.data.current_step || 0);
            setCompletedSteps(new Set(res.data.completed_steps || []));
        } catch {
            // Profile doesn't exist yet — use defaults
        } finally {
            setLoading(false);
        }
    };

    const updateField = (field: keyof SetupProfile, value: string | number) => {
        setProfile(prev => ({ ...prev, [field]: value }));
    };

    const saveStep = async () => {
        setSaving(true);
        try {
            const newCompleted = new Set(completedSteps);
            newCompleted.add(currentStep);
            setCompletedSteps(newCompleted);
            await apiClient.put('/core/setup/profile/', {
                ...profile,
                current_step: currentStep,
                completed_step: currentStep,
            });
        } catch {
            // Silently continue
        } finally {
            setSaving(false);
        }
    };

    const handleNext = async () => {
        await saveStep();
        if (currentStep < STEPS.length - 1) setCurrentStep(prev => prev + 1);
    };

    const handleBack = () => {
        if (currentStep > 0) setCurrentStep(prev => prev - 1);
    };

    const handleComplete = async () => {
        await saveStep();
        setSaving(true);
        try {
            await apiClient.post('/core/setup/complete/');
            navigate('/dashboard');
        } catch {
            navigate('/dashboard');
        } finally {
            setSaving(false);
        }
    };

    const handleSkip = () => navigate('/dashboard');

    // ── Input Styles ─────────────────────────────────────────
    const inputBase: React.CSSProperties = {
        width: '100%', padding: '12px 16px', border: '2px solid #e2e8f0',
        borderRadius: '12px', fontSize: '14px', background: '#fff',
        outline: 'none', color: '#1e293b', fontFamily: 'inherit',
        transition: 'all 0.2s ease',
    };
    const labelStyle: React.CSSProperties = {
        display: 'flex', alignItems: 'center', gap: '6px',
        fontSize: '12px', fontWeight: 700, color: '#475569',
        marginBottom: '8px', textTransform: 'uppercase', letterSpacing: '0.6px',
    };
    const selectStyle: React.CSSProperties = {
        ...inputBase, appearance: 'none' as const, cursor: 'pointer', paddingRight: '40px',
        backgroundImage: 'url("data:image/svg+xml,%3Csvg xmlns=\'http://www.w3.org/2000/svg\' width=\'12\' height=\'12\' fill=\'%2394a3b8\' viewBox=\'0 0 16 16\'%3E%3Cpath d=\'M8 11L3 6h10z\'/%3E%3C/svg%3E")',
        backgroundRepeat: 'no-repeat', backgroundPosition: 'right 14px center',
    };
    const handleFocus = (e: React.FocusEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
        e.target.style.borderColor = STEPS[currentStep].color;
        e.target.style.boxShadow = `0 0 0 4px ${STEPS[currentStep].color}12`;
        e.target.style.background = 'white';
    };
    const handleBlur = (e: React.FocusEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
        e.target.style.borderColor = '#e2e8f0';
        e.target.style.boxShadow = 'none';
    };

    const stepColor = STEPS[currentStep].color;

    if (loading) {
        return (
            <div style={{
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                minHeight: '100vh', background: '#0f172a',
            }}>
                <div style={{ textAlign: 'center' }}>
                    <Loader2 size={40} style={{ animation: 'spin 1s linear infinite', color: '#6366f1' }} />
                    <div style={{ marginTop: '16px', fontSize: '14px', color: '#94a3b8', fontWeight: 500 }}>
                        Loading your workspace...
                    </div>
                </div>
            </div>
        );
    }

    const isLastStep = currentStep === STEPS.length - 1;
    const progressPct = ((completedSteps.size) / STEPS.length) * 100;

    return (
        <div style={{
            display: 'flex', minHeight: '100vh',
            fontFamily: "'Inter', -apple-system, sans-serif",
        }}>
            {/* ── Left Sidebar ─────────────────────────────────────────── */}
            <div style={{
                width: '380px', flexShrink: 0,
                background: 'linear-gradient(165deg, #0f172a 0%, #1e1b4b 50%, #312e81 100%)',
                padding: '40px 32px', display: 'flex', flexDirection: 'column',
                position: 'relative', overflow: 'hidden',
            }}>
                {/* Decorative circles */}
                <div style={{
                    position: 'absolute', top: '-80px', right: '-80px',
                    width: '240px', height: '240px', borderRadius: '50%',
                    background: 'rgba(99, 102, 241, 0.08)',
                }} />
                <div style={{
                    position: 'absolute', bottom: '-60px', left: '-40px',
                    width: '200px', height: '200px', borderRadius: '50%',
                    background: 'rgba(99, 102, 241, 0.05)',
                }} />
                <div style={{
                    position: 'absolute', top: '40%', right: '10%',
                    width: '120px', height: '120px', borderRadius: '50%',
                    background: 'rgba(14, 165, 233, 0.06)',
                }} />

                {/* Logo & Brand */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '14px', marginBottom: '48px', position: 'relative', zIndex: 1 }}>
                    <div style={{
                        width: '44px', height: '44px',
                        background: 'linear-gradient(135deg, #6366f1, #8b5cf6)',
                        borderRadius: '14px', display: 'flex', alignItems: 'center', justifyContent: 'center',
                        boxShadow: '0 8px 24px rgba(99, 102, 241, 0.3)',
                        overflow: 'hidden',
                    }}>
                        {branding.logo ? (
                            <img src={branding.logo} alt="" style={{ width: '100%', height: '100%', objectFit: 'contain' }} />
                        ) : (
                            <Building2 size={22} color="white" />
                        )}
                    </div>
                    <div>
                        <div style={{ fontSize: '18px', fontWeight: 800, color: 'white', letterSpacing: '-0.3px' }}>
                            {branding.appName || 'QUOT ERP'}
                        </div>
                        <div style={{ fontSize: '12px', color: '#94a3b8', fontWeight: 500 }}>Setup Wizard</div>
                    </div>
                </div>

                {/* Step Navigation */}
                <div style={{ flex: 1, position: 'relative', zIndex: 1 }}>
                    <div style={{ fontSize: '11px', fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '1.2px', marginBottom: '20px' }}>
                        Getting Started
                    </div>

                    {STEPS.map((step, idx) => {
                        const isActive = idx === currentStep;
                        const isDone = completedSteps.has(idx);
                        const StepIcon = step.icon;
                        return (
                            <button
                                key={step.id}
                                onClick={() => setCurrentStep(idx)}
                                style={{
                                    display: 'flex', alignItems: 'center', gap: '14px',
                                    width: '100%', padding: '14px 16px', marginBottom: '6px',
                                    borderRadius: '14px', border: 'none',
                                    background: isActive ? 'rgba(255,255,255,0.08)' : 'transparent',
                                    cursor: 'pointer', transition: 'all 0.25s ease',
                                    textAlign: 'left',
                                }}
                            >
                                <div style={{
                                    width: '40px', height: '40px', borderRadius: '12px',
                                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                                    background: isDone
                                        ? 'linear-gradient(135deg, #22c55e, #16a34a)'
                                        : isActive
                                            ? `linear-gradient(135deg, ${step.color}, ${step.color}cc)`
                                            : 'rgba(255,255,255,0.06)',
                                    boxShadow: isDone
                                        ? '0 4px 12px rgba(34, 197, 94, 0.3)'
                                        : isActive
                                            ? `0 4px 12px ${step.color}40`
                                            : 'none',
                                    transition: 'all 0.3s ease', flexShrink: 0,
                                }}>
                                    {isDone
                                        ? <Check size={16} color="white" strokeWidth={3} />
                                        : <StepIcon size={16} color={isActive ? 'white' : '#64748b'} />
                                    }
                                </div>
                                <div>
                                    <div style={{
                                        fontSize: '14px', fontWeight: 600,
                                        color: isActive ? 'white' : isDone ? '#a5b4fc' : '#64748b',
                                        transition: 'color 0.2s',
                                    }}>{step.title}</div>
                                    <div style={{
                                        fontSize: '12px',
                                        color: isActive ? '#a5b4fc' : '#475569',
                                        marginTop: '2px',
                                    }}>{step.description}</div>
                                </div>
                            </button>
                        );
                    })}

                    {/* Progress bar */}
                    <div style={{ marginTop: '32px', padding: '0 4px' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                            <span style={{ fontSize: '12px', color: '#64748b', fontWeight: 600 }}>Progress</span>
                            <span style={{ fontSize: '12px', color: '#a5b4fc', fontWeight: 700 }}>
                                {completedSteps.size}/{STEPS.length}
                            </span>
                        </div>
                        <div style={{
                            height: '6px', borderRadius: '3px',
                            background: 'rgba(255,255,255,0.08)',
                            overflow: 'hidden',
                        }}>
                            <div style={{
                                height: '100%', borderRadius: '3px',
                                background: 'linear-gradient(90deg, #6366f1, #8b5cf6)',
                                width: `${progressPct}%`,
                                transition: 'width 0.5s ease',
                            }} />
                        </div>
                    </div>
                </div>

                {/* Feature Cards */}
                <div style={{ position: 'relative', zIndex: 1, borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: '24px' }}>
                    {FEATURES.map((f, i) => {
                        const FIcon = f.icon;
                        return (
                            <div key={i} style={{
                                display: 'flex', alignItems: 'center', gap: '12px',
                                padding: '10px 0',
                            }}>
                                <div style={{
                                    width: '32px', height: '32px', borderRadius: '8px',
                                    background: 'rgba(99, 102, 241, 0.12)',
                                    display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
                                }}>
                                    <FIcon size={14} color="#a5b4fc" />
                                </div>
                                <div>
                                    <div style={{ fontSize: '13px', fontWeight: 600, color: '#e2e8f0' }}>{f.title}</div>
                                    <div style={{ fontSize: '11px', color: '#64748b' }}>{f.desc}</div>
                                </div>
                            </div>
                        );
                    })}
                </div>
            </div>

            {/* ── Right Content Panel ──────────────────────────────────── */}
            <div style={{
                flex: 1, background: '#f8fafc',
                display: 'flex', flexDirection: 'column',
                overflow: 'auto',
            }}>
                {/* Top Bar */}
                <div style={{
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    padding: '20px 40px', borderBottom: '1px solid #e2e8f0',
                    background: 'white',
                }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                        {/* Step badge */}
                        <div style={{
                            display: 'flex', alignItems: 'center', gap: '6px',
                            padding: '6px 14px', borderRadius: '999px',
                            background: `${stepColor}10`, border: `1.5px solid ${stepColor}30`,
                        }}>
                            <div style={{
                                width: '6px', height: '6px', borderRadius: '50%',
                                background: stepColor,
                            }} />
                            <span style={{ fontSize: '12px', fontWeight: 700, color: stepColor }}>
                                Step {currentStep + 1} of {STEPS.length}
                            </span>
                        </div>
                        {/* Inline dots */}
                        <div style={{ display: 'flex', gap: '4px' }}>
                            {STEPS.map((_, i) => (
                                <div key={i} style={{
                                    width: i === currentStep ? '24px' : '8px',
                                    height: '8px', borderRadius: '4px',
                                    background: i === currentStep ? stepColor
                                        : completedSteps.has(i) ? '#22c55e' : '#e2e8f0',
                                    transition: 'all 0.3s ease',
                                }} />
                            ))}
                        </div>
                    </div>
                    <button onClick={handleSkip} style={{
                        padding: '8px 20px', border: '1.5px solid #e2e8f0', borderRadius: '10px',
                        background: 'white', fontSize: '13px', fontWeight: 600, color: '#94a3b8',
                        cursor: 'pointer', fontFamily: 'inherit', transition: 'all 0.2s',
                    }}
                        onMouseEnter={e => { e.currentTarget.style.borderColor = '#cbd5e1'; e.currentTarget.style.color = '#64748b'; }}
                        onMouseLeave={e => { e.currentTarget.style.borderColor = '#e2e8f0'; e.currentTarget.style.color = '#94a3b8'; }}
                    >
                        Skip for now
                    </button>
                </div>

                {/* Form Area */}
                <div style={{
                    flex: 1, padding: '40px',
                    display: 'flex', justifyContent: 'center',
                }}>
                    <div style={{ width: '100%', maxWidth: '680px' }}>
                        {/* Step Header */}
                        <div style={{ marginBottom: '32px' }}>
                            <div style={{
                                display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                                width: '52px', height: '52px', borderRadius: '16px',
                                background: `linear-gradient(135deg, ${stepColor}18, ${stepColor}08)`,
                                border: `1.5px solid ${stepColor}20`,
                                marginBottom: '16px',
                            }}>
                                {React.createElement(STEPS[currentStep].icon, { size: 24, color: stepColor })}
                            </div>
                            <h2 style={{
                                fontSize: '26px', fontWeight: 800, color: '#0f172a',
                                marginBottom: '6px', letterSpacing: '-0.4px',
                            }}>
                                {STEPS[currentStep].title}
                            </h2>
                            <p style={{ fontSize: '15px', color: '#64748b', lineHeight: 1.5, margin: 0 }}>
                                {STEPS[currentStep].hint}
                            </p>
                        </div>

                        {/* Form Card */}
                        <div style={{
                            background: 'white', borderRadius: '20px', padding: '32px',
                            border: '1px solid #e2e8f0',
                            boxShadow: '0 1px 3px rgba(0,0,0,0.04), 0 8px 24px rgba(0,0,0,0.02)',
                        }}>
                            {/* Step 0: Company Info */}
                            {currentStep === 0 && (
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
                                    <div style={{ gridColumn: '1 / -1' }}>
                                        <label style={labelStyle}>
                                            <Building2 size={12} /> Company Name
                                            <span style={{ color: '#ef4444', marginLeft: '2px' }}>*</span>
                                        </label>
                                        <input value={profile.company_name}
                                            onChange={e => updateField('company_name', e.target.value)}
                                            placeholder="Acme Corporation Ltd."
                                            style={inputBase} onFocus={handleFocus} onBlur={handleBlur} />
                                    </div>
                                    <div>
                                        <label style={labelStyle}>
                                            <FileText size={12} /> Registration Number
                                        </label>
                                        <input value={profile.registration_number}
                                            onChange={e => updateField('registration_number', e.target.value)}
                                            placeholder="RC-123456"
                                            style={inputBase} onFocus={handleFocus} onBlur={handleBlur} />
                                    </div>
                                    <div>
                                        <label style={labelStyle}>
                                            <FileText size={12} /> Tax ID / TIN / VAT
                                        </label>
                                        <input value={profile.tax_id}
                                            onChange={e => updateField('tax_id', e.target.value)}
                                            placeholder="TIN-00000000-0001"
                                            style={inputBase} onFocus={handleFocus} onBlur={handleBlur} />
                                    </div>
                                    <div style={{ gridColumn: '1 / -1' }}>
                                        <label style={labelStyle}>
                                            <Globe size={12} /> Company Website
                                        </label>
                                        <input value={profile.company_website}
                                            onChange={e => updateField('company_website', e.target.value)}
                                            placeholder="https://www.example.com"
                                            style={inputBase} onFocus={handleFocus} onBlur={handleBlur} />
                                    </div>
                                    <div style={{ gridColumn: '1 / -1' }}>
                                        <label style={labelStyle}>
                                            <Sparkles size={12} /> Business Category
                                        </label>
                                        <div style={{
                                            display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '10px',
                                        }}>
                                            {BUSINESS_CATEGORIES.map(cat => {
                                                const sel = profile.business_category === cat.value;
                                                const CatIcon = cat.icon;
                                                return (
                                                    <button key={cat.value} type="button"
                                                        onClick={() => updateField('business_category', cat.value)}
                                                        style={{
                                                            display: 'flex', flexDirection: 'column',
                                                            alignItems: 'center', gap: '6px',
                                                            padding: '14px 8px', borderRadius: '14px',
                                                            border: sel ? `2px solid ${stepColor}` : '2px solid #f1f5f9',
                                                            background: sel ? `${stepColor}08` : '#fafbfc',
                                                            cursor: 'pointer', transition: 'all 0.2s',
                                                            fontFamily: 'inherit',
                                                        }}
                                                        onMouseEnter={e => { if (!sel) e.currentTarget.style.borderColor = '#e2e8f0'; }}
                                                        onMouseLeave={e => { if (!sel) e.currentTarget.style.borderColor = '#f1f5f9'; }}
                                                    >
                                                        <CatIcon size={18} color={sel ? stepColor : '#94a3b8'} />
                                                        <span style={{
                                                            fontSize: '11px', fontWeight: 600,
                                                            color: sel ? '#1e293b' : '#64748b',
                                                        }}>{cat.label}</span>
                                                    </button>
                                                );
                                            })}
                                        </div>
                                    </div>
                                </div>
                            )}

                            {/* Step 1: Contact & Location */}
                            {currentStep === 1 && (
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
                                    <div>
                                        <label style={labelStyle}>
                                            <Mail size={12} /> Company Email
                                            <span style={{ color: '#ef4444', marginLeft: '2px' }}>*</span>
                                        </label>
                                        <input type="email" value={profile.company_email}
                                            onChange={e => updateField('company_email', e.target.value)}
                                            placeholder="info@company.com"
                                            style={inputBase} onFocus={handleFocus} onBlur={handleBlur} />
                                    </div>
                                    <div>
                                        <label style={labelStyle}>
                                            <Phone size={12} /> Phone Number
                                        </label>
                                        <input value={profile.company_phone}
                                            onChange={e => updateField('company_phone', e.target.value)}
                                            placeholder="+234 800 000 0000"
                                            style={inputBase} onFocus={handleFocus} onBlur={handleBlur} />
                                    </div>
                                    <div style={{ gridColumn: '1 / -1' }}>
                                        <label style={labelStyle}>
                                            <MapPin size={12} /> Address
                                        </label>
                                        <textarea value={profile.company_address}
                                            onChange={e => updateField('company_address', e.target.value)}
                                            placeholder="123 Business Avenue, Suite 100"
                                            rows={2}
                                            style={{ ...inputBase, resize: 'vertical' as const }}
                                            onFocus={handleFocus} onBlur={handleBlur} />
                                    </div>
                                    <div>
                                        <label style={labelStyle}>City</label>
                                        <input value={profile.company_city}
                                            onChange={e => updateField('company_city', e.target.value)}
                                            placeholder="Lagos"
                                            style={inputBase} onFocus={handleFocus} onBlur={handleBlur} />
                                    </div>
                                    <div>
                                        <label style={labelStyle}>State / Province</label>
                                        <input value={profile.company_state}
                                            onChange={e => updateField('company_state', e.target.value)}
                                            placeholder="Lagos State"
                                            style={inputBase} onFocus={handleFocus} onBlur={handleBlur} />
                                    </div>
                                    <div style={{ gridColumn: '1 / -1' }}>
                                        <label style={labelStyle}>
                                            <Globe size={12} /> Country
                                        </label>
                                        <input value={profile.company_country}
                                            onChange={e => updateField('company_country', e.target.value)}
                                            placeholder="Nigeria"
                                            style={inputBase} onFocus={handleFocus} onBlur={handleBlur} />
                                    </div>
                                </div>
                            )}

                            {/* Step 2: Financial Settings */}
                            {currentStep === 2 && (
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
                                    <div>
                                        <label style={labelStyle}>
                                            <DollarSign size={12} /> Default Currency
                                        </label>
                                        <select value={profile.default_currency}
                                            onChange={e => updateField('default_currency', e.target.value)}
                                            style={selectStyle} onFocus={handleFocus} onBlur={handleBlur}>
                                            {CURRENCIES.map(c => <option key={c} value={c}>{c}</option>)}
                                        </select>
                                    </div>
                                    <div>
                                        <label style={labelStyle}>
                                            <Calendar size={12} /> Fiscal Year Start
                                        </label>
                                        <select value={profile.fiscal_year_start}
                                            onChange={e => updateField('fiscal_year_start', Number(e.target.value))}
                                            style={selectStyle} onFocus={handleFocus} onBlur={handleBlur}>
                                            {FISCAL_MONTHS.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}
                                        </select>
                                    </div>
                                    <div style={{ gridColumn: '1 / -1' }}>
                                        <label style={labelStyle}>
                                            <Clock size={12} /> Timezone
                                        </label>
                                        <select value={profile.timezone}
                                            onChange={e => updateField('timezone', e.target.value)}
                                            style={selectStyle} onFocus={handleFocus} onBlur={handleBlur}>
                                            {TIMEZONES.map(tz => <option key={tz} value={tz}>{tz.replace(/_/g, ' ')}</option>)}
                                        </select>
                                    </div>

                                    {/* Info callout */}
                                    <div style={{
                                        gridColumn: '1 / -1',
                                        display: 'flex', alignItems: 'flex-start', gap: '12px',
                                        padding: '16px', borderRadius: '14px',
                                        background: 'linear-gradient(135deg, #f0fdf4, #ecfdf5)',
                                        border: '1.5px solid #bbf7d0',
                                    }}>
                                        <div style={{
                                            width: '32px', height: '32px', borderRadius: '10px',
                                            background: '#dcfce7', display: 'flex', alignItems: 'center',
                                            justifyContent: 'center', flexShrink: 0,
                                        }}>
                                            <Shield size={16} color="#16a34a" />
                                        </div>
                                        <div>
                                            <div style={{ fontSize: '13px', fontWeight: 700, color: '#166534', marginBottom: '2px' }}>
                                                Financial settings are important
                                            </div>
                                            <div style={{ fontSize: '12px', color: '#15803d', lineHeight: 1.5 }}>
                                                Currency and fiscal year affect all financial reports, invoices, and accounting entries.
                                                These can be changed later in Settings.
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            )}

                            {/* Step 3: Organization Size */}
                            {currentStep === 3 && (
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '28px' }}>
                                    <div>
                                        <label style={labelStyle}>
                                            <Users size={12} /> Number of Employees
                                        </label>
                                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px', marginTop: '4px' }}>
                                            {EMPLOYEE_RANGES.map(range => {
                                                const selected = profile.employee_count_range === range;
                                                return (
                                                    <button key={range} type="button"
                                                        onClick={() => updateField('employee_count_range', range)}
                                                        style={{
                                                            display: 'flex', alignItems: 'center', gap: '8px',
                                                            padding: '12px 22px', borderRadius: '14px',
                                                            border: selected ? `2px solid ${stepColor}` : '2px solid #f1f5f9',
                                                            background: selected
                                                                ? `linear-gradient(135deg, ${stepColor}10, ${stepColor}05)`
                                                                : '#fafbfc',
                                                            color: selected ? '#1e293b' : '#64748b',
                                                            fontSize: '14px', fontWeight: 600, cursor: 'pointer',
                                                            fontFamily: 'inherit', transition: 'all 0.2s',
                                                            boxShadow: selected ? `0 2px 8px ${stepColor}18` : 'none',
                                                        }}
                                                        onMouseEnter={e => { if (!selected) { e.currentTarget.style.borderColor = '#e2e8f0'; e.currentTarget.style.background = '#f8fafc'; } }}
                                                        onMouseLeave={e => { if (!selected) { e.currentTarget.style.borderColor = '#f1f5f9'; e.currentTarget.style.background = '#fafbfc'; } }}
                                                    >
                                                        <Users size={14} color={selected ? stepColor : '#94a3b8'} />
                                                        {range}
                                                        {selected && <Check size={14} color={stepColor} strokeWidth={3} />}
                                                    </button>
                                                );
                                            })}
                                        </div>
                                    </div>
                                    <div>
                                        <label style={labelStyle}>
                                            <TrendingUp size={12} /> Annual Revenue Range
                                        </label>
                                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px', marginTop: '4px' }}>
                                            {REVENUE_RANGES.map(range => {
                                                const selected = profile.annual_revenue_range === range;
                                                return (
                                                    <button key={range} type="button"
                                                        onClick={() => updateField('annual_revenue_range', range)}
                                                        style={{
                                                            display: 'flex', alignItems: 'center', gap: '8px',
                                                            padding: '12px 22px', borderRadius: '14px',
                                                            border: selected ? `2px solid ${stepColor}` : '2px solid #f1f5f9',
                                                            background: selected
                                                                ? `linear-gradient(135deg, ${stepColor}10, ${stepColor}05)`
                                                                : '#fafbfc',
                                                            color: selected ? '#1e293b' : '#64748b',
                                                            fontSize: '14px', fontWeight: 600, cursor: 'pointer',
                                                            fontFamily: 'inherit', transition: 'all 0.2s',
                                                            boxShadow: selected ? `0 2px 8px ${stepColor}18` : 'none',
                                                        }}
                                                        onMouseEnter={e => { if (!selected) { e.currentTarget.style.borderColor = '#e2e8f0'; e.currentTarget.style.background = '#f8fafc'; } }}
                                                        onMouseLeave={e => { if (!selected) { e.currentTarget.style.borderColor = '#f1f5f9'; e.currentTarget.style.background = '#fafbfc'; } }}
                                                    >
                                                        <TrendingUp size={14} color={selected ? stepColor : '#94a3b8'} />
                                                        {range}
                                                        {selected && <Check size={14} color={stepColor} strokeWidth={3} />}
                                                    </button>
                                                );
                                            })}
                                        </div>
                                    </div>

                                    {/* Completion callout */}
                                    <div style={{
                                        display: 'flex', alignItems: 'flex-start', gap: '12px',
                                        padding: '16px', borderRadius: '14px',
                                        background: 'linear-gradient(135deg, #fffbeb, #fef3c7)',
                                        border: '1.5px solid #fde68a',
                                    }}>
                                        <div style={{
                                            width: '32px', height: '32px', borderRadius: '10px',
                                            background: '#fef9c3', display: 'flex', alignItems: 'center',
                                            justifyContent: 'center', flexShrink: 0,
                                        }}>
                                            <Sparkles size={16} color="#d97706" />
                                        </div>
                                        <div>
                                            <div style={{ fontSize: '13px', fontWeight: 700, color: '#92400e', marginBottom: '2px' }}>
                                                Almost there!
                                            </div>
                                            <div style={{ fontSize: '12px', color: '#a16207', lineHeight: 1.5 }}>
                                                After completing this step, your workspace will be ready.
                                                You can always update these details later from Settings.
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            )}
                        </div>

                        {/* Navigation Buttons */}
                        <div style={{
                            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                            marginTop: '28px',
                        }}>
                            <button onClick={handleBack} disabled={currentStep === 0}
                                style={{
                                    display: 'flex', alignItems: 'center', gap: '8px',
                                    padding: '12px 24px', borderRadius: '14px',
                                    border: '2px solid #e2e8f0', background: 'white',
                                    fontSize: '14px', fontWeight: 600,
                                    color: currentStep === 0 ? '#cbd5e1' : '#475569',
                                    cursor: currentStep === 0 ? 'default' : 'pointer',
                                    fontFamily: 'inherit', transition: 'all 0.2s',
                                }}
                                onMouseEnter={e => { if (currentStep > 0) { e.currentTarget.style.borderColor = '#cbd5e1'; e.currentTarget.style.background = '#f8fafc'; } }}
                                onMouseLeave={e => { e.currentTarget.style.borderColor = '#e2e8f0'; e.currentTarget.style.background = 'white'; }}
                            >
                                <ChevronLeft size={18} /> Back
                            </button>

                            <div style={{ display: 'flex', gap: '12px' }}>
                                {isLastStep ? (
                                    <button onClick={handleComplete} disabled={saving}
                                        style={{
                                            display: 'flex', alignItems: 'center', gap: '10px',
                                            padding: '14px 36px', borderRadius: '14px', border: 'none',
                                            background: 'linear-gradient(135deg, #22c55e, #16a34a)',
                                            fontSize: '15px', fontWeight: 700, color: 'white',
                                            cursor: saving ? 'wait' : 'pointer', fontFamily: 'inherit',
                                            boxShadow: '0 4px 16px rgba(34,197,94,0.35)',
                                            transition: 'all 0.2s',
                                            letterSpacing: '-0.2px',
                                        }}
                                        onMouseEnter={e => { e.currentTarget.style.transform = 'translateY(-1px)'; e.currentTarget.style.boxShadow = '0 6px 20px rgba(34,197,94,0.4)'; }}
                                        onMouseLeave={e => { e.currentTarget.style.transform = 'none'; e.currentTarget.style.boxShadow = '0 4px 16px rgba(34,197,94,0.35)'; }}
                                    >
                                        {saving
                                            ? <Loader2 size={18} style={{ animation: 'spin 1s linear infinite' }} />
                                            : <><Check size={18} strokeWidth={3} /> Complete Setup</>
                                        }
                                    </button>
                                ) : (
                                    <button onClick={handleNext} disabled={saving}
                                        style={{
                                            display: 'flex', alignItems: 'center', gap: '8px',
                                            padding: '14px 32px', borderRadius: '14px', border: 'none',
                                            background: `linear-gradient(135deg, ${stepColor}, ${stepColor}dd)`,
                                            fontSize: '15px', fontWeight: 700, color: 'white',
                                            cursor: saving ? 'wait' : 'pointer', fontFamily: 'inherit',
                                            boxShadow: `0 4px 16px ${stepColor}40`,
                                            transition: 'all 0.2s',
                                            letterSpacing: '-0.2px',
                                        }}
                                        onMouseEnter={e => { e.currentTarget.style.transform = 'translateY(-1px)'; e.currentTarget.style.boxShadow = `0 6px 20px ${stepColor}50`; }}
                                        onMouseLeave={e => { e.currentTarget.style.transform = 'none'; e.currentTarget.style.boxShadow = `0 4px 16px ${stepColor}40`; }}
                                    >
                                        {saving
                                            ? <Loader2 size={18} style={{ animation: 'spin 1s linear infinite' }} />
                                            : <>Continue <ChevronRight size={18} /></>
                                        }
                                    </button>
                                )}
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <style>{`
                @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
                @media (max-width: 960px) {
                    /* Hide sidebar on narrow screens, go single-column */
                }
            `}</style>
        </div>
    );
};

export default SetupWizard;
