import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { UserCircle, Save, Check } from 'lucide-react';
import PortalLayout from '../PortalLayout';
import PortalPageHeader from '../components/PortalPageHeader';
import { portalApi, type ProfilePatch } from '../api';

export default function MyProfile() {
  const qc = useQueryClient();
  const { data, isLoading, isError } = useQuery({
    queryKey: ['portal-profile'],
    queryFn: portalApi.getProfile,
  });

  const [patch, setPatch] = useState<ProfilePatch>({});
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (data) {
      setPatch({
        emergency_contact_name: data.emergency_contact_name,
        emergency_contact_phone: data.emergency_contact_phone,
        emergency_contact_relation: data.emergency_contact_relation,
      });
    }
  }, [data]);

  const mutation = useMutation({
    mutationFn: portalApi.updateProfile,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['portal-profile'] });
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    },
  });

  const save = (e: React.FormEvent) => {
    e.preventDefault();
    mutation.mutate(patch);
  };

  const labelStyle: React.CSSProperties = {
    display: 'block', marginBottom: '0.5rem', fontSize: 'var(--text-xs)',
    fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)',
  };
  const helpStyle: React.CSSProperties = {
    fontSize: '11px', color: 'var(--color-text-muted)', marginTop: '4px',
  };

  return (
    <PortalLayout>
      <PortalPageHeader
        title="My Profile"
        subtitle="Review your employment details and keep your emergency contact up to date"
        icon={<UserCircle size={20} color="#ffffff" />}
        actions={
          data ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
              {saved && (
                <span style={{ color: '#ffffff', fontSize: 13, display: 'flex', alignItems: 'center', gap: 4 }}>
                  <Check size={14} /> Saved
                </span>
              )}
              <button type="submit" form="profile-form" className="btn btn-primary" disabled={mutation.isPending}>
                <Save size={16} /> {mutation.isPending ? 'Saving…' : 'Save Changes'}
              </button>
            </div>
          ) : undefined
        }
      />

      {isLoading && <div style={{ color: '#94a3b8' }}>Loading…</div>}
      {isError && <div style={{ color: '#b91c1c' }}>Could not load profile.</div>}

      {data && (
        <>
          {/* ── Employment (read-only) ───────────────────── */}
          <div className="card" style={{ marginBottom: '1.5rem' }}>
            <h3 style={{ marginBottom: '1.5rem' }}>Employment</h3>
            <Row label="Full Name" value={data.full_name} />
            <Row label="Employee Number" value={data.employee_number} />
            <Row label="Email" value={data.email} />
            <Row label="Department" value={data.department || '—'} />
            <Row label="Position" value={data.position || '—'} />
            <Row label="Type" value={data.employee_type} />
            <Row label="Status" value={data.status} />
            <Row label="Hire Date" value={new Date(data.hire_date).toLocaleDateString()} />
            {data.confirmation_date && (
              <Row label="Confirmed" value={new Date(data.confirmation_date).toLocaleDateString()} />
            )}
            <Row label="Bank" value={data.bank_name || '—'} />
            <Row
              label="Account"
              value={data.bank_account_last4 ? `****${data.bank_account_last4}` : '—'}
            />
            <p style={{ ...helpStyle, marginTop: '1rem' }}>
              To update your employment details or bank information, please contact your HR representative.
            </p>
          </div>

          {/* ── Emergency Contact ────────────────────────── */}
          <div className="card" style={{ marginBottom: '1.5rem' }}>
            <h3 style={{ marginBottom: '1.5rem' }}>Emergency Contact</h3>
            <form id="profile-form" onSubmit={save}>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '1.5rem' }}>
                <div>
                  <label style={labelStyle}>Contact Name</label>
                  <input
                    type="text"
                    className="input"
                    value={patch.emergency_contact_name ?? ''}
                    onChange={(e) => setPatch({ ...patch, emergency_contact_name: e.target.value })}
                  />
                </div>
                <div>
                  <label style={labelStyle}>Contact Phone</label>
                  <input
                    type="tel"
                    className="input"
                    value={patch.emergency_contact_phone ?? ''}
                    onChange={(e) => setPatch({ ...patch, emergency_contact_phone: e.target.value })}
                  />
                </div>
                <div>
                  <label style={labelStyle}>Relationship</label>
                  <input
                    type="text"
                    className="input"
                    value={patch.emergency_contact_relation ?? ''}
                    onChange={(e) => setPatch({ ...patch, emergency_contact_relation: e.target.value })}
                    placeholder="e.g. Spouse, Parent, Sibling"
                  />
                  <p style={helpStyle}>Who we should contact in case of an emergency.</p>
                </div>
              </div>
            </form>
          </div>
        </>
      )}
    </PortalLayout>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        padding: '7px 0',
        borderBottom: '1px dashed #f1f5f9',
        fontSize: 13,
      }}
    >
      <span style={{ color: '#64748b' }}>{label}</span>
      <span style={{ color: '#0f172a', fontWeight: 600 }}>{value}</span>
    </div>
  );
}
