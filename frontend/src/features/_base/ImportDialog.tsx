import { useMemo, useState } from 'react';
import { Modal } from 'antd';
import { DownloadOutlined, UploadOutlined } from '@ant-design/icons';
import apiClient from '../../api/client';
import { importableFields, parseCsv, planImport, templateCsv, type ImportPlan, type PlannedRow } from './csvImport';
import { describeRecord, recordNames, resolveReferencePath } from './referenceRegistry';
import { plainName, singularLabel } from './labels';
import type { EntityConfig } from './types';

interface Props {
  open: boolean;
  entity: EntityConfig;
  basePath: string;
  onClose: () => void;
  /** Called once rows have been saved, so the register can reload. */
  onImported: () => void;
}

const MAX_LOOKUP_MATCHES = 25;

function apiMessage(e: unknown): string {
  const data = (e as { response?: { data?: unknown } })?.response?.data;
  if (typeof data === 'string') return data.slice(0, 200);
  if (data && typeof data === 'object') {
    const parts = Object.entries(data as Record<string, unknown>).map(([k, v]) => {
      const msg = Array.isArray(v) ? v.join(' ') : String(v);
      return k === 'detail' || k === 'non_field_errors' ? msg : `${k}: ${msg}`;
    });
    if (parts.length) return parts.join(' ');
  }
  return 'The server did not accept this row.';
}

/** Find the record a cell names. Exactly one match is a hit; none or several is an error that says what to do. */
async function resolveLookup(
  entity: EntityConfig, fieldName: string, text: string, cache: Map<string, Promise<number | string>>,
): Promise<number | string> {
  const field = entity.fields.find((f) => f.name === fieldName)!;
  const key = `${field.reference!.module}.${field.reference!.entity}|${text.toLowerCase()}`;
  const hit = cache.get(key);
  if (hit) return hit;
  const job = (async () => {
    const path = await resolveReferencePath(field.reference!);
    if (!path) return `Cannot look up ${field.label}: enter the record's ID.`;
    const data = (await apiClient.get(path, { params: { search: text, page_size: MAX_LOOKUP_MATCHES } })).data;
    const rows = (data.results ?? data ?? []) as Record<string, any>[];
    const exact = rows.filter((r) => recordNames(r).includes(text.toLowerCase()));
    if (exact.length === 1) return exact[0].id as number;
    if (exact.length > 1) {
      const some = exact.slice(0, 4).map((r) => `${describeRecord(r)} = ID ${r.id}`).join('; ');
      return `${field.label} “${text}” matches ${exact.length} records (${some}). Enter the ID instead.`;
    }
    if (/^\d+$/.test(text)) {
      try { return (await apiClient.get(`${path}${text}/`)).data.id as number; } catch { /* not an ID either */ }
    }
    return `No ${plainName(field.label)} matches “${text}”.`;
  })();
  cache.set(key, job);
  return job;
}

type Phase = 'choose' | 'checking' | 'ready' | 'saving' | 'done';

/**
 * Import a register from a CSV: download the template, fill it in, choose the file. Every row is checked, and every linked
 * record found, before anything is saved; rows are then saved one by one through the register's own API, so the server's
 * rules apply as they do for the form. Rows that fail are listed with the reason and can be fixed and imported again.
 */
