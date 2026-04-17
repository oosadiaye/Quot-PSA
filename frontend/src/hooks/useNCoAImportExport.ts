/**
 * useNCoAImportExport — Hooks for NCoA segment template download and bulk import.
 */
import { useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '../api/client';

export type NCoASegmentType =
    | 'administrative'
    | 'economic'
    | 'functional'
    | 'programme'
    | 'fund'
    | 'geographic';

export interface BulkImportResult {
    success: boolean;
    created: number;
    updated: number;
    skipped: number;
    errors: string[];
}

/** Download a CSV import template for a specific NCoA segment type. */
export async function downloadNCoATemplate(segmentType: NCoASegmentType): Promise<void> {
    const response = await apiClient.get(
        `/accounting/ncoa/${segmentType}/import-template/`,
        { responseType: 'blob' },
    );
    const blob = new Blob([response.data], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${segmentType}_segment_import_template.csv`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
}

/** Mutation hook for bulk-importing a CSV/XLSX file into an NCoA segment. */
export function useNCoABulkImport(segmentType: NCoASegmentType) {
    const qc = useQueryClient();
    return useMutation<BulkImportResult, Error, File>({
        mutationFn: async (file: File) => {
            const formData = new FormData();
            formData.append('file', file);
            const res = await apiClient.post(
                `/accounting/ncoa/${segmentType}/bulk-import/`,
                formData,
                { headers: { 'Content-Type': 'multipart/form-data' } },
            );
            return res.data as BulkImportResult;
        },
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['generic-list'] });
            qc.invalidateQueries({ queryKey: ['ncoa-segments-all'] });
        },
    });
}
