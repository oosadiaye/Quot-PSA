import apiClient from '../../../api/client';
import type { SearchOption } from '../../accounting/hooks/useAccountSearch';

/**
 * Server-side appropriation search for `SearchableSelect`'s async `onSearch`.
 *
 * Hits `/budget/appropriations/?status=ACTIVE&search=` (the viewset has
 * SearchFilter + a `status` filter), pulling ~`pageSize` rows per keystroke
 * instead of the whole budget. Labelled by the economic (GL) segment — the
 * appropriation is one MDA × Fund × GL line — with the approved amount as the
 * sublabel. Mirrors `makeAccountSearch`.
 *
 * Usage (memoise in the caller, and pass the selected option in `options` so its
 * label shows before typing):
 *   const apprSearch = useMemo(() => makeAppropriationSearch(), []);
 */
export function makeAppropriationSearch(
  opts?: { pageSize?: number },
): (query: string) => Promise<SearchOption[]> {
  const pageSize = opts?.pageSize ?? 20;

  return async (query: string): Promise<SearchOption[]> => {
    const params: Record<string, string | number | boolean> = {
      status: 'ACTIVE', page_size: pageSize,
    };
    const q = query.trim();
    if (q) params.search = q;

    const { data } = await apiClient.get('/budget/appropriations/', { params });
    const rows = (data?.results ?? data ?? []) as Array<{
      id: number | string;
      economic_code?: string;
      economic_name?: string;
      amount_approved?: string | number;
    }>;

    return rows.map((a) => ({
      value: String(a.id),
      label: a.economic_code
        ? `${a.economic_code}${a.economic_name ? ' — ' + a.economic_name : ''}`
        : `Appropriation #${a.id}`,
      sublabel: a.amount_approved != null
        ? `₦${Number(a.amount_approved).toLocaleString()}`
        : undefined,
    }));
  };
}
