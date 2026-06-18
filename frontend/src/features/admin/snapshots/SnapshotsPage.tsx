import ListPageShell from '@/components/layout/ListPageShell';
import { CreateSnapshotForm } from './components/CreateSnapshotForm';
import { SnapshotsTable } from './components/SnapshotsTable';
import { useSnapshotJobs } from './hooks/useSnapshotJobs';
import { useCreateSnapshot } from './hooks/useCreateSnapshot';
import { useDeleteSnapshot } from './hooks/useDeleteSnapshot';

export function SnapshotsPage() {
  const { data: jobs = [], isLoading } = useSnapshotJobs();
  const createMutation = useCreateSnapshot();
  const deleteMutation = useDeleteSnapshot();

  return (
    <ListPageShell title="Snapshots (all tenants)">
      <CreateSnapshotForm
        canEditSchema
        onSubmit={(payload) => createMutation.mutate(payload)}
        isSubmitting={createMutation.isPending}
      />
      <SnapshotsTable
        jobs={jobs}
        onDelete={(id) => deleteMutation.mutate(id)}
        isLoading={isLoading}
      />
    </ListPageShell>
  );
}
