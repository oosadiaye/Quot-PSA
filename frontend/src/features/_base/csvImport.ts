/**
 * Bulk import for a register: the template an officer fills in, and the reading of the file they hand back.
 *
 * The template is a CSV (it opens in Excel) with one column per field a person would fill, headed by the label the form
 * uses, and one example row. Reading is strict and says what is wrong in words, row by row, before anything is saved.
 * Dates are DD/MM/YYYY, as everywhere else in the app; a linked record is named by its code or name and looked up.
 */
import type { EntityConfig, EntityField } from './types';

/** The fields a person fills in: not server-managed, not files, not nested data. */
export function importableFields(entity: EntityConfig): EntityField[] {
  return entity.fields.filter((f) => !f.readOnly && !f.hideInForm && f.type !== 'object' && f.type !== 'file');
}

const norm = (s: string) => s.replace(/\*/g, '').replace(/\s+/g, ' ').trim().toLowerCase();

/** Parse CSV text: quoted cells, doubled quotes, commas and line breaks inside quotes, a leading byte-order mark. */
export function parseCsv(input: string): string[][] {
  const text = input.replace(/^﻿/, '');
  const rows: string[][] = [];
  let row: string[] = [];
  let cell = '';
  let quoted = false;
  for (let i = 0; i < text.length; i += 1) {
    const c = text[i];
    if (quoted) {
      if (c === '"' && text[i + 1] === '"') { cell += '"'; i += 1; }
      else if (c === '"') quoted = false;
      else cell += c;
    } else if (c === '"') quoted = true;
    else if (c === ',') { row.push(cell); cell = ''; }
    else if (c === '\n' || c === '\r') {
      if (c === '\r' && text[i + 1] === '\n') i += 1;
      row.push(cell); cell = '';
      rows.push(row); row = [];
    } else cell += c;
  }
  if (cell !== '' || row.length > 0) { row.push(cell); rows.push(row); }
  return rows;
}

