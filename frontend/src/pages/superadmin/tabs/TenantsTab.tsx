import {
  Card, Table, Tag, Button, Space, Badge, Drawer, Descriptions, Divider,
  InputNumber, Modal, Form, Input, Select, App, Dropdown, Tabs, Switch,
  Popconfirm, Row, Col, Tooltip, Empty, Skeleton, Typography, Input as AntInput,
} from 'antd';
import {
  ShopOutlined, PlusOutlined, SwapOutlined, CalendarOutlined, StopOutlined,
  PlayCircleOutlined, MoreOutlined, DeleteOutlined, EditOutlined, SearchOutlined,
  LoginOutlined, AppstoreOutlined, UserOutlined, InfoCircleOutlined,
  ReloadOutlined, KeyOutlined,
} from '@ant-design/icons';
import { useState, useMemo, useEffect } from 'react';
import {
  useTenants, useCreateTenant, useTenantAction, usePlans,
  useTenantModules, useToggleTenantModule, useImpersonateUser,
} from '../hooks/useSuperAdmin';
import type { Tenant, SubscriptionPlan } from '../../../api/superadmin';

const { Text, Title } = Typography;
const { Search } = AntInput;

const cardStyle: React.CSSProperties = {
  borderRadius: 12,
  border: 'none',
  boxShadow: '0 2px 8px rgba(0, 0, 0, 0.06), 0 1px 2px rgba(0, 0, 0, 0.04)',
};

