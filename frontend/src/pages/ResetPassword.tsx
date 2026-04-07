import React, { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Eye, EyeOff, CheckCircle, XCircle, Shield, Lock } from 'lucide-react';
import apiClient from '../api/client';
import { useBranding } from '../context/BrandingContext';

const ResetPassword = () => {
    const { branding } = useBranding();
    const [searchParams] = useSearchParams();
    const uid = searchParams.get('uid') || '';
    const token = searchParams.get('token') || '';

    const [password, setPassword] = useState('');
    const [passwordConfirm, setPasswordConfirm] = useState('');
    const [showPassword, setShowPassword] = useState(false);
    const [showPasswordConfirm, setShowPasswordConfirm] = useState(false);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const [success, setSuccess] = useState(false);

    // ── Password strength helpers ──────────────────────────────────
    const passwordRules = [
        { label: 'At least 8 characters', pass: password.length >= 8 },
        { label: 'One uppercase letter',  pass: /[A-Z]/.test(password) },
        { label: 'One number',            pass: /[0-9]/.test(password) },
        { label: 'One special character', pass: /[^A-Za-z0-9]/.test(password) },
    ];

    const getPasswordStrength = () => {
        if (!password) return { bars: 0, label: '', color: '' };
        const score = passwordRules.filter((r) => r.pass).length;
        if (score <= 1) return { bars: 1, label: 'Weak',   color: '#ef4444' };
        if (score === 2) return { bars: 2, label: 'Fair',   color: '#f59e0b' };
        if (score === 3) return { bars: 3, label: 'Good',   color: '#22c55e' };
        return              { bars: 4, label: 'Strong', color: '#22c55e' };
    };

    const strength = getPasswordStrength();
    const passwordsMatch = passwordConfirm.length > 0 && password === passwordConfirm;

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError('');

        if (password !== passwordConfirm) {
            setError("Passwords don't match.");
            return;
        }
        if (passwordRules.filter((r) => r.pass).length < 3) {
            setError('Password is too weak. Please meet at least 3 of the 4 requirements shown.');
            return;
        }

        setLoading(true);
        try {
            await apiClient.post('/core/auth/reset-password/', {
                uid, token,
                new_password: password,
                new_password_confirm: passwordConfirm,
            });
            setSuccess(true);
        } catch (err: any) {
            setError(err.response?.data?.error || 'Failed to reset password. The link may have expired.');
        } finally {
            setLoading(false);
        }
    };

    const inputStyle: React.CSSProperties = {
        width: '100%', padding: '14px 46px 14px 16px', border: '2.5px solid #e2e8f0',
        borderRadius: '12px', fontSize: '15px', background: '#f8fafc',
        outline: 'none', color: '#1e293b', fontFamily: 'inherit', transition: 'all 0.2s'
    };

    const handleFocus = (e: React.FocusEvent<HTMLInputElement>) => {
        e.target.style.borderColor = '#2e35a0';
        e.target.style.background = 'white';
        e.target.style.boxShadow = '0 0 0 3px rgba(74,82,192,0.1)';
    };
    const handleBlur = (e: React.FocusEvent<HTMLInputElement>) => {
        e.target.style.borderColor = '#e2e8f0';
        e.target.style.background = '#f8fafc';
        e.target.style.boxShadow = 'none';
    };

    // Brand panel shared across all states
    const BrandPanel = () => (
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
                Create Your New Password<br/>Keep your account secure
            </div>

            <div style={{
                background: 'rgba(255,255,255,0.08)', borderRadius: '16px',
                padding: '28px', maxWidth: '360px', textAlign: 'center'
            }}>
                <Lock size={32} style={{ color: 'rgba(255,255,255,0.7)', marginBottom: '16px' }} />
                <div style={{ fontSize: '15px', color: 'rgba(255,255,255,0.85)', lineHeight: 1.7 }}>
                    Choose a strong password that you haven't used before. Your password should be at least 8 characters with a mix of letters, numbers, and symbols.
                </div>
            </div>
        </div>
    );

    if (!uid || !token) {
        return (
            <div style={{ display: 'flex', minHeight: '100vh' }}>
                <BrandPanel />
                <div style={{
                    width: '50%', minHeight: '100vh', display: 'flex',
                    flexDirection: 'column', justifyContent: 'center', alignItems: 'center',
                    padding: '60px', background: 'white'
                }}>
                    <div style={{ width: '100%', maxWidth: '420px', textAlign: 'center' }}>
                        <h2 style={{ fontSize: '28px', fontWeight: 700, color: '#0f172a', marginBottom: '12px' }}>
                            Invalid Link
                        </h2>
                        <p style={{ fontSize: '15px', color: '#64748b', marginBottom: '24px' }}>
                            This password reset link is invalid or incomplete.
                        </p>
                        <a href="/forgot-password" style={{
                            display: 'inline-block', padding: '14px 28px',
                            background: 'linear-gradient(135deg, #242a88, #2e35a0)',
                            color: 'white', borderRadius: '12px', textDecoration: 'none',
                            fontWeight: 600, fontSize: '15px',
                            boxShadow: '0 4px 14px rgba(36,42,136,0.3)'
                        }}>
                            Request a new link
                        </a>
                    </div>
                </div>
            </div>
        );
    }

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
                            Reset Password
                        </h2>
                        <p style={{ fontSize: '15px', color: '#64748b' }}>Enter your new password below</p>
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

                    {success ? (
                        <div style={{
                            padding: '24px', background: '#f0fdf4', borderRadius: '12px',
                            border: '1px solid #bbf7d0', textAlign: 'center'
                        }}>
                            <CheckCircle size={32} style={{ color: '#22c55e', margin: '0 auto 12px', display: 'block' }} />
                            <div style={{ fontSize: '16px', color: '#16a34a', fontWeight: 600, marginBottom: '16px' }}>
                                Password has been reset successfully!
                            </div>
                            <a href="/login" style={{
                                display: 'inline-block', padding: '12px 28px',
                                background: 'linear-gradient(135deg, #242a88, #2e35a0)',
                                color: 'white', borderRadius: '10px', textDecoration: 'none',
                                fontWeight: 600, fontSize: '15px',
                                boxShadow: '0 4px 14px rgba(36,42,136,0.3)'
                            }}>
                                Sign In
                            </a>
                        </div>
                    ) : (
                        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '22px' }}>
                            <div>
                                <label style={{
                                    display: 'block', fontSize: '13px', fontWeight: 600, color: '#475569',
                                    marginBottom: '8px', textTransform: 'uppercase', letterSpacing: '0.5px'
                                }}>
                                    New Password
                                </label>
                                <div style={{ position: 'relative' }}>
                                    <input type={showPassword ? 'text' : 'password'}
                                        placeholder="Enter new password" value={password}
                                        onChange={(e) => setPassword(e.target.value)} required
                                        style={inputStyle} onFocus={handleFocus} onBlur={handleBlur} />
                                    <button type="button" onClick={() => setShowPassword(!showPassword)}
                                        style={{
                                            position: 'absolute', right: '14px', top: '50%', transform: 'translateY(-50%)',
                                            background: 'none', border: 'none', cursor: 'pointer', padding: '4px',
                                            color: '#94a3b8', display: 'flex', alignItems: 'center'
                                        }}>
                                        {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                                    </button>
                                </div>

                                {/* Strength bar + per-rule checklist */}
                                {password && (
                                    <>
                                        <div style={{ marginTop: '8px', display: 'flex', gap: '4px', alignItems: 'center' }}>
                                            {[1, 2, 3, 4].map(i => (
                                                <div key={i} style={{
                                                    height: '4px', flex: 1, borderRadius: '2px',
                                                    background: i <= strength.bars ? strength.color : '#e2e8f0',
                                                    transition: 'background 0.3s',
                                                }} />
                                            ))}
                                            <span style={{ fontSize: '11px', color: strength.color, fontWeight: 600, marginLeft: '8px', minWidth: '36px' }}>
                                                {strength.label}
                                            </span>
                                        </div>
                                        <div style={{ marginTop: '8px', display: 'flex', flexWrap: 'wrap', gap: '4px 16px' }}>
                                            {passwordRules.map((rule) => (
                                                <span key={rule.label} style={{
                                                    fontSize: '11px', display: 'flex', alignItems: 'center', gap: '4px',
                                                    color: rule.pass ? '#22c55e' : '#94a3b8'
                                                }}>
                                                    {rule.pass ? <CheckCircle size={11} /> : <XCircle size={11} />}
                                                    {rule.label}
                                                </span>
                                            ))}
                                        </div>
                                    </>
                                )}
                            </div>

                            <div>
                                <label style={{
                                    display: 'block', fontSize: '13px', fontWeight: 600, color: '#475569',
                                    marginBottom: '8px', textTransform: 'uppercase', letterSpacing: '0.5px'
                                }}>
                                    Confirm New Password
                                </label>
                                <div style={{ position: 'relative' }}>
                                    <input type={showPasswordConfirm ? 'text' : 'password'}
                                        placeholder="Confirm new password" value={passwordConfirm}
                                        onChange={(e) => setPasswordConfirm(e.target.value)} required
                                        style={{
                                            ...inputStyle,
                                            borderColor: passwordConfirm.length > 0
                                                ? (passwordsMatch ? '#22c55e' : '#ef4444')
                                                : undefined,
                                        }}
                                        onFocus={handleFocus} onBlur={handleBlur} />
                                    <button type="button" onClick={() => setShowPasswordConfirm(!showPasswordConfirm)}
                                        style={{
                                            position: 'absolute', right: '14px', top: '50%', transform: 'translateY(-50%)',
                                            background: 'none', border: 'none', cursor: 'pointer', padding: '4px',
                                            color: '#94a3b8', display: 'flex', alignItems: 'center'
                                        }}>
                                        {showPasswordConfirm ? <EyeOff size={18} /> : <Eye size={18} />}
                                    </button>
                                </div>
                                {passwordConfirm.length > 0 && !passwordsMatch && (
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

                            <button type="submit" disabled={loading}
                                style={{
                                    width: '100%', padding: '15px',
                                    background: 'linear-gradient(135deg, #242a88, #2e35a0)',
                                    color: 'white', border: 'none', borderRadius: '12px',
                                    fontSize: '16px', fontWeight: 600, fontFamily: 'inherit',
                                    cursor: loading ? 'wait' : 'pointer', letterSpacing: '0.3px',
                                    boxShadow: '0 4px 14px rgba(36,42,136,0.3)'
                                }}>
                                {loading ? 'Resetting...' : 'Reset Password'}
                            </button>
                        </form>
                    )}

                    <div style={{
                        display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px',
                        marginTop: '32px', fontSize: '12px', color: '#94a3b8'
                    }}>
                        <Shield size={14} />
                        256-bit SSL encrypted &middot; SOC 2 Compliant
                    </div>
                </div>
            </div>
        </div>
    );
};

export default ResetPassword;
