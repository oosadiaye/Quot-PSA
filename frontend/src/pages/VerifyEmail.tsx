import { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { CheckCircle, XCircle, Loader, Mail, Shield } from 'lucide-react';
import apiClient from '../api/client';
import { useBranding } from '../context/BrandingContext';

/**
 * Handles the /verify-email?token=... route that is linked from the
 * registration confirmation email.
 *
 * Automatically submits the token on mount.  Three visual states:
 *   • verifying  — spinner while the API call is in flight
 *   • success    — green confirmation with a "Sign In" button
 *   • error      — red error message with a "Resend email" option
 */
const VerifyEmail = () => {
    const { branding } = useBranding();
    const [searchParams] = useSearchParams();
    const token = searchParams.get('token') || '';

    type State = 'verifying' | 'success' | 'error' | 'no-token';
    const [state, setState] = useState<State>(token ? 'verifying' : 'no-token');
    const [errorMessage, setErrorMessage] = useState('');
    const [resendLoading, setResendLoading] = useState(false);
    const [resendSent, setResendSent] = useState(false);

    // Auto-verify on mount
    useEffect(() => {
        if (!token) return;
        apiClient
            .post('/core/auth/verify-email/', { token })
            .then(() => setState('success'))
            .catch((err) => {
                setErrorMessage(
                    err.response?.data?.error ||
                    'Verification failed. The link may have expired.'
                );
                setState('error');
            });
    }, [token]);

    const handleResend = async () => {
        setResendLoading(true);
        try {
            await apiClient.post('/core/auth/resend-verification/');
            setResendSent(true);
        } catch {
            // If resend fails the user is prompted to contact support
        } finally {
            setResendLoading(false);
        }
    };

    // ── Brand Panel ────────────────────────────────────────────────
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
                Email Verification<br/>Confirming your identity
            </div>

            <div style={{
                background: 'rgba(255,255,255,0.08)', borderRadius: '16px',
                padding: '28px', maxWidth: '360px', textAlign: 'center'
            }}>
                <Mail size={32} style={{ color: 'rgba(255,255,255,0.7)', marginBottom: '16px' }} />
                <div style={{ fontSize: '15px', color: 'rgba(255,255,255,0.85)', lineHeight: 1.7 }}>
                    Verifying your email address helps us keep your account secure and ensures you receive important notifications.
                </div>
            </div>
        </div>
    );

    // ── Verifying spinner ──────────────────────────────────────────
    const VerifyingContent = () => (
        <div style={{ textAlign: 'center' }}>
            <div style={{
                width: '72px', height: '72px', borderRadius: '50%',
                background: '#eff6ff',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                margin: '0 auto 24px',
            }}>
                <Loader size={32} style={{ color: '#2e35a0', animation: 'spin 1s linear infinite' }} />
            </div>
            <h2 style={{ fontSize: '24px', fontWeight: 700, color: '#0f172a', marginBottom: '8px' }}>
                Verifying your email…
            </h2>
            <p style={{ fontSize: '15px', color: '#64748b' }}>
                Please wait while we confirm your email address.
            </p>
            <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
        </div>
    );

    // ── Success state ──────────────────────────────────────────────
    const SuccessContent = () => (
        <div style={{ textAlign: 'center' }}>
            <div style={{
                width: '72px', height: '72px', borderRadius: '50%',
                background: '#f0fdf4',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                margin: '0 auto 24px',
            }}>
                <CheckCircle size={36} style={{ color: '#22c55e' }} />
            </div>
            <h2 style={{ fontSize: '24px', fontWeight: 700, color: '#0f172a', marginBottom: '8px' }}>
                Email Verified!
            </h2>
            <p style={{ fontSize: '15px', color: '#64748b', lineHeight: 1.6, marginBottom: '32px' }}>
                Your email address has been confirmed. You can now sign in and
                access all features of your account.
            </p>
            <a href="/login" style={{
                display: 'inline-block', padding: '14px 36px',
                background: 'linear-gradient(135deg, #242a88, #2e35a0)',
                color: 'white', borderRadius: '12px', textDecoration: 'none',
                fontWeight: 600, fontSize: '16px',
                boxShadow: '0 4px 14px rgba(36,42,136,0.3)',
                transition: 'opacity 0.2s',
            }}>
                Sign In to Your Account
            </a>
        </div>
    );

    // ── Error state ────────────────────────────────────────────────
    const ErrorContent = () => (
        <div style={{ textAlign: 'center' }}>
            <div style={{
                width: '72px', height: '72px', borderRadius: '50%',
                background: '#fef2f2',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                margin: '0 auto 24px',
            }}>
                <XCircle size={36} style={{ color: '#ef4444' }} />
            </div>
            <h2 style={{ fontSize: '24px', fontWeight: 700, color: '#0f172a', marginBottom: '8px' }}>
                Verification Failed
            </h2>
            <p style={{ fontSize: '15px', color: '#64748b', lineHeight: 1.6, marginBottom: '8px' }}>
                {errorMessage}
            </p>
            <p style={{ fontSize: '14px', color: '#94a3b8', marginBottom: '28px' }}>
                Verification links expire after <strong>72 hours</strong>. Please request a new one.
            </p>

            {resendSent ? (
                <div style={{
                    padding: '16px', background: '#f0fdf4', borderRadius: '12px',
                    border: '1px solid #bbf7d0', marginBottom: '20px',
                    display: 'flex', alignItems: 'center', gap: '10px', justifyContent: 'center',
                    fontSize: '14px', color: '#16a34a', fontWeight: 500,
                }}>
                    <CheckCircle size={16} />
                    A new verification email has been sent. Check your inbox.
                </div>
            ) : (
                <button
                    onClick={handleResend}
                    disabled={resendLoading}
                    style={{
                        display: 'inline-block', padding: '13px 28px',
                        background: 'linear-gradient(135deg, #242a88, #2e35a0)',
                        color: 'white', border: 'none', borderRadius: '12px',
                        fontWeight: 600, fontSize: '15px', fontFamily: 'inherit',
                        cursor: resendLoading ? 'wait' : 'pointer',
                        boxShadow: '0 4px 14px rgba(36,42,136,0.3)',
                        marginBottom: '16px', width: '100%',
                    }}
                >
                    {resendLoading ? 'Sending…' : 'Resend Verification Email'}
                </button>
            )}

            <div style={{ marginTop: '8px' }}>
                <a href="/login" style={{ fontSize: '14px', color: '#64748b', textDecoration: 'none' }}>
                    Back to Sign In
                </a>
            </div>
        </div>
    );

    // ── No token state ─────────────────────────────────────────────
    const NoTokenContent = () => (
        <div style={{ textAlign: 'center' }}>
            <div style={{
                width: '72px', height: '72px', borderRadius: '50%',
                background: '#fff7ed',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                margin: '0 auto 24px',
            }}>
                <Mail size={36} style={{ color: '#f59e0b' }} />
            </div>
            <h2 style={{ fontSize: '24px', fontWeight: 700, color: '#0f172a', marginBottom: '8px' }}>
                Invalid Verification Link
            </h2>
            <p style={{ fontSize: '15px', color: '#64748b', lineHeight: 1.6, marginBottom: '28px' }}>
                This link appears to be incomplete. Please use the link directly
                from your verification email, or request a new one after signing in.
            </p>
            <a href="/login" style={{
                display: 'inline-block', padding: '14px 28px',
                background: 'linear-gradient(135deg, #242a88, #2e35a0)',
                color: 'white', borderRadius: '12px', textDecoration: 'none',
                fontWeight: 600, fontSize: '15px',
                boxShadow: '0 4px 14px rgba(36,42,136,0.3)',
            }}>
                Go to Sign In
            </a>
        </div>
    );

    return (
        <div style={{ display: 'flex', minHeight: '100vh', fontFamily: "'Inter', sans-serif" }}>
            <BrandPanel />

            <div style={{
                width: '50%', minHeight: '100vh', display: 'flex',
                flexDirection: 'column', justifyContent: 'center', alignItems: 'center',
                padding: '60px', background: 'white'
            }}>
                <div style={{ width: '100%', maxWidth: '420px' }}>
                    {state === 'verifying'  && <VerifyingContent />}
                    {state === 'success'    && <SuccessContent />}
                    {state === 'error'      && <ErrorContent />}
                    {state === 'no-token'   && <NoTokenContent />}

                    <div style={{
                        display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px',
                        marginTop: '40px', fontSize: '12px', color: '#94a3b8'
                    }}>
                        <Shield size={14} />
                        256-bit SSL encrypted · SOC 2 Compliant
                    </div>
                </div>
            </div>
        </div>
    );
};

export default VerifyEmail;
