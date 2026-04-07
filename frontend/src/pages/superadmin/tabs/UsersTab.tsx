import {
  Card, Table, Tag, Button, Space, Badge, Avatar, Popconfirm, Modal, Form,
  Input, Select, App, Tooltip, Drawer, Descriptions, Tabs, Typography, Row,
  Col, Empty, Skeleton, Divider, Input as AntInput,
} from 'antd';
import {
  UserOutlined, PlusOutlined, ReloadOutlined, EditOutlined, StopOutlined,
  CheckCircleOutlined, LoginOutlined, SearchOutlined, KeyOutlined,
  HistoryOutlined, DeleteOutlined,
} from '@ant-design/icons';
import { useState, useMemo } from 'react';
import {
  useUsers, useSaveUser, useToggleUserStatus, useImpersonateUser,
  useImpersonationLogs, useTenants, useBulkDeleteUsers,
} from '../hooks/useSuperAdmin';
import { useQueryClient } from '@tanstack/react-query';
import type { CrossTenantUser, ImpersonationLog } from '../../../api/superadmin';

const { Text, Title } = Typography;
const { Search } = AntInput;

const cardStyle: React.CSSProperties = {
  borderRadius: 12,
  border: 'none',
  boxShadow: '0 2px 8px rgba(0, 0, 0, 0.06), 0 1px 2px rgba(0, 0, 0, 0.04)',
};

