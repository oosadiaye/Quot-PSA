import { useMutation, useQueryClient } from '@tanstack/react-query';
import { createSnapshot } from '@/api/snapshots';
import type { CreateSnapshotPayload, SnapshotJob } from '@/types/snapshots';
import { useToast } from '@/context/ToastContext';

export function useCreateSnapshot() {
  const queryClient = useQueryClient();
  const { addToast } = useToast();
  return useMutation<SnapshotJob, Error, CreateSnapshotPayload>({
    mutationFn: createSnapshot,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['snapshots'] });
      addToast('Snapshot queued.', 'success');
    },
    onError: (error: any) => {
      const msg =
        error?.response?.data?.detail ||
        error?.response?.data?.schema_name?.[0] ||
        error?.message ||
        'Snapshot creation failed.';
      addToast(msg, 'error');
    },
  });
}
