import { describe, expect, it } from 'vitest';
import { plainName, singularLabel } from '../labels';
import { describeRecord } from '../referenceRegistry';

describe('singularLabel', () => {
  it.each([
    ['Vehicle Assignments', 'Vehicle Assignment'],
    ['Call Circulars', 'Call Circular'],
    ['Hearing Diaries', 'Hearing Diary'],
    ['Staff Advances', 'Staff Advance'],
    ['Integration Messages', 'Integration Message'],
    ['Budget Calendar', 'Budget Calendar'],
    ['Case Addresses', 'Case Address'],
    ['Cash Plan Variances', 'Cash Plan Variance'],
  ])('%s -> %s', (plural, single) => {
    expect(singularLabel(plural)).toBe(single);
  });

  it('prefers an explicit singular', () => {
    expect(singularLabel('Evaluation Criteria', 'Evaluation Criterion')).toBe('Evaluation Criterion');
  });

  it('leaves words that merely end in s alone', () => {
    expect(singularLabel('Analysis')).toBe('Analysis');
    expect(singularLabel('Status')).toBe('Status');
  });
});

describe('plainName', () => {
  it('lowercases ordinary words but keeps acronyms', () => {
    expect(plainName('Vehicle Assignment')).toBe('vehicle assignment');
    expect(plainName('MTEF Year')).toBe('MTEF year');
    expect(plainName('IGR Billing Run')).toBe('IGR billing run');
    expect(plainName('Budget Calendar')).toBe('budget calendar');
  });
});

describe('describeRecord', () => {
  it('joins a code and a name', () => {
    expect(describeRecord({ id: 1, code: '1254s', name: 'Jacob PLC' })).toBe('1254s · Jacob PLC');
  });

  it('names a person from first and last name', () => {
    expect(describeRecord({ id: 3, first_name: 'Ada', last_name: 'Obi', employee_id: 'E-77' })).toBe('E-77 · Ada Obi');
  });

  it('uses a document number when there is no name', () => {
    expect(describeRecord({ id: 9, instrument_number: 'LN-2026-001' })).toBe('LN-2026-001');
  });

  it('does not repeat itself when code and name match', () => {
    expect(describeRecord({ id: 2, code: 'ABC', name: 'ABC' })).toBe('ABC');
  });

  it('falls back to the MDA and economic names of an appropriation', () => {
    expect(describeRecord({ id: 5, administrative_name: 'Works', economic_name: 'Salaries' })).toBe('Works · Salaries');
  });

  it('never returns an empty string for a real record', () => {
    expect(describeRecord({ id: 12 })).toBe('Record 12');
    expect(describeRecord(null)).toBe('');
  });
});
