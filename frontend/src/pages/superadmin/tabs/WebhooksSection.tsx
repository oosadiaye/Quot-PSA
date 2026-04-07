import { useState } from 'react';
import {
  Table, Tag, Button, Space, Modal, Form, Input, InputNumber, Switch, Select,
  App, Empty, Typography, Row, Col, Tooltip, Badge, Drawer, Popconfirm,
} from 'antd';
import {
  PlusOutlined, DeleteOutlined, EditOutlined, SendOutlined,
  CheckCircleOutlined, CloseCircleOutlined, HistoryOutlined,
  ExclamationCircleOutlined,
} from '@ant-design/icons';
import { Webhook, RefreshCw, Send, Eye } from 'lucide-react';
import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';
import {
  useWebhooks, useCreateWebhook, useUpdateWebhook, useDeleteWebhook,
  useTestWebhook, useWebhookDeliveries,
} from '../hooks/useSuperAdmin';
import type { WebhookConfigItem, WebhookDeliveryItem } from '../hooks/useSuperAdmin';
import { useTenants } from '../hooks/useSuperAdmin';

dayjs.extend(relativeTime);

const { Text } = Typography;

const WEBHOOK_EVENTS = [
  { value: 'tenant.created', label: 'Tenant Created' },
  { value: 'tenant.updated', label: 'Tenant Updated' },
  { value: 'tenant.suspended', label: 'Tenant Suspended' },
  { value: 'subscription.created', label: 'Subscription Created' },
  { value: 'subscription.renewed', label: 'Subscription Renewed' },
  { value: 'subscription.cancelled', label: 'Subscription Cancelled' },
  { value: 'payment.success', label: 'Payment Success' },
  { value: 'payment.failed', label: 'Payment Failed' },
  { value: 'user.created', label: 'User Created' },
  { value: 'user.login', label: 'User Login' },
];

