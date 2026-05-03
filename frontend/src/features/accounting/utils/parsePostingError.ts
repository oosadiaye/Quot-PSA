/**
 * Parses a backend API error response into a single human-readable string.
 *
 * Backend posting endpoints (AP invoice, AR invoice, journal post,
 * payment voucher, PO) return a structured envelope. The most common
 * shapes — listed in the priority we extract them:
 *
 *   { error: "..." }                        → simple top-level error
 *   { detail: "..." }                       → DRF default envelope
 *   { budget: ["..." | "..."] }             → BudgetCheckRule violation
 *   { warrant_exceeded: true,
 *     error: "..."                          → warrant ceiling breach
 *     warrant_info: {...} }
 *   { appropriation_exceeded: true, ... }   → strict appropriation block
 *   { period_closed: true, error: "..." }   → fiscal period gate
 *   { non_field_errors: ["..."] }           → DRF serializer
 *   { field_a: ["..."], field_b: "..." }    → DRF field validation
 *
 * Earlier we had each form parsing this differently — VendorInvoiceForm
 * filtered structured fields properly while CustomerInvoiceForm just
 * flattened all values, losing context. Centralising here means every
 * form gets consistent, prioritised error text.
 */
const STRUCTURED_FIELDS = new Set([
    'appropriation_exceeded',
    'warrant_exceeded',
    'no_appropriation',
    'missing_dimensions',
    'dimensions',
    'appropriation_id',
    'requested',
    'available',
    'deficit',
    'warrant_info',
    'period_closed',
    'invoice',
]);

export function parsePostingError(err: unknown, fallback = 'Failed to save document.'): string {
    if (!err) return fallback;
    const anyErr = err as { response?: { data?: unknown }; message?: string };
    const data = anyErr.response?.data;

    if (typeof data === 'string') return data;
    if (!data || typeof data !== 'object') return anyErr.message || fallback;

    const d = data as Record<string, unknown>;

    // Priority 1 — structured budget envelope.
    if (d.budget) return Array.isArray(d.budget) ? d.budget.join(' ') : String(d.budget);

    // Priority 2 — explicit error / detail field.
    if (d.error) return Array.isArray(d.error) ? d.error.join(' ') : String(d.error);
    if (d.detail) return Array.isArray(d.detail) ? d.detail.join(' ') : String(d.detail);

    // Priority 3 — DRF non_field_errors.
    if (Array.isArray(d.non_field_errors) && d.non_field_errors.length) {
        return d.non_field_errors.map(String).join(' ');
    }

    // Priority 4 — flatten remaining fields, excluding the structured-
    // envelope flags that don't carry user-readable text.
    const userFields = Object.entries(d).filter(([k]) => !STRUCTURED_FIELDS.has(k));
    if (userFields.length === 0) return fallback;

    return userFields
        .map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(', ') : String(v)}`)
        .join(' | ');
}
