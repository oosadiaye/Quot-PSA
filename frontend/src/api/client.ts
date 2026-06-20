import axios from 'axios';
import logger from '../utils/logger';
import { getActiveTenantDomain } from '../utils/tenantResolver';

const API_BASE_URL = `${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/api/v1`;

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  // ``withCredentials: true`` instructs the browser to attach cookies
  // (and the matching ``Set-Cookie`` round-trip) on cross-origin
  // requests. Required for the httpOnly auth-cookie path — the
  // backend issues ``auth_token`` as an httpOnly cookie when
  // ``AUTH_COOKIE_ENABLED`` is set, and without this flag the
  // browser would silently drop it on the way out.
  //
  // Safe-additive: when the cookie path is OFF the backend doesn't
  // emit a cookie, so this flag costs nothing. When ON, the cookie
  // travels alongside the existing ``Authorization: Token`` header
  // — the backend prefers the header (back-compat) and falls back
  // to the cookie when no header is present.
  //
  // CORS_ALLOW_CREDENTIALS is already True server-side (settings.py).
  withCredentials: true,
});

// Request interceptor — inject auth token & tenant header
apiClient.interceptors.request.use((config) => {
  // Skip auth headers for login/register endpoints to prevent stale tokens
  // from interfering with authentication
  const isAuthEndpoint = config.url?.includes('/auth/login') || config.url?.includes('/auth/register');

  if (!isAuthEndpoint) {
    // Authorization header path — still emitted for the migration
    // window so users who logged in before AUTH_COOKIE_ENABLED was
    // flipped on continue to authenticate. After the migration is
    // complete the sessionStorage read can be deleted; the cookie
    // travels via ``withCredentials: true`` above.
    //
    // ``VITE_AUTH_COOKIE_ONLY`` is the frontend twin of the backend
    // ``AUTH_COOKIE_ONLY`` flag. When True the SPA stops reading from
    // sessionStorage entirely — auth is cookie-only and the backend
    // hydrates state via ``GET /api/v1/core/users/me/``. Defaults to
    // false so existing builds keep working. When the cookie path is
    // active and BOTH are present, the backend prefers the header
    // (back-compat); the cookie kicks in for browsers that never
    // received a body token (cookie-only mode).
    const cookieOnly =
      String(import.meta.env.VITE_AUTH_COOKIE_ONLY ?? 'false').toLowerCase() === 'true';
    if (!cookieOnly) {
      // Auth tokens are stored in sessionStorage only — localStorage is
      // XSS-readable for the lifetime of the browser profile. sessionStorage
      // is still XSS-readable while the tab is open but at least dies with
      // the tab. (httpOnly cookie migration is the proper fix; tracked
      // separately.)
      const token = sessionStorage.getItem('authToken');
      if (token) {
        config.headers['Authorization'] = `Token ${token}`;
      }
    }

    // Tenant resolution: hostname (subdomain) wins over localStorage so
    // a stale tenant value in storage can't shadow an explicit
    // subdomain URL. Apex/admin hosts fall through to the localStorage
    // path, preserving the multi-tenant picker flow for users who
    // have access to more than one organisation.
    const tenantDomain = getActiveTenantDomain();
    if (tenantDomain) {
      config.headers['X-Tenant-Domain'] = tenantDomain;
    }

    // Inject active organization header for MDA-scoped requests
    const orgRaw = localStorage.getItem('activeOrganization') ?? sessionStorage.getItem('activeOrganization');
    if (orgRaw) {
      try {
        const org = JSON.parse(orgRaw);
        if (org?.id) {
          config.headers['X-Organization-Id'] = String(org.id);
        }
      } catch { /* ignore parse errors */ }
    }
  }

  return config;
}, (error) => {
  return Promise.reject(error);
});

// Response interceptor for handling auth errors
apiClient.interceptors.response.use(
  (response) => {
    if (typeof response.data === 'string') {
      try {
        response.data = JSON.parse(response.data);
      } catch {
        // Not JSON, leave as-is
      }
    }
    return response;
  },
  (error) => {
    if (!error.response) {
      logger.error('Network error: Unable to reach server');
      return Promise.reject(new Error('Network error: Unable to reach the server. Please check your connection.'));
    }

    const { status } = error.response;

    if (status === 401) {
      // Check if we're in an impersonation session before clearing auth
      const impersonation = sessionStorage.getItem('impersonation_session');
      if (impersonation) {
        // During impersonation, redirect back to superadmin instead of login
        sessionStorage.removeItem('impersonation_session');
        localStorage.removeItem('impersonation');
        window.location.href = '/superadmin';
      } else {
        // Was the user actually authenticated before this request? A 401 on
        // a fresh visit to /login (or on the boot-time /core/users/me/
        // hydration call that AuthContext fires in cookie-only mode) is the
        // expected response to an anonymous request — NOT a session-expired
        // event. Surfacing the "Your session expired" banner in that case
        // makes first-time visitors think they were timed out.
        //
        // We treat the request as a real expiry only when at least one of
        // these markers existed in storage at the time the request fired:
        //   • ``authToken`` in sessionStorage (the legacy token path), OR
        //   • a ``user`` object in either storage (the cookie-only path —
        //     the cookie itself isn't readable from JS, but ``user`` is
        //     mirrored to localStorage on login).
        const hadToken = !!sessionStorage.getItem('authToken');
        const hadUser =
          !!localStorage.getItem('user') ||
          !!sessionStorage.getItem('user');
        const wasAuthenticated = hadToken || hadUser;

        if (wasAuthenticated) {
          // Clear stale auth data from both storages and notify ProtectedRoute
          // + the Login page (via sessionStorage flag) that the session expired
          // so the user sees an explanatory banner instead of a silent redirect.
          const keys = ['authToken', 'user', 'tenantDomain', 'tenantInfo', 'tenantPermissions'];
          for (const key of keys) {
            localStorage.removeItem(key);
            sessionStorage.removeItem(key);
          }
          // One-shot reason the Login page can read & clear so it knows to show
          // "Your session expired. Please log in again." rather than looking like
          // a spurious logout.
          try {
            sessionStorage.setItem(
              'auth-expired-reason',
              'Your session expired. Please log in again to continue.'
            );
          } catch { /* storage quota / disabled — non-fatal */ }
          // Dispatch event so ProtectedRoute can react without hard redirect
          window.dispatchEvent(new Event('auth-expired'));
        }
        // else: anonymous 401 — caller (Login page, AuthContext /me/
        // hydration) handles its own UX. We just reject below without
        // poisoning sessionStorage with a misleading reason.
      }
    } else if (status === 403) {
      // Permission denied — don't redirect, let the component handle it
    } else if (status >= 500) {
      logger.error('Server error:', error.response.data || 'Internal server error');
    }

    return Promise.reject(error);
  }
);

export default apiClient;
