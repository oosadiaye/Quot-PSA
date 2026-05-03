import { useState, useEffect } from 'react';
import { useDialog } from '../hooks/useDialog';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
    User, Lock, Activity, Eye, EyeOff, CheckCircle, XCircle,
    Monitor, Smartphone, Globe, LogOut, RefreshCw, Save,
    Shield, Clock, MapPin, AlertTriangle, Mail,
} from 'lucide-react';
import apiClient from '../api/client';
import Sidebar from '../components/Sidebar';
import BackButton from '../components/BackButton';

// ── Types ──────────────────────────────────────────────────────────────

interface UserProfile {
    id: number;
    username: string;
    email: string;
    first_name: string;
    last_name: string;
    is_active: boolean;
    date_joined: string;
}

interface Session {
    id: number;
    ip_address: string;
    user_agent: string;
    created_at: string;
    last_activity: string;
    is_current: boolean;
}

interface LoginEntry {
    ip_address: string;
    user_agent: string;
    attempted_at: string;
    was_successful: boolean;
}

// ── Helpers ────────────────────────────────────────────────────────────

const formatDate = (iso: string) => {
    try {
        return new Date(iso).toLocaleString(undefined, {
            dateStyle: 'medium', timeStyle: 'short',
        });
    } catch { return iso; }
};

const getDeviceIcon = (ua: string) => {
    if (!ua) return Globe;
    const lower = ua.toLowerCase();
    if (lower.includes('mobile') || lower.includes('android') || lower.includes('iphone')) return Smartphone;
    if (lower.includes('mozilla') || lower.includes('chrome') || lower.includes('safari')) return Monitor;
    return Globe;
};

const parseBrowser = (ua: string) => {
    if (!ua) return 'Unknown browser';
    if (ua.includes('Chrome') && !ua.includes('Edg')) return 'Chrome';
    if (ua.includes('Firefox')) return 'Firefox';
    if (ua.includes('Safari') && !ua.includes('Chrome')) return 'Safari';
    if (ua.includes('Edg')) return 'Edge';
    if (ua.includes('Opera') || ua.includes('OPR')) return 'Opera';
    return 'Browser';
};

const parseOS = (ua: string) => {
    if (!ua) return '';
    if (ua.includes('Windows')) return 'Windows';
    if (ua.includes('Mac OS')) return 'macOS';
    if (ua.includes('Android')) return 'Android';
    if (ua.includes('iPhone') || ua.includes('iPad')) return 'iOS';
    if (ua.includes('Linux')) return 'Linux';
    return '';
};

// ── Password rules (same as Register/ResetPassword) ───────────────────

const getPasswordRules = (pw: string) => [
    { label: 'At least 8 characters', pass: pw.length >= 8 },
    { label: 'One uppercase letter',  pass: /[A-Z]/.test(pw) },
    { label: 'One number',            pass: /[0-9]/.test(pw) },
    { label: 'One special character', pass: /[^A-Za-z0-9]/.test(pw) },
];

const getStrength = (pw: string) => {
    const score = getPasswordRules(pw).filter((r) => r.pass).length;
    if (!pw || score === 0) return { bars: 0, label: '', color: '' };
    if (score <= 1) return { bars: 1, label: 'Weak',   color: '#ef4444' };
    if (score === 2) return { bars: 2, label: 'Fair',   color: '#f59e0b' };
    if (score === 3) return { bars: 3, label: 'Good',   color: '#22c55e' };
    return              { bars: 4, label: 'Strong', color: '#22c55e' };
};

// ── Shared style tokens ────────────────────────────────────────────────

const inputCss: React.CSSProperties = {
    width: '100%', padding: '11px 14px',
    border: '1.5px solid #e2e8f0', borderRadius: '10px',
    fontSize: '14px', background: '#f8fafc',
    color: '#1e293b', fontFamily: 'inherit', outline: 'none',
    transition: 'all 0.2s',
};

const labelCss: React.CSSProperties = {
    display: 'block', fontSize: '12px', fontWeight: 600,
    color: '#475569', marginBottom: '6px',
    textTransform: 'uppercase', letterSpacing: '0.5px',
};

