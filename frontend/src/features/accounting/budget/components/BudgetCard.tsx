import React from 'react';
import { Card, Statistic, Typography, Space } from 'antd';
import { ArrowUpOutlined, ArrowDownOutlined } from '@ant-design/icons';
import './BudgetCard.css';

const { Text } = Typography;

interface BudgetCardProps {
    title: string;
    value: string | number;
    prefix?: string;
    suffix?: string;
    trend?: {
        value: number;
        isPositive: boolean;
    };
    icon?: React.ReactNode;
    loading?: boolean;
    className?: string;
    valueStyle?: React.CSSProperties;
}

export const BudgetCard: React.FC<BudgetCardProps> = ({
    title,
    value,
    prefix = '',
    suffix,
    trend,
    icon,
    loading = false,
    className = '',
    valueStyle,
}) => {
    return (
        <Card
            className={`budget-card glassmorphism ${className}`}
            loading={loading}
            bordered={false}
        >
            <Space direction="vertical" size="small" style={{ width: '100%' }}>
                <div className="budget-card-header">
                    {icon && <div className="budget-card-icon">{icon}</div>}
                    <Text className="budget-card-title">{title}</Text>
                </div>

                <Statistic
                    value={value}
                    prefix={prefix}
                    suffix={suffix}
                    styles={{ content: {
                        fontSize: 'var(--text-2xl)',
                        fontWeight: 600,
                        ...valueStyle,
                    } }}
                />

                {trend && (
                    <div className="budget-card-trend">
                        <Space size={4}>
                            {trend.isPositive ? (
                                <ArrowUpOutlined style={{ color: '#52c41a' }} />
                            ) : (
                                <ArrowDownOutlined style={{ color: '#ff4d4f' }} />
                            )}
                            <Text
                                style={{
                                    color: trend.isPositive ? '#52c41a' : '#ff4d4f',
                                    fontSize: 'var(--text-sm)',
                                }}
                            >
                                {Math.abs(trend.value)}%
                            </Text>
                            <Text type="secondary" style={{ fontSize: 'var(--text-xs)' }}>
                                vs last period
                            </Text>
                        </Space>
                    </div>
                )}
            </Space>
        </Card>
    );
};
