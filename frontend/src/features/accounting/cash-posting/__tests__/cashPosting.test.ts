import { describe, expect, it } from 'vitest';
import {
    actionsFor, blankLine, countDifference, formProblems, lineTotal, payloadFor, specOf, usedLines,
    type DraftDocument,
} from '../cashPosting';

const draft = (over: Partial<DraftDocument> = {}): DraftDocument => ({
    cash_journal: '1', posting_date: '2026-10-29', transaction_type: 'REVENUE', amount: '100', description: '', reference: '',
    recipient: '', offset_account: '5', bank_account: '', mda: '2', fund: '', function: '', program: '', geo: '', ...over,
});
const line = (account: string, amount: string, description = '') => ({ ...blankLine(), account, amount, description });

describe('lineTotal', () => {
    it('adds money exactly, with no floating-point drift', () => {
        expect(lineTotal([line('1', '0.10'), line('1', '0.20')])).toBe(0.3);
        expect(lineTotal([line('1', '1,250.50'), line('1', '749.50')])).toBe(2000);
    });

    it('treats a blank or unreadable amount as nothing', () => {
        expect(lineTotal([line('1', ''), line('1', 'abc')])).toBe(0);
    });
});

describe('formProblems', () => {
    it('accepts a complete receipt', () => {
        expect(formProblems(draft(), [])).toEqual({});
    });

    it('asks for the journal, the date, the amount, the account and the MDA', () => {
        const problems = formProblems(draft({ cash_journal: '', posting_date: '', amount: '', offset_account: '', mda: '' }), []);
        expect(Object.keys(problems).sort()).toEqual(['amount', 'cash_journal', 'mda', 'offset_account', 'posting_date']);
    });

    it('wants a bank account, not a GL account, for a transfer with the bank', () => {
        const problems = formProblems(draft({ transaction_type: 'BANK_WITHDRAWAL', offset_account: '' }), []);
        expect(problems.bank_account).toBeTruthy();
        expect(problems.offset_account).toBeUndefined();
        expect(formProblems(draft({ transaction_type: 'BANK_DEPOSIT', offset_account: '', bank_account: '9' }), [])).toEqual({});
    });

    it('does not ask for an amount or a single account once an expense has line items', () => {
        const problems = formProblems(draft({ transaction_type: 'EXPENSE', amount: '', offset_account: '' }), [line('3', '40'), line('4', '60')]);
        expect(problems).toEqual({});
    });

    it('names the first line that is missing its account or amount', () => {
        const problems = formProblems(draft({ transaction_type: 'EXPENSE' }), [line('3', '40'), line('', '60')]);
        expect(problems.lines).toMatch(/Line 2/);
        expect(formProblems(draft({ transaction_type: 'EXPENSE' }), [line('3', '0')]).lines).toMatch(/Line 1/);
    });

    it('ignores an untouched blank line', () => {
        expect(usedLines([blankLine(), line('3', '10')])).toHaveLength(1);
        expect(formProblems(draft({ transaction_type: 'EXPENSE', offset_account: '' }), [blankLine()]).offset_account).toBeTruthy();
    });
});

describe('payloadFor', () => {
    it('sends numeric ids, a two-decimal amount and nothing for the side the kind does not use', () => {
        const body = payloadFor(draft({ amount: '1,250.5', bank_account: '9', fund: '7' }), []);
        expect(body).toMatchObject({ cash_journal: 1, amount: '1250.50', offset_account: 5, bank_account: null, mda: 2, fund: 7, function: null });
    });

    it('sends line items for an itemised expense and leaves the single account and amount out', () => {
        const body = payloadFor(draft({ transaction_type: 'EXPENSE' }), [line('3', '40', ' pens '), line('4', '60.5')]);
        expect(body.lines).toEqual([{ account: 3, description: 'pens', amount: '40.00' }, { account: 4, description: '', amount: '60.50' }]);
        expect(body.offset_account).toBeNull();
        expect('amount' in body).toBe(false);
    });

    it('clears old line items when an expense is saved without any', () => {
        expect(payloadFor(draft({ transaction_type: 'EXPENSE' }), []).lines).toEqual([]);
    });

    it('sends the bank account for a transfer and no GL account', () => {
        expect(payloadFor(draft({ transaction_type: 'BANK_DEPOSIT', bank_account: '9' }), [])).toMatchObject({ bank_account: 9, offset_account: null });
    });
});

describe('countDifference', () => {
    it('says when the count agrees', () => {
        expect(countDifference('1000', '1000.00')).toEqual({ difference: 0, label: 'The count agrees with the book.' });
    });

    it('says short or over, by how much', () => {
        expect(countDifference('970', '1000.00')).toMatchObject({ difference: -30 });
        expect(countDifference('970', '1000.00').label).toBe('Cash short by 30.00');
        expect(countDifference('1012.5', '1000.00').label).toBe('Cash over by 12.50');
    });
});

describe('actionsFor', () => {
    it('lets a Draft be edited, deleted and posted', () => {
        expect(actionsFor({ status: 'Draft', posting_date: '2026-10-29' }, null)).toEqual({ canEdit: true, canDelete: true, canPost: true, canReverse: false });
    });

    it('lets a Posted document be reversed and nothing else', () => {
        expect(actionsFor({ status: 'Posted', posting_date: '2026-10-29' }, null)).toEqual({ canEdit: false, canDelete: false, canPost: false, canReverse: true });
        expect(actionsFor({ status: 'Reversed', posting_date: '2026-10-29' }, null)).toEqual({ canEdit: false, canDelete: false, canPost: false, canReverse: false });
    });

    it('hides posting and reversing on or before the closed day', () => {
        expect(actionsFor({ status: 'Draft', posting_date: '2026-10-28' }, '2026-10-28').canPost).toBe(false);
        expect(actionsFor({ status: 'Posted', posting_date: '2026-10-28' }, '2026-10-28').canReverse).toBe(false);
        expect(actionsFor({ status: 'Posted', posting_date: '2026-10-29' }, '2026-10-28').canReverse).toBe(true);
    });
});

describe('specOf', () => {
    it('knows which kinds bring cash in', () => {
        expect(['EXPENSE', 'REVENUE', 'BANK_WITHDRAWAL', 'BANK_DEPOSIT'].map(k => specOf(k).isReceipt)).toEqual([false, true, true, false]);
    });
});
