import { useMemo, useState } from 'react';
import {
  Card, Table, Button, Tag, Space, Modal, Form, Input, Select, Switch,
  message, Tabs, Drawer, Popconfirm, Typography, Empty,
} from 'antd';
import {
  PlusOutlined, EditOutlined, EyeOutlined, DeleteOutlined, SendOutlined,
  MailOutlined,
} from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { superadminApi, type EmailTemplate } from '../../../api/superadmin';

const { TextArea } = Input;
const { Text } = Typography;

const CATEGORIES: Array<{ value: EmailTemplate['category']; label: string; color: string }> = [
  { value: 'auth', label: 'Authentication', color: 'blue' },
  { value: 'billing', label: 'Billing', color: 'green' },
  { value: 'support', label: 'Support', color: 'orange' },
  { value: 'notification', label: 'Notification', color: 'geekblue' },
  { value: 'marketing', label: 'Marketing', color: 'magenta' },
  { value: 'system', label: 'System', color: 'default' },
];

const LANGUAGES = [
  { value: 'en', label: 'English' },
  { value: 'fr', label: 'French' },
  { value: 'es', label: 'Spanish' },
  { value: 'de', label: 'German' },
  { value: 'ar', label: 'Arabic' },
  { value: 'pt', label: 'Portuguese' },
  { value: 'zh', label: 'Chinese' },
  { value: 'ja', label: 'Japanese' },
];

const categoryTag = (cat: EmailTemplate['category']) => {
  const c = CATEGORIES.find((x) => x.value === cat);
  return <Tag color={c?.color || 'default'}>{c?.label || cat}</Tag>;
};

interface EditorState {
  open: boolean;
  template: EmailTemplate | null;
  mode: 'create' | 'edit';
}

interface PreviewState {
  open: boolean;
  subject: string;
  html: string;
  text: string;
}

