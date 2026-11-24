import { useMemo, useState } from 'react';
import { Plus, Trash2 } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import apiClient from '../../../api/client';
import AmountInput from '../../../components/AmountInput';
import SearchableSelect from '../../../components/SearchableSelect';
import { useCurrency } from '../../../context/CurrencyContext';
import { useDimensions } from '../hooks/useJournal';
import { useMDAs } from '../hooks/useBudgetDimensions';
import {
    KINDS, blankLine, formProblems, lineTotal, payloadFor, specOf,
    type DraftDocument, type DraftLine, type TransactionType,
} from './cashPosting';
import { errorSentence, useSaveCashDocument, type CashDocument, type CashJournal } from './hooks/useCashPosting';
import ModalShell, { ErrorLine, Field } from './ModalShell';

interface Props {
    journals: CashJournal[];
    journal: CashJournal;
    /** An existing Draft to change; omit for a new document. */
    document?: CashDocument;
    /** Values to start a new document with (a replenishment, for one). */
    preset?: Partial<DraftDocument>;
    onClose: () => void;
    onSaved: (doc: CashDocument) => void;
}

type Coded = { id: number | string; code?: string; name?: string };

const todayISO = () => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
};

const options = (list: Coded[]) =>
    [...list]
        .sort((a, b) => (a.code ?? '').localeCompare(b.code ?? '', undefined, { numeric: true }))
        .map(x => ({ value: String(x.id), label: x.code ? `${x.code} - ${x.name ?? ''}` : (x.name ?? '') }));

function startingDraft(journal: CashJournal, doc?: CashDocument, preset?: Partial<DraftDocument>): DraftDocument {
    const id = (v: number | null | undefined) => (v ? String(v) : '');
    if (doc) {
        return {
            cash_journal: String(doc.cash_journal), posting_date: doc.posting_date, transaction_type: doc.transaction_type, amount: doc.lines.length ? '' : doc.amount,
            description: doc.description, reference: doc.reference, recipient: doc.recipient, offset_account: id(doc.offset_account),
            bank_account: id(doc.bank_account), mda: id(doc.mda), fund: id(doc.fund), function: id(doc.function), program: id(doc.program), geo: id(doc.geo),
        };
    }
    return {
        cash_journal: String(journal.id), posting_date: todayISO(), transaction_type: 'EXPENSE', amount: '', description: '', reference: '', recipient: '',
        offset_account: '', bank_account: '', mda: id(journal.mda), fund: '', function: '', program: '', geo: '', ...preset,
    };
}

function useBankAccounts() {
    return useQuery<{ id: number; account_name?: string; name?: string; account_number?: string }[]>({
        queryKey: ['cash-bank-accounts'],
        queryFn: async () => {
            const { data } = await apiClient.get('/accounting/bank-accounts/', { params: { page_size: 500, account_type: 'Bank' } });
            return Array.isArray(data) ? data : data?.results ?? [];
        },
        staleTime: 5 * 60 * 1000,
    });
}

