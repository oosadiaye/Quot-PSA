import { useState, useEffect, useCallback, useRef } from 'react';
import {
  Card, Table, Tag, Button, Space, Modal, Form, Input, Select, App, Empty,
  Skeleton, Typography, Row, Col, Badge, Drawer, Descriptions, Divider,
  Statistic, Timeline,
} from 'antd';
import {
  CustomerServiceOutlined, PlusOutlined, ReloadOutlined, SendOutlined,
  ClockCircleOutlined, CheckCircleOutlined, ExclamationCircleOutlined,
  MessageOutlined, DeleteOutlined,
} from '@ant-design/icons';
import { superadminApi } from '../../../api/superadmin';
import type { SupportTicket, TicketComment } from '../../../api/superadmin';

const { Text, Title, Paragraph } = Typography;
const { TextArea } = Input;

const cardStyle: React.CSSProperties = {
  borderRadius: 12,
  border: 'none',
  boxShadow: '0 2px 8px rgba(0, 0, 0, 0.06), 0 1px 2px rgba(0, 0, 0, 0.04)',
};

const priorityConfig: Record<string, { color: string }> = {
  Critical: { color: 'red' },
  High: { color: 'orange' },
  Medium: { color: 'gold' },
  Low: { color: 'default' },
};

const statusConfig: Record<string, { color: string; icon: React.ReactNode }> = {
  Open: { color: 'blue', icon: <ExclamationCircleOutlined /> },
  InProgress: { color: 'purple', icon: <ClockCircleOutlined /> },
  WaitingCustomer: { color: 'orange', icon: <ClockCircleOutlined /> },
  Resolved: { color: 'green', icon: <CheckCircleOutlined /> },
  Closed: { color: 'default', icon: <CheckCircleOutlined /> },
};

const categoryIcons: Record<string, string> = {
  Technical: '🔧',
  Billing: '💰',
  Account: '👤',
  FeatureRequest: '✨',
  DataIssue: '📊',
  Integration: '🔗',
  Other: '📝',
};

