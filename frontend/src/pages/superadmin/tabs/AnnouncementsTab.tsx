import { useState, useMemo } from 'react';
import {
  Card, Table, Button, Tag, Space, Statistic, Row, Col,
  Modal, Form, Input, DatePicker, Select, message, Typography,
} from 'antd';
import { PlusOutlined, ExclamationCircleOutlined } from '@ant-design/icons';
import {
  Megaphone, Bell, AlertTriangle, Info, Archive, Trash2, Edit, Send,
} from 'lucide-react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { superadminApi, type Announcement } from '../../../api/superadmin';
import dayjs from 'dayjs';

const { Text } = Typography;
const { TextArea } = Input;

const PRIORITY_OPTIONS = [
  { value: 'Low', label: 'Low' },
  { value: 'Normal', label: 'Normal' },
  { value: 'High', label: 'High' },
  { value: 'Critical', label: 'Critical' },
];

const TYPE_COLORS: Record<string, string> = {
  Low: '#8c8c8c',
  Normal: '#2471a3',
  High: '#fa8c16',
  Critical: '#cf1322',
};

const TARGET_OPTIONS = [
  { value: 'All', label: 'All Tenants' },
  { value: 'Tenant', label: 'Specific Tenants' },
];

const PRIORITY_ICONS: Record<string, React.ReactNode> = {
  Low: <Info size={14} />,
  Normal: <Bell size={14} />,
  High: <AlertTriangle size={14} />,
  Critical: <AlertTriangle size={14} />,
};

/** Derive a display status from the backend fields. */
function deriveStatus(a: Announcement): 'published' | 'draft' | 'scheduled' | 'archived' {
  if (a.is_published && a.ends_at && dayjs(a.ends_at).isBefore(dayjs())) return 'archived';
  if (a.is_published) return 'published';
  if (!a.is_published && a.starts_at && dayjs(a.starts_at).isAfter(dayjs())) return 'scheduled';
  return 'draft';
}

const STATUS_TAG: Record<string, { color: string; label: string }> = {
  published: { color: 'green', label: 'Published' },
  draft: { color: 'blue', label: 'Draft' },
  scheduled: { color: 'orange', label: 'Scheduled' },
  archived: { color: 'default', label: 'Archived' },
};

