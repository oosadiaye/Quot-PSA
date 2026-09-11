/**
 * Which sidebar group owns a route.
 *
 * These exist because the shipped rule was wrong and nothing caught it:
 * opening Payment Batches expanded General Ledger and highlighted both
 * groups. It was found by opening the app, not by a test, and the PR
 * test plan claimed the behaviour worked.
 *
 * The trap is ordering. General Ledger sits at '/accounting' and is
 * listed *above* Treasury at '/accounting/tsa-accounts', so any rule
 * that prefix-matches group-by-group in array order hands every
 * '/accounting/*' route to General Ledger and never reaches the group
 * that actually lists the page. The fixture below preserves that
 * ordering deliberately — a test with the groups in a friendlier order
 * would pass against the broken implementation.
 */
import { describe, it, expect } from 'vitest';
import { findActiveParent, isMenuPathActive, type MenuLike } from '../sidebarMenu';

/** Mirrors the real menu's shape *and its order*, which is the point. */
const MENU: MenuLike[] = [
    { name: 'Dashboard', path: '/dashboard' },
    {
        name: 'General Ledger',
        path: '/accounting',
        subItems: [
            { path: '/accounting' },
            { path: '/accounting/coa' },
            { path: '/accounting/trial-balance' },
        ],
    },
    {
        name: 'Treasury & Banking (TSA)',
        path: '/accounting/tsa-accounts',
        subItems: [
            { path: '/accounting/tsa-accounts' },
            { path: '/accounting/payment-batches' },
            { path: '/accounting/payment-vouchers' },
        ],
    },
    {
        name: 'Receivables',
        path: '/accounting/ar',
        subItems: [
            { path: '/accounting/ar?tab=invoices' },
            { path: '/accounting/ar?tab=payments' },
        ],
    },
];

const owner = (pathname: string, search = '') =>
    findActiveParent(MENU, pathname, search)?.name;

describe('findActiveParent', () => {
    it('gives a page to the group that lists it, not to an earlier broad prefix', () => {
        // The shipped bug. '/accounting/payment-batches' startsWith
        // '/accounting', and General Ledger comes first in the array.
        expect(owner('/accounting/payment-batches')).toBe('Treasury & Banking (TSA)');
    });

    it('still resolves the broad group for its own pages', () => {
        expect(owner('/accounting/coa')).toBe('General Ledger');
        expect(owner('/accounting/trial-balance')).toBe('General Ledger');
    });

    it('prefers a submenu hit over a group whose path equals the route', () => {
        // '/accounting' is General Ledger's own path *and* its first
        // submenu entry; either way the answer must be General Ledger,
        // never a later group.
        expect(owner('/accounting')).toBe('General Ledger');
    });

    it('does not let a prefix claim a sibling that merely starts the same way', () => {
        // '/accounting-archive'.startsWith('/accounting') is true, which
        // is why the boundary slash matters.
        expect(owner('/accounting-archive')).toBeUndefined();
    });

    it('falls back to the longest matching prefix for an unlisted child page', () => {
        // A detail route nobody put in the menu still belongs to the most
        // specific group, not the shortest path that happens to match.
        expect(owner('/accounting/tsa-accounts/42')).toBe('Treasury & Banking (TSA)');
    });

    it('returns undefined when nothing owns the route', () => {
        expect(owner('/settings/profile')).toBeUndefined();
    });

    it('distinguishes query-string tabs', () => {
        expect(owner('/accounting/ar', '?tab=payments')).toBe('Receivables');
        // Same path, a tab the menu does not list: no submenu hit, and
        // '/accounting/ar' is Receivables' own path, so it still owns it.
        expect(owner('/accounting/ar', '?tab=unknown')).toBe('Receivables');
    });

    it('never returns two owners — the highlight and the open group are one value', () => {
        for (const p of [
            '/accounting',
            '/accounting/coa',
            '/accounting/payment-batches',
            '/accounting/tsa-accounts',
            '/dashboard',
        ]) {
            const matches = MENU.filter((m) => m.name === owner(p));
            expect(matches.length).toBeLessThanOrEqual(1);
        }
    });
});

describe('isMenuPathActive', () => {
    it('matches on pathname alone when the entry carries no query', () => {
        expect(isMenuPathActive('/accounting/coa', '/accounting/coa')).toBe(true);
        expect(isMenuPathActive('/accounting/coa', '/accounting')).toBe(false);
    });

    it('requires the search string to match when the entry carries one', () => {
        expect(isMenuPathActive('/accounting/ar?tab=payments', '/accounting/ar', '?tab=payments')).toBe(true);
        expect(isMenuPathActive('/accounting/ar?tab=payments', '/accounting/ar', '?tab=invoices')).toBe(false);
        // Without this, every tab entry reads as active at once.
        expect(isMenuPathActive('/accounting/ar?tab=payments', '/accounting/ar', '')).toBe(false);
    });
});
