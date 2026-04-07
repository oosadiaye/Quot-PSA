import type { ReactNode } from 'react';
import '../../styles/glassmorphism.css';

interface GlassCardProps {
    children: ReactNode;
    className?: string;
    hover?: boolean;
    gradient?: boolean;
    onClick?: () => void;
    style?: React.CSSProperties;
}

export default function GlassCard({ children, className = '', hover = false, gradient = false, onClick, style }: GlassCardProps) {
    const baseClass = gradient ? 'gradient-border' : 'glass-card';
    const hoverClass = hover ? 'glass-card-hover' : '';
    const clickableClass = onClick ? 'cursor-pointer' : '';

    return (
        <div
            className={`${baseClass} ${hoverClass} ${clickableClass} ${className}`}
            onClick={onClick}
            style={style}
        >
            {children}
        </div>
    );
}