export default function ImportDialog({ open, entity, basePath, onClose, onImported }: Props) {
  const single = plainName(singularLabel(entity.label, entity.singular));
  const [phase, setPhase] = useState<Phase>('choose');
  const [plan, setPlan] = useState<ImportPlan | null>(null);
  const [fileName, setFileName] = useState('');
  const [rows, setRows] = useState<PlannedRow[]>([]);
  const [saved, setSaved] = useState(0);
  const [failed, setFailed] = useState<{ line: number; message: string }[]>([]);
  const fields = useMemo(() => importableFields(entity), [entity]);

  const reset = () => { setPhase('choose'); setPlan(null); setRows([]); setSaved(0); setFailed([]); setFileName(''); };
  const close = () => { reset(); onClose(); };

  const download = () => {
    const url = URL.createObjectURL(new Blob([templateCsv(entity)], { type: 'text/csv;charset=utf-8' }));
    const a = document.createElement('a');
    a.href = url;
    a.download = `${entity.plural}-import-template.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };

  const choose = async (file: File | undefined) => {
    if (!file) return;
    reset();
    setFileName(file.name);
    setPhase('checking');
    const next = planImport(entity, parseCsv(await file.text()));
    setPlan(next);
    const cache = new Map<string, Promise<number | string>>();
    const checked: PlannedRow[] = [];
    for (const row of next.rows) {
      const payload = { ...row.payload };
      const errors = [...row.errors];
      for (const [name, text] of Object.entries(row.lookups)) {
        try {
          const found = await resolveLookup(entity, name, text, cache);
          if (typeof found === 'number') payload[name] = found; else errors.push(found);
        } catch { errors.push(`Could not look up “${text}”. Try again.`); }
      }
      checked.push({ ...row, payload, errors });
    }
    setRows(checked);
    setPhase('ready');
  };

  // A problem with the file as a whole (a required column missing) means no row can be trusted, so nothing is saved.
  const blocked = (plan?.fileErrors.length ?? 0) > 0;
  const valid = blocked ? [] : rows.filter((r) => r.errors.length === 0);
  const invalid = blocked ? [] : rows.filter((r) => r.errors.length > 0);
  const noun = valid.length === 1 ? single : plainName(entity.label);

  const save = async () => {
    setPhase('saving');
    const problems: { line: number; message: string }[] = [];
    let ok = 0;
    for (const row of valid) {
      try { await apiClient.post(basePath, row.payload); ok += 1; } catch (e) { problems.push({ line: row.line, message: apiMessage(e) }); }
      setSaved(ok);
    }
    setFailed(problems);
    setPhase('done');
    if (ok > 0) onImported();
  };

  return (
    <Modal open={open} onCancel={close} footer={null} centered width="min(860px, calc(100vw - 24px))" className="ef-modal" destroyOnHidden
      title={(
        <div>
          <div style={{ fontSize: 16, fontWeight: 700 }}>Import {plainName(entity.label)}</div>
          <div style={{ fontSize: 12.5, fontWeight: 400, color: 'var(--color-text-muted)' }}>From a CSV file, checked before anything is saved</div>
        </div>
      )}
      styles={{ container: { padding: 0, overflow: 'hidden' }, header: { margin: 0, padding: '18px 28px 14px' }, body: { padding: 0 } }}>
      <div className="imp" data-testid="import-dialog">
        <ol className="imp-steps">
          <li>
            <b>Download the template.</b> It has a column for each thing you enter ({fields.map((f) => f.label).join(', ')}) and an example row to copy.
            Dates are DD/MM/YYYY. A linked record is entered by its code or name.
            <div><button type="button" className="ef-btn" data-testid="import-template" onClick={download}><DownloadOutlined /> Download template</button></div>
          </li>
          <li>
            <b>Fill it in and choose the file.</b> A * marks a column you must fill.
            <div>
              <label className="ef-btn imp-file">
                <UploadOutlined /> {fileName ? 'Choose another file' : 'Choose CSV file'}
                <input type="file" accept=".csv,text/csv" data-testid="import-file" aria-label="CSV file to import"
                  onChange={(e) => { void choose(e.target.files?.[0]); e.target.value = ''; }} />
              </label>
              {fileName && <span className="imp-name">{fileName}</span>}
            </div>
          </li>
        </ol>

        {phase === 'checking' && <p className="imp-note" aria-busy="true">Checking the file…</p>}

        {plan && phase !== 'checking' && (
          <div className="imp-result">
            {plan.fileErrors.map((m) => <p key={m} className="imp-bad" role="alert">{m}</p>)}
            {plan.ignoredColumns.length > 0 && <p className="imp-note">Not used: {plan.ignoredColumns.join(', ')}.</p>}
            {plan.fileErrors.length === 0 && phase !== 'done' && (
              <p className="imp-summary" data-testid="import-summary">
                {valid.length} {valid.length === 1 ? 'row is' : 'rows are'} ready
                {invalid.length > 0 ? `, ${invalid.length} ${invalid.length === 1 ? 'has a problem and will be skipped' : 'have problems and will be skipped'}` : ''}.
              </p>
            )}
            {invalid.length > 0 && phase !== 'done' && (
              <ul className="imp-errors" data-testid="import-errors">
                {invalid.map((r) => <li key={r.line}><b>Row {r.line}:</b> {r.errors.join(' ')}</li>)}
              </ul>
            )}
            {phase === 'done' && (
              <>
                <p className="imp-summary" data-testid="import-done">
                  {saved} {saved === 1 ? single : plainName(entity.label)} saved{failed.length + invalid.length > 0 ? `; ${failed.length + invalid.length} not saved` : ''}.
                </p>
                {failed.length > 0 && (
                  <ul className="imp-errors" data-testid="import-failed">
                    {failed.map((f) => <li key={f.line}><b>Row {f.line}:</b> {f.message}</li>)}
                  </ul>
                )}
              </>
            )}
          </div>
        )}

        <div className="imp-foot">
          <button type="button" className="ef-btn" onClick={close}>{phase === 'done' ? 'Close' : 'Cancel'}</button>
          {phase !== 'done' && (
            <button type="button" className="ef-btn ef-btn-primary" data-testid="import-run" disabled={valid.length === 0 || phase !== 'ready'} onClick={save}>
              {phase === 'saving' ? `Saving ${saved} of ${valid.length}…` : `Import ${valid.length > 0 ? `${valid.length} ` : ''}${noun}`}
            </button>
          )}
        </div>
      </div>
    </Modal>
  );
}
