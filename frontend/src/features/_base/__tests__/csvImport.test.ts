import { describe, expect, it } from 'vitest';
import { convertCell, importableFields, parseCsv, planImport, templateCsv, toIsoDate } from '../csvImport';
import type { EntityConfig } from '../types';

const entity: EntityConfig = {
  key: 'thing', plural: 'things', label: 'Things', searchField: 'name', columns: [],
  fields: [
    { name: 'fiscal_year', label: 'Fiscal Year', type: 'integer', required: true },
    { name: 'mda_name', label: 'MDA Name', type: 'text', required: true, importExample: 'Ministry of Works' },
    { name: 'amount', label: 'Amount', type: 'decimal' },
    { name: 'kind', label: 'Kind', type: 'select', options: { original: 'Original budget', supplementary: 'Supplementary budget' } },
    { name: 'due', label: 'Due', type: 'date' },
    { name: 'active', label: 'Active', type: 'boolean' },
    { name: 'account', label: 'Account', type: 'integer', reference: { module: 'accounting', entity: 'account' } },
    { name: 'total', label: 'Total', type: 'decimal', readOnly: true },
    { name: 'doc', label: 'Document', type: 'file' },
  ],
};

describe('parseCsv', () => {
  it('reads quoted cells with commas, doubled quotes and line breaks', () => {
    expect(parseCsv('a,"b,c","say ""hi"""\r\n"x\ny",2,\r\n')).toEqual([['a', 'b,c', 'say "hi"'], ['x\ny', '2', '']]);
  });
  it('drops a byte-order mark and accepts bare line feeds and no final newline', () => {
    expect(parseCsv('\uFEFFa,b\nc,d')).toEqual([['a', 'b'], ['c', 'd']]);
  });
});

describe('the template', () => {
  it('has the fillable fields only, required ones starred, and an example row', () => {
    expect(importableFields(entity).map((f) => f.name)).toEqual(['fiscal_year', 'mda_name', 'amount', 'kind', 'due', 'active', 'account']);
    const [head, example] = parseCsv(templateCsv(entity));
    expect(head).toEqual(['Fiscal Year *', 'MDA Name *', 'Amount', 'Kind', 'Due', 'Active', 'Account']);
    expect(example).toEqual(['2027', 'Ministry of Works', '1000000.00', 'Original budget', '31/03/2027', 'Yes', 'Code or name']);
  });
});

describe('toIsoDate', () => {
  it.each([['31/03/2027', '2027-03-31'], ['1/2/2027', '2027-02-01'], ['2027-03-31', '2027-03-31']])('%s', (a, b) => expect(toIsoDate(a)).toBe(b));
  it.each(['31/02/2027', '2027/03/31', 'soon', '13/13/2027'])('rejects %s', (a) => expect(toIsoDate(a)).toBeNull());
});

describe('convertCell', () => {
  const f = (name: string) => entity.fields.find((x) => x.name === name)!;
  it('strips thousands separators and the naira sign from amounts', () => {
    expect(convertCell(f('amount'), '₦1,250,000.50')).toEqual({ value: '1250000.50' });
  });
  it('reads a select by its label or its stored value, in any case', () => {
    expect(convertCell(f('kind'), 'supplementary budget')).toEqual({ value: 'supplementary' });
    expect(convertCell(f('kind'), 'original')).toEqual({ value: 'original' });
  });
  it('names the allowed choices when a select is wrong', () => {
    expect(convertCell(f('kind'), 'other')).toEqual({ error: 'Kind must be one of: Original budget, Supplementary budget.' });
  });
  it('requires a required value and skips an optional blank one', () => {
    expect(convertCell(f('fiscal_year'), ' ')).toEqual({ error: 'Fiscal Year is required.' });
    expect(convertCell(f('amount'), '')).toEqual({ skip: true });
  });
  it('turns a date to ISO and Yes/No to a boolean', () => {
    expect(convertCell(f('due'), '31/03/2027')).toEqual({ value: '2027-03-31' });
    expect(convertCell(f('active'), 'no')).toEqual({ value: false });
  });
  it('hands a linked record back as a lookup', () => {
    expect(convertCell(f('account'), '21010101')).toEqual({ lookup: '21010101' });
  });
});

describe('planImport', () => {
  const file = (rows: string[]) => parseCsv(['Fiscal Year *,MDA Name *,Amount,Kind', ...rows].join('\n'));

  it('plans good rows, reports bad ones by line, and ignores the untouched example and blank rows', () => {
    const plan = planImport(entity, file(['2027,Ministry of Works,,', '2028,Health,"1,000",Supplementary budget', '2029,,x,nope', ',,,', '2027,Ministry of Works,1000000.00,Original budget']));
    expect(plan.fileErrors).toEqual([]);
    expect(plan.rows.map((r) => r.line)).toEqual([2, 3, 4]);
    expect(plan.rows[1].payload).toEqual({ fiscal_year: 2028, mda_name: 'Health', amount: '1000', kind: 'supplementary' });
    expect(plan.rows[2].errors).toEqual(['MDA Name is required.', 'Amount must be a number, not “x”.', 'Kind must be one of: Original budget, Supplementary budget.']);
  });

  it('says so when a required column is missing, and when there is nothing to import', () => {
    expect(planImport(entity, parseCsv('MDA Name\nHealth')).fileErrors).toEqual(['The file has no “Fiscal Year” column.']);
    expect(planImport(entity, file([])).fileErrors).toEqual(['The file has no rows to import. Fill in the template, below its example row.']);
  });

  it('matches columns by field name too, and reports columns it does not know', () => {
    const plan = planImport(entity, parseCsv('fiscal_year,mda_name,Colour\n2030,Works,red'));
    expect(plan.rows[0].payload).toEqual({ fiscal_year: 2030, mda_name: 'Works' });
    expect(plan.ignoredColumns).toEqual(['Colour']);
  });

  it('collects a linked record as a lookup to resolve', () => {
    const plan = planImport(entity, parseCsv('Fiscal Year,MDA Name,Account\n2030,Works,21010101'));
    expect(plan.rows[0].lookups).toEqual({ account: '21010101' });
  });
});
