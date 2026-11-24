import { describe, expect, it } from 'vitest';
import { activeModule, currentSub, fitCount, menuCount, menusLabel, pathMatches, toTiles } from '../modules';
import { menuItems, type MenuItem } from '../navigation';

const icon = () => null;
const mod = (name: string, path: string, subs: [string, string][] = []): MenuItem => ({
  name, icon, path, requiredPerm: null, module: null,
  subItems: subs.length ? subs.map(([n, p]) => ({ name: n, path: p, icon })) : undefined,
});

const ITEMS: MenuItem[] = [
  mod('Accounting', '/accounting', [['Journal Entries', '/accounting'], ['Suppliers/Vendor', '/procurement/vendors'], ['Trial Balance', '/accounting/reports/trial-balance']]),
  mod('Treasury & Banking', '/accounting/tsa-accounts', [['Bank Accounts', '/accounting/tsa-accounts'], ['Cash Position', '/accounting/ipsas/tsa-cash-position']]),
  mod('Procurement', '/procurement/requisitions', [['Purchase Orders', '/procurement/orders'], ['Suppliers/Vendor', '/procurement/vendors']]),
  mod('IPSAS Reporting', '/accounting/ipsas/financial-position', [['Cash Position', '/accounting/ipsas/tsa-cash-position']]),
  mod('Dashboard', '/dashboard'),
  mod('Budget Preparation', '/budget-prep'),
];

describe('tiles', () => {
  it('counts a module’s menus, and a single-page module as one', () => {
    expect(menuCount(ITEMS[0])).toBe(3);
    expect(menuCount(ITEMS[4])).toBe(1);
    expect(menusLabel(1)).toBe('1 menu');
    expect(menusLabel(11)).toBe('11 menus');
  });

  it('gives every module a tile with its count and an accent token, never a literal colour', () => {
    const tiles = toTiles(menuItems);
    expect(tiles).toHaveLength(menuItems.length);
    for (const t of tiles) expect(t.accent).toMatch(/^var\(--/);
    expect(tiles.find((t) => t.name === 'Accounting')?.menus).toBe(menuItems.find((m) => m.name === 'Accounting')!.subItems!.length);
  });
});

describe('activeModule', () => {
  it('finds the module a page is listed under', () => {
    expect(activeModule(ITEMS, '/accounting/reports/trial-balance')?.name).toBe('Accounting');
    expect(activeModule(ITEMS, '/procurement/orders')?.name).toBe('Procurement');
  });

  it('prefers the more specific page: a Treasury page under /accounting is Treasury, not Accounting', () => {
    expect(activeModule(ITEMS, '/accounting/tsa-accounts')?.name).toBe('Treasury & Banking');
  });

  it('finds a module from a page under one of its menus', () => {
    expect(activeModule(ITEMS, '/procurement/orders/42')?.name).toBe('Procurement');
  });

  it('uses the module the user came from when two list the same page', () => {
    expect(activeModule(ITEMS, '/procurement/vendors', '', 'Accounting')?.name).toBe('Accounting');
    expect(activeModule(ITEMS, '/procurement/vendors', '', 'Procurement')?.name).toBe('Procurement');
    expect(activeModule(ITEMS, '/accounting/ipsas/tsa-cash-position', '', 'IPSAS Reporting')?.name).toBe('IPSAS Reporting');
  });

  it('falls back to the first listed when nothing says where the user came from', () => {
    expect(activeModule(ITEMS, '/procurement/vendors')?.name).toBe('Accounting');
  });

  it('knows a single-page module by its own path, and a route in no module as none', () => {
    expect(activeModule(ITEMS, '/budget-prep')?.name).toBe('Budget Preparation');
    expect(activeModule(ITEMS, '/dashboard')?.name).toBe('Dashboard');
    expect(activeModule(ITEMS, '/account')).toBeNull();
    expect(activeModule(ITEMS, '/accountable')).toBeNull();                 // a longer word is not a sub-path
  });

  it('resolves every page in the real navigation to some module', () => {
    for (const item of menuItems) for (const sub of item.subItems ?? []) {
      const [path, query] = sub.path.split('?');
      expect(activeModule(menuItems, path, query ? `?${query}` : ''), sub.path).not.toBeNull();
    }
  });
});

describe('currentSub', () => {
  const subs = ITEMS[0].subItems!;
  it('marks the exact page, or the longest path the route sits under', () => {
    expect(currentSub(subs, '/accounting/reports/trial-balance')?.name).toBe('Trial Balance');
    expect(currentSub(subs, '/accounting')?.name).toBe('Journal Entries');
    expect(currentSub(subs, '/accounting/reports/trial-balance/2026')?.name).toBe('Trial Balance');
    expect(currentSub(subs, '/elsewhere')).toBeNull();
  });

  it('matches a menu with a query string only when the query matches', () => {
    expect(pathMatches('/x?tab=a', '/x', '?tab=a')).toBe(true);
    expect(pathMatches('/x?tab=a', '/x', '?tab=b')).toBe(false);
    expect(pathMatches('/x', '/x', '?anything')).toBe(true);
  });
});

describe('fitCount', () => {
  const widths = [100, 100, 100, 100, 100];
  it('shows everything when it all fits, with no More', () => {
    expect(fitCount(widths, 520, 60, 2)).toBe(5);                      // 500 + 8 gaps = 508
  });

  it('leaves room for More when it does not all fit', () => {
    expect(fitCount(widths, 400, 60, 2)).toBe(3);                      // 60 + 3 x 102 = 366; a fourth would reach 468
  });

  it('shows none inline when even one does not fit beside More', () => {
    expect(fitCount(widths, 120, 60, 2)).toBe(0);
  });

  it('copes with no menus', () => {
    expect(fitCount([], 300, 60, 2)).toBe(0);
  });
});
