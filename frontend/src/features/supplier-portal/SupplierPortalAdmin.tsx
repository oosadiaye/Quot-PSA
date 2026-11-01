import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { message } from 'antd';
import apiClient from '../../api/client';
import PageHeader from '../../components/PageHeader';
import { ListPageShell } from '../../components/layout';
import { formatDate } from '../../utils/date';
import { portalError } from './api';
import './supplier-portal.css';

interface PortalSettings { enabled: boolean; auto_activate_on_payment: boolean }
interface SupplierRow { id: number; name: string; code: string; email: string; is_active: boolean; portal_status: PortalStatus }
interface ChangeRow {
  id: number; vendor_name: string; vendor_code: string; current_bank_name: string; bank_name: string; bank_account_number: string;
  status: 'pending' | 'approved' | 'rejected'; reason: string; created_at: string;
}
type PortalStatus = 'not_invited' | 'invited' | 'active' | 'suspended';

const STATUS: Record<PortalStatus, { word: string; tone: string }> = {
  not_invited: { word: 'Not invited', tone: '' }, invited: { word: 'Invited', tone: 'warn' },
  active: { word: 'Active', tone: 'ok' }, suspended: { word: 'Suspended', tone: 'bad' },
};

const unwrap = <T,>(data: { results?: T[] } | T[]): T[] => (Array.isArray(data) ? data : data.results ?? []);

/**
 * The procurement office's side of the supplier portal: switch it on, choose how suppliers are let in, invite and
 * suspend suppliers, and decide the bank-detail changes suppliers ask for.
 */
