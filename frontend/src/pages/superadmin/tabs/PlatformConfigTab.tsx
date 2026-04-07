import { useState } from 'react';
import {
  Card, Tabs, Table, Tag, Button, Space, Modal, Form, Input, InputNumber,
  Switch, Select, App, Empty, Typography, Row, Col,
  Popconfirm, Tooltip, Badge,
} from 'antd';
import {
  GlobalOutlined, DollarOutlined, MailOutlined,
  PlusOutlined, DeleteOutlined, EditOutlined,
  CheckCircleOutlined, CloseCircleOutlined, SendOutlined,
  ReloadOutlined, StarOutlined,
} from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { superadminApi } from '../../../api/superadmin';
import type { LanguageConfig, CurrencyConfig, TenantSMTPConfig } from '../../../api/superadmin';

const { Text, Title } = Typography;

const cardStyle: React.CSSProperties = {
  borderRadius: 12,
  border: 'none',
  boxShadow: '0 2px 8px rgba(0, 0, 0, 0.06), 0 1px 2px rgba(0, 0, 0, 0.04)',
};

// ============================================================================
// Languages Sub-tab
// ============================================================================

function LanguagesSubTab() {
  const { message } = App.useApp();
  const qc = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [editingLang, setEditingLang] = useState<LanguageConfig | null>(null);
  const [form] = Form.useForm();

  const { data: languages = [], isLoading } = useQuery<LanguageConfig[]>({
    queryKey: ['superadmin-languages'],
    queryFn: async () => {
      const { data } = await superadminApi.getLanguages();
      return Array.isArray(data) ? data : (data as any)?.results || [];
    },
  });

  const createMut = useMutation({
    mutationFn: (values: Partial<LanguageConfig>) => superadminApi.createLanguage(values),
    onSuccess: () => {
      message.success('Language created');
      qc.invalidateQueries({ queryKey: ['superadmin-languages'] });
      closeModal();
    },
    onError: () => message.error('Failed to create language'),
  });

  const updateMut = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<LanguageConfig> }) =>
      superadminApi.updateLanguage(id, data),
    onSuccess: () => {
      message.success('Language updated');
      qc.invalidateQueries({ queryKey: ['superadmin-languages'] });
      closeModal();
    },
    onError: () => message.error('Failed to update language'),
  });

  const deleteMut = useMutation({
    mutationFn: (id: number) => superadminApi.deleteLanguage(id),
    onSuccess: () => {
      message.success('Language deleted');
      qc.invalidateQueries({ queryKey: ['superadmin-languages'] });
    },
    onError: () => message.error('Failed to delete language'),
  });

  const closeModal = () => {
    setModalOpen(false);
    setEditingLang(null);
    form.resetFields();
  };

  const openEdit = (lang: LanguageConfig) => {
    setEditingLang(lang);
    form.setFieldsValue(lang);
    setModalOpen(true);
  };

  const handleSubmit = (values: any) => {
    if (editingLang) {
      updateMut.mutate({ id: editingLang.id, data: values });
    } else {
      createMut.mutate(values);
    }
  };

  const handleSetDefault = (lang: LanguageConfig) => {
    updateMut.mutate({ id: lang.id, data: { is_default: true } });
  };

  const columns = [
    {
      title: 'Code', dataIndex: 'language_code', key: 'code', width: 80,
      render: (v: string) => <Tag style={{ borderRadius: 6, fontFamily: 'monospace' }}>{v}</Tag>,
    },
    {
      title: 'Flag', dataIndex: 'flag_emoji', key: 'flag', width: 60,
      render: (v: string) => <span style={{ fontSize: 20 }}>{v || '\uD83C\uDF10'}</span>,
    },
    { title: 'Name', dataIndex: 'language_name', key: 'name', render: (v: string) => <Text strong>{v}</Text> },
    { title: 'Native Name', dataIndex: 'native_name', key: 'native' },
    {
      title: 'Default', dataIndex: 'is_default', key: 'default', width: 100,
      render: (v: boolean) => v ? <Tag color="green" icon={<StarOutlined />}>Default</Tag> : null,
    },
    {
      title: 'Active', dataIndex: 'is_active', key: 'active', width: 100,
      render: (v: boolean) => <Badge status={v ? 'success' : 'default'} text={v ? 'Active' : 'Inactive'} />,
    },
    {
      title: 'RTL', dataIndex: 'is_rtl', key: 'rtl', width: 70,
      render: (v: boolean) => v ? <Tag color="orange">RTL</Tag> : null,
    },
    {
      title: 'Actions', key: 'actions', width: 200,
      render: (_: any, record: LanguageConfig) => (
        <Space size="small">
          {!record.is_default && (
            <Tooltip title="Set as default">
              <Button size="small" type="text" icon={<StarOutlined />}
                onClick={() => handleSetDefault(record)} style={{ color: '#fa8c16' }} />
            </Tooltip>
          )}
          <Tooltip title="Edit">
            <Button size="small" type="text" icon={<EditOutlined />}
              onClick={() => openEdit(record)} style={{ color: '#2471a3' }} />
          </Tooltip>
          <Popconfirm title="Delete this language?" onConfirm={() => deleteMut.mutate(record.id)}
            okText="Delete" okType="danger">
            <Tooltip title="Delete">
              <Button size="small" type="text" danger icon={<DeleteOutlined />} />
            </Tooltip>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <Title level={5} style={{ margin: 0 }}>Platform Languages</Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}
          style={{ borderRadius: 8 }}>
          Add Language
        </Button>
      </div>

      <Table
        dataSource={languages}
        columns={columns}
        rowKey="id"
        loading={isLoading}
        size="middle"
        pagination={false}
      />
      {!isLoading && languages.length === 0 && <Empty description="No languages configured" style={{ marginTop: 24 }} />}

      <Modal
        title={editingLang ? 'Edit Language' : 'Add Language'}
        open={modalOpen}
        onCancel={closeModal}
        footer={null}
        width={560}
      >
        <Form form={form} layout="vertical" onFinish={handleSubmit} style={{ marginTop: 16 }}>
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item label="Code" name="language_code" rules={[{ required: true, message: 'Required' }]}>
                <Input placeholder="en" maxLength={10} disabled={!!editingLang} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item label="Name" name="language_name" rules={[{ required: true, message: 'Required' }]}>
                <Input placeholder="English" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item label="Native Name" name="native_name" rules={[{ required: true, message: 'Required' }]}>
                <Input placeholder="English" />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item label="Flag Emoji" name="flag_emoji">
                <Input placeholder="\uD83C\uDDFA\uD83C\uDDF8" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item label="Date Format" name="date_format" initialValue="YYYY-MM-DD">
                <Input placeholder="YYYY-MM-DD" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item label="Time Format" name="time_format" initialValue="HH:mm">
                <Input placeholder="HH:mm" />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item label="Sort Order" name="sort_order" initialValue={0}>
                <InputNumber min={0} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item label="Default" name="is_default" valuePropName="checked" initialValue={false}>
                <Switch checkedChildren="Yes" unCheckedChildren="No" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item label="RTL" name="is_rtl" valuePropName="checked" initialValue={false}>
                <Switch checkedChildren="RTL" unCheckedChildren="LTR" />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item label="Active" name="is_active" valuePropName="checked" initialValue={true}>
            <Switch checkedChildren="Active" unCheckedChildren="Inactive" />
          </Form.Item>
          <Form.Item style={{ marginBottom: 0, marginTop: 8 }}>
            <Button type="primary" htmlType="submit" block
              loading={createMut.isPending || updateMut.isPending}
              style={{ borderRadius: 8 }}>
              {editingLang ? 'Update Language' : 'Create Language'}
            </Button>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

// ============================================================================
// Currencies Sub-tab
// ============================================================================

function CurrenciesSubTab() {
  const { message } = App.useApp();
  const qc = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [editingCurr, setEditingCurr] = useState<CurrencyConfig | null>(null);
  const [form] = Form.useForm();

  const { data: currencies = [], isLoading } = useQuery<CurrencyConfig[]>({
    queryKey: ['superadmin-currencies'],
    queryFn: async () => {
      const { data } = await superadminApi.getCurrencies();
      return Array.isArray(data) ? data : (data as any)?.results || [];
    },
  });

  const createMut = useMutation({
    mutationFn: (values: Partial<CurrencyConfig>) => superadminApi.createCurrency(values),
    onSuccess: () => {
      message.success('Currency created');
      qc.invalidateQueries({ queryKey: ['superadmin-currencies'] });
      closeModal();
    },
    onError: () => message.error('Failed to create currency'),
  });

  const updateMut = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<CurrencyConfig> }) =>
      superadminApi.updateCurrency(id, data),
    onSuccess: () => {
      message.success('Currency updated');
      qc.invalidateQueries({ queryKey: ['superadmin-currencies'] });
      closeModal();
    },
    onError: () => message.error('Failed to update currency'),
  });

  const deleteMut = useMutation({
    mutationFn: (id: number) => superadminApi.deleteCurrency(id),
    onSuccess: () => {
      message.success('Currency deleted');
      qc.invalidateQueries({ queryKey: ['superadmin-currencies'] });
    },
    onError: () => message.error('Failed to delete currency'),
  });

  const closeModal = () => {
    setModalOpen(false);
    setEditingCurr(null);
    form.resetFields();
  };

  const openEdit = (curr: CurrencyConfig) => {
    setEditingCurr(curr);
    form.setFieldsValue({
      ...curr,
      exchange_rate_to_base: Number(curr.exchange_rate_to_base),
      country_codes: (curr.country_codes || []).join(', '),
    });
    setModalOpen(true);
  };

  const handleSubmit = (values: any) => {
    // Parse country_codes from comma-separated string to array
    const payload = {
      ...values,
      country_codes: values.country_codes
        ? String(values.country_codes).split(',').map((s: string) => s.trim().toUpperCase()).filter(Boolean)
        : [],
    };
    if (editingCurr) {
      updateMut.mutate({ id: editingCurr.id, data: payload });
    } else {
      createMut.mutate(payload);
    }
  };

  const columns = [
    {
      title: 'Currency', dataIndex: 'currency_code', key: 'code', width: 200,
      render: (_: string, record: CurrencyConfig) => (
        <Space>
          {record.flag_emoji && <span style={{ fontSize: 20 }}>{record.flag_emoji}</span>}
          <div>
            <Text strong>{record.symbol} {record.currency_code}</Text>
            <br />
            <Text type="secondary" style={{ fontSize: 11 }}>{record.currency_name}</Text>
          </div>
        </Space>
      ),
    },
    {
      title: 'Rate (1 USD =)', dataIndex: 'exchange_rate_to_base', key: 'rate', width: 150,
      render: (v: string, record: CurrencyConfig) => (
        <Text strong style={{ fontFamily: 'monospace' }}>
          {record.symbol}{Number(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 4 })}
        </Text>
      ),
    },
    {
      title: 'Countries', key: 'countries', width: 180,
      render: (_: any, record: CurrencyConfig) => {
        const codes = record.country_codes || [];
        if (codes.length === 0) return <Text type="secondary">—</Text>;
        return (
          <Space size={2} wrap>
            {codes.slice(0, 5).map((c: string) => (
              <Tag key={c} style={{ borderRadius: 4, fontSize: 11, fontFamily: 'monospace' }}>{c}</Tag>
            ))}
            {codes.length > 5 && <Text type="secondary" style={{ fontSize: 11 }}>+{codes.length - 5}</Text>}
          </Space>
        );
      },
    },
    {
      title: 'Default', dataIndex: 'is_default', key: 'default', width: 80,
      render: (v: boolean) => v ? <Tag color="green" icon={<StarOutlined />}>Default</Tag> : null,
    },
    {
      title: 'Active', dataIndex: 'is_active', key: 'active', width: 80,
      render: (v: boolean) => <Badge status={v ? 'success' : 'default'} text={v ? 'Active' : 'Inactive'} />,
    },
    {
      title: 'Actions', key: 'actions', width: 140,
      render: (_: any, record: CurrencyConfig) => (
        <Space size="small">
          <Tooltip title="Edit">
            <Button size="small" type="text" icon={<EditOutlined />}
              onClick={() => openEdit(record)} style={{ color: '#2471a3' }} />
          </Tooltip>
          <Popconfirm title="Delete this currency?" onConfirm={() => deleteMut.mutate(record.id)}
            okText="Delete" okType="danger">
            <Tooltip title="Delete">
              <Button size="small" type="text" danger icon={<DeleteOutlined />} />
            </Tooltip>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <Title level={5} style={{ margin: 0 }}>Platform Currencies</Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}
          style={{ borderRadius: 8 }}>
          Add Currency
        </Button>
      </div>

      <Table
        dataSource={currencies}
        columns={columns}
        rowKey="id"
        loading={isLoading}
        size="middle"
        pagination={false}
      />
      {!isLoading && currencies.length === 0 && <Empty description="No currencies configured" style={{ marginTop: 24 }} />}

      <Modal
        title={editingCurr ? 'Edit Currency' : 'Add Currency'}
        open={modalOpen}
        onCancel={closeModal}
        footer={null}
        width={560}
      >
        <Form form={form} layout="vertical" onFinish={handleSubmit} style={{ marginTop: 16 }}>
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item label="Code" name="currency_code" rules={[{ required: true, message: 'Required' }]}>
                <Input placeholder="NGN" maxLength={3} style={{ textTransform: 'uppercase' }}
                  disabled={!!editingCurr} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item label="Name" name="currency_name" rules={[{ required: true, message: 'Required' }]}>
                <Input placeholder="Nigerian Naira" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item label="Symbol" name="symbol" rules={[{ required: true, message: 'Required' }]}>
                <Input placeholder="\u20A6" />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item label="Decimal Places" name="decimal_places" initialValue={2}>
                <InputNumber min={0} max={6} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item label="Exchange Rate" name="exchange_rate_to_base" initialValue={1}
                rules={[{ required: true, message: 'Required' }]}>
                <InputNumber min={0} step={0.0001} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item label="Symbol Position" name="symbol_position" initialValue="prefix">
                <Select options={[
                  { label: 'Before Amount', value: 'prefix' },
                  { label: 'After Amount', value: 'suffix' },
                ]} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item label="Decimal Sep" name="decimal_separator" initialValue=".">
                <Input maxLength={1} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item label="Thousand Sep" name="thousand_separator" initialValue=",">
                <Input maxLength={1} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item label="Auto Update" name="auto_update" valuePropName="checked" initialValue={false}>
                <Switch checkedChildren="Yes" unCheckedChildren="No" />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={16}>
              <Form.Item
                label="Country Codes (ISO)"
                name="country_codes"
                tooltip="Comma-separated ISO 3166-1 alpha-2 codes for IP auto-detection, e.g. NG, GH"
              >
                <Input placeholder="NG, GH, SN" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item label="Flag Emoji" name="flag_emoji" tooltip="Flag emoji for display">
                <Input placeholder="🇳🇬" style={{ fontSize: 20 }} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item label="Default" name="is_default" valuePropName="checked" initialValue={false}>
                <Switch checkedChildren="Default" unCheckedChildren="No" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item label="Active" name="is_active" valuePropName="checked" initialValue={true}>
                <Switch checkedChildren="Active" unCheckedChildren="Inactive" />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item style={{ marginBottom: 0, marginTop: 8 }}>
            <Button type="primary" htmlType="submit" block
              loading={createMut.isPending || updateMut.isPending}
              style={{ borderRadius: 8 }}>
              {editingCurr ? 'Update Currency' : 'Create Currency'}
            </Button>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

// ============================================================================
// Tenant SMTP Sub-tab
// ============================================================================

function TenantSMTPSubTab() {
  const { message } = App.useApp();
  const qc = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [editingSMTP, setEditingSMTP] = useState<TenantSMTPConfig | null>(null);
  const [form] = Form.useForm();

  const { data: smtpConfigs = [], isLoading } = useQuery<TenantSMTPConfig[]>({
    queryKey: ['superadmin-tenant-smtp'],
    queryFn: async () => {
      const { data } = await superadminApi.getTenantSMTP();
      return Array.isArray(data) ? data : (data as any)?.results || [];
    },
  });

  const { data: tenants = [] } = useQuery({
    queryKey: ['superadmin-tenants'],
    queryFn: async () => {
      const { data } = await superadminApi.getTenants();
      return data || [];
    },
  });

  const createMut = useMutation({
    mutationFn: (values: Partial<TenantSMTPConfig>) => superadminApi.createTenantSMTP(values),
    onSuccess: () => {
      message.success('SMTP configuration created');
      qc.invalidateQueries({ queryKey: ['superadmin-tenant-smtp'] });
      closeModal();
    },
    onError: () => message.error('Failed to create SMTP config'),
  });

  const updateMut = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<TenantSMTPConfig> }) =>
      superadminApi.updateTenantSMTP(id, data),
    onSuccess: () => {
      message.success('SMTP configuration updated');
      qc.invalidateQueries({ queryKey: ['superadmin-tenant-smtp'] });
      closeModal();
    },
    onError: () => message.error('Failed to update SMTP config'),
  });

  const deleteMut = useMutation({
    mutationFn: (id: number) => superadminApi.deleteTenantSMTP(id),
    onSuccess: () => {
      message.success('SMTP configuration deleted');
      qc.invalidateQueries({ queryKey: ['superadmin-tenant-smtp'] });
    },
    onError: () => message.error('Failed to delete SMTP config'),
  });

  const testMut = useMutation({
    mutationFn: (id: number) => superadminApi.testTenantSMTP(id),
    onSuccess: () => {
      message.success('Test email sent successfully');
      qc.invalidateQueries({ queryKey: ['superadmin-tenant-smtp'] });
    },
    onError: () => message.error('SMTP test failed'),
  });

  const closeModal = () => {
    setModalOpen(false);
    setEditingSMTP(null);
    form.resetFields();
  };

  const openEdit = (smtp: TenantSMTPConfig) => {
    setEditingSMTP(smtp);
    form.setFieldsValue({
      ...smtp,
      tenant_id: smtp.tenant_id,
    });
    setModalOpen(true);
  };

  const handleSubmit = (values: any) => {
    if (editingSMTP) {
      updateMut.mutate({ id: editingSMTP.id, data: values });
    } else {
      createMut.mutate(values);
    }
  };

  const columns = [
    {
      title: 'Tenant', dataIndex: 'tenant_name', key: 'tenant',
      render: (v: string) => <Text strong>{v || '-'}</Text>,
    },
    {
      title: 'SMTP Host', dataIndex: 'smtp_host', key: 'host',
      render: (v: string) => <Text style={{ fontFamily: 'monospace', fontSize: 12 }}>{v}</Text>,
    },
    { title: 'Port', dataIndex: 'smtp_port', key: 'port', width: 70 },
    {
      title: 'Security', key: 'security', width: 100,
      render: (_: any, r: TenantSMTPConfig) => (
        <Space size={4}>
          {r.smtp_use_tls && <Tag color="blue" style={{ borderRadius: 4 }}>TLS</Tag>}
          {r.smtp_use_ssl && <Tag color="purple" style={{ borderRadius: 4 }}>SSL</Tag>}
        </Space>
      ),
    },
    {
      title: 'From Email', dataIndex: 'smtp_from_email', key: 'from',
      render: (v: string) => <Text type="secondary">{v}</Text>,
    },
    {
      title: 'Status', key: 'status', width: 180,
      render: (_: any, r: TenantSMTPConfig) => (
        <Space>
          {r.is_verified
            ? <Tag icon={<CheckCircleOutlined />} color="success" style={{ borderRadius: 6 }}>Verified</Tag>
            : <Tag icon={<CloseCircleOutlined />} color="default" style={{ borderRadius: 6 }}>Unverified</Tag>
          }
          <Badge status={r.is_active ? 'success' : 'default'} text={r.is_active ? 'Active' : 'Inactive'} />
        </Space>
      ),
    },
    {
      title: 'Actions', key: 'actions', width: 200,
      render: (_: any, r: TenantSMTPConfig) => (
        <Space size="small">
          <Tooltip title="Test connection">
            <Button size="small" type="text" icon={<SendOutlined />}
              onClick={() => testMut.mutate(r.id)}
              loading={testMut.isPending}
              style={{ color: '#2471a3' }} />
          </Tooltip>
          <Tooltip title="Edit">
            <Button size="small" type="text" icon={<EditOutlined />}
              onClick={() => openEdit(r)} style={{ color: '#2471a3' }} />
          </Tooltip>
          <Popconfirm title="Delete this SMTP config?" onConfirm={() => deleteMut.mutate(r.id)}
            okText="Delete" okType="danger">
            <Tooltip title="Delete">
              <Button size="small" type="text" danger icon={<DeleteOutlined />} />
            </Tooltip>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <Title level={5} style={{ margin: 0 }}>Tenant SMTP Configurations</Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}
          style={{ borderRadius: 8 }}>
          Configure SMTP
        </Button>
      </div>

      <Table
        dataSource={smtpConfigs}
        columns={columns}
        rowKey="id"
        loading={isLoading}
        size="middle"
        pagination={{ pageSize: 10 }}
      />
      {!isLoading && smtpConfigs.length === 0 && (
        <Empty description="No SMTP configurations" style={{ marginTop: 24 }} />
      )}

      <Modal
        title={editingSMTP ? 'Edit SMTP Configuration' : 'Configure SMTP'}
        open={modalOpen}
        onCancel={closeModal}
        footer={null}
        width={580}
      >
        <Form form={form} layout="vertical" onFinish={handleSubmit} style={{ marginTop: 16 }}>
          <Form.Item label="Tenant" name="tenant_id" rules={[{ required: true, message: 'Required' }]}>
            <Select
              placeholder="Select tenant"
              showSearch
              disabled={!!editingSMTP}
              filterOption={(input, opt) => (opt?.label as string || '').toLowerCase().includes(input.toLowerCase())}
              options={(tenants as any[]).map((t: any) => ({ value: t.id, label: t.name }))}
            />
          </Form.Item>
          <Row gutter={16}>
            <Col span={16}>
              <Form.Item label="SMTP Host" name="smtp_host" rules={[{ required: true, message: 'Required' }]}>
                <Input placeholder="smtp.gmail.com" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item label="Port" name="smtp_port" rules={[{ required: true, message: 'Required' }]}
                initialValue={587}>
                <InputNumber style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item label="Username" name="smtp_username">
                <Input placeholder="user@gmail.com" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item label="Password" name="smtp_password">
                <Input.Password placeholder="App password" />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item label="From Email" name="smtp_from_email"
                rules={[{ required: true, type: 'email', message: 'Valid email required' }]}>
                <Input placeholder="noreply@company.com" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item label="From Name" name="smtp_from_name">
                <Input placeholder="Company Name" />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item label="Reply-To Email" name="reply_to_email">
            <Input placeholder="support@company.com" />
          </Form.Item>
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item label="Use TLS" name="smtp_use_tls" valuePropName="checked" initialValue={true}>
                <Switch checkedChildren="TLS" unCheckedChildren="Off" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item label="Use SSL" name="smtp_use_ssl" valuePropName="checked" initialValue={false}>
                <Switch checkedChildren="SSL" unCheckedChildren="Off" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item label="Active" name="is_active" valuePropName="checked" initialValue={true}>
                <Switch checkedChildren="Active" unCheckedChildren="Inactive" />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item style={{ marginBottom: 0, marginTop: 8 }}>
            <Button type="primary" htmlType="submit" block
              loading={createMut.isPending || updateMut.isPending}
              style={{ borderRadius: 8 }}>
              {editingSMTP ? 'Update SMTP Config' : 'Create SMTP Config'}
            </Button>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

// ============================================================================
// Main PlatformConfigTab
// ============================================================================

export default function PlatformConfigTab() {
  const qc = useQueryClient();

  const handleRefresh = () => {
    qc.invalidateQueries({ queryKey: ['superadmin-languages'] });
    qc.invalidateQueries({ queryKey: ['superadmin-currencies'] });
    qc.invalidateQueries({ queryKey: ['superadmin-tenant-smtp'] });
  };

  const tabItems = [
    {
      key: 'languages',
      label: <span><GlobalOutlined /> Languages</span>,
      children: <LanguagesSubTab />,
    },
    {
      key: 'currencies',
      label: <span><DollarOutlined /> Currencies</span>,
      children: <CurrenciesSubTab />,
    },
    {
      key: 'smtp',
      label: <span><MailOutlined /> Tenant SMTP</span>,
      children: <TenantSMTPSubTab />,
    },
  ];

  return (
    <Card style={cardStyle}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0, color: '#0f172a', fontWeight: 700 }}>
          Platform Configuration
        </Title>
        <Button icon={<ReloadOutlined />} onClick={handleRefresh} style={{ borderRadius: 8 }}>
          Refresh
        </Button>
      </div>
      <Tabs items={tabItems} />
    </Card>
  );
}
