import { useAuth } from '@/context/AuthContext';
import ListPageShell from '@/components/layout/ListPageShell';
import { CreateSnapshotForm } from './components/CreateSnapshotForm';
import { SnapshotsTable } from './components/SnapshotsTable';
import { useSnapshotJobs } from './hooks/useSnapshotJobs';
import { useCreateSnapshot } from './hooks/useCreateSnapshot';
import { useDeleteSnapshot } from './hooks/useDeleteSnapshot';

/**
 * Tenant-admin view: schema is pre-filled from the current tenant's
 * `schema_name` (returned by the login API) and locked — the user
 * cannot target another tenant's data.
 *
 * `AuthContext.TenantInfo` declares only the subset of fields consumed
 * by the auth layer. The API also returns `schema_name`; we cast to
 * access it without widening the public `TenantInfo` interface.
 */
interface TenantInfoWithSchema {
  schema_name?: string;
}

export function TenantSnapshotsPage() {
  const { tenantInfo } = useAuth();
  const { data: jobs = [], isLoading } = useSnapshotJobs();
  const createMutation = useCreateSnapshot();
  const deleteMutation = useDeleteSnapshot();

  const tenantSchema =
    (tenantInfo as (typeof tenantInfo & TenantInfoWithSchema) | null)
      ?.schema_name ?? '';

  return (
    <ListPageShell title="Snapshots">
      <CreateSnapshotForm
        defaultSchema={tenantSchema}
        canEditSchema={false}
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
