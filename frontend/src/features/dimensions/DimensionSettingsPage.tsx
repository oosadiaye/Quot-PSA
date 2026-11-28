import { useState } from 'react';
import { Button, Checkbox, Form, Input, Modal, Select, Switch, Table, Tag, message } from 'antd';
import { Link } from 'react-router-dom';
import {
  apiMessage, RECORD_TYPE_LABELS, useDimensionTypes, useDimensionValues, useDimensionWrite,
  type DimensionType, type DimensionValueRow, type RecordType,
} from './api';

const RECORD_OPTIONS = (Object.keys(RECORD_TYPE_LABELS) as RecordType[]).map((k) => ({ value: k, label: RECORD_TYPE_LABELS[k] }));

function TypeModal({ open, editing, types, onClose }: { open: boolean; editing: DimensionType | null; types: DimensionType[]; onClose: () => void }) {
  const [form] = Form.useForm();
  const write = useDimensionWrite('types');
  const applies: RecordType[] = Form.useWatch('applies_to', form) ?? [];
  const submit = async () => {
    const body = await form.validateFields();
    try {
      await write.mutateAsync({ id: editing?.id, body: { ...body, parent_type: body.parent_type ?? null, required_on: body.required_on ?? [] } });
      message.success(editing ? 'Dimension updated.' : 'Dimension created.');
      onClose();
    } catch (e) { message.error(apiMessage(e)); }
  };
  return (
    <Modal open={open} title={editing ? `Edit ${editing.name}` : 'New dimension'} onCancel={onClose} onOk={submit}
           okText="Save" confirmLoading={write.isPending} destroyOnHidden afterOpenChange={(o) => { if (o) form.setFieldsValue(editing ?? { applies_to: ['journal_line'], required_on: [], is_active: true }); }}>
      <Form form={form} layout="vertical" preserve={false}>
        <Form.Item name="name" label="Name" rules={[{ required: true }]} extra="What people see on forms and reports, e.g. Ward.">
          <Input data-testid="dim-name" />
        </Form.Item>
        <Form.Item name="code" label="Code" rules={[{ required: true, pattern: /^[-a-zA-Z0-9_]+$/, message: 'Letters, numbers, dashes and underscores only.' }]}
                   extra="Short and permanent, e.g. ward.">
          <Input data-testid="dim-code" disabled={!!editing} />
        </Form.Item>
        <Form.Item name="parent_type" label="Sits under (optional)" extra="A Ward can sit under a Zone: pick the Zone dimension here.">
          <Select allowClear showSearch optionFilterProp="label" placeholder="— none —" options={types.filter((t) => t.is_active && t.id !== editing?.id).map((t) => ({ value: t.id, label: t.name }))} />
        </Form.Item>
        <Form.Item name="applies_to" label="Show on" extra="The forms and reports where people can pick a value.">
          <Checkbox.Group options={RECORD_OPTIONS} />
        </Form.Item>
        <Form.Item name="required_on" label="Mandatory on" extra={applies.length ? undefined : 'Switch it on somewhere first.'}>
          <Checkbox.Group options={RECORD_OPTIONS.filter((o) => applies.includes(o.value))} />
        </Form.Item>
        {editing && <Form.Item name="is_active" label="Active" valuePropName="checked"><Switch /></Form.Item>}
      </Form>
    </Modal>
  );
}