/** Create a cash document, or change a Draft. Saving never posts: the cashier checks the entries first and posts from the list. */
export default function CashDocumentModal({ journals, journal, document, preset, onClose, onSaved }: Props) {
    const { formatCurrency } = useCurrency();
    const { data: dims } = useDimensions();
    const { data: mdas = [] } = useMDAs({ is_active: true });
    const { data: banks = [] } = useBankAccounts();
    const save = useSaveCashDocument();

    const [draft, setDraft] = useState<DraftDocument>(() => startingDraft(journal, document, preset));
    const [lines, setLines] = useState<DraftLine[]>(() => (document?.lines ?? []).map(l => ({ ...blankLine(), account: String(l.account), description: l.description, amount: l.amount })));
    const [problems, setProblems] = useState<ReturnType<typeof formProblems>>({});
    const [error, setError] = useState('');

    const spec = specOf(draft.transaction_type);
    const itemised = draft.transaction_type === 'EXPENSE' && lines.length > 0;
    const set = <K extends keyof DraftDocument>(key: K, value: DraftDocument[K]) => setDraft(d => ({ ...d, [key]: value }));
    const setLine = (key: string, patch: Partial<DraftLine>) => setLines(ls => ls.map(l => (l.key === key ? { ...l, ...patch } : l)));

    const postable = useMemo(() => ((dims?.accounts ?? []) as (Coded & { is_postable?: boolean; is_reconciliation?: boolean })[])
        .filter(a => a.is_postable !== false && !a.is_reconciliation), [dims?.accounts]);
    const accountOptions = useMemo(() => options(postable), [postable]);
    const bankOptions = useMemo(() => banks.map(b => ({ value: String(b.id), label: b.account_name || b.name || 'Bank account' })), [banks]);

    const submit = async () => {
        const found = formProblems(draft, lines);
        setProblems(found);
        if (Object.keys(found).length) { setError(Object.values(found)[0] ?? ''); return; }
        setError('');
        try {
            const saved = await save.mutateAsync({ id: document?.id, body: payloadFor(draft, lines) });
            onSaved(saved);
        } catch (err) {
            setError(errorSentence(err, 'The cash document could not be saved.'));
        }
    };

    const kindChange = (kind: TransactionType) => { set('transaction_type', kind); if (kind !== 'EXPENSE') setLines([]); };

    return (
        <ModalShell
            title={document ? `Change ${document.document_number}` : 'New cash document'}
            subtitle={`${journal.name}  ·  book balance ${formatCurrency(Number(journal.balance))}`}
            onClose={onClose}
            footer={<>
                <button type="button" className="cash-btn" onClick={onClose}>Cancel</button>
                <button type="button" className="cash-btn primary" onClick={submit} disabled={save.isPending} data-testid="cash-save">
                    {save.isPending ? 'Saving...' : 'Save as draft'}
                </button>
            </>}
        >
            <div className="cash-form-grid">
                {!document && journals.length > 1 && (
                    <Field label="Cash journal" error={problems.cash_journal}>
                        <select value={draft.cash_journal} onChange={e => set('cash_journal', e.target.value)}>
                            {journals.map(j => <option key={j.id} value={j.id}>{j.code} - {j.name}</option>)}
                        </select>
                    </Field>
                )}
                <Field label="Transaction" error={problems.transaction_type}>
                    <select value={draft.transaction_type} onChange={e => kindChange(e.target.value as TransactionType)} data-testid="cash-kind">
                        {KINDS.map(k => <option key={k.value} value={k.value}>{k.label}</option>)}
                    </select>
                </Field>
                <Field label="Posting date" error={problems.posting_date}>
                    <input type="date" value={draft.posting_date} onChange={e => set('posting_date', e.target.value)} data-testid="cash-date" />
                </Field>

                {!itemised && (
                    <Field label="Amount" error={problems.amount}>
                        <AmountInput value={draft.amount} onChange={v => set('amount', v)} aria-label="Amount" />
                    </Field>
                )}

                {spec.other === 'account' && !itemised && (
                    <Field label={spec.otherLabel} error={problems.offset_account} style={{ gridColumn: '1 / -1' }}>
                        <SearchableSelect options={accountOptions} value={draft.offset_account} onChange={v => set('offset_account', v)} placeholder="Search by code or name" />
                    </Field>
                )}
                {spec.other === 'bank' && (
                    <Field label={spec.otherLabel} error={problems.bank_account} style={{ gridColumn: '1 / -1' }}>
                        <SearchableSelect options={bankOptions} value={draft.bank_account} onChange={v => set('bank_account', v)} placeholder="Choose the bank account" />
                    </Field>
                )}

                <Field label={spec.isReceipt ? 'Received from' : 'Paid to'}>
                    <input value={draft.recipient} onChange={e => set('recipient', e.target.value)} placeholder="Name of the person" maxLength={150} />
                </Field>
                <Field label="Reference / voucher no.">
                    <input value={draft.reference} onChange={e => set('reference', e.target.value)} maxLength={100} />
                </Field>
                <Field label="Description" style={{ gridColumn: '1 / -1' }}>
                    <input value={draft.description} onChange={e => set('description', e.target.value)} maxLength={255} />
                </Field>
            </div>

            {draft.transaction_type === 'EXPENSE' && (
                <fieldset className="cash-lines">
                    <legend>Line items <small>(optional: split the payment across several accounts)</small></legend>
                    {lines.map((l, i) => (
                        <div className="cash-line" key={l.key}>
                            <SearchableSelect options={accountOptions} value={l.account} onChange={v => setLine(l.key, { account: v })} placeholder={`Account for line ${i + 1}`} />
                            <input value={l.description} onChange={e => setLine(l.key, { description: e.target.value })} placeholder="What for" maxLength={255} aria-label={`Line ${i + 1} description`} />
                            <AmountInput value={l.amount} onChange={v => setLine(l.key, { amount: v })} aria-label={`Line ${i + 1} amount`} />
                            <button type="button" className="cash-icon-btn" onClick={() => setLines(ls => ls.filter(x => x.key !== l.key))} aria-label={`Remove line ${i + 1}`}><Trash2 size={15} /></button>
                        </div>
                    ))}
                    {problems.lines && <small className="cash-field-error" role="alert">{problems.lines}</small>}
                    <div className="cash-lines-foot">
                        <button type="button" className="cash-btn" onClick={() => setLines(ls => [...ls, blankLine()])} data-testid="cash-add-line"><Plus size={14} /> Add a line</button>
                        {itemised && <strong>Total {formatCurrency(lineTotal(lines))}</strong>}
                    </div>
                </fieldset>
            )}

            <fieldset className="cash-coding">
                <legend>NCoA coding <small>(flows onto the journal and the budget check)</small></legend>
                <Field label="MDA" error={problems.mda}>
                    <SearchableSelect options={options(mdas as Coded[])} value={draft.mda} onChange={v => set('mda', v)} placeholder="Charged to MDA" />
                </Field>
                <Field label="Fund">
                    <SearchableSelect options={options((dims?.funds ?? []) as Coded[])} value={draft.fund} onChange={v => set('fund', v)} placeholder="Fund" />
                </Field>
                <Field label="Function">
                    <SearchableSelect options={options((dims?.functions ?? []) as Coded[])} value={draft.function} onChange={v => set('function', v)} placeholder="Function" />
                </Field>
                <Field label="Programme">
                    <SearchableSelect options={options((dims?.programs ?? []) as Coded[])} value={draft.program} onChange={v => set('program', v)} placeholder="Programme" />
                </Field>
                <Field label="Geo">
                    <SearchableSelect options={options((dims?.geos ?? []) as Coded[])} value={draft.geo} onChange={v => set('geo', v)} placeholder="Geographic" />
                </Field>
            </fieldset>
            <ErrorLine message={error} />
        </ModalShell>
    );
}
