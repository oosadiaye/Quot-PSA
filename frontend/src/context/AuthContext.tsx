import React, { createContext, useContext, useState, useCallback, useEffect, useMemo } from 'react';

interface UserInfo {
    id: number;
    username: string;
    email: string;
    first_name: string;
    last_name: string;
    is_superuser?: boolean;
}

interface TenantInfo {
    id: number;
    name: string;
    domain: string;
    role: string;
}

const ROLE_HIERARCHY: Record<string, number> = {
    admin: 5,
    senior_manager: 4,
    manager: 3,
    user: 2,
    viewer: 1,
};

interface AuthState {
    user: UserInfo | null;
    tenantInfo: TenantInfo | null;
    tenantRole: string | null;
    permissions: string[];
    isAuthenticated: boolean;
    hasPermission: (perm: string) => boolean;
    hasRole: (minRole: string) => boolean;
    setAuthData: (user: UserInfo, token: string, rememberMe?: boolean) => void;
    setTenantData: (tenant: TenantInfo, permissions: string[]) => void;
    logout: () => void;
}

// Helper: get the active storage backend (localStorage if remembered, sessionStorage otherwise)
function getStorage(): Storage {
    // If sessionStorage has the token, the user chose not to be remembered
    if (sessionStorage.getItem('authToken')) return sessionStorage;
    return localStorage;
}

// Helper: read a value from whichever storage has it
function getStored(key: string): string | null {
    return localStorage.getItem(key) ?? sessionStorage.getItem(key);
}

const AuthContext = createContext<AuthState | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    const [user, setUser] = useState<UserInfo | null>(() => {
        try {
            const raw = getStored('user');
            return raw ? JSON.parse(raw) : null;
        } catch { return null; }
    });

    const [tenantInfo, setTenantInfo] = useState<TenantInfo | null>(() => {
        try {
            const raw = getStored('tenantInfo');
            return raw ? JSON.parse(raw) : null;
        } catch { return null; }
    });

    const [permissions, setPermissions] = useState<string[]>(() => {
        try {
            const raw = getStored('tenantPermissions');
            return raw ? JSON.parse(raw) : [];
        } catch { return []; }
    });

    const isAuthenticated = !!getStored('authToken') && !!user;
    const tenantRole = tenantInfo?.role ?? null;

    const hasPermission = useCallback((perm: string): boolean => {
        if (!user) return false;
        if (perm === 'is_superuser') return user.is_superuser === true;
        if (user.is_superuser) return true;
        if (tenantRole === 'admin') return true;
        if (permissions.includes('__all__')) return true;
        return permissions.includes(perm);
    }, [user, tenantRole, permissions]);

    const hasRole = useCallback((minRole: string): boolean => {
        if (!tenantRole) return false;
        if (user?.is_superuser) return true;
        const currentLevel = ROLE_HIERARCHY[tenantRole] ?? 0;
        const requiredLevel = ROLE_HIERARCHY[minRole] ?? 0;
        return currentLevel >= requiredLevel;
    }, [tenantRole, user]);

    const setAuthData = useCallback((newUser: UserInfo, token: string, rememberMe = true) => {
        // Choose storage based on "Remember Me"
        const store = rememberMe ? localStorage : sessionStorage;
        // Clear the other storage to avoid conflicts
        const other = rememberMe ? sessionStorage : localStorage;
        other.removeItem('authToken');
        other.removeItem('user');

        store.setItem('authToken', token);
        store.setItem('user', JSON.stringify(newUser));

        // Save/clear remembered username for pre-filling login form
        if (rememberMe) {
            localStorage.setItem('rememberedUser', newUser.username || newUser.email);
        } else {
            localStorage.removeItem('rememberedUser');
        }

        setUser(newUser);
    }, []);

    const setTenantData = useCallback((tenant: TenantInfo, perms: string[]) => {
        const store = getStorage();
        store.setItem('tenantDomain', tenant.domain);
        store.setItem('tenantInfo', JSON.stringify(tenant));
        store.setItem('tenantPermissions', JSON.stringify(perms));
        // activeTenant drives the "Organization" display in Dashboard
        store.setItem('activeTenant', tenant.name || tenant.domain);
        setTenantInfo(tenant);
        setPermissions(perms);
    }, []);

    const logout = useCallback(() => {
        // Clear auth data from both storages
        const keys = ['authToken', 'user', 'tenantDomain', 'tenantInfo',
                      'tenantPermissions', 'activeTenant', 'impersonation'];
        for (const key of keys) {
            localStorage.removeItem(key);
            sessionStorage.removeItem(key);
        }
        // Keep 'rememberedUser' in localStorage — it should survive logout
        setUser(null);
        setTenantInfo(null);
        setPermissions([]);
    }, []);

    // Sync with storage changes from other tabs (localStorage only — sessionStorage doesn't fire cross-tab)
    useEffect(() => {
        const handler = (e: StorageEvent) => {
            if (e.key === 'authToken' && !e.newValue) {
                logout();
            }
        };
        window.addEventListener('storage', handler);
        return () => window.removeEventListener('storage', handler);
    }, [logout]);

    const value = useMemo(() => ({
        user, tenantInfo, tenantRole, permissions, isAuthenticated,
        hasPermission, hasRole, setAuthData, setTenantData, logout,
    }), [user, tenantInfo, tenantRole, permissions, isAuthenticated,
        hasPermission, hasRole, setAuthData, setTenantData, logout]);

    return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export const useAuth = (): AuthState => {
    const ctx = useContext(AuthContext);
    if (!ctx) throw new Error('useAuth must be used within an AuthProvider');
    return ctx;
};

export default AuthContext;
