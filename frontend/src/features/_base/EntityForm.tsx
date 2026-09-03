/**
 * EntityForm — generic create/edit modal form rendered from an
 * EntityConfig. One "primary key / label" summary identifier per entity is
 * surfaced as the top summary line; all other writable fields are rendered
 * as labelled inputs matching the Quot PSE input style.
 *
 * Props:
 *   config   — the entity config describing fields
 *   initial  — existing record when editing, otherwise null (create)
 *   onSubmit — called with the collected payload
 *   onCancel — close the modal
 *   submitting
 */
import React, { useMemo, useState } from 'react';
import type { EntityConfig, EntityField } from '../_base/types';

interface EntityFormProps {
  config: EntityConfig;
  initial?: Record<string, any> | null;
  onSubmit: (payload: Record<string, any>) => void;
  onCancel: () => void;
  submitting?: boolean;
  error?: string | null;
}

const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: '8px 10px',
  borderRadius: 8,
  border: '1px solid #cbd5e1',
  fontSize: 13,
  fontFamily: 'inherit',
  background: '#fff',
  color: '#0b1320',
};

const labelStyle: React.CSSProperties = {
  fontSize: 11,
  fontWeight: 700,
  color: '#475569',
  textTransform: 'uppercase',
  letterSpacing: '0.4px',
  marginBottom: 4,
  display: 'block',
};

function formatValue(field: EntityField, value: any): string {
  if (value === null || value === undefined) return '';
  if (field.type === 'boolean') return String(value);
  return String(value);
}

export const EntityForm: React.FC<EntityFormProps> = ({
  config,
  initial,
  onSubmit,
  onCancel,
  submitting,
  error,
}) => {
  const formFields = useMemo(
    () => config.fields.filter((f) => !f.hideInForm),
    [config],
  );

  // Initialise local form state from the config + existing record. The
  // form is remounted on every open (Modal destroyOnClose), so a lazy
  // initialiser is safe here — no effect-driven setState required.
  const [values, setValues] = useState<Record<string, any>>(() => {
    const seed: Record<string, any> = {};
    for (const f of config.fields) {
      if (f.hideInForm) continue;
      let v = initial ? initial[f.name] : undefined;
      if (v === undefined || v === null) {
        v = f.type === 'boolean' ? false : f.type === 'number' || f.type === 'decimal' || f.type === 'integer' ? '' : '';
      }
      seed[f.name] = v;
    }
    return seed;
  });

  // Summary = id field + a small set of headline text fields, shown above
  // the inputs (or the label field if one is marked primary).
  const summaryFields = useMemo(() => {
    const id = config.fields.find((f) => f.name === config.idField);
    const headline = config.fields.filter((f) => !f.hideInForm && (f.name === 'reference' || f.name === 'code' || f.name === 'name' || f.name === 'title' || f.name === 'description')).slice(0, 2);
    return [id, ...headline].filter(Boolean) as EntityField[];
  }, [config]);

  const set = (name: string, v: any) => setValues((p) => ({ ...p, [name]: v }));

  const renderControl = (field: EntityField) => {
    const value = formatValue(field, values[field.name]);
    if (field.type === 'boolean') {
      return (
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: '#0b1320' }}>
          <input
            type="checkbox"
            checked={!!values[field.name]}
            onChange={(e) => set(field.name, e.target.checked)}
          />
          {field.label}
        </label>
      );
    }
    if (field.type === 'select' && field.options) {
      return (
        <select
          style={inputStyle}
          value={value}
          onChange={(e) => set(field.name, e.target.value)}
        >
          <option value="">— Select —</option>
          {Object.entries(field.options).map(([k, v]) => (
            <option key={k} value={k}>{v}</option>
          ))}
        </select>
      );
    }
    if (field.type === 'longtext') {
      return (
        <textarea
          style={{ ...inputStyle, minHeight: 72, resize: 'vertical' }}
          value={value}
          onChange={(e) => set(field.name, e.target.value)}
          placeholder={field.placeholder}
        />
      );
    }
    if (field.type === 'date') {
      return (
        <input
          type="date"
          style={inputStyle}
          value={value}
          onChange={(e) => set(field.name, e.target.value)}
        />
      );
    }
    if (field.type === 'datetime') {
      return (
        <input
          type="datetime-local"
          style={inputStyle}
          value={value}
          onChange={(e) => set(field.name, e.target.value)}
        />
      );
    }
    if (field.type === 'number' || field.type === 'decimal' || field.type === 'integer') {
      return (
        <input
          type="number"
          step={field.type === 'integer' ? 1 : 'any'}
          style={inputStyle}
          value={value}
          onChange={(e) => set(field.name, e.target.value === '' ? '' : Number(e.target.value))}
        />
      );
    }
    if (field.type === 'object') {
      // Read-only display for nested / structured values.
      return (
        <input
          style={inputStyle}
          value={typeof value === 'string' ? value : JSON.stringify(value ?? '')}
          readOnly
        />
      );
    }
    // text
    return (
      <input
        style={inputStyle}
        value={value}
        onChange={(e) => set(field.name, e.target.value)}
        placeholder={field.placeholder}
      />
    );
  };

  const submit = () => {
    // Drop empty numeric strings and empty values that aren't required.
    const payload: Record<string, any> = {};
    for (const f of formFields) {
      const v = values[f.name];
      if (f.type === 'boolean') { payload[f.name] = !!v; continue; }
      if (v === '' || v === null || v === undefined) {
        if (f.required) payload[f.name] = v;
        continue;
      }
      payload[f.name] = v;
    }
    onSubmit(payload);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      {initial && summaryFields.length > 0 && (
        <div
          style={{
            background: '#f8fafc',
            border: '1px solid #e2e8f0',
            borderRadius: 10,
            padding: '10px 14px',
            fontSize: 13,
            color: '#334155',
          }}
        >
          {summaryFields.map((f) => (
            <span key={f.name} style={{ marginRight: 16 }}>
              <strong>{f.label}:</strong>{' '}{formatValue(f, initial?.[f.name]) ?? '—'}
            </span>
          ))}
        </div>
      )}

      {error && (
        <div style={{ background: '#fef2f2', color: '#b91c1c', padding: '8px 12px', borderRadius: 8, fontSize: 13 }}>
          {error}
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px 16px' }}>
        {formFields.map((f) => (
          <div key={f.name} style={{ gridColumn: f.type === 'longtext' ? '1 / -1' : undefined }}>
            <label style={labelStyle}>{f.label}{f.required ? ' *' : ''}</label>
            {renderControl(f)}
          </div>
        ))}
      </div>

      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 8 }}>
        <button
          type="button"
          onClick={onCancel}
          style={{ ...inputStyle, width: 'auto', padding: '8px 16px', background: '#fff', border: '1px solid #cbd5e1', color: '#242a88', fontWeight: 600 }}
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={submit}
          disabled={submitting}
          style={{
            ...inputStyle,
            width: 'auto',
            padding: '8px 18px',
            background: 'linear-gradient(135deg, #242a88, #2e35a0)',
            border: 'none',
            color: '#fff',
            fontWeight: 600,
          }}
        >
          {submitting ? 'Saving…' : initial ? 'Save Changes' : 'Create'}
        </button>
      </div>
    </div>
  );
};

export default EntityForm;
