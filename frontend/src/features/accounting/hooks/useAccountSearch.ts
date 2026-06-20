import apiClient from '../../../api/client';

export interface SearchOption {
    value: string;
    label: string;
    sublabel?: string;
}

/**
 * Server-side account search for `SearchableSelect`'s async `onSearch` mode.
 *
 * Replaces the "fetch all ~10,000 accounts then filter in the browser"
 * pattern on account pickers (the G2 high-traffic risk): each keystroke
 * pulls ~`pageSize` rows from the existing `/accounting/accounts/?search=`
 * endpoint (`AccountViewSet` already exposes `search_fields=['code','name']`
 * and an `is_postable` filter) instead of the full chart.
 *
 * Usage:
 *   const accountSearch = useMemo(() => makeAccountSearch({ postableOnly: true }), []);
 *   // pass the currently-selected account in `options` so its label shows
 *   // before the user types (async results won't contain it on first paint):
 *   <SearchableSelect
 *     value={form.account}
 *     onChange={v => set('account', v)}
 *     onSearch={accountSearch}
 *     options={selectedAccountOption ? [selectedAccountOption] : []}
 *   />
 *
 * Returns a stable async function suitable for `onSearch`. Memoise it in the
 * caller (`useMemo`) so the debounced effect inside SearchableSelect doesn't
 * re-subscribe on every render.
 */
export function makeAccountSearch(
    opts?: { postableOnly?: boolean; pageSize?: number },
): (query: string) => Promise<SearchOption[]> {
    const pageSize = opts?.pageSize ?? 20;
    const postableOnly = opts?.postableOnly ?? false;

    return async (query: string): Promise<SearchOption[]> => {
        const params: Record<string, string | number | boolean> = { page_size: pageSize };
        const q = query.trim();
        if (q) params.search = q;
        if (postableOnly) params.is_postable = true;

        const { data } = await apiClient.get('/accounting/accounts/', { params });
        const rows = (data?.results ?? data ?? []) as Array<{
            id: number | string;
            code: string;
            name: string;
            account_type?: string;
        }>;

        return rows.map((a) => ({
            value: String(a.id),
            label: `${a.code} — ${a.name}`,
            sublabel: a.account_type,
        }));
    };
}