const EmailTemplatesTab = () => {
  const qc = useQueryClient();
  const [categoryFilter, setCategoryFilter] = useState<string | undefined>();
  const [langFilter, setLangFilter] = useState<string | undefined>();
  const [search, setSearch] = useState('');

  const [editor, setEditor] = useState<EditorState>({ open: false, template: null, mode: 'create' });
  const [preview, setPreview] = useState<PreviewState>({ open: false, subject: '', html: '', text: '' });
  const [testOpen, setTestOpen] = useState<EmailTemplate | null>(null);
  const [testEmail, setTestEmail] = useState('');
  const [form] = Form.useForm();

  const { data, isLoading } = useQuery({
    queryKey: ['superadmin-email-templates', categoryFilter, langFilter, search],
    queryFn: () =>
      superadminApi.getEmailTemplates({
        category: categoryFilter,
        language: langFilter,
        search: search || undefined,
      }).then((r) => r.data),
  });

  const templates = data ?? [];

  const createMut = useMutation({
    mutationFn: (payload: Partial<EmailTemplate>) =>
      superadminApi.createEmailTemplate(payload).then((r) => r.data),
    onSuccess: () => {
      message.success('Template created');
      qc.invalidateQueries({ queryKey: ['superadmin-email-templates'] });
      setEditor({ open: false, template: null, mode: 'create' });
    },
    onError: (e: any) => message.error(e?.response?.data?.error || 'Create failed'),
  });

  const updateMut = useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: Partial<EmailTemplate> }) =>
      superadminApi.updateEmailTemplate(id, payload).then((r) => r.data),
    onSuccess: () => {
      message.success('Template updated');
      qc.invalidateQueries({ queryKey: ['superadmin-email-templates'] });
      setEditor({ open: false, template: null, mode: 'create' });
    },
    onError: (e: any) => message.error(e?.response?.data?.error || 'Update failed'),
  });

  const deleteMut = useMutation({
    mutationFn: (id: number) => superadminApi.deleteEmailTemplate(id),
    onSuccess: () => {
      message.success('Template deleted');
      qc.invalidateQueries({ queryKey: ['superadmin-email-templates'] });
    },
    onError: (e: any) => message.error(e?.response?.data?.error || 'Delete failed'),
  });

  const previewMut = useMutation({
    mutationFn: (id: number) => superadminApi.previewEmailTemplate(id).then((r) => r.data),
    onSuccess: (payload) => setPreview({ open: true, ...payload }),
    onError: (e: any) => message.error(e?.response?.data?.error || 'Preview failed'),
  });

  const sendTestMut = useMutation({
    mutationFn: ({ id, toEmail }: { id: number; toEmail: string }) =>
      superadminApi.sendTestEmailTemplate(id, toEmail).then((r) => r.data),
    onSuccess: (r) => {
      message.success(`Test email sent to ${r.sent_to}`);
      setTestOpen(null);
      setTestEmail('');
    },
    onError: (e: any) => message.error(e?.response?.data?.error || 'Send test failed'),
  });

  const openCreate = () => {
    form.resetFields();
    form.setFieldsValue({
      language: 'en',
      category: 'notification',
      is_active: true,
      variables: [],
    });
    setEditor({ open: true, template: null, mode: 'create' });
  };

  const openEdit = (t: EmailTemplate) => {
    form.resetFields();
    form.setFieldsValue({
      ...t,
      variables: (t.variables || []).join(', '),
    });
    setEditor({ open: true, template: t, mode: 'edit' });
  };

  const submitEditor = async () => {
    const vals = await form.validateFields();
    const payload: Partial<EmailTemplate> = {
      ...vals,
      variables: typeof vals.variables === 'string'
        ? vals.variables.split(',').map((s: string) => s.trim()).filter(Boolean)
        : (vals.variables || []),
    };
    if (editor.mode === 'create') {
      createMut.mutate(payload);
    } else if (editor.template) {
      updateMut.mutate({ id: editor.template.id, payload });
    }
  };

  const columns = useMemo(() => [
    {
      title: 'Key',
      dataIndex: 'key',
      render: (k: string, r: EmailTemplate) => (
        <div>
          <div style={{ fontWeight: 600, color: '#0b1320' }}>{k}</div>
          <div style={{ fontSize: 12, color: '#64748b' }}>{r.display_name}</div>
        </div>
      ),
    },
    {
      title: 'Category',
      dataIndex: 'category',
      render: (c: EmailTemplate['category']) => categoryTag(c),
      width: 140,
    },
    {
      title: 'Language',
      dataIndex: 'language',
      render: (l: string) => <Tag>{l.toUpperCase()}</Tag>,
      width: 100,
    },
    {
      title: 'Subject',
      dataIndex: 'subject',
      ellipsis: true,
    },
    {
      title: 'Status',
      dataIndex: 'is_active',
      width: 110,
      render: (active: boolean, r: EmailTemplate) => (
        <Space direction="vertical" size={2}>
          <Tag color={active ? 'green' : 'default'}>{active ? 'Active' : 'Inactive'}</Tag>
          {r.is_system && <Tag color="blue">System</Tag>}
        </Space>
      ),
    },
    {
      title: 'Updated',
      dataIndex: 'updated_at',
      width: 160,
      render: (dt: string | null, r: EmailTemplate) => (
        <Text type="secondary" style={{ fontSize: 12 }}>
          {dt ? new Date(dt).toLocaleString() : '—'}
          {r.updated_by ? <><br />by {r.updated_by}</> : null}
        </Text>
      ),
    },
    {
      title: 'Actions',
      key: 'actions',
      width: 220,
      render: (_: unknown, r: EmailTemplate) => (
        <Space size={4} wrap>
          <Button size="small" icon={<EyeOutlined />} onClick={() => previewMut.mutate(r.id)}>
            Preview
          </Button>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(r)}>
            Edit
          </Button>
          <Button
            size="small"
            icon={<SendOutlined />}
            onClick={() => setTestOpen(r)}
          >
            Test
          </Button>
          {!r.is_system && (
            <Popconfirm
              title="Delete this template?"
              onConfirm={() => deleteMut.mutate(r.id)}
              okText="Delete"
              okButtonProps={{ danger: true }}
            >
              <Button size="small" danger icon={<DeleteOutlined />} />
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ], [previewMut, deleteMut]);

  return (
    <div>
      <Card
        title={
          <Space>
            <MailOutlined style={{ color: '#242a88' }} />
            <span>Email Templates</span>
          </Space>
        }
        extra={
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
            New Template
          </Button>
        }
      >
        <Space style={{ marginBottom: 16 }} wrap>
          <Input.Search
            placeholder="Search key, name, subject"
            allowClear
            onSearch={setSearch}
            style={{ width: 280 }}
          />
          <Select
            placeholder="Category"
            allowClear
            style={{ width: 180 }}
            value={categoryFilter}
            onChange={setCategoryFilter}
            options={CATEGORIES.map((c) => ({ value: c.value, label: c.label }))}
          />
          <Select
            placeholder="Language"
            allowClear
            style={{ width: 140 }}
            value={langFilter}
            onChange={setLangFilter}
            options={LANGUAGES}
          />
        </Space>

        {templates.length === 0 && !isLoading ? (
          <Empty
            description={
              <div>
                <div>No email templates yet.</div>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  Run <code>python manage.py seed_email_templates</code> to create the default set,
                  or click "New Template" to start from scratch.
                </Text>
              </div>
            }
          />
        ) : (
          <Table
            rowKey="id"
            loading={isLoading}
            columns={columns as any}
            dataSource={templates}
            pagination={{ pageSize: 20 }}
          />
        )}
      </Card>

      {/* Editor drawer */}
      <Drawer
        open={editor.open}
        onClose={() => setEditor({ open: false, template: null, mode: 'create' })}
        width={820}
        title={editor.mode === 'create' ? 'New Email Template' : `Edit: ${editor.template?.display_name}`}
        destroyOnClose
        extra={
          <Space>
            <Button onClick={() => setEditor({ open: false, template: null, mode: 'create' })}>
              Cancel
            </Button>
            <Button
              type="primary"
              loading={createMut.isPending || updateMut.isPending}
              onClick={submitEditor}
            >
              Save
            </Button>
          </Space>
        }
      >
        <Form form={form} layout="vertical">
          <Tabs
            items={[
              {
                key: 'meta',
                label: 'Metadata',
                children: (
                  <>
                    <Form.Item
                      name="key"
                      label="Key"
                      rules={[{ required: true, pattern: /^[a-z0-9_]+$/, message: 'Lowercase, numbers, underscores only.' }]}
                      extra="Stable identifier used by the code to look up this template (e.g. welcome, password_reset)."
                    >
                      <Input disabled={editor.template?.is_system} placeholder="welcome" />
                    </Form.Item>
                    <Form.Item name="language" label="Language" rules={[{ required: true }]}>
                      <Select options={LANGUAGES} disabled={editor.template?.is_system} />
                    </Form.Item>
                    <Form.Item name="category" label="Category" rules={[{ required: true }]}>
                      <Select options={CATEGORIES.map((c) => ({ value: c.value, label: c.label }))} />
                    </Form.Item>
                    <Form.Item name="display_name" label="Display name" rules={[{ required: true }]}>
                      <Input placeholder="Welcome / Signup Confirmation" />
                    </Form.Item>
                    <Form.Item name="description" label="Description">
                      <TextArea rows={2} placeholder="When does this template fire and who receives it?" />
                    </Form.Item>
                    <Form.Item
                      name="variables"
                      label="Available placeholders"
                      extra="Comma-separated (e.g. first_name, login_url). Use these as {first_name} in subject or body."
                    >
                      <Input placeholder="first_name, org_name, login_url" />
                    </Form.Item>
                    <Form.Item name="is_active" label="Active" valuePropName="checked">
                      <Switch />
                    </Form.Item>
                  </>
                ),
              },
              {
                key: 'content',
                label: 'Content',
                children: (
                  <>
                    <Form.Item
                      name="subject"
                      label="Subject"
                      rules={[{ required: true }]}
                      extra="Supports {placeholder} substitution."
                    >
                      <Input placeholder="Welcome to {org_name}" />
                    </Form.Item>
                    <Form.Item
                      name="body_html"
                      label="HTML body"
                      rules={[{ required: true }]}
                      extra="The beautified header and footer are added automatically — focus on the inner content."
                    >
                      <TextArea
                        rows={18}
                        style={{ fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace', fontSize: 13 }}
                      />
                    </Form.Item>
                    <Form.Item
                      name="body_text"
                      label="Plain-text fallback"
                      extra="Optional. If blank, the HTML is auto-stripped at send time."
                    >
                      <TextArea rows={6} />
                    </Form.Item>
                  </>
                ),
              },
            ]}
          />
        </Form>
      </Drawer>

      {/* Preview modal */}
      <Modal
        open={preview.open}
        onCancel={() => setPreview((p) => ({ ...p, open: false }))}
        footer={null}
        width={720}
        title={`Preview: ${preview.subject}`}
      >
        <Tabs
          items={[
            {
              key: 'html',
              label: 'HTML',
              children: (
                <iframe
                  title="email-preview"
                  srcDoc={preview.html}
                  style={{ width: '100%', height: 560, border: '1px solid #e2e8f0', borderRadius: 8 }}
                />
              ),
            },
            {
              key: 'text',
              label: 'Plain text',
              children: (
                <pre style={{
                  background: '#f8fafc', padding: 16, borderRadius: 8, maxHeight: 560,
                  overflow: 'auto', fontSize: 13, whiteSpace: 'pre-wrap',
                }}>
                  {preview.text}
                </pre>
              ),
            },
          ]}
        />
      </Modal>

      {/* Send test modal */}
      <Modal
        open={!!testOpen}
        onCancel={() => { setTestOpen(null); setTestEmail(''); }}
        onOk={() => {
          if (!testOpen || !testEmail) { message.warning('Enter an email address'); return; }
          sendTestMut.mutate({ id: testOpen.id, toEmail: testEmail });
        }}
        confirmLoading={sendTestMut.isPending}
        okText="Send test"
        title={`Send test of "${testOpen?.display_name}"`}
      >
        <Form layout="vertical">
          <Form.Item
            label="Send to"
            extra="Placeholders render with their names in angle brackets, e.g. <first_name>."
          >
            <Input
              type="email"
              placeholder="you@example.com"
              value={testEmail}
              onChange={(e) => setTestEmail(e.target.value)}
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default EmailTemplatesTab;
