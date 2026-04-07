import type { ReactNode } from 'react';
import { TrendingUp, TrendingDown } from 'lucide-react';
import '../../styles/glassmorphism.css';

interface MetricCardProps {
    label: string;
    value: string | number;
    icon?: ReactNode;
    trend?: {
        value: number;
        isPositive: boolean;
    };
    className?: string;
}

export default function MetricCard({ label, value, icon, trend, className = '' }: MetricCardProps) {
    return (
        <div className={`metric-card ${className}`}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div style={{ flex: 1 }}>
                    <div className="metric-label">{label}</div>
                    <div className="metric-value">{value}</div>
                    {trend && (
                        <div className={`metric-trend ${trend.isPositive ? 'positive' : 'negative'}`}>
                            {trend.isPositive ? <TrendingUp size={16} /> : <TrendingDown size={16} />}
                            <span>{Math.abs(trend.value)}%</span>
                        </div>
                    )}
                </div>
                {icon && (
                    <div style={{
                        padding: '12px',
                        borderRadius: '12px',
                        background: 'rgba(36, 113, 163, 0.1)',
                        color: '#2471a3'
                    }}>
                        {icon}
                    </div>
                )}
            </div>
        </div>
    );
}
