/**
 * IPC Detail — redesigned per the analytical-dashboard reference.
 *
 * Layout: 3-col left sidebar (Status / Contract Reference / Audit
 * Trail) + 9-col main column (3 stat cards on top, GL Ledger table in
 * the middle, compliance + chart at the bottom). The "Adjustment
 * Ledger" of the original mock is replaced with the **real GL
 * journal lines** sourced from the IPC's accrual journal — DR
 * Expense, DR Input VAT, CR Accounts Payable (vendor), CR WHT — so
 * what the operator sees on screen exactly matches what posted to
 * the books. When the journal hasn't posted yet (Submitted /
 * Certified states), the table shows the *projected* entries
 * computed from the IPC's deduction columns; an "Unposted" pill
 * makes the distinction clear.
 *
 * Card meanings (per spec):
 *   ① GROSS AMOUNT     = contract sum (the ceiling — original_sum +
 *                         approved variations)
 *   ② NET PAYABLE      = this IPC's net_payable (after deductions)
 *   ③ PREV. CERTIFIED  = sum of `this_certificate_gross` across all
 *                         OTHER IPCs on this contract (excludes the
 *                         one being viewed)
 */
import { useNavigate, useParams } from 'react-router-dom';
import {
  Modal, Input, App as AntApp, Popconfirm,
} from 'antd';
import { useMemo, useState } from 'react';
import {
  ArrowLeft, Printer, FileText, Shield, Clock, CheckCircle,
  AlertCircle, Wallet, ListChecks,
} from 'lucide-react';
import LoadingScreen from '../../../components/common/LoadingScreen';
import {
  useIPC, useIPCs,
  useCertifyIPC, useApproveIPC, useRaiseVoucher,
  useMarkIPCPaid, useRejectIPC, useSetIPCWhtExemption,
} from '../hooks/useIPCs';
import { useContract } from '../hooks/useContracts';
import { useJournal } from '../../accounting/hooks/useJournal';
import { formatServiceError } from '../utils/errors';
import { useCurrency } from '../../../context/CurrencyContext';
import { ListPageShell } from '../../../components/layout';

// ── Status → step machine (which buttons are valid) ──────────────────
const ACTION_MAP: Record<string, Array<'certify' | 'approve' | 'raise_voucher' | 'mark_paid'>> = {
  SUBMITTED:          ['certify'],
  CERTIFIER_REVIEWED: ['approve'],
  APPROVED:           ['raise_voucher'],
  VOUCHER_RAISED:     ['mark_paid'],
};

const STATUS_PILL: Record<string, { bg: string; fg: string }> = {
  DRAFT:              { bg: '#f1f5f9', fg: '#475569' },
  SUBMITTED:          { bg: '#dcfce7', fg: '#15803d' },
  CERTIFIER_REVIEWED: { bg: '#dbeafe', fg: '#1d4ed8' },
  APPROVED:           { bg: '#e0e7ff', fg: '#4338ca' },
  VOUCHER_RAISED:     { bg: '#fef3c7', fg: '#a16207' },
  PAID:               { bg: '#dcfce7', fg: '#15803d' },
  REJECTED:           { bg: '#fee2e2', fg: '#b91c1c' },
};


