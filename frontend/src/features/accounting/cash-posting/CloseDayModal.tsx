import { useState } from 'react';
import AmountInput from '../../../components/AmountInput';
import { useCurrency } from '../../../context/CurrencyContext';
import { formatDate } from '@/utils/date';
import { countDifference } from './cashPosting';
import { errorSentence, useCloseCashJournal, type CashBook, type CashJournal } from './hooks/useCashPosting';
import ModalShell, { ErrorLine, Field } from './ModalShell';

interface Props {
    journal: CashJournal;
    book: CashBook | undefined;
    onClose: () => void;
    onDone: () => void;
}

const todayISO = () => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
};

/** The day-end count: the cashier counts the notes and coins, the count is compared with the book, a difference is posted, the day closes. */
export default function CloseDayModal({ journal, book, onClose, onDone }: Props) {
    const { formatCurrency } = useCurrency();
    const close = useCloseCashJournal();
    const [date, setDate] = useState(todayISO());
    const [counted, setCounted] = useState('');
    const [note, setNote] = useState('');
    const [error, setError] = useState('');
    const bookBalance = book?.current_balance ?? journal.balance;
    const result = counted ? countDifference(counted, bookBalance) : null;

    const submit = async () => {
        if (!counted) { setError('Enter the cash you counted.'); return; }
        try {
            await close.mutateAsync({ id: journal.id, closing_date: date, counted_amount: counted, note });
            onDone();
        } catch (err) {
            setError(errorSentence(err, 'The day could not be closed.'));
        }
    };

    return (
        <ModalShell
            title={`Close the day: ${journal.name}`}
            subtitle={journal.last_closed_date ? `Last closed ${formatDate(journal.last_closed_date)}` : 'Never closed'}
            onClose={onClose} width={520}
            footer={<>
                <button type="button" className="cash-btn" onClick={onClose}>Cancel</button>
                <button type="button" className="cash-btn primary" onClick={submit} disabled={close.isPending} data-testid="cash-close-confirm">
                    {close.isPending ? 'Closing...' : 'Post count and close'}
                </button>
            </>}
        >
            <div className="cash-form-grid">
                <Field label="Closing date"><input type="date" value={date} max={todayISO()} onChange={e => setDate(e.target.value)} /></Field>
                <Field label="Book balance"><input value={formatCurrency(Number(bookBalance))} readOnly /></Field>
                <Field label="Cash counted" style={{ gridColumn: '1 / -1' }}>
                    <AmountInput value={counted} onChange={setCounted} aria-label="Cash counted" autoFocus />
                </Field>
                {result && (
                    <p className={`cash-count ${result.difference === 0 ? 'ok' : 'off'}`} data-testid="cash-count-result" style={{ gridColumn: '1 / -1' }}>{result.label}</p>
                )}
                <Field label="Note" style={{ gridColumn: '1 / -1' }}><input value={note} onChange={e => setNote(e.target.value)} maxLength={255} /></Field>
            </div>
            {result && result.difference !== 0 && !journal.difference_account && (
                <p className="cash-note">A difference needs a cash difference account. Set one in the journal settings first, or recount.</p>
            )}
            <p className="cash-note">Closing locks the day: nothing dated on or before it can be posted or reversed afterwards. Post or delete any drafts first.</p>
            <ErrorLine message={error} />
        </ModalShell>
    );
}
