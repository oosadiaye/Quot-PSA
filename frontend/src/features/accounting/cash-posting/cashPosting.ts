/**
 * Cash Posting (the FBCJ equivalent): the rules of the cash document form, kept out of the components so they can be tested.
 * The server enforces all of them again when the document is saved and posted; these only tell the cashier early.
 */

export type TransactionType = 'EXPENSE' | 'REVENUE' | 'BANK_WITHDRAWAL' | 'BANK_DEPOSIT';

export interface KindSpec {
    value: TransactionType;
    label: string;
    /** Brings cash in (a receipt) rather than taking it out. */
    isReceipt: boolean;
    /** The other side of the entry: a GL account, or a bank account. */
    other: 'account' | 'bank';
    /** What the other side is called on the form. */
    otherLabel: string;
}

export const KINDS: readonly KindSpec[] = [
    { value: 'EXPENSE', label: 'Cash payment - expense', isReceipt: false, other: 'account', otherLabel: 'Expense GL account' },
    { value: 'REVENUE', label: 'Cash receipt - revenue', isReceipt: true, other: 'account', otherLabel: 'Revenue GL account' },
    { value: 'BANK_WITHDRAWAL', label: 'Cash withdrawal from bank', isReceipt: true, other: 'bank', otherLabel: 'Bank account' },
    { value: 'BANK_DEPOSIT', label: 'Cash deposit to bank', isReceipt: false, other: 'bank', otherLabel: 'Bank account' },
];

export const specOf = (kind: string): KindSpec => KINDS.find(k => k.value === kind) ?? KINDS[0];

export interface DraftLine {
    key: string;
    account: string;
    description: string;
    amount: string;
}

export interface DraftDocument {
    cash_journal: string;
    posting_date: string;
    transaction_type: TransactionType;
    amount: string;
    description: string;
    reference: string;
    recipient: string;
    offset_account: string;
    bank_account: string;
    mda: string;
    fund: string;
    function: string;
    program: string;
    geo: string;
}

let lineCounter = 0;
export const blankLine = (): DraftLine => ({ key: `line-${++lineCounter}`, account: '', description: '', amount: '' });

/** Money in whole kobo, so a column of 0.10 + 0.20 adds to exactly 0.30. */
const toKobo = (value: string): number => {
    const n = Number(String(value).replace(/,/g, ''));
    return Number.isFinite(n) ? Math.round(n * 100) : 0;
};

export const lineTotal = (lines: readonly DraftLine[]): number => lines.reduce((sum, l) => sum + toKobo(l.amount), 0) / 100;

/** Lines that carry anything at all; an untouched blank row is ignored. */
export const usedLines = (lines: readonly DraftLine[]): DraftLine[] => lines.filter(l => l.account || l.amount || l.description);

export type FormProblems = Partial<Record<keyof DraftDocument | 'lines', string>>;

/** Everything the cashier can be told before saving. An empty object means the form is ready. */
export function formProblems(draft: DraftDocument, lines: readonly DraftLine[]): FormProblems {
    const problems: FormProblems = {};
    const spec = specOf(draft.transaction_type);
    const items = usedLines(lines);
    const itemised = draft.transaction_type === 'EXPENSE' && items.length > 0;

    if (!draft.cash_journal) problems.cash_journal = 'Choose the cash journal.';
    if (!draft.posting_date) problems.posting_date = 'Enter the posting date.';

    if (itemised) {
        const bad = items.findIndex(l => !l.account || toKobo(l.amount) <= 0);
        if (bad >= 0) problems.lines = `Line ${bad + 1}: choose the account and enter an amount above zero.`;
    } else {
        if (toKobo(draft.amount) <= 0) problems.amount = 'Enter an amount above zero.';
        if (spec.other === 'account' && !draft.offset_account) problems.offset_account = `Choose the ${spec.otherLabel.toLowerCase()}.`;
    }
    if (spec.other === 'bank' && !draft.bank_account) problems.bank_account = 'Choose the bank account.';
    if (!draft.mda) problems.mda = 'Choose the MDA this document is charged to.';
    return problems;
}

/** The body the API takes: numbers where it wants ids, nothing for what this kind of document does not use. */
export function payloadFor(draft: DraftDocument, lines: readonly DraftLine[]): Record<string, unknown> {
    const spec = specOf(draft.transaction_type);
    const items = usedLines(lines);
    const itemised = draft.transaction_type === 'EXPENSE' && items.length > 0;
    const id = (value: string) => (value ? Number(value) : null);
    const body: Record<string, unknown> = {
        cash_journal: Number(draft.cash_journal),
        posting_date: draft.posting_date,
        transaction_type: draft.transaction_type,
        description: draft.description.trim(),
        reference: draft.reference.trim(),
        recipient: draft.recipient.trim(),
        offset_account: spec.other === 'account' && !itemised ? id(draft.offset_account) : null,
        bank_account: spec.other === 'bank' ? id(draft.bank_account) : null,
        mda: id(draft.mda), fund: id(draft.fund), function: id(draft.function), program: id(draft.program), geo: id(draft.geo),
    };
    if (itemised) {
        body.lines = items.map(l => ({ account: Number(l.account), description: l.description.trim(), amount: (toKobo(l.amount) / 100).toFixed(2) }));
    } else {
        body.amount = (toKobo(draft.amount) / 100).toFixed(2);
        if (draft.transaction_type === 'EXPENSE') body.lines = [];
    }
    return body;
}

/** The day-end count against the book: positive is cash over, negative is cash short. */
export function countDifference(counted: string, book: string | number): { difference: number; label: string } {
    const difference = (toKobo(counted) - toKobo(String(book))) / 100;
    if (difference === 0) return { difference, label: 'The count agrees with the book.' };
    const amount = Math.abs(difference).toLocaleString('en-NG', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    return { difference, label: difference < 0 ? `Cash short by ${amount}` : `Cash over by ${amount}` };
}

export interface Reachable {
    status: string;
    posting_date: string;
}

/** What the cashier may do with a document; the server decides again, this only hides buttons that cannot work. */
export function actionsFor(doc: Reachable, lastClosed: string | null) {
    const closed = !!lastClosed && doc.posting_date <= lastClosed;
    return {
        canEdit: doc.status === 'Draft',
        canDelete: doc.status === 'Draft',
        canPost: doc.status === 'Draft' && !closed,
        canReverse: doc.status === 'Posted' && !closed,
    };
}
