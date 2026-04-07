import { useState } from 'react';
import {
  Table, Tag, Button, Space, Modal, Form, Input, InputNumber, Switch, Select,
  App, Empty, Typography, Row, Col, Tooltip, Badge, Popconfirm, DatePicker,
} from 'antd';
import {
  PlusOutlined, DeleteOutlined, EditOutlined, CopyOutlined,
  ExclamationCircleOutlined,
} from '@ant-design/icons';
import { Key, RefreshCw } from 'lucide-react';
import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';
import {
  useAPIKeys, useCreateAPIKey, useUpdateAPIKey, useDeleteAPIKey, useTenants,
} from '../hooks/useSuperAdmin';
import type { APIKeyItem } from '../hooks/useSuperAdmin';

dayjs.extend(relativeTime);

const { Text } = Typography;

export default function APIKeysSection() {
  const { message } = App.useApp();
  const { data: apiKeys = [], isLoading } = useAPIKeys();
  const { data: tenants = [] } = useTenants();
  const createAPIKey = useCreateAPIKey();
  const updateAPIKey = useUpdateAPIKey();
  const deleteAPIKey = useDeleteAPIKey();

  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<APIKeyItem | null>(null);
  const [form] = Form.useForm();

  // Holds the newly created key (shown once only)
  const [newKeyData, setNewKeyData] = useState<{ api_key: string; api_secret: string } | null>(null);

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({ key_type: 'Production', rate_limit: 1000, is_active: true });
    setModalOpen(true);
  };

  const openEdit = (record: APIKeyItem) => {
    setEditing(record);
    form.setFieldsValue({
      tenant_id: record.tenant_id,
      key_name: record.key_name,
      key_type: record.key_type,
      allowed_ips: record.allowed_ips,
      rate_limit: record.rate_limit,
      is_active: record.is_active,
      expires_at: record.expires_at ? dayjs(record.expires_at) : null,
    });
    setModalOpen(true);
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      const payload = {
        ...values,
        expires_at: values.expires_at ? values.expires_at.toISOString() : null,
      };

      if (editing) {
        await updateAPIKey.mutateAsync({ id: editing.id, data: payload });
        message.success('API key updated');
      } else {
        const res = await createAPIKey.mutateAsync(payload);
        message.success('API key created');
        if (res?.api_key) {
          setNewKeyData({ api_key: res.api_key, api_secret: res.api_secret });
        }
      }
      setModalOpen(false);
      form.resetFields();
      setEditing(null);
    } catch (err: any) {
      if (err?.errorFields) return;
      message.error(err?.response?.data?.error || 'Operation failed');
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await deleteAPIKey.mutateAsync(id);
      message.success('API key revoked');
    } catch {
      message.error('Failed to revoke API key');
    }
  };

  const handleRegenerate = async (record: APIKeyItem) => {
    try {
      const res = await updateAPIKey.mutateAsync({ id: record.id, data: { regenerate: true } });
      message.success('API key regenerated');
      if (res?.api_key) {
        setNewKeyData({ api_key: res.api_key, api_secret: res.api_secret });
      }
    } catch {
      message.error('Failed to regenerate API key');
    }
  };

  const handleToggleActive = async (record: APIKeyItem) => {
    try {
      await updateAPIKey.mutateAsync({ id: record.id, data: { is_active: !record.is_active } });
      message.success(`API key ${!record.is_active ? 'activated' : 'deactivated'}`);
    } catch {
      message.error('Failed to update API key');
    }
  };

  const isExpired = (expiresAt: string | null): boolean => {
    if (!expiresAt) return false;
    return dayjs(expiresAt).isBefore(dayjs());
  };

  const columns = [
    {
      title: 'Name',
      dataIndex: 'key_name',
      key: 'name',
      render: (v: string, r: APIKeyItem) => (
        <div>
          <Text strong>{v}</Text>
          <div><Text type="secondary" style={{ fontSize: 12 }}>{r.tenant_name}</Text></div>
        </div>
      ),
    },
    {
      title: 'Key',
      dataIndex: 'api_key',
      key: 'key',
      width: 200,
      render: (v: string) => (
        <Space>
          <Text style={{ fontFamily: 'monospace', fontSize: 12 }}>{v}</Text>
          <Tooltip title="Copy masked key">
            <Button
              size="small"
              type="text"
              icon={<CopyOutlined />}
              onClick={() => {
                navigator.clipboard.writeText(v);
                message.success('Copied to clipboard');
              }}
            />
          </Tooltip>
        </Space>
      ),
    },
    {
      title: 'Type',
      dataIndex: 'key_type',
      key: 'type',
      width: 110,
      render: (v: string) => (
        <Tag color={v === 'Production' ? 'blue' : 'orange'}>{v}</Tag>
      ),
    },
    {
      title: 'Permissions',
      dataIndex: 'rate_limit',
      key: 'rate_limit',
      width: 120,
      render: (v: number) => (
        <Tooltip title="Requests per hour">
          <Text style={{ fontSize: 12 }}>{v?.toLocaleString()} req/hr</Text>
        </Tooltip>
      ),
    },
    {
      title: 'Created',
      dataIndex: 'created_at',
      key: 'created',
      width: 110,
      render: (v: string) => (
        <Tooltip title={dayjs(v).format('YYYY-MM-DD HH:mm')}>
          <Text style={{ fontSize: 12 }}>{dayjs(v).format('MMM D, YYYY')}</Text>
        </Tooltip>
      ),
    },
    {
      title: 'Last Used',
      dataIndex: 'last_used_at',
      key: 'last_used',
      width: 120,
      render: (v: string | null) => {
        if (!v) return <Text type="secondary" style={{ fontSize: 12 }}>Never</Text>;
        return (
          <Tooltip title={dayjs(v).format('YYYY-MM-DD HH:mm')}>
            <Text style={{ fontSize: 12 }}>{dayjs(v).fromNow()}</Text>
          </Tooltip>
        );
      },
    },
    {
      title: 'Expires',
      dataIndex: 'expires_at',
      key: 'expires',
      width: 120,
      render: (v: string | null) => {
        if (!v) return <Text type="secondary" style={{ fontSize: 12 }}>Never</Text>;
        const expired = isExpired(v);
        return (
          <Tooltip title={dayjs(v).format('YYYY-MM-DD HH:mm')}>
            <Text type={expired ? 'danger' : undefined} style={{ fontSize: 12 }}>
              {expired ? 'Expired' : dayjs(v).fromNow()}
            </Text>
          </Tooltip>
        );
      },
    },
    {
      title: 'Status',
      key: 'status',
      width: 90,
      render: (_: any, r: APIKeyItem) => {
        if (isExpired(r.expires_at)) {
          return <Tag color="red">Expired</Tag>;
        }
        return (
          <Switch
            size="small"
            checked={r.is_active}
            checkedChildren="Active"
            unCheckedChildren="Off"
            onChange={() => handleToggleActive(r)}
          />
        );
      },
    },
    {
      title: 'Actions',
      key: 'actions',
      width: 140,
      render: (_: any, r: APIKeyItem) => (
        <Space size={4}>
          <Tooltip title="Edit">
            <Button size="small" type="text" icon={<EditOutlined />} onClick={() => openEdit(r)} />
          </Tooltip>
          <Popconfirm
            title="Regenerate API key?"
            description="The current key will be invalidated. This cannot be undone."
            onConfirm={() => handleRegenerate(r)}
            okText="Regenerate"
            okButtonProps={{ danger: true }}
          >
            <Tooltip title="Regenerate Key">
              <Button size="small" type="text" icon={<RefreshCw size={14} />} />
            </Tooltip>
          </Popconfirm>
          <Popconfirm
            title="Revoke this API key?"
            description="This will permanently delete the key."
            onConfirm={() => handleDelete(r.id)}
            okText="Revoke"
            okButtonProps={{ danger: true }}
          >
            <Tooltip title="Revoke / Delete">
              <Button size="small" type="text" danger icon={<DeleteOutlined />} />
            </Tooltip>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Space>
          <Key size={20} style={{ color: '#2471a3' }} />
          <Typography.Title level={5} style={{ margin: 0 }}>API Keys</Typography.Title>
          <Badge count={apiKeys.length} style={{ backgroundColor: '#2471a3' }} />
        </Space>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate} style={{ backgroundColor: '#2471a3' }}>
          Generate API Key
        </Button>
      </div>

      <Table
        dataSource={apiKeys}
        columns={columns}
        rowKey="id"
        size="middle"
        loading={isLoading}
        pagination={{ pageSize: 10, showSizeChanger: false, showTotal: (t) => `${t} keys` }}
        locale={{ emptyText: <Empty description="No API keys" /> }}
      />

      {/* Create/Edit Modal */}
      <Modal
        title={editing ? 'Edit API Key' : 'Generate API Key'}
        open={modalOpen}
        onCancel={() => { setModalOpen(false); setEditing(null); form.resetFields(); }}
        onOk={handleSubmit}
        confirmLoading={createAPIKey.isPending || updateAPIKey.isPending}
        okText={editing ? 'Update' : 'Generate'}
        width={520}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          {!editing && (
            <Form.Item label="Tenant" name="tenant_id" rules={[{ required: true, message: 'Select a tenant' }]}>
              <Select
                placeholder="Select tenant (optional for global key)"
                showSearch
                optionFilterProp="children"
                allowClear
                options={tenants.map((t: any) => ({ value: t.id, label: t.name }))}
              />
            </Form.Item>
          )}
          <Form.Item label="Key Name" name="key_name" rules={[{ required: true, message: 'Enter a name' }]}>
            <Input placeholder="e.g., Production API Key" />
          </Form.Item>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item label="Key Type" name="key_type">
                <Select>
                  <Select.Option value="Production">Production</Select.Option>
                  <Select.Option value="Sandbox">Sandbox</Select.Option>
                </Select>
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item label="Rate Limit (req/hr)" name="rate_limit">
                <InputNumber min={100} max={100000} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item
            label="Allowed IPs"
            name="allowed_ips"
            extra="Comma-separated list of IPs. Leave empty to allow all."
          >
            <Input placeholder="e.g., 192.168.1.1, 10.0.0.0/8" />
          </Form.Item>
          <Form.Item label="Expiry Date" name="expires_at" extra="Leave empty for a key that never expires.">
            <DatePicker
              style={{ width: '100%' }}
              showTime
              disabledDate={(d) => d.isBefore(dayjs())}
            />
          </Form.Item>
          {editing && (
            <Form.Item label="Active" name="is_active" valuePropName="checked">
              <Switch checkedChildren="Active" unCheckedChildren="Revoked" />
            </Form.Item>
          )}
        </Form>
      </Modal>

      {/* New Key Display Modal (shown once on creation/regeneration) */}
      <Modal
        title="API Key Generated"
        open={!!newKeyData}
        onOk={() => setNewKeyData(null)}
        onCancel={() => setNewKeyData(null)}
        cancelButtonProps={{ style: { display: 'none' } }}
        width={520}
      >
        <div style={{ marginBottom: 16 }}>
          <ExclamationCircleOutlined style={{ color: '#faad14', marginRight: 8 }} />
          <Text strong>Save these credentials now -- they will not be shown again.</Text>
        </div>

        <div style={{ marginBottom: 12 }}>
          <Text type="secondary" style={{ fontSize: 12 }}>API Key</Text>
          <Input.TextArea
            value={newKeyData?.api_key || ''}
            readOnly
            rows={2}
            style={{ fontFamily: 'monospace', marginTop: 4 }}
          />
          <Button
            block
            size="small"
            style={{ marginTop: 4 }}
            icon={<CopyOutlined />}
            onClick={() => {
              if (newKeyData?.api_key) {
                navigator.clipboard.writeText(newKeyData.api_key);
                message.success('API key copied');
              }
            }}
          >
            Copy API Key
          </Button>
        </div>

        <div>
          <Text type="secondary" style={{ fontSize: 12 }}>API Secret</Text>
          <Input.TextArea
            value={newKeyData?.api_secret || ''}
            readOnly
            rows={2}
            style={{ fontFamily: 'monospace', marginTop: 4 }}
          />
          <Button
            block
            size="small"
            style={{ marginTop: 4 }}
            icon={<CopyOutlined />}
            onClick={() => {
              if (newKeyData?.api_secret) {
                navigator.clipboard.writeText(newKeyData.api_secret);
                message.success('API secret copied');
              }
            }}
          >
            Copy API Secret
          </Button>
        </div>
      </Modal>
    </div>
  );
}