const onFocus = (e: React.FocusEvent<HTMLInputElement>) => {
    e.target.style.borderColor = '#2471a3';
    e.target.style.background  = 'white';
    e.target.style.boxShadow   = '0 0 0 3px rgba(36,113,163,0.1)';
};
const onBlur = (e: React.FocusEvent<HTMLInputElement>) => {
    e.target.style.borderColor = '#e2e8f0';
    e.target.style.background  = '#f8fafc';
    e.target.style.boxShadow   = 'none';
};

// ── Sub-components ─────────────────────────────────────────────────────

/** Inline success/error toast that auto-dismisses after 4 s */
const Toast = ({ msg, type }: { msg: string; type: 'success' | 'error' }) => (
    <div style={{
        padding: '10px 16px', borderRadius: '10px', fontSize: '13px',
        display: 'flex', alignItems: 'center', gap: '8px',
        background: type === 'success' ? '#f0fdf4' : '#fef2f2',
        color: type === 'success' ? '#16a34a' : '#dc2626',
        border: `1px solid ${type === 'success' ? '#bbf7d0' : '#fecaca'}`,
        marginBottom: '16px',
    }}>
        {type === 'success' ? <CheckCircle size={14} /> : <XCircle size={14} />}
        {msg}
    </div>
);

// ──────────────────────────────────────────────────────────────────────
//  Main component
// ──────────────────────────────────────────────────────────────────────

type Tab = 'profile' | 'security' | 'activity';

