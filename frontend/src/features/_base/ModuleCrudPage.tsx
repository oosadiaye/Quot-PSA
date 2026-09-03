/**
 * ModuleCrudPage — a single page that renders every entity of a future
 * module as a set of tabs, each tab giving full CRUD through a responsive
 * table + modal form. Driven entirely by the module's config.ts.
 */
import React, { useMemo, useState } from 'react';
import { Modal, message, Input } from 'antd';
import { SearchOutlined, PlusOutlined, EditOutlined, DeleteOutlined, ReloadOutlined } from '@ant-design/icons';
import PageHeader from '../../components/PageHeader';
import { ListPageShell, SectionCard, StatusBadge, ThemedButton } from '../../components/layout';
import ResponsiveTable from '../../components/ResponsiveTable';
import type { Column } from '../../components/ResponsiveTable';
import type { EntityConfig, ModuleConfig } from '../_base/types';
import { EntityForm } from '../_base/EntityForm';
import { useEntityList, useEntityCreate, useEntityUpdate, useEntityDelete } from '../_base/useEntityCrud';

interface ModuleCrudPageProps {
  config: ModuleConfig;
}

const listBase = (module: ModuleConfig, entity: EntityConfig) =>
  `${module.basePath}/${entity.plural}/`;

const formatCell = (field: any, value: any): React.ReactNode => {
  if (value === null || value === undefined) return '—';
  if (field.type === 'boolean') return value ? 'Yes' : 'No';
  if (field.type === 'decimal' || field.type === 'number') {
    const n = Number(value);
    return isNaN(n) ? String(value) : n.toLocaleString(undefined, { maximumFractionDigits: 2 });
  }
  if (field.type === 'date' && typeof value === 'string' && value.length >= 10) return value.slice(0, 10);
  return String(value);
};

