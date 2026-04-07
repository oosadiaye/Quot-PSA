import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
    Building2, Mail, Phone, MapPin, Globe, FileText, Calendar,
    DollarSign, Clock, Users, TrendingUp, ChevronRight, ChevronLeft,
    Check, Loader2,
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
    { id: 0, title: 'Company Info', icon: Building2, description: 'Basic company details' },
    { id: 1, title: 'Contact & Location', icon: MapPin, description: 'Address and contact info' },
    { id: 2, title: 'Financial Settings', icon: DollarSign, description: 'Currency, fiscal year, tax' },
    { id: 3, title: 'Organization Size', icon: Users, description: 'Team and revenue range' },
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

    useEffect(() => {
        loadProfile();
    }, []);

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
            // Silently continue — data will be saved on next attempt
        } finally {
            setSaving(false);
        }
    };

    const handleNext = async () => {
        await saveStep();
        if (currentStep < STEPS.length - 1) {
            setCurrentStep(prev => prev + 1);
        }
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

    const handleSkip = () => {
        navigate('/dashboard');
    };

    // ── Styles ────────────────────────────────────────────────
    const inputStyle: React.CSSProperties = {
        width: '100%', padding: '12px 14px', border: '2px solid #e2e8f0',
        borderRadius: '10px', fontSize: '14px', background: '#f8fafc',
        outline: 'none', color: '#1e293b', fontFamily: 'inherit',
        transition: 'border-color 0.2s, box-shadow 0.2s',
    };
    const labelStyle: React.CSSProperties = {
        display: 'block', fontSize: '12px', fontWeight: 600, color: '#475569',
        marginBottom: '6px', textTransform: 'uppercase', letterSpacing: '0.5px',
    };
    const selectStyle: React.CSSProperties = {
        ...inputStyle, appearance: 'none' as const, cursor: 'pointer', paddingRight: '36px',
    };
    const handleFocus = (e: React.FocusEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
        e.target.style.borderColor = '#242a88';
        e.target.style.boxShadow = '0 0 0 3px rgba(36,42,136,0.08)';
        e.target.style.background = 'white';
    };
    const handleBlur = (e: React.FocusEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
        e.target.style.borderColor = '#e2e8f0';
        e.target.style.boxShadow = 'none';
        e.target.style.background = '#f8fafc';
    };

    if (loading) {
        return (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '100vh', background: '#f8fafc' }}>
                <Loader2 size={32} style={{ animation: 'spin 1s linear infinite', color: '#242a88' }} />
            </div>
        );
    }

    const isLastStep = currentStep === STEPS.length - 1;

    return (
        <div style={{ minHeight: '100vh', background: '#f8fafc', fontFamily: "'Inter', sans-serif" }}>
            {/* Header */}
            <div style={{
                background: 'white', borderBottom: '1px solid #e2e8f0', padding: '16px 32px',
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                    <div style={{
                        width: '36px', height: '36px', background: 'linear-gradient(135deg, #242a88, #2e35a0)',
                        borderRadius: '10px', display: 'flex', alignItems: 'center', justifyContent: 'center',
                        overflow: 'hidden',
                    }}>
                        {branding.logo ? (
                            <img src={branding.logo} alt="" style={{ width: '100%', height: '100%', objectFit: 'contain' }} />
                        ) : (
                            <Building2 size={18} color="white" />
                        )}
                    </div>
                    <div>
                        <div style={{ fontSize: '16px', fontWeight: 700, color: '#0f172a' }}>Setup Wizard</div>
                        <div style={{ fontSize: '12px', color: '#94a3b8' }}>Configure your organization</div>
                    </div>
                </div>
                <button onClick={handleSkip} style={{
                    padding: '8px 20px', border: '1.5px solid #e2e8f0', borderRadius: '8px',
                    background: 'white', fontSize: '13px', fontWeight: 600, color: '#64748b',
                    cursor: 'pointer', fontFamily: 'inherit',
                }}>
                    Skip for now
                </button>
            </div>

            <div style={{ maxWidth: '860px', margin: '0 auto', padding: '40px 24px' }}>
                {/* Step Indicator */}
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px', marginBottom: '40px' }}>
                    {STEPS.map((step, idx) => {
                        const isActive = idx === currentStep;
                        const isDone = completedSteps.has(idx);
                        return (
                            <React.Fragment key={step.id}>
                                {idx > 0 && (
                                    <div style={{
                                        width: '48px', height: '2px',
                                        background: isDone || isActive ? '#242a88' : '#e2e8f0',
                                        borderRadius: '1px', transition: 'background 0.3s',
                                    }} />
                                )}
                                <button
                                    onClick={() => setCurrentStep(idx)}
                                    style={{
                                        display: 'flex', alignItems: 'center', gap: '8px',
                                        padding: '8px 16px', borderRadius: '10px', border: 'none',
                                        background: isActive ? 'rgba(36,42,136,0.08)' : 'transparent',
                                        cursor: 'pointer', transition: 'all 0.2s',
                                    }}
                                >
                                    <div style={{
                                        width: '32px', height: '32px', borderRadius: '50%',
                                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                                        background: isDone ? '#22c55e' : isActive ? '#242a88' : '#e2e8f0',
                                        color: isDone || isActive ? 'white' : '#94a3b8',
                                        transition: 'all 0.3s', flexShrink: 0,
                                    }}>
                                        {isDone ? <Check size={14} strokeWidth={3} /> : <step.icon size={14} />}
                                    </div>
                                    <div style={{ textAlign: 'left' }}>
                                        <div style={{
                                            fontSize: '13px', fontWeight: 600,
                                            color: isActive ? '#0f172a' : '#94a3b8',
                                        }}>{step.title}</div>
                                    </div>
                                </button>
                            </React.Fragment>
                        );
                    })}
                </div>

                {/* Step Content */}
                <div style={{
                    background: 'white', borderRadius: '16px', padding: '36px',
                    border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
                }}>
                    <div style={{ marginBottom: '28px' }}>
                        <h2 style={{ fontSize: '22px', fontWeight: 700, color: '#0f172a', marginBottom: '4px' }}>
                            {STEPS[currentStep].title}
                        </h2>
                        <p style={{ fontSize: '14px', color: '#64748b' }}>{STEPS[currentStep].description}</p>
                    </div>

                    {/* Step 0: Company Info */}
                    {currentStep === 0 && (
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '18px' }}>
                            <div style={{ gridColumn: '1 / -1' }}>
                                <label style={labelStyle}>Company Name *</label>
                                <input value={profile.company_name} onChange={e => updateField('company_name', e.target.value)}
                                    placeholder="Acme Corporation Ltd." style={inputStyle} onFocus={handleFocus} onBlur={handleBlur} />
                            </div>
                            <div>
                                <label style={labelStyle}>Registration Number</label>
                                <div style={{ position: 'relative' }}>
                                    <FileText size={15} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: '#94a3b8' }} />
                                    <input value={profile.registration_number} onChange={e => updateField('registration_number', e.target.value)}
                                        placeholder="RC-123456" style={{ ...inputStyle, paddingLeft: '36px' }} onFocus={handleFocus} onBlur={handleBlur} />
                                </div>
                            </div>
                            <div>
                                <label style={labelStyle}>Tax ID / TIN / VAT</label>
                                <div style={{ position: 'relative' }}>
                                    <FileText size={15} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: '#94a3b8' }} />
                                    <input value={profile.tax_id} onChange={e => updateField('tax_id', e.target.value)}
                                        placeholder="TIN-00000000-0001" style={{ ...inputStyle, paddingLeft: '36px' }} onFocus={handleFocus} onBlur={handleBlur} />
                                </div>
                            </div>
                            <div style={{ gridColumn: '1 / -1' }}>
                                <label style={labelStyle}>Company Website</label>
                                <div style={{ position: 'relative' }}>
                                    <Globe size={15} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: '#94a3b8' }} />
                                    <input value={profile.company_website} onChange={e => updateField('company_website', e.target.value)}
                                        placeholder="https://www.example.com" style={{ ...inputStyle, paddingLeft: '36px' }} onFocus={handleFocus} onBlur={handleBlur} />
                                </div>
                            </div>
                        </div>
                    )}

                    {/* Step 1: Contact & Location */}
                    {currentStep === 1 && (
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '18px' }}>
                            <div>
                                <label style={labelStyle}>Company Email *</label>
                                <div style={{ position: 'relative' }}>
                                    <Mail size={15} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: '#94a3b8' }} />
                                    <input type="email" value={profile.company_email} onChange={e => updateField('company_email', e.target.value)}
                                        placeholder="info@company.com" style={{ ...inputStyle, paddingLeft: '36px' }} onFocus={handleFocus} onBlur={handleBlur} />
                                </div>
                            </div>
                            <div>
                                <label style={labelStyle}>Phone Number</label>
                                <div style={{ position: 'relative' }}>
                                    <Phone size={15} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: '#94a3b8' }} />
                                    <input value={profile.company_phone} onChange={e => updateField('company_phone', e.target.value)}
                                        placeholder="+234 800 000 0000" style={{ ...inputStyle, paddingLeft: '36px' }} onFocus={handleFocus} onBlur={handleBlur} />
                                </div>
                            </div>
                            <div style={{ gridColumn: '1 / -1' }}>
                                <label style={labelStyle}>Address</label>
                                <textarea value={profile.company_address} onChange={e => updateField('company_address', e.target.value)}
                                    placeholder="123 Business Avenue, Suite 100"
                                    rows={2}
                                    style={{ ...inputStyle, resize: 'vertical' as const }} onFocus={handleFocus} onBlur={handleBlur} />
                            </div>
                            <div>
                                <label style={labelStyle}>City</label>
                                <input value={profile.company_city} onChange={e => updateField('company_city', e.target.value)}
                                    placeholder="Lagos" style={inputStyle} onFocus={handleFocus} onBlur={handleBlur} />
                            </div>
                            <div>
                                <label style={labelStyle}>State / Province</label>
                                <input value={profile.company_state} onChange={e => updateField('company_state', e.target.value)}
                                    placeholder="Lagos State" style={inputStyle} onFocus={handleFocus} onBlur={handleBlur} />
                            </div>
                            <div style={{ gridColumn: '1 / -1' }}>
                                <label style={labelStyle}>Country</label>
                                <input value={profile.company_country} onChange={e => updateField('company_country', e.target.value)}
                                    placeholder="Nigeria" style={inputStyle} onFocus={handleFocus} onBlur={handleBlur} />
                            </div>
                        </div>
                    )}

                    {/* Step 2: Financial Settings */}
                    {currentStep === 2 && (
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '18px' }}>
                            <div>
                                <label style={labelStyle}>Default Currency</label>
                                <div style={{ position: 'relative' }}>
                                    <DollarSign size={15} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: '#94a3b8', zIndex: 1 }} />
                                    <select value={profile.default_currency} onChange={e => updateField('default_currency', e.target.value)}
                                        style={{ ...selectStyle, paddingLeft: '36px' }} onFocus={handleFocus} onBlur={handleBlur}>
                                        {CURRENCIES.map(c => <option key={c} value={c}>{c}</option>)}
                                    </select>
                                </div>
                            </div>
                            <div>
                                <label style={labelStyle}>Fiscal Year Start</label>
                                <div style={{ position: 'relative' }}>
                                    <Calendar size={15} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: '#94a3b8', zIndex: 1 }} />
                                    <select value={profile.fiscal_year_start} onChange={e => updateField('fiscal_year_start', Number(e.target.value))}
                                        style={{ ...selectStyle, paddingLeft: '36px' }} onFocus={handleFocus} onBlur={handleBlur}>
                                        {FISCAL_MONTHS.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}
                                    </select>
                                </div>
                            </div>
                            <div style={{ gridColumn: '1 / -1' }}>
                                <label style={labelStyle}>Timezone</label>
                                <div style={{ position: 'relative' }}>
                                    <Clock size={15} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: '#94a3b8', zIndex: 1 }} />
                                    <select value={profile.timezone} onChange={e => updateField('timezone', e.target.value)}
                                        style={{ ...selectStyle, paddingLeft: '36px' }} onFocus={handleFocus} onBlur={handleBlur}>
                                        {TIMEZONES.map(tz => <option key={tz} value={tz}>{tz.replace(/_/g, ' ')}</option>)}
                                    </select>
                                </div>
                            </div>
                            <div>
                                <label style={labelStyle}>Tax ID / TIN</label>
                                <input value={profile.tax_id} onChange={e => updateField('tax_id', e.target.value)}
                                    placeholder="TIN-00000000-0001" style={inputStyle} onFocus={handleFocus} onBlur={handleBlur} />
                            </div>
                            <div>
                                <label style={labelStyle}>Registration Number</label>
                                <input value={profile.registration_number} onChange={e => updateField('registration_number', e.target.value)}
                                    placeholder="RC-123456" style={inputStyle} onFocus={handleFocus} onBlur={handleBlur} />
                            </div>
                        </div>
                    )}

                    {/* Step 3: Organization Size */}
                    {currentStep === 3 && (
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px' }}>
                            <div>
                                <label style={labelStyle}>Number of Employees</label>
                                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginTop: '4px' }}>
                                    {EMPLOYEE_RANGES.map(range => {
                                        const selected = profile.employee_count_range === range;
                                        return (
                                            <button key={range} type="button"
                                                onClick={() => updateField('employee_count_range', range)}
                                                style={{
                                                    padding: '10px 18px', borderRadius: '10px', border: 'none',
                                                    background: selected ? '#242a88' : '#f1f5f9',
                                                    color: selected ? 'white' : '#475569',
                                                    fontSize: '13px', fontWeight: 600, cursor: 'pointer',
                                                    fontFamily: 'inherit', transition: 'all 0.15s',
                                                }}>
                                                <Users size={13} style={{ marginRight: '6px', verticalAlign: '-2px' }} />
                                                {range}
                                            </button>
                                        );
                                    })}
                                </div>
                            </div>
                            <div>
                                <label style={labelStyle}>Annual Revenue Range</label>
                                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginTop: '4px' }}>
                                    {REVENUE_RANGES.map(range => {
                                        const selected = profile.annual_revenue_range === range;
                                        return (
                                            <button key={range} type="button"
                                                onClick={() => updateField('annual_revenue_range', range)}
                                                style={{
                                                    padding: '10px 18px', borderRadius: '10px', border: 'none',
                                                    background: selected ? '#242a88' : '#f1f5f9',
                                                    color: selected ? 'white' : '#475569',
                                                    fontSize: '13px', fontWeight: 600, cursor: 'pointer',
                                                    fontFamily: 'inherit', transition: 'all 0.15s',
                                                }}>
                                                <TrendingUp size={13} style={{ marginRight: '6px', verticalAlign: '-2px' }} />
                                                {range}
                                            </button>
                                        );
                                    })}
                                </div>
                            </div>
                        </div>
                    )}

                    {/* Navigation Buttons */}
                    <div style={{
                        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                        marginTop: '36px', paddingTop: '24px', borderTop: '1px solid #f1f5f9',
                    }}>
                        <button onClick={handleBack} disabled={currentStep === 0}
                            style={{
                                display: 'flex', alignItems: 'center', gap: '6px',
                                padding: '10px 20px', borderRadius: '10px',
                                border: '1.5px solid #e2e8f0', background: 'white',
                                fontSize: '14px', fontWeight: 600, color: currentStep === 0 ? '#cbd5e1' : '#475569',
                                cursor: currentStep === 0 ? 'default' : 'pointer',
                                fontFamily: 'inherit',
                            }}>
                            <ChevronLeft size={16} /> Back
                        </button>

                        <div style={{ display: 'flex', gap: '12px' }}>
                            {isLastStep ? (
                                <button onClick={handleComplete} disabled={saving}
                                    style={{
                                        display: 'flex', alignItems: 'center', gap: '8px',
                                        padding: '12px 28px', borderRadius: '10px', border: 'none',
                                        background: 'linear-gradient(135deg, #22c55e, #16a34a)',
                                        fontSize: '14px', fontWeight: 600, color: 'white',
                                        cursor: saving ? 'wait' : 'pointer', fontFamily: 'inherit',
                                        boxShadow: '0 4px 12px rgba(34,197,94,0.3)',
                                    }}>
                                    {saving ? <Loader2 size={16} style={{ animation: 'spin 1s linear infinite' }} /> : <Check size={16} />}
                                    Complete Setup
                                </button>
                            ) : (
                                <button onClick={handleNext} disabled={saving}
                                    style={{
                                        display: 'flex', alignItems: 'center', gap: '6px',
                                        padding: '12px 28px', borderRadius: '10px', border: 'none',
                                        background: 'linear-gradient(135deg, #242a88, #2e35a0)',
                                        fontSize: '14px', fontWeight: 600, color: 'white',
                                        cursor: saving ? 'wait' : 'pointer', fontFamily: 'inherit',
                                        boxShadow: '0 4px 12px rgba(36,42,136,0.3)',
                                    }}>
                                    {saving ? <Loader2 size={16} style={{ animation: 'spin 1s linear infinite' }} /> : <>Next <ChevronRight size={16} /></>}
                                </button>
                            )}
                        </div>
                    </div>
                </div>

                {/* Progress Summary */}
                <div style={{
                    textAlign: 'center', marginTop: '24px', fontSize: '13px', color: '#94a3b8',
                }}>
                    Step {currentStep + 1} of {STEPS.length} &middot; {completedSteps.size} completed
                </div>
            </div>

            <style>{`
                @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
            `}</style>
        </div>
    );
};

export default SetupWizard;