export default function WebhooksSection() {
  const { message } = App.useApp();
  const { data: webhooks = [], isLoading } = useWebhooks();
  const { data: tenants = [] } = useTenants();
  const createWebhook = useCreateWebhook();
  const updateWebhook = useUpdateWebhook();
  const deleteWebhook = useDeleteWebhook();
  const testWebhook = useTestWebhook();

  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<WebhookConfigItem | null>(null);
  const [deliveryWebhookId, setDeliveryWebhookId] = useState<number | null>(null);
  const [deliveryPage, setDeliveryPage] = useState(1);
  const { data: deliveriesData } = useWebhookDeliveries(deliveryWebhookId, deliveryPage);

  const [form] = Form.useForm();
  const [secretKeyVisible, setSecretKeyVisible] = useState<string | null>(null);

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({ timeout_seconds: 30, retry_count: 3, is_active: true });
    setModalOpen(true);
  };

  const openEdit = (record: WebhookConfigItem) => {
    setEditing(record);
    form.setFieldsValue({
      tenant_id: record.tenant_id,
      webhook_name: record.webhook_name,
      webhook_url: record.webhook_url,
      subscribed_events: record.subscribed_events,
      timeout_seconds: record.timeout_seconds,
      retry_count: record.retry_count,
      is_active: record.is_active,
    });
    setModalOpen(true);
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      if (editing) {
        await updateWebhook.mutateAsync({ id: editing.id, data: values });
        message.success('Webhook updated');
      } else {
        const res = await createWebhook.mutateAsync(values);
        message.success('Webhook created');
        if (res?.secret_key) {
          setSecretKeyVisible(res.secret_key);
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
      await deleteWebhook.mutateAsync(id);
      message.success('Webhook deleted');
    } catch {
      message.error('Failed to delete webhook');
    }
  };

  const handleTest = async (id: number) => {
    try {
      const res = await testWebhook.mutateAsync(id);
      if (res?.status === 'Success') {
        message.success(`Test delivered (${res.status_code}) in ${res.duration_ms}ms`);
      } else {
        message.warning(`Test failed: ${res?.error || `Status ${res?.status_code}`}`);
      }
    } catch (err: any) {
      message.error(err?.response?.data?.error || 'Webhook test failed');
    }
  };

  const handleToggleActive = async (record: WebhookConfigItem) => {
    try {
      await updateWebhook.mutateAsync({ id: record.id, data: { is_active: !record.is_active } });
      message.success(`Webhook ${!record.is_active ? 'activated' : 'deactivated'}`);
    } catch {
      message.error('Failed to update webhook');
    }
  };

  const getStatusColor = (code: number | null): string => {
    if (!code) return 'default';
    if (code >= 200 && code < 300) return 'success';
    if (code >= 400) return 'error';
    return 'warning';
  };

  const columns = [
    {
      title: 'Name',
      dataIndex: 'webhook_name',
      key: 'name',
      render: (v: string, r: WebhookConfigItem) => (
        <div>
          <Text strong>{v}</Text>
          <div><Text type="secondary" style={{ fontSize: 12 }}>{r.tenant_name}</Text></div>
        </div>
      ),
    },
    {
      title: 'URL',
      dataIndex: 'webhook_url',
      key: 'url',
      ellipsis: true,
      width: 220,
      render: (v: string) => (
        <Tooltip title={v}>
          <Text style={{ fontFamily: 'monospace', fontSize: 12 }}>{v.length > 40 ? v.substring(0, 40) + '...' : v}</Text>
        </Tooltip>
      ),
    },
    {
      title: 'Events',
      dataIndex: 'subscribed_events',
      key: 'events',
      width: 200,
      render: (events: string[]) => (
        <Space wrap size={4}>
          {(events || []).slice(0, 2).map((e) => (
            <Tag key={e} color="blue" style={{ fontSize: 11 }}>{e}</Tag>
          ))}
          {(events || []).length > 2 && (
            <Tooltip title={(events || []).slice(2).join(', ')}>
              <Tag>+{events.length - 2}</Tag>
            </Tooltip>
          )}
        </Space>
      ),
    },
    {
      title: 'Status',
      key: 'status',
      width: 100,
      render: (_: any, r: WebhookConfigItem) => (
        <Switch
          size="small"
          checked={r.is_active}
          checkedChildren="Active"
          unCheckedChildren="Off"
          onChange={() => handleToggleActive(r)}
        />
      ),
    },
    {
      title: 'Last Triggered',
      dataIndex: 'last_triggered_at',
      key: 'last_triggered',
      width: 140,
      render: (v: string | null, r: WebhookConfigItem) => {
        if (!v) return <Text type="secondary">Never</Text>;
        return (
          <Tooltip title={dayjs(v).format('YYYY-MM-DD HH:mm:ss')}>
            <Space size={4}>
              <Text style={{ fontSize: 12 }}>{dayjs(v).fromNow()}</Text>
              {r.last_status_code && (
                <Tag color={getStatusColor(r.last_status_code)} style={{ fontSize: 11 }}>
                  {r.last_status_code}
                </Tag>
              )}
            </Space>
          </Tooltip>
        );
      },
    },
    {
      title: 'Actions',
      key: 'actions',
      width: 180,
      render: (_: any, r: WebhookConfigItem) => (
        <Space size={4}>
          <Tooltip title="Test Webhook">
            <Button
              size="small"
              type="text"
              icon={<Send size={14} />}
              onClick={() => handleTest(r.id)}
              loading={testWebhook.isPending}
            />
          </Tooltip>
          <Tooltip title="Delivery History">
            <Button
              size="small"
              type="text"
              icon={<HistoryOutlined />}
              onClick={() => { setDeliveryWebhookId(r.id); setDeliveryPage(1); }}
            />
          </Tooltip>
          <Tooltip title="Edit">
            <Button
              size="small"
              type="text"
              icon={<EditOutlined />}
              onClick={() => openEdit(r)}
            />
          </Tooltip>
          <Popconfirm
            title="Delete this webhook?"
            description="This action cannot be undone."
            onConfirm={() => handleDelete(r.id)}
            okText="Delete"
            okButtonProps={{ danger: true }}
          >
            <Tooltip title="Delete">
              <Button size="small" type="text" danger icon={<DeleteOutlined />} />
            </Tooltip>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const deliveryColumns = [
    {
      title: 'Event',
      dataIndex: 'event',
      key: 'event',
      render: (v: string) => <Tag color="blue">{v}</Tag>,
    },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      render: (v: string, r: WebhookDeliveryItem) => (
        <Space size={4}>
          {v === 'Success' ? (
            <Tag icon={<CheckCircleOutlined />} color="success">Success</Tag>
          ) : v === 'Failed' ? (
            <Tag icon={<CloseCircleOutlined />} color="error">Failed</Tag>
          ) : (
            <Tag color="processing">Pending</Tag>
          )}
          {r.status_code && <Text type="secondary" style={{ fontSize: 12 }}>{r.status_code}</Text>}
        </Space>
      ),
    },
    {
      title: 'Duration',
      dataIndex: 'duration_ms',
      key: 'duration',
      render: (v: number | null) => v != null ? `${v}ms` : '-',
    },
    {
      title: 'Attempted',
      dataIndex: 'attempted_at',
      key: 'attempted',
      render: (v: string) => (
        <Tooltip title={dayjs(v).format('YYYY-MM-DD HH:mm:ss')}>
          <Text style={{ fontSize: 12 }}>{dayjs(v).fromNow()}</Text>
        </Tooltip>
      ),
    },
    {
      title: 'Retry',
      dataIndex: 'retry_attempt',
      key: 'retry',
      render: (v: number) => v > 0 ? <Tag color="orange">#{v}</Tag> : '-',
    },
    {
      title: 'Error',
      dataIndex: 'error_message',
      key: 'error',
      ellipsis: true,
      width: 200,
      render: (v: string) => v ? (
        <Tooltip title={v}>
          <Text type="danger" style={{ fontSize: 12 }}>{v.substring(0, 60)}{v.length > 60 ? '...' : ''}</Text>
        </Tooltip>
      ) : '-',
    },
  ];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Space>
          <Webhook size={20} style={{ color: '#2471a3' }} />
          <Typography.Title level={5} style={{ margin: 0 }}>Webhooks</Typography.Title>
          <Badge count={webhooks.length} style={{ backgroundColor: '#2471a3' }} />
        </Space>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate} style={{ backgroundColor: '#2471a3' }}>
          Add Webhook
        </Button>
      </div>

      <Table
        dataSource={webhooks}
        columns={columns}
        rowKey="id"
        size="middle"
        loading={isLoading}
        pagination={{ pageSize: 10, showSizeChanger: false, showTotal: (t) => `${t} webhooks` }}
        locale={{ emptyText: <Empty description="No webhooks configured" /> }}
      />

      {/* Create/Edit Modal */}
      <Modal
        title={editing ? 'Edit Webhook' : 'Add Webhook'}
        open={modalOpen}
        onCancel={() => { setModalOpen(false); setEditing(null); form.resetFields(); }}
        onOk={handleSubmit}
        confirmLoading={createWebhook.isPending || updateWebhook.isPending}
        okText={editing ? 'Update' : 'Create'}
        width={560}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          {!editing && (
            <Form.Item label="Tenant" name="tenant_id" rules={[{ required: true, message: 'Select a tenant' }]}>
              <Select
                placeholder="Select tenant"
                showSearch
                optionFilterProp="children"
                options={tenants.map((t: any) => ({ value: t.id, label: t.name }))}
              />
            </Form.Item>
          )}
          <Form.Item label="Webhook Name" name="webhook_name" rules={[{ required: true, message: 'Enter a name' }]}>
            <Input placeholder="e.g., Payment Notifications" />
          </Form.Item>
          <Form.Item
            label="URL"
            name="webhook_url"
            rules={[
              { required: true, message: 'Enter webhook URL' },
              { type: 'url', message: 'Enter a valid URL' },
            ]}
          >
            <Input placeholder="https://example.com/webhook" />
          </Form.Item>
          <Form.Item label="Events" name="subscribed_events">
            <Select
              mode="multiple"
              placeholder="Select events to subscribe"
              options={WEBHOOK_EVENTS}
              optionFilterProp="label"
            />
          </Form.Item>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item label="Timeout (seconds)" name="timeout_seconds">
                <InputNumber min={1} max={60} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item label="Retry Count" name="retry_count">
                <InputNumber min={0} max={10} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item label="Active" name="is_active" valuePropName="checked">
            <Switch checkedChildren="Active" unCheckedChildren="Inactive" />
          </Form.Item>
        </Form>
      </Modal>

      {/* Secret Key display modal */}
      <Modal
        title="Webhook Created"
        open={!!secretKeyVisible}
        onOk={() => setSecretKeyVisible(null)}
        onCancel={() => setSecretKeyVisible(null)}
        cancelButtonProps={{ style: { display: 'none' } }}
      >
        <div style={{ marginBottom: 12 }}>
          <ExclamationCircleOutlined style={{ color: '#faad14', marginRight: 8 }} />
          <Text strong>Save this secret key now -- it will not be shown again.</Text>
        </div>
        <Input.TextArea
          value={secretKeyVisible || ''}
          readOnly
          rows={2}
          style={{ fontFamily: 'monospace', marginBottom: 8 }}
        />
        <Button
          block
          onClick={() => {
            if (secretKeyVisible) {
              navigator.clipboard.writeText(secretKeyVisible);
              message.success('Secret key copied to clipboard');
            }
          }}
        >
          Copy to Clipboard
        </Button>
      </Modal>

      {/* Delivery History Drawer */}
      <Drawer
        title="Delivery History"
        open={!!deliveryWebhookId}
        onClose={() => setDeliveryWebhookId(null)}
        styles={{ wrapper: { width: '700px' } }}
      >
        <Table
          dataSource={deliveriesData?.results || []}
          columns={deliveryColumns}
          rowKey="id"
          size="small"
          pagination={{
            current: deliveryPage,
            pageSize: 20,
            total: deliveriesData?.count || 0,
            onChange: (p) => setDeliveryPage(p),
            showSizeChanger: false,
          }}
          locale={{ emptyText: <Empty description="No deliveries yet" /> }}
        />
      </Drawer>
    </div>
  );
}
