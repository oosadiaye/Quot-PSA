import { useEffect, useState, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '../../api/client';
import SettingsLayout from './SettingsLayout';
import LoadingScreen from '../../components/common/LoadingScreen';
import {
    Building, CheckCircle, AlertTriangle, Upload, Trash2,
    Phone, Mail, Globe, MapPin, Image,
} from 'lucide-react';

interface BrandingData {
    name: string;
    tagline: string;
    logo: string | null;
    address: string;
    city: string;
    state: string;
    country: string;
    postal_code: string;
    phone: string;
    email: string;
    website: string;
}

const useTenantBranding = () =>
    useQuery<BrandingData>({
        queryKey: ['tenant-branding'],
        queryFn: async () => {
            const { data } = await apiClient.get('/tenants/branding/');
            return data;
        },
    });

const useUpdateBranding = () => {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: async (formData: FormData) => {
            const { data } = await apiClient.patch('/tenants/branding/', formData, {
                headers: { 'Content-Type': 'multipart/form-data' },
            });
            return data;
        },
        onSuccess: () => qc.invalidateQueries({ queryKey: ['tenant-branding'] }),
    });
};

// ─── Shared style tokens ────────────────────────────────────────────────────

const cardStyle: React.CSSProperties = {
    background: 'white',
    borderRadius: '20px',
    padding: '28px 32px',
    border: '1px solid #e2e8f0',
    boxShadow: '0 1px 3px rgba(0,0,0,0.04), 0 8px 24px rgba(0,0,0,0.02)',
};

const labelStyle: React.CSSProperties = {
    display: 'block',
    fontSize: '11px',
    fontWeight: 700,
    color: '#64748b',
    textTransform: 'uppercase',
    letterSpacing: '0.6px',
    marginBottom: '8px',
};

const inputStyle: React.CSSProperties = {
    width: '100%',
    padding: '10px 14px',
    border: '1.5px solid #e2e8f0',
    borderRadius: '12px',
    background: '#f8fafc',
    color: '#0f172a',
    fontSize: '14px',
    fontFamily: 'inherit',
    outline: 'none',
    transition: 'border-color 0.2s, box-shadow 0.2s',
    boxSizing: 'border-box',
};

// ─── Reusable input ─────────────────────────────────────────────────────────

function Field({
    label, value, onChange, placeholder, icon: Icon, type = 'text', multiline = false,
}: {
    label: string;
    value: string;
    onChange: (v: string) => void;
    placeholder?: string;
    icon?: React.ElementType;
    type?: string;
    multiline?: boolean;
}) {
    const shared: React.CSSProperties = {
        ...inputStyle,
        paddingLeft: Icon ? '38px' : '14px',
    };

    const handleFocus = (e: React.FocusEvent<HTMLInputElement | HTMLTextAreaElement>) => {
        e.target.style.borderColor = '#6366f1';
        e.target.style.boxShadow = '0 0 0 3px rgba(99,102,241,0.1)';
    };

    const handleBlur = (e: React.FocusEvent<HTMLInputElement | HTMLTextAreaElement>) => {
        e.target.style.borderColor = '#e2e8f0';
        e.target.style.boxShadow = 'none';
    };

    return (
        <div style={{ marginBottom: '16px' }}>
            <label style={labelStyle}>
                {label}
            </label>
            <div style={{ position: 'relative' }}>
                {Icon && (
                    <Icon size={16} style={{
                        position: 'absolute', left: '12px', top: multiline ? '12px' : '50%',
                        transform: multiline ? undefined : 'translateY(-50%)',
                        color: '#94a3b8', pointerEvents: 'none',
                    }} />
                )}
                {multiline ? (
                    <textarea
                        value={value}
                        onChange={e => onChange(e.target.value)}
                        placeholder={placeholder}
                        rows={3}
                        style={{ ...shared, resize: 'vertical' }}
                        onFocus={handleFocus}
                        onBlur={handleBlur}
                    />
                ) : (
                    <input
                        type={type}
                        value={value}
                        onChange={e => onChange(e.target.value)}
                        placeholder={placeholder}
                        style={shared}
                        onFocus={handleFocus}
                        onBlur={handleBlur}
                    />
                )}
            </div>
        </div>
    );
}

// ─── Section header with gradient icon badge ────────────────────────────────

function SectionHeader({ icon: Icon, title, color }: {
    icon: React.ElementType;
    title: string;
    color: string;
}) {
    return (
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '14px' }}>
            <div style={{
                width: '32px', height: '32px', borderRadius: '10px',
                background: `linear-gradient(135deg, ${color}, ${color}dd)`,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                boxShadow: `0 3px 8px ${color}33`,
            }}>
                <Icon size={16} color="white" />
            </div>
            <h2 style={{ fontSize: '16px', fontWeight: 700, margin: 0, color: '#0f172a' }}>
                {title}
            </h2>
        </div>
    );
}

// ─── Component ──────────────────────────────────────────────────────────────

