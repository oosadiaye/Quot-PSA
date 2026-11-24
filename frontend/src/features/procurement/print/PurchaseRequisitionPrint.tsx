import DocumentPrintLayout from '../../../components/print/DocumentPrintLayout';
import { useCurrency } from '../../../context/CurrencyContext';
import { formatDate } from '../../../utils/date';
import { usePrintRecord } from './usePrintRecord';

/** Route: /procurement/requisitions/:id/print */
export default function PurchaseRequisitionPrint() {
    const { formatCurrency } = useCurrency();
    const { data: pr, isLoading, isError } = usePrintRecord('/procurement/requests');
    const lines: any[] = pr?.lines ?? [];
    const total = lines.reduce((sum, l) => sum + Number(l.total_estimated_price ?? 0), 0);

    return (
        <DocumentPrintLayout
            title="Purchase Requisition" number={pr?.request_number ?? ''} status={pr?.status}
            isLoading={isLoading} error={isError}
            signatories={['Requesting Officer', 'Head of Department', 'Budget Officer', 'Approving Authority']}
            details={[
                { label: 'MDA', value: pr?.mda_name },
                { label: 'Date requested', value: pr?.requested_date && formatDate(pr.requested_date) },
                { label: 'Requested by', value: pr?.requested_by_name },
                { label: 'Priority', value: pr?.priority },
                { label: 'Fund', value: pr?.fund_name },
                { label: 'Function', value: pr?.function_name },
                { label: 'Programme', value: pr?.program_name },
                { label: 'Geo', value: pr?.geo_name },
            ]}
        >
            {pr?.description && <div className="doc-note"><b>Purpose</b>{pr.description}</div>}
            <table className="doc-table">
                <thead><tr><th>#</th><th>Description</th><th>Account</th><th className="r">Qty</th><th className="r">Est. unit price</th><th className="r">Est. total</th></tr></thead>
                <tbody>
                    {lines.map((l, i) => (
                        <tr key={l.id ?? i}>
                            <td>{i + 1}</td><td>{l.item_description}</td><td>{l.account_code}</td>
                            <td className="r">{l.quantity}</td>
                            <td className="r">{formatCurrency(Number(l.estimated_unit_price ?? 0))}</td>
                            <td className="r">{formatCurrency(Number(l.total_estimated_price ?? 0))}</td>
                        </tr>
                    ))}
                </tbody>
                <tfoot><tr><td colSpan={5} className="r">Estimated total</td><td className="r">{formatCurrency(total)}</td></tr></tfoot>
            </table>
        </DocumentPrintLayout>
    );
}
