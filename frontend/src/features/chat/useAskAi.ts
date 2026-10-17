import { useMemo } from 'react';
import { usePermissions } from '../../hooks/usePermissions';
import { useTenantModules } from '../../hooks/useTenantModules';
import { buildFeatureIndex, type Feature } from './featureIndex';

/**
 * Every screen this user may open, built from the same nav tree and visibility rules as the sidebar,
 * so Ask AI can never point someone at a menu they cannot see.
 */
export function useFeatureIndex(): Feature[] {
    const { data: user, isLoading: permLoading } = usePermissions();
    const { data: tenantModules, isLoading: modulesLoading } = useTenantModules();
    const enabledModules = tenantModules?.enabled_modules;
    return useMemo(
        () => buildFeatureIndex({
            viewer: { user, loading: permLoading },
            modules: { enabledModules, loading: modulesLoading },
        }),
        [user, permLoading, enabledModules, modulesLoading],
    );
}
