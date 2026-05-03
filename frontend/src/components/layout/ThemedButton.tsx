/**
 * ThemedButton — the brand gradient primary / bordered secondary /
 * danger / ghost variants used across every page of Quot PSE.
 *
 * Gradient is the same as PageHeader / AuthShell:
 *   linear-gradient(135deg, #242a88, #2e35a0)
 *
 * Sizes map to 32/40/48px heights.  On mobile, buttons have `min-height: 44`
 * to hit the iOS tap target.
 */
import { ReactNode, CSSProperties, MouseEvent } from 'react';

type Variant = 'primary' | 'secondary' | 'danger' | 'ghost';
type Size = 'sm' | 'md' | 'lg';

interface ThemedButtonProps {
    children: ReactNode;
    onClick?: (e: MouseEvent<HTMLButtonElement>) => void;
    type?: 'button' | 'submit' | 'reset';
    variant?: Variant;
    size?: Size;
    icon?: ReactNode;
    disabled?: boolean;
    loading?: boolean;
    fullWidth?: boolean;
    style?: CSSProperties;
    title?: string;
    'aria-label'?: string;
}

const sizeMap: Record<Size, { height: number; padX: number; fontSize: number }> = {
    sm: { height: 32, padX: 12, fontSize: 13 },
    md: { height: 40, padX: 16, fontSize: 14 },
    lg: { height: 48, padX: 20, fontSize: 15 },
};

const variantStyles = (variant: Variant, disabled: boolean): CSSProperties => {
    if (variant === 'primary') {
        return {
            background: disabled
                ? '#cbd5e1'
                : 'linear-gradient(135deg, #242a88, #2e35a0)',
            color: '#ffffff',
            border: 'none',
            boxShadow: disabled ? 'none' : '0 4px 12px rgba(36,42,136,0.25)',
        };
    }
    if (variant === 'secondary') {
        return {
            background: '#ffffff',
            color: disabled ? '#94a3b8' : '#242a88',
            border: '1px solid #cbd5e1',
            boxShadow: '0 1px 2px rgba(15,23,42,0.04)',
        };
    }
    if (variant === 'danger') {
        return {
            background: disabled ? '#fecaca' : '#dc2626',
            color: '#ffffff',
            border: 'none',
            boxShadow: disabled ? 'none' : '0 4px 12px rgba(220,38,38,0.25)',
        };
    }
    // ghost
    return {
        background: 'transparent',
        color: disabled ? '#94a3b8' : '#242a88',
        border: 'none',
    };
};

const ThemedButton = ({
    children,
    onClick,
    type = 'button',
    variant = 'primary',
    size = 'md',
    icon,
    disabled = false,
    loading = false,
    fullWidth = false,
    style,
    title,
    'aria-label': ariaLabel,
}: ThemedButtonProps) => {
    const isDisabled = disabled || loading;
    const { height, padX, fontSize } = sizeMap[size];

    return (
        <button
            type={type}
            onClick={onClick}
            disabled={isDisabled}
            title={title}
            aria-label={ariaLabel}
            style={{
                height,
                minHeight: 44,
                padding: `0 ${padX}px`,
                fontSize,
                fontWeight: 600,
                fontFamily: 'inherit',
                borderRadius: 10,
                cursor: isDisabled ? 'not-allowed' : 'pointer',
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: 8,
                letterSpacing: '0.2px',
                width: fullWidth ? '100%' : undefined,
                transition: 'transform 120ms ease, box-shadow 120ms ease, background 120ms ease',
                whiteSpace: 'nowrap',
                ...variantStyles(variant, isDisabled),
                ...style,
            }}
            onMouseEnter={(e) => {
                if (!isDisabled && variant === 'primary') {
                    e.currentTarget.style.transform = 'translateY(-1px)';
                    e.currentTarget.style.boxShadow = '0 6px 16px rgba(36,42,136,0.32)';
                }
            }}
            onMouseLeave={(e) => {
                e.currentTarget.style.transform = 'translateY(0)';
                if (!isDisabled && variant === 'primary') {
                    e.currentTarget.style.boxShadow = '0 4px 12px rgba(36,42,136,0.25)';
                }
            }}
        >
            {loading ? <Spinner /> : icon}
            <span>{children}</span>
        </button>
    );
};

const Spinner = () => (
    <span
        style={{
            width: 14,
            height: 14,
            border: '2px solid rgba(255,255,255,0.35)',
            borderTopColor: '#ffffff',
            borderRadius: '50%',
            display: 'inline-block',
            animation: 'themed-btn-spin 650ms linear infinite',
        }}
    />
);

export default ThemedButton;
