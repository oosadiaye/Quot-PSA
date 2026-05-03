/**
 * Cross-host tenant bootstrap consumer.
 *
 * When the apex login page redirects a user to their tenant subdomain
 * after picking an organisation, it appends auth state to the URL
 * fragment because ``localStorage`` doesn't travel across origins.
 * Fragment shape (set by ``Login.tsx::selectTenantAndNavigate``):
 *
 *   #t=<authToken>&u=<base64(userJson)>&d=<tenantDomain>
 *    &tn=<tenantName>&r=<role>&p=<base64(permissionsJson)>
 *
 * On every app mount we run ``consumeTenantBootstrap()`` BEFORE
 * React renders. If a bootstrap fragment is present we copy it into
 * ``localStorage`` and replace the URL via ``history.replaceState``
 * so the token never appears in browser history or referrer headers.
 *
 * Idempotent: running twice on the same page is a no-op because the
 * fragment is stripped on the first call.
 */

export interface BootstrapResult {
    /** True when a bootstrap fragment was found and consumed. */
    bootstrapped: boolean;
    /** Tenant domain copied into storage, if any. */
    tenantDomain?: string;
}


function safeAtob(s: string): string | null {
    try {
        // ``decodeURIComponent(escape(...))`` reverses the
        // ``encodeURIComponent(unescape(btoa(...)))`` used at the
        // sender side to round-trip multi-byte UTF-8 safely.
        return decodeURIComponent(escape(atob(s)));
    } catch {
        return null;
    }
}


export function consumeTenantBootstrap(): BootstrapResult {
    if (typeof window === 'undefined') return { bootstrapped: false };
    const hash = window.location.hash.replace(/^#/, '');
    if (!hash || !hash.includes('t=')) return { bootstrapped: false };

    let params: URLSearchParams;
    try {
        params = new URLSearchParams(hash);
    } catch {
        return { bootstrapped: false };
    }

    const token = params.get('t');
    const userB64 = params.get('u');
    const domain = params.get('d');
    const tenantName = params.get('tn') || '';
    const role = params.get('r') || '';
    const permsB64 = params.get('p');

    // Require at minimum the token + tenant domain — anything less
    // means this isn't actually a bootstrap fragment (could be a
    // legitimate in-app anchor like ``#section-2``).
    if (!token || !domain) return { bootstrapped: false };

    // Persist into the destination subdomain's localStorage so all
    // subsequent React Query / axios calls behave as if the user
    // logged in directly on this hostname.
    localStorage.setItem('authToken', token);
    localStorage.setItem('tenantDomain', domain);
    localStorage.setItem('activeTenant', tenantName || domain);

    if (userB64) {
        const userJson = safeAtob(userB64);
        if (userJson) localStorage.setItem('user', userJson);
    }

    const tenantInfo = {
        domain,
        name: tenantName,
        role: role || null,
    };
    localStorage.setItem('tenantInfo', JSON.stringify(tenantInfo));

    if (permsB64) {
        try {
            const permsJson = atob(permsB64);
            // Validate it's parseable JSON before storing.
            JSON.parse(permsJson);
            localStorage.setItem('tenantPermissions', permsJson);
        } catch {
            /* ignore — permissions get re-fetched by useUserBootstrap */
        }
    }

    // Strip the fragment so the token never sits in browser history
    // or the document.referrer of subsequent requests. ``replaceState``
    // doesn't trigger navigation so React mounts on a clean URL.
    const cleanUrl = window.location.pathname + window.location.search;
    window.history.replaceState({}, document.title, cleanUrl);

    return { bootstrapped: true, tenantDomain: domain };
}
