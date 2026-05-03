/**
 * StatusBadge — pill-shaped status indicator with semantic colour
 * mapping. Replaces the Ant-Design `<Tag>` palette with a tighter
 * theme-matched set (light-tinted pill + solid dot + bold label).
 *
 * The mapping knows common ERP status terms; unknown statuses fall
 * back to a neutral grey.
 */
import { ReactNode } from 'react';

type Tone = 'neutral' | 'info' | 'success' | 'warning' | 'danger' | 'purple' | 'gold';

interface StatusBadgeProps {
    children: ReactNode;
    tone?: Tone;
    /** Optional explicit status string — will be mapped to a tone. */
    status?: string;
    size?: 'sm' | 'md';
}

const toneStyle: Record<Tone, { bg: string; fg: string; dot: string }> = {
    neutral: { bg: '#f1f5f9', fg: '#475569', dot: '#94a3b8' },
    info:    { bg: '#eff6ff', fg: '#1d4ed8', dot: '#3b82f6' },
    success: { bg: '#f0fdf4', fg: '#15803d', dot: '#22c55e' },
    warning: { bg: '#fffbeb', fg: '#b45309', dot: '#f59e0b' },
    danger:  { bg: '#fef2f2', fg: '#b91c1c', dot: '#ef4444' },
    purple:  { bg: '#faf5ff', fg: '#6d28d9', dot: '#8b5cf6' },
    gold:    { bg: '#fefce8', fg: '#a16207', dot: '#eab308' },
};

const STATUS_TONE: Record<string, Tone> = {
    DRAFT: 'neutral',
    PENDING: 'warning',
    SUBMITTED: 'info',
    REVIEWED: 'info',
    CERTIFIER_REVIEWED: 'info',
    APPROVED: 'success',
    ACTIVE: 'success',
    IN_PROGRESS: 'info',
    COMPLETED: 'purple',
    VOUCHER_RAISED: 'purple',
    PAID: 'gold',
    SUSPENDED: 'warning',
    REJECTED: 'danger',
    TERMINATED: 'danger',
    FAILED: 'danger',
    LOCAL: 'info',
    BOARD: 'warning',
    BPP_REQUIRED: 'danger',
};

const StatusBadge = ({ children, tone, status, size = 'md' }: StatusBadgeProps) => {
    const resolvedTone: Tone = tone ?? (status ? STATUS_TONE[status.toUpperCase()] ?? 'neutral' : 'neutral');
    const s = toneStyle[resolvedTone];
    const padding = size === 'sm' ? '2px 8px' : '4px 10px';
    const fontSize = size === 'sm' ? 11 : 12;

    return (
        <span
            style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 6,
                background: s.bg,
                color: s.fg,
                padding,
                fontSize,
                fontWeight: 600,
                borderRadius: 999,
                letterSpacing: '0.2px',
                textTransform: 'uppercase',
                lineHeight: 1.4,
                border: `1px solid ${s.bg}`,
                whiteSpace: 'nowrap',
            }}
        >
            <span
                style={{
                    width: 6,
                    height: 6,
                    borderRadius: '50%',
                    background: s.dot,
                    flexShrink: 0,
                }}
            />
            {children}
        </span>
    );
};

export default StatusBadge;
