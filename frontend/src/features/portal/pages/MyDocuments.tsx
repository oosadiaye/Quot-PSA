import { useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  FolderOpen,
  Upload,
  Trash2,
  FileText,
  ShieldCheck,
  ShieldAlert,
  AlertTriangle,
  Check,
} from 'lucide-react';
import PortalLayout from '../PortalLayout';
import PortalPageHeader from '../components/PortalPageHeader';
import {
  portalApi,
  type DocumentCategory,
  type PortalDocument,
  type PortalVerificationSubmission,
} from '../api';

const CATEGORIES: Array<{ value: DocumentCategory; label: string }> = [
  { value: 'national_id', label: 'National ID Card' },
  { value: 'passport', label: 'International Passport' },
  { value: 'drivers_license', label: "Driver's License" },
  { value: 'nin_proof', label: 'NIN Slip / Proof' },
  { value: 'bvn_proof', label: 'BVN Proof' },
  { value: 'academic_certificate', label: 'Academic Certificate' },
  { value: 'professional_cert', label: 'Professional Certificate' },
  { value: 'appointment_letter', label: 'Letter of Appointment' },
  { value: 'confirmation_letter', label: 'Letter of Confirmation' },
  { value: 'pension_letter', label: 'Pension PIN Letter' },
  { value: 'marriage_certificate', label: 'Marriage Certificate' },
  { value: 'birth_certificate', label: 'Birth Certificate' },
  { value: 'medical_report', label: 'Medical Report' },
  { value: 'other', label: 'Other' },
];

const STATUS_STYLES: Record<
  PortalDocument['status'],
  { bg: string; fg: string; label: string }
> = {
  uploaded: { bg: '#eff6ff', fg: '#1d4ed8', label: 'Uploaded' },
  verified: { bg: '#f0fdf4', fg: '#15803d', label: 'Verified' },
  rejected: { bg: '#fef2f2', fg: '#b91c1c', label: 'Rejected' },
};

const formatBytes = (bytes: number): string => {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};

const daysUntil = (iso: string): number => {
  const target = new Date(iso).getTime();
  const now = Date.now();
  return Math.ceil((target - now) / (1000 * 60 * 60 * 24));
};

