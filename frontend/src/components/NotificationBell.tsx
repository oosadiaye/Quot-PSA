/**
 * Notification Bell — Quot PSE
 *
 * Shows unread notification count badge in sidebar header.
 * Dropdown lists recent notifications with mark-as-read.
 * Polls every 30 seconds for new notifications.
 */
import { useState, useEffect, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Bell, Check, CheckCheck, ExternalLink, X } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import apiClient from '../api/client';
import { useIsMobile } from '../design';

const CATEGORY_COLORS: Record<string, string> = {
    WARRANT: '#166534',
    BUDGET: '#1e40af',
    PAYMENT: '#6b21a8',
    APPROVAL: '#c2410c',
    REVENUE: '#0e7490',
    SYSTEM: '#64748b',
    PERIOD: '#b45309',
    PROCUREMENT: '#0369a1',
};

interface NotificationItem {
    id: number;
    category: string;
    priority: string;
    title: string;
    message: string;
    action_url: string;
    is_read: boolean;
    created_at: string;
}

const timeAgo = (iso: string): string => {
    const diff = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return 'just now';
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    return `${Math.floor(hrs / 24)}d ago`;
};

export default function NotificationBell() {
    const [open, setOpen] = useState(false);
    const ref = useRef<HTMLDivElement>(null);
    const navigate = useNavigate();
    const qc = useQueryClient();
    const isMobile = useIsMobile();

    // Close on outside click (desktop only — mobile uses scrim)
    useEffect(() => {
        if (isMobile) return;
        const handler = (e: MouseEvent) => {
            if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
        };
        document.addEventListener('mousedown', handler);
        return () => document.removeEventListener('mousedown', handler);
    }, [isMobile]);

    // Close on Escape
    useEffect(() => {
        if (!open) return;
        const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, [open]);

    // Lock body scroll when bottom sheet is open on mobile
    useEffect(() => {
        if (isMobile && open) {
            const prev = document.body.style.overflow;
            document.body.style.overflow = 'hidden';
            return () => { document.body.style.overflow = prev; };
        }
    }, [isMobile, open]);

    // Poll unread count every 30s
    const { data: countData } = useQuery({
        queryKey: ['notification-count'],
        queryFn: async () => {
            const res = await apiClient.get('/core/notifications/unread_count/');
            return res.data as { unread_count: number };
        },
        refetchInterval: 30_000,
        staleTime: 10_000,
    });

    // Fetch notifications when dropdown opens
    const { data: notifications } = useQuery({
        queryKey: ['notifications-list'],
        queryFn: async () => {
            const res = await apiClient.get('/core/notifications/', { params: { page_size: 15 } });
            const d = res.data;
            return (Array.isArray(d) ? d : d.results || []) as NotificationItem[];
        },
        enabled: open,
        staleTime: 5_000,
    });

    const markRead = useMutation({
        mutationFn: (id: number) => apiClient.post(`/core/notifications/${id}/read/`),
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['notification-count'] });
            qc.invalidateQueries({ queryKey: ['notifications-list'] });
        },
    });

    const markAllRead = useMutation({
        mutationFn: () => apiClient.post('/core/notifications/mark_all_read/'),
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['notification-count'] });
            qc.invalidateQueries({ queryKey: ['notifications-list'] });
        },
    });

    const unread = countData?.unread_count || 0;

    const handleClick = (n: NotificationItem) => {
        if (!n.is_read) markRead.mutate(n.id);
        if (n.action_url) {
            navigate(n.action_url);
            setOpen(false);
        }
    };

    return (
        <div ref={ref} style={{ position: 'relative' }}>
            {/* Bell button */}
            <button
                onClick={() => setOpen(!open)}
                style={{
                    background: 'none', border: 'none', cursor: 'pointer',
                    color: 'rgba(255,255,255,0.7)', padding: 6, position: 'relative',
                }}
            >
                <Bell size={18} />
                {unread > 0 && (
                    <span style={{
                        position: 'absolute', top: 2, right: 2,
                        background: '#ef4444', color: '#fff', fontSize: 9, fontWeight: 700,
                        borderRadius: '50%', width: 16, height: 16,
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                    }}>
                        {unread > 9 ? '9+' : unread}
                    </span>
                )}
            </button>

            {/* Mobile scrim */}
            {open && isMobile && (
                <div
                    onClick={() => setOpen(false)}
                    style={{ position: 'fixed', inset: 0, background: 'rgba(15,23,89,0.45)', zIndex: 199 }}
                />
            )}

            {/* Dropdown / Bottom sheet */}
            {open && (
                <div style={isMobile ? {
                    // Mobile: full-width bottom sheet
                    position: 'fixed', left: 0, right: 0, bottom: 0, zIndex: 200,
                    width: '100%',
                    background: '#1e293b', border: '1px solid #334155',
                    borderRadius: '16px 16px 0 0',
                    boxShadow: '0 -12px 32px rgba(0,0,0,0.4)',
                    maxHeight: '75vh', display: 'flex', flexDirection: 'column',
                    animation: 'slide-up 220ms cubic-bezier(0.16, 1, 0.3, 1)',
                    paddingBottom: 'env(safe-area-inset-bottom, 0)',
                } : {
                    // Desktop: anchored dropdown
                    position: 'absolute', top: '100%', right: -80, zIndex: 100,
                    width: 340, marginTop: 6,
                    background: '#1e293b', border: '1px solid #334155',
                    borderRadius: 10, boxShadow: '0 12px 32px rgba(0,0,0,0.4)',
                    maxHeight: 420, display: 'flex', flexDirection: 'column',
                }}>
                    {/* Header */}
                    <div style={{
                        padding: isMobile ? '14px 18px' : '10px 14px',
                        borderBottom: '1px solid #334155',
                        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    }}>
                        <span style={{ color: '#fff', fontWeight: 700, fontSize: isMobile ? 15 : 13 }}>
                            Notifications {unread > 0 && `(${unread})`}
                        </span>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                            {unread > 0 && (
                                <button
                                    onClick={() => markAllRead.mutate()}
                                    style={{
                                        background: 'none', border: 'none', cursor: 'pointer',
                                        color: '#60a5fa', fontSize: 12, fontWeight: 600,
                                        display: 'flex', alignItems: 'center', gap: 4,
                                    }}
                                >
                                    <CheckCheck size={13} /> Mark all read
                                </button>
                            )}
                            {isMobile && (
                                <button
                                    onClick={() => setOpen(false)}
                                    aria-label="Close"
                                    style={{
                                        background: 'rgba(255,255,255,0.08)', border: 'none', cursor: 'pointer',
                                        color: '#fff', borderRadius: 6, padding: 4,
                                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                                    }}
                                >
                                    <X size={16} />
                                </button>
                            )}
                        </div>
                    </div>

                    {/* List */}
                    <div style={{ overflowY: 'auto', flex: 1 }}>
                        {(!notifications || notifications.length === 0) ? (
                            <div style={{ padding: 24, textAlign: 'center', color: '#64748b', fontSize: 12 }}>
                                No notifications yet
                            </div>
                        ) : (
                            notifications.map(n => (
                                <button
                                    key={n.id}
                                    onClick={() => handleClick(n)}
                                    style={{
                                        width: '100%', padding: '10px 14px', border: 'none',
                                        background: n.is_read ? 'transparent' : 'rgba(59,130,246,0.08)',
                                        cursor: 'pointer', textAlign: 'left',
                                        borderBottom: '1px solid rgba(255,255,255,0.05)',
                                        display: 'flex', gap: 10,
                                    }}
                                >
                                    {/* Unread dot */}
                                    <div style={{ paddingTop: 4, width: 8, flexShrink: 0 }}>
                                        {!n.is_read && (
                                            <div style={{ width: 6, height: 6, borderRadius: '50%', background: '#3b82f6' }} />
                                        )}
                                    </div>
                                    <div style={{ flex: 1, minWidth: 0 }}>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2 }}>
                                            <span style={{
                                                fontSize: 8, fontWeight: 700, textTransform: 'uppercase',
                                                padding: '1px 5px', borderRadius: 3,
                                                background: `${CATEGORY_COLORS[n.category] || '#64748b'}22`,
                                                color: CATEGORY_COLORS[n.category] || '#64748b',
                                            }}>
                                                {n.category}
                                            </span>
                                            <span style={{ fontSize: 10, color: '#64748b' }}>{timeAgo(n.created_at)}</span>
                                            {n.action_url && <ExternalLink size={9} color="#64748b" />}
                                        </div>
                                        <div style={{
                                            fontSize: 12, fontWeight: n.is_read ? 400 : 600,
                                            color: n.is_read ? '#94a3b8' : '#fff',
                                            whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                                        }}>
                                            {n.title}
                                        </div>
                                        <div style={{
                                            fontSize: 11, color: '#64748b', marginTop: 2,
                                            whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                                        }}>
                                            {n.message.split('\n')[0]}
                                        </div>
                                    </div>
                                    {!n.is_read && (
                                        <button
                                            onClick={e => { e.stopPropagation(); markRead.mutate(n.id); }}
                                            title="Mark as read"
                                            style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#64748b', padding: 4, flexShrink: 0 }}
                                        >
                                            <Check size={12} />
                                        </button>
                                    )}
                                </button>
                            ))
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}
