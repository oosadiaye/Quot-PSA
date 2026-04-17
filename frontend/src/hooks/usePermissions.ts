import { useQuery } from '@tanstack/react-query';
import apiClient from '../api/client';

export interface UserPermissions {
    id: number;
    username: string;
    email: string;
    first_name: string;
    last_name: string;
    is_superuser?: boolean;
    groups: string[];
    permissions: string[];
    tenant_role?: string | null;
    tenant_permissions?: string[];
}

/** Read user data stored in localStorage during login as a fallback. */
const getLocalUser = (): UserPermissions | null => {
    try {
        const raw = localStorage.getItem('user');
        return raw ? JSON.parse(raw) : null;
    } catch {
        return null;
    }
};

export const usePermissions = () => {
    return useQuery<UserPermissions>({
        queryKey: ['user-permissions'],
        queryFn: async () => {
            try {
                const response = await apiClient.get('/core/users/me/');
                return response.data;
            } catch {
                // Backend unreachable — fall back to localStorage user data from login
                const local = getLocalUser();
                if (local) return local;
                throw new Error('No user data available');
            }
        },
        staleTime: 1000 * 60 * 5,
        gcTime: 1000 * 60 * 10,
        retry: false,
        // Seed initial data from localStorage so the UI renders immediately
        placeholderData: () => getLocalUser() ?? undefined,
    });
};

/**
 * Check if user has a specific permission.
 * - 'is_superuser' is a pseudo-permission that only checks the superuser flag.
 * - Superusers (is_superuser === true) have all permissions.
 * - Tenant admins (role === 'admin' in tenantInfo) see all module menus.
 * - Otherwise checks the permissions array from the API.
 */
export const hasPermission = (user: UserPermissions | undefined | null, permissionCodename: string): boolean => {
    if (!user) return false;

    // Special pseudo-permission: only superusers pass this check
    if (permissionCodename === 'is_superuser') {
        return user.is_superuser === true;
    }

    // Superuser bypass — all real permissions granted
    if (user.is_superuser) return true;

    // Tenant admin bypass — check API response first, then localStorage
    if (user.tenant_role === 'admin') return true;
    try {
        const tenantInfoStr = localStorage.getItem('tenantInfo');
        if (tenantInfoStr) {
            const tenantInfo = JSON.parse(tenantInfoStr);
            if (tenantInfo.role === 'admin') return true;
        }
    } catch { /* ignore parse errors */ }

    // Check tenant-scoped permissions (from API response first, then localStorage)
    if (user.tenant_permissions && Array.isArray(user.tenant_permissions)) {
        if (user.tenant_permissions.includes('__all__')) return true;
        if (user.tenant_permissions.includes(permissionCodename)) return true;
    }
    try {
        const tenantPermsStr = localStorage.getItem('tenantPermissions');
        if (tenantPermsStr) {
            const tenantPerms: string[] = JSON.parse(tenantPermsStr);
            if (tenantPerms.includes('__all__')) return true;
            if (tenantPerms.includes(permissionCodename)) return true;
        }
    } catch { /* ignore parse errors */ }

    // Fallback: check user-level permissions array
    if (!user.permissions || !Array.isArray(user.permissions)) return false;
    return user.permissions.includes(permissionCodename);
};
