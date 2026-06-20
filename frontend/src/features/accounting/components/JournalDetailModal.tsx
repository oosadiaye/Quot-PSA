import { X } from 'lucide-react';
import { useJournalDetail } from '../hooks/useJournal';

interface JournalDetailModalProps {
    id: number;
    onClose: () => void;
}

/**
 * Read-only drill-down into a single journal's accounting entries
 * (the full double-entry: account, debit, credit, memo).
 *
 * Shared by the Journal list ("View") and the GL Ledger drill-down
 * (click a journal number on a ledger line). Overlay z-index is 1100
 * so it stacks ABOVE the GL Ledger modal (z-index 1000) when used as
 * a nested drill-down.
 */
const JournalDetailModal = ({ id, onClose }: JournalDetailModalProps) => {
    const { data: journal, isLoading } = useJournalDetail(id);

    return (
        <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(0,0,0,0.5)', zIndex: 1100, display: 'flex', alignItems: 'center', justifyContent: 'center' }} onClick={onClose} role="presentation">
            <div className="card glass" style={{ width: '90%', maxWidth: '800px', maxHeight: '90vh', overflowY: 'auto' }} onClick={e => e.stopPropagation()} role="dialog" aria-modal="true">
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '1.5rem' }}>
                    <h2 style={{ fontSize: 'var(--text-lg)', margin: 0 }}>
                        Journal Details: {journal?.document_number || journal?.reference_number || `JE-${id}`}
                    </h2>
                    <button onClick={onClose} aria-label="Close" style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text)' }}><X size={20} /></button>
                </div>
                {isLoading ? (
                    <p>Loading details...</p>
                ) : (
                    <div>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1.5rem', fontSize: 'var(--text-sm)' }}>
                            <div><strong>Reference:</strong> {journal?.reference_number || '-'}</div>
                            <div><strong>Date:</strong> {journal?.posting_date}</div>
                            <div><strong>Status:</strong> {journal?.status}</div>
                            <div><strong>Fund:</strong> {journal?.fund_name || '-'}</div>
                            <div><strong>Geo:</strong> {journal?.geo_name || '-'}</div>
                            <div style={{ gridColumn: 'span 2' }}><strong>Description:</strong> {journal?.description}</div>
                        </div>

                        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--text-sm)' }}>
                            <thead>
                                <tr style={{ background: 'var(--color-surface)', textAlign: 'left' }}>
                                    <th style={{ padding: '0.75rem' }}>Account</th>
                                    <th style={{ padding: '0.75rem' }}>Document No.</th>
                                    <th style={{ padding: '0.75rem', textAlign: 'right' }}>Debit</th>
                                    <th style={{ padding: '0.75rem', textAlign: 'right' }}>Credit</th>
                                    <th style={{ padding: '0.75rem' }}>Memo</th>
                                </tr>
                            </thead>
                            <tbody>
                                {journal?.lines?.map((line: any) => (
                                    <tr key={line.id ?? line.account_code} style={{ borderBottom: '1px solid var(--color-border)' }}>
                                        <td style={{ padding: '0.75rem' }}>{line.account_code} - {line.account_name}</td>
                                        <td style={{ padding: '0.75rem', fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>{line.document_number || '-'}</td>
                                        <td style={{ padding: '0.75rem', textAlign: 'right' }}>{(parseFloat(line.debit) || 0) > 0 ? (parseFloat(line.debit)).toLocaleString(undefined, { minimumFractionDigits: 2 }) : '-'}</td>
                                        <td style={{ padding: '0.75rem', textAlign: 'right' }}>{(parseFloat(line.credit) || 0) > 0 ? (parseFloat(line.credit)).toLocaleString(undefined, { minimumFractionDigits: 2 }) : '-'}</td>
                                        <td style={{ padding: '0.75rem' }}>{line.memo || '-'}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>
        </div>
    );
};

export default JournalDetailModal;
