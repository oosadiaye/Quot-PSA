/**
 * Bank instruction letter for one cheque in the Cheque Register.
 *
 * Reuses the shared `BankLetterLayout` — the `checks/{id}/letter/` endpoint
 * returns the same `{ batch, settings }` envelope the payment-batch letter
 * used, so a cheque covering several posted payments prints one signed
 * instruction to the bank with a line per payment.
 */
import { useParams } from 'react-router-dom';
import BankLetterLayout from '../../../components/bank-letter/BankLetterLayout';
import { useChequeLetter } from '../hooks/usePaymentBatches';

export default function ChequeLetterPrintPreview() {
  const { id } = useParams<{ id: string }>();
  const { data, isLoading, error } = useChequeLetter(id ? Number(id) : undefined);

  if (isLoading) return <div style={{ padding: 24 }}>Loading letter…</div>;
  if (error || !data) {
    return (
      <div style={{ padding: 24, color: '#b91c1c' }}>
        Could not load this cheque. It may have been cancelled or you may not
        have access to it.
      </div>
    );
  }

  return (
    <div style={{ background: 'var(--color-surface-hover)', minHeight: '100vh', padding: '16px 0' }}>
      <div className="no-print" style={{ textAlign: 'center', marginBottom: 12 }}>
        <button
          onClick={() => window.print()}
          style={{
            padding: '8px 20px', borderRadius: 8, border: '1px solid var(--color-border)',
            background: 'var(--color-surface)', cursor: 'pointer', fontSize: 14, fontWeight: 600,
          }}
        >
          Print letter
        </button>
      </div>
      <div style={{ background: '#fff', boxShadow: '0 1px 4px rgba(0,0,0,.15)', maxWidth: '210mm', margin: '0 auto' }}>
        <BankLetterLayout batch={data.batch} settings={data.settings} />
      </div>
    </div>
  );
}
