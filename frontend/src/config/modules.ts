/**
 * What the module launcher and the horizontal menu need from ``navigation.ts``: the tiles, which module a route belongs to,
 * and how many of a module's menus fit on the bar. Pure functions, so they are tested without rendering anything.
 */
import type { MenuItem, SubItem } from './navigation';

/** A module's accent: the name of a ``--module-*`` token in ``styles/design-tokens.css`` (a tile is never given a literal colour). */
const ACCENT: Record<string, string> = {
  Dashboard: 'blue', Accounting: 'green', 'Budget & Appropriation': 'orange', 'Treasury & Banking': 'sky',
  'NCoA Classification': 'teal', Procurement: 'brown', 'Contracts & Milestones': 'crimson', 'Government Stores': 'cyan',
  'Human Resources': 'purple', 'IPSAS Reporting': 'royal', 'Data Quality': 'slate', Administration: 'indigo',
  'Audit Trail': 'charcoal', Approvals: 'emerald', Workflow: 'violet', Settings: 'charcoal',
  'Budget Preparation': 'orange', 'e-Procurement': 'brown', 'Establishment & Payroll': 'plum', 'Public Debt': 'crimson',
  'Fiscal Transparency': 'sky', 'Results & M&E': 'aqua', 'Integration Gateway': 'indigo', 'Revenue Administration': 'green',
  'Cash Planning': 'sky', 'Advances & Travel': 'orange', 'Internal Audit': 'charcoal', 'Fleet Management': 'cyan',
  'Supplier Catalogue': 'teal', 'Asset Declaration': 'slate', 'Legal & Risk': 'plum', 'System Admin': 'charcoal',
};

/** The CSS value for a module's tile colour. */
export const accentOf = (name: string): string => (ACCENT[name] ? `var(--module-${ACCENT[name]})` : 'var(--color-primary)');

/** How many menus a module has: its entries, or one for a module that is a single page. */
export const menuCount = (item: MenuItem): number => item.subItems?.length ?? 1;

export interface ModuleTile {
  name: string;
  path: string;
  icon: MenuItem['icon'];
  menus: number;
  accent: string;
}

export const toTiles = (items: MenuItem[]): ModuleTile[] =>
  items.map((i) => ({ name: i.name, path: i.path, icon: i.icon, menus: menuCount(i), accent: accentOf(i.name) }));

/** "1 menu", "11 menus". */
export const menusLabel = (n: number): string => `${n} ${n === 1 ? 'menu' : 'menus'}`;

/** Whether a menu path is the page being viewed. A path with a query string must match it too (``/x?tab=y``). */
export function pathMatches(path: string, pathname: string, search = ''): boolean {
  if (path.includes('?')) {
    const [p, q] = path.split('?');
    return pathname === p && search === `?${q}`;
  }
  return pathname === path;
}

const within = (path: string, pathname: string) => {
  const base = path.split('?')[0];
  return pathname === base || pathname.startsWith(base.endsWith('/') ? base : `${base}/`);
};

/**
 * The module a route belongs to. A page listed under a module's menus wins, the most specific path first; then a module whose
 * own path the route sits under. Two modules can list the same page (Suppliers/Vendor, Cash Position), so ``preferred`` (the
 * one the user came from) breaks that tie; with none, the first listed wins. A route in no module has none.
 */
export function activeModule(items: MenuItem[], pathname: string, search = '', preferred?: string | null): MenuItem | null {
  type Hit = { item: MenuItem; score: number };
  const hits: Hit[] = [];
  for (const item of items) {
    let best = -1;
    for (const sub of item.subItems ?? []) {
      if (pathMatches(sub.path, pathname, search)) best = Math.max(best, 10_000 + sub.path.length);
      else if (within(sub.path, pathname)) best = Math.max(best, sub.path.length);
    }
    if (best < 0 && item.path && within(item.path, pathname)) best = 0;
    if (best >= 0) hits.push({ item, score: best });
  }
  if (hits.length === 0) return null;
  const top = Math.max(...hits.map((h) => h.score));
  const tied = hits.filter((h) => h.score === top);
  return (tied.find((h) => h.item.name === preferred) ?? tied[0]).item;
}

/** The menu to mark as current in a module: an exact page first, else the longest path the route sits under. */
export function currentSub(subs: SubItem[], pathname: string, search = ''): SubItem | null {
  const exact = subs.find((s) => pathMatches(s.path, pathname, search));
  if (exact) return exact;
  const under = subs.filter((s) => within(s.path, pathname)).sort((a, b) => b.path.length - a.path.length);
  return under[0] ?? null;
}

/**
 * How many of a bar's menus show inline. If all fit they all do; otherwise as many as fit beside a "More" button, the rest
 * going into it. ``gap`` is the space between two menus.
 */
export function fitCount(widths: number[], available: number, moreWidth: number, gap: number): number {
  const total = widths.reduce((sum, w) => sum + w, 0) + gap * Math.max(0, widths.length - 1);
  if (total <= available) return widths.length;
  let used = moreWidth;
  let shown = 0;
  for (const w of widths) {
    if (used + w + gap > available) break;
    used += w + gap;
    shown += 1;
  }
  return shown;
}