const csvCell = (v: string) => (/[",\r\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v);

export function exampleValue(f: EntityField): string {
  if (f.importExample !== undefined) return f.importExample;
  if (f.type === 'select' && f.options) return Object.values(f.options)[0] ?? '';
  if (f.reference) return 'Code or name';
  switch (f.type) {
    case 'integer': return /year/i.test(f.name) ? '2027' : '1';
    case 'decimal': case 'number': return '1000000.00';
    case 'date': return '31/03/2027';
    case 'datetime': return '31/03/2027 09:00';
    case 'boolean': return 'Yes';
    default: return `Example ${f.label.toLowerCase()}`;
  }
}

/** The template: a header of field labels (a * marks a required one) and one example row to copy the shape from. */
export function templateCsv(entity: EntityConfig): string {
  const fields = importableFields(entity);
  const head = fields.map((f) => csvCell(f.required ? `${f.label} *` : f.label)).join(',');
  const example = fields.map((f) => csvCell(exampleValue(f))).join(',');
  return `﻿${head}\r\n${example}\r\n`;
}

const pad = (n: number) => String(n).padStart(2, '0');

/** DD/MM/YYYY or YYYY-MM-DD, and a real calendar day, to YYYY-MM-DD; null when it is neither. */
export function toIsoDate(text: string): string | null {
  const t = text.trim();
  let y: number; let m: number; let d: number;
  let match = /^(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})$/.exec(t);
  if (match) { d = Number(match[1]); m = Number(match[2]); y = Number(match[3]); }
  else if ((match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(t))) { y = Number(match[1]); m = Number(match[2]); d = Number(match[3]); }
  else return null;
  const real = new Date(Date.UTC(y, m - 1, d));
  if (real.getUTCFullYear() !== y || real.getUTCMonth() !== m - 1 || real.getUTCDate() !== d) return null;
  return `${y}-${pad(m)}-${pad(d)}`;
}

export type Converted = { value: unknown } | { skip: true } | { lookup: string } | { error: string };

/** One cell to the value the API takes. A linked record comes back as a lookup to be resolved against the server. */
export function convertCell(f: EntityField, raw: string): Converted {
  const text = raw.trim();
  if (text === '') return f.required ? { error: `${f.label} is required.` } : { skip: true };
  if (f.reference) return { lookup: text };
  switch (f.type) {
    case 'integer': {
      const n = text.replace(/[,\s]/g, '');
      return /^-?\d+$/.test(n) ? { value: Number(n) } : { error: `${f.label} must be a whole number, not “${text}”.` };
    }
    case 'decimal': case 'number': {
      const n = text.replace(/[,\s₦]/g, '');
      return /^-?\d+(\.\d+)?$/.test(n) ? { value: n } : { error: `${f.label} must be a number, not “${text}”.` };
    }
    case 'boolean': {
      const t = text.toLowerCase();
      if (['yes', 'y', 'true', '1'].includes(t)) return { value: true };
      if (['no', 'n', 'false', '0'].includes(t)) return { value: false };
      return { error: `${f.label} must be Yes or No, not “${text}”.` };
    }
    case 'select': {
      const t = text.toLowerCase();
      const hit = Object.entries(f.options ?? {}).find(([key, label]) => key.toLowerCase() === t || label.toLowerCase() === t);
      return hit ? { value: hit[0] } : { error: `${f.label} must be one of: ${Object.values(f.options ?? {}).join(', ')}.` };
    }
    case 'date': {
      const iso = toIsoDate(text);
      return iso ? { value: iso } : { error: `${f.label} must be a date as DD/MM/YYYY, not “${text}”.` };
    }
    case 'datetime': {
      const [day, time = '00:00'] = text.split(/\s+/);
      const iso = toIsoDate(day);
      return iso && /^\d{1,2}:\d{2}$/.test(time) ? { value: `${iso}T${time.padStart(5, '0')}` }
        : { error: `${f.label} must be a date and time as DD/MM/YYYY HH:MM, not “${text}”.` };
    }
    default: return { value: text };
  }
}

export interface PlannedRow {
  /** The row's line in the file, counting the header as line 1. */
  line: number;
  payload: Record<string, unknown>;
  lookups: Record<string, string>;
  errors: string[];
}

export interface ImportPlan {
  rows: PlannedRow[];
  /** Problems with the file as a whole: a required column missing, an unknown column, nothing to import. */
  fileErrors: string[];
  ignoredColumns: string[];
}

/** Read the file against the entity: match columns to fields, convert every cell, and note every problem. */
export function planImport(entity: EntityConfig, table: string[][]): ImportPlan {
  const fields = importableFields(entity);
  const [header = [], ...body] = table;
  const byHeader = new Map<string, EntityField>();
  fields.forEach((f) => { byHeader.set(norm(f.label), f); byHeader.set(norm(f.name), f); });
  const columns = header.map((h) => byHeader.get(norm(h)));
  const ignoredColumns = header.filter((h, i) => h.trim() !== '' && !columns[i]);
  const present = new Set(columns.filter(Boolean).map((f) => f!.name));
  const fileErrors = fields.filter((f) => f.required && !present.has(f.name)).map((f) => `The file has no “${f.label}” column.`);

  const example = fields.map((f) => exampleValue(f));
  const rows: PlannedRow[] = [];
  body.forEach((cells, i) => {
    if (cells.every((c) => c.trim() === '')) return;
    const isExample = header.length > 0 && columns.every((f, c) => !f || (cells[c] ?? '').trim() === example[fields.indexOf(f)]);
    if (isExample) return;
    const row: PlannedRow = { line: i + 2, payload: {}, lookups: {}, errors: [] };
    columns.forEach((f, c) => {
      if (!f) return;
      const out = convertCell(f, cells[c] ?? '');
      if ('error' in out) row.errors.push(out.error);
      else if ('lookup' in out) row.lookups[f.name] = out.lookup;
      else if ('value' in out) row.payload[f.name] = out.value;
    });
    rows.push(row);
  });
  if (fileErrors.length === 0 && rows.length === 0) fileErrors.push('The file has no rows to import. Fill in the template, below its example row.');
  return { rows, fileErrors, ignoredColumns };
}
