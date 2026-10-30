import { useMemo, useState } from 'react';
import AmountInput from '../../../components/AmountInput';
import SearchableSelect from '../../../components/SearchableSelect';
import { useDimensions } from '../hooks/useJournal';
import { useMDAs } from '../hooks/useBudgetDimensions';
import { errorSentence, useSaveJournalSettings, type CashJournal } from './hooks/useCashPosting';
import ModalShell, { ErrorLine, Field } from './ModalShell';

interface Props {
    journal: CashJournal;
    onClose: () => void;
}

type Coded = { id: number | string; code?: string; name?: string };

/** What belongs to the desk itself: its MDA, the imprest float, where a counting difference is posted, and whether it may go negative. */
export default function JournalSettingsModal({ journal, onClose }: Props) {
    const save = useSaveJournalSettings();
    const { data: dims } = useDimensions();
    const { data: mdas = [] } = useMDAs({ is_active: true });
    const [mda, setMda] = useState(journal.mda ? String(journal.mda) : '');
    const [float, setFloat] = useState(journal.float_amount);
    const [difference, setDifference] = useState(journal.difference_account ? String(journal.difference_account) : '');
    const [negative, setNegative] = useState(journal.allow_negative_balance);
    const [limit, setLimit] = useState(journal.overdraft_limit);
    const [error, setError] = useState('');

    const opts = (list: Coded[]) => [...list].sort((a, b) => (a.code ?? '').localeCompare(b.code ?? '', undefined, { numeric: true }))
        .map(x => ({ value: String(x.id), label: x.code ? `${x.code} - ${x.name ?? ''}` : (x.name ?? '') }));
    const accounts = useMemo(() => opts(((dims?.accounts ?? []) as (Coded & { is_postable?: boolean })[]).filter(a => a.is_postable !== false)), [dims?.accounts]);

    const submit = async () => {
        try {
            await save.mutateAsync({ id: journal.id, body: {
                mda: mda ? Number(mda) : null, float_amount: float || '0', difference_account: difference ? Number(difference) : null,
                allow_negative_balance: negative, overdraft_limit: negative ? limit || '0' : '0',
            } });
            onClose();
        } catch (err) {
            setError(errorSentence(err, 'The settings could not be saved.'));
        }
    };

    return (
        <ModalShell title={`Settings: ${journal.name}`} subtitle={`${journal.code}  ·  ${journal.cash_account_name}`} onClose={onClose} width={560}
            footer={<>
                <button type="button" className="cash-btn" onClick={onClose}>Cancel</button>
                <button type="button" className="cash-btn primary" onClick={submit} disabled={save.isPending}>Save settings</button>
            </>}>
            <div className="cash-form-grid">
                <Field label="MDA that owns this desk" style={{ gridColumn: '1 / -1' }}>
                    <SearchableSelect options={opts(mdas as Coded[])} value={mda} onChange={setMda} placeholder="MDA" />
                </Field>
                <Field label="Imprest float (0 for an ordinary desk)"><AmountInput value={float} onChange={setFloat} aria-label="Imprest float" /></Field>
                <Field label="Cash difference account">
                    <SearchableSelect options={accounts} value={difference} onChange={setDifference} placeholder="Where short / over is posted" />
                </Field>
                <label className="cash-check" style={{ gridColumn: '1 / -1' }}>
                    <input type="checkbox" checked={negative} onChange={e => setNegative(e.target.checked)} />
                    Allow the book to go below zero
                </label>
                {negative && (
                    <Field label="Limit below zero (0 for no limit)" style={{ gridColumn: '1 / -1' }}>
                        <AmountInput value={limit} onChange={setLimit} aria-label="Overdraft limit" />
                    </Field>
                )}
            </div>
            <ErrorLine message={error} />
        </ModalShell>
    );
}
