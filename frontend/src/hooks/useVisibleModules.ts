import { useMemo } from 'react';
import { menuItems, isNavItemVisible, type MenuItem } from '../config/navigation';
import { usePermissions } from './usePermissions';
import { useTenantModules } from './useTenantModules';

/**
 * The modules the signed-in user may open: the same rule the Ask AI finder uses, so the launcher, the menu bar and the finder
 * can never disagree about what a user may open.
 */
export function useVisibleModules(): MenuItem[] {
  const { data: user, isLoading: permLoading } = usePermissions();
  const { data: tenantModules, isLoading: modulesLoading } = useTenantModules();
  const enabled = tenantModules?.enabled_modules;
  return useMemo(
    () => menuItems.filter((item) => isNavItemVisible(
      item,
      { user, loading: permLoading },
      { enabledModules: enabled, loading: modulesLoading },
    )),
    [user, permLoading, enabled, modulesLoading],
  );
}
