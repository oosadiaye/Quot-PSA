import { useMutation, useQueryClient } from '@tanstack/react-query';
import { deleteSnapshot } from '@/api/snapshots';

export function useDeleteSnapshot() {
  const queryClient = useQueryClient();
  return useMutation<void, Error, number>({
    mutationFn: deleteSnapshot,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['snapshots'] });
    },
  });
}
