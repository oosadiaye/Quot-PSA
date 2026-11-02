import { beforeEach, describe, expect, it } from 'vitest';
import { isModuleEnabled, isNavItemVisible, menuItems, type MenuItem } from '../navigation';
import type { UserPermissions } from '../../hooks/usePermissions';

const user = (over: Partial<UserPermissions> = {}): UserPermissions => ({
    id: 1, username: 'ada', email: 'a@b.co', first_name: 'Ada', last_name: 'L',
    groups: [], permissions: [], tenant_permissions: [], ...over,
});
const find = (name: string): MenuItem => menuItems.find(m => m.name === name)!;
const ready = { loading: false };

describe('isModuleEnabled', () => {
    it('is on for an entry that belongs to no module', () => {
        expect(isModuleEnabled(null, { enabledModules: { budget: false }, loading: false })).toBe(true);
    });

    it('counts unknown or still-loading module data as on, so a slow response never blanks the menu', () => {
        expect(isModuleEnabled('budget', { enabledModules: undefined, loading: false })).toBe(true);
        expect(isModuleEnabled('budget', { enabledModules: null, loading: false })).toBe(true);
        expect(isModuleEnabled('budget', { enabledModules: { budget: false }, loading: true })).toBe(true);
    });

    it('treats an empty module list as "everything on"', () => {
        expect(isModuleEnabled('budget', { enabledModules: {}, loading: false })).toBe(true);
    });

    it('with an explicit list, only modules set to true are on', () => {
        const modules = { enabledModules: { accounting: true, budget: false }, loading: false };
        expect(isModuleEnabled('accounting', modules)).toBe(true);
        expect(isModuleEnabled('budget', modules)).toBe(false);
        expect(isModuleEnabled('treasury', modules)).toBe(false); // absent from an explicit list = off
    });
});

describe('isNavItemVisible', () => {
    beforeEach(() => localStorage.clear());
    const everything = { enabledModules: {}, loading: false };

    it('always shows an entry that needs no permission', () => {
        expect(isNavItemVisible(find('Dashboard'), { user: user(), ...ready }, everything)).toBe(true);
    });

    it('hides an entry whose permission the user lacks, shows it when they have it', () => {
        const budget = find('Budget & Appropriation');
        expect(isNavItemVisible(budget, { user: user(), ...ready }, everything)).toBe(false);
        expect(isNavItemVisible(budget, { user: user({ tenant_permissions: ['view_budget'] }), ...ready }, everything)).toBe(true);
    });

    it('lets tenant admins and superusers through', () => {
        const budget = find('Budget & Appropriation');
        expect(isNavItemVisible(budget, { user: user({ tenant_role: 'admin' }), ...ready }, everything)).toBe(true);
        expect(isNavItemVisible(budget, { user: user({ is_superuser: true }), ...ready }, everything)).toBe(true);
    });

    it('keeps System Admin for superusers only, even for a tenant admin', () => {
        expect(isNavItemVisible(find('System Admin'), { user: user({ tenant_role: 'admin' }), ...ready }, everything)).toBe(false);
        expect(isNavItemVisible(find('System Admin'), { user: user({ is_superuser: true }), ...ready }, everything)).toBe(true);
    });

    it('shows everything while permissions are loading or the user is unknown', () => {
        const budget = find('Budget & Appropriation');
        expect(isNavItemVisible(budget, { user: undefined, loading: true }, everything)).toBe(true);
        expect(isNavItemVisible(budget, { user: null, loading: false }, everything)).toBe(true);
    });

    it('hides an entry whose module is switched off, whatever the user may do', () => {
        const budget = find('Budget & Appropriation');
        const noBudget = { enabledModules: { accounting: true, budget: false }, loading: false };
        expect(isNavItemVisible(budget, { user: user({ is_superuser: true }), ...ready }, noBudget)).toBe(false);
    });
});

describe('the menu itself', () => {
    it('has an absolute path on every entry and no icon missing', () => {
        for (const item of menuItems) {
            expect(item.path.startsWith('/'), item.name).toBe(true);
            expect(item.icon, item.name).toBeTruthy();
            for (const sub of item.subItems ?? []) {
                expect(sub.path.startsWith('/'), `${item.name} > ${sub.name}`).toBe(true);
                expect(sub.icon, `${item.name} > ${sub.name}`).toBeTruthy();
            }
        }
    });

    it('lists no screen twice within one menu', () => {
        for (const item of menuItems) {
            const keys = (item.subItems ?? []).map(s => `${s.name}|${s.path}`);
            expect(new Set(keys).size, item.name).toBe(keys.length);
        }
    });

    it('still contains the screens the user guide sends people to', () => {
        const trails = menuItems.flatMap(m => (m.subItems ?? []).map(s => `${m.name} > ${s.name}`));
        expect(trails).toEqual(expect.arrayContaining([
            'Budget & Appropriation > Appropriations',
            'Budget & Appropriation > Budget Check',
            'Treasury & Banking > Payment Proposal',
            'Treasury & Banking > Outgoing Payments',
            'Administration > User Management',
        ]));
    });
});
