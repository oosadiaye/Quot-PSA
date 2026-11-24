import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import apiClient from '../../../api/client';

/** Loads one record by the `:id` in the route, for a print page. */
export function usePrintRecord<T = any>(endpoint: string) {
    const { id } = useParams<{ id: string }>();
    return useQuery<T>({
        queryKey: ['print', endpoint, id],
        queryFn: async () => (await apiClient.get(`${endpoint}/${id}/`)).data,
        enabled: !!id,
    });
}
