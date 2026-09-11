/**
 * Which sidebar group owns the current route.
 *
 * Extracted from Sidebar.tsx because the rule used to live in two
 * places — the auto-expand effect and the highlight predicate — which
 * is how they drifted apart and started disagreeing. One exported
 * function means the group that opens and the group that highlights
 * cannot be different groups.
 */

/** The shape this module needs. The real MenuItem carries an icon and
 *  permission fields too; none of that affects ownership, so keeping
 *  the input minimal keeps the tests free of React and lucide imports. */
export interface MenuLike {
    name: string;
    path: string;
    subItems?: { path: string }[];
}

/**
 * Exact-match a menu path against the current location.
 *
 * Some menu entries carry a query string (``/accounting/ar?tab=payments``)
 * because the tab, not the path, is what distinguishes them — so those
 * must compare search as well or every tab looks active at once.
 */
export function isMenuPathActive(path: string, pathname: string, search = ''): boolean {
    if (path.includes('?')) {
        const [p, q] = path.split('?');
        return pathname === p && search === `?${q}`;
    }
    return pathname === path;
}

/**
 * The single group that owns ``pathname``, or undefined if none does.
 *
 * Specificity is resolved across *all* groups before any prefix
 * matching. That ordering is the whole point: `menuItems` lists
 * General Ledger (path '/accounting') above Treasury (path
 * '/accounting/tsa-accounts'), so a single `find` whose predicate ends
 * in a prefix test returns General Ledger for every '/accounting/*'
 * route and never reaches the group that actually lists the page —
 * which is what made opening Payment Batches expand General Ledger and
 * highlight both.
 *
 * Three passes, strongest signal first:
 *   1. a group listing this exact page in its submenu;
 *   2. a group whose own path is exactly this page;
 *   3. the *longest* path that is a parent segment of it.
 *
 * Pass 3 requires a '/' boundary, so '/accounting' cannot claim
 * '/accounting-archive', and takes the longest match so a nested group
 * beats its parent.
 */
export function findActiveParent<T extends MenuLike>(
    items: readonly T[],
    pathname: string,
    search = '',
): T | undefined {
    return (
        items.find((i) => i.subItems?.some((sub) => isMenuPathActive(sub.path, pathname, search)))
        ?? items.find((i) => i.path === pathname)
        ?? items
            .filter((i) => i.path && pathname.startsWith(`${i.path}/`))
            .sort((a, b) => b.path.length - a.path.length)[0]
    );
}
