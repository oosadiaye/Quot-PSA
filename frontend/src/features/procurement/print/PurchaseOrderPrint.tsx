import DocumentPrintLayout from '../../../components/print/DocumentPrintLayout';
import { useCurrency } from '../../../context/CurrencyContext';
import { formatDate } from '../../../utils/date';
import { usePrintRecord } from './usePrintRecord';

/** Route: /procurement/orders/:id/print */
export default function PurchaseOrderPrint() {
    const { formatCurrency } = useCurrency();
    const { data: po, isLoading, isError } = usePrintRecord('/procurement/orders');
    const lines: any[] = po?.lines ?? [];
    const money = (v: unknown) => formatCurrency(Number(v ?? 0));

    return (
        <DocumentPrintLayout
            title="Purchase Order" number={po?.po_number ?? ''} status={po?.status}
            isLoading={isLoading} error={isError}
            signatories={['Prepared by', 'Procurement Officer', 'Accounting Officer']}
            details={[
                { label: 'Supplier', value: po?.vendor_name },
                { label: 'MDA', value: po?.mda_name },
                { label: 'Order date', value: po?.order_date && formatDate(po.order_date) },
                { label: 'Expected delivery', value: po?.expected_delivery_date && formatDate(po.expected_delivery_date) },
                { label: 'Deliver to', value: po?.delivery_address },
                { label: 'Delivery contact', value: po?.delivery_contact },
                { label: 'Payment terms', value: po?.payment_terms },
                { label: 'Fund', value: po?.fund_name },
            ]}
        >
            <table className="doc-table">
                <thead><tr><th>#</th><th>Description</th><th className="r">Qty</th><th className="r">Unit price</th><th className="r">Amount</th></tr></thead>
                <tbody>
                    {lines.map((l, i) => (
                        <tr key={l.id ?? i}>
                            <td>{i + 1}</td><td>{l.item_description}</td>
                            <td className="r">{l.quantity}</td><td className="r">{money(l.unit_price)}</td><td className="r">{money(l.total_price)}</td>
                        </tr>
                    ))}
                </tbody>
                <tfoot>
                    <tr><td colSpan={4} className="r">Subtotal</td><td className="r">{money(po?.subtotal)}</td></tr>
                    {Number(po?.tax_amount) > 0 && <tr><td colSpan={4} className="r">Tax ({po?.tax_rate}%)</td><td className="r">{money(po?.tax_amount)}</td></tr>}
                    <tr><td colSpan={4} className="r">Total</td><td className="r">{money(po?.total_amount)}</td></tr>
                </tfoot>
            </table>
            {po?.terms_and_conditions && <div className="doc-note"><b>Terms and conditions</b>{po.terms_and_conditions}</div>}
            {po?.notes && <div className="doc-note"><b>Notes</b>{po.notes}</div>}
        </DocumentPrintLayout>
    );
}
