import type { ReactNode } from 'react';
import { useState } from 'react';
import '../../styles/glassmorphism.css';

interface AnimatedButtonProps {
    children: ReactNode;
    onClick?: () => void;
    variant?: 'primary' | 'glass';
    disabled?: boolean;
    loading?: boolean;
    className?: string;
    type?: 'button' | 'submit' | 'reset';
    style?: React.CSSProperties;
}

export default function AnimatedButton({
    children,
    onClick,
    variant = 'primary',
    disabled = false,
    loading = false,
    className = '',
    type = 'button',
    style
}: AnimatedButtonProps) {
    const [ripple, setRipple] = useState(false);

    const handleClick = () => {
        if (disabled || loading) return;

        setRipple(true);
        setTimeout(() => setRipple(false), 600);

        if (onClick) onClick();
    };

    const baseClass = variant === 'primary' ? 'btn-primary' : 'btn-glass';
    const rippleClass = ripple ? 'ripple' : '';

    return (
        <button
            type={type}
            className={`${baseClass} ${rippleClass} ${className}`}
            onClick={handleClick}
            disabled={disabled || loading}
            style={{ opacity: disabled ? 0.5 : 1, cursor: disabled ? 'not-allowed' : 'pointer', ...style }}
        >
            {loading ? (
                <span className="flex items-center gap-2">
                    <svg className="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                    Loading...
                </span>
            ) : children}
        </button>
    );
}