export default function SupplierPortalAdmin() {
  const qc = useQueryClient();
  const refresh = () => { void qc.invalidateQueries({ queryKey: ['supplier-admin'] }); };
  const [search, setSearch] = useState('');
  const [rejecting, setRejecting] = useState<number | null>(null);
  const [reason, setReason] = useState('');
  const [error, setError] = useState<string | null>(null);

  const settings = useQuery({ queryKey: ['supplier-admin', 'settings'], queryFn: async (): Promise<PortalSettings> => (await apiClient.get('/procurement/portal-settings/current/')).data });
  const suppliers = useQuery({
    queryKey: ['supplier-admin', 'suppliers', search],
    queryFn: async () => unwrap<SupplierRow>((await apiClient.get('/procurement/vendors/', { params: { search, page_size: 50 } })).data),
  });
  const changes = useQuery({
    queryKey: ['supplier-admin', 'changes'],
    queryFn: async () => unwrap<ChangeRow>((await apiClient.get('/procurement/bank-change-requests/', { params: { page_size: 50 } })).data),
  });

  const saveSettings = useMutation({
    mutationFn: async (patch: Partial<PortalSettings>) => (await apiClient.patch('/procurement/portal-settings/current/', patch)).data,
    // Show the choice at once; the server's answer replaces it (or, on a refusal, puts the old value back).
    onMutate: (patch) => { qc.setQueryData<PortalSettings>(['supplier-admin', 'settings'], (old) => (old ? { ...old, ...patch } : old)); },
    onSuccess: () => { message.success('Portal settings saved'); refresh(); },
    onError: (e) => { setError(portalError(e)); refresh(); },
  });
  const act = useMutation({
    mutationFn: async ({ id, verb }: { id: number; verb: 'portal-invite' | 'portal-activate' | 'portal-suspend' }) =>
      (await apiClient.post(`/procurement/vendors/${id}/${verb}/`, {})).data,
    onSuccess: (_d, v) => {
      setError(null);
      message.success(v.verb === 'portal-invite' ? 'Invitation sent' : v.verb === 'portal-activate' ? 'Supplier is now active on the portal' : 'Supplier suspended');
      refresh();
    },
    onError: (e) => setError(portalError(e)),
  });
  const decide = useMutation({
    mutationFn: async ({ id, verb, why }: { id: number; verb: 'approve' | 'reject'; why?: string }) =>
      (await apiClient.post(`/procurement/bank-change-requests/${id}/${verb}/`, { reason: why ?? '' })).data,
    onSuccess: (_d, v) => { setError(null); setRejecting(null); setReason(''); message.success(v.verb === 'approve' ? 'Bank change approved' : 'Bank change rejected'); refresh(); },
    onError: (e) => setError(portalError(e)),
  });

  const enabled = settings.data?.enabled ?? false;
  const pending = (changes.data ?? []).filter((c) => c.status === 'pending');

  return (
    <ListPageShell>
      <PageHeader title="Supplier Portal" subtitle="Let suppliers see their orders and payments, and keep their own details, without a staff account." />
      <div className="sp spa" data-testid="spa">
        {error && <div className="sp-alert bad" role="alert" data-testid="spa-error">{error}</div>}

        <section className="sp-card" aria-labelledby="spa-settings">
          <h2 id="spa-settings">Portal settings</h2>
          <p className="sp-sub">The portal is off until you switch it on. Switching it off locks every supplier out at once; their records are kept.</p>
          <label className="spa-check"><input type="checkbox" data-testid="spa-enabled" checked={enabled} disabled={settings.isLoading || saveSettings.isPending}
            onChange={(e) => saveSettings.mutate({ enabled: e.target.checked })} /> Supplier portal is on</label>
          <label className="spa-check"><input type="checkbox" data-testid="spa-auto" checked={settings.data?.auto_activate_on_payment ?? false}
            disabled={settings.isLoading || saveSettings.isPending || !enabled}
            onChange={(e) => saveSettings.mutate({ auto_activate_on_payment: e.target.checked })} />
            Let a supplier in automatically when its registration payment is confirmed</label>
          {!enabled && <p className="sp-hint">Switch the portal on first to invite suppliers.</p>}
        </section>

        <section className="sp-card" aria-labelledby="spa-banks">
          <h2 id="spa-banks">Bank detail changes waiting for you ({pending.length})</h2>
          <p className="sp-sub">Approving changes where the supplier is paid. Check the account name with the supplier before you approve.</p>
          {pending.length === 0 ? <p className="sp-hint" data-testid="spa-no-changes">Nothing is waiting.</p> : (
            <div className="sp-table-wrap"><table className="sp-table" aria-label="Pending bank changes">
              <thead><tr><th scope="col">Supplier</th><th scope="col">Now</th><th scope="col">Asks for</th><th scope="col">Asked</th><th scope="col"><span className="sr-only">Decide</span></th></tr></thead>
              <tbody>{pending.map((c) => (
                <tr key={c.id} data-testid="spa-change">
                  <td><b>{c.vendor_name}</b><br /><span className="sp-hint">{c.vendor_code}</span></td>
                  <td>{c.current_bank_name || 'Not set'}</td>
                  <td>{c.bank_name}<br /><span className="sp-hint">{c.bank_account_number}</span></td>
                  <td>{formatDate(c.created_at)}</td>
                  <td>
                    {rejecting === c.id ? (
                      <div className="sp-field" style={{ minWidth: 220 }}>
                        <label htmlFor={`spa-why-${c.id}`}>Reason for rejecting</label>
                        <input id={`spa-why-${c.id}`} data-testid="spa-reason" value={reason} onChange={(e) => setReason(e.target.value)} />
                        <div className="sp-actions">
                          <button type="button" className="sp-btn primary" data-testid="spa-reject-confirm" disabled={!reason.trim() || decide.isPending}
                            onClick={() => decide.mutate({ id: c.id, verb: 'reject', why: reason })}>Reject</button>
                          <button type="button" className="sp-btn" onClick={() => { setRejecting(null); setReason(''); }}>Cancel</button>
                        </div>
                      </div>
                    ) : (
                      <div className="sp-actions" style={{ marginTop: 0 }}>
                        <button type="button" className="sp-btn primary" data-testid="spa-approve" disabled={decide.isPending} onClick={() => decide.mutate({ id: c.id, verb: 'approve' })}>Approve</button>
                        <button type="button" className="sp-btn" data-testid="spa-reject" onClick={() => { setRejecting(c.id); setReason(''); }}>Reject</button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}</tbody>
            </table></div>
          )}
        </section>

        <section className="sp-card" aria-labelledby="spa-suppliers">
          <h2 id="spa-suppliers">Suppliers</h2>
          <div className="sp-field" style={{ maxWidth: 360 }}>
            <label htmlFor="spa-search">Search suppliers</label>
            <input id="spa-search" type="search" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Name or code" />
          </div>
          {suppliers.isLoading ? <p className="sp-sub" aria-busy="true">Loading suppliers…</p> : (suppliers.data ?? []).length === 0 ? (
            <p className="sp-hint">No suppliers match.</p>
          ) : (
            <div className="sp-table-wrap"><table className="sp-table" aria-label="Suppliers and their portal access">
              <thead><tr><th scope="col">Supplier</th><th scope="col">Email</th><th scope="col">Portal</th><th scope="col"><span className="sr-only">Actions</span></th></tr></thead>
              <tbody>{(suppliers.data ?? []).map((s) => {
                const st = STATUS[s.portal_status] ?? STATUS.not_invited;
                const go = (verb: 'portal-invite' | 'portal-activate' | 'portal-suspend') => act.mutate({ id: s.id, verb });
                return (
                  <tr key={s.id} data-testid={`spa-supplier-${s.code}`}>
                    <td><b>{s.name}</b><br /><span className="sp-hint">{s.code}</span></td>
                    <td>{s.email || <span className="sp-hint">No email: add one to invite</span>}</td>
                    <td><span className={`sp-pill ${st.tone}`} data-testid={`spa-status-${s.code}`}>{st.word}</span></td>
                    <td><div className="sp-actions" style={{ marginTop: 0 }}>
                      {(s.portal_status === 'not_invited' || s.portal_status === 'invited') && (
                        <button type="button" className="sp-btn" data-testid={`spa-invite-${s.code}`} disabled={!enabled || !s.email || act.isPending} onClick={() => go('portal-invite')}>
                          {s.portal_status === 'invited' ? 'Send invitation again' : 'Invite'}</button>)}
                      {s.portal_status === 'invited' && <button type="button" className="sp-btn primary" data-testid={`spa-activate-${s.code}`} disabled={act.isPending} onClick={() => go('portal-activate')}>Let in</button>}
                      {s.portal_status === 'active' && <button type="button" className="sp-btn" data-testid={`spa-suspend-${s.code}`} disabled={act.isPending} onClick={() => go('portal-suspend')}>Suspend</button>}
                      {s.portal_status === 'suspended' && <button type="button" className="sp-btn primary" data-testid={`spa-reactivate-${s.code}`} disabled={act.isPending} onClick={() => go('portal-activate')}>Let back in</button>}
                    </div></td>
                  </tr>
                );
              })}</tbody>
            </table></div>
          )}
        </section>
      </div>
    </ListPageShell>
  );
}
