import { describe, expect, it } from 'vitest';
import { buildFeatureIndex, findFeatures, type Feature } from './featureIndex';
import { findGuides } from './knowledge/findGuides';
import { GUIDES } from './knowledge/guides';
import { menuItems } from '../../config/navigation';
import type { UserPermissions } from '../../hooks/usePermissions';

const user = (over: Partial<UserPermissions> = {}): UserPermissions => ({
    id: 1, username: 'ada', email: 'a@b.co', first_name: 'Ada', last_name: 'L',
    groups: [], permissions: [], tenant_permissions: [], ...over,
});
const all = { enabledModules: {}, loading: false };
const admin = buildFeatureIndex({ viewer: { user: user({ tenant_role: 'admin' }), loading: false }, modules: all });
const guideIds = (index: Feature[], q: string) => findGuides(index, q).map(g => g.id);

describe('guides', () => {
    it('"how do I post a budget" leads to the appropriation guide, not the budget check', () => {
        expect(guideIds(admin, 'how do I post a budget')[0]).toBe('post-budget');
        expect(guideIds(admin, 'how do I post a budget')).not.toContain('check-budget');
    });

    it('"how to check budget" leads to Budget Check, not the posting guide', () => {
        expect(guideIds(admin, 'how to check budget')[0]).toBe('check-budget');
        expect(guideIds(admin, 'how to check budget')).not.toContain('post-budget');
    });

    it('understands everyday wording for the same task', () => {
        expect(guideIds(admin, 'enter appropriation')[0]).toBe('post-budget');
        expect(guideIds(admin, 'what is my available budget')[0]).toBe('check-budget');
        expect(guideIds(admin, 'I want to pay a vendor')[0]).toBe('pay-supplier');
        expect(guideIds(admin, 'add new vendor')[0]).toBe('add-supplier');
    });

    it('hides a guide whose screen the user cannot open', () => {
        const noBudget = buildFeatureIndex({ viewer: { user: user(), loading: false }, modules: all });
        expect(guideIds(noBudget, 'how do I post a budget')).toEqual([]);
    });

    it('hides guides for a module that is switched off', () => {
        const off = buildFeatureIndex({
            viewer: { user: user({ is_superuser: true }), loading: false },
            modules: { enabledModules: { accounting: true, budget: false }, loading: false },
        });
        expect(guideIds(off, 'check budget')).toEqual([]);
    });

    it('still offers a guide for a screen outside the sidebar', () => {
        expect(guideIds([], 'change password')).toEqual(['change-password']);
    });

    it('returns nothing for an unrelated question', () => {
        expect(guideIds(admin, 'purple elephants')).toEqual([]);
    });

    it('every guide screen exists in the menu, so no guide points at a dead page', () => {
        const paths = new Set(menuItems.flatMap(m => [m.path, ...(m.subItems ?? []).map(s => s.path)]));
        for (const g of GUIDES) if (g.screen) expect(paths.has(g.screen), g.id).toBe(true);
    });

    it('every guide is reachable by its own first phrase', () => {
        for (const g of GUIDES) expect(guideIds(admin, g.asks[0]), g.id).toContain(g.id);
    });
});

describe('findFeatures', () => {
    it('finds a screen by its name', () => {
        expect(findFeatures(admin, 'budget check')[0].path).toBe('/budget/check');
    });

    it('finds a screen through a synonym', () => {
        expect(findFeatures(admin, 'cheques').map(h => h.path)).toContain('/accounting/cheque-register');
    });

    it('never returns a screen the user cannot see', () => {
        const plain = buildFeatureIndex({ viewer: { user: user(), loading: false }, modules: all });
        expect(findFeatures(plain, 'appropriations').map(h => h.path)).not.toContain('/budget/appropriations');
    });

    it('never offers the superadmin console', () => {
        const su = buildFeatureIndex({ viewer: { user: user({ is_superuser: true }), loading: false }, modules: all });
        expect(su.map(f => f.path)).not.toContain('/superadmin');
    });
});
