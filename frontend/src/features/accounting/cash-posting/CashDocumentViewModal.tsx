import { Printer } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useCurrency } from '../../../context/CurrencyContext';
import { formatDate, formatDateTime } from '@/utils/date';
import { errorSentence, useCashDocumentHistory, type CashDocument, type HistoryEntry } from './hooks/useCashPosting';
import ModalShell, { ErrorLine } from './ModalShell';

interface Props {
    document: CashDocument;
    onClose: () => void;
}

function Entries({ entries, title }: { entries: HistoryEntry[]; title: string }) {
    const { formatCurrency } = useCurrency();
    const money = (v: string) => (Number(v) ? formatCurrency(Number(v)) : '');
    const debit = entries.reduce((s, e) => s + Number(e.debit), 0);
    const credit = entries.reduce((s, e) => s + Number(e.credit), 0);
    return (
        <div className="cash-entries">
            <h3>{title}</h3>
            <table>
                <thead><tr><th>Account</th><th>Memo</th><th className="r">Debit</th><th className="r">Credit</th></tr></thead>
                <tbody>
                    {entries.map((e, i) => (
                        <tr key={i}><td>{e.account_code} {e.account_name}</td><td>{e.memo}</td><td className="r">{money(e.debit)}</td><td className="r">{money(e.credit)}</td></tr>
                    ))}
                </tbody>
                <tfoot><tr><td colSpan={2}>Total</td><td className="r">{formatCurrency(debit)}</td><td className="r">{formatCurrency(credit)}</td></tr></tfoot>
            </table>
        </div>
    );
}

/** The View screen: who did what, and the accounting entries (the ones a Draft will post, or the journal a posted one made). */
export default function CashDocumentViewModal({ document, onClose }: Props) {
    const navigate = useNavigate();
    const { formatCurrency } = useCurrency();
    const { data, isLoading, error } = useCashDocumentHistory(document.id);

    return (
        <ModalShell
            title={`${document.document_number}  ·  ${document.status}`}
            subtitle={`${document.transaction_type_label}  ·  ${formatCurrency(Number(document.amount))}  ·  ${formatDate(document.posting_date)}`}
            onClose={onClose}
            width={820}
            footer={<>
                <button type="button" className="cash-btn" onClick={() => navigate(`/accounting/cash-posting/${document.id}/print`)}><Printer size={14} /> Print voucher</button>
                <button type="button" className="cash-btn primary" onClick={onClose}>Close</button>
            </>}
        >
            {isLoading && <p>Loading...</p>}
            {error ? <ErrorLine message={errorSentence(error, 'The history could not be loaded.')} /> : null}
            {data && (
                <>
                    <ul className="cash-events">
                        {data.events.map(ev => (
                            <li key={ev.event}><span>{ev.label}</span><strong>{ev.by || 'Unknown'}</strong><time>{ev.at ? formatDateTime(ev.at) : ''}</time></li>
                        ))}
                    </ul>
                    {data.note && <p className="cash-note">{data.note}</p>}
                    {data.entries.length > 0 && (
                        <Entries entries={data.entries} title={data.entries_are_projected ? 'Entries this document will post' : `Journal ${data.journal_number ?? ''}`} />
                    )}
                    {data.reversal_entries.length > 0 && <Entries entries={data.reversal_entries} title={`Reversal journal ${data.reversal_journal_number ?? ''}`} />}
                </>
            )}
        </ModalShell>
    );
}