export default function SupportTab() {
  const { message } = App.useApp();
  const [tickets, setTickets] = useState<SupportTicket[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined);
  const [detailDrawer, setDetailDrawer] = useState(false);
  const [selectedTicket, setSelectedTicket] = useState<SupportTicket | null>(null);
  const [createModal, setCreateModal] = useState(false);
  const [resolution, setResolution] = useState('');
  const [form] = Form.useForm();

  const loadTickets = useCallback(async () => {
    try {
      setLoading(true);
      const res = await superadminApi.getSupportTickets({ page: 1, page_size: 100, status: statusFilter || undefined });
      const data = res.data;
      setTickets(Array.isArray(data) ? data : (data as any)?.results || []);
    } catch {
      message.error('Failed to load tickets');
    } finally {
      setLoading(false);
    }
  }, [statusFilter, message]);

  useEffect(() => { loadTickets(); }, [loadTickets]);

  const handleUpdateTicket = async (id: number, data: Partial<SupportTicket>) => {
    try {
      await superadminApi.updateSupportTicket(id, data);
      message.success('Ticket updated');
      loadTickets();
      // Update selected ticket in drawer
      if (selectedTicket?.id === id) {
        setSelectedTicket({ ...selectedTicket, ...data } as SupportTicket);
      }
    } catch {
      message.error('Failed to update ticket');
    }
  };

  const handleResolve = async () => {
    if (!selectedTicket || !resolution.trim()) {
      message.warning('Please enter resolution notes');
      return;
    }
    await handleUpdateTicket(selectedTicket.id, {
      status: 'Resolved',
      resolution: resolution.trim(),
    });
    setResolution('');
  };

  const handleCreateTicket = async (values: any) => {
    try {
      await superadminApi.createSupportTicket(values);
      message.success('Ticket created');
      setCreateModal(false);
      form.resetFields();
      loadTickets();
    } catch {
      message.error('Failed to create ticket');
    }
  };

  const openDetail = async (ticket: SupportTicket) => {
    setSelectedTicket(ticket);
    setResolution(ticket.resolution || '');
    setDetailDrawer(true);
    // Load full ticket details with comments
    try {
      const res = await superadminApi.getSupportTicket(ticket.id);
      setSelectedTicket(res.data);
    } catch {
      // Keep basic ticket data
    }
  };

  if (loading && tickets.length === 0) return <Skeleton active paragraph={{ rows: 10 }} />;

  // Stats
  const openCount = tickets.filter((t) => t.status === 'Open').length;
  const inProgressCount = tickets.filter((t) => t.status === 'InProgress').length;
  const resolvedCount = tickets.filter((t) => t.status === 'Resolved' || t.status === 'Closed').length;

  const columns = [
    {
      title: 'Ticket',
      key: 'ticket',
      render: (_: any, r: SupportTicket) => (
        <Space>
          <span style={{ fontSize: 20 }}>{categoryIcons[r.category] || '📝'}</span>
          <div>
            <a onClick={() => openDetail(r)} style={{ fontWeight: 600 }}>{r.subject}</a>
            <div>
              <Text type="secondary" style={{ fontFamily: 'monospace', fontSize: 11 }}>{r.ticket_number}</Text>
            </div>
          </div>
        </Space>
      ),
    },
    {
      title: 'Requester',
      key: 'requester',
      render: (_: any, r: SupportTicket) => (
        <div>
          <Text>{r.requester_name}</Text>
          <div><Text type="secondary" style={{ fontSize: 12 }}>{r.requester_email}</Text></div>
        </div>
      ),
    },
    {
      title: 'Category',
      dataIndex: 'category',
      key: 'category',
      render: (v: string) => <Tag>{v}</Tag>,
    },
    {
      title: 'Priority',
      dataIndex: 'priority',
      key: 'priority',
      render: (v: string) => <Tag color={priorityConfig[v]?.color || 'default'}>{v}</Tag>,
    },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      render: (v: string) => {
        const config = statusConfig[v] || statusConfig.Open;
        return <Tag icon={config.icon} color={config.color}>{v}</Tag>;
      },
    },
    {
      title: 'Created',
      dataIndex: 'created_at',
      key: 'created',
      sorter: (a: SupportTicket, b: SupportTicket) => (a.created_at || '').localeCompare(b.created_at || ''),
      render: (v: string) => v ? new Date(v).toLocaleDateString() : '-',
    },
    {
      title: 'Actions',
      key: 'actions',
      width: 160,
      render: (_: any, r: SupportTicket) => (
        <Space size="small">
          <Button size="small" type="link" onClick={() => openDetail(r)}>
            View
          </Button>
          <Button
            size="small"
            type="link"
            danger
            icon={<DeleteOutlined />}
            onClick={() => {
              Modal.confirm({
                title: 'Delete Ticket',
                content: `Are you sure you want to delete ticket ${r.ticket_number || '#' + r.id}? This action cannot be undone.`,
                okText: 'Delete',
                okType: 'danger',
                onOk: async () => {
                  try {
                    await superadminApi.deleteSupportTicket(r.id);
                    message.success('Ticket deleted');
                    loadTickets();
                  } catch {
                    message.error('Failed to delete ticket');
                  }
                },
              });
            }}
          />
        </Space>
      ),
    },
  ];

  return (
    <Card style={cardStyle}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={5} style={{ margin: 0 }}>Support Tickets</Title>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={loadTickets}>Refresh</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateModal(true)}>
            New Ticket
          </Button>
        </Space>
      </div>

      {/* Stats */}
      <Row gutter={[16, 16]} style={{ marginBottom: 20 }}>
        <Col xs={8} sm={6}>
          <Card size="small" style={{ borderRadius: 10, borderLeft: '4px solid #1890ff' }}>
            <Statistic title="Open" value={openCount} styles={{ content: { color: '#1890ff' } }} />
          </Card>
        </Col>
        <Col xs={8} sm={6}>
          <Card size="small" style={{ borderRadius: 10, borderLeft: '4px solid #722ed1' }}>
            <Statistic title="In Progress" value={inProgressCount} styles={{ content: { color: '#722ed1' } }} />
          </Card>
        </Col>
        <Col xs={8} sm={6}>
          <Card size="small" style={{ borderRadius: 10, borderLeft: '4px solid #52c41a' }}>
            <Statistic title="Resolved" value={resolvedCount} styles={{ content: { color: '#52c41a' } }} />
          </Card>
        </Col>
      </Row>

      {/* Filters */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col xs={24} sm={8}>
          <Select
            placeholder="Filter by status"
            allowClear
            style={{ width: '100%' }}
            value={statusFilter}
            onChange={(val) => setStatusFilter(val)}
            options={[
              { value: 'Open', label: 'Open' },
              { value: 'InProgress', label: 'In Progress' },
              { value: 'WaitingCustomer', label: 'Waiting Customer' },
              { value: 'Resolved', label: 'Resolved' },
              { value: 'Closed', label: 'Closed' },
            ]}
          />
        </Col>
      </Row>

      <Table
        columns={columns}
        dataSource={tickets}
        rowKey="id"
        loading={loading}
        size="middle"
        pagination={{ pageSize: 10, showTotal: (t) => `${t} tickets` }}
      />

      {/* ── Ticket Detail Drawer ──────────────────────────────── */}
      <Drawer
        title={
          <Space>
            <CustomerServiceOutlined />
            <span>{selectedTicket?.ticket_number}</span>
            {selectedTicket?.priority && (
              <Tag color={priorityConfig[selectedTicket.priority]?.color}>
                {selectedTicket.priority}
              </Tag>
            )}
            {selectedTicket?.status && (
              <Tag color={statusConfig[selectedTicket.status]?.color}>
                {selectedTicket.status}
              </Tag>
            )}
          </Space>
        }
        placement="right"
        styles={{ wrapper: { width: '580px' } }}
        open={detailDrawer}
        onClose={() => { setDetailDrawer(false); setSelectedTicket(null); setResolution(''); }}
      >
        {selectedTicket && (
          <div>
            <Title level={5}>{selectedTicket.subject}</Title>

            <Descriptions column={2} size="small" bordered style={{ marginBottom: 16 }}>
              <Descriptions.Item label="Requester">{selectedTicket.requester_name}</Descriptions.Item>
              <Descriptions.Item label="Email">{selectedTicket.requester_email}</Descriptions.Item>
              <Descriptions.Item label="Category">
                <Space>
                  <span>{categoryIcons[selectedTicket.category] || '📝'}</span>
                  {selectedTicket.category}
                </Space>
              </Descriptions.Item>
              <Descriptions.Item label="Created">
                {new Date(selectedTicket.created_at).toLocaleString()}
              </Descriptions.Item>
            </Descriptions>

            <Divider orientation="left">Description</Divider>
            <Card size="small" style={{ borderRadius: 8, marginBottom: 16, background: '#fafafa' }}>
              <Paragraph style={{ whiteSpace: 'pre-wrap', margin: 0 }}>
                {selectedTicket.description}
              </Paragraph>
            </Card>

            {/* Status Change */}
            <Divider orientation="left">Update Status</Divider>
            <Select
              value={selectedTicket.status}
              style={{ width: '100%', marginBottom: 16 }}
              onChange={(val) => handleUpdateTicket(selectedTicket.id, { status: val })}
              options={[
                { value: 'Open', label: 'Open' },
                { value: 'InProgress', label: 'In Progress' },
                { value: 'WaitingCustomer', label: 'Waiting Customer' },
                { value: 'Resolved', label: 'Resolved' },
                { value: 'Closed', label: 'Closed' },
              ]}
            />

            {/* Resolution */}
            {selectedTicket.resolution && (
              <>
                <Divider orientation="left">Resolution</Divider>
                <Card size="small" style={{ borderRadius: 8, marginBottom: 16, background: '#f6ffed', borderColor: '#b7eb8f' }}>
                  <Paragraph style={{ whiteSpace: 'pre-wrap', margin: 0 }}>
                    {selectedTicket.resolution}
                  </Paragraph>
                </Card>
              </>
            )}

            {/* Comments */}
            {selectedTicket.comments && selectedTicket.comments.length > 0 && (
              <>
                <Divider orientation="left">
                  <Space><MessageOutlined /> Comments ({selectedTicket.comments.length})</Space>
                </Divider>
                <Timeline
                  items={selectedTicket.comments.map((c: TicketComment) => ({
                    color: c.is_internal ? 'gray' : 'blue',
                    children: (
                      <div>
                        <Space>
                          <Text strong>{c.author_name}</Text>
                          <Text type="secondary" style={{ fontSize: 12 }}>
                            {new Date(c.created_at).toLocaleString()}
                          </Text>
                          {c.is_internal && <Tag>Internal</Tag>}
                        </Space>
                        <Paragraph style={{ marginTop: 4, marginBottom: 0 }}>{c.content}</Paragraph>
                      </div>
                    ),
                  }))}
                />
              </>
            )}

            {/* Resolve Form */}
            <Divider orientation="left">Add Resolution / Notes</Divider>
            <TextArea
              rows={3}
              value={resolution}
              onChange={(e) => setResolution(e.target.value)}
              placeholder="Enter resolution notes..."
              style={{ marginBottom: 12 }}
            />
            <Space style={{ width: '100%' }}>
              <Button
                type="primary"
                icon={<CheckCircleOutlined />}
                onClick={handleResolve}
                disabled={!resolution.trim()}
                style={{ flex: 1 }}
              >
                Save & Mark Resolved
              </Button>
              <Button
                onClick={() => {
                  if (resolution.trim()) {
                    handleUpdateTicket(selectedTicket.id, { resolution: resolution.trim() });
                  }
                }}
                disabled={!resolution.trim()}
              >
                Save Notes Only
              </Button>
            </Space>
          </div>
        )}
      </Drawer>

      {/* ── Create Ticket Modal ───────────────────────────────── */}
      <Modal
        title="Create Support Ticket"
        open={createModal}
        onCancel={() => { setCreateModal(false); form.resetFields(); }}
        footer={null}
        width={520}
      >
        <Form form={form} layout="vertical" onFinish={handleCreateTicket}>
          <Form.Item label="Subject" name="subject" rules={[{ required: true }]}>
            <Input placeholder="Brief description of the issue" />
          </Form.Item>
          <Form.Item label="Description" name="description" rules={[{ required: true }]}>
            <TextArea rows={4} placeholder="Detailed description..." />
          </Form.Item>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item label="Category" name="category" rules={[{ required: true }]} initialValue="Technical">
                <Select>
                  <Select.Option value="Technical">Technical</Select.Option>
                  <Select.Option value="Billing">Billing</Select.Option>
                  <Select.Option value="Account">Account</Select.Option>
                  <Select.Option value="FeatureRequest">Feature Request</Select.Option>
                  <Select.Option value="DataIssue">Data Issue</Select.Option>
                  <Select.Option value="Integration">Integration</Select.Option>
                  <Select.Option value="Other">Other</Select.Option>
                </Select>
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item label="Priority" name="priority" rules={[{ required: true }]} initialValue="Medium">
                <Select>
                  <Select.Option value="Low">Low</Select.Option>
                  <Select.Option value="Medium">Medium</Select.Option>
                  <Select.Option value="High">High</Select.Option>
                  <Select.Option value="Critical">Critical</Select.Option>
                </Select>
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item label="Requester Name" name="requester_name" rules={[{ required: true }]}>
                <Input placeholder="Name" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item label="Requester Email" name="requester_email" rules={[{ required: true, type: 'email' }]}>
                <Input placeholder="email@example.com" />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item>
            <Button type="primary" htmlType="submit" block>
              Create Ticket
            </Button>
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  );
}
