import { useState } from 'react';
import { Download, Trash2, Eye } from 'lucide-react';
import type { SnapshotJob } from '@/types/snapshots';
import { SnapshotJobStatusPill } from './SnapshotJobStatusPill';
import { snapshotDownloadUrl } from '@/api/snapshots';
import { SnapshotDetailDrawer } from './SnapshotDetailDrawer';

interface Props {
  jobs: SnapshotJob[];
  onDelete: (id: number) => void;
  isLoading?: boolean;
}

export function SnapshotsTable({ jobs, onDelete, isLoading }: Props) {
  const [detailJob, setDetailJob] = useState<SnapshotJob | null>(null);

  if (isLoading) {
    return <div className="p-4 text-sm text-gray-500">Loading snapshots…</div>;
  }
  if (jobs.length === 0) {
    return (
      <div className="p-8 text-center text-sm text-gray-500">
        No snapshots yet. Create one above.
      </div>
    );
  }

  return (
    <>
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-200 text-sm">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-3 py-2 text-left font-medium text-gray-700">Status</th>
              <th className="px-3 py-2 text-left font-medium text-gray-700">Schema</th>
              <th className="px-3 py-2 text-left font-medium text-gray-700">Label</th>
              <th className="px-3 py-2 text-left font-medium text-gray-700">Triggered by</th>
              <th className="px-3 py-2 text-left font-medium text-gray-700">When</th>
              <th className="px-3 py-2 text-left font-medium text-gray-700">Size</th>
              <th className="px-3 py-2 text-right font-medium text-gray-700">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200 bg-white">
            {jobs.map((job) => (
              <tr key={job.id}>
                <td className="px-3 py-2">
                  <SnapshotJobStatusPill status={job.status} label={job.status_display} />
                </td>
                <td className="px-3 py-2 font-mono text-xs">{job.schema_name}</td>
                <td className="px-3 py-2">{job.label || '—'}</td>
                <td className="px-3 py-2">{job.triggered_by_username}</td>
                <td className="px-3 py-2">
                  {new Date(job.triggered_at).toLocaleString('en-GB')}
                </td>
                <td className="px-3 py-2 font-mono text-xs">
                  {job.size_bytes != null ? formatBytes(job.size_bytes) : '—'}
                </td>
                <td className="px-3 py-2 text-right">
                  <button
                    type="button"
                    onClick={() => setDetailJob(job)}
                    className="inline-flex items-center gap-1 px-2 py-1 text-xs text-gray-700 hover:text-gray-900"
                    title="View details"
                  >
                    <Eye className="h-3.5 w-3.5" />
                  </button>
                  {job.has_artifact && (
                    <a
                      href={snapshotDownloadUrl(job.id)}
                      className="inline-flex items-center gap-1 px-2 py-1 text-xs text-blue-700 hover:text-blue-900"
                      download
                      title="Download"
                    >
                      <Download className="h-3.5 w-3.5" />
                    </a>
                  )}
                  <button
                    type="button"
                    onClick={() => {
                      if (window.confirm('Delete this snapshot? The artifact will be removed.')) {
                        onDelete(job.id);
                      }
                    }}
                    className="inline-flex items-center gap-1 px-2 py-1 text-xs text-red-700 hover:text-red-900"
                    title="Delete"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {detailJob && (
        <SnapshotDetailDrawer job={detailJob} onClose={() => setDetailJob(null)} />
      )}
    </>
  );
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
}
