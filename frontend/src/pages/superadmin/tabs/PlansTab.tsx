import {
  Card, Table, Tag, Button, Space, Popconfirm, Modal, Form, Input, Select,
  Row, Col, InputNumber, Switch, Checkbox, Typography, App, Statistic, Alert,
  Tooltip, Badge, Segmented,
} from 'antd';
import {
  CrownOutlined, PlusOutlined, EditOutlined, DeleteOutlined,
  WarningOutlined, TeamOutlined, CheckCircleFilled, CloseCircleFilled,
  SyncOutlined, ThunderboltOutlined, RocketOutlined, ExperimentOutlined,
  SafetyCertificateOutlined, ApiOutlined, CloudOutlined, UserOutlined,
  AppstoreOutlined,
} from '@ant-design/icons';
import React, { useState, useMemo } from 'react';
import {
  usePlans, useCreatePlan, useUpdatePlan, useDeletePlan,
  usePlanComparison, useExpiringTrials,
  useModulePricingAdmin, useCreateModulePricing, useUpdateModulePricing, useDeleteModulePricing,
} from '../hooks/useSuperAdmin';
import type { ModulePricingRecord } from '../hooks/useSuperAdmin';
import { useCurrency } from '../../../context/CurrencyContext';
import type { SubscriptionPlan, PlanFeature } from '../../../api/superadmin';

const { Text, Title } = Typography;
const { TextArea } = Input;

// ── Style constants ────────────────────────────────────────────────────
const cardStyle: React.CSSProperties = {
  borderRadius: 12,
  border: 'none',
  boxShadow: '0 2px 8px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04)',
};

const PLAN_COLORS: Record<string, string> = {
  free: '#8c8c8c',
  basic: '#1890ff',
  standard: '#52c41a',
  premium: '#722ed1',
  enterprise: '#fa8c16',
};

const PLAN_ICONS: Record<string, React.ReactNode> = {
  free: <ExperimentOutlined />,
  basic: <ThunderboltOutlined />,
  standard: <RocketOutlined />,
  premium: <CrownOutlined />,
  enterprise: <SafetyCertificateOutlined />,
};

const CATEGORY_ICONS: Record<string, React.ReactNode> = {
  'Core': <AppstoreOutlined />,
  'Users & Access': <UserOutlined />,
  'Storage & Data': <CloudOutlined />,
  'Modules': <AppstoreOutlined />,
  'Support': <SafetyCertificateOutlined />,
  'Integrations': <ApiOutlined />,
};

