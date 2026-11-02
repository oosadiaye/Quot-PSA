import { describe, it, expect } from 'vitest';
import { daysOverdue, agingLabel, matchesAging } from '../aging';

// Fixed "today" so the maths is deterministic regardless of when tests run.
// Use a mid-day local time to prove the date-only UTC normalisation ignores
// time-of-day (the off-by-one an aging report gets wrong).
const TODAY = new Date(2026, 8, 29, 14, 30, 0); // 29 Sep 2026, 14:30 local

describe('daysOverdue', () => {
    it('is 0 when the invoice is due today', () => {
        expect(daysOverdue('2026-09-29', TODAY)).toBe(0);
    });

    it('is positive (overdue) when the due date is in the past', () => {
        expect(daysOverdue('2026-09-17', TODAY)).toBe(12);
        expect(daysOverdue('2026-09-28', TODAY)).toBe(1);
    });

    it('is negative (days remaining) when the due date is in the future', () => {
        expect(daysOverdue('2026-10-04', TODAY)).toBe(-5);
        expect(daysOverdue('2026-09-30', TODAY)).toBe(-1);
    });

    it('ignores time-of-day (no off-by-one across midnight)', () => {
        const lateToday = new Date(2026, 8, 29, 23, 59, 59);
        const earlyToday = new Date(2026, 8, 29, 0, 0, 1);
        expect(daysOverdue('2026-09-29', lateToday)).toBe(0);
        expect(daysOverdue('2026-09-29', earlyToday)).toBe(0);
    });

    it('returns null for a missing or malformed due date', () => {
        expect(daysOverdue(null, TODAY)).toBeNull();
        expect(daysOverdue('', TODAY)).toBeNull();
        expect(daysOverdue('not-a-date', TODAY)).toBeNull();
    });
});

describe('agingLabel', () => {
    it('reads naturally for overdue, due-today and not-yet-due', () => {
        expect(agingLabel(12)).toBe('12 days overdue');
        expect(agingLabel(1)).toBe('1 day overdue');
        expect(agingLabel(0)).toBe('Due today');
        expect(agingLabel(-1)).toBe('Due in 1 day');
        expect(agingLabel(-5)).toBe('Due in 5 days');
    });
});

describe('matchesAging', () => {
    it("'all' matches everything, including settled rows (null)", () => {
        expect(matchesAging(null, 'all')).toBe(true);
        expect(matchesAging(42, 'all')).toBe(true);
        expect(matchesAging(-3, 'all')).toBe(true);
    });

    it('settled rows (null) match no specific bucket', () => {
        for (const f of ['notdue', 'due7', 'overdue', 'd1_30', 'd31_60', 'd61_90', 'd90p'] as const) {
            expect(matchesAging(null, f)).toBe(false);
        }
    });

    it('separates not-yet-due from overdue at the 0 boundary', () => {
        expect(matchesAging(-1, 'notdue')).toBe(true);
        expect(matchesAging(0, 'notdue')).toBe(false); // due today is not "not yet due"
        expect(matchesAging(0, 'overdue')).toBe(false); // nor overdue
        expect(matchesAging(1, 'overdue')).toBe(true);
    });

    it("'due ≤ 7 days' spans due-today through 7 days out, not overdue", () => {
        expect(matchesAging(0, 'due7')).toBe(true);
        expect(matchesAging(-7, 'due7')).toBe(true);
        expect(matchesAging(-8, 'due7')).toBe(false);
        expect(matchesAging(1, 'due7')).toBe(false);
    });

    it('overdue buckets are inclusive and contiguous', () => {
        expect(matchesAging(1, 'd1_30')).toBe(true);
        expect(matchesAging(30, 'd1_30')).toBe(true);
        expect(matchesAging(31, 'd1_30')).toBe(false);
        expect(matchesAging(31, 'd31_60')).toBe(true);
        expect(matchesAging(60, 'd31_60')).toBe(true);
        expect(matchesAging(61, 'd61_90')).toBe(true);
        expect(matchesAging(90, 'd61_90')).toBe(true);
        expect(matchesAging(91, 'd90p')).toBe(true);
        expect(matchesAging(90, 'd90p')).toBe(false);
    });
});
