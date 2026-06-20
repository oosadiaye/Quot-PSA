import React, { createContext, useState, useCallback, useEffect, useMemo, useRef } from 'react';
import apiClient from '../api/client';

// VITE_AUTH_COOKIE_ONLY is the frontend twin of the backend
// AUTH_COOKIE_ONLY flag. When 'true', the SPA does NOT write the
// auth token to sessionStorage on login and hydrates user state via
// GET /core/users/me/ on mount. Defaults to false during the
// migration window so existing builds keep working unchanged.
const COOKIE_ONLY =
  String(import.meta.env.VITE_AUTH_COOKIE_ONLY ?? 'false').toLowerCase() === 'true';

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

export interface OrganizationInfo {
    id: number;
    name: string;
    code: string;
    short_name: string;
    org_role: 'MDA' | 'BUDGET_AUTHORITY' | 'FINANCE_AUTHORITY' | 'AUDIT_AUTHORITY';
    is_oversight: boolean;
    is_read_only: boolean;
    per_org_role: string;
    is_default: boolean;
}

const ROLE_HIERARCHY: Record<string, number> = {
    admin: 5,
    senior_manager: 4,
    manager: 3,
    user: 2,
    viewer: 1,
};

export interface AuthState {
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
    // Organization (MDA branch) state
    activeOrganization: OrganizationInfo | null;
    userOrganizations: OrganizationInfo[];
    mdaIsolationMode: 'UNIFIED' | 'SEPARATED';
    setActiveOrganization: (org: OrganizationInfo | null) => void;
    setOrganizationList: (orgs: OrganizationInfo[], mode: 'UNIFIED' | 'SEPARATED') => void;
}

// Helper: read a value from whichever storage has it
function getStored(key: string): string | null {
    return localStorage.getItem(key) ?? sessionStorage.getItem(key);
}

