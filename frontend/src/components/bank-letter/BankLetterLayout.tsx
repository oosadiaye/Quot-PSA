import type { BankLetterSettings, PaymentBatch } from
  '../../features/accounting/hooks/usePaymentBatches';

/** Minimum ruled rows on the printed form.
 *
 * Blank ruled rows are not decoration: on a signed instruction they are
 * what stops a line being appended after the signatures. Reproduced from
 * the OAG's paper form.
 */
const MIN_ROWS = 14;

interface BankLetterLayoutProps {
  batch: PaymentBatch;
  settings: BankLetterSettings;
}

/** DD/MM/YYYY. Nigerian convention — never the US ordering. */
function formatLetterDate(iso: string): string {
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(y, m - 1, d).toLocaleDateString('en-GB');
}

function formatAmount(value: string): string {
  return Number(value).toLocaleString('en-NG', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

export default function BankLetterLayout({ batch, settings }: BankLetterLayoutProps) {
  const lines = batch.lines.filter((l) => l.is_active_membership);
  const padding = Math.max(0, MIN_ROWS - lines.length);
  const total = lines.reduce((sum, l) => sum + Number(l.amount), 0);

  return (
    <div className="bank-letter">
      <style>{`
        .bank-letter { font-family: Arial, Helvetica, sans-serif; color:#000;
                       background:#fff; max-width:210mm; margin:0 auto; padding:12mm; }
        .bank-letter table { width:100%; border-collapse:collapse; margin-top:8px; }
        .bank-letter th, .bank-letter td { border:1px solid #000; padding:3px 6px;
                       font-size:11px; height:18px; }
        .bank-letter th { text-align:center; font-weight:700; }
        .bank-letter .num { text-align:right; }
        .bank-letter .ctr { text-align:center; }
        @media print {
          .bank-letter { padding:0; max-width:none; }
          @page { size:A4 portrait; margin:15mm; }
          .no-print { display:none !important; }
        }
      `}</style>

      {settings.letterhead_logo && (
        <div style={{ textAlign: 'center' }}>
          <img src={settings.letterhead_logo} alt="" style={{ height: 70 }} />
        </div>
      )}

      <div style={{ textAlign: 'center', fontWeight: 700, fontSize: 13, marginTop: 8 }}>
        <div>{settings.ministry_name}</div>
        <div style={{ marginTop: 6 }}>{settings.office_name}</div>
        {settings.office_address && <div style={{ marginTop: 6 }}>{settings.office_address}</div>}
      </div>

      <div style={{ textAlign: 'right', fontWeight: 700, fontSize: 12, marginTop: 10 }}>
        DATE: {formatLetterDate(batch.batch_date)}
      </div>

      <div style={{ fontWeight: 700, fontSize: 12, marginTop: 10, lineHeight: 1.9 }}>
        <div>THE MANAGER</div>
        <div>{batch.addressee_bank_name}:</div>
        <div>ACCOUNT NO:{batch.addressee_account_no}</div>
      </div>

      <div style={{ textAlign: 'center', fontWeight: 700, fontSize: 14, marginTop: 12 }}>
        BANK PAYMENT(S)/CONFIRMATION(S)
      </div>

      <table>
        <thead>
          <tr>
            <th style={{ width: '6%' }}>S/N</th>
            <th style={{ width: '24%' }}>VENDOR NAME</th>
            <th style={{ width: '16%' }}>BANK</th>
            <th style={{ width: '16%' }}>ACCOUNT</th>
            <th style={{ width: '20%' }}>PURPOSE</th>
            <th style={{ width: '18%' }}>AMOUNT</th>
          </tr>
        </thead>
        <tbody>
          {lines.map((line) => (
            <tr key={line.id}>
              <td className="ctr">{line.sequence}</td>
              <td>{line.payee_name}</td>
              <td>{line.payee_bank}</td>
              <td>{line.payee_account}</td>
              <td>{line.purpose}</td>
              <td className="num">{formatAmount(line.amount)}</td>
            </tr>
          ))}
          {Array.from({ length: padding }, (_, i) => (
            <tr key={`pad-${i}`}>
              <td className="ctr">{lines.length + i + 1}</td>
              <td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr>
            <th>TOTAL</th>
            <th /><th /><th /><th />
            <th className="num" data-testid="letter-total">
              {formatAmount(String(total))}
            </th>
          </tr>
        </tfoot>
      </table>

      <div style={{ marginTop: 48, textAlign: 'center', fontSize: 12 }}>
        {settings.accountant_general_signature && (
          <img src={settings.accountant_general_signature} alt="" style={{ height: 40 }} />
        )}
        <div>----------------------</div>
        <div style={{ fontWeight: 700, marginTop: 6 }}>{settings.accountant_general_name}</div>
        <div style={{ fontWeight: 700 }}>{settings.accountant_general_title}</div>
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 56, fontSize: 12 }}>
        <div style={{ textAlign: 'left' }}>
          {settings.director_treasury_signature && (
            <img src={settings.director_treasury_signature} alt="" style={{ height: 36 }} />
          )}
          <div>---------------------------</div>
          <div style={{ fontWeight: 700, marginTop: 6 }}>{settings.director_treasury_name}</div>
          <div style={{ fontWeight: 700 }}>{settings.director_treasury_title}</div>
        </div>
        <div style={{ textAlign: 'left' }}>
          {settings.director_mgmt_acct_signature && (
            <img src={settings.director_mgmt_acct_signature} alt="" style={{ height: 36 }} />
          )}
          <div>-----------------------------------</div>
          <div style={{ fontWeight: 700, marginTop: 6 }}>{settings.director_mgmt_acct_name}</div>
          <div style={{ fontWeight: 700 }}>{settings.director_mgmt_acct_title}</div>
        </div>
      </div>
    </div>
  );
}
