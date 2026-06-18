export type SnapshotStatus =
  | 'queued'
  | 'running'
  | 'succeeded'
  | 'failed'
  | 'expired';

export interface ManifestSummary {
  schema_version?: number;
  created_at_utc?: string;
  database_sql_sha256?: string;
  media_file_count?: number;
  media_total_bytes?: number;
}

export interface SnapshotJob {
  id: number;
  schema_name: string;
  label: string;
  status: SnapshotStatus;
  status_display: string;
  triggered_by_username: string;
  triggered_at: string;
  started_at: string | null;
  completed_at: string | null;
  size_bytes: number | null;
  sha256: string;
  manifest_summary: ManifestSummary;
  error_class: string;
  error_message: string;
  has_artifact: boolean;
}

export interface CreateSnapshotPayload {
  schema_name: string;
  label?: string;
}

export interface SnapshotListResponse {
  count?: number;
  next?: string | null;
  previous?: string | null;
  results: SnapshotJob[];
}