const TenantsTab = () => {
  const { message } = App.useApp();
  const { data: tenants = [], isLoading } = useTenants();
  const { data: plans = [] } = usePlans();
  const createTenant = useCreateTenant();
  const tenantAction = useTenantAction();
  const impersonate = useImpersonateUser();

  // UI state
  const [drawerVisible, setDrawerVisible] = useState(false);
  const [tenantDetail, setTenantDetail] = useState<Tenant | null>(null);
  const [createModalVisible, setCreateModalVisible] = useState(false);
  const [editModalVisible, setEditModalVisible] = useState(false);
  const [planModalVisible, setPlanModalVisible] = useState(false);
  const [extendDays, setExtendDays] = useState(30);
  const [searchText, setSearchText] = useState('');
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined);
  const [createForm] = Form.useForm();
  const [editForm] = Form.useForm();

  // Sync tenantDetail with latest query data after mutations
  useEffect(() => {
    if (tenantDetail && tenants.length) {
      const updated = tenants.find((t) => t.id === tenantDetail.id);
      if (updated) {
        setTenantDetail(updated);
      } else {
        // Tenant was deleted
        setTenantDetail(null);
        setDrawerVisible(false);
      }
    }
  }, [tenants]);

  // Filter tenants
  const filteredTenants = useMemo(() => {
    let result = tenants;
    if (searchText) {
      const lower = searchText.toLowerCase();
      result = result.filter(
        (t) =>
          t.name.toLowerCase().includes(lower) ||
          t.schema_name.toLowerCase().includes(lower)
      );
    }
    if (statusFilter) {
      result = result.filter((t) => t.status === statusFilter);
    }
    return result;
  }, [tenants, searchText, statusFilter]);

  // Handlers
  const handleAction = async (tenantId: number, action: string, data?: any) => {
    try {
      await tenantAction.mutateAsync({ tenantId, action, data });
      const messages: Record<string, string> = {
        suspend: 'Tenant suspended',
        activate: 'Tenant activated',
        extend: `Subscription extended by ${data?.days || 30} days`,
      };
      message.success(messages[action] || 'Action completed');
    } catch {
      message.error('Operation failed');
    }
  };

  const handleCreate = async (values: any) => {
    // POST returns 202 in <1s; async Celery worker finishes schema
    // migrations in the background. useTenants() polls every 3s while any
    // row is still provisioning, so the status chip updates live.
    message.loading({
      key: 'create-tenant',
      content: 'Creating tenant… schema provisioning runs in background',
      duration: 0,
    });
    try {
      await createTenant.mutateAsync(values);
      message.success({
        key: 'create-tenant',
        content: 'Tenant queued — schema provisioning in progress',
      });
      setCreateModalVisible(false);
      createForm.resetFields();
    } catch (err: unknown) {
      const msg =
        err instanceof Error ? err.message : 'Failed to create tenant';
      message.error({ key: 'create-tenant', content: msg });
    }
  };

  const handleEdit = async (values: any) => {
    if (!tenantDetail) return;
    try {
      await tenantAction.mutateAsync({
        tenantId: tenantDetail.id,
        action: 'update',
        data: values,
      });
      message.success('Tenant updated');
      setEditModalVisible(false);
      editForm.resetFields();
    } catch {
      message.error('Failed to update tenant');
    }
  };

  const handleChangePlan = async (planId: number) => {
    if (!tenantDetail) return;
    try {
      await tenantAction.mutateAsync({
        tenantId: tenantDetail.id,
        action: 'change_plan',
        data: { planId },
      });
      message.success('Plan changed successfully');
      setPlanModalVisible(false);
    } catch {
      message.error('Failed to change plan');
    }
  };

  const handleDelete = async (tenant: Tenant) => {
    try {
      await tenantAction.mutateAsync({ tenantId: tenant.id, action: 'delete' });
      message.success('Tenant deleted');
      setDrawerVisible(false);
      setTenantDetail(null);
    } catch {
      message.error('Failed to delete tenant');
    }
  };

  const handleImpersonate = async (tenant: Tenant) => {
    try {
      // Impersonate as the first admin user in the tenant
      const data = await impersonate.mutateAsync({ userId: 0, tenantId: tenant.id });
      const impersonationData = {
        token: data.token,
        tenant_domain: data.tenant_domain,
        tenant_name: data.tenant_name || tenant.name,
        user: data.user?.username || 'admin',
        user_id: data.user?.id,
        user_email: data.user?.email,
        user_first_name: data.user?.first_name,
        user_last_name: data.user?.last_name,
        session_id: data.session_id,
      };
      // Store impersonation data temporarily in sessionStorage (more secure than URL params)
      sessionStorage.setItem('pending_impersonation', JSON.stringify(impersonationData));
      window.open('/?impersonation=pending', '_blank');
      message.success(`Impersonating admin in ${tenant.name}`);
    } catch (err: any) {
      message.error(err?.response?.data?.error || 'Failed to impersonate');
    }
  };

  const handleResetPassword = (tenant: Tenant) => {
    Modal.confirm({
      title: `Reset password for "${tenant.name}"?`,
      content: 'A new temporary password will be generated and emailed to the tenant admin.',
      okText: 'Reset Password',
      okType: 'primary',
      icon: <KeyOutlined style={{ color: '#d97706' }} />,
      onOk: async () => {
        try {
          const result = await tenantAction.mutateAsync({
            tenantId: tenant.id,
            action: 'reset_password',
          });
          Modal.success({
            title: 'Password Reset Successful',
            width: 480,
            content: (
              <Descriptions column={1} size="small" style={{ marginTop: 12 }}>
                <Descriptions.Item label="Username">{result.username}</Descriptions.Item>
                <Descriptions.Item label="Email">{result.email}</Descriptions.Item>
                <Descriptions.Item label="Temporary Password">
                  <Text code copyable strong>{result.temp_password}</Text>
                </Descriptions.Item>
                <Descriptions.Item label="Email Sent">
                  <Tag color={result.email_sent ? 'green' : 'red'}>
                    {result.email_sent ? 'Yes' : 'Failed'}
                  </Tag>
                </Descriptions.Item>
              </Descriptions>
            ),
          });
        } catch (err) {
          const detail =
            (err as { response?: { data?: { error?: string } } })?.response?.data?.error;
          message.error(detail || 'Failed to reset password');
        }
      },
    });
  };

  // Re-queue a failed tenant. Server short-circuits idempotently, so
  // clicking Retry on a partially-provisioned schema is safe.
  const handleRetryProvisioning = (tenant: Tenant) => {
    Modal.confirm({
      title: `Retry provisioning for "${tenant.name}"?`,
      content:
        'This will re-queue schema creation. If a previous attempt left a partial schema, the task will resume from where it stopped.',
      okText: 'Retry',
      okType: 'primary',
      icon: <ReloadOutlined style={{ color: '#2563eb' }} />,
      onOk: async () => {
        const key = `retry-${tenant.id}`;
        message.loading({ content: 'Re-queueing provisioning…', key, duration: 0 });
        try {
          await tenantAction.mutateAsync({
            tenantId: tenant.id,
            action: 'retry_provisioning',
          });
          message.success({ content: 'Provisioning queued', key, duration: 2 });
        } catch (err: unknown) {
          const msg =
            (err as { response?: { data?: { error?: string } } })?.response?.data?.error
            ?? 'Failed to retry provisioning';
          message.error({ content: msg, key, duration: 4 });
        }
      },
    });
  };

  const openDetail = (tenant: Tenant) => {
    setTenantDetail(tenant);
    setDrawerVisible(true);
  };

  // Status color map
  const statusConfig: Record<string, { color: string; badge: 'success' | 'warning' | 'error' | 'default' }> = {
    active: { color: 'green', badge: 'success' },
    trial: { color: 'orange', badge: 'warning' },
    suspended: { color: 'red', badge: 'error' },
    expired: { color: 'default', badge: 'default' },
    cancelled: { color: 'default', badge: 'default' },
  };

  const columns = [
    {
      title: 'Tenant',
      dataIndex: 'name',
      key: 'name',
      sorter: (a: Tenant, b: Tenant) => a.name.localeCompare(b.name),
      render: (text: string, record: Tenant) => (
        <Space>
          <div
            style={{
              width: 36, height: 36, borderRadius: 8,
              background: 'linear-gradient(135deg, #1890ff 0%, #096dd9 100%)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}
          >
            <ShopOutlined style={{ color: '#fff', fontSize: 16 }} />
          </div>
          <div>
            <a onClick={() => openDetail(record)} style={{ fontWeight: 600 }}>{text}</a>
            <div style={{ fontSize: 12, color: '#8c8c8c' }}>{record.schema_name}</div>
          </div>
        </Space>
      ),
    },
    {
      title: 'Plan',
      dataIndex: 'plan',
      key: 'plan',
      render: (plan: string) => plan ? <Tag color="blue">{plan}</Tag> : <Tag>None</Tag>,
    },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      filters: [
        { text: 'Active', value: 'active' },
        { text: 'Trial', value: 'trial' },
        { text: 'Suspended', value: 'suspended' },
        { text: 'Expired', value: 'expired' },
      ],
      onFilter: (value: any, record: Tenant) => record.status === value,
      render: (status: string, record: Tenant) => {
        // Provisioning chip takes precedence: if the tenant is still being
        // created asynchronously we show that, not the subscription status.
        const prov = record.provisioning_status;
        if (prov === 'pending' || prov === 'provisioning') {
          return (
            <Tooltip title="Schema migrations running on a background worker">
              <Tag icon={<ReloadOutlined spin />} color="processing">
                {prov === 'pending' ? 'Queued' : 'Provisioning…'}
              </Tag>
            </Tooltip>
          );
        }
        if (prov === 'failed') {
          return (
            <Tooltip title={record.provisioning_error || 'Provisioning failed'}>
              <Tag color="error">Failed</Tag>
            </Tooltip>
          );
        }
        const config = statusConfig[status] || statusConfig.expired;
        return <Badge status={config.badge} text={<span style={{ textTransform: 'capitalize' }}>{status || 'Unknown'}</span>} />;
      },
    },
    {
      title: 'Expires',
      dataIndex: 'end_date',
      key: 'end_date',
      sorter: (a: Tenant, b: Tenant) => (a.end_date || '').localeCompare(b.end_date || ''),
      render: (date: string) => {
        if (!date) return <Text type="secondary">-</Text>;
        const d = new Date(date);
        const now = new Date();
        const daysLeft = Math.ceil((d.getTime() - now.getTime()) / (1000 * 60 * 60 * 24));
        return (
          <Tooltip title={`${daysLeft} days remaining`}>
            <Text type={daysLeft < 7 ? 'danger' : daysLeft < 30 ? 'warning' : undefined}>
              {d.toLocaleDateString()}
            </Text>
          </Tooltip>
        );
      },
    },
    {
      title: 'Created',
      dataIndex: 'created_on',
      key: 'created_on',
      sorter: (a: Tenant, b: Tenant) => (a.created_on || '').localeCompare(b.created_on || ''),
      render: (date: string) => date ? new Date(date).toLocaleDateString() : '-',
    },
    {
      title: 'Actions',
      key: 'actions',
      width: 180,
      render: (_: any, record: Tenant) => {
        const canRetry = record.provisioning_status === 'failed';
        const menuItems = [
          { key: 'view', label: 'View Details', icon: <InfoCircleOutlined /> },
          { key: 'edit', label: 'Edit', icon: <EditOutlined /> },
          { key: 'change_plan', label: 'Change Plan', icon: <SwapOutlined /> },
          { key: 'extend', label: 'Extend Subscription', icon: <CalendarOutlined /> },
          { key: 'impersonate', label: 'Login As Admin', icon: <LoginOutlined /> },
          { key: 'reset_password', label: 'Reset Password', icon: <KeyOutlined /> },
          ...(canRetry
            ? [
                { type: 'divider' as const },
                {
                  key: 'retry_provisioning',
                  label: 'Retry Provisioning',
                  icon: <ReloadOutlined />,
                },
              ]
            : []),
          { type: 'divider' as const },
          record.status === 'suspended'
            ? { key: 'activate', label: 'Activate', icon: <PlayCircleOutlined /> }
            : { key: 'suspend', label: 'Suspend', icon: <StopOutlined />, danger: true },
          { key: 'delete', label: 'Delete Tenant', icon: <DeleteOutlined />, danger: true },
        ];

        return (
          <Space>
            <Button size="small" type="link" onClick={() => openDetail(record)}>
              Manage
            </Button>
            <Dropdown
              menu={{
                items: menuItems,
                onClick: ({ key }) => {
                  setTenantDetail(record);
                  switch (key) {
                    case 'view':
                      openDetail(record);
                      break;
                    case 'edit':
                      editForm.setFieldsValue({ name: record.name });
                      setEditModalVisible(true);
                      break;
                    case 'change_plan':
                      setPlanModalVisible(true);
                      break;
                    case 'extend':
                      openDetail(record);
                      break;
                    case 'impersonate':
                      handleImpersonate(record);
                      break;
                    case 'reset_password':
                      handleResetPassword(record);
                      break;
                    case 'retry_provisioning':
                      handleRetryProvisioning(record);
                      break;
                    case 'suspend':
                      handleAction(record.id, 'suspend');
                      break;
                    case 'activate':
                      handleAction(record.id, 'activate');
                      break;
                    case 'delete':
                      Modal.confirm({
                        title: `Delete tenant "${record.name}"?`,
                        content: 'This action cannot be undone. All tenant data will be permanently deleted.',
                        okText: 'Delete',
                        okType: 'danger',
                        onOk: () => handleDelete(record),
                      });
                      break;
                  }
                },
              }}
              trigger={['click']}
            >
              <Button size="small" icon={<MoreOutlined />} />
            </Dropdown>
          </Space>
        );
      },
    },
  ];

  return (
    <div>
      {/* Header with search and filters */}
      <Card style={cardStyle}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <Title level={5} style={{ margin: 0 }}>Tenant Management</Title>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => setCreateModalVisible(true)}
            style={{ borderRadius: 8 }}
          >
            Add Tenant
          </Button>
        </div>

        <Row gutter={16} style={{ marginBottom: 16 }}>
          <Col xs={24} sm={12} md={8}>
            <Search
              placeholder="Search tenants..."
              allowClear
              onChange={(e) => setSearchText(e.target.value)}
              prefix={<SearchOutlined />}
            />
          </Col>
          <Col xs={24} sm={8} md={6}>
            <Select
              placeholder="Filter by status"
              allowClear
              style={{ width: '100%' }}
              onChange={(val) => setStatusFilter(val)}
              options={[
                { value: 'active', label: 'Active' },
                { value: 'trial', label: 'Trial' },
                { value: 'suspended', label: 'Suspended' },
                { value: 'expired', label: 'Expired' },
              ]}
            />
          </Col>
          <Col>
            <Text type="secondary">{filteredTenants.length} tenant{filteredTenants.length !== 1 ? 's' : ''}</Text>
          </Col>
        </Row>

        <Table
          columns={columns}
          dataSource={filteredTenants}
          rowKey="id"
          loading={isLoading}
          pagination={{ pageSize: 10, showSizeChanger: true, showTotal: (total) => `Total ${total} tenants` }}
        />
      </Card>

      {/* ── Tenant Detail Drawer ──────────────────────────────────────── */}
      <Drawer
        title={
          <Space>
            <ShopOutlined />
            <span>{tenantDetail?.name || 'Tenant Details'}</span>
            {tenantDetail?.status && (
              <Tag color={statusConfig[tenantDetail.status]?.color || 'default'}>
                {tenantDetail.status}
              </Tag>
            )}
          </Space>
        }
        placement="right"
        styles={{ wrapper: { width: '640px' } }}
        open={drawerVisible}
        onClose={() => { setDrawerVisible(false); setTenantDetail(null); }}
        extra={
          <Space>
            <Tooltip title="Login as admin in this tenant">
              <Button
                icon={<LoginOutlined />}
                onClick={() => tenantDetail && handleImpersonate(tenantDetail)}
                loading={impersonate.isPending}
              >
                Impersonate
              </Button>
            </Tooltip>
            <Button
              icon={<EditOutlined />}
              onClick={() => {
                if (tenantDetail) {
                  editForm.setFieldsValue({ name: tenantDetail.name });
                  setEditModalVisible(true);
                }
              }}
            >
              Edit
            </Button>
          </Space>
        }
      >
        {tenantDetail && (
          <Tabs
            defaultActiveKey="info"
            items={[
              {
                key: 'info',
                label: <span><InfoCircleOutlined /> Info</span>,
                children: (
                  <div>
                    <Descriptions column={1} bordered size="small" style={{ marginBottom: 24 }}>
                      <Descriptions.Item label="Organization">{tenantDetail.name}</Descriptions.Item>
                      <Descriptions.Item label="Schema">{tenantDetail.schema_name}</Descriptions.Item>
                      <Descriptions.Item label="Domains">
                        {tenantDetail.domains?.length
                          ? tenantDetail.domains.map((d, i) => <Tag key={i}>{d}</Tag>)
                          : <Text type="secondary">No domains</Text>
                        }
                      </Descriptions.Item>
                      <Descriptions.Item label="Plan">
                        <Space>
                          {tenantDetail.plan ? <Tag color="blue">{tenantDetail.plan}</Tag> : <Tag>None</Tag>}
                          <Button size="small" type="link" icon={<SwapOutlined />} onClick={() => setPlanModalVisible(true)}>
                            Change
                          </Button>
                        </Space>
                      </Descriptions.Item>
                      <Descriptions.Item label="Status">
                        <Badge
                          status={statusConfig[tenantDetail.status]?.badge || 'default'}
                          text={<span style={{ textTransform: 'capitalize' }}>{tenantDetail.status}</span>}
                        />
                      </Descriptions.Item>
                      <Descriptions.Item label="Created">
                        {new Date(tenantDetail.created_on).toLocaleDateString()}
                      </Descriptions.Item>
                      {tenantDetail.end_date && (
                        <Descriptions.Item label="Expires">
                          {new Date(tenantDetail.end_date).toLocaleDateString()}
                        </Descriptions.Item>
                      )}
                    </Descriptions>

                    <Divider orientation="left">Subscription Actions</Divider>
                    <Space direction="vertical" style={{ width: '100%' }} size="middle">
                      <Space.Compact style={{ width: '100%' }}>
                        <InputNumber
                          style={{ width: '60%' }}
                          value={extendDays}
                          onChange={(v) => setExtendDays(v || 30)}
                          min={1}
                          max={3650}
                          addonBefore="Extend by"
                          addonAfter="days"
                        />
                        <Button
                          style={{ width: '40%' }}
                          icon={<CalendarOutlined />}
                          onClick={() => handleAction(tenantDetail.id, 'extend', { days: extendDays })}
                          loading={tenantAction.isPending}
                        >
                          Extend
                        </Button>
                      </Space.Compact>

                      <Button
                        block
                        icon={<KeyOutlined />}
                        style={{ background: '#fffbeb', borderColor: '#fbbf24', color: '#92400e' }}
                        onClick={() => handleResetPassword(tenantDetail)}
                        loading={tenantAction.isPending}
                      >
                        Reset Admin Password
                      </Button>

                      <Row gutter={12}>
                        <Col span={12}>
                          {tenantDetail.status === 'suspended' ? (
                            <Button
                              block
                              type="primary"
                              icon={<PlayCircleOutlined />}
                              onClick={() => handleAction(tenantDetail.id, 'activate')}
                              loading={tenantAction.isPending}
                            >
                              Activate
                            </Button>
                          ) : (
                            <Popconfirm
                              title="Suspend this tenant?"
                              description="Tenant users will lose access immediately."
                              onConfirm={() => handleAction(tenantDetail.id, 'suspend')}
                              okText="Suspend"
                              okButtonProps={{ danger: true }}
                            >
                              <Button block danger icon={<StopOutlined />} loading={tenantAction.isPending}>
                                Suspend
                              </Button>
                            </Popconfirm>
                          )}
                        </Col>
                        <Col span={12}>
                          <Popconfirm
                            title={`Delete tenant "${tenantDetail.name}"?`}
                            description="This action cannot be undone."
                            onConfirm={() => handleDelete(tenantDetail)}
                            okText="Delete"
                            okButtonProps={{ danger: true }}
                          >
                            <Button block danger type="dashed" icon={<DeleteOutlined />}>
                              Delete Tenant
                            </Button>
                          </Popconfirm>
                        </Col>
                      </Row>
                    </Space>
                  </div>
                ),
              },
              {
                key: 'modules',
                label: <span><AppstoreOutlined /> Modules</span>,
                children: <TenantModulesPanel tenantId={tenantDetail.id} />,
              },
            ]}
          />
        )}
      </Drawer>

      {/* ── Create Tenant Modal ───────────────────────────────────────── */}
      <Modal
        title="Create New Tenant"
        open={createModalVisible}
        onCancel={() => { setCreateModalVisible(false); createForm.resetFields(); }}
        footer={null}
        width={520}
      >
        <Form form={createForm} layout="vertical" onFinish={handleCreate}>
          <Form.Item
            label="Organization Name"
            name="organization_name"
            rules={[{ required: true, message: 'Please enter organization name' }]}
          >
            <Input placeholder="e.g., Acme Corporation" />
          </Form.Item>
          <Form.Item
            label="Admin Email"
            name="admin_email"
            rules={[{ required: true, type: 'email', message: 'Please enter a valid email' }]}
          >
            <Input placeholder="admin@example.com" />
          </Form.Item>
          <Form.Item
            label="Admin Username"
            name="admin_username"
            rules={[{ required: true, message: 'Please enter admin username' }]}
          >
            <Input placeholder="admin" />
          </Form.Item>
          <Form.Item label="Initial Plan" name="plan_type">
            <Select placeholder="Select a plan (optional)" allowClear>
              {plans.map((p: SubscriptionPlan) => (
                <Select.Option key={p.id} value={p.plan_type}>
                  {p.name} - {p.plan_type}
                </Select.Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" block loading={createTenant.isPending}>
              Create Tenant
            </Button>
          </Form.Item>
        </Form>
      </Modal>

      {/* ── Edit Tenant Modal ─────────────────────────────────────────── */}
      <Modal
        title="Edit Tenant"
        open={editModalVisible}
        onCancel={() => { setEditModalVisible(false); editForm.resetFields(); }}
        footer={null}
      >
        <Form form={editForm} layout="vertical" onFinish={handleEdit}>
          <Form.Item
            label="Organization Name"
            name="name"
            rules={[{ required: true, message: 'Please enter organization name' }]}
          >
            <Input />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" block loading={tenantAction.isPending}>
              Save Changes
            </Button>
          </Form.Item>
        </Form>
      </Modal>

      {/* ── Change Plan Modal ─────────────────────────────────────────── */}
      <Modal
        title={`Change Plan for ${tenantDetail?.name || ''}`}
        open={planModalVisible}
        onCancel={() => setPlanModalVisible(false)}
        footer={null}
        width={700}
      >
        {plans.length === 0 ? (
          <Empty description="No subscription plans available" />
        ) : (
          <Row gutter={[16, 16]}>
            {plans.map((plan: SubscriptionPlan) => (
              <Col xs={24} sm={12} key={plan.id}>
                <Card
                  hoverable
                  style={{
                    borderRadius: 12,
                    border: tenantDetail?.plan === plan.name ? '2px solid #1890ff' : '1px solid #f0f0f0',
                  }}
                  onClick={() => {
                    Modal.confirm({
                      title: 'Change Subscription Plan',
                      content: `Are you sure you want to change this tenant's plan to "${plan.name}"? This may affect billing.`,
                      okText: 'Change Plan',
                      onOk: () => handleChangePlan(plan.id),
                    });
                  }}
                >
                  <div style={{ textAlign: 'center' }}>
                    <Title level={5} style={{ marginBottom: 4 }}>{plan.name}</Title>
                    <Text type="secondary">{plan.plan_type}</Text>
                    <Divider style={{ margin: '12px 0' }} />
                    <Title level={3} style={{ margin: 0, color: '#1890ff' }}>
                      {Number(plan.price).toLocaleString()}
                    </Title>
                    <Text type="secondary">/{plan.billing_cycle}</Text>
                    <Divider style={{ margin: '12px 0' }} />
                    <Space direction="vertical" size={4}>
                      <Text>{plan.max_users} users</Text>
                      <Text>{plan.max_storage_gb} GB storage</Text>
                      <Text>{plan.allowed_modules?.length || 0} modules</Text>
                      {plan.trial_days > 0 && <Tag color="orange">{plan.trial_days}-day trial</Tag>}
                    </Space>
                  </div>
                  {tenantDetail?.plan === plan.name && (
                    <div style={{ textAlign: 'center', marginTop: 12 }}>
                      <Tag color="blue">Current Plan</Tag>
                    </div>
                  )}
                </Card>
              </Col>
            ))}
          </Row>
        )}
      </Modal>
    </div>
  );
};

// ── Tenant Modules Sub-Panel ──────────────────────────────────────────────
const TenantModulesPanel = ({ tenantId }: { tenantId: number }) => {
  const { message } = App.useApp();
  const { data: modules = [], isLoading } = useTenantModules(tenantId);
  const toggleModule = useToggleTenantModule();

  const handleToggle = async (moduleName: string, checked: boolean) => {
    try {
      await toggleModule.mutateAsync({
        tenantId,
        modules: { [moduleName]: checked },
      });
      message.success(`Module ${checked ? 'enabled' : 'disabled'}`);
    } catch {
      message.error('Failed to update module');
    }
  };

  if (isLoading) return <Skeleton active paragraph={{ rows: 6 }} />;

  if (!modules.length) return <Empty description="No modules configured" />;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {modules.map((mod: any) => (
        <Card key={mod.module_name} size="small" style={{ borderRadius: 8 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <Text strong>{mod.module_title || mod.module_name}</Text>
              {mod.description && (
                <div><Text type="secondary" style={{ fontSize: 12 }}>{mod.description}</Text></div>
              )}
            </div>
            <Switch
              checked={mod.is_active}
              onChange={(checked) => handleToggle(mod.module_name, checked)}
              loading={toggleModule.isPending}
            />
          </div>
        </Card>
      ))}
    </div>
  );
};

export default TenantsTab;
