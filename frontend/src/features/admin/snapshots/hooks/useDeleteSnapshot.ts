import { useMutation, useQueryClient } from '@tanstack/react-query';
import { deleteSnapshot } from '@/api/snapshots';
import { useToast } from '@/context/ToastContext';

export function useDeleteSnapshot() {
  const queryClient = useQueryClient();
  const { addToast } = useToast();
  return useMutation<void, Error, number>({
    mutationFn: deleteSnapshot,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['snapshots'] });
      addToast('Snapshot deleted.', 'success');
    },
    onError: (error: any) => {
      addToast(error?.message || 'Delete failed.', 'error');
    },
  });
}
