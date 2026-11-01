/**
 * ModuleCrudPage — a single page that renders every entity of a future
 * module as a set of tabs, each tab giving full CRUD through a responsive
 * table + modal form. Driven entirely by the module's config.ts.
 */
import React, { useEffect, useMemo, useState } from 'react';
import { Modal, message } from 'antd';
import { SearchOutlined, PlusOutlined, UploadOutlined, EditOutlined, DeleteOutlined, ReloadOutlined, InboxOutlined } from '@ant-design/icons';
import PageHeader from '../../components/PageHeader';
import { ListPageShell, StatusBadge, ThemedButton } from '../../components/layout';
import ResponsiveTable from '../../components/ResponsiveTable';
import type { Column } from '../../components/ResponsiveTable';
import type { EntityConfig, ModuleConfig } from '../_base/types';
import { EntityForm } from '../_base/EntityForm';
import ImportDialog from './ImportDialog';
import { useEntityList, useEntityCreate, useEntityUpdate, useEntityDelete } from '../_base/useEntityCrud';
import { plainName, singularLabel } from './labels';
import './crud.css';

interface ModuleCrudPageProps {
  config: ModuleConfig;
  /**
   * Extra content a module wants above the register. It renders inside the page shell, so it gets the same offset and padding.
   * Pass a function to vary it by tab and to open the form from the panel (a new record can start with `defaults`).
   */
  banner?: React.ReactNode | ((ctx: BannerContext) => React.ReactNode);
  /** For a tab whose entity sets `panel`: the screen that replaces the register under the tabs. */
  panel?: (ctx: BannerContext) => React.ReactNode;
}

export interface BannerContext {
  activeKey: string;
  openForm: (entityKey: string, record?: Record<string, any> | null, defaults?: Record<string, any>) => void;
}

const listBase = (module: ModuleConfig, entity: EntityConfig) =>
  `${module.basePath}/${entity.plural}/`;

const formatCell = (field: any, value: any): React.ReactNode => {
  if (value === null || value === undefined) return '—';
  if (field.type === 'boolean') return value ? 'Yes' : 'No';
  if (field.type === 'select' && field.options) return field.options[String(value)] ?? String(value);
  if (field.type === 'object') return Array.isArray(value) ? value.length.toLocaleString() : '—';
  if (field.type === 'decimal' || field.type === 'number') {
    const n = Number(value);
    return isNaN(n) ? String(value) : n.toLocaleString(undefined, { maximumFractionDigits: 2 });
  }
  // Nigerian convention: DD/MM/YYYY on screen (ISO stays in the API and the form inputs).
  if (field.type === 'date' && typeof value === 'string' && /^\d{4}-\d{2}-\d{2}/.test(value)) return value.slice(0, 10).split('-').reverse().join('/');
  return String(value);
};

/** The server's own reason for a refused save: detail/error, else the first field error named by its label. */
function describeSaveError(e: any, entity: EntityConfig): string {
  const data = e?.response?.data;
  if (data?.detail) return String(data.detail);
  if (data?.error) return String(data.error);
  if (data && typeof data === 'object') {
    const [name, msg] = Object.entries(data).find(([, v]) => v) ?? [];
    if (name) {
      const label = entity.fields.find((f) => f.name === name)?.label ?? name.replace(/_/g, ' ');
      return `${label}: ${Array.isArray(msg) ? msg[0] : msg}`;
    }
  }
  return e?.response?.status >= 500 ? 'The server could not save this record. Please try again.' : 'Save failed';
}

