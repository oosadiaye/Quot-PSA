/**
 * EntityForm: the create / edit form for any registry entity, rendered from its config.
 *
 * Laid out like an official form: numbered sections, one question per field, required fields marked, guidance and errors
 * beside the field they belong to, and the actions pinned at the bottom so they never scroll away. Fields marked
 * `secondary` sit in a second, collapsible section unless they are required or already filled.
 *
 * Props:
 *   config   the entity config describing fields
 *   initial  the existing record when editing, otherwise null (create)
 *   onSubmit called with the collected payload once it passes validation
 *   onCancel close the form
 */
import React, { useId, useMemo, useRef, useState } from 'react';
import './crud.css';
import { ReferenceField } from './ReferenceField';
import { singularLabel } from './labels';
import type { EntityConfig, EntityField } from './types';

interface EntityFormProps {
  config: EntityConfig;
  initial?: Record<string, any> | null;
  onSubmit: (payload: Record<string, any>) => void;
  onCancel: () => void;
  submitting?: boolean;
  error?: string | null;
}

const NUMERIC: EntityField['type'][] = ['number', 'decimal', 'integer'];
const isNumeric = (f: EntityField) => NUMERIC.includes(f.type);
const isEmpty = (v: unknown) => v === '' || v === null || v === undefined;
const asText = (v: unknown) => (v === null || v === undefined ? '' : String(v));

function seedValues(config: EntityConfig, initial?: Record<string, any> | null): Record<string, any> {
  const seed: Record<string, any> = {};
  for (const f of config.fields) {
    if (f.hideInForm) continue;
    const v = initial ? initial[f.name] : undefined;
    seed[f.name] = isEmpty(v) ? (f.type === 'boolean' ? false : '') : v;
  }
  return seed;
}

/** What is wrong with one field's value, or '' when it is fine. */
function problemWith(f: EntityField, v: unknown): string {
  if (f.readOnly || f.type === 'boolean' || f.type === 'object') return '';
  if (f.type === 'file') return f.required && !(v instanceof File) && !(typeof v === 'string' && v) ? 'Choose a file to upload.' : '';
  if (isEmpty(v)) return f.required ? 'This field is required.' : '';
  if (isNumeric(f)) {
    if (!Number.isFinite(Number(v))) return 'Enter a valid number.';
    if (f.type === 'integer' && !Number.isInteger(Number(v))) return 'Enter a whole number.';
  }
  return '';
}