const UsersTab = () => {
  const { message } = App.useApp();
  const { data: usersData, isLoading } = useUsers();
  const users: CrossTenantUser[] = Array.isArray(usersData) ? usersData : (usersData as any)?.results || [];
  const { data: tenants = [] } = useTenants();
  const saveUser = useSaveUser();
  const toggleStatus = useToggleUserStatus();
  const impersonate = useImpersonateUser();
  const bulkDelete = useBulkDeleteUsers();
  const qc = useQueryClient();

  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const [modalVisible, setModalVisible] = useState(false);
  const [editing, setEditing] = useState<CrossTenantUser | null>(null);
  const [detailDrawer, setDetailDrawer] = useState(false);
  const [selectedUser, setSelectedUser] = useState<CrossTenantUser | null>(null);
  const [logsDrawer, setLogsDrawer] = useState(false);
  const [impersonateModal, setImpersonateModal] = useState(false);
  const [impersonateUserId, setImpersonateUserId] = useState<number | null>(null);
  const [searchText, setSearchText] = useState('');
  const [form] = Form.useForm();
  const [resetForm] = Form.useForm();
  const [resetModalVisible, setResetModalVisible] = useState(false);
  const [resetUserId, setResetUserId] = useState<number | null>(null);

  // Filter users
  const filteredUsers = useMemo(() => {
    if (!searchText) return users;
    const lower = searchText.toLowerCase();
    return users.filter(
      (u) =>
        u.username.toLowerCase().includes(lower) ||
        u.email.toLowerCase().includes(lower) ||
        (u.first_name || '').toLowerCase().includes(lower) ||
        (u.last_name || '').toLowerCase().includes(lower)
    );
  }, [users, searchText]);

  const handleSave = async (values: any) => {
    try {
      await saveUser.mutateAsync({ id: editing?.id, data: values });
      message.success(editing ? 'User updated successfully' : 'User created successfully');
      setModalVisible(false);
      form.resetFields();
      setEditing(null);
    } catch {
      message.error(`Failed to ${editing ? 'update' : 'create'} user`);
    }
  };

  const handleToggle = async (user: CrossTenantUser) => {
    try {
      await toggleStatus.mutateAsync({ userId: user.id, isActive: !user.is_active, tenantId: user.tenant_id });
      message.success(`User ${user.is_active ? 'disabled' : 'enabled'} successfully`);
    } catch {
      message.error('Failed to change user status');
    }
  };

  const handleImpersonate = async (user: CrossTenantUser, tenantId?: number) => {
    const targetTenantId = tenantId || user.tenant_id || user.tenants?.[0]?.tenant_id;
    if (!targetTenantId) {
      message.warning('User has no tenant assigned');
      return;
    }
    try {
      const data = await impersonate.mutateAsync({ userId: user.id, tenantId: targetTenantId });
      const impersonationData = {
        token: data.token,
        tenant_domain: data.tenant_domain,
        user: data.user?.username || 'admin',
        session_id: data.session_id,
      };
      // Store impersonation data temporarily in sessionStorage (more secure than URL params)
      sessionStorage.setItem('pending_impersonation', JSON.stringify(impersonationData));
      window.open('/?impersonation=pending', '_blank');
      message.success(`Impersonating ${user.username} in ${data.tenant_name}`);
      setImpersonateModal(false);
    } catch (err: any) {
      message.error(err?.response?.data?.error || 'Failed to impersonate user');
    }
  };

  const openImpersonateWithPicker = (user: CrossTenantUser) => {
    if (!user.tenants || user.tenants.length <= 1) {
      handleImpersonate(user);
      return;
    }
    setImpersonateUserId(user.id);
    setSelectedUser(user);
    setImpersonateModal(true);
  };

  const handleResetPassword = async (values: { password: string }) => {
    if (!resetUserId) return;
    try {
      await saveUser.mutateAsync({ id: resetUserId, data: { password: values.password } });
      message.success('Password reset successfully');
      setResetModalVisible(false);
      resetForm.resetFields();
      setResetUserId(null);
    } catch {
      message.error('Failed to reset password');
    }
  };

  const openUserDetail = (user: CrossTenantUser) => {
    setSelectedUser(user);
    setDetailDrawer(true);
  };

  const handleBulkDelete = () => {
    const ids = selectedRowKeys.map(Number);
    const superadminSelected = filteredUsers.filter(u => ids.includes(u.id) && u.is_superuser);
    if (superadminSelected.length > 0) {
      message.error('Cannot delete superadmin users. Deselect them first.');
      return;
    }
    Modal.confirm({
      title: `Delete ${ids.length} user(s)?`,
      content: 'This will permanently remove the selected users and all their tenant assignments. This action cannot be undone.',
      okText: 'Delete',
      okType: 'danger',
      cancelText: 'Cancel',
      onOk: async () => {
        try {
          const res = await bulkDelete.mutateAsync(ids);
          message.success(res.status || `${ids.length} user(s) deleted`);
          setSelectedRowKeys([]);
        } catch (err: any) {
          message.error(err?.response?.data?.error || 'Failed to delete users');
        }
      },
    });
  };

  const rowSelection = {
    selectedRowKeys,
    onChange: (keys: React.Key[]) => setSelectedRowKeys(keys),
    getCheckboxProps: (record: CrossTenantUser) => ({
      disabled: record.is_superuser,
    }),
  };

  const columns = [
    {
      title: 'User',
      key: 'user',
      sorter: (a: CrossTenantUser, b: CrossTenantUser) => a.username.localeCompare(b.username),
      render: (_: any, record: CrossTenantUser) => (
        <Space>
          <Avatar
            icon={<UserOutlined />}
            style={{
              background: record.is_superuser
                ? 'linear-gradient(135deg, #ff4d4f, #ff7a45)'
                : 'linear-gradient(135deg, #1890ff, #096dd9)',
            }}
          />
          <div>
            <a onClick={() => openUserDetail(record)} style={{ fontWeight: 600 }}>
              {record.username}
            </a>
            {record.is_superuser && <Tag color="red" style={{ marginLeft: 8 }}>SuperAdmin</Tag>}
            <div style={{ fontSize: 12, color: '#8c8c8c' }}>
              {[record.first_name, record.last_name].filter(Boolean).join(' ') || record.email}
            </div>
          </div>
        </Space>
      ),
    },
    {
      title: 'Email',
      dataIndex: 'email',
      key: 'email',
      responsive: ['md' as const],
    },
    {
      title: 'Tenants',
      key: 'tenant',
      render: (_: any, record: CrossTenantUser) => {
        if (record.tenants && record.tenants.length > 0) {
          return (
            <Space wrap size={4}>
              {record.tenants.slice(0, 3).map((t) => (
                <Tag key={t.tenant_id} color="blue">
                  {t.tenant_name} <Text type="secondary" style={{ fontSize: 11 }}>({t.role})</Text>
                </Tag>
              ))}
              {record.tenants.length > 3 && (
                <Tag>+{record.tenants.length - 3} more</Tag>
              )}
            </Space>
          );
        }
        return record.tenant_name ? <Tag color="blue">{record.tenant_name}</Tag> : <Text type="secondary">-</Text>;
      },
    },
    {
      title: 'Status',
      dataIndex: 'is_active',
      key: 'is_active',
      filters: [
        { text: 'Active', value: true },
        { text: 'Inactive', value: false },
      ],
      onFilter: (value: any, record: CrossTenantUser) => record.is_active === value,
      render: (active: boolean) => (
        <Badge status={active ? 'success' : 'default'} text={active ? 'Active' : 'Inactive'} />
      ),
    },
    {
      title: 'Last Login',
      dataIndex: 'last_login',
      key: 'last_login',
      responsive: ['lg' as const],
      render: (date: string | null) =>
        date ? <Text type="secondary">{new Date(date).toLocaleDateString()}</Text> : <Text type="secondary">Never</Text>,
    },
    {
      title: 'Actions',
      key: 'actions',
      width: 220,
      render: (_: any, record: CrossTenantUser) => (
        <Space size={4}>
          <Tooltip title="Edit">
            <Button
              size="small"
              type="link"
              icon={<EditOutlined />}
              onClick={() => {
                setEditing(record);
                form.setFieldsValue({
                  username: record.username,
                  email: record.email,
                  first_name: record.first_name,
                  last_name: record.last_name,
                });
                setModalVisible(true);
              }}
            />
          </Tooltip>
          {!record.is_superuser && (
            <Tooltip title="Login as this user">
              <Button
                size="small"
                type="link"
                icon={<LoginOutlined />}
                onClick={() => openImpersonateWithPicker(record)}
                loading={impersonate.isPending}
              />
            </Tooltip>
          )}
          <Tooltip title="Reset Password">
            <Button
              size="small"
              type="link"
              icon={<KeyOutlined />}
              onClick={() => {
                setResetUserId(record.id);
                setResetModalVisible(true);
              }}
            />
          </Tooltip>
          <Popconfirm
            title={`${record.is_active ? 'Disable' : 'Enable'} User`}
            description={`Are you sure you want to ${record.is_active ? 'disable' : 'enable'} this user?`}
            onConfirm={() => handleToggle(record)}
            okText="Yes"
            cancelText="No"
            okButtonProps={{ danger: record.is_active }}
          >
            <Tooltip title={record.is_active ? 'Disable' : 'Enable'}>
              <Button
                size="small"
                type="link"
                danger={record.is_active}
                icon={record.is_active ? <StopOutlined /> : <CheckCircleOutlined />}
              />
            </Tooltip>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Card style={cardStyle}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <Title level={5} style={{ margin: 0 }}>User Management</Title>
          <Space>
            <Button icon={<HistoryOutlined />} onClick={() => setLogsDrawer(true)}>
              Impersonation Logs
            </Button>
            {selectedRowKeys.length > 0 && (
              <Button
                danger
                icon={<DeleteOutlined />}
                onClick={handleBulkDelete}
                loading={bulkDelete.isPending}
              >
                Delete Selected ({selectedRowKeys.length})
              </Button>
            )}
            <Button icon={<ReloadOutlined />} onClick={() => qc.invalidateQueries({ queryKey: ['superadmin-users'] })}>
              Refresh
            </Button>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => { setEditing(null); form.resetFields(); setModalVisible(true); }}
              style={{ borderRadius: 8 }}
            >
              Add User
            </Button>
          </Space>
        </div>

        <Row gutter={16} style={{ marginBottom: 16 }}>
          <Col xs={24} sm={12} md={8}>
            <Search
              placeholder="Search users..."
              allowClear
              onChange={(e) => setSearchText(e.target.value)}
              prefix={<SearchOutlined />}
            />
          </Col>
          <Col>
            <Text type="secondary">{filteredUsers.length} user{filteredUsers.length !== 1 ? 's' : ''}</Text>
          </Col>
        </Row>

        <Table
          columns={columns}
          dataSource={filteredUsers}
          rowKey={(r) => r.id}
          rowSelection={rowSelection}
          loading={isLoading}
          pagination={{ pageSize: 10, showSizeChanger: true, showTotal: (total) => `Total ${total} users` }}
        />
      </Card>

      {/* ── User Detail Drawer ────────────────────────────────────────── */}
      <Drawer
        title={
          <Space>
            <Avatar icon={<UserOutlined />} />
            <span>{selectedUser?.username || 'User Details'}</span>
            {selectedUser?.is_superuser && <Tag color="red">SuperAdmin</Tag>}
          </Space>
        }
        placement="right"
        styles={{ wrapper: { width: '540px' } }}
        open={detailDrawer}
        onClose={() => { setDetailDrawer(false); setSelectedUser(null); }}
      >
        {selectedUser && (
          <div>
            <Descriptions column={1} bordered size="small" style={{ marginBottom: 24 }}>
              <Descriptions.Item label="Username">{selectedUser.username}</Descriptions.Item>
              <Descriptions.Item label="Email">{selectedUser.email}</Descriptions.Item>
              <Descriptions.Item label="First Name">{selectedUser.first_name || '-'}</Descriptions.Item>
              <Descriptions.Item label="Last Name">{selectedUser.last_name || '-'}</Descriptions.Item>
              <Descriptions.Item label="Status">
                <Badge status={selectedUser.is_active ? 'success' : 'default'} text={selectedUser.is_active ? 'Active' : 'Inactive'} />
              </Descriptions.Item>
              <Descriptions.Item label="Date Joined">
                {selectedUser.date_joined ? new Date(selectedUser.date_joined).toLocaleDateString() : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="Last Login">
                {selectedUser.last_login ? new Date(selectedUser.last_login).toLocaleString() : 'Never'}
              </Descriptions.Item>
              <Descriptions.Item label="Staff">{selectedUser.is_staff ? 'Yes' : 'No'}</Descriptions.Item>
              <Descriptions.Item label="SuperUser">{selectedUser.is_superuser ? 'Yes' : 'No'}</Descriptions.Item>
            </Descriptions>

            <Divider orientation="left">Tenant Roles</Divider>
            {selectedUser.tenants && selectedUser.tenants.length > 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {selectedUser.tenants.map((t) => (
                  <Card key={t.tenant_id} size="small" style={{ borderRadius: 8 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div>
                        <Text strong>{t.tenant_name}</Text>
                        <div>
                          <Tag color="blue">{t.role}</Tag>
                          <Badge status={t.is_active ? 'success' : 'default'} text={t.is_active ? 'Active' : 'Inactive'} />
                        </div>
                      </div>
                      {!selectedUser.is_superuser && (
                        <Tooltip title={`Login as ${selectedUser.username} in ${t.tenant_name}`}>
                          <Button
                            size="small"
                            icon={<LoginOutlined />}
                            onClick={() => handleImpersonate(selectedUser, t.tenant_id)}
                            loading={impersonate.isPending}
                          >
                            Impersonate
                          </Button>
                        </Tooltip>
                      )}
                    </div>
                  </Card>
                ))}
              </div>
            ) : (
              <Empty description="No tenant assignments" />
            )}
          </div>
        )}
      </Drawer>

      {/* ── Create/Edit User Modal ────────────────────────────────────── */}
      <Modal
        title={editing ? 'Edit User' : 'Create New User'}
        open={modalVisible}
        onCancel={() => { setModalVisible(false); form.resetFields(); setEditing(null); }}
        footer={null}
        width={520}
      >
        <Form form={form} layout="vertical" onFinish={handleSave}>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item label="First Name" name="first_name">
                <Input placeholder="John" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item label="Last Name" name="last_name">
                <Input placeholder="Doe" />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item
            label="Username"
            name="username"
            rules={[{ required: true, message: 'Please enter username' }]}
          >
            <Input placeholder="Enter username" disabled={!!editing} />
          </Form.Item>
          <Form.Item
            label="Email"
            name="email"
            rules={[{ required: true, type: 'email', message: 'Please enter valid email' }]}
          >
            <Input type="email" placeholder="Enter email" />
          </Form.Item>
          {!editing && (
            <Form.Item
              label="Password"
              name="password"
              rules={[
                { required: true, message: 'Please enter password' },
                { min: 8, message: 'Password must be at least 8 characters' },
                { pattern: /(?=.*[A-Z])/, message: 'Must contain at least one uppercase letter' },
                { pattern: /(?=.*[0-9])/, message: 'Must contain at least one number' },
              ]}
            >
              <Input.Password placeholder="Enter password" />
            </Form.Item>
          )}
          {!editing && (
            <Form.Item label="Assign to Tenant" name="tenant_id">
              <Select placeholder="Select tenant (optional)" allowClear showSearch optionFilterProp="label">
                {tenants.map((t) => (
                  <Select.Option key={t.id} value={t.id} label={t.name}>
                    {t.name}
                  </Select.Option>
                ))}
              </Select>
            </Form.Item>
          )}
          <Form.Item label="Role" name="role">
            <Select placeholder="Select role">
              <Select.Option value="admin">Administrator</Select.Option>
              <Select.Option value="senior_manager">Senior Manager</Select.Option>
              <Select.Option value="manager">Manager</Select.Option>
              <Select.Option value="user">User</Select.Option>
              <Select.Option value="viewer">Viewer</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" block loading={saveUser.isPending}>
              {editing ? 'Save Changes' : 'Create User'}
            </Button>
          </Form.Item>
        </Form>
      </Modal>

      {/* ── Reset Password Modal ──────────────────────────────────────── */}
      <Modal
        title="Reset Password"
        open={resetModalVisible}
        onCancel={() => { setResetModalVisible(false); resetForm.resetFields(); setResetUserId(null); }}
        footer={null}
      >
        <Form form={resetForm} layout="vertical" onFinish={handleResetPassword}>
          <Form.Item
            label="New Password"
            name="password"
            rules={[
              { required: true, message: 'Please enter new password' },
              { min: 8, message: 'Password must be at least 8 characters' },
            ]}
          >
            <Input.Password placeholder="Enter new password" />
          </Form.Item>
          <Form.Item
            label="Confirm Password"
            name="confirm_password"
            dependencies={['password']}
            rules={[
              { required: true, message: 'Please confirm password' },
              ({ getFieldValue }) => ({
                validator(_, value) {
                  if (!value || getFieldValue('password') === value) return Promise.resolve();
                  return Promise.reject(new Error('Passwords do not match'));
                },
              }),
            ]}
          >
            <Input.Password placeholder="Confirm new password" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" block loading={saveUser.isPending}>
              Reset Password
            </Button>
          </Form.Item>
        </Form>
      </Modal>

      {/* ── Impersonate Tenant Picker Modal ───────────────────────────── */}
      <Modal
        title="Select Tenant to Impersonate"
        open={impersonateModal}
        onCancel={() => { setImpersonateModal(false); setImpersonateUserId(null); }}
        footer={null}
      >
        {selectedUser?.tenants && selectedUser.tenants.length > 0 ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {selectedUser.tenants.map((t) => (
              <Card
                key={t.tenant_id}
                hoverable
                size="small"
                style={{ borderRadius: 8 }}
                onClick={() => impersonateUserId && handleImpersonate(selectedUser, t.tenant_id)}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div>
                    <Text strong>{t.tenant_name}</Text>
                    <Tag color="blue" style={{ marginLeft: 8 }}>{t.role}</Tag>
                  </div>
                  <LoginOutlined />
                </div>
              </Card>
            ))}
          </div>
        ) : (
          <Empty description="No tenants available" />
        )}
      </Modal>

      {/* ── Impersonation Logs Drawer ─────────────────────────────────── */}
      <Drawer
        title={<Space><HistoryOutlined /> Impersonation Logs</Space>}
        placement="right"
        styles={{ wrapper: { width: '640px' } }}
        open={logsDrawer}
        onClose={() => setLogsDrawer(false)}
      >
        <ImpersonationLogsPanel />
      </Drawer>
    </div>
  );
};

// ── Impersonation Logs Panel ──────────────────────────────────────────────
const ImpersonationLogsPanel = () => {
  const { data: logsData, isLoading } = useImpersonationLogs();
  const logs: ImpersonationLog[] = Array.isArray(logsData) ? logsData : (logsData as any)?.results || [];

  if (isLoading) return <Skeleton active paragraph={{ rows: 6 }} />;
  if (!logs.length) return <Empty description="No impersonation logs" />;

  const columns = [
    {
      title: 'Admin',
      dataIndex: 'superadmin',
      key: 'superadmin',
      render: (v: string) => <Text strong>{v}</Text>,
    },
    {
      title: 'Target User',
      dataIndex: 'target_user',
      key: 'target_user',
    },
    {
      title: 'Tenant',
      dataIndex: 'target_tenant',
      key: 'target_tenant',
      render: (v: string) => <Tag color="blue">{v}</Tag>,
    },
    {
      title: 'Started',
      dataIndex: 'started_at',
      key: 'started_at',
      render: (v: string) => v ? new Date(v).toLocaleString() : '-',
    },
    {
      title: 'Ended',
      dataIndex: 'ended_at',
      key: 'ended_at',
      render: (v: string | null) => v ? new Date(v).toLocaleString() : <Tag color="orange">Active</Tag>,
    },
    {
      title: 'IP',
      dataIndex: 'ip_address',
      key: 'ip_address',
      render: (v: string) => <Text type="secondary" style={{ fontFamily: 'monospace' }}>{v}</Text>,
    },
  ];

  return (
    <Table
      columns={columns}
      dataSource={logs}
      rowKey="id"
      size="small"
      pagination={{ pageSize: 10 }}
    />
  );
};

export default UsersTab;
