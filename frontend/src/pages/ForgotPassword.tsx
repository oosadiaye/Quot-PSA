import React, { useState } from 'react';
import { Mail, ArrowLeft, KeyRound } from 'lucide-react';
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
        <KeyRound size={32} style={{ color: 'rgba(255,255,255,0.7)', marginBottom: 16 }} />
        <div style={{ fontSize: 15, color: 'rgba(255,255,255,0.85)', lineHeight: 1.7 }}>
            Don't worry — it happens to the best of us. Enter your email and we'll send you instructions
            to reset your password.
        </div>
    </div>
);

const ForgotPassword: React.FC = () => {
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
        } catch (err: unknown) {
            const msg =
                (err as { response?: { data?: { error?: string } } })?.response?.data?.error ||
                'Something went wrong. Please try again.';
            setError(msg);
        } finally {
            setLoading(false);
        }
    };

    return (
        <AuthShell
            title="Forgot Password"
            subtitle={sent ? 'Check your inbox for the reset link' : 'Enter your email to receive a reset link'}
            brandTagline={'Secure Account Recovery\nWe\u2019ll help you get back in'}
            brandContent={<BrandCallout />}
            footer={
                <a
                    href="/login"
                    style={{
                        color: '#64748b',
                        textDecoration: 'none',
                        fontSize: 14,
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: 6,
                    }}
                >
                    <ArrowLeft size={16} /> Back to Sign In
                </a>
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

            {sent ? (
                <div
                    style={{
                        padding: 24,
                        background: '#f0fdf4',
                        borderRadius: 12,
                        border: '1px solid #bbf7d0',
                        textAlign: 'center',
                    }}
                >
                    <Mail size={32} style={{ color: '#22c55e', margin: '0 auto 12px', display: 'block' }} />
                    <div style={{ fontSize: 15, color: '#16a34a', fontWeight: 500, lineHeight: 1.6 }}>
                        If an account with that email exists, we've sent a password reset link.
                    </div>
                </div>
            ) : (
                <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 22 }}>
                    <FormField
                        label="Email Address"
                        name="email"
                        type="email"
                        placeholder="Enter your email"
                        value={email}
                        onChange={setEmail}
                        autoComplete="email"
                        required
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
                        {loading ? 'Sending...' : 'Send Reset Link'}
                    </button>
                </form>
            )}
        </AuthShell>
    );
};

export default ForgotPassword;
