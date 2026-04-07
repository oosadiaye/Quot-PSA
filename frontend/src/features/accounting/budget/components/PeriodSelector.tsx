import React, { useState } from 'react';
import { Select, Typography, Space } from 'antd';
import './PeriodSelector.css';

const { Text } = Typography;
const { Option } = Select;

interface Period {
    id: number;
    fiscal_year: number;
    period_type: 'ANNUAL' | 'QUARTERLY' | 'MONTHLY';
    period_number: number;
    start_date: string;
    end_date: string;
    status: 'DRAFT' | 'ACTIVE' | 'CLOSED';
}

interface PeriodSelectorProps {
    periods: Period[];
    value?: number;
    onChange: (periodId: number) => void;
    loading?: boolean;
    disabled?: boolean;
}

export const PeriodSelector: React.FC<PeriodSelectorProps> = ({
    periods,
    value,
    onChange,
    loading = false,
    disabled = false,
}) => {
    const formatPeriodLabel = (period: Period) => {
        const typeLabel = {
            ANNUAL: 'Annual',
            QUARTERLY: `Q${period.period_number}`,
            MONTHLY: `Month ${period.period_number}`,
        };

        return `FY${period.fiscal_year} - ${typeLabel[period.period_type]}`;
    };

    const getPeriodStatus = (status: string) => {
        const statusColors = {
            DRAFT: '#d9d9d9',
            ACTIVE: '#52c41a',
            CLOSED: '#ff4d4f',
        };
        return statusColors[status as keyof typeof statusColors] || '#d9d9d9';
    };

    return (
        <div className="period-selector">
            <Space direction="vertical" size={4} style={{ width: '100%' }}>
                <Text strong>Budget Period</Text>
                <Select
                    style={{ width: '100%' }}
                    placeholder="Select budget period"
                    value={value}
                    onChange={onChange}
                    loading={loading}
                    disabled={disabled}
                    showSearch
                    optionFilterProp="children"
                >
                    {periods?.map((period) => (
                        <Option key={period.id} value={period.id}>
                            <Space>
                                <span>{formatPeriodLabel(period)}</span>
                                <span
                                    style={{
                                        display: 'inline-block',
                                        width: 8,
                                        height: 8,
                                        borderRadius: '50%',
                                        backgroundColor: getPeriodStatus(period.status),
                                    }}
                                />
                            </Space>
                        </Option>
                    ))}
                </Select>
            </Space>
        </div>
    );
};
