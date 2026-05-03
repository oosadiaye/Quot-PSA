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

  return (
    <PortalLayout>
      <PortalPageHeader
        title="My Profile"
        subtitle="Review your employment details and keep your emergency contact up to date"
        icon={<UserCircle size={20} color="#ffffff" />}
      />

      {isLoading && <div style={{ color: '#94a3b8' }}>Loading…</div>}
      {isError && <div style={{ color: '#b91c1c' }}>Could not load profile.</div>}

      {data && (
        <div style={{ display: 'grid', gridTemplateColumns: '1.1fr 1fr', gap: 18 }}>
          <Card title="Employment">
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
            <div style={{ marginTop: 12, padding: 10, background: '#f8fafc', borderRadius: 8, fontSize: 12, color: '#64748b' }}>
              To update your employment details or bank information, please contact your HR representative.
            </div>
          </Card>

          <Card title="Emergency Contact">
            <form onSubmit={save}>
              <Field label="Contact Name">
                <input
                  type="text"
                  value={patch.emergency_contact_name ?? ''}
                  onChange={(e) => setPatch({ ...patch, emergency_contact_name: e.target.value })}
                  style={inputStyle}
                />
              </Field>
              <Field label="Contact Phone">
                <input
                  type="tel"
                  value={patch.emergency_contact_phone ?? ''}
                  onChange={(e) => setPatch({ ...patch, emergency_contact_phone: e.target.value })}
                  style={inputStyle}
                />
              </Field>
              <Field label="Relationship">
                <input
                  type="text"
                  value={patch.emergency_contact_relation ?? ''}
                  onChange={(e) => setPatch({ ...patch, emergency_contact_relation: e.target.value })}
                  style={inputStyle}
                  placeholder="e.g. Spouse, Parent, Sibling"
                />
              </Field>
              <div style={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'center', gap: 12, marginTop: 10 }}>
                {saved && (
                  <span style={{ color: '#15803d', fontSize: 13, display: 'flex', alignItems: 'center', gap: 4 }}>
                    <Check size={14} /> Saved
                  </span>
                )}
                <button
                  type="submit"
                  disabled={mutation.isPending}
                  style={{
                    background: 'linear-gradient(135deg, #242a88, #2e35a0)',
                    color: '#ffffff',
                    border: 0,
                    padding: '9px 18px',
                    borderRadius: 8,
                    cursor: 'pointer',
                    fontSize: 13,
                    fontWeight: 600,
                    display: 'flex',
                    alignItems: 'center',
                    gap: 6,
                    opacity: mutation.isPending ? 0.6 : 1,
                  }}
                >
                  <Save size={14} />
                  {mutation.isPending ? 'Saving…' : 'Save Changes'}
                </button>
              </div>
            </form>
          </Card>
        </div>
      )}
    </PortalLayout>
  );
}

const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: '9px 11px',
  border: '1px solid #e2e8f0',
  borderRadius: 8,
  fontSize: 13,
  color: '#0f172a',
  outline: 'none',
  background: '#ffffff',
};

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section
      style={{
        background: '#ffffff',
        border: '1px solid #e2e8f0',
        borderRadius: 12,
        padding: 20,
      }}
    >
      <div
        style={{
          fontSize: 12,
          fontWeight: 700,
          textTransform: 'uppercase',
          letterSpacing: 0.6,
          color: '#64748b',
          marginBottom: 14,
        }}
      >
        {title}
      </div>
      {children}
    </section>
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

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label style={{ display: 'block', marginBottom: 12 }}>
      <div style={{ fontSize: 12, fontWeight: 600, color: '#475569', marginBottom: 5 }}>{label}</div>
      {children}
    </label>
  );
}
