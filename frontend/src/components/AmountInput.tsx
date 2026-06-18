/**
 * AmountInput — Drop-in replacement for `<input type="number" step="0.01">`
 * that displays values with thousand separators while keeping the raw
 * numeric string in component state.
 *
 * Why a text input?
 *   `<input type="number">` rejects commas at the DOM level, so the
 *   formatted value `1,250,000.00` cannot appear inside the field. We
 *   switch to `type="text" inputMode="decimal"` (decimal keypad on
 *   mobile) and own validation in `parseAmount`.
 *
 * Contract:
 *   - `value` is the raw numeric string from form state (no commas).
 *   - `onChange(rawString)` emits a sanitised raw string (no commas,
 *      no alpha, max one decimal point, max 2 fractional digits).
 *   - Empty input emits `''` so existing `required` validation and
 *      `parseFloat(form.amount)` handlers behave identically.
 *
 * Drop-in migration:
 *   <input type="number" step="0.01" value={form.amount}
 *          onChange={e => set('amount', e.target.value)} />
 *   becomes
 *   <AmountInput value={form.amount}
 *                onChange={v => set('amount', v)} />
 *
 *   All form submission and Decimal coercion in handlers stays the
 *   same — the wire value is always a comma-less string.
 */
import { useMemo, type CSSProperties, type FocusEventHandler } from 'react';

/**
 * Strip commas, alpha, and stray symbols from user input and clamp
 * to at most one decimal point + 2 fractional digits.
 */
export function parseAmount(input: string, allowNegative: boolean = false): string {
    if (input === null || input === undefined) {
        return '';
    }

    let cleaned = String(input).replace(/,/g, '').replace(/[^0-9.\-]/g, '');

    // Allow a single leading minus only when permitted.
    const negative = allowNegative && cleaned.startsWith('-');
    cleaned = cleaned.replace(/-/g, '');

    // Collapse multiple decimal points to the first one.
    const firstDot = cleaned.indexOf('.');
    if (firstDot !== -1) {
        const intPart = cleaned.slice(0, firstDot);
        const fracPart = cleaned.slice(firstDot + 1).replace(/\./g, '').slice(0, 2);
        cleaned = `${intPart}.${fracPart}`;
    }

    if (cleaned === '' || cleaned === '.') {
        // Preserve a lone minus so the user can keep typing digits
        // after the sign in an allowNegative input.
        if (negative && cleaned === '') {
            return '-';
        }
        return cleaned;
    }

    return negative ? `-${cleaned}` : cleaned;
}

/**
 * Format a raw numeric string for display: insert thousand separators
 * in the integer portion while preserving the user's in-flight decimal
 * (so typing "1234." keeps the trailing dot, and "1234.5" keeps a
 * single fractional digit without prematurely rounding to two).
 */
export function formatAmountDisplay(raw: string | number | null | undefined): string {
    if (raw === null || raw === undefined || raw === '') {
        return '';
    }

    const str = String(raw);
    const negative = str.startsWith('-');
    const abs = negative ? str.slice(1) : str;

    const [intPart, fracPart] = abs.split('.');
    const intFormatted = intPart === '' ? '' : Number(intPart).toLocaleString('en-US');

    let result: string;
    if (str.includes('.')) {
        result = `${intFormatted || '0'}.${fracPart ?? ''}`;
    } else {
        result = intFormatted;
    }

    return negative ? `-${result}` : result;
}

export interface AmountInputProps {
    value: string | number;
    onChange: (value: string) => void;
    onBlur?: FocusEventHandler<HTMLInputElement>;
    placeholder?: string;
    required?: boolean;
    disabled?: boolean;
    readOnly?: boolean;
    autoFocus?: boolean;
    allowNegative?: boolean;
    id?: string;
    name?: string;
    className?: string;
    style?: CSSProperties;
    'aria-label'?: string;
    'aria-describedby'?: string;
    'aria-invalid'?: boolean;
    /** Optional max for soft enforcement; not a hard DOM constraint. */
    max?: number;
    /** Optional min for soft enforcement; not a hard DOM constraint. */
    min?: number;
}

export default function AmountInput({
    value,
    onChange,
    onBlur,
    placeholder = '0.00',
    required,
    disabled,
    readOnly,
    autoFocus,
    allowNegative = false,
    id,
    name,
    className,
    style,
    max,
    min,
    ...aria
}: AmountInputProps) {
    const display = useMemo(
        () => formatAmountDisplay(value as string | number | null | undefined),
        [value],
    );

    return (
        <input
            type="text"
            inputMode="decimal"
            autoComplete="off"
            spellCheck={false}
            value={display}
            placeholder={placeholder}
            required={required}
            disabled={disabled}
            readOnly={readOnly}
            autoFocus={autoFocus}
            id={id}
            name={name}
            className={className}
            style={style}
            onChange={(e) => {
                const raw = parseAmount(e.target.value, allowNegative);
                if (raw === '' || raw === '.' || raw === '-' || raw === '-.') {
                    onChange(raw);
                    return;
                }

                const numeric = Number(raw);
                if (Number.isFinite(numeric)) {
                    if (typeof max === 'number' && numeric > max) {
                        return;
                    }
                    if (typeof min === 'number' && numeric < min) {
                        return;
                    }
                }
                onChange(raw);
            }}
            onBlur={onBlur}
            {...aria}
        />
    );
}