// Helpers: write/remove a value to BOTH storages.
//
// We mirror everything so right-click → "Open in new tab" works:
// sessionStorage is per-tab scoped, so a new tab boots empty unless
// localStorage also holds a copy. Hoisted to module scope (rather than
// living inside the AuthProvider component) so they're stable across
// renders and don't pollute useCallback dep arrays.
function writeBoth(key: string, value: string): void {
    localStorage.setItem(key, value);
    sessionStorage.setItem(key, value);
}
function removeBoth(key: string): void {
    localStorage.removeItem(key);
    sessionStorage.removeItem(key);
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

    const [activeOrganization, setActiveOrgState] = useState<OrganizationInfo | null>(() => {
        try {
            const raw = getStored('activeOrganization');
            return raw ? JSON.parse(raw) : null;
        } catch { return null; }
    });

    const [userOrganizations, setUserOrganizations] = useState<OrganizationInfo[]>(() => {
        try {
            const raw = getStored('userOrganizations');
            return raw ? JSON.parse(raw) : [];
        } catch { return []; }
    });

    const [mdaIsolationMode, setMdaIsolationMode] = useState<'UNIFIED' | 'SEPARATED'>(() => {
        return (getStored('mdaIsolationMode') as 'UNIFIED' | 'SEPARATED') || 'UNIFIED';
    });

    // ── Cross-tab boot phase (right-click → "Open link in new tab") ──
    //
    // sessionStorage is per-tab scoped, so a freshly-opened tab boots
    // with the user JSON mirrored from localStorage but NO ``authToken``.
    // The BroadcastChannel handshake below would deliver the token from
    // the sibling tab — but only AFTER the first React render, so any
    // child API call fires synchronously without an ``Authorization``
    // header and gets a 401 → bounce to login.
    //
    // Fix: when we detect this state on mount (user present, token
    // absent, BroadcastChannel available), short-circuit rendering to
    // a "Restoring session…" placeholder for up to 600ms. The handshake
    // either succeeds (token lands in sessionStorage, flag cleared,
    // children mount with a valid token) or times out (we fall through
    // to the unauthenticated path and the user lands on /login cleanly).
    const initialAuthToken = (typeof window !== 'undefined')
        ? sessionStorage.getItem('authToken')
        : null;
    const needsCrossTabBoot = !!user && !initialAuthToken
        && typeof BroadcastChannel !== 'undefined';
    const [restoringFromSibling, setRestoringFromSibling] = useState<boolean>(
        needsCrossTabBoot,
    );

    // Derive auth state from the ``user`` state variable only — NOT
    // from synchronous storage reads. ``user`` is set via
    // ``setAuthData`` only after the token was persisted, and cleared
    // via ``logout`` immediately after the token is removed. Tying
    // ``isAuthenticated`` to a storage read produces a one-render
    // window where storage was just cleared but state hasn't flushed,
    // so consumers see ``isAuthenticated=true`` momentarily after a
    // 401 logout. Sourcing it from ``user`` makes it fully reactive
    // and eliminates that desync.
    const isAuthenticated = !!user;
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
        // Always mirror auth to BOTH storages so right-click → "Open in
        // new tab" works regardless of the Remember Me toggle. The
        // previous design wrote only to sessionStorage when rememberMe
        // was false, which made multi-tab navigation impossible
        // (sessionStorage is per-tab scoped) — every new tab bounced
        // to /login because storage was empty.
        //
        // The session-vs-persistent distinction doesn't really need
        // storage segregation here: real security relies on server-side
        // token expiry, and the previous "session-only" guarantee was
        // already approximate (closing one tab didn't clear other
        // tabs; full browser exit is only reliable on some platforms).
        // Mirroring to both storages is the standard SaaS pattern.
        //
        // ``rememberMe`` is preserved as the gate for username
        // pre-fill on the login screen (``rememberedUser``) so users
        // who explicitly opt out of being recognised by username still
        // get that — they just won't lose their session when right-
        // clicking a link.
        // Auth token is sessionStorage-only — localStorage is XSS-readable
        // for the lifetime of the browser profile. ``user`` is mirrored
        // to both storages because it's non-sensitive (display name /
        // role) and the right-click → "Open in new tab" UX needs it.
        //
        // COOKIE_ONLY mode: the backend has set an httpOnly cookie so
        // the token never needs to touch storage. Skip the
        // sessionStorage write entirely — the cookie is authoritative
        // and survives navigation natively. We still mirror ``user``
        // (display name / role) for fast first-render and for the
        // multi-tab "right-click open in new tab" UX.
        if (!COOKIE_ONLY) {
            sessionStorage.setItem('authToken', token);
        }
        sessionStorage.setItem('user', JSON.stringify(newUser));
        localStorage.setItem('user', JSON.stringify(newUser));

        // Save/clear remembered username for pre-filling login form
        if (rememberMe) {
            localStorage.setItem('rememberedUser', newUser.username || newUser.email);
        } else {
            localStorage.removeItem('rememberedUser');
        }

        setUser(newUser);
    }, []);

    // ``writeBoth`` / ``removeBoth`` live at module scope above so
    // they're stable references and don't dirty useCallback deps.
    const setTenantData = useCallback((tenant: TenantInfo, perms: string[]) => {
        writeBoth('tenantDomain', tenant.domain);
        writeBoth('tenantInfo', JSON.stringify(tenant));
        writeBoth('tenantPermissions', JSON.stringify(perms));
        // activeTenant drives the "Organization" display in Dashboard
        writeBoth('activeTenant', tenant.name || tenant.domain);
        setTenantInfo(tenant);
        setPermissions(perms);
    }, []);

    const setActiveOrganization = useCallback((org: OrganizationInfo | null) => {
        if (org) {
            writeBoth('activeOrganization', JSON.stringify(org));
        } else {
            removeBoth('activeOrganization');
        }
        setActiveOrgState(org);
    }, []);

    const setOrganizationList = useCallback((orgs: OrganizationInfo[], mode: 'UNIFIED' | 'SEPARATED') => {
        writeBoth('userOrganizations', JSON.stringify(orgs));
        writeBoth('mdaIsolationMode', mode);
        setUserOrganizations(orgs);
        setMdaIsolationMode(mode);
    }, []);

    const logout = useCallback(() => {
        // Hit the server logout endpoint so the backend deletes both
        // the auth token (server-side) AND the httpOnly cookie
        // (Set-Cookie max-age=0). Fire-and-forget — if it fails the
        // local state is still cleared below and the token will be
        // garbage-collected by the next expiry sweep.
        apiClient.post('/core/auth/logout/').catch(() => {
            /* swallow — local cleanup below is the source of truth */
        });
        // Clear auth data from both storages
        const keys = ['authToken', 'user', 'tenantDomain', 'tenantInfo',
                      'tenantPermissions', 'activeTenant', 'impersonation',
                      'activeOrganization', 'userOrganizations', 'mdaIsolationMode'];
        for (const key of keys) {
            localStorage.removeItem(key);
            sessionStorage.removeItem(key);
        }
        // Keep 'rememberedUser' in localStorage — it should survive logout
        setUser(null);
        setTenantInfo(null);
        setPermissions([]);
        setActiveOrgState(null);
        setUserOrganizations([]);
        setMdaIsolationMode('UNIFIED');
    }, []);

    // ── Cookie-only hydration ─────────────────────────────────────────
    //
    // In cookie-only mode the SPA has no token in storage to detect
    // "am I logged in?". On mount we ping /core/users/me/ — if the
    // browser holds the httpOnly auth cookie the request succeeds
    // and we hydrate ``user`` from the response. 401 means anonymous
    // and we leave state empty (ProtectedRoute redirects to /login).
    //
    // Skipped entirely when COOKIE_ONLY is false: the legacy storage-
    // read path already hydrated ``user`` synchronously above.
    useEffect(() => {
        if (!COOKIE_ONLY) return;
        if (user) return;  // already hydrated from a previous mount cycle
        let cancelled = false;
        apiClient.get('/core/users/me/').then((res) => {
            if (cancelled) return;
            const data = res.data || {};
            // Shape parity with login response — username/email/etc.
            setUser({
                id: data.id,
                username: data.username,
                email: data.email,
                first_name: data.first_name,
                last_name: data.last_name,
                is_superuser: data.is_superuser,
            });
        }).catch(() => {
            /* 401/network — leave state empty, user is anonymous */
        });
        return () => { cancelled = true; };
    }, [user]);

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

    // Same-tab token expiry: ``apiClient`` dispatches ``auth-expired``
    // when a 401 lands. The ``storage`` event above doesn't fire in
    // the same tab that cleared the token, so without this listener
    // the user state would persist after a session-expired response
    // and ``isAuthenticated`` would briefly remain true.
    useEffect(() => {
        const handler = () => logout();
        window.addEventListener('auth-expired', handler);
        return () => window.removeEventListener('auth-expired', handler);
    }, [logout]);

    // ── Cross-tab auth sync via BroadcastChannel ─────────────────────
    //
    // Why this exists: when ``rememberMe`` is unchecked, ``setAuthData``
    // writes the token to ``sessionStorage``, which is per-tab scoped.
    // Right-click → "Open in new tab" gives the new tab an empty
    // ``sessionStorage``, so without this handshake ``ProtectedRoute``
    // would correctly but unhelpfully bounce the user to /login even
    // though they're authenticated in the parent tab.
    //
    // Protocol:
    //   • Every AuthProvider instance subscribes to ``quot-auth``.
    //   • On mount, if the local user state is null, the new tab
    //     posts ``request-auth-state``. Sibling tabs respond with
    //     ``auth-state`` carrying their token + tenant info. The new
    //     tab writes those into its ``sessionStorage``, sets the React
    //     state, and dispatches a ``storage`` event so ProtectedRoute
    //     re-runs its check. If no sibling answers within ~250ms, the
    //     new tab falls through to its empty-storage code path and
    //     correctly redirects to login (genuine cold-start).
    //   • On logout, the originating tab posts ``logout-sync`` so
    //     siblings clear their state too — closing one tab shouldn't
    //     leave another tab logged in if the user explicitly signed out.
    //
    // BroadcastChannel is supported in every modern browser (Chrome 54,
    // Firefox 38, Safari 15.4, Edge 79+). We feature-detect with a
    // typeof check so older browsers degrade gracefully.
    useEffect(() => {
        if (typeof BroadcastChannel === 'undefined') return;
        // COOKIE_ONLY: the httpOnly cookie is shared natively across
        // tabs in the same browser profile so we don't need to replay
        // the token via BroadcastChannel. Skip the whole handshake to
        // avoid race conditions between the /me/ hydration and an
        // older sibling tab broadcasting stale storage values.
        if (COOKIE_ONLY) return;
        const channel = new BroadcastChannel('quot-auth');

        type SyncMessage =
            | { type: 'request-auth-state' }
            | {
                  type: 'auth-state';
                  token: string;
                  user: string;
                  tenantInfo?: string;
                  tenantPermissions?: string;
                  tenantDomain?: string;
                  activeTenant?: string;
                  activeOrganization?: string;
                  userOrganizations?: string;
                  mdaIsolationMode?: string;
              }
            | { type: 'logout-sync' };

        const onMessage = (event: MessageEvent<SyncMessage>) => {
            const msg = event.data;
            if (!msg || typeof msg !== 'object') return;

            if (msg.type === 'request-auth-state') {
                // Only respond when we actually have an authenticated state
                // — otherwise we'd echo emptiness back at the asker.
                const token = sessionStorage.getItem('authToken');
                if (!token) return;
                const userRaw = localStorage.getItem('user')
                    ?? sessionStorage.getItem('user');
                if (!userRaw) return;
                channel.postMessage({
                    type: 'auth-state',
                    token,
                    user: userRaw,
                    tenantInfo:
                        localStorage.getItem('tenantInfo')
                        ?? sessionStorage.getItem('tenantInfo')
                        ?? undefined,
                    tenantPermissions:
                        localStorage.getItem('tenantPermissions')
                        ?? sessionStorage.getItem('tenantPermissions')
                        ?? undefined,
                    tenantDomain:
                        localStorage.getItem('tenantDomain')
                        ?? sessionStorage.getItem('tenantDomain')
                        ?? undefined,
                    activeTenant:
                        localStorage.getItem('activeTenant')
                        ?? sessionStorage.getItem('activeTenant')
                        ?? undefined,
                    activeOrganization:
                        localStorage.getItem('activeOrganization')
                        ?? sessionStorage.getItem('activeOrganization')
                        ?? undefined,
                    userOrganizations:
                        localStorage.getItem('userOrganizations')
                        ?? sessionStorage.getItem('userOrganizations')
                        ?? undefined,
                    mdaIsolationMode:
                        localStorage.getItem('mdaIsolationMode')
                        ?? sessionStorage.getItem('mdaIsolationMode')
                        ?? undefined,
                } satisfies SyncMessage);
            } else if (msg.type === 'auth-state') {
                // Validate incoming shape — any other origin posting on
                // the same channel name (or a malicious extension) could
                // forge a message. Require ``token`` to be a non-empty
                // string and ``user`` to be a JSON-parseable object.
                if (typeof msg.token !== 'string' || !msg.token) return;
                if (typeof msg.user !== 'string' || !msg.user) return;
                let parsedUser: unknown;
                try { parsedUser = JSON.parse(msg.user); }
                catch { return; }
                if (!parsedUser || typeof parsedUser !== 'object') return;

                // Only adopt sibling state if we don't already have our own.
                // Avoids overwriting a freshly-logged-in tab's state with a
                // stale broadcast from an older sibling.
                if (sessionStorage.getItem('authToken')) {
                    return;
                }
                // Mirror into sessionStorage so the existing storage-read
                // paths (ProtectedRoute, getStored helper, /me/ fetcher)
                // pick it up without any further changes.
                sessionStorage.setItem('authToken', msg.token);
                sessionStorage.setItem('user', msg.user);
                // Token landed — release the cross-tab boot gate so the
                // children mount with a populated sessionStorage.
                setRestoringFromSibling(false);
                if (msg.tenantInfo) sessionStorage.setItem('tenantInfo', msg.tenantInfo);
                if (msg.tenantPermissions) sessionStorage.setItem('tenantPermissions', msg.tenantPermissions);
                if (msg.tenantDomain) sessionStorage.setItem('tenantDomain', msg.tenantDomain);
                if (msg.activeTenant) sessionStorage.setItem('activeTenant', msg.activeTenant);
                if (msg.activeOrganization) sessionStorage.setItem('activeOrganization', msg.activeOrganization);
                if (msg.userOrganizations) sessionStorage.setItem('userOrganizations', msg.userOrganizations);
                if (msg.mdaIsolationMode) sessionStorage.setItem('mdaIsolationMode', msg.mdaIsolationMode);

                // Hydrate React state immediately so consumers re-render.
                try { setUser(JSON.parse(msg.user)); } catch { /* ignore */ }
                if (msg.tenantInfo) {
                    try { setTenantInfo(JSON.parse(msg.tenantInfo)); } catch { /* ignore */ }
                }
                if (msg.tenantPermissions) {
                    try { setPermissions(JSON.parse(msg.tenantPermissions)); } catch { /* ignore */ }
                }
                if (msg.activeOrganization) {
                    try { setActiveOrgState(JSON.parse(msg.activeOrganization)); } catch { /* ignore */ }
                }
                if (msg.userOrganizations) {
                    try { setUserOrganizations(JSON.parse(msg.userOrganizations)); } catch { /* ignore */ }
                }
                if (msg.mdaIsolationMode === 'UNIFIED' || msg.mdaIsolationMode === 'SEPARATED') {
                    setMdaIsolationMode(msg.mdaIsolationMode);
                }
                // Tell ProtectedRoute (and any other listener that
                // re-checks on storage events) to refresh its decision.
                window.dispatchEvent(new Event('auth-restored'));
            } else if (msg.type === 'logout-sync') {
                // A sibling tab logged out — clear our state too.
                logout();
            }
        };
        channel.addEventListener('message', onMessage);

        // If we mounted with no user, ask siblings for their state.
        // No-op in tabs that already have a user — they don't need help.
        // Also fire the request when we're in the cross-tab boot phase
        // (user mirrored from localStorage but token missing in this tab).
        const needsRequest = !user || restoringFromSibling;
        if (needsRequest) {
            channel.postMessage({ type: 'request-auth-state' } satisfies SyncMessage);
        }

        // Safety net: if no sibling responds within 600ms, release the
        // boot gate so the user lands on /login cleanly instead of
        // staring at "Restoring session…" forever. This window is wide
        // enough for typical same-machine BroadcastChannel round-trips
        // (~5-20ms) plus React render headroom on slow devices.
        let bootTimeout: ReturnType<typeof setTimeout> | undefined;
        if (restoringFromSibling) {
            bootTimeout = setTimeout(() => {
                setRestoringFromSibling(false);
            }, 600);
        }

        return () => {
            channel.removeEventListener('message', onMessage);
            channel.close();
            if (bootTimeout) clearTimeout(bootTimeout);
        };
        // We intentionally only run this on mount. ``user`` and
        // ``logout`` are referenced via the closure but their stale
        // values are acceptable here because the handler reads from
        // storage live, and ``logout`` only flips state (no need to
        // rebind on every change).
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    // Broadcast logout intent so other tabs in this browser also clear.
    // Wired as a separate effect that watches ``isAuthenticated`` so we
    // only post when the user transitions from authenticated → null,
    // not on the initial empty state.
    const wasAuthenticated = useRef(isAuthenticated);
    useEffect(() => {
        if (typeof BroadcastChannel === 'undefined') return;
        if (wasAuthenticated.current && !isAuthenticated) {
            const ch = new BroadcastChannel('quot-auth');
            try { ch.postMessage({ type: 'logout-sync' }); } finally { ch.close(); }
        }
        wasAuthenticated.current = isAuthenticated;
    }, [isAuthenticated]);

    const value = useMemo(() => ({
        user, tenantInfo, tenantRole, permissions, isAuthenticated,
        hasPermission, hasRole, setAuthData, setTenantData, logout,
        activeOrganization, userOrganizations, mdaIsolationMode,
        setActiveOrganization, setOrganizationList,
    }), [user, tenantInfo, tenantRole, permissions, isAuthenticated,
        hasPermission, hasRole, setAuthData, setTenantData, logout,
        activeOrganization, userOrganizations, mdaIsolationMode,
        setActiveOrganization, setOrganizationList]);

    // While restoring auth state from a sibling tab, render a tiny
    // placeholder instead of children. This prevents API calls from
    // firing without an Authorization header — which is the exact race
    // that caused "Session expired" on right-click → "Open in new tab".
    // Hard cap is 600ms (see the BroadcastChannel useEffect above).
    if (restoringFromSibling) {
        return (
            <AuthContext.Provider value={value}>
                <div
                    role="status"
                    aria-live="polite"
                    style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        minHeight: '100vh',
                        fontFamily: "'Manrope', system-ui, sans-serif",
                        color: '#0f172a',
                        fontSize: 14,
                    }}
                >
                    Restoring session…
                </div>
            </AuthContext.Provider>
        );
    }

    return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

// ``useAuth`` lives in ``./useAuth`` so this file can export ONLY the
// ``AuthProvider`` component (plus type definitions and the default
// context). Fast-refresh works file-by-file: keeping hooks here would
// force a full page reload on every edit to the provider. Re-exported
// below for backward compatibility — existing consumers that import
// ``useAuth`` from this path continue to work without changes.
export { useAuth } from './useAuth';

export default AuthContext;
