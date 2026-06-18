import apiClient from './client';
import type {
  SnapshotJob,
  SnapshotListResponse,
  CreateSnapshotPayload,
} from '../types/snapshots';

export async function listSnapshots(): Promise<SnapshotListResponse | SnapshotJob[]> {
  const { data } = await apiClient.get<SnapshotListResponse | SnapshotJob[]>(
    'snapshots/',
  );
  return data;
}

export async function getSnapshot(id: number): Promise<SnapshotJob> {
  const { data } = await apiClient.get<SnapshotJob>(`snapshots/${id}/`);
  return data;
}

export async function createSnapshot(
  payload: CreateSnapshotPayload,
): Promise<SnapshotJob> {
  const { data } = await apiClient.post<SnapshotJob>('snapshots/', payload);
  return data;
}

export async function deleteSnapshot(id: number): Promise<void> {
  await apiClient.delete(`snapshots/${id}/`);
}

export function snapshotDownloadUrl(id: number): string {
  return `/api/v1/snapshots/${id}/download/`;
}
