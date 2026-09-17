/**
 * Amount-input helpers — Quot PSE.
 *
 * Number inputs (``type="number"``) can't render thousands separators, so
 * money fields use a plain text input whose displayed value is formatted
 * with commas while the *raw* unformatted numeric string is kept in state.
 * Store `stripThousands(input)` in state; render `formatThousandsInput(state)`.
 */

/** Format a raw numeric string with comma thousands separators, preserving a
 *  trailing dot and up to the digits the user has typed (live-typing safe). */
export function formatThousandsInput(raw: string | number | null | undefined): string {
    if (raw === null || raw === undefined) return '';
    const str = String(raw);
    if (str === '') return '';
    const neg = str.startsWith('-');
    const body = neg ? str.slice(1) : str;
    const [intPart, ...rest] = body.split('.');
    const intFmt = (intPart || '').replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    let out = intFmt;
    if (body.includes('.')) out += '.' + rest.join('');
    return (neg ? '-' : '') + out;
}

/** Strip comma separators back to a raw numeric string for state / parseFloat. */
export function stripThousands(display: string): string {
    return (display || '').replace(/,/g, '');
}
