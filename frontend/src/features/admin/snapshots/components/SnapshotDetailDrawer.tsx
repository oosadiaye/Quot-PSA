import type { ReactNode } from 'react';
import { X } from 'lucide-react';
import type { SnapshotJob } from '@/types/snapshots';
import { SnapshotJobStatusPill } from './SnapshotJobStatusPill';

interface Props {
  job: SnapshotJob;
  onClose: () => void;
}

export function SnapshotDetailDrawer({ job, onClose }: Props) {
  return (
    <div className="fixed inset-0 z-50 flex justify-end" onClick={onClose}>
      <div
        className="w-full max-w-md h-full bg-white shadow-xl p-6 overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex justify-between items-start mb-4">
          <div>
            <h2 className="text-lg font-semibold">Snapshot #{job.id}</h2>
            <p className="text-sm text-gray-500">{job.schema_name}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-gray-500 hover:text-gray-700"
            aria-label="Close"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <dl className="space-y-3 text-sm">
          <Row label="Status">
            <SnapshotJobStatusPill status={job.status} label={job.status_display} />
          </Row>
          <Row label="Label">{job.label || '—'}</Row>
          <Row label="Triggered by">{job.triggered_by_username}</Row>
          <Row label="Triggered at">
            {new Date(job.triggered_at).toLocaleString('en-GB')}
          </Row>
          <Row label="Started at">
            {job.started_at ? new Date(job.started_at).toLocaleString('en-GB') : '—'}
          </Row>
          <Row label="Completed at">
            {job.completed_at ? new Date(job.completed_at).toLocaleString('en-GB') : '—'}
          </Row>
          <Row label="Size">
            {job.size_bytes != null
              ? `${job.size_bytes.toLocaleString('en-GB')} bytes`
              : '—'}
          </Row>
          <Row label="SHA256">
            <code className="text-xs font-mono break-all">{job.sha256 || '—'}</code>
          </Row>
          {job.error_class && (
            <Row label="Error">
              <div>
                <div className="text-red-700 font-mono text-xs">{job.error_class}</div>
                <pre className="mt-1 text-xs text-red-900 whitespace-pre-wrap">
                  {job.error_message}
                </pre>
              </div>
            </Row>
          )}
          {job.manifest_summary && Object.keys(job.manifest_summary).length > 0 && (
            <Row label="Manifest">
              <pre className="text-xs bg-gray-50 p-2 rounded overflow-x-auto">
                {JSON.stringify(job.manifest_summary, null, 2)}
              </pre>
            </Row>
          )}
        </dl>
      </div>
    </div>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt className="text-xs font-medium text-gray-500 uppercase tracking-wide">
        {label}
      </dt>
      <dd className="mt-1">{children}</dd>
    </div>
  );
}
