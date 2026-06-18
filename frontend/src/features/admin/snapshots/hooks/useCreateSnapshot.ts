import { useMutation, useQueryClient } from '@tanstack/react-query';
import { createSnapshot } from '@/api/snapshots';
import type { CreateSnapshotPayload, SnapshotJob } from '@/types/snapshots';

export function useCreateSnapshot() {
  const queryClient = useQueryClient();
  return useMutation<SnapshotJob, Error, CreateSnapshotPayload>({
    mutationFn: createSnapshot,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['snapshots'] });
    },
  });
}
