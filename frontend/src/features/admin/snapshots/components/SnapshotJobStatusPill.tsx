import type { SnapshotStatus } from '@/types/snapshots';
import StatusBadge from '@/components/layout/StatusBadge';

type Tone = 'neutral' | 'info' | 'success' | 'warning' | 'danger';

const TONE_MAP: Record<SnapshotStatus, Tone> = {
  queued: 'neutral',
  running: 'info',
  succeeded: 'success',
  failed: 'danger',
  expired: 'warning',
};

interface Props {
  status: SnapshotStatus;
  label?: string;
}

export function SnapshotJobStatusPill({ status, label }: Props) {
  return (
    <StatusBadge tone={TONE_MAP[status]}>
      {label ?? status}
    </StatusBadge>
  );
}