export const EntityForm: React.FC<EntityFormProps> = ({ config, initial, onSubmit, onCancel, submitting, error }) => {
  const uid = useId();
  const scrollRef = useRef<HTMLDivElement>(null);
  const formFields = useMemo(() => config.fields.filter((f) => !f.hideInForm), [config]);
  const [values, setValues] = useState<Record<string, any>>(() => seedValues(config, initial));
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [summary, setSummary] = useState<string | null>(null);

  const primary = useMemo(() => {
    const main = formFields.filter((f) => !f.secondary || f.required);
    return main.length ? main : formFields;
  }, [formFields]);
  const more = useMemo(() => formFields.filter((f) => !primary.includes(f)), [formFields, primary]);
  const [moreOpen, setMoreOpen] = useState(() => !!initial && more.some((f) => !isEmpty(initial[f.name])));

  // The record being edited, named by the fields people recognise it by.
  const recordSummary = useMemo(() => {
    if (!initial) return [];
    // What people recognise a record by: the entity's own search key first, then the usual naming fields.
    const naming = [config.searchField, 'reference', 'code', 'name', 'title', 'description'];
    const headline = naming
      .map((n) => config.fields.find((f) => f.name === n))
      .filter((f, i, all): f is EntityField => !!f && all.indexOf(f) === i)
      .slice(0, 2);
    const id = config.fields.find((f) => f.name === config.idField);
    return [id, ...headline].filter((f): f is EntityField => !!f && !isEmpty(initial[f.name]));
  }, [config, initial]);

  const set = (name: string, v: unknown) => {
    setValues((p) => ({ ...p, [name]: v }));
    if (errors[name]) setErrors((p) => ({ ...p, [name]: '' }));
  };

  const submit = () => {
    const found: Record<string, string> = {};
    for (const f of formFields) {
      const problem = problemWith(f, values[f.name]);
      if (problem) found[f.name] = problem;
    }
    setErrors(found);
    const count = Object.keys(found).length;
    if (count) {
      setSummary(`${count} field${count === 1 ? ' needs' : 's need'} attention before this can be saved.`);
      if (more.some((f) => found[f.name])) setMoreOpen(true);
      requestAnimationFrame(() => scrollRef.current?.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus());
      return;
    }
    setSummary(null);
    const payload: Record<string, any> = {};
    for (const f of formFields) {
      if (f.readOnly) continue;
      const v = values[f.name];
      if (f.type === 'boolean') { payload[f.name] = !!v; continue; }
      if (f.type === 'file' && !(v instanceof File)) continue;   // an unchanged stored file is a URL: leave it alone
      if (isEmpty(v)) { if (f.required) payload[f.name] = v; continue; }
      payload[f.name] = v;
    }
    onSubmit(payload);
  };

  const control = (f: EntityField, id: string, described: string | undefined) => {
    const invalid = errors[f.name] ? true : undefined;
    const common = { id, 'aria-invalid': invalid, 'aria-describedby': described, 'aria-required': f.required || undefined };
    const v = values[f.name];

    if (f.reference && isNumeric(f)) {
      return <ReferenceField field={f} value={v} onChange={(next) => set(f.name, next)} id={id} invalid={!!invalid} />;
    }
    if (f.type === 'select' && f.options) {
      return (
        <select {...common} className="ef-input" disabled={f.readOnly} value={asText(v)} onChange={(e) => set(f.name, e.target.value)}>
          <option value="">Select…</option>
          {Object.entries(f.options).map(([k, label]) => <option key={k} value={k}>{label}</option>)}
        </select>
      );
    }
    if (f.type === 'longtext') {
      return <textarea {...common} className="ef-input" readOnly={f.readOnly} value={asText(v)} placeholder={f.placeholder} onChange={(e) => set(f.name, e.target.value)} />;
    }
    if (f.type === 'date' || f.type === 'datetime') {
      return (
        <input {...common} className="ef-input" type={f.type === 'date' ? 'date' : 'datetime-local'} readOnly={f.readOnly}
          value={f.type === 'datetime' ? asText(v).slice(0, 16) : asText(v).slice(0, 10)} onChange={(e) => set(f.name, e.target.value)} />
      );
    }
    if (isNumeric(f)) {
      return (
        <input {...common} className={f.type === 'integer' ? 'ef-input' : 'ef-input num'} type="number" inputMode={f.type === 'integer' ? 'numeric' : 'decimal'}
          step={f.type === 'integer' ? 1 : 'any'} readOnly={f.readOnly} value={asText(v)} placeholder={f.placeholder}
          onChange={(e) => set(f.name, e.target.value === '' ? '' : Number(e.target.value))} />
      );
    }
    if (f.type === 'file') {
      const current = typeof v === 'string' ? v : '';
      return (
        <div className="ef-file" aria-invalid={invalid}>
          <input {...common} type="file" data-testid={`file-${f.name}`} onChange={(e) => set(f.name, e.target.files?.[0] ?? '')} />
          {current && <span>Current file: <strong>{current.split('/').pop()}</strong></span>}
        </div>
      );
    }
    if (f.type === 'object') {
      return <input {...common} className="ef-input" readOnly value={typeof v === 'string' ? v : JSON.stringify(v ?? '')} />;
    }
    return <input {...common} className="ef-input" readOnly={f.readOnly} value={asText(v)} placeholder={f.placeholder} onChange={(e) => set(f.name, e.target.value)} />;
  };

  const field = (f: EntityField) => {
    const id = `${uid}-${f.name}`;
    const hintId = f.hint ? `${id}-hint` : undefined;
    const errId = errors[f.name] ? `${id}-err` : undefined;
    const described = [hintId, errId].filter(Boolean).join(' ') || undefined;

    if (f.type === 'boolean') {
      return (
        <div key={f.name} className="ef-field full">
          <div className="ef-switch-row">
            <div>
              <label className="ef-label" htmlFor={id}>{f.label}</label>
              {f.hint && <p className="ef-hint" id={hintId}>{f.hint}</p>}
            </div>
            <button id={id} type="button" role="switch" aria-checked={!!values[f.name]} aria-label={f.label} className="ef-switch"
              disabled={f.readOnly} onClick={() => set(f.name, !values[f.name])} />
          </div>
        </div>
      );
    }
    return (
      <div key={f.name} className={`ef-field${f.type === 'longtext' || f.type === 'object' ? ' full' : ''}`}>
        <label className="ef-label" htmlFor={id}>
          {f.label}{f.required && <span className="ef-req" aria-hidden="true">*</span>}
        </label>
        {control(f, id, described)}
        {f.hint && !errors[f.name] && <p className="ef-hint" id={hintId}>{f.hint}</p>}
        {errors[f.name] && <p className="ef-error" id={errId} role="alert">{errors[f.name]}</p>}
      </div>
    );
  };

  const singular = singularLabel(config.label, config.singular);

  return (
    <div className="ef">
      <div className="ef-scroll" ref={scrollRef}>
        {recordSummary.length > 0 && (
          <div className="ef-record" data-testid="ef-record">
            {recordSummary.map((f) => <span key={f.name}><b>{f.label}</b>{asText(initial?.[f.name])}</span>)}
          </div>
        )}

        {(error || summary) && (
          <div className="ef-alert" role="alert" data-testid="ef-error">{error ?? summary}</div>
        )}

        <section className="ef-section">
          <div className="ef-section-head">
            <span className="ef-section-no">01</span>
            <span className="ef-section-title">Details</span>
          </div>
          <div className="ef-grid">{primary.map(field)}</div>
        </section>

        {more.length > 0 && (
          <section className="ef-section">
            <button type="button" className="ef-section-head" aria-expanded={moreOpen} onClick={() => setMoreOpen((o) => !o)}>
              <span className="ef-section-no">02</span>
              <span className="ef-section-title">Additional information</span>
              <span className="ef-section-toggle">{moreOpen ? 'Hide' : `Show ${more.length}`}</span>
            </button>
            {moreOpen && <div className="ef-grid">{more.map(field)}</div>}
          </section>
        )}
      </div>

      <div className="ef-footer">
        <span className="ef-footer-note"><span className="ef-req">*</span> Required</span>
        <span className="ef-footer-actions">
          <button type="button" className="ef-btn" onClick={onCancel}>Cancel</button>
          <button type="button" className="ef-btn ef-btn-primary" onClick={submit} disabled={submitting}>
            {submitting ? 'Saving…' : initial ? 'Save changes' : `Create ${singular.toLowerCase()}`}
          </button>
        </span>
      </div>
    </div>
  );
};

export default EntityForm;
