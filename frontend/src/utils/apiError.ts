/**
 * apiError.ts — centralise how we extract a readable message from
 * an axios / fetch error response.
 *
 * DRF serialises common failure bodies in several shapes:
 *   · PermissionDenied     → { "detail": "..." }
 *   · NotAuthenticated     → { "detail": "..." }
 *   · ViewSet 400 errors   → { "error": "..." }   (our own convention)
 *   · ValidationError      → { "field": ["..."], "non_field_errors": ["..."] }
 *   · Plain string         → "..."
 *
 * `formatApiError` prepends a status-specific prefix so users can
 * distinguish authorisation failures (401/403) from validation failures
 * (400) from genuine server errors (5xx) at a glance.
 */

export function formatApiError(error: any, fallback = 'Action failed'): string {
    const resp = error?.response;
    if (!resp) {
        // Network / no response
        return `Network error — ${error?.message || fallback}. Check your connection.`;
    }
    const status = resp.status;
    const data = resp.data;

    // Extract the most specific reason available
    const reason =
        data?.detail ||
        data?.error ||
        data?.message ||
        (Array.isArray(data?.non_field_errors) && data.non_field_errors[0]) ||
        (typeof data === 'string' ? data : null) ||
        flattenFieldErrors(data);

    let prefix = '';
    if (status === 401) prefix = 'Not signed in — ';
    else if (status === 403) prefix = 'Not authorised — ';
    else if (status === 400) prefix = 'Validation failed — ';
    else if (status === 404) prefix = 'Not found — ';
    else if (status === 409) prefix = 'Conflict — ';
    else if (status === 429) prefix = 'Rate limit reached — ';
    else if (status >= 500) prefix = 'Server error — ';

    return prefix + (reason || error?.message || fallback);
}

/**
 * Flatten DRF field-level validation errors into a single readable line.
 * Returns null if there are no field errors.
 */
function flattenFieldErrors(data: any): string | null {
    if (!data || typeof data !== 'object') return null;
    const parts: string[] = [];
    for (const [field, value] of Object.entries(data)) {
        if (field === 'detail' || field === 'error' || field === 'message') continue;
        if (Array.isArray(value)) {
            parts.push(`${field}: ${value.join(' ')}`);
        } else if (typeof value === 'string') {
            parts.push(`${field}: ${value}`);
        }
    }
    return parts.length ? parts.join(' · ') : null;
}