export const ModuleCrudPage: React.FC<ModuleCrudPageProps> = ({ config }) => {
  const [activeKey, setActiveKey] = useState(config.entities[0]?.key ?? '');
  const [search, setSearch] = useState('');
  const [modal, setModal] = useState<{ entity: EntityConfig; record: Record<string, any> | null } | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(10);

  const activeEntity = useMemo(
    () => config.entities.find((e) => e.key === activeKey) ?? config.entities[0],
    [config, activeKey],
  );

  const base = activeEntity ? listBase(config, activeEntity) : '';
  const filters = useMemo(() => {
    const f: Record<string, any> = { page, page_size: pageSize };
    if (search.trim()) f['search'] = search.trim();
    return { ...(activeEntity?.fixedParams ?? {}), ...f };
  }, [search, page, pageSize, activeEntity]);

  const list = useEntityList(config.key, base, filters);
  const createMut = useEntityCreate(config.key, base);
  const updateMut = useEntityUpdate(config.key, base);
  const deleteMut = useEntityDelete(config.key, base);

  const rows: Record<string, any>[] = list.data?.results ?? [];

  const handleSubmit = async (payload: Record<string, any>) => {
    if (!activeEntity || !modal) return;
    try {
      if (modal.record) {
        await updateMut.mutateAsync({ id: modal.record[activeEntity.idField ?? 'id'], payload });
        message.success('Record updated');
      } else {
        await createMut.mutateAsync(payload);
        message.success('Record created');
      }
      setModal(null);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.response?.data?.error || 'Save failed');
    }
  };

  const handleDelete = (row: Record<string, any>) => {
    if (!activeEntity) return;
    const id = row[activeEntity.idField ?? 'id'];
    Modal.confirm({
      title: `Delete this ${activeEntity.label.toLowerCase()}?`,
      content: 'This action cannot be undone.',
      okText: 'Delete',
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          await deleteMut.mutateAsync(id);
          message.success('Record deleted');
        } catch (e: any) {
          message.error(e?.response?.data?.detail || 'Delete failed');
        }
      },
    });
  };

  const columns: Column<Record<string, any>>[] = useMemo(() => {
    if (!activeEntity) return [];
    const cols: Column<Record<string, any>>[] = activeEntity.columns.map((f) => ({
      key: f.name,
      header: f.label,
      align: f.numeric ? ('right' as const) : ('left' as const),
      mobilePrimary: f === activeEntity.columns[0] || f === activeEntity.columns[1],
      render: (row: Record<string, any>) =>
        f.name === activeEntity.statusField ? (
          <StatusBadge status={String(row[f.name] ?? '')}>{String(row[f.name] ?? '—')}</StatusBadge>
        ) : (
          formatCell(f, row[f.name])
        ),
    }));
    cols.push({
      key: '__actions',
      header: '',
      align: 'right',
      mobilePrimary: false,
      render: (row) => (
        <span style={{ display: 'inline-flex', gap: 6 }}>
          <ThemedButton size="sm" variant="ghost" icon={<EditOutlined />} title="Edit" children=""
            onClick={() => setModal({ entity: activeEntity, record: row })} />
          <ThemedButton size="sm" variant="danger" icon={<DeleteOutlined />} title="Delete" children=""
            onClick={(e) => { e?.stopPropagation(); handleDelete(row); }} />
        </span>
      ),
    });
    return cols;
  }, [activeEntity, search]);

  const refresh = () => list.refetch();

  return (
    <ListPageShell>
      <PageHeader
        title={config.label}
        subtitle={config.description}
        icon={<span style={{ fontSize: 22 }}>{config.icon}</span>}
        actions={
          <ThemedButton size="sm" variant="secondary" icon={<ReloadOutlined />} onClick={refresh}>
            Refresh
          </ThemedButton>
        }
      />

      {/* Entity tabs */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 16 }}>
        {config.entities.map((e) => {
          const active = e.key === activeKey;
          return (
            <button
              key={e.key}
              onClick={() => { setActiveKey(e.key); setPage(1); }}
              style={{
                padding: '8px 14px',
                borderRadius: 999,
                border: active ? '1px solid #242a88' : '1px solid #cbd5e1',
                background: active ? '#242a88' : '#ffffff',
                color: active ? '#ffffff' : '#475569',
                fontSize: 12.5,
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              {e.label}
            </button>
          );
        })}
      </div>

      {activeEntity && (
        <SectionCard
          title={`${activeEntity.label} Register`}
          subtitle={list.data ? `${list.data.count} record(s)` : 'Loading…'}
          actions={
            <ThemedButton size="sm" icon={<PlusOutlined />} onClick={() => setModal({ entity: activeEntity, record: null })}>
              New {activeEntity.label}
            </ThemedButton>
          }
        >
          <div style={{ marginBottom: 12 }}>
            <Input
              allowClear
              prefix={<SearchOutlined style={{ color: '#94a3b8' }} />}
              placeholder={`Search ${activeEntity.label.toLowerCase()}…`}
              style={{ maxWidth: 340 }}
              value={search}
              onChange={(e) => { setSearch(e.target.value); setPage(1); }}
            />
          </div>
          <ResponsiveTable
            data={rows}
            columns={columns as Column<Record<string, any>>[]}
            keyField={(activeEntity.idField ?? 'id') as any}
            emptyState={`No ${activeEntity.label.toLowerCase()} records found.`}
            ariaLabel={activeEntity.label}
          />
          <div style={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'center', gap: 8, marginTop: 12 }}>
            <ThemedButton size="sm" variant="secondary" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
              Prev
            </ThemedButton>
            <span style={{ fontSize: 13, color: '#475569' }}>Page {page}</span>
            <ThemedButton size="sm" variant="secondary" disabled={!list.data || page * pageSize >= list.data.count} onClick={() => setPage((p) => p + 1)}>
              Next
            </ThemedButton>
          </div>
        </SectionCard>
      )}

      <Modal
        title={modal ? (modal.record ? `Edit ${modal.entity.label}` : `New ${modal.entity.label}`) : ''}
        open={!!modal}
        onCancel={() => setModal(null)}
        footer={null}
        width={720}
        destroyOnClose
      >
        {modal && (
          <EntityForm
            config={modal.entity}
            initial={modal.record}
            onCancel={() => setModal(null)}
            onSubmit={handleSubmit}
            submitting={createMut.isPending || updateMut.isPending}
          />
        )}
      </Modal>
    </ListPageShell>
  );
};

export default ModuleCrudPage;