function ValuesPanel({ type, parentType }: { type: DimensionType; parentType: DimensionType | null }) {
  const values = useDimensionValues(type.id);
  const parentValues = useDimensionValues(parentType?.id ?? null);
  const write = useDimensionWrite('values');
  const [form] = Form.useForm();
  const add = async () => {
    const body = await form.validateFields();
    try {
      await write.mutateAsync({ body: { dimension_type: type.id, code: body.code, name: body.name, parent: body.parent ?? null } });
      form.resetFields();
      message.success(`${type.name} added.`);
    } catch (e) { message.error(apiMessage(e)); }
  };
  const toggle = (row: DimensionValueRow) => write.mutate({ id: row.id, body: { is_active: !row.is_active } });
  return (
    <div data-testid={`dim-values-${type.code}`} style={{ padding: '4px 0 12px' }}>
      <Form form={form} layout="inline" style={{ marginBottom: 12, rowGap: 8 }} onFinish={add}>
        <Form.Item name="code" rules={[{ required: true, message: 'Code' }]}><Input placeholder="Code" data-testid="dim-value-code" style={{ width: 110 }} /></Form.Item>
        <Form.Item name="name" rules={[{ required: true, message: 'Name' }]}><Input placeholder={`${type.name} name`} data-testid="dim-value-name" style={{ width: 220 }} /></Form.Item>
        {parentType && (
          <Form.Item name="parent" rules={[{ required: true, message: `Pick a ${parentType.name}` }]}>
            <Select placeholder={`${parentType.name}…`} aria-label={parentType.name} style={{ width: 220 }} showSearch optionFilterProp="label"
                    options={(parentValues.data ?? []).filter((v) => v.is_active).map((v) => ({ value: v.id, label: `${v.code} — ${v.name}` }))} />
          </Form.Item>
        )}
        <Button type="primary" htmlType="submit" loading={write.isPending} data-testid="dim-value-add">Add {type.name}</Button>
      </Form>
      <Table<DimensionValueRow> size="small" rowKey="id" loading={values.isLoading} dataSource={values.data ?? []} pagination={{ pageSize: 10, hideOnSinglePage: true }}
        columns={[
          { title: 'Code', dataIndex: 'code', width: 120 },
          { title: 'Name', dataIndex: 'name' },
          ...(parentType ? [{ title: parentType.name, dataIndex: 'parent_code', width: 140 }] : []),
          { title: 'Active', dataIndex: 'is_active', width: 90, render: (_: boolean, row: DimensionValueRow) => <Switch size="small" checked={row.is_active} onChange={() => toggle(row)} aria-label={`Active ${row.code}`} /> },
        ]} />
    </div>
  );
}

export default function DimensionSettingsPage() {
  const types = useDimensionTypes();
  const [editing, setEditing] = useState<DimensionType | null>(null);
  const [open, setOpen] = useState(false);
  const list = types.data ?? [];
  const byId = new Map(list.map((t) => [t.id, t]));
  return (
    <div style={{ padding: '1.25rem', maxWidth: 1100, margin: '0 auto' }} data-testid="dimension-settings">
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12, gap: 12, flexWrap: 'wrap' }}>
        <div>
          <h1 style={{ margin: 0 }}>Custom dimensions</h1>
          <p style={{ margin: '4px 0 0', color: 'var(--color-text-muted, #666)' }}>
            Add your own analysis objects (a Ward, a Zone, a Polling Unit) and choose where people can pick them. Nothing changes until you add one.
          </p>
        </div>
        <Button type="primary" data-testid="dim-new" onClick={() => { setEditing(null); setOpen(true); }}>New dimension</Button>
      </header>
      <Table<DimensionType> rowKey="id" loading={types.isLoading} dataSource={list} pagination={false} locale={{ emptyText: 'No custom dimensions yet.' }}
        expandable={{ expandedRowRender: (t) => <ValuesPanel type={t} parentType={t.parent_type ? byId.get(t.parent_type) ?? null : null} />, rowExpandable: () => true }}
        columns={[
          { title: 'Name', dataIndex: 'name', render: (n: string, t) => <strong data-testid={`dim-row-${t.code}`}>{n}</strong> },
          { title: 'Code', dataIndex: 'code', width: 120 },
          { title: 'Sits under', dataIndex: 'parent_type_code', width: 130, render: (c: string | null) => c ?? '—' },
          { title: 'Shown on', dataIndex: 'applies_to', render: (a: RecordType[]) => a.length ? a.map((r) => <Tag key={r}>{RECORD_TYPE_LABELS[r]}</Tag>) : '—' },
          { title: 'Values', dataIndex: 'value_count', width: 80 },
          { title: 'Active', dataIndex: 'is_active', width: 80, render: (v: boolean) => (v ? 'Yes' : 'No') },
          { title: '', key: 'actions', width: 150, render: (_, t) => (
            <span style={{ display: 'inline-flex', gap: 8 }}>
              <Button size="small" onClick={() => { setEditing(t); setOpen(true); }}>Edit</Button>
              <Link to={`/accounting/reports/dimension/${t.code}`}>Report</Link>
            </span>) },
        ]} />
      <TypeModal open={open} editing={editing} types={list} onClose={() => setOpen(false)} />
    </div>
  );
}
