import DocumentPrintLayout from '../../../components/print/DocumentPrintLayout';
import { useCurrency } from '../../../context/CurrencyContext';
import { formatDate } from '../../../utils/date';
import { usePrintRecord } from './usePrintRecord';

/** Three-way match sheet (PO vs GRN vs invoice). Route: /procurement/matching/:id/print */
export default function InvoiceVerificationPrint() {
    const { formatCurrency } = useCurrency();
    const { data: m, isLoading, isError } = usePrintRecord('/procurement/invoice-matching');
    const money = (v: unknown) => (v === null || v === undefined || v === '' ? 'n/a' : formatCurrency(Number(v)));
    const hasWht = Number(m?.wht_amount) > 0;

    return (
        <DocumentPrintLayout
            title="Invoice Verification" number={m?.verification_number ?? ''} status={m?.status}
            isLoading={isLoading} error={isError}
            signatories={['Verified by', 'Checked by (Accountant)', 'Approved by']}
            details={[
                { label: 'Supplier', value: m?.vendor_name },
                { label: 'Supplier invoice no.', value: m?.invoice_reference },
                { label: 'Invoice date', value: m?.invoice_date && formatDate(m.invoice_date) },
                { label: 'Purchase order', value: m?.po_number },
                { label: 'GRN', value: m?.grn_number },
                { label: 'Match result', value: m?.match_type },
                { label: 'Verified on', value: m?.matched_date && formatDate(m.matched_date) },
                { label: 'Payment hold', value: m?.payment_hold ? 'Yes' : undefined },
            ]}
        >
            <table className="doc-table">
                <thead><tr><th>Three-way comparison</th><th className="r">Amount</th></tr></thead>
                <tbody>
                    <tr><td>Purchase order</td><td className="r">{money(m?.po_amount)}</td></tr>
                    <tr><td>Goods received (GRN)</td><td className="r">{money(m?.grn_amount)}</td></tr>
                    <tr><td>Supplier invoice</td><td className="r">{money(m?.invoice_amount)}</td></tr>
                </tbody>
                <tfoot>
                    <tr><td>Variance (invoice against receipt)</td><td className="r">{money(m?.variance_amount)} ({Number(m?.variance_percentage ?? 0).toFixed(2)}%)</td></tr>
                </tfoot>
            </table>
            {m?.variance_reason && <div className="doc-note"><b>Variance explanation</b>{m.variance_reason}</div>}
            <table className="doc-table">
                <thead><tr><th>Invoice settlement</th><th className="r">Amount</th></tr></thead>
                <tbody>
                    <tr><td>Invoice subtotal</td><td className="r">{money(m?.invoice_subtotal)}</td></tr>
                    <tr><td>Tax on invoice</td><td className="r">{money(m?.invoice_tax_amount)}</td></tr>
                    {hasWht && <tr><td>Withholding tax deducted</td><td className="r">{money(m?.wht_amount)}</td></tr>}
                    {Number(m?.down_payment_applied) > 0 && <tr><td>Down payment applied</td><td className="r">{money(m?.down_payment_applied)}</td></tr>}
                </tbody>
                <tfoot><tr><td>Net payable</td><td className="r">{money(m?.net_payable)}</td></tr></tfoot>
            </table>
            {m?.notes && <div className="doc-note"><b>Notes</b>{m.notes}</div>}
            <div className="doc-note"><b>Certification</b>I certify that the goods or services were received as stated above and that the invoice agrees with the purchase order and receipt.</div>
        </DocumentPrintLayout>
    );
}
