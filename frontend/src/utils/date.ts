/**
 * Date display helpers — the single source of the house DD/MM/YYYY format.
 *
 * Nigerian convention is day-first. ISO (`YYYY-MM-DD`) is kept only for
 * `input[type=date]` values, API payloads and storage — never for display.
 * Use these helpers instead of a bare `toLocaleDateString()`, which falls
 * back to the browser's locale and silently renders MM/DD/YYYY for some users.
 */

/** DD/MM/YYYY, or an em dash when the value is empty/invalid. */
export function formatDate(value?: string | number | Date | null): string {
    if (value === null || value === undefined || value === '') return '—';
    const d = value instanceof Date ? value : new Date(value);
    return Number.isNaN(d.getTime()) ? String(value) : d.toLocaleDateString('en-GB');
}

/** DD/MM/YYYY, HH:MM:SS — for created/updated timestamps. */
export function formatDateTime(value?: string | number | Date | null): string {
    if (value === null || value === undefined || value === '') return '—';
    const d = value instanceof Date ? value : new Date(value);
    return Number.isNaN(d.getTime()) ? String(value) : d.toLocaleString('en-GB');
}
