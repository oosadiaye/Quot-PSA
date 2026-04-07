import React from 'react';
import { Select, Typography, Space, Row, Col, Button } from 'antd';
import { ClearOutlined } from '@ant-design/icons';
import './DimensionSelector.css';

const { Text } = Typography;
const { Option } = Select;

interface DimensionOption {
    id: number;
    code: string;
    name: string;
}

interface DimensionSelectorProps {
    mdas?: DimensionOption[];
    funds?: DimensionOption[];
    functions?: DimensionOption[];
    programs?: DimensionOption[];
    geos?: DimensionOption[];

    selectedMda?: number;
    selectedFund?: number;
    selectedFunction?: number;
    selectedProgram?: number;
    selectedGeo?: number;

    onMdaChange?: (value: number | undefined) => void;
    onFundChange?: (value: number | undefined) => void;
    onFunctionChange?: (value: number | undefined) => void;
    onProgramChange?: (value: number | undefined) => void;
    onGeoChange?: (value: number | undefined) => void;

    onClearAll?: () => void;

    loading?: boolean;
    disabled?: boolean;
}

export const DimensionSelector: React.FC<DimensionSelectorProps> = ({
    mdas = [],
    funds = [],
    functions = [],
    programs = [],
    geos = [],

    selectedMda,
    selectedFund,
    selectedFunction,
    selectedProgram,
    selectedGeo,

    onMdaChange,
    onFundChange,
    onFunctionChange,
    onProgramChange,
    onGeoChange,

    onClearAll,

    loading = false,
    disabled = false,
}) => {
    const renderSelect = (
        label: string,
        options: DimensionOption[],
        value: number | undefined,
        onChange: ((value: number | undefined) => void) | undefined
    ) => (
        <Space direction="vertical" size={4} style={{ width: '100%' }}>
            <Text strong>{label}</Text>
            <Select
                style={{ width: '100%' }}
                placeholder={`Select ${label}`}
                value={value}
                onChange={onChange}
                loading={loading}
                disabled={disabled}
                allowClear
                showSearch
                optionFilterProp="children"
                filterOption={(input, option) =>
                    (option?.children as any)?.toString().toLowerCase().includes(input.toLowerCase())
                }
            >
                {options.map((option) => (
                    <Option key={option.id} value={option.id}>
                        {option.code} - {option.name}
                    </Option>
                ))}
            </Select>
        </Space>
    );

    return (
        <div className="dimension-selector">
            <div className="dimension-selector-header">
                <Text strong style={{ fontSize: 'var(--text-base)' }}>Budget Dimensions</Text>
                {onClearAll && (
                    <Button
                        type="link"
                        icon={<ClearOutlined />}
                        onClick={onClearAll}
                        disabled={disabled}
                    >
                        Clear All
                    </Button>
                )}
            </div>

            <Row gutter={[16, 16]}>
                <Col xs={24} sm={12} lg={8}>
                    {renderSelect('MDA', mdas, selectedMda, onMdaChange)}
                </Col>
                <Col xs={24} sm={12} lg={8}>
                    {renderSelect('Fund', funds, selectedFund, onFundChange)}
                </Col>
                <Col xs={24} sm={12} lg={8}>
                    {renderSelect('Function', functions, selectedFunction, onFunctionChange)}
                </Col>
                <Col xs={24} sm={12} lg={8}>
                    {renderSelect('Program', programs, selectedProgram, onProgramChange)}
                </Col>
                <Col xs={24} sm={12} lg={8}>
                    {renderSelect('Geo Location', geos, selectedGeo, onGeoChange)}
                </Col>
            </Row>
        </div>
    );
};
