import { useQuery } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { portalError, supplierApi } from './api';
import { BankTab, InvoicesTab, OrdersTab, OverviewTab, PaymentsTab } from './SupplierTabs';
import './supplier-portal.css';

const TABS = [
  { key: 'overview', label: 'Overview' },
  { key: 'orders', label: 'Orders' },
  { key: 'invoices', label: 'Invoices' },
  { key: 'payments', label: 'Payments' },
  { key: 'bank', label: 'Bank details' },
] as const;
type TabKey = (typeof TABS)[number]['key'];

/**
 * The supplier portal: a supplier checks its registration, acknowledges purchase orders, follows invoices and payments,
 * and asks to change where it is paid. It stands alone (no staff menus): a supplier account can reach nothing else.
 */
export default function SupplierPortal() {
  const { logout } = useAuth();
  const [params, setParams] = useSearchParams();
  const requested = params.get('tab') as TabKey | null;
  const tab: TabKey = TABS.some((t) => t.key === requested) ? (requested as TabKey) : 'overview';
  const profile = useQuery({ queryKey: ['supplier', 'profile'], queryFn: supplierApi.profile, retry: false });

  return (
    <div className="sp">
      <header className="sp-top">
        <div className="sp-top-inner">
          <div className="sp-bar">
            <div>
              <p className="sp-eyebrow">Supplier portal</p>
              <h1 className="sp-name" data-testid="sp-name">{profile.data?.name ?? 'Your account'}</h1>
              {profile.data && <p className="sp-code">Supplier code {profile.data.code}</p>}
            </div>
            <button type="button" className="sp-signout" onClick={() => logout()}>Sign out</button>
          </div>
          <div className="sp-tabs" role="tablist" aria-label="Supplier portal sections">
            {TABS.map((t) => (
              <button key={t.key} type="button" role="tab" className="sp-tab" aria-selected={t.key === tab} data-testid={`sp-tab-${t.key}`}
                onClick={() => setParams(t.key === 'overview' ? {} : { tab: t.key })}>{t.label}</button>
            ))}
          </div>
        </div>
      </header>

      <main className="sp-main" id="main-content">
        {profile.isLoading && <p className="sp-sub" aria-busy="true">Loading your account…</p>}
        {profile.isError && (
          <div className="sp-alert bad" role="alert" data-testid="sp-denied">
            {portalError(profile.error)} If you were invited recently, the procurement office may not have switched your access on yet.
          </div>
        )}
        {profile.data && (
          <>
            {tab === 'overview' && <OverviewTab profile={profile.data} />}
            {tab === 'orders' && <OrdersTab />}
            {tab === 'invoices' && <InvoicesTab />}
            {tab === 'payments' && <PaymentsTab />}
            {tab === 'bank' && <BankTab profile={profile.data} />}
          </>
        )}
      </main>
    </div>
  );
}