// ── Feature Comparison Matrix ──────────────────────────────────────────
const FeatureComparisonMatrix = ({
  plans,
  formatCurrency,
}: {
  plans: SubscriptionPlan[];
  formatCurrency: (n: number) => string;
}) => {
  // Collect all unique features across plans, grouped by category
  const { categories, featureNames } = useMemo(() => {
    const catMap = new Map<string, Set<string>>();
    for (const plan of plans) {
      for (const f of plan.features || []) {
        if (!catMap.has(f.category)) catMap.set(f.category, new Set());
        catMap.get(f.category)!.add(f.name);
      }
    }
    const cats: string[] = [];
    const names = new Map<string, string[]>();
    const catOrder = ['Core', 'Users & Access', 'Storage & Data', 'Modules', 'Support', 'Integrations'];
    for (const cat of catOrder) {
      if (catMap.has(cat)) {
        cats.push(cat);
        names.set(cat, Array.from(catMap.get(cat)!));
      }
    }
    // Any remaining categories
    for (const [cat, set] of catMap) {
      if (!cats.includes(cat)) {
        cats.push(cat);
        names.set(cat, Array.from(set));
      }
    }
    return { categories: cats, featureNames: names };
  }, [plans]);

  if (plans.length === 0 || categories.length === 0) {
    return <Text type="secondary">No feature data available. Create plans with features to see the comparison matrix.</Text>;
  }

  // Build lookup: planId -> featureName -> feature
  const featureLookup = useMemo(() => {
    const lookup = new Map<number, Map<string, PlanFeature>>();
    for (const plan of plans) {
      const m = new Map<string, PlanFeature>();
      for (const f of plan.features || []) {
        m.set(f.name, f);
      }
      lookup.set(plan.id, m);
    }
    return lookup;
  }, [plans]);

  const renderCell = (planId: number, featureName: string) => {
    const feature = featureLookup.get(planId)?.get(featureName);
    if (!feature) {
      return <CloseCircleFilled style={{ color: '#ff4d4f', fontSize: 16 }} />;
    }
    if (!feature.included) {
      return <CloseCircleFilled style={{ color: '#ff4d4f', fontSize: 16 }} />;
    }
    if (feature.limit) {
      return (
        <Tooltip title={feature.limit}>
          <Tag color="blue" style={{ margin: 0, fontSize: 11 }}>{feature.limit}</Tag>
        </Tooltip>
      );
    }
    return <CheckCircleFilled style={{ color: '#52c41a', fontSize: 16 }} />;
  };

  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
        <thead>
          <tr>
            <th style={{
              position: 'sticky', left: 0, background: '#fafafa',
              padding: '12px 16px', textAlign: 'left', borderBottom: '2px solid #f0f0f0',
              minWidth: 220, zIndex: 2,
            }}>
              Features
            </th>
            {plans.map((plan) => (
              <th key={plan.id} style={{
                padding: '12px 16px', textAlign: 'center',
                borderBottom: `3px solid ${PLAN_COLORS[plan.plan_type] || '#1890ff'}`,
                minWidth: 140,
                background: plan.is_featured
                  ? `linear-gradient(135deg, ${PLAN_COLORS[plan.plan_type]}08 0%, ${PLAN_COLORS[plan.plan_type]}15 100%)`
                  : '#fafafa',
              }}>
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
                  <span style={{ fontSize: 20, color: PLAN_COLORS[plan.plan_type] }}>
                    {PLAN_ICONS[plan.plan_type] || <CrownOutlined />}
                  </span>
                  <Text strong style={{ fontSize: 14 }}>{plan.name}</Text>
                  <Text style={{ fontSize: 16, fontWeight: 700, color: PLAN_COLORS[plan.plan_type] }}>
                    {Number(plan.price) === 0 ? 'Free' : formatCurrency(Number(plan.price))}
                  </Text>
                  <Text type="secondary" style={{ fontSize: 11 }}>
                    /{plan.billing_cycle}
                  </Text>
                  {plan.is_featured && (
                    <Tag color="gold" style={{ fontSize: 10, margin: 0 }}>Most Popular</Tag>
                  )}
                </div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {categories.map((category) => (
            <React.Fragment key={`cat-${category}`}>
              {/* Category header row */}
              <tr>
                <td
                  colSpan={plans.length + 1}
                  style={{
                    padding: '10px 16px',
                    background: '#f5f5f5',
                    fontWeight: 600,
                    fontSize: 13,
                    borderTop: '1px solid #f0f0f0',
                    color: '#262626',
                  }}
                >
                  <Space size={6}>
                    {CATEGORY_ICONS[category] || <AppstoreOutlined />}
                    {category}
                  </Space>
                </td>
              </tr>
              {/* Feature rows */}
              {(featureNames.get(category) || []).map((featureName, idx) => (
                <tr
                  key={`${category}-${featureName}`}
                  style={{
                    background: idx % 2 === 0 ? '#fff' : '#fafafa',
                    transition: 'background 0.2s',
                  }}
                  onMouseEnter={(e) => { e.currentTarget.style.background = '#e6f4ff'; }}
                  onMouseLeave={(e) => { e.currentTarget.style.background = idx % 2 === 0 ? '#fff' : '#fafafa'; }}
                >
                  <td style={{
                    position: 'sticky', left: 0,
                    padding: '8px 16px',
                    borderBottom: '1px solid #f0f0f0',
                    background: 'inherit',
                    zIndex: 1,
                  }}>
                    <Text style={{ fontSize: 13 }}>{featureName}</Text>
                  </td>
                  {plans.map((plan) => (
                    <td key={plan.id} style={{
                      padding: '8px 16px',
                      textAlign: 'center',
                      borderBottom: '1px solid #f0f0f0',
                    }}>
                      {renderCell(plan.id, featureName)}
                    </td>
                  ))}
                </tr>
              ))}
            </React.Fragment>
          ))}
        </tbody>
      </table>
    </div>
  );
};

// ── Plan Cards (Pricing View) ──────────────────────────────────────────
const PlanCards = ({
  plans,
  comparison,
  formatCurrency,
  onEdit,
  onDelete,
}: {
  plans: SubscriptionPlan[];
  comparison: SubscriptionPlan[];
  formatCurrency: (n: number) => string;
  onEdit: (plan: SubscriptionPlan) => void;
  onDelete: (id: number) => void;
}) => {
  const compMap = new Map<number, SubscriptionPlan>();
  comparison.forEach((p) => compMap.set(p.id, p));

  return (
    <Row gutter={[20, 20]}>
      {plans.map((plan) => {
        const comp = compMap.get(plan.id);
        const color = PLAN_COLORS[plan.plan_type] || '#1890ff';
        const includedFeatures = (plan.features || []).filter((f) => f.included);
        const moduleFeatures = (plan.features || []).filter((f) => f.category === 'Modules' && f.included);

        return (
          <Col xs={24} sm={12} lg={6} key={plan.id}>
            <Badge.Ribbon
              text="Most Popular"
              color="gold"
              style={{ display: plan.is_featured ? 'block' : 'none' }}
            >
              <Card
                style={{
                  ...cardStyle,
                  borderTop: `4px solid ${color}`,
                  height: '100%',
                  transition: 'transform 0.2s, box-shadow 0.2s',
                }}
                hoverable
                styles={{ body: { padding: '24px 20px', display: 'flex', flexDirection: 'column', height: '100%' } }}
              >
                {/* Header */}
                <div style={{ textAlign: 'center', marginBottom: 16 }}>
                  <div style={{
                    width: 48, height: 48, borderRadius: 12,
                    background: `${color}15`, color,
                    display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                    fontSize: 22, marginBottom: 8,
                  }}>
                    {PLAN_ICONS[plan.plan_type] || <CrownOutlined />}
                  </div>
                  <Title level={4} style={{ margin: '4px 0 0' }}>{plan.name}</Title>
                  <div style={{ margin: '8px 0' }}>
                    <Text style={{ fontSize: 28, fontWeight: 700, color }}>
                      {Number(plan.price) === 0 ? 'Free' : formatCurrency(Number(plan.price))}
                    </Text>
                    <Text type="secondary" style={{ fontSize: 13 }}>
                      /{plan.billing_cycle}
                    </Text>
                  </div>
                  <Text type="secondary" style={{ fontSize: 12 }}>{plan.description}</Text>
                </div>

                {/* Live stats */}
                {comp && (
                  <div style={{
                    display: 'flex', justifyContent: 'space-around',
                    padding: '12px 0', borderTop: '1px solid #f0f0f0',
                    borderBottom: '1px solid #f0f0f0', marginBottom: 12,
                  }}>
                    <Statistic
                      title={<Text style={{ fontSize: 11 }}>Tenants</Text>}
                      value={comp.tenant_count || 0}
                      prefix={<TeamOutlined />}
                      styles={{ content: { fontSize: 18 } }}
                    />
                    <Statistic
                      title={<Text style={{ fontSize: 11 }}>Active</Text>}
                      value={comp.active_tenants || 0}
                      styles={{ content: { fontSize: 18, color: '#52c41a' } }}
                    />
                    {(comp.trial_tenants || 0) > 0 && (
                      <Statistic
                        title={<Text style={{ fontSize: 11 }}>Trial</Text>}
                        value={comp.trial_tenants || 0}
                        styles={{ content: { fontSize: 18, color: '#faad14' } }}
                      />
                    )}
                  </div>
                )}

                {/* Key limits */}
                <div style={{ marginBottom: 12 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0' }}>
                    <Text type="secondary" style={{ fontSize: 12 }}>Users</Text>
                    <Text strong style={{ fontSize: 12 }}>
                      {(plan.max_users === 0 || plan.max_users >= 999999) ? 'Unlimited' : plan.max_users}
                    </Text>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0' }}>
                    <Text type="secondary" style={{ fontSize: 12 }}>Storage</Text>
                    <Text strong style={{ fontSize: 12 }}>
                      {plan.max_storage_gb === 0 ? 'Unlimited' : plan.max_storage_gb >= 1000 ? `${plan.max_storage_gb / 1000} TB` : `${plan.max_storage_gb} GB`}
                    </Text>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0' }}>
                    <Text type="secondary" style={{ fontSize: 12 }}>Modules</Text>
                    <Text strong style={{ fontSize: 12 }}>{moduleFeatures.length} included</Text>
                  </div>
                  {plan.trial_days > 0 && (
                    <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0' }}>
                      <Text type="secondary" style={{ fontSize: 12 }}>Trial</Text>
                      <Tag color="orange" style={{ margin: 0, fontSize: 11 }}>{plan.trial_days} days</Tag>
                    </div>
                  )}
                </div>

                {/* Top features */}
                <div style={{ flex: 1, marginBottom: 12 }}>
                  {includedFeatures.slice(0, 8).map((f, i) => (
                    <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '3px 0' }}>
                      <CheckCircleFilled style={{ color: '#52c41a', fontSize: 12, flexShrink: 0 }} />
                      <Text style={{ fontSize: 12 }}>
                        {f.name}
                        {f.limit && <Text type="secondary" style={{ fontSize: 11 }}> ({f.limit})</Text>}
                      </Text>
                    </div>
                  ))}
                  {includedFeatures.length > 8 && (
                    <Text type="secondary" style={{ fontSize: 11, display: 'block', marginTop: 4 }}>
                      +{includedFeatures.length - 8} more features
                    </Text>
                  )}
                </div>

                {/* Actions */}
                <Space style={{ width: '100%', justifyContent: 'center' }}>
                  <Button size="small" icon={<EditOutlined />} onClick={() => onEdit(plan)}>
                    Edit
                  </Button>
                  <Popconfirm title="Delete this plan?" onConfirm={() => onDelete(plan.id)} okText="Yes" cancelText="No">
                    <Button size="small" danger icon={<DeleteOutlined />}>Delete</Button>
                  </Popconfirm>
                </Space>
              </Card>
            </Badge.Ribbon>
          </Col>
        );
      })}
    </Row>
  );
};

// ── Module Pricing Manager ────────────────────────────────────────────
const MODULE_NAME_OPTIONS = [
  { value: 'accounting', label: 'Accounting' },
  { value: 'sales', label: 'Sales' },
  { value: 'procurement', label: 'Procurement' },
  { value: 'inventory', label: 'Inventory' },
  { value: 'hrm', label: 'Human Resources' },
  { value: 'budget', label: 'Budget Management' },
  { value: 'production', label: 'Production' },
  { value: 'quality', label: 'Quality' },
  { value: 'service', label: 'Service' },
  { value: 'dimensions', label: 'Dimensions' },
  { value: 'workflow', label: 'Workflow' },
];

const ModulePricingManager = ({ currencySymbol }: { currencySymbol: string }) => {
  const { message } = App.useApp();
  const { data: modules = [], isLoading } = useModulePricingAdmin();
  const createModule = useCreateModulePricing();
  const updateModule = useUpdateModulePricing();
  const deleteModule = useDeleteModulePricing();

  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<ModulePricingRecord | null>(null);
  const [form] = Form.useForm();

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({ features: [], highlights: [], is_active: true, is_popular: false, sort_order: 0 });
    setModalOpen(true);
  };

  const openEdit = (record: ModulePricingRecord) => {
    setEditing(record);
    form.setFieldsValue({
      ...record,
      features: (record.features || []).join('\n'),
      highlights: (record.highlights || []).join('\n'),
    });
    setModalOpen(true);
  };

  const handleSave = async (values: any) => {
    const payload = {
      ...values,
      features: values.features
        ? values.features.split('\n').map((s: string) => s.trim()).filter(Boolean)
        : [],
      highlights: values.highlights
        ? values.highlights.split('\n').map((s: string) => s.trim()).filter(Boolean)
        : [],
    };
    try {
      if (editing) {
        await updateModule.mutateAsync({ id: editing.id, data: payload });
        message.success('Module pricing updated');
      } else {
        await createModule.mutateAsync(payload);
        message.success('Module pricing created');
      }
      setModalOpen(false);
      form.resetFields();
      setEditing(null);
    } catch {
      message.error('Failed to save module pricing');
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await deleteModule.mutateAsync(id);
      message.success('Module pricing deleted');
    } catch {
      message.error('Failed to delete module pricing');
    }
  };

  const columns = [
    {
      title: 'Module', dataIndex: 'title', key: 'title',
      render: (title: string, r: ModulePricingRecord) => (
        <Space>
          <div style={{
            width: 36, height: 36, borderRadius: 8,
            background: 'linear-gradient(135deg, #242a88, #2e35a0)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            color: '#fff', fontSize: 16,
          }}>
            <AppstoreOutlined />
          </div>
          <div>
            <Text strong>{title}</Text>
            <br />
            <Text type="secondary" style={{ fontSize: 11 }}>{r.module_name}</Text>
          </div>
        </Space>
      ),
    },
    {
      title: 'Tagline', dataIndex: 'tagline', key: 'tagline', ellipsis: true,
      render: (t: string) => <Text style={{ fontSize: 12 }}>{t || '—'}</Text>,
    },
    {
      title: 'Monthly', dataIndex: 'price_monthly', key: 'price_monthly',
      render: (v: string) => <Text strong>{currencySymbol}{Number(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</Text>,
    },
    {
      title: 'Yearly', dataIndex: 'price_yearly', key: 'price_yearly',
      render: (v: string) => <Text strong>{currencySymbol}{Number(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</Text>,
    },
    {
      title: 'Features', key: 'features',
      render: (_: any, r: ModulePricingRecord) => (
        <Tag color="blue">{(r.features || []).length} features</Tag>
      ),
    },
    {
      title: 'Status', key: 'status',
      render: (_: any, r: ModulePricingRecord) => (
        <Space size={4}>
          <Tag color={r.is_active ? 'green' : 'default'}>{r.is_active ? 'Active' : 'Inactive'}</Tag>
          {r.is_popular && <Tag color="gold">Popular</Tag>}
        </Space>
      ),
    },
    {
      title: 'Order', dataIndex: 'sort_order', key: 'sort_order', width: 60,
    },
    {
      title: 'Actions', key: 'actions', width: 150,
      render: (_: any, r: ModulePricingRecord) => (
        <Space>
          <Button size="small" type="link" icon={<EditOutlined />} onClick={() => openEdit(r)}>Edit</Button>
          <Popconfirm title="Delete this module pricing?" onConfirm={() => handleDelete(r.id)} okText="Yes" cancelText="No">
            <Button size="small" type="link" danger icon={<DeleteOutlined />}>Delete</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Alert
        style={{ marginBottom: 16, borderRadius: 12 }}
        type="info" showIcon
        description="Configure per-module pricing displayed on the public pricing page. Tenants select individual modules during signup."
      />
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 16 }}>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate} style={{ borderRadius: 8 }}>
          Add Module Pricing
        </Button>
      </div>
      <Card style={cardStyle}>
        <Table columns={columns} dataSource={modules} rowKey="id" loading={isLoading} pagination={false} size="middle" />
      </Card>

      <Modal
        title={editing ? 'Edit Module Pricing' : 'Add Module Pricing'}
        open={modalOpen}
        onCancel={() => { setModalOpen(false); form.resetFields(); setEditing(null); }}
        footer={null}
        width={640}
      >
        <Form form={form} layout="vertical" onFinish={handleSave}>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item label="Module" name="module_name" rules={[{ required: true, message: 'Select module' }]}>
                <Select placeholder="Select module" options={MODULE_NAME_OPTIONS} disabled={!!editing} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item label="Display Title" name="title" rules={[{ required: true, message: 'Enter title' }]}>
                <Input placeholder="e.g., Accounting" />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item label="Tagline" name="tagline">
            <Input placeholder="Short one-liner, e.g., Full double-entry accounting" />
          </Form.Item>
          <Form.Item label="Description" name="description">
            <TextArea placeholder="Detailed description shown on the module detail page" rows={3} />
          </Form.Item>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item label="Price (Monthly)" name="price_monthly" rules={[{ required: true, message: 'Enter monthly price' }]}>
                <InputNumber style={{ width: '100%' }} min={0} step={0.01} prefix={currencySymbol} placeholder="0.00" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item label="Price (Yearly)" name="price_yearly" rules={[{ required: true, message: 'Enter yearly price' }]}>
                <InputNumber style={{ width: '100%' }} min={0} step={0.01} prefix={currencySymbol} placeholder="0.00" />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item label="Features (one per line)" name="features" tooltip="Each line becomes a feature bullet on the pricing card">
            <TextArea placeholder="Chart of Accounts&#10;General Ledger&#10;Accounts Payable" rows={4} />
          </Form.Item>
          <Form.Item label="Key Benefits / Highlights (one per line)" name="highlights" tooltip="Shown as highlighted benefits on the module detail page">
            <TextArea placeholder="Real-time financial reporting&#10;Multi-currency support" rows={3} />
          </Form.Item>
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item label="Sort Order" name="sort_order">
                <InputNumber style={{ width: '100%' }} min={0} placeholder="0" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="is_active" valuePropName="checked" label=" ">
                <Switch checkedChildren="Active" unCheckedChildren="Inactive" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="is_popular" valuePropName="checked" label=" ">
                <Switch checkedChildren="Popular" unCheckedChildren="Standard" />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item>
            <Button type="primary" htmlType="submit" block loading={createModule.isPending || updateModule.isPending}>
              {editing ? 'Update Module Pricing' : 'Create Module Pricing'}
            </Button>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

// ── Main Component ─────────────────────────────────────────────────────
const PlansTab = () => {
  const { message } = App.useApp();
  const { data: plans = [], isLoading, dataUpdatedAt } = usePlans();
  const { data: comparison = [] } = usePlanComparison();
  const { data: expiringTrials = [], isLoading: trialsLoading } = useExpiringTrials(7);
  const createPlan = useCreatePlan();
  const updatePlan = useUpdatePlan();
  const deletePlan = useDeletePlan();
  const { formatCurrency, currencySymbol } = useCurrency();
  const [modalVisible, setModalVisible] = useState(false);
  const [editing, setEditing] = useState<SubscriptionPlan | null>(null);
  const [form] = Form.useForm();
  const [viewMode, setViewMode] = useState<string>('cards');

  const handleSave = async (values: any) => {
    try {
      if (editing) {
        await updatePlan.mutateAsync({ id: editing.id, data: values });
        message.success('Plan updated successfully');
      } else {
        await createPlan.mutateAsync(values);
        message.success('Plan created successfully');
      }
      setModalVisible(false);
      form.resetFields();
      setEditing(null);
    } catch {
      message.error('Failed to save plan');
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await deletePlan.mutateAsync(id);
      message.success('Plan deleted successfully');
    } catch {
      message.error('Failed to delete plan');
    }
  };

  const openEdit = (plan: SubscriptionPlan) => {
    setEditing(plan);
    form.setFieldsValue(plan);
    setModalVisible(true);
  };

  // Build comparison array
  const compArray = Array.isArray(comparison) ? comparison : [];
  const trialsList = Array.isArray(expiringTrials) ? expiringTrials : [];

  // Table columns for list view
  const columns = [
    {
      title: 'Plan Name', dataIndex: 'name', key: 'name',
      render: (text: string, record: SubscriptionPlan) => (
        <Space>
          <span style={{ color: PLAN_COLORS[record.plan_type] || '#1890ff', fontSize: 16 }}>
            {PLAN_ICONS[record.plan_type] || <CrownOutlined />}
          </span>
          <Text strong>{text}</Text>
          {record.is_featured && <Tag color="gold">Popular</Tag>}
        </Space>
      ),
    },
    {
      title: 'Type', dataIndex: 'plan_type', key: 'plan_type',
      render: (type: string) => (
        <Tag color={PLAN_COLORS[type]} style={{ textTransform: 'capitalize' }}>{type}</Tag>
      ),
    },
    {
      title: 'Price', dataIndex: 'price', key: 'price',
      render: (price: string, record: SubscriptionPlan) => (
        <Text strong>
          {Number(price) === 0 ? 'Free' : `${formatCurrency(Number(price))}/${record.billing_cycle}`}
        </Text>
      ),
    },
    { title: 'Max Users', dataIndex: 'max_users', key: 'max_users',
      render: (v: number) => (v === 0 || v >= 999999) ? <Tag color="purple">Unlimited</Tag> : v,
    },
    { title: 'Storage', dataIndex: 'max_storage_gb', key: 'max_storage_gb',
      render: (v: number) => v === 0 ? <Tag color="purple">Unlimited</Tag> : v >= 1000 ? `${v / 1000} TB` : `${v} GB`,
    },
    {
      title: 'Features', key: 'features_count',
      render: (_: any, record: SubscriptionPlan) => {
        const included = (record.features || []).filter((f) => f.included).length;
        const total = (record.features || []).length;
        return <Tag color="blue">{included}/{total}</Tag>;
      },
    },
    {
      title: 'Modules', dataIndex: 'allowed_modules', key: 'allowed_modules',
      render: (modules: string[]) => <Tag>{modules?.length || 0} modules</Tag>,
    },
    {
      title: 'Live Tenants', key: 'tenant_stats',
      render: (_: any, record: SubscriptionPlan) => {
        const comp = compArray.find((c) => c.id === record.id);
        if (!comp) return <SyncOutlined spin style={{ color: '#999' }} />;
        return (
          <Space size={4}>
            <Tag color="blue">{comp.tenant_count || 0}</Tag>
            <Tag color="green">{comp.active_tenants || 0} active</Tag>
            {(comp.trial_tenants || 0) > 0 && <Tag color="orange">{comp.trial_tenants} trial</Tag>}
          </Space>
        );
      },
    },
    {
      title: 'Actions', key: 'actions', width: 150,
      render: (_: any, record: SubscriptionPlan) => (
        <Space>
          <Button size="small" type="link" icon={<EditOutlined />} onClick={() => openEdit(record)}>Edit</Button>
          <Popconfirm title="Delete this plan?" onConfirm={() => handleDelete(record.id)} okText="Yes" cancelText="No">
            <Button size="small" type="link" danger icon={<DeleteOutlined />}>Delete</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const lastUpdated = dataUpdatedAt ? new Date(dataUpdatedAt).toLocaleTimeString() : '';

  return (
    <div>
      {/* Expiring trials alert */}
      {!trialsLoading && trialsList.length > 0 && (
        <Alert
          style={{ marginBottom: 20, borderRadius: 12 }}
          type="warning"
          showIcon
          icon={<WarningOutlined />}
          title={`${trialsList.length} trial${trialsList.length > 1 ? 's' : ''} expiring within 7 days`}
          description={
            <div style={{ marginTop: 8 }}>
              {trialsList.map((t: any) => (
                <Tag key={t.tenant_id} color="orange" style={{ marginBottom: 4 }}>
                  {t.tenant_name} — {t.days_remaining} day{t.days_remaining !== 1 ? 's' : ''} left
                </Tag>
              ))}
            </div>
          }
        />
      )}

      {/* Toolbar */}
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        marginBottom: 16, flexWrap: 'wrap', gap: 12,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <Segmented
            value={viewMode}
            onChange={(v) => setViewMode(v as string)}
            options={[
              { value: 'cards', label: 'Pricing Cards' },
              { value: 'table', label: 'Table View' },
              { value: 'compare', label: 'Feature Matrix' },
              { value: 'module-pricing', label: 'Module Pricing' },
            ]}
          />
          {lastUpdated && (
            <Tooltip title="Data refreshes every 15 seconds">
              <Text type="secondary" style={{ fontSize: 11 }}>
                <SyncOutlined spin style={{ marginRight: 4 }} />
                Live — updated {lastUpdated}
              </Text>
            </Tooltip>
          )}
        </div>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => { setEditing(null); form.resetFields(); setModalVisible(true); }}
          style={{ borderRadius: 8 }}
        >
          Add Plan
        </Button>
      </div>

      {/* Views */}
      {viewMode === 'cards' && (
        <PlanCards
          plans={plans}
          comparison={compArray}
          formatCurrency={formatCurrency}
          onEdit={openEdit}
          onDelete={handleDelete}
        />
      )}

      {viewMode === 'table' && (
        <Card style={cardStyle}>
          <Table
            columns={columns}
            dataSource={plans}
            rowKey="id"
            loading={isLoading}
            pagination={false}
            size="middle"
          />
        </Card>
      )}

      {viewMode === 'compare' && (
        <Card
          title={
            <Space>
              <Text strong style={{ fontSize: 15 }}>Feature Comparison</Text>
              <Tag color="green">{plans.length} plans</Tag>
            </Space>
          }
          style={cardStyle}
        >
          <FeatureComparisonMatrix plans={plans} formatCurrency={formatCurrency} />
        </Card>
      )}

      {viewMode === 'module-pricing' && <ModulePricingManager currencySymbol={currencySymbol} />}

      {/* Add/Edit Modal */}
      <Modal
        title={editing ? 'Edit Plan' : 'Add New Plan'}
        open={modalVisible}
        onCancel={() => { setModalVisible(false); form.resetFields(); setEditing(null); }}
        footer={null}
        width={640}
      >
        <Form form={form} layout="vertical" onFinish={handleSave}>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item label="Plan Name" name="name" rules={[{ required: true, message: 'Enter plan name' }]}>
                <Input placeholder="e.g., Professional" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item label="Plan Type" name="plan_type" rules={[{ required: true, message: 'Select type' }]}>
                <Select placeholder="Select type" options={[
                  { value: 'free', label: 'Free' },
                  { value: 'basic', label: 'Basic' },
                  { value: 'standard', label: 'Standard' },
                  { value: 'premium', label: 'Premium' },
                  { value: 'enterprise', label: 'Enterprise' },
                ]} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                label="Price"
                name="price"
                tooltip="Set to 0 for a free plan"
                rules={[{ required: true, message: 'Enter price (0 for free)' }]}
              >
                <InputNumber style={{ width: '100%' }} placeholder="0 = Free" min={0} prefix={currencySymbol} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item label="Billing Cycle" name="billing_cycle" rules={[{ required: true }]}>
                <Select placeholder="Select cycle" options={[
                  { value: 'monthly', label: 'Monthly' },
                  { value: 'quarterly', label: 'Quarterly' },
                  { value: 'yearly', label: 'Yearly' },
                ]} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item label="Max Users" name="max_users" tooltip="0 = Unlimited">
                <InputNumber style={{ width: '100%' }} min={0} placeholder="0 = Unlimited" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item label="Storage (GB)" name="max_storage_gb" tooltip="0 = Unlimited">
                <InputNumber style={{ width: '100%' }} min={0} placeholder="0 = Unlimited" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item label="Trial Days" name="trial_days" tooltip="0 = No trial period">
                <InputNumber style={{ width: '100%' }} min={0} placeholder="0 = No trial" />
              </Form.Item>
            </Col>
          </Row>
          <Text type="secondary" style={{ fontSize: 11, display: 'block', marginTop: -12, marginBottom: 12 }}>
            Set users or storage to 0 for unlimited. Set price to 0 for a free plan.
          </Text>
          <Form.Item label="Description" name="description">
            <TextArea placeholder="Plan description" rows={2} />
          </Form.Item>
          <Form.Item label="Allowed Modules" name="allowed_modules">
            <Checkbox.Group options={[
              { label: 'Dimensions', value: 'dimensions' },
              { label: 'Accounting', value: 'accounting' },
              { label: 'Budget', value: 'budget' },
              { label: 'Procurement', value: 'procurement' },
              { label: 'Inventory', value: 'inventory' },
              { label: 'Sales', value: 'sales' },
              { label: 'HRM', value: 'hrm' },
              { label: 'Service', value: 'service' },
              { label: 'Workflow', value: 'workflow' },
              { label: 'Production', value: 'production' },
              { label: 'Quality', value: 'quality' },
            ]} />
          </Form.Item>
          <Form.Item name="is_featured" valuePropName="checked">
            <Switch checkedChildren="Featured" unCheckedChildren="Not Featured" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" block loading={createPlan.isPending || updatePlan.isPending}>
              {editing ? 'Update Plan' : 'Create Plan'}
            </Button>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default PlansTab;
