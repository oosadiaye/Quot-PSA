import { useQuery } from '@tanstack/react-query';
import { LayoutDashboard, Wallet, CalendarDays, Clock, ArrowRight } from 'lucide-react';
import { Link } from 'react-router-dom';
import PortalLayout from '../PortalLayout';
import PortalPageHeader from '../components/PortalPageHeader';
import { portalApi } from '../api';

const formatNaira = (value: string | undefined) => {
  if (!value) return '—';
  const num = Number(value);
  if (Number.isNaN(num)) return value;
  return num.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
};

export default function MyDashboard() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['portal-dashboard'],
    queryFn: portalApi.getDashboard,
  });

  return (
    <PortalLayout>
      <PortalPageHeader
        title={data?.employee.full_name ? `Welcome, ${data.employee.full_name.split(' ')[0]}` : 'My Portal'}
        subtitle="Your payslips, leave, and profile at a glance"
        icon={<LayoutDashboard size={20} color="#ffffff" />}
      />

      {isLoading && <Card>Loading your dashboard…</Card>}
      {isError && <Card tone="error">Failed to load dashboard. Please try again.</Card>}

      {data && (
        <>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
              gap: 16,
              marginBottom: 24,
            }}
          >
            <Stat
              icon={<Wallet size={20} />}
              label="Latest Net Pay"
              value={data.latest_payslip ? formatNaira(data.latest_payslip.net_salary) : 'No payslips yet'}
              sub={data.latest_payslip?.period_label}
            />
            <Stat
              icon={<CalendarDays size={20} />}
              label="Leave Balance"
              value={String(
                data.leave_balances.reduce((acc, b) => acc + b.balance, 0)
              )}
              sub="Days available this year"
            />
            <Stat
              icon={<Clock size={20} />}
              label="Pending Requests"
              value={String(data.pending_leave_requests)}
              sub="Awaiting approval"
            />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 16 }}>
            <Card>
              <SectionTitle>Latest Payslip</SectionTitle>
              {data.latest_payslip ? (
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end' }}>
                    <div>
                      <div style={{ fontSize: 13, color: '#64748b' }}>{data.latest_payslip.period_label}</div>
                      <div style={{ fontSize: 26, fontWeight: 700, color: '#0f172a', marginTop: 4 }}>
                        ₦ {formatNaira(data.latest_payslip.net_salary)}
                      </div>
                      <div style={{ fontSize: 12, color: '#94a3b8', marginTop: 2 }}>
                        Paid on {new Date(data.latest_payslip.payment_date).toLocaleDateString()}
                      </div>
                    </div>
                    <Link
                      to="/portal/payslips"
                      style={{
                        color: '#242a88',
                        fontSize: 13,
                        fontWeight: 600,
                        textDecoration: 'none',
                        display: 'flex',
                        alignItems: 'center',
                        gap: 4,
                      }}
                    >
                      View all <ArrowRight size={14} />
                    </Link>
                  </div>
                  <HR />
                  <Row label="Gross salary" value={`₦ ${formatNaira(data.latest_payslip.gross_salary)}`} />
                  <Row label="Deductions" value={`₦ ${formatNaira(data.latest_payslip.total_deductions)}`} />
                </div>
              ) : (
                <div style={{ color: '#94a3b8', fontSize: 14 }}>
                  No payslip available yet. Your HR team will generate one after the next payroll run.
                </div>
              )}
            </Card>

            <Card>
              <SectionTitle>Leave Balances</SectionTitle>
              {data.leave_balances.length === 0 ? (
                <div style={{ color: '#94a3b8', fontSize: 14 }}>No balances configured.</div>
              ) : (
                data.leave_balances.map((b) => (
                  <Row key={b.id} label={b.leave_type} value={`${b.balance} / ${b.allocated}`} />
                ))
              )}
              {data.upcoming_leave && (
                <>
                  <HR />
                  <div style={{ fontSize: 12, color: '#64748b', marginBottom: 4 }}>UPCOMING LEAVE</div>
                  <div style={{ fontSize: 13, color: '#0f172a' }}>
                    {data.upcoming_leave.leave_type} · {new Date(data.upcoming_leave.start_date).toLocaleDateString()} –{' '}
                    {new Date(data.upcoming_leave.end_date).toLocaleDateString()}
                  </div>
                </>
              )}
            </Card>
          </div>
        </>
      )}
    </PortalLayout>
  );
}

function Card({ children, tone }: { children: React.ReactNode; tone?: 'error' }) {
  return (
    <div
      style={{
        background: '#ffffff',
        border: '1px solid #e2e8f0',
        borderRadius: 12,
        padding: 20,
        boxShadow: '0 1px 2px rgba(0,0,0,0.03)',
        color: tone === 'error' ? '#b91c1c' : '#0f172a',
      }}
    >
      {children}
    </div>
  );
}

function Stat({ icon, label, value, sub }: { icon: React.ReactNode; label: string; value: string; sub?: string }) {
  return (
    <Card>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, color: '#242a88', marginBottom: 10 }}>
        {icon}
        <span style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 0.6, color: '#64748b' }}>
          {label}
        </span>
      </div>
      <div style={{ fontSize: 22, fontWeight: 700, color: '#0f172a' }}>{value}</div>
      {sub && <div style={{ fontSize: 12, color: '#94a3b8', marginTop: 4 }}>{sub}</div>}
    </Card>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ fontSize: 12, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 0.6, color: '#64748b', marginBottom: 12 }}>
      {children}
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', fontSize: 13 }}>
      <span style={{ color: '#64748b' }}>{label}</span>
      <span style={{ color: '#0f172a', fontWeight: 600 }}>{value}</span>
    </div>
  );
}

function HR() {
  return <div style={{ height: 1, background: '#e2e8f0', margin: '14px 0' }} />;
}
