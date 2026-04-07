import { useEffect, useState, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '../../api/client';
import Sidebar from '../../components/Sidebar';
import BackButton from '../../components/BackButton';
import LoadingScreen from '../../components/common/LoadingScreen';
import {
    Building, CheckCircle, AlertTriangle, Upload, Trash2,
    Phone, Mail, Globe, MapPin, Image,
} from 'lucide-react';
import '../accounting/styles/glassmorphism.css';

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
        width: '100%',
        padding: '0.625rem 0.75rem',
        paddingLeft: Icon ? '2.25rem' : '0.75rem',
        border: '1px solid var(--color-border)',
        borderRadius: '8px',
        background: 'var(--color-surface)',
        color: 'var(--color-text)',
        fontSize: 'var(--text-sm)',
        fontFamily: 'inherit',
        outline: 'none',
        transition: 'border-color 0.2s',
    };

    return (
        <div style={{ marginBottom: '1rem' }}>
            <label style={{
                display: 'block', fontSize: 'var(--text-xs)', fontWeight: 600,
                color: 'var(--color-text-muted)', marginBottom: '0.35rem',
                textTransform: 'uppercase', letterSpacing: '0.5px',
            }}>
                {label}
            </label>
            <div style={{ position: 'relative' }}>
                {Icon && (
                    <Icon size={16} style={{
                        position: 'absolute', left: '0.65rem', top: multiline ? '0.7rem' : '50%',
                        transform: multiline ? undefined : 'translateY(-50%)',
                        color: 'var(--color-text-muted)', pointerEvents: 'none',
                    }} />
                )}
                {multiline ? (
                    <textarea
                        value={value}
                        onChange={e => onChange(e.target.value)}
                        placeholder={placeholder}
                        rows={3}
                        style={{ ...shared, resize: 'vertical' }}
                        onFocus={e => e.target.style.borderColor = 'var(--color-primary)'}
                        onBlur={e => e.target.style.borderColor = 'var(--color-border)'}
                    />
                ) : (
                    <input
                        type={type}
                        value={value}
                        onChange={e => onChange(e.target.value)}
                        placeholder={placeholder}
                        style={shared}
                        onFocus={e => e.target.style.borderColor = 'var(--color-primary)'}
                        onBlur={e => e.target.style.borderColor = 'var(--color-border)'}
                    />
                )}
            </div>
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
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <div style={{ flex: 1, marginLeft: '260px', minHeight: '100vh', background: 'var(--color-background)' }}>

                {/* ── Page header */}
                <div style={{
                    padding: '1.5rem 3rem 1.25rem',
                    borderBottom: '1px solid var(--color-border)',
                    background: 'var(--color-surface)',
                }}>
                    <BackButton />
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '0.25rem', marginTop: '0.5rem' }}>
                        <Building size={22} style={{ color: 'var(--color-primary)' }} />
                        <h1 style={{ fontSize: 'var(--text-lg)', fontWeight: 700, color: 'var(--color-text)', margin: 0 }}>
                            Branding &amp; Company Info
                        </h1>
                    </div>
                    <p style={{ color: 'var(--color-text-muted)', fontSize: 'var(--text-sm)', margin: 0 }}>
                        Set your organisation name, logo, and contact details. These appear on invoices, reports, and documents.
                    </p>
                </div>

                <div style={{ padding: '2.5rem 3rem', maxWidth: '860px' }}>

                    {/* Status messages */}
                    {saveMsg && (
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.6rem 1rem', background: 'rgba(16,185,129,0.1)', color: '#10b981', borderRadius: '8px', marginBottom: '1.5rem', fontSize: 'var(--text-sm)', fontWeight: 600 }}>
                            <CheckCircle size={15} /> {saveMsg}
                        </div>
                    )}
                    {saveErr && (
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.6rem 1rem', background: 'rgba(239,68,68,0.1)', color: '#ef4444', borderRadius: '8px', marginBottom: '1.5rem', fontSize: 'var(--text-sm)', fontWeight: 600 }}>
                            <AlertTriangle size={15} /> {saveErr}
                        </div>
                    )}

                    {/* ── Section: Identity ─────────────────────────────── */}
                    <div style={{ marginBottom: '2rem' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem' }}>
                            <Image size={16} style={{ color: 'var(--color-primary)' }} />
                            <h2 style={{ fontSize: 'var(--text-base)', fontWeight: 700, margin: 0 }}>Brand Identity</h2>
                        </div>
                        <div className="card" style={{ padding: '1.25rem' }}>

                            {/* Logo upload */}
                            <div style={{ marginBottom: '1.25rem' }}>
                                <label style={{
                                    display: 'block', fontSize: 'var(--text-xs)', fontWeight: 600,
                                    color: 'var(--color-text-muted)', marginBottom: '0.5rem',
                                    textTransform: 'uppercase', letterSpacing: '0.5px',
                                }}>
                                    Organisation Logo
                                </label>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                                    {/* Preview */}
                                    <div style={{
                                        width: '80px', height: '80px', borderRadius: '12px',
                                        border: '2px dashed var(--color-border)',
                                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                                        overflow: 'hidden', background: 'var(--color-surface)', flexShrink: 0,
                                    }}>
                                        {logoPreview ? (
                                            <img src={logoPreview} alt="Logo" style={{ width: '100%', height: '100%', objectFit: 'contain' }} />
                                        ) : (
                                            <Building size={28} style={{ color: 'var(--color-text-muted)', opacity: 0.4 }} />
                                        )}
                                    </div>
                                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                                        <input ref={fileInputRef} type="file" accept="image/*" onChange={handleLogoSelect} style={{ display: 'none' }} />
                                        <button
                                            onClick={() => fileInputRef.current?.click()}
                                            style={{
                                                display: 'inline-flex', alignItems: 'center', gap: '0.4rem',
                                                padding: '0.5rem 1rem', border: '1px solid var(--color-border)',
                                                borderRadius: '8px', background: 'var(--color-surface)',
                                                color: 'var(--color-text)', fontSize: 'var(--text-sm)',
                                                fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit',
                                            }}
                                        >
                                            <Upload size={14} /> Upload Logo
                                        </button>
                                        {logoPreview && (
                                            <button
                                                onClick={handleRemoveLogo}
                                                style={{
                                                    display: 'inline-flex', alignItems: 'center', gap: '0.4rem',
                                                    padding: '0.5rem 1rem', border: 'none', borderRadius: '8px',
                                                    background: 'rgba(239,68,68,0.08)', color: '#ef4444',
                                                    fontSize: 'var(--text-xs)', fontWeight: 600, cursor: 'pointer',
                                                    fontFamily: 'inherit',
                                                }}
                                            >
                                                <Trash2 size={13} /> Remove
                                            </button>
                                        )}
                                        <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>
                                            PNG, JPG, or SVG. Max 2 MB.
                                        </span>
                                    </div>
                                </div>
                            </div>

                            <Field label="Organisation Name" value={form.name} onChange={set('name')} placeholder="e.g. DTSG Holdings" icon={Building} />
                            <Field label="Tagline / Slogan" value={form.tagline} onChange={set('tagline')} placeholder="e.g. Building the future" />
                        </div>
                    </div>

                    {/* ── Section: Contact ──────────────────────────────── */}
                    <div style={{ marginBottom: '2rem' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem' }}>
                            <Phone size={16} style={{ color: 'var(--color-primary)' }} />
                            <h2 style={{ fontSize: 'var(--text-base)', fontWeight: 700, margin: 0 }}>Contact Information</h2>
                        </div>
                        <div className="card" style={{ padding: '1.25rem' }}>
                            <Field label="Phone Number" value={form.phone} onChange={set('phone')} placeholder="+234 800 000 0000" icon={Phone} type="tel" />
                            <Field label="Email Address" value={form.email} onChange={set('email')} placeholder="info@company.com" icon={Mail} type="email" />
                            <Field label="Website" value={form.website} onChange={set('website')} placeholder="https://company.com" icon={Globe} type="url" />
                        </div>
                    </div>

                    {/* ── Section: Address ──────────────────────────────── */}
                    <div style={{ marginBottom: '2rem' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem' }}>
                            <MapPin size={16} style={{ color: 'var(--color-primary)' }} />
                            <h2 style={{ fontSize: 'var(--text-base)', fontWeight: 700, margin: 0 }}>Address</h2>
                        </div>
                        <div className="card" style={{ padding: '1.25rem' }}>
                            <Field label="Street Address" value={form.address} onChange={set('address')} placeholder="123 Business Avenue" icon={MapPin} multiline />
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 1rem' }}>
                                <Field label="City" value={form.city} onChange={set('city')} placeholder="Lagos" />
                                <Field label="State / Province" value={form.state} onChange={set('state')} placeholder="Lagos" />
                            </div>
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 1rem' }}>
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
                                display: 'inline-flex', alignItems: 'center', gap: '0.5rem',
                                padding: '0.75rem 2rem', border: 'none', borderRadius: '10px',
                                background: 'var(--color-primary)', color: 'white',
                                fontSize: 'var(--text-sm)', fontWeight: 700, cursor: 'pointer',
                                fontFamily: 'inherit', letterSpacing: '0.3px',
                                opacity: updateMutation.isPending ? 0.7 : 1,
                            }}
                        >
                            {updateMutation.isPending ? 'Saving...' : 'Save Changes'}
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
}
