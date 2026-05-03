import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Wallet, Download, FileText } from 'lucide-react';
import PortalLayout from '../PortalLayout';
import PortalPageHeader from '../components/PortalPageHeader';
import { portalApi, type PortalPayslipLine } from '../api';

const formatMoney = (value: string) => {
  const num = Number(value);
  if (Number.isNaN(num)) return value;
  return num.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
};

export default function MyPayslips() {
  const [downloading, setDownloading] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const { data, isLoading, isError } = useQuery({
    queryKey: ['portal-payslips'],
    queryFn: portalApi.getPayslips,
  });

  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<PortalPayslipLine | null>(null);

  const openDetail = async (line: PortalPayslipLine) => {
    setSelectedId(line.id);
    setDetail(null);
    try {
      const d = await portalApi.getPayslip(line.id);
      setDetail(d);
    } catch {
      setError('Failed to load payslip details.');
    }
  };

  const download = async (line: PortalPayslipLine) => {
    setDownloading(line.id);
    setError(null);
    try {
      await portalApi.downloadPayslipPdf(
        line.id,
        `payslip-${line.period_label.replace(/\s+/g, '-')}.pdf`
      );
    } catch {
      setError('Could not download the PDF. Please try again.');
    } finally {
      setDownloading(null);
    }
  };

  return (
    <PortalLayout>
      <PortalPageHeader
        title="My Payslips"
        subtitle="View and download your monthly pay statements"
        icon={<Wallet size={20} color="#ffffff" />}
      />

      {error && (
        <div
          style={{
            background: '#fef2f2',
            border: '1px solid #fecaca',
            color: '#b91c1c',
            padding: '10px 14px',
            borderRadius: 10,
            fontSize: 13,
            marginBottom: 14,
          }}
        >
          {error}
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1.1fr 1fr', gap: 16 }}>
        <section
          style={{
            background: '#ffffff',
            borderRadius: 12,
            border: '1px solid #e2e8f0',
            overflow: 'hidden',
          }}
        >
          <header style={{ padding: '14px 18px', borderBottom: '1px solid #e2e8f0', fontSize: 13, fontWeight: 600, color: '#475569' }}>
            Payslip History
          </header>
          {isLoading && <div style={{ padding: 20, color: '#94a3b8' }}>Loading…</div>}
          {isError && <div style={{ padding: 20, color: '#b91c1c' }}>Failed to load payslips.</div>}
          {data?.results.length === 0 && (
            <div style={{ padding: 24, color: '#94a3b8', fontSize: 14 }}>
              No payslips yet. You'll see your slips here after payroll is approved.
            </div>
          )}
          <ul style={{ margin: 0, padding: 0, listStyle: 'none' }}>
            {data?.results.map((line) => (
              <li
                key={line.id}
                onClick={() => openDetail(line)}
                style={{
                  padding: '14px 18px',
                  borderBottom: '1px solid #f1f5f9',
                  cursor: 'pointer',
                  background: selectedId === line.id ? '#eef2ff' : 'transparent',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: 12,
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <div
                    style={{
                      width: 36,
                      height: 36,
                      borderRadius: 9,
                      background: '#eef2ff',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      color: '#242a88',
                    }}
                  >
                    <FileText size={17} />
                  </div>
                  <div>
                    <div style={{ fontSize: 14, fontWeight: 600, color: '#0f172a' }}>{line.period_label}</div>
                    <div style={{ fontSize: 12, color: '#64748b' }}>
                      Paid {new Date(line.payment_date).toLocaleDateString()} · Run {line.run_number}
                    </div>
                  </div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <div style={{ fontSize: 14, fontWeight: 700, color: '#0f172a' }}>
                    ₦ {formatMoney(line.net_salary)}
                  </div>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      download(line);
                    }}
                    disabled={downloading === line.id}
                    style={{
                      background: '#242a88',
                      color: '#ffffff',
                      border: 0,
                      padding: '6px 12px',
                      borderRadius: 7,
                      fontSize: 12,
                      fontWeight: 600,
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 5,
                      opacity: downloading === line.id ? 0.6 : 1,
                    }}
                  >
                    <Download size={13} />
                    {downloading === line.id ? 'Preparing…' : 'PDF'}
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </section>

        <aside
          style={{
            background: '#ffffff',
            borderRadius: 12,
            border: '1px solid #e2e8f0',
            padding: 20,
            alignSelf: 'start',
          }}
        >
          <header style={{ fontSize: 13, fontWeight: 600, color: '#475569', marginBottom: 14 }}>
            Payslip Details
          </header>
          {!selectedId && (
            <div style={{ color: '#94a3b8', fontSize: 13 }}>Select a payslip to view its breakdown.</div>
          )}
          {selectedId && !detail && <div style={{ color: '#94a3b8' }}>Loading…</div>}
          {detail && (
            <div>
              <div style={{ fontSize: 12, color: '#64748b' }}>{detail.period_label}</div>
              <div style={{ fontSize: 22, fontWeight: 700, color: '#0f172a', marginTop: 4, marginBottom: 18 }}>
                ₦ {formatMoney(detail.net_salary)}
              </div>
              <SubHeader>Earnings</SubHeader>
              <Row label="Basic salary" value={`₦ ${formatMoney(detail.basic_salary)}`} />
              {detail.earnings?.map((e) => (
                <Row key={e.name} label={e.name} value={`₦ ${formatMoney(e.amount)}`} />
              ))}
              <Row label="Gross" value={`₦ ${formatMoney(detail.gross_salary)}`} bold />

              <div style={{ height: 12 }} />
              <SubHeader>Deductions</SubHeader>
              <Row label="PAYE Tax" value={`₦ ${formatMoney(detail.tax_deduction || '0')}`} />
              <Row label="Pension" value={`₦ ${formatMoney(detail.pension_deduction || '0')}`} />
              {detail.deductions?.map((d) => (
                <Row key={d.name} label={d.name} value={`₦ ${formatMoney(d.amount)}`} />
              ))}
              <Row label="Total deductions" value={`₦ ${formatMoney(detail.total_deductions)}`} bold />
            </div>
          )}
        </aside>
      </div>
    </PortalLayout>
  );
}

function SubHeader({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: 0.6, color: '#242a88', textTransform: 'uppercase', marginBottom: 6 }}>
      {children}
    </div>
  );
}

function Row({ label, value, bold }: { label: string; value: string; bold?: boolean }) {
  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        padding: '5px 0',
        fontSize: 13,
        borderBottom: '1px dashed #f1f5f9',
      }}
    >
      <span style={{ color: '#475569' }}>{label}</span>
      <span style={{ color: '#0f172a', fontWeight: bold ? 700 : 500 }}>{value}</span>
    </div>
  );
}