export const ModuleCrudPage: React.FC<ModuleCrudPageProps> = ({ config, banner, panel }) => {
  const [formError, setFormError] = useState<string | null>(null);
  const [activeKey, setActiveKey] = useState(config.entities[0]?.key ?? '');
  const [search, setSearch] = useState('');
  const [importing, setImporting] = useState(false);
  const [modal, setModal] = useState<{ entity: EntityConfig; record: Record<string, any> | null; defaults?: Record<string, any> } | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(10);

  useEffect(() => { setFormError(null); }, [modal]);

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
  const singular = activeEntity ? singularLabel(activeEntity.label, activeEntity.singular) : '';
  const total = list.data?.count ?? 0;
  const searching = search.trim() !== '';
  const firstShown = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const lastShown = Math.min(page * pageSize, total);

  const handleSubmit = async (payload: Record<string, any>) => {
    if (!activeEntity || !modal) return;
    setFormError(null);
    try {
      if (modal.record) {
        await updateMut.mutateAsync({ id: modal.record[activeEntity.idField ?? 'id'], payload });
        message.success(`${singular} updated`);
      } else {
        await createMut.mutateAsync(payload);
        message.success(`${singular} created`);
      }
      setModal(null);
    } catch (e: any) {
      setFormError(describeSaveError(e, activeEntity));
    }
  };

  const handleDelete = (row: Record<string, any>) => {
    if (!activeEntity) return;
    const id = row[activeEntity.idField ?? 'id'];
    Modal.confirm({
      title: `Delete this ${plainName(singular)}?`,
      content: 'This cannot be undone.',
      okText: 'Delete',
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          await deleteMut.mutateAsync(id);
          message.success(`${singular} deleted`);
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
      render: (row: Record<string, any>) => {
        if (f.name !== activeEntity.statusField) return formatCell(f, row[f.name]);
        const raw = String(row[f.name] ?? '');
        return <StatusBadge status={raw}>{f.options?.[raw] ?? (raw || '—')}</StatusBadge>;
      },
    }));
    cols.push({
      key: '__actions',
      header: '',
      align: 'right',
      mobilePrimary: false,
      render: (row) => (
        <span style={{ display: 'inline-flex', gap: 2 }}>
          <button type="button" className="reg-act" title="Edit" aria-label={`Edit ${plainName(singular)}`}
            onClick={() => setModal({ entity: activeEntity, record: row })}><EditOutlined /></button>
          <button type="button" className="reg-act danger" title="Delete" aria-label={`Delete ${plainName(singular)}`}
            onClick={(e) => { e.stopPropagation(); handleDelete(row); }}><DeleteOutlined /></button>
        </span>
      ),
    });
    return cols;
  }, [activeEntity, search]);

  const refresh = () => list.refetch();

  const openNew = () => activeEntity && setModal({ entity: activeEntity, record: null });
  const openForm: BannerContext['openForm'] = (entityKey, record = null, defaults) => {
    const entity = config.entities.find((e) => e.key === entityKey);
    if (!entity) return;
    setActiveKey(entityKey);
    setModal({ entity, record, defaults });
  };

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

      {typeof banner === 'function' ? banner({ activeKey, openForm }) : banner}

      <div className="reg-tabs" role="tablist" aria-label={`${config.label} sections`}>
        {config.entities.map((e) => (
          <button
            key={e.key}
            type="button"
            role="tab"
            className="reg-tab"
            aria-selected={e.key === activeKey}
            onClick={() => { setActiveKey(e.key); setPage(1); setSearch(''); }}
          >
            {e.label}
          </button>
        ))}
      </div>

      {activeEntity?.panel && panel ? panel({ activeKey, openForm }) : activeEntity && (
        <>
          <div className="reg-head">
            <div>
              <h2 className="reg-title">{activeEntity.label}</h2>
              <p className="reg-sub" data-testid="reg-count">
                {list.data
                  ? `${total.toLocaleString()} ${total === 1 ? 'record' : 'records'}${searching ? ` matching \u201c${search.trim()}\u201d` : ''}`
                  : 'Loading\u2026'}
              </p>
            </div>
            <div className="reg-tools">
              <label className="reg-search">
                <SearchOutlined />
                <input
                  type="search"
                  aria-label={`Search ${plainName(activeEntity.label)}`}
                  placeholder={`Search ${plainName(activeEntity.label)}\u2026`}
                  value={search}
                  onChange={(e) => { setSearch(e.target.value); setPage(1); }}
                />
              </label>
              {activeEntity.importable && (
                <button type="button" className="ef-btn" data-testid="reg-import" onClick={() => setImporting(true)}>
                  <UploadOutlined /> Import
                </button>
              )}
              <button type="button" className="ef-btn ef-btn-primary" onClick={openNew}>
                <PlusOutlined /> New {singular}
              </button>
            </div>
          </div>

          <div className="reg-surface">
            {list.isLoading ? (
              <div className="reg-skeleton" aria-busy="true" aria-label="Loading records"><span /><span /><span /><span /></div>
            ) : list.isError ? (
              <div className="reg-empty" role="alert">
                <h3>These records could not be loaded</h3>
                <p>Check your connection and try again. If it keeps happening, tell your administrator.</p>
                <button type="button" className="ef-btn" onClick={refresh}>Try again</button>
              </div>
            ) : rows.length === 0 ? (
              <div className="reg-empty" data-testid="reg-empty">
                <div className="reg-empty-mark" aria-hidden="true"><InboxOutlined /></div>
                <h3>{searching ? 'Nothing matches that search' : `No ${plainName(activeEntity.label)} yet`}</h3>
                <p>
                  {searching
                    ? `No ${plainName(activeEntity.label)} match \u201c${search.trim()}\u201d. Check the spelling or clear the search.`
                    : `${activeEntity.label} you add will be listed here.`}
                </p>
                {searching
                  ? <button type="button" className="ef-btn" onClick={() => setSearch('')}>Clear search</button>
                  : <button type="button" className="ef-btn ef-btn-primary" onClick={openNew}><PlusOutlined /> New {singular}</button>}
              </div>
            ) : (
              <ResponsiveTable
                data={rows}
                columns={columns as Column<Record<string, any>>[]}
                keyField={(activeEntity.idField ?? 'id') as any}
                emptyState=""
                ariaLabel={activeEntity.label}
              />
            )}
            {total > 0 && (
              <div className="reg-pager">
                <span data-testid="reg-range">Showing {firstShown.toLocaleString()}–{lastShown.toLocaleString()} of {total.toLocaleString()}</span>
                <span className="reg-pager-actions">
                  <button type="button" className="ef-btn" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Previous</button>
                  <button type="button" className="ef-btn" disabled={page * pageSize >= total} onClick={() => setPage((p) => p + 1)}>Next</button>
                </span>
              </div>
            )}
          </div>
        </>
      )}

      {activeEntity?.importable && (
        <ImportDialog open={importing} entity={activeEntity} basePath={listBase(config, activeEntity)}
          onClose={() => setImporting(false)} onImported={refresh} />
      )}

      <Modal
        open={!!modal}
        onCancel={() => setModal(null)}
        footer={null}
        centered
        width="min(780px, calc(100vw - 24px))"
        className="ef-modal"
        destroyOnHidden
        maskClosable={false}
        title={modal ? (
          <div>
            <div style={{ fontSize: 16, fontWeight: 700 }}>
              {modal.record ? `Edit ${plainName(singularLabel(modal.entity.label, modal.entity.singular))}` : `New ${plainName(singularLabel(modal.entity.label, modal.entity.singular))}`}
            </div>
            <div style={{ fontSize: 12.5, fontWeight: 400, color: 'var(--color-text-muted)' }}>{config.label}</div>
          </div>
        ) : ''}
        styles={{ container: { padding: 0, overflow: 'hidden' }, header: { margin: 0, padding: '18px 28px 14px' }, body: { padding: 0 } }}
      >
        {modal && (
          <EntityForm
            config={modal.entity}
            initial={modal.record}
            defaults={modal.defaults}
            onCancel={() => setModal(null)}
            onSubmit={handleSubmit}
            error={formError}
            submitting={createMut.isPending || updateMut.isPending}
          />
        )}
      </Modal>
    </ListPageShell>
  );
};

export default ModuleCrudPage;
