import { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '../../../api/client';
import Sidebar from '../../../components/Sidebar';
import PageHeader from '../../../components/PageHeader';
import LoadingScreen from '../../../components/common/LoadingScreen';
import { Plus, Pencil, X, Save, Layers } from 'lucide-react';

interface ProductType {
  id: number;
  name: string;
  name_display: string;
  description: string;
  inventory_account: number | null;
  inventory_account_name: string | null;
  expense_account: number | null;
  expense_account_name: string | null;
  revenue_account: number | null;
  revenue_account_name: string | null;
  clearing_account: number | null;
  clearing_account_name: string | null;
}

interface GLAccount {
  id: number;
  code: string;
  name: string;
  account_type: string;
  is_active: boolean;
}

// All GL field metadata
const GL_FIELD_CONFIG = {
  inventory_account: {
    label: 'Inventory GL',
    accountType: 'Asset',
    helpText: 'Balance Sheet — asset account for on-hand stock valuation',
  },
  expense_account: {
    label: 'Expense GL (COGS / Direct Expense)',
    accountType: 'Expense',
    helpText: 'P&L — expense account for cost of goods sold or direct expensing on receipt',
  },
  revenue_account: {
    label: 'Revenue GL',
    accountType: 'Income',
    helpText: 'P&L — income account for sales or service revenue recognition',
  },
  clearing_account: {
    label: 'Clearing GL (GR/IR)',
    accountType: 'Liability',
    helpText: 'Balance Sheet — liability account bridging goods receipt and invoice receipt',
  },
} as const;

type GLFieldKey = keyof typeof GL_FIELD_CONFIG;

// Which GL fields are visible (and required) per type
const GL_FIELDS_BY_TYPE: Record<string, GLFieldKey[]> = {
  stock:     ['inventory_account', 'expense_account', 'revenue_account', 'clearing_account'],
  non_stock: ['expense_account', 'clearing_account'],
  service:   ['revenue_account', 'clearing_account'],
  spares:    ['inventory_account', 'expense_account', 'revenue_account', 'clearing_account'],
};

const TYPE_OPTIONS = [
  { value: 'stock',     label: 'Stock',     badge: 'Balance Sheet + P&L' },
  { value: 'non_stock', label: 'Non-Stock', badge: 'P&L — direct expense' },
  { value: 'service',   label: 'Service',   badge: 'P&L — income' },
  { value: 'spares',    label: 'Spares',    badge: 'Balance Sheet + P&L' },
];

const ALL_GL_FIELDS: GLFieldKey[] = ['inventory_account', 'expense_account', 'revenue_account', 'clearing_account'];

export default function ProductTypes() {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [editingType, setEditingType] = useState<ProductType | null>(null);
  // Controlled: drives which GL fields render
  const [formType, setFormType] = useState<string>('');

  const { data: productTypes, isLoading } = useQuery<ProductType[]>({
    queryKey: ['product-types'],
    queryFn: () =>
      apiClient.get('/inventory/product-types/').then(res => {
        const d = res.data;
        return Array.isArray(d) ? d : Array.isArray(d?.results) ? d.results : [];
      }),
  });

  const { data: accountsData } = useQuery<GLAccount[]>({
    queryKey: ['gl-accounts-all'],
    queryFn: () =>
      apiClient.get('/accounting/accounts/', { params: { page_size: 9999 } }).then(res => {
        const d = res.data;
        return Array.isArray(d) ? d : Array.isArray(d?.results) ? d.results : [];
      }),
    staleTime: 5 * 60 * 1000,
  });

  const allAccounts = useMemo(() => (Array.isArray(accountsData) ? accountsData : []), [accountsData]);

  const accountsByType = useMemo(() => {
    const map: Record<string, GLAccount[]> = {};
    for (const acc of allAccounts) {
      if (!acc.is_active) continue;
      if (!map[acc.account_type]) map[acc.account_type] = [];
      map[acc.account_type].push(acc);
    }
    return map;
  }, [allAccounts]);

  const saveMutation = useMutation({
    mutationFn: (data: Partial<ProductType>) => {
      if (editingType) {
        return apiClient.patch(`/inventory/product-types/${editingType.id}/`, data);
      }
      return apiClient.post('/inventory/product-types/', data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['product-types'] });
      setShowForm(false);
      setEditingType(null);
      setFormType('');
    },
  });

  const openCreate = () => {
    setEditingType(null);
    setFormType('');
    setShowForm(true);
  };

  const openEdit = (type: ProductType) => {
    setEditingType(type);
    setFormType(type.name);
    setShowForm(true);
  };

  const closeForm = () => {
    setShowForm(false);
    setEditingType(null);
    setFormType('');
  };

  const handleSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const formData = new FormData(e.target as HTMLFormElement);
    const visibleFields = GL_FIELDS_BY_TYPE[formType] ?? [];

    const payload: Record<string, unknown> = {
      name: formType,
      description: formData.get('description') as string,
    };

    // Only include visible GL fields; null out the rest
    for (const field of ALL_GL_FIELDS) {
      if (visibleFields.includes(field)) {
        const val = formData.get(field);
        payload[field] = val ? Number(val) : null;
      } else {
        payload[field] = null;
      }
    }

    saveMutation.mutate(payload as Partial<ProductType>);
  };

  // ── Styles ─────────────────────────────────────────────
  const thStyle: React.CSSProperties = {
    padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600,
    textTransform: 'uppercase', color: 'var(--color-text-muted)', textAlign: 'left',
  };
  const tdStyle: React.CSSProperties = {
    padding: '1rem', color: 'var(--color-text)', fontSize: 'var(--text-sm)',
  };
  const labelStyle: React.CSSProperties = {
    display: 'block', marginBottom: '0.5rem', fontSize: 'var(--text-xs)',
    fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)',
  };
  const inputStyle: React.CSSProperties = {
    width: '100%', padding: '0.625rem', border: '2.5px solid var(--color-border)',
    borderRadius: '8px', background: 'var(--color-surface)', color: 'var(--color-text)',
    fontSize: 'var(--text-sm)',
  };
  const helpStyle: React.CSSProperties = {
    fontSize: '11px', color: 'var(--color-text-muted)', marginTop: '4px',
  };

  /** Render a single GL account select for a visible field */
  const renderGLSelect = (fieldKey: GLFieldKey, defaultValue: number | null | undefined) => {
    const config = GL_FIELD_CONFIG[fieldKey];
    const filtered = accountsByType[config.accountType] ?? [];

    return (
      <div key={fieldKey}>
        <label style={labelStyle}>
          {config.label} <span style={{ color: 'var(--color-error)' }}>*</span>
        </label>
        <select
          name={fieldKey}
          required
          defaultValue={defaultValue ?? ''}
          style={inputStyle}
        >
          <option value="">— Select {config.accountType} account —</option>
          {filtered.map(acc => (
            <option key={acc.id} value={acc.id}>
              {acc.code} — {acc.name}
            </option>
          ))}
        </select>
        <p style={helpStyle}>{config.helpText}</p>
      </div>
    );
  };

  if (isLoading) return <LoadingScreen message="Loading product types..." />;

  const visibleGLFields = GL_FIELDS_BY_TYPE[formType] ?? [];

  return (
    <div style={{ display: 'flex' }}>
      <Sidebar />
      <main style={{ flex: 1, minWidth: 0, marginLeft: '260px', padding: '2.5rem' }}>
        <PageHeader
          title="Product Types"
          subtitle="Configure product classifications and their GL account mappings."
          icon={<Layers size={22} color="white" />}
          actions={
            <button
              onClick={openCreate}
              style={{
                display: 'flex', alignItems: 'center', gap: '0.5rem',
                padding: '0.625rem 1.25rem', background: 'var(--color-primary)',
                color: 'white', border: 'none', borderRadius: '8px',
                fontWeight: 600, cursor: 'pointer',
              }}
            >
              <Plus size={18} />
              Add Product Type
            </button>
          }
        />

        {showForm && (
          <div className="card animate-fade" style={{ marginBottom: '2rem', padding: '1.5rem' }}>
            {/* Form header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem' }}>
              <h2 style={{ fontSize: 'var(--text-lg)', fontWeight: 600, color: 'var(--color-text)', margin: 0 }}>
                {editingType ? 'Edit Product Type' : 'New Product Type'}
              </h2>
              <button
                onClick={closeForm}
                style={{ padding: '0.375rem', background: 'transparent', border: '1px solid var(--color-border)', borderRadius: '6px', cursor: 'pointer', color: 'var(--color-text-muted)' }}
              >
                <X size={18} />
              </button>
            </div>

            <form onSubmit={handleSubmit}>
              {/* ── Type + Description ─────────────────────── */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1.5rem' }}>
                <div>
                  <label style={labelStyle}>
                    Type <span style={{ color: 'var(--color-error)' }}>*</span>
                  </label>
                  <select
                    value={formType}
                    onChange={e => setFormType(e.target.value)}
                    required
                    style={inputStyle}
                  >
                    <option value="">— Select product type —</option>
                    {TYPE_OPTIONS.map(opt => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                  {formType && (
                    <p style={helpStyle}>
                      {TYPE_OPTIONS.find(o => o.value === formType)?.badge}
                    </p>
                  )}
                </div>
                <div>
                  <label style={labelStyle}>Description</label>
                  <input
                    name="description"
                    defaultValue={editingType?.description ?? ''}
                    placeholder="Brief description"
                    style={inputStyle}
                  />
                </div>
              </div>

              {/* ── GL Account Assignments (type-driven) ────── */}
              {formType ? (
                // key=formType unmounts/remounts when type changes → resets defaultValues
                <div
                  key={formType}
                  style={{
                    padding: '1.25rem',
                    background: 'var(--color-surface)',
                    borderRadius: '8px',
                    border: '1px solid var(--color-border)',
                    marginBottom: '1rem',
                  }}
                >
                  <p style={{
                    fontSize: 'var(--text-xs)', fontWeight: 700, textTransform: 'uppercase',
                    color: 'var(--color-text-muted)', marginBottom: '1rem', letterSpacing: '0.5px',
                  }}>
                    GL Account Assignments — {TYPE_OPTIONS.find(o => o.value === formType)?.label}
                  </p>
                  <div style={{
                    display: 'grid',
                    gridTemplateColumns: visibleGLFields.length === 4 ? '1fr 1fr' : '1fr 1fr',
                    gap: '1rem',
                  }}>
                    {visibleGLFields.map(field =>
                      renderGLSelect(
                        field,
                        editingType && editingType.name === formType
                          ? editingType[field as keyof ProductType] as number | null
                          : null
                      )
                    )}
                  </div>
                </div>
              ) : (
                <div style={{
                  padding: '1.25rem',
                  background: 'var(--color-surface)',
                  borderRadius: '8px',
                  border: '1px dashed var(--color-border)',
                  marginBottom: '1rem',
                  textAlign: 'center',
                  color: 'var(--color-text-muted)',
                  fontSize: 'var(--text-sm)',
                }}>
                  Select a type above to configure GL account assignments
                </div>
              )}

              {saveMutation.isError && (
                <p style={{ color: 'var(--color-error)', fontSize: 'var(--text-sm)', marginBottom: '0.75rem' }}>
                  Failed to save. Please check all required GL accounts are selected.
                </p>
              )}

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '1.25rem' }}>
                <button
                  type="button"
                  onClick={closeForm}
                  style={{ padding: '0.5rem 1rem', background: 'transparent', border: '1px solid var(--color-border)', borderRadius: '8px', color: 'var(--color-text)', cursor: 'pointer', fontWeight: 600 }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={saveMutation.isPending || !formType}
                  style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.5rem 1rem', background: 'var(--color-primary)', color: 'white', border: 'none', borderRadius: '8px', fontWeight: 600, cursor: 'pointer', opacity: (!formType || saveMutation.isPending) ? 0.6 : 1 }}
                >
                  <Save size={16} />
                  {saveMutation.isPending ? 'Saving...' : 'Save'}
                </button>
              </div>
            </form>
          </div>
        )}

        {/* ── Product Types Table ────────────────────────── */}
        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ background: 'var(--color-surface)', textAlign: 'left' }}>
                <th style={thStyle}>Type</th>
                <th style={thStyle}>Description</th>
                <th style={thStyle}>Inventory GL</th>
                <th style={thStyle}>Expense GL</th>
                <th style={thStyle}>Revenue GL</th>
                <th style={thStyle}>Clearing GL</th>
                <th style={{ ...thStyle, textAlign: 'right' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {!Array.isArray(productTypes) || productTypes.length === 0 ? (
                <tr>
                  <td colSpan={7} style={{ padding: '3rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                    <Layers size={48} style={{ display: 'block', margin: '0 auto 1rem', opacity: 0.5 }} />
                    <p>No product types configured yet</p>
                  </td>
                </tr>
              ) : (
                productTypes.map(type => {
                  const applicable = GL_FIELDS_BY_TYPE[type.name] ?? ALL_GL_FIELDS;
                  const naCell = (
                    <span style={{ color: 'var(--color-text-muted)', fontSize: 'var(--text-xs)', fontStyle: 'italic' }}>
                      N/A
                    </span>
                  );
                  const glCell = (name: string | null) =>
                    name
                      ? <span>{name}</span>
                      : <span style={{ color: 'var(--color-warning)', fontSize: 'var(--text-xs)', fontWeight: 600 }}>Not set</span>;

                  return (
                    <tr key={type.id} style={{ borderBottom: '1px solid var(--color-border)' }}>
                      <td style={tdStyle}>
                        <span style={{
                          display: 'inline-block', padding: '0.2rem 0.6rem',
                          borderRadius: '9999px', fontSize: 'var(--text-xs)', fontWeight: 700,
                          background: type.name === 'stock' || type.name === 'spares'
                            ? 'rgba(59,130,246,0.1)' : type.name === 'service'
                            ? 'rgba(34,197,94,0.1)' : 'rgba(245,158,11,0.1)',
                          color: type.name === 'stock' || type.name === 'spares'
                            ? 'var(--color-info)' : type.name === 'service'
                            ? 'var(--color-success)' : 'var(--color-warning)',
                          textTransform: 'capitalize',
                        }}>
                          {type.name_display.replace('_', '-')}
                        </span>
                      </td>
                      <td style={{ ...tdStyle, color: type.description ? 'var(--color-text)' : 'var(--color-text-muted)' }}>
                        {type.description || '—'}
                      </td>
                      <td style={tdStyle}>
                        {applicable.includes('inventory_account') ? glCell(type.inventory_account_name) : naCell}
                      </td>
                      <td style={tdStyle}>
                        {applicable.includes('expense_account') ? glCell(type.expense_account_name) : naCell}
                      </td>
                      <td style={tdStyle}>
                        {applicable.includes('revenue_account') ? glCell(type.revenue_account_name) : naCell}
                      </td>
                      <td style={tdStyle}>
                        {applicable.includes('clearing_account') ? glCell(type.clearing_account_name) : naCell}
                      </td>
                      <td style={{ ...tdStyle, textAlign: 'right' }}>
                        <button
                          onClick={() => openEdit(type)}
                          style={{
                            padding: '0.375rem 0.75rem', background: 'transparent',
                            color: 'var(--color-text-muted)', border: '1px solid var(--color-border)',
                            borderRadius: '6px', fontSize: 'var(--text-xs)', fontWeight: 600,
                            cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: '0.25rem',
                          }}
                        >
                          <Pencil size={14} />
                          Edit
                        </button>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </main>
    </div>
  );
}
