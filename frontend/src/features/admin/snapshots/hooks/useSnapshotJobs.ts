import { useQuery } from '@tanstack/react-query';
import { listSnapshots } from '@/api/snapshots';
import type { SnapshotJob, SnapshotListResponse } from '@/types/snapshots';

const POLL_INTERVAL_MS = 5000;
const STATES_IN_FLIGHT = new Set(['queued', 'running']);

function isInFlight(job: SnapshotJob): boolean {
  return STATES_IN_FLIGHT.has(job.status);
}

export function useSnapshotJobs() {
  return useQuery({
    queryKey: ['snapshots'],
    queryFn: async () => {
      const data = await listSnapshots();
      const items: SnapshotJob[] = Array.isArray(data)
        ? data
        : ((data as SnapshotListResponse).results ?? []);
      return items;
    },
    refetchInterval: (query) => {
      const items = query.state.data;
      if (!items || !Array.isArray(items)) return false;
      return items.some(isInFlight) ? POLL_INTERVAL_MS : false;
    },
  });
}
