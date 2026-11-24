import { describe, expect, it } from 'vitest';
import { handoffError } from '../useBudgetHandoff';

const fail = (data: unknown) => ({ response: { data } });

describe('handoffError', () => {
  it('names the lines the server could not hand over, and what each lacks', () => {
    const msg = handoffError(fail({
      error: '2 submission line(s) cannot be handed off; fix them in Budget Preparation.',
      lines: [{ line: 4, missing: ['fund', 'programme'] }, { line: 9, conflict: 'functional/programme differ' }],
    }));
    expect(msg).toContain('cannot be handed off');
    expect(msg).toContain('line 4 has no fund, programme');
    expect(msg).toContain('line 9: functional/programme differ');
  });

  it('uses the plain error when there are no lines', () => {
    expect(handoffError(fail({ error: 'Only an incorporated submission can be handed off.' })))
      .toBe('Only an incorporated submission can be handed off.');
  });

  it('shows a module-disabled detail as sent', () => {
    expect(handoffError(fail({ detail: 'The "budget_prep" module is not enabled.' }))).toContain('not enabled');
  });

  it('falls back when the response carries nothing readable', () => {
    expect(handoffError(new Error('Network Error'))).toBe('That did not work. Please try again.');
    expect(handoffError(fail({}), 'custom')).toBe('custom');
  });
});
