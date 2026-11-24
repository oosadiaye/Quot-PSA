import DocumentPrintLayout from '../../../components/print/DocumentPrintLayout';
import { useCurrency } from '../../../context/CurrencyContext';
import { formatDate } from '../../../utils/date';
import { usePrintRecord } from './usePrintRecord';

/** Route: /procurement/grn/:id/print */
export default function GoodsReceivedNotePrint() {
    const { formatCurrency } = useCurrency();
    const { data: grn, isLoading, isError } = usePrintRecord('/procurement/grns');
    const lines: any[] = grn?.lines ?? [];
    const value = (l: any) => Number(l.quantity_received ?? 0) * Number(l.unit_price ?? 0);
    const total = lines.reduce((sum, l) => sum + value(l), 0);

    return (
        <DocumentPrintLayout
            title="Goods Received Note" number={grn?.grn_number ?? ''} status={grn?.status}
            isLoading={isLoading} error={isError}
            signatories={['Delivered by (Supplier)', 'Received by (Store Officer)', 'Inspected by', 'Head of Stores']}
            details={[
                { label: 'Purchase order', value: grn?.po_number },
                { label: 'MDA', value: grn?.mda_name },
                { label: 'Date received', value: grn?.received_date && formatDate(grn.received_date) },
                { label: 'Received by', value: grn?.received_by },
                { label: 'Store', value: grn?.warehouse_name },
            ]}
        >
            <table className="doc-table">
                <thead><tr><th>#</th><th>Description</th><th>Batch</th><th>Expiry</th><th className="r">Qty received</th><th className="r">Unit price</th><th className="r">Value</th></tr></thead>
                <tbody>
                    {lines.map((l, i) => (
                        <tr key={l.id ?? i}>
                            <td>{i + 1}</td><td>{l.item_description}</td><td>{l.batch_number}</td>
                            <td>{l.expiry_date ? formatDate(l.expiry_date) : ''}</td>
                            <td className="r">{l.quantity_received}</td>
                            <td className="r">{formatCurrency(Number(l.unit_price ?? 0))}</td>
                            <td className="r">{formatCurrency(value(l))}</td>
                        </tr>
                    ))}
                </tbody>
                <tfoot><tr><td colSpan={6} className="r">Total value received</td><td className="r">{formatCurrency(total)}</td></tr></tfoot>
            </table>
            {grn?.notes && <div className="doc-note"><b>Remarks</b>{grn.notes}</div>}
        </DocumentPrintLayout>
    );
}
