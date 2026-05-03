import React, { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Eye, EyeOff, CheckCircle, XCircle, Lock } from 'lucide-react';
import apiClient from '../api/client';
import AuthShell from '../components/auth/AuthShell';
import { FormField } from '../components/forms';

const BrandCallout: React.FC = () => (
    <div
        style={{
            background: 'rgba(255,255,255,0.08)',
            borderRadius: 16,
            padding: 28,
            maxWidth: 360,
            textAlign: 'center',
        }}
    >
        <Lock size={32} style={{ color: 'rgba(255,255,255,0.7)', marginBottom: 16 }} />
        <div style={{ fontSize: 15, color: 'rgba(255,255,255,0.85)', lineHeight: 1.7 }}>
            Choose a strong password that you haven't used before. Your password should be at least 8
            characters with a mix of letters, numbers, and symbols.
        </div>
    </div>
);

const ResetPassword: React.FC = () => {
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

    const passwordRules = [
        { label: 'At least 8 characters', pass: password.length >= 8 },
        { label: 'One uppercase letter', pass: /[A-Z]/.test(password) },
        { label: 'One number', pass: /[0-9]/.test(password) },
        { label: 'One special character', pass: /[^A-Za-z0-9]/.test(password) },
    ];

    const getStrength = () => {
        if (!password) return { bars: 0, label: '', color: '' };
        const score = passwordRules.filter((r) => r.pass).length;
        if (score <= 1) return { bars: 1, label: 'Weak', color: '#ef4444' };
        if (score === 2) return { bars: 2, label: 'Fair', color: '#f59e0b' };
        if (score === 3) return { bars: 3, label: 'Good', color: '#22c55e' };
        return { bars: 4, label: 'Strong', color: '#22c55e' };
    };

    const strength = getStrength();
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
                uid,
                token,
                new_password: password,
                new_password_confirm: passwordConfirm,
            });
            setSuccess(true);
        } catch (err: unknown) {
            const msg =
                (err as { response?: { data?: { error?: string } } })?.response?.data?.error ||
                'Failed to reset password. The link may have expired.';
            setError(msg);
        } finally {
            setLoading(false);
        }
    };

    // Invalid / missing link
    if (!uid || !token) {
        return (
            <AuthShell
                title="Invalid Link"
                subtitle="This password reset link is invalid or incomplete."
                brandTagline={'Create Your New Password\nKeep your account secure'}
                brandContent={<BrandCallout />}
                showTrustBadge={false}
            >
                <div style={{ textAlign: 'center', marginTop: 12 }}>
                    <a
                        href="/forgot-password"
                        style={{
                            display: 'inline-block',
                            padding: '14px 28px',
                            background: 'linear-gradient(135deg, #242a88, #2e35a0)',
                            color: 'white',
                            borderRadius: 12,
                            textDecoration: 'none',
                            fontWeight: 600,
                            fontSize: 15,
                            boxShadow: '0 4px 14px rgba(36,42,136,0.3)',
                        }}
                    >
                        Request a new link
                    </a>
                </div>
            </AuthShell>
        );
    }

    return (
        <AuthShell
            title="Reset Password"
            subtitle="Enter your new password below"
            brandTagline={'Create Your New Password\nKeep your account secure'}
            brandContent={<BrandCallout />}
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

            {success ? (
                <div
                    style={{
                        padding: 24,
                        background: '#f0fdf4',
                        borderRadius: 12,
                        border: '1px solid #bbf7d0',
                        textAlign: 'center',
                    }}
                >
                    <CheckCircle size={32} style={{ color: '#22c55e', margin: '0 auto 12px', display: 'block' }} />
                    <div style={{ fontSize: 16, color: '#16a34a', fontWeight: 600, marginBottom: 16 }}>
                        Password has been reset successfully!
                    </div>
                    <a
                        href="/login"
                        style={{
                            display: 'inline-block',
                            padding: '12px 28px',
                            background: 'linear-gradient(135deg, #242a88, #2e35a0)',
                            color: 'white',
                            borderRadius: 10,
                            textDecoration: 'none',
                            fontWeight: 600,
                            fontSize: 15,
                            boxShadow: '0 4px 14px rgba(36,42,136,0.3)',
                        }}
                    >
                        Sign In
                    </a>
                </div>
            ) : (
                <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 22 }}>
                    <div>
                        <FormField
                            label="New Password"
                            name="new-password"
                            type={showPassword ? 'text' : 'password'}
                            placeholder="Enter new password"
                            value={password}
                            onChange={setPassword}
                            required
                            autoComplete="new-password"
                            rightAdornment={
                                <button
                                    type="button"
                                    onClick={() => setShowPassword(!showPassword)}
                                    style={{
                                        background: 'none',
                                        border: 'none',
                                        cursor: 'pointer',
                                        padding: 4,
                                        color: '#94a3b8',
                                        display: 'flex',
                                        alignItems: 'center',
                                    }}
                                    aria-label={showPassword ? 'Hide password' : 'Show password'}
                                >
                                    {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                                </button>
                            }
                        />

                        {password && (
                            <>
                                <div style={{ marginTop: 8, display: 'flex', gap: 4, alignItems: 'center' }}>
                                    {[1, 2, 3, 4].map((i) => (
                                        <div
                                            key={i}
                                            style={{
                                                height: 4,
                                                flex: 1,
                                                borderRadius: 2,
                                                background: i <= strength.bars ? strength.color : '#e2e8f0',
                                                transition: 'background 0.3s',
                                            }}
                                        />
                                    ))}
                                    <span
                                        style={{
                                            fontSize: 11,
                                            color: strength.color,
                                            fontWeight: 600,
                                            marginLeft: 8,
                                            minWidth: 36,
                                        }}
                                    >
                                        {strength.label}
                                    </span>
                                </div>
                                <div style={{ marginTop: 8, display: 'flex', flexWrap: 'wrap', gap: '4px 16px' }}>
                                    {passwordRules.map((rule) => (
                                        <span
                                            key={rule.label}
                                            style={{
                                                fontSize: 11,
                                                display: 'flex',
                                                alignItems: 'center',
                                                gap: 4,
                                                color: rule.pass ? '#22c55e' : '#94a3b8',
                                            }}
                                        >
                                            {rule.pass ? <CheckCircle size={11} /> : <XCircle size={11} />}
                                            {rule.label}
                                        </span>
                                    ))}
                                </div>
                            </>
                        )}
                    </div>

                    <FormField
                        label="Confirm New Password"
                        name="confirm-password"
                        type={showPasswordConfirm ? 'text' : 'password'}
                        placeholder="Confirm new password"
                        value={passwordConfirm}
                        onChange={setPasswordConfirm}
                        required
                        autoComplete="new-password"
                        tone={
                            passwordConfirm.length === 0
                                ? 'default'
                                : passwordsMatch
                                    ? 'success'
                                    : 'error'
                        }
                        error={
                            passwordConfirm.length > 0 && !passwordsMatch ? "Passwords don't match" : undefined
                        }
                        helpText={passwordsMatch ? 'Passwords match' : undefined}
                        rightAdornment={
                            <button
                                type="button"
                                onClick={() => setShowPasswordConfirm(!showPasswordConfirm)}
                                style={{
                                    background: 'none',
                                    border: 'none',
                                    cursor: 'pointer',
                                    padding: 4,
                                    color: '#94a3b8',
                                    display: 'flex',
                                    alignItems: 'center',
                                }}
                                aria-label={showPasswordConfirm ? 'Hide password' : 'Show password'}
                            >
                                {showPasswordConfirm ? <EyeOff size={18} /> : <Eye size={18} />}
                            </button>
                        }
                    />

                    <button
                        type="submit"
                        disabled={loading}
                        style={{
                            width: '100%',
                            padding: 15,
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
                        }}
                    >
                        {loading ? 'Resetting...' : 'Reset Password'}
                    </button>
                </form>
            )}
        </AuthShell>
    );
};

export default ResetPassword;