const AnnouncementsTab = () => {
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<Announcement | null>(null);
  const [filterPriority, setFilterPriority] = useState<string | undefined>(undefined);
  const [filterStatus, setFilterStatus] = useState<string | undefined>(undefined);
  const [form] = Form.useForm();
  const qc = useQueryClient();

  // ---- Queries ----
  const { data: announcementsRes, isLoading } = useQuery({
    queryKey: ['superadmin-announcements'],
    queryFn: () => superadminApi.getAnnouncements(),
    staleTime: 2 * 60 * 1000,
  });

  const { data: tenantsRes } = useQuery({
    queryKey: ['superadmin-tenants'],
    queryFn: () => superadminApi.getTenants(),
    staleTime: 2 * 60 * 1000,
  });

  const announcements: Announcement[] = useMemo(() => {
    const raw = announcementsRes?.data || [];
    return Array.isArray(raw) ? raw : (raw as any)?.results || [];
  }, [announcementsRes]);

  const tenants = useMemo(() => {
    const raw = tenantsRes?.data || [];
    return Array.isArray(raw) ? raw : [];
  }, [tenantsRes]);

  // ---- Mutations ----
  const createMut = useMutation({
    mutationFn: (data: Partial<Announcement>) => superadminApi.createAnnouncement(data),
    onSuccess: () => {
      message.success('Announcement created');
      qc.invalidateQueries({ queryKey: ['superadmin-announcements'] });
      closeModal();
    },
    onError: (err: any) => message.error(err?.response?.data?.error || 'Failed to create'),
  });

  const updateMut = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<Announcement> }) =>
      superadminApi.updateAnnouncement(id, data),
    onSuccess: () => {
      message.success('Announcement updated');
      qc.invalidateQueries({ queryKey: ['superadmin-announcements'] });
      closeModal();
    },
    onError: (err: any) => message.error(err?.response?.data?.error || 'Failed to update'),
  });

  const publishMut = useMutation({
    mutationFn: (id: number) => superadminApi.publishAnnouncement(id),
    onSuccess: (_data, _id) => {
      message.success('Announcement published');
      qc.invalidateQueries({ queryKey: ['superadmin-announcements'] });
    },
    onError: (err: any) => message.error(err?.response?.data?.error || 'Failed to publish'),
  });

  const deleteMut = useMutation({
    mutationFn: (id: number) => superadminApi.deleteAnnouncement(id),
    onSuccess: () => {
      message.success('Announcement deleted');
      qc.invalidateQueries({ queryKey: ['superadmin-announcements'] });
    },
    onError: (err: any) => message.error(err?.response?.data?.error || 'Failed to delete'),
  });

  // ---- Helpers ----
  const closeModal = () => {
    setModalOpen(false);
    setEditing(null);
    form.resetFields();
  };

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({ target: 'All', priority: 'Normal', schedule: 'now' });
    setModalOpen(true);
  };

  const openEdit = (record: Announcement) => {
    setEditing(record);
    const isScheduled = !record.is_published && record.starts_at && dayjs(record.starts_at).isAfter(dayjs());
    form.setFieldsValue({
      title: record.title,
      content: record.content,
      priority: record.priority,
      target: record.target,
      target_tenant_ids: record.target_tenant_ids,
      schedule: isScheduled ? 'later' : 'now',
      starts_at: record.starts_at ? dayjs(record.starts_at) : undefined,
      ends_at: record.ends_at ? dayjs(record.ends_at) : undefined,
    });
    setModalOpen(true);
  };

  const handleArchive = (record: Announcement) => {
    Modal.confirm({
      title: 'Archive Announcement',
      icon: <ExclamationCircleOutlined />,
      content: `Are you sure you want to archive "${record.title}"?`,
      okText: 'Archive',
      onOk: () => updateMut.mutate({ id: record.id, data: { ends_at: dayjs().toISOString(), is_published: true } as any }),
    });
  };

  const handleDelete = (record: Announcement) => {
    Modal.confirm({
      title: 'Delete Announcement',
      icon: <ExclamationCircleOutlined />,
      content: `Permanently delete "${record.title}"? This cannot be undone.`,
      okText: 'Delete',
      okType: 'danger',
      onOk: () => deleteMut.mutate(record.id),
    });
  };

  const handleSubmit = (values: any) => {
    const fmtDate = (d: any) => {
      if (!d) return undefined;
      if (typeof d === 'string') return d;
      return d.toISOString ? d.toISOString() : dayjs(d).toISOString();
    };

    const payload: any = {
      title: values.title,
      content: values.content,
      priority: values.priority,
      target: values.target,
      target_tenant_ids: values.target === 'Tenant' ? (values.target_tenant_ids || []) : [],
      starts_at: values.schedule === 'later' ? fmtDate(values.starts_at) : new Date().toISOString(),
      ends_at: fmtDate(values.ends_at) || null,
      is_published: values.schedule === 'now',
    };

    if (editing) {
      updateMut.mutate({ id: editing.id, data: payload });
    } else {
      createMut.mutate(payload);
    }
  };

  // ---- Stats ----
  const stats = useMemo(() => {
    const total = announcements.length;
    let published = 0, draft = 0, scheduled = 0, archived = 0;
    announcements.forEach(a => {
      const s = deriveStatus(a);
      if (s === 'published') published++;
      else if (s === 'draft') draft++;
      else if (s === 'scheduled') scheduled++;
      else archived++;
    });
    return { total, published, draft, scheduled, archived };
  }, [announcements]);

  // ---- Filtered data ----
  const filteredData = useMemo(() => {
    let result = announcements;
    if (filterPriority) {
      result = result.filter(a => a.priority === filterPriority);
    }
    if (filterStatus) {
      result = result.filter(a => deriveStatus(a) === filterStatus);
    }
    return result;
  }, [announcements, filterPriority, filterStatus]);

  // ---- Form watcher ----
  const targetValue = Form.useWatch('target', form);
  const scheduleValue = Form.useWatch('schedule', form);

  // ---- Table columns ----
  const columns = [
    {
      title: 'Title',
      dataIndex: 'title',
      key: 'title',
      ellipsis: true,
      render: (text: string) => <Text strong>{text}</Text>,
    },
    {
      title: 'Type',
      dataIndex: 'priority',
      key: 'priority',
      width: 130,
      render: (p: string) => (
        <Tag
          icon={<span style={{ marginRight: 4, display: 'inline-flex', verticalAlign: 'middle' }}>{PRIORITY_ICONS[p]}</span>}
          color={TYPE_COLORS[p]}
          style={{ borderRadius: 6 }}
        >
          {p === 'Normal' ? 'info' : p === 'High' ? 'warning' : p === 'Critical' ? 'critical' : 'maintenance'}
        </Tag>
      ),
    },
    {
      title: 'Status',
      key: 'status',
      width: 120,
      render: (_: any, r: Announcement) => {
        const s = deriveStatus(r);
        const cfg = STATUS_TAG[s];
        return <Tag color={cfg.color} style={{ borderRadius: 6 }}>{cfg.label}</Tag>;
      },
    },
    {
      title: 'Target Audience',
      key: 'target',
      width: 160,
      render: (_: any, r: Announcement) =>
        r.target === 'All'
          ? <Tag color="geekblue">All Tenants</Tag>
          : <Tag color="purple">{r.target_tenant_ids.length} Tenant(s)</Tag>,
    },
    {
      title: 'Published Date',
      key: 'published_date',
      width: 170,
      render: (_: any, r: Announcement) => {
        if (r.is_published) return dayjs(r.starts_at).format('MMM D, YYYY h:mm A');
        if (dayjs(r.starts_at).isAfter(dayjs())) return <Text type="secondary">Scheduled: {dayjs(r.starts_at).format('MMM D, YYYY')}</Text>;
        return <Text type="secondary">--</Text>;
      },
    },
    {
      title: 'Actions',
      key: 'actions',
      width: 220,
      render: (_: any, r: Announcement) => {
        const status = deriveStatus(r);
        return (
          <Space size="small">
            <Button
              type="text"
              size="small"
              icon={<Edit size={14} />}
              onClick={() => openEdit(r)}
              style={{ color: '#2471a3' }}
            />
            {status === 'draft' && (
              <Button
                type="text"
                size="small"
                icon={<Send size={14} />}
                onClick={() => publishMut.mutate(r.id)}
                style={{ color: '#389e0d' }}
                title="Publish"
              />
            )}
            {status === 'published' && (
              <Button
                type="text"
                size="small"
                icon={<Archive size={14} />}
                onClick={() => handleArchive(r)}
                style={{ color: '#fa8c16' }}
                title="Archive"
              />
            )}
            <Button
              type="text"
              size="small"
              danger
              icon={<Trash2 size={14} />}
              onClick={() => handleDelete(r)}
              title="Delete"
            />
          </Space>
        );
      },
    },
  ];

  return (
    <div>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <Megaphone size={22} color="#2471a3" />
          <h2 style={{ margin: 0, color: '#0f172a' }}>Announcements</h2>
        </div>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
          Create Announcement
        </Button>
      </div>

      {/* Stats */}
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}>
          <Card size="small">
            <Statistic
              title="Total Announcements"
              value={stats.total}
              prefix={<Megaphone size={16} style={{ marginRight: 4 }} />}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic
              title="Published"
              value={stats.published}
              styles={{ content: { color: '#389e0d' } }}
              prefix={<Send size={16} style={{ marginRight: 4 }} />}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic
              title="Draft"
              value={stats.draft}
              styles={{ content: { color: '#1890ff' } }}
              prefix={<Edit size={16} style={{ marginRight: 4 }} />}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic
              title="Scheduled"
              value={stats.scheduled}
              styles={{ content: { color: '#fa8c16' } }}
              prefix={<Bell size={16} style={{ marginRight: 4 }} />}
            />
          </Card>
        </Col>
      </Row>

      {/* Filters */}
      <div style={{ marginBottom: 16, display: 'flex', gap: 12 }}>
        <Select
          allowClear
          placeholder="Filter by type"
          style={{ width: 180 }}
          value={filterPriority}
          onChange={setFilterPriority}
          options={PRIORITY_OPTIONS}
        />
        <Select
          allowClear
          placeholder="Filter by status"
          style={{ width: 180 }}
          value={filterStatus}
          onChange={setFilterStatus}
          options={[
            { value: 'published', label: 'Published' },
            { value: 'draft', label: 'Draft' },
            { value: 'scheduled', label: 'Scheduled' },
            { value: 'archived', label: 'Archived' },
          ]}
        />
      </div>

      {/* Table */}
      <Table
        dataSource={filteredData}
        columns={columns}
        rowKey="id"
        loading={isLoading}
        size="middle"
        pagination={{ pageSize: 15, showSizeChanger: false }}
      />

      {/* Create / Edit Modal */}
      <Modal
        title={editing ? 'Edit Announcement' : 'Create Announcement'}
        open={modalOpen}
        onCancel={closeModal}
        onOk={() => form.submit()}
        confirmLoading={createMut.isPending || updateMut.isPending}
        width={640}
        destroyOnHidden
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={handleSubmit}
          initialValues={{ target: 'All', priority: 'Normal', schedule: 'now' }}
        >
          <Form.Item name="title" label="Title" rules={[{ required: true, message: 'Title is required' }]}>
            <Input placeholder="Announcement title" />
          </Form.Item>

          <Form.Item name="content" label="Content" rules={[{ required: true, message: 'Content is required' }]}>
            <TextArea rows={5} placeholder="Write your announcement content..." />
          </Form.Item>

          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="priority" label="Type" rules={[{ required: true }]}>
                <Select options={[
                  { value: 'Low', label: 'Maintenance' },
                  { value: 'Normal', label: 'Info' },
                  { value: 'High', label: 'Warning' },
                  { value: 'Critical', label: 'Critical' },
                ]} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="target" label="Target Audience" rules={[{ required: true }]}>
                <Select options={TARGET_OPTIONS} />
              </Form.Item>
            </Col>
          </Row>

          {targetValue === 'Tenant' && (
            <Form.Item name="target_tenant_ids" label="Select Tenants">
              <Select
                mode="multiple"
                placeholder="Choose tenants"
                showSearch
                filterOption={(input, opt) =>
                  (opt?.label as string || '').toLowerCase().includes(input.toLowerCase())
                }
                options={tenants.map((t: any) => ({ value: t.id, label: t.name || t.organization_name }))}
              />
            </Form.Item>
          )}

          <Form.Item name="schedule" label="Publish">
            <Select options={[
              { value: 'now', label: 'Publish Now' },
              { value: 'later', label: 'Schedule for Later' },
            ]} />
          </Form.Item>

          {scheduleValue === 'later' && (
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item
                  name="starts_at"
                  label="Scheduled Date"
                  rules={[{ required: true, message: 'Schedule date is required' }]}
                >
                  <DatePicker showTime style={{ width: '100%' }} />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="ends_at" label="End Date (optional)">
                  <DatePicker showTime style={{ width: '100%' }} />
                </Form.Item>
              </Col>
            </Row>
          )}
        </Form>
      </Modal>
    </div>
  );
};

export default AnnouncementsTab;
