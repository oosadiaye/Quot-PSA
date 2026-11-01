/**
 * How the three-year table is laid out: which rows, in which order, under which heading. The wording follows a Fiscal
 * Strategy Paper's macro-fiscal framework, so an officer reads it the way they would read the printed one.
 */
import type { PolicyValues, RuleStatus, YearView } from './useMtef';

export interface MoneyRow {
  key: string;
  label: string;
  note?: string;
}

export const REVENUE_ROWS: MoneyRow[] = [
  { key: 'rev_statutory', label: 'Statutory allocation (FAAC)' },
  { key: 'rev_vat', label: 'VAT allocation' },
  { key: 'rev_igr', label: 'Internally generated revenue' },
  { key: 'rev_other', label: 'Other recurrent revenue' },
  { key: 'rev_grants', label: 'Grants and aid' },
  { key: 'rev_capital_receipts', label: 'Capital receipts' },
];

export const EXPENDITURE_ROWS: MoneyRow[] = [
  { key: 'exp_debt_service', label: 'Debt service', note: 'first charge on revenue' },
  { key: 'exp_personnel', label: 'Personnel cost' },
  { key: 'exp_overhead', label: 'Overheads' },
  { key: 'exp_other_recurrent', label: 'Other recurrent' },
  { key: 'exp_capital', label: 'Capital expenditure' },
];

export const FINANCING_ROWS: MoneyRow[] = [
  { key: 'fin_domestic', label: 'Domestic borrowing' },
  { key: 'fin_external', label: 'External borrowing' },
  { key: 'fin_other', label: 'Other financing', note: 'balances brought forward and similar' },
];

export interface RatioRow {
  key: keyof NonNullable<YearView['ratios']>;
  label: string;
  /** The policy field that bounds it, and whether that bound is a ceiling or a floor. */
  limit: keyof PolicyValues;
  bound: 'max' | 'min';
}

export const RATIO_ROWS: RatioRow[] = [
  { key: 'debt_service_pct_revenue', label: 'Debt service, % of revenue', limit: 'max_debt_service_pct', bound: 'max' },
  { key: 'personnel_pct_recurrent_revenue', label: 'Personnel cost, % of recurrent revenue', limit: 'max_personnel_pct', bound: 'max' },
  { key: 'capital_pct_expenditure', label: 'Capital, % of expenditure', limit: 'min_capital_pct', bound: 'min' },
  { key: 'borrowing_pct_revenue', label: 'New borrowing, % of revenue', limit: 'max_borrowing_pct', bound: 'max' },
];

export const STATUS_WORD: Record<RuleStatus, string> = { pass: 'Met', warn: 'Check', fail: 'Broken' };
export const STATUS_MARK: Record<RuleStatus, string> = { pass: '✓', warn: '!', fail: '✕' };

export const MTEF_STATUS_LABEL: Record<string, string> = { draft: 'Draft', reviewed: 'Reviewed', approved: 'Approved' };

export const CEILING_LABEL: Record<string, string> = { personnel: 'Personnel', overhead: 'Overheads', capital: 'Capital' };

export const ruleSlug = (rule: string) => rule.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');

export const POLICY_FIELDS: { key: keyof PolicyValues; label: string; hint: string }[] = [
  { key: 'max_debt_service_pct', label: 'Debt service limit (%)', hint: 'Of total revenue. Breaking it blocks approval.' },
  { key: 'max_personnel_pct', label: 'Personnel cost limit (%)', hint: 'Of recurrent revenue.' },
  { key: 'min_capital_pct', label: 'Capital spending floor (%)', hint: 'Of total expenditure.' },
  { key: 'max_borrowing_pct', label: 'New borrowing limit (%)', hint: 'Of total revenue.' },
  { key: 'max_revenue_growth_pct', label: 'Revenue growth above inflation (points)', hint: 'How far year-on-year growth may beat inflation.' },
  { key: 'max_outturn_jump_pct', label: 'Rise on last year’s actuals (points)', hint: 'How far the budget year may exceed what was actually spent, above inflation.' },
];