const AccountProfile = () => {
    const { showAlert } = useDialog();
    const qc = useQueryClient();
    const [activeTab, setActiveTab] = useState<Tab>('profile');

    // ── Profile tab state ────────────────────────────────────────────
    const [firstName, setFirstName] = useState('');
    const [lastName, setLastName]   = useState('');
    const [email, setEmail]         = useState('');
    const [profileMsg, setProfileMsg] = useState<{ text: string; type: 'success' | 'error' } | null>(null);

    // ── Security tab — password ──────────────────────────────────────
    const [currentPw,  setCurrentPw]  = useState('');
    const [newPw,      setNewPw]      = useState('');
    const [confirmPw,  setConfirmPw]  = useState('');
    const [showCurrent, setShowCurrent] = useState(false);
    const [showNew,     setShowNew]     = useState(false);
    const [showConfirm, setShowConfirm] = useState(false);
    const [pwMsg, setPwMsg] = useState<{ text: string; type: 'success' | 'error' } | null>(null);

    // ── Queries ──────────────────────────────────────────────────────
    const { data: profile, isLoading: profileLoading } = useQuery<UserProfile>({
        queryKey: ['me'],
        queryFn: async () => (await apiClient.get('/core/users/me/')).data,
        staleTime: 30_000,
    });

    const { data: sessionsData, isLoading: sessionsLoading, refetch: refetchSessions } = useQuery<{ sessions: Session[] }>({
        queryKey: ['active-sessions'],
        queryFn: async () => (await apiClient.get('/core/auth/sessions/')).data,
        enabled: activeTab === 'security',
    });

    const { data: historyData, isLoading: historyLoading } = useQuery<{ login_history: LoginEntry[] }>({
        queryKey: ['login-history'],
        queryFn: async () => (await apiClient.get('/core/auth/login-history/')).data,
        enabled: activeTab === 'activity',
    });

    // Pre-fill profile fields when data arrives
    useEffect(() => {
        if (profile) {
            setFirstName(profile.first_name || '');
            setLastName(profile.last_name  || '');
            setEmail(profile.email         || '');
        }
    }, [profile]);

    // Auto-clear toasts after 4 s
    useEffect(() => {
        if (!profileMsg) return;
        const t = setTimeout(() => setProfileMsg(null), 4000);
        return () => clearTimeout(t);
    }, [profileMsg]);
    useEffect(() => {
        if (!pwMsg) return;
        const t = setTimeout(() => setPwMsg(null), 4000);
        return () => clearTimeout(t);
    }, [pwMsg]);

    // ── Mutations ────────────────────────────────────────────────────
    const updateProfileMutation = useMutation({
        mutationFn: (data: Record<string, string>) =>
            apiClient.patch('/core/users/update_profile/', data),
        onSuccess: (res) => {
            qc.invalidateQueries({ queryKey: ['me'] });
            // Keep localStorage in sync
            try {
                const stored = JSON.parse(localStorage.getItem('user') || '{}');
                localStorage.setItem('user', JSON.stringify({ ...stored, ...res.data }));
            } catch { /* ignore */ }
            setProfileMsg({ text: 'Profile updated successfully.', type: 'success' });
        },
        onError: (err: any) => {
            setProfileMsg({
                text: err.response?.data?.error || 'Failed to update profile.',
                type: 'error',
            });
        },
    });

    const changePwMutation = useMutation({
        mutationFn: (data: { old_password: string; new_password: string }) =>
            apiClient.post('/core/users/change_password/', data),
        onSuccess: () => {
            setCurrentPw(''); setNewPw(''); setConfirmPw('');
            setPwMsg({ text: 'Password changed successfully. All other sessions have been signed out.', type: 'success' });
        },
        onError: (err: any) => {
            const data = err.response?.data;
            // Backend returns either { error: "..." } or DRF per-field errors
            // like { old_password: ["Current password is incorrect"] }.
            const fieldError =
                data && typeof data === 'object'
                    ? Object.values(data).flat().find((v) => typeof v === 'string')
                    : undefined;
            setPwMsg({
                text: data?.error || (fieldError as string) || 'Failed to change password.',
                type: 'error',
            });
        },
    });

    const revokeSessionMutation = useMutation({
        mutationFn: (id: number) => apiClient.post('/core/auth/sessions/revoke/', { session_id: id }),
        onSuccess: () => refetchSessions(),
        onError: (err: any) => showAlert(err.response?.data?.error || 'Could not revoke session.'),
    });

    const revokeAllMutation = useMutation({
        mutationFn: () => apiClient.post('/core/auth/sessions/revoke-all/'),
        onSuccess: () => refetchSessions(),
    });

    // ── Derived ──────────────────────────────────────────────────────
    const strength = getStrength(newPw);
    const rules    = getPasswordRules(newPw);
    const pwMatch  = confirmPw.length > 0 && newPw === confirmPw;
    const pwMismatch = confirmPw.length > 0 && newPw !== confirmPw;

    const sessions = sessionsData?.sessions ?? [];
    const history  = historyData?.login_history ?? [];

    // ── Handlers ─────────────────────────────────────────────────────
    const handleProfileSave = () => {
        if (!email.trim()) {
            setProfileMsg({ text: 'Email cannot be empty.', type: 'error' });
            return;
        }
        updateProfileMutation.mutate({ first_name: firstName, last_name: lastName, email });
    };

    const handleChangePw = () => {
        if (!currentPw || !newPw || !confirmPw) {
            setPwMsg({ text: 'All password fields are required.', type: 'error' });
            return;
        }
        if (newPw !== confirmPw) {
            setPwMsg({ text: "New passwords don't match.", type: 'error' });
            return;
        }
        if (rules.filter((r) => r.pass).length < 3) {
            setPwMsg({ text: 'New password is too weak — please meet at least 3 of the 4 requirements.', type: 'error' });
            return;
        }
        changePwMutation.mutate({
            old_password: currentPw,
            new_password: newPw,
        });
    };

    // ── Tab definitions ───────────────────────────────────────────────
    const tabs: { key: Tab; label: string; icon: typeof User }[] = [
        { key: 'profile',  label: 'Profile',  icon: User     },
        { key: 'security', label: 'Security', icon: Lock     },
        { key: 'activity', label: 'Activity', icon: Activity },
    ];

    const tabBtn = (t: typeof tabs[0]) => {
        const active = activeTab === t.key;
        return (
            <button key={t.key} onClick={() => setActiveTab(t.key)}
                style={{
                    display: 'flex', alignItems: 'center', gap: '8px',
                    padding: '10px 20px', border: 'none', cursor: 'pointer',
                    background: 'none', fontFamily: 'inherit',
                    fontSize: '14px', fontWeight: active ? 600 : 500,
                    color: active ? '#2471a3' : '#64748b',
                    borderBottom: `2px solid ${active ? '#2471a3' : 'transparent'}`,
                    transition: 'all 0.15s',
                }}
            >
                <t.icon size={15} /> {t.label}
            </button>
        );
    };

    if (profileLoading) {
        return (
            <div style={{ display: 'flex' }}>
                <Sidebar />
                <main style={{ flex: 1, marginLeft: '260px', padding: '40px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <div style={{ color: '#64748b', fontSize: '15px' }}>Loading account…</div>
                </main>
            </div>
        );
    }

    const avatarInitials = [profile?.first_name?.[0], profile?.last_name?.[0]]
        .filter(Boolean).join('').toUpperCase() || profile?.username?.[0]?.toUpperCase() || 'U';

    // ──────────────────────────────────────────────────────────────────
    //  Render
    // ──────────────────────────────────────────────────────────────────
    return (
        <div style={{ display: 'flex', background: '#f1f5f9', minHeight: '100vh' }}>
            <Sidebar />

            <main style={{ flex: 1, marginLeft: '260px', padding: '40px' }}>
                {/* Page header */}
                <div style={{ marginBottom: '28px' }}>
                    <BackButton />
                    <h1 style={{ fontSize: '22px', fontWeight: 700, color: '#0f172a', margin: '12px 0 4px' }}>
                        Account Settings
                    </h1>
                    <p style={{ fontSize: '14px', color: '#64748b', margin: 0 }}>
                        Manage your profile, password, and active sessions.
                    </p>
                </div>

                <div style={{ maxWidth: '760px' }}>
                    {/* Avatar card */}
                    <div style={{
                        background: 'white', borderRadius: '16px', padding: '24px',
                        border: '1px solid #e2e8f0', marginBottom: '24px',
                        display: 'flex', alignItems: 'center', gap: '20px',
                    }}>
                        <div style={{
                            width: '64px', height: '64px', borderRadius: '50%',
                            background: 'linear-gradient(135deg, #0f3460, #2471a3)',
                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                            fontSize: '22px', fontWeight: 700, color: 'white', flexShrink: 0,
                        }}>
                            {avatarInitials}
                        </div>
                        <div>
                            <div style={{ fontSize: '18px', fontWeight: 700, color: '#0f172a' }}>
                                {[profile?.first_name, profile?.last_name].filter(Boolean).join(' ') || profile?.username}
                            </div>
                            <div style={{ fontSize: '13px', color: '#64748b', marginTop: '2px' }}>
                                @{profile?.username}
                            </div>
                            <div style={{ fontSize: '12px', color: '#94a3b8', marginTop: '4px', display: 'flex', alignItems: 'center', gap: '4px' }}>
                                <Clock size={11} />
                                Member since {profile?.date_joined ? formatDate(profile.date_joined) : '—'}
                            </div>
                        </div>
                        <div style={{ marginLeft: 'auto' }}>
                            <span style={{
                                padding: '4px 12px', borderRadius: '20px', fontSize: '12px', fontWeight: 600,
                                background: '#f0fdf4', color: '#16a34a', border: '1px solid #bbf7d0',
                            }}>
                                Active
                            </span>
                        </div>
                    </div>

                    {/* Tab bar */}
                    <div style={{
                        background: 'white', borderRadius: '16px', border: '1px solid #e2e8f0',
                        overflow: 'hidden',
                    }}>
                        <div style={{
                            display: 'flex', borderBottom: '1px solid #e2e8f0',
                            padding: '0 8px',
                        }}>
                            {tabs.map(tabBtn)}
                        </div>

                        <div style={{ padding: '28px' }}>

                            {/* ── Profile tab ──────────────────────────── */}
                            {activeTab === 'profile' && (
                                <div>
                                    <h2 style={{ fontSize: '16px', fontWeight: 700, color: '#0f172a', marginBottom: '20px' }}>
                                        Personal Information
                                    </h2>

                                    {profileMsg && <Toast msg={profileMsg.text} type={profileMsg.type} />}

                                    <div style={{ display: 'flex', gap: '16px', marginBottom: '18px' }}>
                                        <div style={{ flex: 1 }}>
                                            <label style={labelCss}>First Name</label>
                                            <input value={firstName} onChange={(e) => setFirstName(e.target.value)}
                                                placeholder="First name" style={inputCss}
                                                onFocus={onFocus} onBlur={onBlur} />
                                        </div>
                                        <div style={{ flex: 1 }}>
                                            <label style={labelCss}>Last Name</label>
                                            <input value={lastName} onChange={(e) => setLastName(e.target.value)}
                                                placeholder="Last name" style={inputCss}
                                                onFocus={onFocus} onBlur={onBlur} />
                                        </div>
                                    </div>

                                    <div style={{ marginBottom: '18px' }}>
                                        <label style={labelCss}>Username</label>
                                        <input value={profile?.username || ''} disabled
                                            style={{ ...inputCss, background: '#f1f5f9', color: '#94a3b8', cursor: 'not-allowed' }} />
                                        <p style={{ fontSize: '11px', color: '#94a3b8', marginTop: '4px' }}>
                                            Username cannot be changed after registration.
                                        </p>
                                    </div>

                                    <div style={{ marginBottom: '24px' }}>
                                        <label style={labelCss}>Email Address</label>
                                        <div style={{ position: 'relative' }}>
                                            <Mail size={14} style={{
                                                position: 'absolute', left: '14px', top: '50%',
                                                transform: 'translateY(-50%)', color: '#94a3b8',
                                            }} />
                                            <input value={email} onChange={(e) => setEmail(e.target.value)}
                                                type="email" placeholder="name@company.com"
                                                style={{ ...inputCss, paddingLeft: '36px' }}
                                                onFocus={onFocus} onBlur={onBlur} />
                                        </div>
                                    </div>

                                    <button
                                        onClick={handleProfileSave}
                                        disabled={updateProfileMutation.isPending}
                                        style={{
                                            display: 'flex', alignItems: 'center', gap: '8px',
                                            padding: '11px 24px',
                                            background: 'linear-gradient(135deg, #0f3460, #2471a3)',
                                            color: 'white', border: 'none', borderRadius: '10px',
                                            fontSize: '14px', fontWeight: 600, fontFamily: 'inherit',
                                            cursor: updateProfileMutation.isPending ? 'wait' : 'pointer',
                                            boxShadow: '0 4px 12px rgba(15,52,96,0.25)',
                                        }}
                                    >
                                        <Save size={14} />
                                        {updateProfileMutation.isPending ? 'Saving…' : 'Save Changes'}
                                    </button>
                                </div>
                            )}

                            {/* ── Security tab ─────────────────────────── */}
                            {activeTab === 'security' && (
                                <div>
                                    {/* Change Password */}
                                    <h2 style={{ fontSize: '16px', fontWeight: 700, color: '#0f172a', marginBottom: '20px' }}>
                                        Change Password
                                    </h2>

                                    {pwMsg && <Toast msg={pwMsg.text} type={pwMsg.type} />}

                                    <div style={{ marginBottom: '16px' }}>
                                        <label style={labelCss}>Current Password</label>
                                        <div style={{ position: 'relative' }}>
                                            <input type={showCurrent ? 'text' : 'password'}
                                                value={currentPw} onChange={(e) => setCurrentPw(e.target.value)}
                                                placeholder="Enter current password"
                                                style={{ ...inputCss, paddingRight: '42px' }}
                                                onFocus={onFocus} onBlur={onBlur} />
                                            <button type="button" onClick={() => setShowCurrent(!showCurrent)}
                                                style={{ position: 'absolute', right: '12px', top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', color: '#94a3b8', padding: '4px', display: 'flex' }}>
                                                {showCurrent ? <EyeOff size={16} /> : <Eye size={16} />}
                                            </button>
                                        </div>
                                    </div>

                                    <div style={{ marginBottom: '16px' }}>
                                        <label style={labelCss}>New Password</label>
                                        <div style={{ position: 'relative' }}>
                                            <input type={showNew ? 'text' : 'password'}
                                                value={newPw} onChange={(e) => setNewPw(e.target.value)}
                                                placeholder="Enter new password"
                                                style={{ ...inputCss, paddingRight: '42px' }}
                                                onFocus={onFocus} onBlur={onBlur} />
                                            <button type="button" onClick={() => setShowNew(!showNew)}
                                                style={{ position: 'absolute', right: '12px', top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', color: '#94a3b8', padding: '4px', display: 'flex' }}>
                                                {showNew ? <EyeOff size={16} /> : <Eye size={16} />}
                                            </button>
                                        </div>
                                        {newPw && (
                                            <>
                                                <div style={{ marginTop: '8px', display: 'flex', gap: '4px', alignItems: 'center' }}>
                                                    {[1, 2, 3, 4].map(i => (
                                                        <div key={i} style={{ height: '4px', flex: 1, borderRadius: '2px', background: i <= strength.bars ? strength.color : '#e2e8f0', transition: 'background 0.3s' }} />
                                                    ))}
                                                    <span style={{ fontSize: '11px', color: strength.color, fontWeight: 600, marginLeft: '8px', minWidth: '36px' }}>{strength.label}</span>
                                                </div>
                                                <div style={{ marginTop: '8px', display: 'flex', flexWrap: 'wrap', gap: '4px 16px' }}>
                                                    {rules.map((r) => (
                                                        <span key={r.label} style={{ fontSize: '11px', display: 'flex', alignItems: 'center', gap: '4px', color: r.pass ? '#22c55e' : '#94a3b8' }}>
                                                            {r.pass ? <CheckCircle size={11} /> : <XCircle size={11} />}
                                                            {r.label}
                                                        </span>
                                                    ))}
                                                </div>
                                            </>
                                        )}
                                    </div>

                                    <div style={{ marginBottom: '24px' }}>
                                        <label style={labelCss}>Confirm New Password</label>
                                        <div style={{ position: 'relative' }}>
                                            <input type={showConfirm ? 'text' : 'password'}
                                                value={confirmPw} onChange={(e) => setConfirmPw(e.target.value)}
                                                placeholder="Confirm new password"
                                                style={{
                                                    ...inputCss, paddingRight: '42px',
                                                    borderColor: confirmPw.length > 0 ? (pwMatch ? '#22c55e' : '#ef4444') : undefined,
                                                }}
                                                onFocus={onFocus} onBlur={onBlur} />
                                            <button type="button" onClick={() => setShowConfirm(!showConfirm)}
                                                style={{ position: 'absolute', right: '12px', top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', color: '#94a3b8', padding: '4px', display: 'flex' }}>
                                                {showConfirm ? <EyeOff size={16} /> : <Eye size={16} />}
                                            </button>
                                        </div>
                                        {pwMismatch && <p style={{ fontSize: '12px', color: '#ef4444', marginTop: '4px', display: 'flex', alignItems: 'center', gap: '4px' }}><XCircle size={12} /> Passwords don't match.</p>}
                                        {pwMatch    && <p style={{ fontSize: '12px', color: '#22c55e', marginTop: '4px', display: 'flex', alignItems: 'center', gap: '4px' }}><CheckCircle size={12} /> Passwords match.</p>}
                                    </div>

                                    <button
                                        onClick={handleChangePw}
                                        disabled={changePwMutation.isPending}
                                        style={{
                                            display: 'flex', alignItems: 'center', gap: '8px',
                                            padding: '11px 24px',
                                            background: 'linear-gradient(135deg, #0f3460, #2471a3)',
                                            color: 'white', border: 'none', borderRadius: '10px',
                                            fontSize: '14px', fontWeight: 600, fontFamily: 'inherit',
                                            cursor: changePwMutation.isPending ? 'wait' : 'pointer',
                                            boxShadow: '0 4px 12px rgba(15,52,96,0.25)',
                                        }}
                                    >
                                        <Lock size={14} />
                                        {changePwMutation.isPending ? 'Updating…' : 'Update Password'}
                                    </button>

                                    {/* Active Sessions */}
                                    <div style={{ marginTop: '36px', paddingTop: '28px', borderTop: '1px solid #e2e8f0' }}>
                                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                                            <h2 style={{ fontSize: '16px', fontWeight: 700, color: '#0f172a', margin: 0 }}>
                                                Active Sessions
                                            </h2>
                                            <div style={{ display: 'flex', gap: '8px' }}>
                                                <button onClick={() => refetchSessions()}
                                                    style={{ background: 'none', border: '1px solid #e2e8f0', borderRadius: '8px', padding: '6px 12px', cursor: 'pointer', fontSize: '12px', color: '#64748b', display: 'flex', alignItems: 'center', gap: '4px', fontFamily: 'inherit' }}>
                                                    <RefreshCw size={12} /> Refresh
                                                </button>
                                                {sessions.filter(s => !s.is_current).length > 0 && (
                                                    <button
                                                        onClick={() => revokeAllMutation.mutate()}
                                                        disabled={revokeAllMutation.isPending}
                                                        style={{ background: '#fef2f2', border: '1px solid #fecaca', borderRadius: '8px', padding: '6px 12px', cursor: 'pointer', fontSize: '12px', color: '#ef4444', display: 'flex', alignItems: 'center', gap: '4px', fontFamily: 'inherit', fontWeight: 600 }}>
                                                        <LogOut size={12} /> Sign Out All Others
                                                    </button>
                                                )}
                                            </div>
                                        </div>

                                        {sessionsLoading ? (
                                            <p style={{ color: '#94a3b8', fontSize: '13px' }}>Loading sessions…</p>
                                        ) : sessions.length === 0 ? (
                                            <p style={{ color: '#94a3b8', fontSize: '13px' }}>No active sessions found.</p>
                                        ) : (
                                            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                                                {sessions.map((s) => {
                                                    const DeviceIcon = getDeviceIcon(s.user_agent);
                                                    const browser = parseBrowser(s.user_agent);
                                                    const os = parseOS(s.user_agent);
                                                    return (
                                                        <div key={s.id} style={{
                                                            display: 'flex', alignItems: 'center', gap: '14px',
                                                            padding: '14px 16px', borderRadius: '12px',
                                                            border: s.is_current ? '1.5px solid #bfdbfe' : '1px solid #f1f5f9',
                                                            background: s.is_current ? '#eff6ff' : '#f8fafc',
                                                        }}>
                                                            <div style={{
                                                                width: '40px', height: '40px', borderRadius: '10px',
                                                                background: s.is_current ? '#dbeafe' : '#e2e8f0',
                                                                display: 'flex', alignItems: 'center', justifyContent: 'center',
                                                                flexShrink: 0,
                                                            }}>
                                                                <DeviceIcon size={18} style={{ color: s.is_current ? '#2471a3' : '#64748b' }} />
                                                            </div>
                                                            <div style={{ flex: 1, minWidth: 0 }}>
                                                                <div style={{ fontSize: '13px', fontWeight: 600, color: '#0f172a', display: 'flex', alignItems: 'center', gap: '8px' }}>
                                                                    {browser}{os ? ` · ${os}` : ''}
                                                                    {s.is_current && (
                                                                        <span style={{ fontSize: '11px', fontWeight: 600, color: '#2471a3', background: '#dbeafe', padding: '2px 8px', borderRadius: '10px' }}>
                                                                            Current
                                                                        </span>
                                                                    )}
                                                                </div>
                                                                <div style={{ fontSize: '11px', color: '#94a3b8', marginTop: '3px', display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
                                                                    <span style={{ display: 'flex', alignItems: 'center', gap: '3px' }}><MapPin size={10} />{s.ip_address || 'Unknown IP'}</span>
                                                                    <span style={{ display: 'flex', alignItems: 'center', gap: '3px' }}><Clock size={10} />Last active {formatDate(s.last_activity)}</span>
                                                                </div>
                                                            </div>
                                                            {!s.is_current && (
                                                                <button
                                                                    onClick={() => revokeSessionMutation.mutate(s.id)}
                                                                    disabled={revokeSessionMutation.isPending}
                                                                    title="Sign out this session"
                                                                    style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#ef4444', padding: '6px', borderRadius: '6px', display: 'flex', alignItems: 'center' }}
                                                                    onMouseOver={(e) => (e.currentTarget.style.background = '#fef2f2')}
                                                                    onMouseOut={(e) => (e.currentTarget.style.background = 'none')}
                                                                >
                                                                    <LogOut size={15} />
                                                                </button>
                                                            )}
                                                        </div>
                                                    );
                                                })}
                                            </div>
                                        )}
                                    </div>
                                </div>
                            )}

                            {/* ── Activity tab ─────────────────────────── */}
                            {activeTab === 'activity' && (
                                <div>
                                    <h2 style={{ fontSize: '16px', fontWeight: 700, color: '#0f172a', marginBottom: '20px' }}>
                                        Login History
                                        <span style={{ fontSize: '12px', fontWeight: 400, color: '#94a3b8', marginLeft: '8px' }}>
                                            Last 20 attempts
                                        </span>
                                    </h2>

                                    {historyLoading ? (
                                        <p style={{ color: '#94a3b8', fontSize: '13px' }}>Loading history…</p>
                                    ) : history.length === 0 ? (
                                        <p style={{ color: '#94a3b8', fontSize: '13px' }}>No login history available.</p>
                                    ) : (
                                        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                                            {history.map((entry, i) => {
                                                const DeviceIcon = getDeviceIcon(entry.user_agent);
                                                return (
                                                    <div key={i} style={{
                                                        display: 'flex', alignItems: 'center', gap: '14px',
                                                        padding: '12px 16px', borderRadius: '10px',
                                                        border: '1px solid #f1f5f9', background: '#f8fafc',
                                                    }}>
                                                        <div style={{
                                                            width: '34px', height: '34px', borderRadius: '8px',
                                                            background: entry.was_successful ? '#f0fdf4' : '#fef2f2',
                                                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                                                            flexShrink: 0,
                                                        }}>
                                                            {entry.was_successful
                                                                ? <CheckCircle size={16} style={{ color: '#22c55e' }} />
                                                                : <AlertTriangle size={16} style={{ color: '#ef4444' }} />}
                                                        </div>
                                                        <div style={{ flex: 1, minWidth: 0 }}>
                                                            <div style={{ fontSize: '13px', fontWeight: 600, color: '#0f172a', display: 'flex', alignItems: 'center', gap: '8px' }}>
                                                                <DeviceIcon size={12} style={{ color: '#64748b' }} />
                                                                {parseBrowser(entry.user_agent)}
                                                                {parseOS(entry.user_agent) && ` · ${parseOS(entry.user_agent)}`}
                                                                <span style={{
                                                                    fontSize: '11px', fontWeight: 600,
                                                                    color: entry.was_successful ? '#16a34a' : '#dc2626',
                                                                    background: entry.was_successful ? '#f0fdf4' : '#fef2f2',
                                                                    padding: '1px 7px', borderRadius: '8px',
                                                                }}>
                                                                    {entry.was_successful ? 'Success' : 'Failed'}
                                                                </span>
                                                            </div>
                                                            <div style={{ fontSize: '11px', color: '#94a3b8', marginTop: '3px', display: 'flex', gap: '12px' }}>
                                                                <span style={{ display: 'flex', alignItems: 'center', gap: '3px' }}><MapPin size={10} />{entry.ip_address || 'Unknown'}</span>
                                                                <span style={{ display: 'flex', alignItems: 'center', gap: '3px' }}><Clock size={10} />{formatDate(entry.attempted_at)}</span>
                                                            </div>
                                                        </div>
                                                    </div>
                                                );
                                            })}
                                        </div>
                                    )}

                                    <div style={{ marginTop: '20px', padding: '14px', background: '#fffbeb', borderRadius: '10px', border: '1px solid #fde68a', display: 'flex', gap: '10px' }}>
                                        <Shield size={15} style={{ color: '#d97706', flexShrink: 0, marginTop: '1px' }} />
                                        <p style={{ fontSize: '12px', color: '#92400e', margin: 0, lineHeight: 1.6 }}>
                                            If you see any failed login attempts you don't recognise, change your password immediately and contact your administrator.
                                        </p>
                                    </div>
                                </div>
                            )}

                        </div>
                    </div>
                </div>
            </main>
        </div>
    );
};

export default AccountProfile;