export default function MyDocuments() {
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [category, setCategory] = useState<DocumentCategory>('national_id');
  const [title, setTitle] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [confirmAccurate, setConfirmAccurate] = useState(false);
  const [attestNotes, setAttestNotes] = useState('');

  const documentsQuery = useQuery({
    queryKey: ['portal-documents'],
    queryFn: portalApi.getDocuments,
  });

  const cyclesQuery = useQuery({
    queryKey: ['portal-verification-cycles'],
    queryFn: portalApi.getVerificationCycles,
  });

  const uploadMutation = useMutation({
    mutationFn: portalApi.uploadDocument,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['portal-documents'] });
      setTitle('');
      if (fileRef.current) fileRef.current.value = '';
    },
    onError: (err: unknown) => {
      const message = err instanceof Error ? err.message : 'Upload failed';
      setError(message);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: portalApi.deleteDocument,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['portal-documents'] }),
  });

  const submitMutation = useMutation({
    mutationFn: ({ cycleId, documentIds }: { cycleId: number; documentIds: number[] }) =>
      portalApi.submitVerification(cycleId, {
        attestation: { confirm_accurate: true, notes: attestNotes },
        document_ids: documentIds,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['portal-verification-cycles'] });
      setConfirmAccurate(false);
      setAttestNotes('');
    },
  });

  const handleUpload = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    const file = fileRef.current?.files?.[0];
    if (!file) {
      setError('Please pick a file to upload.');
      return;
    }
    uploadMutation.mutate({ file, category, title: title || undefined });
  };

  const documents = documentsQuery.data?.results ?? [];
  const pendingSubmission = (cyclesQuery.data?.results ?? []).find(
    (s) => s.status === 'pending',
  );

  const labelStyle: React.CSSProperties = { display:'block', marginBottom:'0.5rem', fontSize:'var(--text-xs)', fontWeight:600, textTransform:'uppercase', color:'var(--color-text-muted)' };
  const helpStyle: React.CSSProperties = { fontSize:'11px', color:'var(--color-text-muted)', marginTop:'4px' };

  return (
    <PortalLayout>
      <PortalPageHeader
        title="My Documents"
        subtitle="Upload and manage your personnel documents, and respond to verification cycles"
        icon={<FolderOpen size={22} color="#ffffff" />}
        actions={
          <button
            type="submit"
            form="document-upload-form"
            disabled={uploadMutation.isPending}
            className="btn btn-outline"
            style={{ background: 'rgba(255,255,255,0.16)', color: '#ffffff', borderColor: 'rgba(255,255,255,0.3)' }}
          >
            <Upload size={18} /> {uploadMutation.isPending ? 'Uploading…' : 'Upload Document'}
          </button>
        }
      />

      {pendingSubmission && (
        <VerificationBanner
          submission={pendingSubmission}
          documents={documents}
          confirmAccurate={confirmAccurate}
          onConfirm={setConfirmAccurate}
          notes={attestNotes}
          onNotesChange={setAttestNotes}
          onSubmit={(ids) =>
            submitMutation.mutate({ cycleId: pendingSubmission.cycle.id, documentIds: ids })
          }
          isSubmitting={submitMutation.isPending}
          error={submitMutation.error instanceof Error ? submitMutation.error.message : null}
        />
      )}

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

      <div className="card" style={{ marginBottom: '1.5rem' }}>
        <h3 style={{ marginBottom: '1.5rem' }}>Upload Document</h3>
        <form id="document-upload-form" onSubmit={handleUpload}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '1.5rem' }}>
            <div>
              <label style={labelStyle}>Category<span className="required-mark"> *</span></label>
              <select
                className="input"
                value={category}
                onChange={(e) => setCategory(e.target.value as DocumentCategory)}
              >
                {CATEGORIES.map((c) => (
                  <option key={c.value} value={c.value}>
                    {c.label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label style={labelStyle}>Title</label>
              <input
                type="text"
                className="input"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="e.g. BSc Certificate (UNILAG, 2014)"
              />
              <p style={helpStyle}>Optional — a short label to help you identify this document.</p>
            </div>
          </div>
          <div style={{ marginTop: '1.5rem' }}>
            <label style={labelStyle}>File<span className="required-mark"> *</span></label>
            <input
              ref={fileRef}
              type="file"
              className="input"
              accept=".pdf,.jpg,.jpeg,.png,.heic,.doc,.docx,application/pdf,image/*"
            />
            <p style={helpStyle}>PDF, image, or Word — max 10 MB.</p>
          </div>
        </form>
        <div
          style={{
            marginTop: 16,
            padding: 12,
            background: '#f8fafc',
            borderRadius: 8,
            fontSize: 12,
            color: '#64748b',
            lineHeight: 1.5,
          }}
        >
          Only you and HR reviewers can see your documents. Verified documents can't be
          deleted — contact HR if a correction is needed.
        </div>
      </div>

      <div className="card" style={{ marginBottom: '1.5rem' }}>
        <h3
          style={{
            marginBottom: '1.5rem',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'baseline',
          }}
        >
          <span>Your Documents</span>
          <span style={{ color: '#94a3b8', fontWeight: 500, fontSize: 13 }}>
            {documents.length} on file
          </span>
        </h3>
        <div style={{ border: '1px solid #e2e8f0', borderRadius: 12, overflow: 'hidden' }}>
          {documentsQuery.isLoading && (
            <div style={{ padding: 24, color: '#94a3b8' }}>Loading…</div>
          )}
          {!documentsQuery.isLoading && documents.length === 0 && (
            <div style={{ padding: 28, color: '#94a3b8', fontSize: 14 }}>
              No documents uploaded yet. Start with your National ID or NIN slip.
            </div>
          )}
          <ul style={{ margin: 0, padding: 0, listStyle: 'none' }}>
            {documents.map((doc) => {
              const style = STATUS_STYLES[doc.status];
              const expiresSoon = doc.expires_on && daysUntil(doc.expires_on) <= 60;
              return (
                <li
                  key={doc.id}
                  style={{
                    padding: '14px 18px',
                    borderBottom: '1px solid #f1f5f9',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 14,
                  }}
                >
                  <div
                    style={{
                      width: 40,
                      height: 40,
                      borderRadius: 10,
                      background: '#eef2ff',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      color: '#242a88',
                      flexShrink: 0,
                    }}
                  >
                    <FileText size={18} />
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div
                      style={{
                        fontSize: 14,
                        fontWeight: 600,
                        color: '#0f172a',
                        marginBottom: 2,
                      }}
                    >
                      {doc.title || doc.category_label}
                    </div>
                    <div style={{ fontSize: 12, color: '#64748b' }}>
                      {doc.category_label} ·{' '}
                      {doc.original_filename || 'file'} ·{' '}
                      {formatBytes(doc.size_bytes)} · uploaded{' '}
                      {new Date(doc.uploaded_at).toLocaleDateString()}
                    </div>
                    {doc.hr_notes && (
                      <div
                        style={{
                          fontSize: 12,
                          color: '#b45309',
                          marginTop: 4,
                          fontStyle: 'italic',
                        }}
                      >
                        HR note: {doc.hr_notes}
                      </div>
                    )}
                    {expiresSoon && (
                      <div
                        style={{
                          fontSize: 12,
                          color: '#b45309',
                          marginTop: 4,
                          display: 'flex',
                          alignItems: 'center',
                          gap: 4,
                        }}
                      >
                        <AlertTriangle size={12} /> Expires{' '}
                        {new Date(doc.expires_on!).toLocaleDateString()}
                      </div>
                    )}
                  </div>
                  <span
                    style={{
                      background: style.bg,
                      color: style.fg,
                      fontSize: 11,
                      fontWeight: 600,
                      padding: '4px 9px',
                      borderRadius: 999,
                      textTransform: 'uppercase',
                      letterSpacing: 0.4,
                    }}
                  >
                    {style.label}
                  </span>
                  {doc.download_url && (
                    <a
                      href={doc.download_url}
                      target="_blank"
                      rel="noreferrer"
                      style={{
                        color: '#242a88',
                        fontSize: 12,
                        fontWeight: 600,
                        textDecoration: 'none',
                      }}
                    >
                      View
                    </a>
                  )}
                  {doc.status !== 'verified' && (
                    <button
                      onClick={() => deleteMutation.mutate(doc.id)}
                      disabled={deleteMutation.isPending}
                      title="Remove document"
                      style={{
                        background: 'transparent',
                        border: '1px solid #fecaca',
                        color: '#b91c1c',
                        borderRadius: 7,
                        padding: 6,
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                      }}
                    >
                      <Trash2 size={13} />
                    </button>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      </div>
    </PortalLayout>
  );
}

interface BannerProps {
  submission: PortalVerificationSubmission;
  documents: PortalDocument[];
  confirmAccurate: boolean;
  onConfirm: (v: boolean) => void;
  notes: string;
  onNotesChange: (v: string) => void;
  onSubmit: (documentIds: number[]) => void;
  isSubmitting: boolean;
  error: string | null;
}

function VerificationBanner({
  submission,
  documents,
  confirmAccurate,
  onConfirm,
  notes,
  onNotesChange,
  onSubmit,
  isSubmitting,
  error,
}: BannerProps) {
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const days = daysUntil(submission.cycle.deadline);
  const urgency = days <= 3 ? 'danger' : days <= 7 ? 'warn' : 'info';

  const palette: Record<typeof urgency, { bg: string; border: string; fg: string }> = {
    danger: { bg: '#fef2f2', border: '#fecaca', fg: '#991b1b' },
    warn: { bg: '#fffbeb', border: '#fde68a', fg: '#92400e' },
    info: { bg: '#eff6ff', border: '#bfdbfe', fg: '#1e40af' },
  };
  const colors = palette[urgency];

  const toggle = (id: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <div
      style={{
        background: colors.bg,
        border: `1px solid ${colors.border}`,
        color: colors.fg,
        borderRadius: 12,
        padding: 18,
        marginBottom: 20,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
        {urgency === 'danger' ? (
          <ShieldAlert size={18} />
        ) : (
          <ShieldCheck size={18} />
        )}
        <strong style={{ fontSize: 14 }}>{submission.cycle.name}</strong>
        <span style={{ fontSize: 12, opacity: 0.8 }}>
          · deadline {new Date(submission.cycle.deadline).toLocaleDateString()}{' '}
          ({days >= 0 ? `${days} day${days === 1 ? '' : 's'} left` : 'overdue'})
        </span>
      </div>
      {submission.cycle.instructions && (
        <div style={{ fontSize: 13, marginBottom: 10, lineHeight: 1.5 }}>
          {submission.cycle.instructions}
        </div>
      )}
      <div
        style={{
          background: '#ffffff',
          borderRadius: 10,
          padding: 14,
          color: '#0f172a',
        }}
      >
        <div style={{ fontSize: 12, fontWeight: 600, color: '#475569', marginBottom: 8 }}>
          Link supporting documents (optional)
        </div>
        {documents.length === 0 ? (
          <div style={{ fontSize: 12, color: '#94a3b8' }}>
            Upload documents below to attach them to your attestation.
          </div>
        ) : (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {documents.map((d) => (
              <label
                key={d.id}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                  fontSize: 12,
                  padding: '6px 10px',
                  border: '1px solid #e2e8f0',
                  borderRadius: 999,
                  cursor: 'pointer',
                  background: selected.has(d.id) ? '#eef2ff' : '#ffffff',
                }}
              >
                <input
                  type="checkbox"
                  checked={selected.has(d.id)}
                  onChange={() => toggle(d.id)}
                />
                {d.title || d.category_label}
              </label>
            ))}
          </div>
        )}
        <textarea
          value={notes}
          onChange={(e) => onNotesChange(e.target.value)}
          placeholder="Optional notes for HR (e.g. changed address, new bank details)"
          rows={2}
          style={{
            width: '100%',
            marginTop: 10,
            padding: '8px 10px',
            border: '1px solid #e2e8f0',
            borderRadius: 8,
            fontSize: 13,
            resize: 'vertical',
          }}
        />
        <label
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            marginTop: 10,
            fontSize: 13,
            color: '#0f172a',
          }}
        >
          <input
            type="checkbox"
            checked={confirmAccurate}
            onChange={(e) => onConfirm(e.target.checked)}
          />
          I confirm that my profile information is accurate and I am still in active service.
        </label>
        {error && (
          <div style={{ color: '#b91c1c', fontSize: 12, marginTop: 8 }}>{error}</div>
        )}
        <button
          onClick={() => onSubmit(Array.from(selected))}
          disabled={!confirmAccurate || isSubmitting}
          style={{
            marginTop: 12,
            background: 'linear-gradient(135deg, #242a88, #2e35a0)',
            color: '#ffffff',
            border: 0,
            padding: '9px 18px',
            borderRadius: 8,
            cursor: confirmAccurate ? 'pointer' : 'not-allowed',
            fontSize: 13,
            fontWeight: 600,
            display: 'inline-flex',
            alignItems: 'center',
            gap: 6,
            opacity: confirmAccurate && !isSubmitting ? 1 : 0.6,
          }}
        >
          <Check size={14} />
          {isSubmitting ? 'Submitting…' : 'Submit attestation'}
        </button>
      </div>
    </div>
  );
}