const IPCDetail = () => {
  const { id } = useParams<{ id: string }>();
  const iid = Number(id);
  const navigate = useNavigate();
  const { message } = AntApp.useApp();
  const { formatCurrency } = useCurrency();

  const { data: ipc, isLoading } = useIPC(iid);
  const { data: contract } = useContract(ipc?.contract ?? null);
  // All IPCs on the same contract — drives the "Prev. Certified"
  // card. We exclude the IPC currently being viewed so the figure
  // genuinely is "previous", not "cumulative including this one".
  const { data: siblingIPCs } = useIPCs({ contract: ipc?.contract });
  // The accrual journal (set on APPROVED). When present, the GL
  // ledger table renders real journal lines — exactly what posted.
  const { data: accrualJournal } = useJournal(ipc?.accrual_journal ?? null);

  const certify = useCertifyIPC();
  const approve = useApproveIPC();
  const raiseV = useRaiseVoucher();
  const markPaid = useMarkIPCPaid();
  const reject = useRejectIPC();
  const setWhtExempt = useSetIPCWhtExemption();

  const [rejectOpen, setRejectOpen] = useState(false);
  const [rejectReason, setRejectReason] = useState('');

  // ── Derived numbers ─────────────────────────────────────────────────
  const contractSum = Number(contract?.contract_ceiling || 0);
  const netPayable = Number(ipc?.net_payable ?? 0);
  const previousCertified = useMemo(() => {
    const rows = (siblingIPCs?.results ?? siblingIPCs ?? []) as any[];
    return rows
      .filter((r) => r.id !== iid && r.status !== 'REJECTED')
      .reduce((s, r) => s + (parseFloat(String(r.this_certificate_gross || 0)) || 0), 0);
  }, [siblingIPCs, iid]);
  const contractProgress = useMemo(() => {
    if (!contractSum || contractSum <= 0) return 0;
    return Math.min(
      100,
      ((Number(contract?.cumulative_gross_certified ?? previousCertified) + Number(ipc?.this_certificate_gross ?? 0))
       / contractSum) * 100,
    );
  }, [contract, ipc, previousCertified, contractSum]);

  if (isLoading || !ipc) return <LoadingScreen />;

  const allowed = ACTION_MAP[ipc.status] ?? [];
  const terminal = ['PAID', 'REJECTED'].includes(ipc.status);
  const tag = STATUS_PILL[ipc.status] ?? STATUS_PILL.DRAFT;

  // ── Action handlers ─────────────────────────────────────────────────
  const runAction = async (
    label: string,
    hook: { mutateAsync: (v: { id: number }) => Promise<unknown> },
  ) => {
    try {
      await hook.mutateAsync({ id: iid });
      message.success(`${label} successful`);
    } catch (e) {
      message.error(formatServiceError(e, `${label} failed`));
    }
  };

  return (
    <ListPageShell>
      {/* ── Top dark header ───────────────────────────────────────── */}
      <header style={topHeader}>
        <div style={topHeaderInner}>
          <button onClick={() => navigate(`/contracts/${ipc.contract}`)} style={backBtn}>
            <ArrowLeft size={14} />
          </button>
          <div style={{ flex: 1 }}>
            <div style={topBreadcrumb}>
              IPC REVIEW
              <span style={{ color: '#475569', margin: '0 6px' }}>•</span>
              <span style={{ color: '#94a3b8' }}>
                {ipc.ipc_number || `IPC #${iid}`}
              </span>
            </div>
            <h1 style={topTitle}>
              Certificate {ipc.ipc_number ? ipc.ipc_number.split('/').pop() : `#${iid}`}
              {' — '}
              <span style={{ fontWeight: 500, opacity: 0.85 }}>
                {contract?.title ?? `Contract #${ipc.contract}`}
              </span>
            </h1>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button onClick={() => window.print()} style={topBtnGhost}>
              <Printer size={14} /> Print Preview
            </button>
            {!terminal && (
              <button onClick={() => setRejectOpen(true)} style={topBtnDanger}>
                Reject
              </button>
            )}
            {allowed.includes('certify') && (
              <button onClick={() => runAction('Certify', certify)} style={topBtnPrimary}>
                Certify Payment
              </button>
            )}
            {allowed.includes('approve') && (
              <Popconfirm
                title="Approve this IPC?"
                description="Approval triggers the accrual journal: DR Expense / CR AP."
                okText="Yes, approve" cancelText="Cancel"
                onConfirm={() => runAction('Approve', approve)}
              >
                <button style={topBtnPrimary}>Approve</button>
              </Popconfirm>
            )}
            {allowed.includes('raise_voucher') && (
              <button onClick={() => runAction('Raise Voucher', raiseV)} style={topBtnPrimary}>
                Raise Voucher
              </button>
            )}
            {allowed.includes('mark_paid') && (
              <button onClick={() => runAction('Mark Paid', markPaid)} style={topBtnPrimary}>
                Mark Paid
              </button>
            )}
          </div>
        </div>
      </header>

      {/* ── Body grid ─────────────────────────────────────────────── */}
      <div style={bodyGrid}>
        {/* LEFT COLUMN */}
        <div style={leftCol}>
          {/* Document lifecycle */}
          <div style={panelLight}>
            <div style={panelHeaderRow}>
              <h3 style={panelHeader}>Document Lifecycle</h3>
              <span style={{
                ...statusPillBase,
                background: tag.bg, color: tag.fg,
              }}>
                {ipc.status}
              </span>
            </div>
            <div style={{ padding: '1rem', display: 'flex', flexDirection: 'column', gap: 12 }}>
              <MetaTile
                label="Creation Date"
                value={ipc.created_at ? new Date(ipc.created_at).toLocaleDateString('en-GB', {
                  year: 'numeric', month: 'short', day: '2-digit',
                }) : '—'}
              />
              <MetaTile
                label="Last Updated"
                value={ipc.updated_at ? new Date(ipc.updated_at).toLocaleString('en-GB', {
                  year: 'numeric', month: 'short', day: '2-digit',
                  hour: '2-digit', minute: '2-digit', hour12: false,
                }) : '—'}
              />
              <MetaTile label="Posting Date" value={ipc.posting_date ?? '—'} />
            </div>
          </div>

          {/* Project reference */}
          <div style={panelLight}>
            <div style={panelHeaderRow}>
              <h3 style={{ ...panelHeader, textAlign: 'center', flex: 1 }}>Project Reference</h3>
            </div>
            <div style={{ padding: '1rem', display: 'flex', flexDirection: 'column', gap: 12 }}>
              <FieldStack
                label="Contractor"
                value={contract?.vendor_name ?? `Vendor #${contract?.vendor ?? '—'}`}
              />
              <FieldStack
                label="Contract"
                value={contract?.contract_number ?? `#${ipc.contract}`}
              />
              <div style={{ paddingTop: 8, borderTop: '1px solid #f1f5f9' }}>
                <div style={progressLabelRow}>
                  <span style={{ color: '#64748b' }}>Contract Progress</span>
                  <span style={{ color: '#2563eb', fontWeight: 700 }}>
                    {contractProgress.toFixed(1)}%
                  </span>
                </div>
                <div style={progressTrack}>
                  <div style={{ ...progressFill, width: `${contractProgress}%` }} />
                </div>
              </div>
            </div>
          </div>

          {/* WHT determination — parity with Invoice Verification.
              The exemption toggle stays available until the IPC is
              terminal; once PAID the row is locked and the actual
              wht_amount tells the story. */}
          <div style={panelLight}>
            <div style={panelHeaderRow}>
              <h3 style={panelHeader}>Withholding Tax</h3>
              {ipc.wht_exempt ? (
                <span style={{ ...statusPillBase, background: '#fef3c7', color: '#a16207' }}>
                  EXEMPT
                </span>
              ) : (
                <span style={{ ...statusPillBase, background: '#dbeafe', color: '#1d4ed8' }}>
                  SUBJECT
                </span>
              )}
            </div>
            <div style={{ padding: '1rem', display: 'flex', flexDirection: 'column', gap: 12 }}>
              {(() => {
                // Compute the projected WHT from the IPC's stored
                // determination — same algebra the backend's
                // ``IPCService._derive_taxes`` runs at payment time.
                const gross = Number(ipc.this_certificate_gross || 0);
                const rate = Number((ipc.withholding_tax as any)?.rate ?? 0);
                const projectedWht = !ipc.wht_exempt && rate > 0 && gross > 0
                  ? (gross * rate) / 100
                  : 0;
                return (
                  <>
                    <FieldStack
                      label="Determination"
                      value={
                        ipc.withholding_tax_code
                          ? `${ipc.withholding_tax_code} @ ${rate.toFixed(2)}%`
                          : ipc.withholding_tax
                            ? `Code #${ipc.withholding_tax} @ ${rate.toFixed(2)}%`
                            : 'No WHT code on file'
                      }
                    />
                    <FieldStack
                      label="Projected WHT at Payment"
                      value={
                        ipc.wht_amount && Number(ipc.wht_amount) > 0
                          ? formatCurrency(Number(ipc.wht_amount)) + ' (recognised)'
                          : ipc.wht_exempt
                            ? `${formatCurrency(0)} — exempt`
                            : projectedWht > 0
                              ? `${formatCurrency(projectedWht)} (auto on Mark Paid)`
                              : `${formatCurrency(0)} — no WHT applies`
                      }
                    />
                    {!terminal && (
                      <button
                        type="button"
                        onClick={() => {
                          setWhtExempt.mutate(
                            { id: iid, wht_exempt: !ipc.wht_exempt },
                            {
                              onSuccess: () => message.success(
                                ipc.wht_exempt
                                  ? 'WHT exemption cleared — vendor default applies.'
                                  : 'WHT exemption applied — no WHT will be deducted at payment.',
                              ),
                              onError: (e) =>
                                message.error(formatServiceError(e, 'Toggle failed')),
                            },
                          );
                        }}
                        disabled={setWhtExempt.isPending}
                        style={whtToggleBtn(ipc.wht_exempt)}
                      >
                        {ipc.wht_exempt ? 'Remove Exemption' : 'Mark as Exempt'}
                      </button>
                    )}
                  </>
                );
              })()}
            </div>
          </div>

          {/* Audit Trail (dark) */}
          <div style={panelDark}>
            <div style={{
              ...panelHeaderRow,
              background: 'rgba(255,255,255,0.05)',
              borderColor: 'rgba(255,255,255,0.05)',
            }}>
              <Shield size={13} color="#34d399" />
              <h3 style={{ ...panelHeader, color: '#94a3b8', marginLeft: 6 }}>Audit Trail</h3>
            </div>
            <div style={{ padding: '1rem', display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div style={hashCard}>
                <span style={hashCaption}>Verification Hash</span>
                <code style={hashCode}>
                  {ipc.integrity_hash || ipc.line_items_hash || '—'}
                </code>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={shieldDot} />
                <span style={{ fontSize: 9, color: '#94a3b8', fontStyle: 'italic' }}>
                  Integrity Shield Active
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* MAIN COLUMN */}
        <div style={mainCol}>
          {/* Stat cards row */}
          <div style={statRow}>
            <StatCard
              label="Gross Amount"
              value={formatCurrency(contractSum)}
              caption="Total Contract Sum"
              accentBar="#3b82f6"
              icon={<FileText size={14} color="#cbd5e1" />}
            />
            <StatCardDark
              label="Net Payable"
              value={formatCurrency(netPayable)}
              caption="This IPC — amount after all deductions"
              icon={<Wallet size={14} color="rgba(191,219,254,0.6)" />}
            />
            <StatCard
              label="Prev. Certified"
              value={formatCurrency(previousCertified)}
              caption={
                previousCertified > 0
                  ? `Sum of prior IPCs on this contract`
                  : 'No previous IPCs'
              }
              accentBar="#94a3b8"
              valueColor="#64748b"
              icon={<Clock size={14} color="#cbd5e1" />}
            />
          </div>

          {/* GL Ledger table */}
          <GLLedgerCard
            ipc={ipc}
            journal={accrualJournal}
            contract={contract}
            formatCurrency={formatCurrency}
          />

          {/* Bottom row — payment history + compliance */}
          <div style={bottomRow}>
            <div style={panelLight}>
              <div style={{ padding: '1rem' }}>
                <h4 style={chartHeader}>Payment History Trend</h4>
                <div style={chartArea}>
                  {/* Render up to 5 bars from sibling IPCs (this IPC
                      highlighted, prior ones in light blue, future
                      placeholders dimmed). */}
                  {(() => {
                    const allRows = ((siblingIPCs?.results ?? siblingIPCs ?? []) as any[])
                      .filter((r) => r.status !== 'REJECTED');
                    const max = Math.max(
                      contractSum,
                      ...allRows.map((r) => parseFloat(String(r.this_certificate_gross || 0)) || 0),
                    ) || 1;
                    const slots = [...allRows];
                    while (slots.length < 5) slots.push(null);
                    return slots.slice(0, 5).map((r, i) => {
                      if (r == null) {
                        return <div key={i} style={chartBarEmpty} />;
                      }
                      const v = parseFloat(String(r.this_certificate_gross || 0)) || 0;
                      const pct = (v / max) * 100;
                      const isCurrent = r.id === iid;
                      return (
                        <div
                          key={r.id ?? i}
                          style={{
                            ...chartBar,
                            height: `${Math.max(4, pct)}%`,
                            background: isCurrent ? '#3b82f6' : '#dbeafe',
                          }}
                          title={`${r.ipc_number ?? `#${r.id}`} — ${formatCurrency(v)}`}
                        />
                      );
                    });
                  })()}
                </div>
                <div style={chartXLabel}>
                  <span>Start</span><span>Current</span><span>Future Est.</span>
                </div>
              </div>
            </div>
            <div style={{ ...panelLight, ...complianceBox }}>
              <div style={complianceIconBox}>
                <CheckCircle size={22} color="#2563eb" />
              </div>
              <h4 style={{ fontSize: 12, fontWeight: 700, color: '#1e293b', marginBottom: 4 }}>
                Financial Compliance Pass
              </h4>
              <p style={{ fontSize: 10, color: '#64748b', maxWidth: 220, lineHeight: 1.5, margin: 0 }}>
                {ipc.integrity_hash
                  ? 'Statutory calculations and integrity hash verified for current procurement rules.'
                  : 'Integrity hash will be computed once the IPC is certified.'}
              </p>
            </div>
          </div>

          {/* Footer nav */}
          <div style={footerRow}>
            <button
              onClick={() => navigate(`/contracts/${ipc.contract}`)}
              style={footerBackBtn}
            >
              <ArrowLeft size={14} /> Return to Contract Master
            </button>
            <p style={footerNote}>
              Interim Payment Certificate — Analytical Dashboard View
            </p>
          </div>
        </div>
      </div>

      {/* Reject modal */}
      <Modal
        title="Reject IPC"
        open={rejectOpen}
        onOk={async () => {
          try {
            await reject.mutateAsync({ id: iid, payload: { reason: rejectReason } });
            message.success('IPC rejected');
            setRejectOpen(false);
          } catch (e) {
            message.error(formatServiceError(e, 'Reject failed'));
          }
        }}
        onCancel={() => setRejectOpen(false)}
        confirmLoading={reject.isPending}
      >
        <Input.TextArea
          rows={4}
          placeholder="Reason for rejection (recorded in audit trail)"
          value={rejectReason}
          onChange={(e) => setRejectReason(e.target.value)}
        />
      </Modal>
    </ListPageShell>
  );
};

export default IPCDetail;


// ──────────────────────────────────────────────────────────────────────
// Sub-components
// ──────────────────────────────────────────────────────────────────────

interface MetaTileProps { label: string; value: string }
function MetaTile({ label, value }: MetaTileProps) {
  return (
    <div style={metaTile}>
      <span style={metaTileLabel}>{label}</span>
      <span style={metaTileValue}>{value}</span>
    </div>
  );
}

interface FieldStackProps { label: string; value: string }
function FieldStack({ label, value }: FieldStackProps) {
  return (
    <div>
      <span style={metaTileLabel}>{label}</span>
      <p style={fieldValue}>{value}</p>
    </div>
  );
}

interface StatCardProps {
  label: string;
  value: string;
  caption: string;
  accentBar: string;
  valueColor?: string;
  icon?: React.ReactNode;
}
function StatCard({ label, value, caption, accentBar, valueColor, icon }: StatCardProps) {
  return (
    <div style={{ ...panelLight, ...statBaseCard, borderLeft: `4px solid ${accentBar}` }}>
      <div style={{ padding: '1.25rem' }}>
        <div style={statTopRow}>
          <span style={statLabel}>{label}</span>
          {icon}
        </div>
        <div style={statValueRow}>
          <span style={statCurrencySymbol}>₦</span>
          <span style={{ ...statValue, color: valueColor ?? '#0f172a' }}>{value.replace(/^[^\d-]+/, '')}</span>
        </div>
        <div style={statCaption}>{caption}</div>
      </div>
    </div>
  );
}

interface StatCardDarkProps {
  label: string;
  value: string;
  caption: string;
  icon?: React.ReactNode;
}
function StatCardDark({ label, value, caption, icon }: StatCardDarkProps) {
  return (
    <div style={statDarkCard}>
      <div style={{ padding: '1.25rem' }}>
        <div style={statTopRow}>
          <span style={{ ...statLabel, color: 'rgba(191, 219, 254, 0.6)' }}>{label}</span>
          {icon}
        </div>
        <div style={{ ...statValueRow, color: '#fff' }}>
          <span style={{ ...statCurrencySymbol, opacity: 0.7 }}>₦</span>
          <span style={{ ...statValue, color: '#fff' }}>{value.replace(/^[^\d-]+/, '')}</span>
        </div>
        <div style={{ ...statCaption, color: 'rgba(191, 219, 254, 0.8)', fontStyle: 'italic' }}>
          {caption}
        </div>
      </div>
    </div>
  );
}


interface GLLedgerCardProps {
  ipc: any;
  journal: any;
  contract: any;
  formatCurrency: (n: number) => string;
}
function GLLedgerCard({ ipc, journal, contract, formatCurrency }: GLLedgerCardProps) {
  // Build the rows. Two modes:
  //   • Posted: read journal.lines directly — what the GL actually has.
  //   • Unposted: synthesise the *projected* DR/CR lines from the IPC
  //     deductions so the user sees what WILL post on Approve.
  const isPosted = !!journal && Array.isArray(journal.lines) && journal.lines.length > 0;

  const posted = isPosted ? journal.lines : [];
  const projected = useMemo(() => {
    if (isPosted) return [];
    const gross = Number(ipc.this_certificate_gross || 0);
    const vat = Number(ipc.vat_amount || 0);
    const wht = Number(ipc.wht_amount || 0);
    const retention = Number(ipc.retention_deduction_this_cert || 0);
    const mob = Number(ipc.mobilization_recovery_this_cert || 0);
    const apCredit = Number(ipc.net_payable || (gross - retention - mob - wht + vat));
    const rows: Array<{
      account_code?: string;
      account_name: string;
      memo?: string;
      debit?: number;
      credit?: number;
      muted?: boolean;
    }> = [];
    if (gross > 0) {
      rows.push({
        // Use the contract's economic-segment code/name when available
        // — the same line that funded the contract is the one we
        // debit on certification. Falls back to a descriptive label
        // when the contract serializer hasn't surfaced it yet.
        account_code: contract?.ncoa_economic_code || '',
        account_name: contract?.ncoa_economic_name || 'Expense / Work-in-Progress',
        memo: 'Gross certified value for the period',
        debit: gross,
      });
    }
    if (vat > 0) {
      rows.push({
        account_code: contract?.input_tax_account_code || '',
        account_name: 'Input VAT (Recoverable)',
        memo: 'Statutory FIRS tax',
        debit: vat,
      });
    }
    if (mob > 0) {
      rows.push({
        account_name: 'Mobilization Advance Recovery',
        memo: 'Pro-rata recovery of advance',
        credit: mob,
      });
    }
    if (retention > 0) {
      rows.push({
        account_name: 'Retention Held',
        memo: 'Performance security holdback',
        credit: retention,
      });
    }
    if (wht > 0) {
      rows.push({
        account_code: contract?.withholding_account_code || '',
        account_name: 'Withholding Tax Payable',
        memo: 'Advance income tax (payment time)',
        credit: wht,
      });
    }
    rows.push({
      account_code: contract?.vendor_ap_code || '',
      account_name: (
        contract?.vendor_ap_name
          ? `${contract.vendor_ap_name}${contract.vendor_name ? ` — ${contract.vendor_name}` : ''}`
          : (contract?.vendor_name
              ? `Accounts Payable — ${contract.vendor_name}`
              : 'Accounts Payable')
      ),
      memo: 'Net amount due to contractor',
      credit: apCredit,
    });
    return rows;
  }, [ipc, contract, isPosted]);

  const rows = isPosted
    ? posted.map((l: any) => ({
        account_code: l.account_code,
        account_name: l.account_name || `Account #${l.account}`,
        memo: l.memo,
        debit: parseFloat(String(l.debit || 0)) || 0,
        credit: parseFloat(String(l.credit || 0)) || 0,
      }))
    : projected;

  const totalDr = rows.reduce((s: number, r: any) => s + Number(r.debit || 0), 0);
  const totalCr = rows.reduce((s: number, r: any) => s + Number(r.credit || 0), 0);
  // The "Final Net Payable to Contractor" must match the Net Payable
  // card (= what cash actually goes to the vendor). That's the AP
  // credit only — retention/WHT/mob-recovery are *deductions held
  // back*, not paid out. Source-of-truth precedence:
  //   1. ``ipc.net_payable`` (backend-computed, authoritative)
  //   2. AP-line credit from the journal rows (when net_payable is 0)
  //   3. ``totalCr - retention - wht - mob`` as a derivation fallback
  const apRowCredit = rows
    .filter((r: any) => /(account.*payable|^ap\b)/i.test(r.account_name || ''))
    .reduce((s: number, r: any) => s + Number(r.credit || 0), 0);
  const finalNetPayable =
    Number(ipc.net_payable || 0)
    || apRowCredit
    || Math.max(
        0,
        totalCr
          - Number(ipc.retention_deduction_this_cert || 0)
          - Number(ipc.wht_amount || 0)
          - Number(ipc.mobilization_recovery_this_cert || 0),
      );
  const balanced = Math.abs(totalDr - totalCr) < 0.01;

  return (
    <div style={panelLight}>
      <div style={ledgerHeader}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <ListChecks size={14} color="#64748b" />
          <h3 style={ledgerTitle}>GL Ledger</h3>
          <span style={isPosted ? postedPill : unpostedPill}>
            {isPosted ? 'POSTED' : 'PROJECTED'}
          </span>
          {journal?.document_number && (
            <span style={journalRef}>
              Journal: <strong>{journal.document_number}</strong>
            </span>
          )}
        </div>
        {!isPosted && (
          <span style={ledgerNote}>
            <AlertCircle size={12} /> These lines will post on Approve
          </span>
        )}
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table style={ledgerTable}>
          <thead>
            <tr style={ledgerHeadRow}>
              <th style={ledgerTh}>GL Code</th>
              <th style={ledgerTh}>Account</th>
              <th style={ledgerTh}>Memo</th>
              <th style={{ ...ledgerTh, textAlign: 'right' }}>Debit (₦)</th>
              <th style={{ ...ledgerTh, textAlign: 'right' }}>Credit (₦)</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={5} style={ledgerEmpty}>No lines to display.</td>
              </tr>
            ) : rows.map((r: any, i: number) => (
              <tr key={i} style={ledgerRow}>
                <td style={{
                  ...ledgerTd,
                  fontFamily: 'ui-monospace, "SF Mono", Consolas, monospace',
                  fontWeight: 700, color: r.account_code ? '#1e40af' : '#cbd5e1',
                  fontSize: 11.5, letterSpacing: 0,
                }}>
                  {r.account_code || (
                    <span title="GL code resolves on Approve when the accrual journal posts" style={{ fontStyle: 'italic' }}>
                      pending
                    </span>
                  )}
                </td>
                <td style={{ ...ledgerTd, fontWeight: 600, color: '#0f172a' }}>{r.account_name}</td>
                <td style={{ ...ledgerTd, color: '#64748b', fontSize: 11.5 }}>{r.memo || '—'}</td>
                <td style={{
                  ...ledgerTd, textAlign: 'right',
                  fontFamily: 'ui-monospace, "SF Mono", Consolas, monospace',
                  fontWeight: 700,
                  fontVariantNumeric: 'tabular-nums',
                  color: r.debit ? '#0f172a' : '#e2e8f0',
                }}>
                  {r.debit ? formatCurrency(r.debit) : '—'}
                </td>
                <td style={{
                  ...ledgerTd, textAlign: 'right',
                  fontFamily: 'ui-monospace, "SF Mono", Consolas, monospace',
                  fontWeight: 700,
                  fontVariantNumeric: 'tabular-nums',
                  color: r.credit ? '#dc2626' : '#e2e8f0',
                }}>
                  {r.credit ? formatCurrency(r.credit) : '—'}
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            {/* Row 1 — journal balance (sanity check). Same colour
                treatment as the existing dark footer, just relabelled
                as totals + a Balanced/Unbalanced indicator. */}
            <tr style={ledgerFootRow}>
              <td
                style={{
                  ...ledgerTd, color: 'rgba(255,255,255,0.85)',
                  fontWeight: 700, fontSize: 10,
                  textTransform: 'uppercase', letterSpacing: '0.1em',
                }}
                colSpan={3}
              >
                Journal Total
                {balanced ? (
                  <span style={ledgerBalancedTag}>Balanced</span>
                ) : (
                  <span style={ledgerUnbalancedTag}>Out of Balance</span>
                )}
              </td>
              <td style={{ ...ledgerTd, textAlign: 'right', color: 'rgba(255,255,255,0.85)', fontFamily: 'monospace' }}>
                {formatCurrency(totalDr)}
              </td>
              <td style={{ ...ledgerTd, textAlign: 'right', color: 'rgba(255,255,255,0.85)', fontFamily: 'monospace' }}>
                {formatCurrency(totalCr)}
              </td>
            </tr>
            {/* Row 2 — the actual cash-to-contractor figure. This MUST
                equal the ``Net Payable`` stat card (both come from
                ``ipc.net_payable`` when present), so an auditor can
                cross-reference at a glance. Retention / WHT / mob
                recovery are credits in the journal but *held back*
                from the contractor — not part of this number. */}
            <tr style={{ ...ledgerFootRow, borderTop: '1px solid rgba(255,255,255,0.15)' }}>
              <td
                style={{
                  ...ledgerTd, color: '#fff',
                  fontWeight: 800, fontSize: 11,
                  textTransform: 'uppercase', letterSpacing: '0.1em',
                }}
                colSpan={4}
              >
                Final Net Payable to Contractor
                <span style={ledgerNetSubLabel}>
                  (after retention / mobilisation recovery / WHT)
                </span>
              </td>
              <td style={{
                ...ledgerTd, textAlign: 'right',
                color: '#fff', fontFamily: 'monospace',
                fontSize: 16, fontWeight: 900,
              }}>
                {formatCurrency(finalNetPayable)}
              </td>
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  );
}


// ──────────────────────────────────────────────────────────────────────
// Styles
// ──────────────────────────────────────────────────────────────────────
const topHeader: React.CSSProperties = {
  background: 'linear-gradient(180deg, #0f172a 0%, #1e293b 100%)',
  color: '#fff',
  borderRadius: '12px 12px 0 0',
  marginBottom: '1.5rem',
};
const topHeaderInner: React.CSSProperties = {
  display: 'flex', alignItems: 'center', gap: '1rem',
  padding: '0.85rem 1.25rem',
};
const backBtn: React.CSSProperties = {
  width: 32, height: 32, borderRadius: 8,
  background: 'rgba(255,255,255,0.06)',
  border: '1px solid rgba(255,255,255,0.08)', color: '#fff',
  display: 'flex', alignItems: 'center', justifyContent: 'center',
  cursor: 'pointer',
};
const topBreadcrumb: React.CSSProperties = {
  fontSize: 10, fontWeight: 700, color: '#3b82f6',
  textTransform: 'uppercase', letterSpacing: '0.08em',
};
const topTitle: React.CSSProperties = {
  fontSize: 17, fontWeight: 700, color: '#fff', margin: '2px 0 0',
  lineHeight: 1.25, letterSpacing: '-0.01em',
};
const topBtnGhost: React.CSSProperties = {
  display: 'inline-flex', alignItems: 'center', gap: 6,
  padding: '6px 12px',
  background: 'rgba(255,255,255,0.06)', color: '#fff',
  border: '1px solid rgba(255,255,255,0.08)', borderRadius: 6,
  fontSize: 11, fontWeight: 700, cursor: 'pointer',
};
const topBtnDanger: React.CSSProperties = {
  padding: '6px 18px',
  background: '#dc2626', color: '#fff',
  border: 'none', borderRadius: 6,
  fontSize: 11, fontWeight: 700, cursor: 'pointer',
  boxShadow: '0 2px 6px rgba(220, 38, 38, 0.3)',
};
const topBtnPrimary: React.CSSProperties = {
  padding: '6px 22px',
  background: '#3b82f6', color: '#fff',
  border: 'none', borderRadius: 6,
  fontSize: 11, fontWeight: 700, cursor: 'pointer',
  boxShadow: '0 4px 12px rgba(59, 130, 246, 0.4)',
};

const bodyGrid: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: '280px minmax(0, 1fr)',
  gap: '1.5rem',
};
const leftCol: React.CSSProperties = {
  display: 'flex', flexDirection: 'column', gap: '1.5rem',
};
const mainCol: React.CSSProperties = {
  display: 'flex', flexDirection: 'column', gap: '1.5rem',
};

// Panels
const panelLight: React.CSSProperties = {
  background: '#fff',
  border: '1px solid #e2e8f0',
  borderRadius: 8,
  boxShadow: '0 1px 2px rgba(15, 23, 42, 0.04)',
  overflow: 'hidden',
};
const panelDark: React.CSSProperties = {
  background: '#0f172a',
  border: '1px solid #1e293b',
  borderRadius: 8,
  boxShadow: '0 8px 20px -8px rgba(15, 23, 42, 0.5)',
  overflow: 'hidden',
  color: '#fff',
};
const panelHeaderRow: React.CSSProperties = {
  padding: '0.65rem 1rem',
  borderBottom: '1px solid #f1f5f9',
  background: 'rgba(248, 250, 252, 0.5)',
  display: 'flex', alignItems: 'center', gap: 6,
};
const panelHeader: React.CSSProperties = {
  fontSize: 11, fontWeight: 800,
  color: '#64748b',
  textTransform: 'uppercase', letterSpacing: '0.1em',
  margin: 0,
};
const statusPillBase: React.CSSProperties = {
  fontSize: 9, fontWeight: 800,
  padding: '2px 8px', borderRadius: 4,
  border: '1px solid currentColor',
};

// Meta tiles
const metaTile: React.CSSProperties = {
  background: '#f8fafc',
  border: '1px solid #f1f5f9',
  borderRadius: 6,
  padding: '0.65rem 0.75rem',
  display: 'flex', flexDirection: 'column', gap: 4,
};
const metaTileLabel: React.CSSProperties = {
  fontSize: 9, fontWeight: 700, color: '#94a3b8',
  textTransform: 'uppercase', letterSpacing: '0.05em',
};
const metaTileValue: React.CSSProperties = {
  fontSize: 12, fontWeight: 700, color: '#1e293b',
};
const fieldValue: React.CSSProperties = {
  fontSize: 12, fontWeight: 600, color: '#1e293b',
  margin: '4px 0 0', lineHeight: 1.3,
};
const progressLabelRow: React.CSSProperties = {
  display: 'flex', justifyContent: 'space-between',
  fontSize: 10, marginBottom: 4,
};
const progressTrack: React.CSSProperties = {
  width: '100%', height: 6, borderRadius: 999,
  background: '#f1f5f9', overflow: 'hidden',
};
const progressFill: React.CSSProperties = {
  height: '100%', background: '#3b82f6',
  transition: 'width 0.4s ease',
};

// Audit trail (dark)
const hashCard: React.CSSProperties = {
  padding: '0.5rem',
  background: 'rgba(0,0,0,0.4)',
  border: '1px solid rgba(255,255,255,0.08)',
  borderRadius: 4,
  display: 'flex', flexDirection: 'column', gap: 4,
};
const hashCaption: React.CSSProperties = {
  fontSize: 8, fontWeight: 700,
  color: 'rgba(52, 211, 153, 0.7)',
  textTransform: 'uppercase',
};
const hashCode: React.CSSProperties = {
  fontSize: 9, fontFamily: 'monospace',
  wordBreak: 'break-all',
  color: 'rgba(52, 211, 153, 0.9)',
  lineHeight: 1.3,
};
const shieldDot: React.CSSProperties = {
  width: 8, height: 8, borderRadius: '50%',
  background: '#10b981',
  animation: 'pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
};

// Stat cards
const statRow: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
  gap: '1rem',
};
const statBaseCard: React.CSSProperties = {
  borderRadius: 8,
};
const statDarkCard: React.CSSProperties = {
  background: 'linear-gradient(135deg, #1e3a8a 0%, #1e40af 100%)',
  border: '1px solid #1e293b',
  borderRadius: 8,
  boxShadow: '0 8px 20px -8px rgba(30, 64, 175, 0.4)',
  overflow: 'hidden',
};
const statTopRow: React.CSSProperties = {
  display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start',
  marginBottom: 8,
};
const statLabel: React.CSSProperties = {
  fontSize: 10, fontWeight: 800,
  color: '#94a3b8',
  textTransform: 'uppercase', letterSpacing: '0.05em',
};
const statValueRow: React.CSSProperties = {
  display: 'flex', alignItems: 'baseline', gap: 4,
};
const statCurrencySymbol: React.CSSProperties = {
  fontSize: 11, fontWeight: 700, color: '#94a3b8',
};
const statValue: React.CSSProperties = {
  fontSize: 26, fontWeight: 800,
  color: '#0f172a', letterSpacing: '-0.03em',
  fontVariantNumeric: 'tabular-nums',
};
const statCaption: React.CSSProperties = {
  marginTop: 6,
  fontSize: 11, fontWeight: 500, color: '#64748b',
  letterSpacing: '-0.005em',
};

// GL Ledger
const ledgerHeader: React.CSSProperties = {
  padding: '1rem 1.25rem',
  borderBottom: '1px solid #f1f5f9',
  display: 'flex', justifyContent: 'space-between',
  alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem',
};
const ledgerTitle: React.CSSProperties = {
  fontSize: 12, fontWeight: 800, color: '#334155',
  textTransform: 'uppercase', letterSpacing: '0.1em',
  margin: 0,
};
const postedPill: React.CSSProperties = {
  padding: '2px 8px', borderRadius: 4,
  fontSize: 9, fontWeight: 800,
  background: '#dcfce7', color: '#15803d',
};
const unpostedPill: React.CSSProperties = {
  padding: '2px 8px', borderRadius: 4,
  fontSize: 9, fontWeight: 800,
  background: '#fef3c7', color: '#a16207',
};
const journalRef: React.CSSProperties = {
  fontSize: 11, color: '#64748b', marginLeft: 8,
};
const ledgerNote: React.CSSProperties = {
  display: 'inline-flex', alignItems: 'center', gap: 4,
  fontSize: 11, color: '#a16207', fontStyle: 'italic',
};
const ledgerTable: React.CSSProperties = {
  width: '100%', borderCollapse: 'collapse',
};
const ledgerHeadRow: React.CSSProperties = {
  background: '#f8fafc', borderBottom: '1px solid #f1f5f9',
};
const ledgerTh: React.CSSProperties = {
  padding: '0.75rem 1.25rem', textAlign: 'left',
  fontSize: 10, fontWeight: 800, color: '#94a3b8',
  textTransform: 'uppercase', letterSpacing: '0.05em',
};
const ledgerRow: React.CSSProperties = {
  borderBottom: '1px solid #f1f5f9',
};
const ledgerTd: React.CSSProperties = {
  padding: '0.85rem 1.25rem', fontSize: 12.5, verticalAlign: 'middle',
  letterSpacing: '-0.005em',
};
const ledgerEmpty: React.CSSProperties = {
  padding: '2rem', textAlign: 'center', color: '#94a3b8',
};
const ledgerFootRow: React.CSSProperties = {
  background: '#1e293b',
};
const ledgerBalancedTag: React.CSSProperties = {
  marginLeft: 10,
  padding: '2px 8px', borderRadius: 4,
  fontSize: 9, fontWeight: 800,
  background: 'rgba(16, 185, 129, 0.20)',
  color: '#34d399',
  border: '1px solid rgba(52, 211, 153, 0.35)',
  letterSpacing: '0.05em',
};
const ledgerUnbalancedTag: React.CSSProperties = {
  marginLeft: 10,
  padding: '2px 8px', borderRadius: 4,
  fontSize: 9, fontWeight: 800,
  background: 'rgba(239, 68, 68, 0.20)',
  color: '#fca5a5',
  border: '1px solid rgba(252, 165, 165, 0.35)',
  letterSpacing: '0.05em',
};
const ledgerNetSubLabel: React.CSSProperties = {
  marginLeft: 8,
  fontSize: 9, fontWeight: 500,
  color: 'rgba(255,255,255,0.55)',
  textTransform: 'none',
  letterSpacing: 'normal',
  fontStyle: 'italic',
};

// Bottom row
const bottomRow: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
  gap: '1.5rem',
};
const chartHeader: React.CSSProperties = {
  fontSize: 10, fontWeight: 800, color: '#94a3b8',
  textTransform: 'uppercase', letterSpacing: '0.1em',
  marginBottom: 16,
};
const chartArea: React.CSSProperties = {
  height: 128,
  display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between',
  padding: '0 0.5rem', gap: 8,
};
const chartBar: React.CSSProperties = {
  width: '100%',
  borderRadius: '4px 4px 0 0',
  transition: 'height 0.4s ease',
};
const chartBarEmpty: React.CSSProperties = {
  width: '100%',
  height: '5%',
  background: '#f8fafc',
  borderRadius: '4px 4px 0 0',
  borderTop: '1px solid #e2e8f0',
};
const chartXLabel: React.CSSProperties = {
  display: 'flex', justifyContent: 'space-between',
  marginTop: 8,
  fontSize: 9, fontWeight: 700, color: '#94a3b8',
  textTransform: 'uppercase', padding: '0 4px',
};
const complianceBox: React.CSSProperties = {
  display: 'flex', flexDirection: 'column', alignItems: 'center',
  justifyContent: 'center', textAlign: 'center', padding: '1.5rem',
};
const complianceIconBox: React.CSSProperties = {
  width: 48, height: 48, borderRadius: '50%',
  background: '#dbeafe',
  display: 'flex', alignItems: 'center', justifyContent: 'center',
  marginBottom: 12,
};

// Footer
const footerRow: React.CSSProperties = {
  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
  padding: '1rem 0',
  borderTop: '1px solid #e2e8f0',
};
const footerBackBtn: React.CSSProperties = {
  display: 'inline-flex', alignItems: 'center', gap: 6,
  fontSize: 12, fontWeight: 700, color: '#64748b',
  background: 'none', border: 'none', cursor: 'pointer',
};
const footerNote: React.CSSProperties = {
  fontSize: 10, color: '#94a3b8', fontWeight: 500, margin: 0,
};

const whtToggleBtn = (exempt: boolean): React.CSSProperties => ({
  width: '100%',
  padding: '0.5rem',
  borderRadius: 6,
  fontSize: 11, fontWeight: 700,
  background: exempt ? '#fff' : '#fef3c7',
  color: exempt ? '#1d4ed8' : '#a16207',
  border: `1px solid ${exempt ? '#dbeafe' : '#fde68a'}`,
  cursor: 'pointer',
});
