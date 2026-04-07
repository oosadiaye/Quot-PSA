import React, { useState } from 'react';
import { Mail, ArrowLeft, Shield, KeyRound } from 'lucide-react';
import apiClient from '../api/client';
import { useBranding } from '../context/BrandingContext';

const ForgotPassword = () => {
    const { branding } = useBranding();
    const [email, setEmail] = useState('');
    const [loading, setLoading] = useState(false);
    const [sent, setSent] = useState(false);
    const [error, setError] = useState('');

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError('');
        setLoading(true);
        try {
            await apiClient.post('/core/auth/forgot-password/', { email });
            setSent(true);
        } catch (err: any) {
            setError(err.response?.data?.error || 'Something went wrong. Please try again.');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div style={{ display: 'flex', minHeight: '100vh' }}>
            {/* Left Branding Panel */}
            <div style={{
                width: '50%', minHeight: '100vh',
                background: 'linear-gradient(135deg, #242a88 0%, #1e2480 40%, #2e35a0 100%)',
                display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center',
                padding: '60px', position: 'relative', overflow: 'hidden'
            }}>
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

                <div style={{
                    width: '72px', height: '72px', background: 'white',
                    borderRadius: '18px', display: 'flex', alignItems: 'center', justifyContent: 'center',
                    marginBottom: '28px', boxShadow: '0 8px 32px rgba(0,0,0,0.15)'
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
                <div style={{ fontSize: '17px', color: 'rgba(255,255,255,0.75)', textAlign: 'center', lineHeight: 1.6, marginBottom: '56px' }}>
                    Secure Account Recovery<br/>We'll help you get back in
                </div>

                <div style={{
                    background: 'rgba(255,255,255,0.08)', borderRadius: '16px',
                    padding: '28px', maxWidth: '360px', textAlign: 'center'
                }}>
                    <KeyRound size={32} style={{ color: 'rgba(255,255,255,0.7)', marginBottom: '16px' }} />
                    <div style={{ fontSize: '15px', color: 'rgba(255,255,255,0.85)', lineHeight: 1.7 }}>
                        Don't worry, it happens to the best of us. Enter your email and we'll send you instructions to reset your password.
                    </div>
                </div>
            </div>

            {/* Right Form Panel */}
            <div style={{
                width: '50%', minHeight: '100vh', display: 'flex',
                flexDirection: 'column', justifyContent: 'center', alignItems: 'center',
                padding: '60px', background: 'white'
            }}>
                <div style={{ width: '100%', maxWidth: '420px' }}>
                    <div style={{ marginBottom: '36px' }}>
                        <h2 style={{ fontSize: '28px', fontWeight: 700, color: '#0f172a', marginBottom: '8px' }}>
                            Forgot Password
                        </h2>
                        <p style={{ fontSize: '15px', color: '#64748b' }}>
                            {sent ? 'Check your inbox for the reset link' : 'Enter your email to receive a reset link'}
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

                    {sent ? (
                        <div style={{
                            padding: '24px', background: '#f0fdf4', borderRadius: '12px',
                            border: '1px solid #bbf7d0', textAlign: 'center'
                        }}>
                            <Mail size={32} style={{ color: '#22c55e', margin: '0 auto 12px', display: 'block' }} />
                            <div style={{ fontSize: '15px', color: '#16a34a', fontWeight: 500, lineHeight: 1.6 }}>
                                If an account with that email exists, we've sent a password reset link.
                            </div>
                        </div>
                    ) : (
                        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '22px' }}>
                            <div>
                                <label style={{
                                    display: 'block', fontSize: '13px', fontWeight: 600, color: '#475569',
                                    marginBottom: '8px', textTransform: 'uppercase', letterSpacing: '0.5px'
                                }}>
                                    Email Address
                                </label>
                                <input
                                    type="email" placeholder="Enter your email" value={email}
                                    onChange={(e) => setEmail(e.target.value)} required
                                    style={{
                                        width: '100%', padding: '14px 16px', border: '1.5px solid #e2e8f0',
                                        borderRadius: '12px', fontSize: '15px', background: '#f8fafc',
                                        outline: 'none', color: '#1e293b', fontFamily: 'inherit',
                                        transition: 'all 0.2s'
                                    }}
                                    onFocus={(e) => {
                                        e.target.style.borderColor = '#2e35a0';
                                        e.target.style.background = 'white';
                                        e.target.style.boxShadow = '0 0 0 3px rgba(74,82,192,0.1)';
                                    }}
                                    onBlur={(e) => {
                                        e.target.style.borderColor = '#e2e8f0';
                                        e.target.style.background = '#f8fafc';
                                        e.target.style.boxShadow = 'none';
                                    }}
                                />
                            </div>

                            <button type="submit" disabled={loading}
                                style={{
                                    width: '100%', padding: '15px',
                                    background: 'linear-gradient(135deg, #242a88, #2e35a0)',
                                    color: 'white', border: 'none', borderRadius: '12px',
                                    fontSize: '16px', fontWeight: 600, fontFamily: 'inherit',
                                    cursor: loading ? 'wait' : 'pointer', letterSpacing: '0.3px',
                                    boxShadow: '0 4px 14px rgba(36,42,136,0.3)'
                                }}>
                                {loading ? 'Sending...' : 'Send Reset Link'}
                            </button>
                        </form>
                    )}

                    <div style={{ textAlign: 'center', marginTop: '32px' }}>
                        <a href="/login" style={{
                            color: '#64748b', textDecoration: 'none', fontSize: '14px',
                            display: 'inline-flex', alignItems: 'center', gap: '6px'
                        }}>
                            <ArrowLeft size={16} /> Back to Sign In
                        </a>
                    </div>

                    <div style={{
                        display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px',
                        marginTop: '24px', fontSize: '12px', color: '#94a3b8'
                    }}>
                        <Shield size={14} />
                        Your account is protected with enterprise-grade security
                    </div>
                </div>
            </div>
        </div>
    );
};

export default ForgotPassword;
