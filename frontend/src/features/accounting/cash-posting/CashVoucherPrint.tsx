import DocumentPrintLayout from '../../../components/print/DocumentPrintLayout';
import { useCurrency } from '../../../context/CurrencyContext';
import { formatDate } from '@/utils/date';
import { useCashDocumentHistory, type CashDocument } from './hooks/useCashPosting';
import { usePrintRecord } from '../../procurement/print/usePrintRecord';

/** The cash voucher: a receipt or payment voucher on council letterhead. Route: /accounting/cash-posting/:id/print */
export default function CashVoucherPrint() {
    const { formatCurrency } = useCurrency();
    const { data: doc, isLoading, isError } = usePrintRecord<CashDocument>('/accounting/cash-documents');
    const history = useCashDocumentHistory(doc?.id ?? null).data;
    const money = (v: string) => (Number(v) ? formatCurrency(Number(v)) : '');
    const title = doc?.is_receipt ? 'Cash Receipt Voucher' : 'Cash Payment Voucher';

    return (
        <DocumentPrintLayout
            title={title} number={doc?.document_number ?? ''} status={doc?.status}
            isLoading={isLoading} error={isError}
            signatories={doc?.is_receipt ? ['Received by (Cashier)', 'Paid in by', 'Approved by'] : ['Prepared by', 'Approved by', 'Received by (Payee)']}
            details={[
                { label: 'Cash journal', value: doc?.cash_journal_name },
                { label: 'Posting date', value: doc?.posting_date && formatDate(doc.posting_date) },
                { label: 'Transaction', value: doc?.transaction_type_label },
                { label: doc?.is_receipt ? 'Received from' : 'Paid to', value: doc?.recipient },
                { label: 'Reference', value: doc?.reference },
                { label: 'MDA', value: doc?.mda_name },
                { label: 'Journal', value: doc?.journal_number },
            ]}
        >
            {doc?.description && <div className="doc-note"><b>Description</b>{doc.description}</div>}
            <table className="doc-table">
                <thead><tr><th>Account</th><th>Particulars</th><th className="r">Debit</th><th className="r">Credit</th></tr></thead>
                <tbody>
                    {(history?.entries ?? []).map((e, i) => (
                        <tr key={i}><td>{e.account_code} {e.account_name}</td><td>{e.memo}</td><td className="r">{money(e.debit)}</td><td className="r">{money(e.credit)}</td></tr>
                    ))}
                </tbody>
                <tfoot><tr><td colSpan={3} className="r">Amount</td><td className="r">{doc ? formatCurrency(Number(doc.amount)) : ''}</td></tr></tfoot>
            </table>
            {history?.entries_are_projected && <div className="doc-note"><b>Draft</b>This voucher has not been posted. The entries shown are the ones it will post.</div>}
        </DocumentPrintLayout>
    );
}
