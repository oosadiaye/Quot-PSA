/**
 * Where to look up the record a reference field points at, and how to name a record for a person.
 *
 * Entities of the future modules resolve from their own configs (loaded on demand), so there is one source of truth for
 * their paths. Entities of the established modules use the endpoints the app already calls. A target that cannot be
 * resolved returns null and the form falls back to asking for the record's ID.
 */
import type { ModuleConfig } from './types';

/** Endpoints of the established modules, keyed `module.entity`. */
const CORE_PATHS: Record<string, string> = {
  'accounting.revenueHead': '/accounting/revenue-heads/',
  'accounting.fund': '/accounting/funds/',
  'accounting.account': '/accounting/accounts/',
  'accounting.currency': '/accounting/currencies/',
  'accounting.administrativeSegment': '/accounting/ncoa/administrative/',
  'accounting.administrativeSegments': '/accounting/ncoa/administrative/',
  'accounting.programmeSegment': '/accounting/ncoa/programme/',
  'accounting.fundSegment': '/accounting/ncoa/fund/',
  'accounting.mda': '/accounting/mdas/',
  'accounting.function': '/accounting/functions/',
  'accounting.program': '/accounting/programs/',
  'accounting.geo': '/accounting/geos/',
  'accounting.functionalSegment': '/accounting/ncoa/functional/',
  'accounting.reportSnapshot': '/accounting/snapshots/',
  'budget.warrant': '/budget/warrants/',
  'budget.appropriation': '/budget/appropriations/',
  'budget.appropriations': '/budget/appropriations/',
  'hrm.employee': '/hrm/employees/',
  'hrm.payrollRuns': '/hrm/payroll-runs/',
  'procurement.vendor': '/procurement/vendors/',
  'inventory.item': '/inventory/items/',
};

type ConfigLoader = () => Promise<{ moduleConfig: ModuleConfig }>;

const FUTURE_LOADERS: Record<string, ConfigLoader> = {
  budget_prep: () => import('../budget-prep/config'),
  cash_planning: () => import('../cash-planning/config'),
  catalogue: () => import('../catalogue/config'),
  debt: () => import('../debt/config'),
  disclosure: () => import('../disclosure/config'),
  egp: () => import('../egp/config'),
  fleet: () => import('../fleet/config'),
  integrations: () => import('../integrations/config'),
  internal_audit: () => import('../internal-audit/config'),
  legal: () => import('../legal/config'),
  personnel_budget: () => import('../personnel-budget/config'),
  results: () => import('../results/config'),
  revenue_admin: () => import('../revenue-admin/config'),
  staff_advances: () => import('../staff-advances/config'),
  transparency: () => import('../transparency/config'),
};

export interface ReferenceTarget {
  module: string;
  entity: string;
}

/** The list endpoint for a reference target, or null when it is not known. */
export async function resolveReferencePath(target: ReferenceTarget): Promise<string | null> {
  const core = CORE_PATHS[`${target.module}.${target.entity}`];
  if (core) return core;
  const load = FUTURE_LOADERS[target.module];
  if (!load) return null;
  const { moduleConfig } = await load();
  const entity = moduleConfig.entities.find((e) => e.key === target.entity);
  return entity ? `${moduleConfig.basePath}/${entity.plural}/` : null;
}

const NAME_KEYS = [
  'name', 'full_name', 'title', 'instrument_number', 'run_number', 'invoice_number', 'case_number', 'reference',
  'plate_number', 'registration_number', 'number', 'label', 'mda_name', 'description',
];
const CODE_KEYS = ['code', 'employee_id', 'staff_id', 'budget_code', 'economic_code'];

const text = (v: unknown) => (v === null || v === undefined ? '' : String(v).trim());

/** Every name a person might call a record by: its code, its name, and the combined label. Used to find a record from text. */
export function recordNames(row: Record<string, any>): string[] {
  const person = [text(row.first_name), text(row.last_name)].filter(Boolean).join(' ');
  return [describeRecord(row), person, ...CODE_KEYS.map((k) => text(row[k])), ...NAME_KEYS.map((k) => text(row[k]))]
    .filter(Boolean).map((v) => v.toLowerCase());
}

/** A short human name for a record: "code · name" when it has both, never a bare number if anything readable exists. */
export function describeRecord(row: Record<string, any> | null | undefined): string {
  if (!row) return '';
  const person = [text(row.first_name), text(row.last_name)].filter(Boolean).join(' ');
  const name = person || NAME_KEYS.map((k) => text(row[k])).find(Boolean) || '';
  const code = CODE_KEYS.map((k) => text(row[k])).find(Boolean) || '';
  if (name && code && name !== code) return `${code} · ${name}`;
  if (name || code) return name || code;
  const mda = [text(row.administrative_name), text(row.economic_name)].filter(Boolean).join(' · ');
  return mda || `Record ${row.id ?? ''}`.trim();
}