export default function BrandingSettings() {
    const { data: branding, isLoading } = useTenantBranding();
    const updateMutation = useUpdateBranding();
    const fileInputRef = useRef<HTMLInputElement>(null);

    const [form, setForm] = useState<BrandingData>({
        name: '', tagline: '', logo: null,
        address: '', city: '', state: '', country: '', postal_code: '',
        phone: '', email: '', website: '',
    });
    const [logoPreview, setLogoPreview] = useState<string | null>(null);
    const [logoFile, setLogoFile] = useState<File | null>(null);
    const [removeLogo, setRemoveLogo] = useState(false);
    const [saveMsg, setSaveMsg] = useState<string | null>(null);
    const [saveErr, setSaveErr] = useState<string | null>(null);

    useEffect(() => {
        if (!branding) return;
        setForm(branding);
        setLogoPreview(branding.logo);
    }, [branding]);

    const set = (field: keyof BrandingData) => (value: string) =>
        setForm(prev => ({ ...prev, [field]: value }));

    const handleLogoSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;
        if (file.size > 2 * 1024 * 1024) {
            setSaveErr('Logo must be under 2 MB.');
            return;
        }
        setLogoFile(file);
        setRemoveLogo(false);
        setLogoPreview(URL.createObjectURL(file));
    };

    const handleRemoveLogo = () => {
        setLogoFile(null);
        setRemoveLogo(true);
        setLogoPreview(null);
        if (fileInputRef.current) fileInputRef.current.value = '';
    };

    const handleSave = async () => {
        setSaveMsg(null);
        setSaveErr(null);
        const fd = new FormData();
        fd.append('name', form.name);
        fd.append('tagline', form.tagline);
        fd.append('address', form.address);
        fd.append('city', form.city);
        fd.append('state', form.state);
        fd.append('country', form.country);
        fd.append('postal_code', form.postal_code);
        fd.append('phone', form.phone);
        fd.append('email', form.email);
        fd.append('website', form.website);

        if (logoFile) fd.append('logo', logoFile);
        else if (removeLogo) fd.append('remove_logo', 'true');

        try {
            await updateMutation.mutateAsync(fd);
            setLogoFile(null);
            setRemoveLogo(false);
            setSaveMsg('Branding saved successfully.');
            setTimeout(() => setSaveMsg(null), 3000);
        } catch {
            setSaveErr('Failed to save branding. Please try again.');
        }
    };

    if (isLoading) return <LoadingScreen message="Loading branding settings..." />;

    return (
        <SettingsLayout
            title="Branding & Company Info"
            breadcrumb="Branding"
            icon={<Building size={22} color="white" />}
            gradient="linear-gradient(135deg, #f59e0b, #d97706)"
            gradientShadow="rgba(245, 158, 11, 0.25)"
            subtitle="Organisation name, logo, and contact details that appear on invoices, reports, and documents."
        >
            {/* Status messages */}
            {saveMsg && (
                <div style={{
                    display: 'flex', alignItems: 'center', gap: '10px',
                    padding: '12px 18px', background: 'rgba(16,185,129,0.08)',
                    color: '#059669', borderRadius: '16px', marginBottom: '24px',
                    fontSize: '14px', fontWeight: 600,
                    border: '1px solid rgba(16,185,129,0.15)',
                }}>
                    <CheckCircle size={18} /> {saveMsg}
                </div>
            )}
            {saveErr && (
                <div style={{
                    display: 'flex', alignItems: 'center', gap: '10px',
                    padding: '12px 18px', background: 'rgba(239,68,68,0.06)',
                    color: '#dc2626', borderRadius: '16px', marginBottom: '24px',
                    fontSize: '14px', fontWeight: 600,
                    border: '1px solid rgba(239,68,68,0.12)',
                }}>
                    <AlertTriangle size={18} /> {saveErr}
                </div>
            )}

            {/* ── Section: Brand Identity ─────────────────────────── */}
            <div style={{ marginBottom: '28px' }}>
                <SectionHeader icon={Image} title="Brand Identity" color="#f59e0b" />
                <div style={cardStyle}>

                    {/* Logo upload */}
                    <div style={{ marginBottom: '20px' }}>
                        <label style={labelStyle}>
                            Organisation Logo
                        </label>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                            {/* Preview */}
                            <div style={{
                                width: '84px', height: '84px', borderRadius: '16px',
                                border: '2px dashed #cbd5e1',
                                display: 'flex', alignItems: 'center', justifyContent: 'center',
                                overflow: 'hidden', background: '#f8fafc', flexShrink: 0,
                                transition: 'border-color 0.2s',
                            }}>
                                {logoPreview ? (
                                    <img src={logoPreview} alt="Logo" style={{ width: '100%', height: '100%', objectFit: 'contain' }} />
                                ) : (
                                    <Building size={28} style={{ color: '#cbd5e1' }} />
                                )}
                            </div>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                                <input ref={fileInputRef} type="file" accept="image/*" onChange={handleLogoSelect} style={{ display: 'none' }} />
                                <button
                                    onClick={() => fileInputRef.current?.click()}
                                    style={{
                                        display: 'inline-flex', alignItems: 'center', gap: '6px',
                                        padding: '8px 16px', border: '1.5px solid #e2e8f0',
                                        borderRadius: '12px', background: 'white',
                                        color: '#0f172a', fontSize: '13px',
                                        fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit',
                                        transition: 'border-color 0.2s, box-shadow 0.2s',
                                    }}
                                    onMouseEnter={e => {
                                        e.currentTarget.style.borderColor = '#6366f1';
                                        e.currentTarget.style.boxShadow = '0 0 0 3px rgba(99,102,241,0.08)';
                                    }}
                                    onMouseLeave={e => {
                                        e.currentTarget.style.borderColor = '#e2e8f0';
                                        e.currentTarget.style.boxShadow = 'none';
                                    }}
                                >
                                    <Upload size={14} /> Upload Logo
                                </button>
                                {logoPreview && (
                                    <button
                                        onClick={handleRemoveLogo}
                                        style={{
                                            display: 'inline-flex', alignItems: 'center', gap: '6px',
                                            padding: '8px 16px', border: 'none', borderRadius: '12px',
                                            background: 'rgba(239,68,68,0.08)', color: '#ef4444',
                                            fontSize: '12px', fontWeight: 600, cursor: 'pointer',
                                            fontFamily: 'inherit', transition: 'background 0.2s',
                                        }}
                                        onMouseEnter={e => e.currentTarget.style.background = 'rgba(239,68,68,0.14)'}
                                        onMouseLeave={e => e.currentTarget.style.background = 'rgba(239,68,68,0.08)'}
                                    >
                                        <Trash2 size={13} /> Remove
                                    </button>
                                )}
                                <span style={{ fontSize: '12px', color: '#94a3b8' }}>
                                    PNG, JPG, or SVG. Max 2 MB.
                                </span>
                            </div>
                        </div>
                    </div>

                    <Field label="Organisation Name" value={form.name} onChange={set('name')} placeholder="e.g. DTSG Holdings" icon={Building} />
                    <Field label="Tagline / Slogan" value={form.tagline} onChange={set('tagline')} placeholder="e.g. Building the future" />
                </div>
            </div>

            {/* ── Section: Contact Information ──────────────────── */}
            <div style={{ marginBottom: '28px' }}>
                <SectionHeader icon={Phone} title="Contact Information" color="#6366f1" />
                <div style={cardStyle}>
                    <Field label="Phone Number" value={form.phone} onChange={set('phone')} placeholder="+234 800 000 0000" icon={Phone} type="tel" />
                    <Field label="Email Address" value={form.email} onChange={set('email')} placeholder="info@company.com" icon={Mail} type="email" />
                    <Field label="Website" value={form.website} onChange={set('website')} placeholder="https://company.com" icon={Globe} type="url" />
                </div>
            </div>

            {/* ── Section: Address ──────────────────────────────── */}
            <div style={{ marginBottom: '28px' }}>
                <SectionHeader icon={MapPin} title="Address" color="#10b981" />
                <div style={cardStyle}>
                    <Field label="Street Address" value={form.address} onChange={set('address')} placeholder="123 Business Avenue" icon={MapPin} multiline />
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 16px' }}>
                        <Field label="City" value={form.city} onChange={set('city')} placeholder="Lagos" />
                        <Field label="State / Province" value={form.state} onChange={set('state')} placeholder="Lagos" />
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 16px' }}>
                        <Field label="Country" value={form.country} onChange={set('country')} placeholder="Nigeria" />
                        <Field label="Postal / ZIP Code" value={form.postal_code} onChange={set('postal_code')} placeholder="100001" />
                    </div>
                </div>
            </div>

            {/* ── Save button ───────────────────────────────────── */}
            <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                <button
                    onClick={handleSave}
                    disabled={updateMutation.isPending}
                    style={{
                        display: 'inline-flex', alignItems: 'center', gap: '8px',
                        padding: '12px 32px', border: 'none', borderRadius: '12px',
                        background: 'linear-gradient(135deg, #f59e0b, #d97706)',
                        color: 'white', fontSize: '14px', fontWeight: 700,
                        cursor: updateMutation.isPending ? 'not-allowed' : 'pointer',
                        fontFamily: 'inherit', letterSpacing: '0.3px',
                        opacity: updateMutation.isPending ? 0.7 : 1,
                        boxShadow: '0 4px 12px rgba(245,158,11,0.3)',
                        transition: 'transform 0.15s, box-shadow 0.15s',
                    }}
                    onMouseEnter={e => {
                        if (!updateMutation.isPending) {
                            e.currentTarget.style.transform = 'translateY(-1px)';
                            e.currentTarget.style.boxShadow = '0 6px 20px rgba(245,158,11,0.35)';
                        }
                    }}
                    onMouseLeave={e => {
                        e.currentTarget.style.transform = 'translateY(0)';
                        e.currentTarget.style.boxShadow = '0 4px 12px rgba(245,158,11,0.3)';
                    }}
                >
                    {updateMutation.isPending ? 'Saving...' : 'Save Changes'}
                </button>
            </div>
        </SettingsLayout>
    );
}
