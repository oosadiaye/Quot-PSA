/**
 * Tenant resolver — derives the active tenant domain from the URL.
 *
 * Subdomain-based tenancy: each tenant lives at
 * ``<slug>.erp.tryquot.com`` (or whatever ``VITE_TENANT_BASE`` points
 * at in non-production environments). This helper inspects
 * ``window.location.hostname`` and decides whether the current request
 * is on a tenant subdomain or on the apex / superadmin host.
 *
 * Resolution order (highest priority wins):
 *   1. Hostname matches ``<slug>.<base>`` → use the hostname directly.
 *   2. Hostname is in ``APEX_HOSTS`` (apex, ``admin.<base>``, ``localhost``,
 *      etc.) → no tenant on URL; fall back to localStorage.
 *   3. Otherwise → treat as legacy (existing ``*.dtsg.test`` etc.) and
 *      use the hostname as-is. The backend's ``TenantHeaderMiddleware``
 *      already accepts any registered Domain row, so legacy URLs keep
 *      working through the migration window.
 */

// Read the apex base from build-time env so dev (``localhost``) and
// prod (``erp.tryquot.com``) get different defaults without code change.
const TENANT_BASE: string =
    (import.meta as unknown as { env?: Record<string, string> }).env
        ?.VITE_TENANT_BASE?.trim() || 'erp.tryquot.com';

// Hostnames that explicitly do NOT carry a tenant. We treat the apex
// itself + the conventional ``admin.<apex>`` as superadmin/landing
// territory. ``localhost`` and 127.0.0.1 are dev defaults.
const APEX_HOSTS: ReadonlySet<string> = new Set([
    TENANT_BASE,
    `admin.${TENANT_BASE}`,
    'localhost',
    '127.0.0.1',
]);


export interface TenantContext {
    /** True when the current URL is a tenant subdomain. */
    isTenantSubdomain: boolean;
    /** True when the current URL is the apex or admin host. */
    isApex: boolean;
    /**
     * Hostname-derived tenant domain (sent as ``X-Tenant-Domain``
     * header) when ``isTenantSubdomain`` is true; ``null`` on apex.
     */
    tenantDomain: string | null;
    /** Just the slug portion when on a subdomain — e.g. ``oag-delta``. */
    tenantSlug: string | null;
}


export function resolveTenantContext(hostname: string = window.location.hostname): TenantContext {
    const host = hostname.toLowerCase().replace(/:\d+$/, ''); // strip port

    // Apex / admin / localhost — no tenant on URL.
    if (APEX_HOSTS.has(host)) {
        return { isTenantSubdomain: false, isApex: true, tenantDomain: null, tenantSlug: null };
    }

    // ``<slug>.<base>`` — tenant subdomain on the configured apex.
    if (host.endsWith(`.${TENANT_BASE}`)) {
        const slug = host.slice(0, -`.${TENANT_BASE}`.length);
        // Reject ``<empty>.<base>`` (would mean host === ``.<base>``,
        // which shouldn't happen but guard anyway).
        if (slug && !slug.includes('.')) {
            return {
                isTenantSubdomain: true,
                isApex: false,
                tenantDomain: host,
                tenantSlug: slug,
            };
        }
    }

    // Legacy / unknown hostname (e.g. ``*.dtsg.test``, ``*.localhost``,
    // a custom domain). The backend's middleware accepts any
    // registered Domain row, so we hand the raw hostname through and
    // let the server validate.
    return {
        isTenantSubdomain: true,
        isApex: false,
        tenantDomain: host,
        tenantSlug: null,
    };
}


/**
 * Returns the tenant domain string the API client should send as
 * ``X-Tenant-Domain``, applying the URL-first / localStorage-fallback
 * rule. URL wins when present so a multi-tenant user can't have a
 * stale localStorage value override the explicit subdomain.
 */
export function getActiveTenantDomain(): string | null {
    const ctx = resolveTenantContext();
    if (ctx.tenantDomain) return ctx.tenantDomain;
    const stored =
        localStorage.getItem('tenantDomain') ?? sessionStorage.getItem('tenantDomain');
    if (stored && stored !== 'null' && stored !== 'undefined') return stored;
    return null;
}
