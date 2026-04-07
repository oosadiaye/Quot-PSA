import React from 'react';
import { Progress, Typography, Space } from 'antd';
import './UtilizationGauge.css';

const { Text } = Typography;

interface UtilizationGaugeProps {
    title: string;
    percentage: number;
    allocated: string;
    used: string;
    type?: 'circle' | 'line';
    size?: number;
    showInfo?: boolean;
    currencySymbol?: string;
}

export const UtilizationGauge: React.FC<UtilizationGaugeProps> = ({
    title,
    percentage,
    allocated,
    used,
    type = 'circle',
    size = 120,
    showInfo = true,
    currencySymbol = '',
}) => {
    // Determine color based on utilization
    const getColor = (percent: number) => {
        if (percent >= 95) return '#ff4d4f'; // Critical (red)
        if (percent >= 80) return '#faad14'; // Warning (orange)
        if (percent >= 60) return '#1890ff'; // Normal (blue)
        return '#52c41a'; // Low (green)
    };

    const strokeColor = getColor(percentage);

    return (
        <div className="utilization-gauge">
            {type === 'circle' ? (
                <div className="gauge-circle">
                    <Progress
                        type="circle"
                        percent={percentage}
                        strokeColor={strokeColor}
                        size={size}
                        format={(percent) => (
                            <div className="gauge-center">
                                <div className="gauge-percentage">{percent}%</div>
                                <div className="gauge-label">Used</div>
                            </div>
                        )}
                    />
                    <div className="gauge-title">{title}</div>
                    {showInfo && (
                        <div className="gauge-info">
                            <Space direction="vertical" size={2}>
                                <Text type="secondary" style={{ fontSize: 'var(--text-xs)' }}>
                                    Used: {currencySymbol}{used}
                                </Text>
                                <Text type="secondary" style={{ fontSize: 'var(--text-xs)' }}>
                                    Allocated: {currencySymbol}{allocated}
                                </Text>
                            </Space>
                        </div>
                    )}
                </div>
            ) : (
                <div className="gauge-line">
                    <div className="gauge-header">
                        <Text strong>{title}</Text>
                        <Text type="secondary">{percentage}%</Text>
                    </div>
                    <Progress
                        percent={percentage}
                        strokeColor={strokeColor}
                        showInfo={false}
                    />
                    {showInfo && (
                        <div className="gauge-details">
                            <Text type="secondary" style={{ fontSize: 'var(--text-xs)' }}>
                                {currencySymbol}{used} / {currencySymbol}{allocated}
                            </Text>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
};
