/**
 * AmountInput regression suite.
 *
 * Tests split into two layers:
 *   1. Pure helpers (parseAmount, formatAmountDisplay) — exhaustive
 *      edge-case coverage with no React.
 *   2. Component behaviour — typing, paste, controlled-value sync,
 *      and the "emits raw string, no commas" contract that downstream
 *      form submission handlers rely on.
 */
import { describe, it, expect, vi } from 'vitest';
import { useState } from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import AmountInput, { parseAmount, formatAmountDisplay } from '../AmountInput';

describe('parseAmount', () => {
    it('strips commas from user input', () => {
        expect(parseAmount('1,234,567')).toBe('1234567');
    });

    it('keeps a single decimal point with two fractional digits', () => {
        expect(parseAmount('1234.56')).toBe('1234.56');
    });

    it('truncates fractional digits beyond two', () => {
        expect(parseAmount('1234.5678')).toBe('1234.56');
    });

    it('collapses multiple decimal points to the first', () => {
        expect(parseAmount('12.34.56')).toBe('12.34');
    });

    it('strips alphabetic characters', () => {
        expect(parseAmount('1a2b3c.4d5')).toBe('123.45');
    });

    it('handles paste with commas and currency symbol', () => {
        expect(parseAmount('₦1,250,000.00')).toBe('1250000.00');
    });

    it('returns empty string for empty input', () => {
        expect(parseAmount('')).toBe('');
    });

    it('preserves a trailing decimal point while typing', () => {
        expect(parseAmount('1234.')).toBe('1234.');
    });

    it('rejects negative numbers by default', () => {
        expect(parseAmount('-500')).toBe('500');
    });

    it('preserves a single leading minus when allowNegative is true', () => {
        expect(parseAmount('-500.25', true)).toBe('-500.25');
    });

    it('collapses multiple minuses to one when allowNegative is true', () => {
        expect(parseAmount('--500', true)).toBe('-500');
    });
});

describe('formatAmountDisplay', () => {
    it('inserts thousand separators into the integer portion', () => {
        expect(formatAmountDisplay('1234567')).toBe('1,234,567');
    });

    it('formats two decimal places without rounding', () => {
        expect(formatAmountDisplay('1234567.89')).toBe('1,234,567.89');
    });

    it('preserves a trailing decimal point during typing', () => {
        expect(formatAmountDisplay('1234.')).toBe('1,234.');
    });

    it('preserves a single fractional digit during typing', () => {
        expect(formatAmountDisplay('1234.5')).toBe('1,234.5');
    });

    it('returns empty string for empty input', () => {
        expect(formatAmountDisplay('')).toBe('');
    });

    it('returns empty string for null or undefined', () => {
        expect(formatAmountDisplay(null)).toBe('');
        expect(formatAmountDisplay(undefined)).toBe('');
    });

    it('formats negative values', () => {
        expect(formatAmountDisplay('-1234567.89')).toBe('-1,234,567.89');
    });

    it('accepts a number prop and formats it', () => {
        expect(formatAmountDisplay(1250000)).toBe('1,250,000');
    });

    it('handles a leading decimal point (".5") cleanly', () => {
        expect(formatAmountDisplay('.5')).toBe('0.5');
    });
});

describe('<AmountInput />', () => {
    function Controlled({ onValueChange }: { onValueChange?: (v: string) => void }) {
        const [value, setValue] = useState('');
        return (
            <AmountInput
                value={value}
                onChange={(v) => {
                    setValue(v);
                    onValueChange?.(v);
                }}
                aria-label="amount"
            />
        );
    }

    it('renders an empty input initially', () => {
        render(<Controlled />);
        const input = screen.getByLabelText('amount') as HTMLInputElement;
        expect(input.value).toBe('');
        expect(input.type).toBe('text');
        expect(input.inputMode).toBe('decimal');
    });

    it('formats typed digits with thousand separators', async () => {
        const user = userEvent.setup();
        render(<Controlled />);
        const input = screen.getByLabelText('amount') as HTMLInputElement;

        await user.type(input, '1234567');

        expect(input.value).toBe('1,234,567');
    });

    it('emits raw (comma-less) string to onChange', async () => {
        const user = userEvent.setup();
        const onChange = vi.fn();
        render(<Controlled onValueChange={onChange} />);

        await user.type(screen.getByLabelText('amount'), '1234');

        // Final emitted value carries no commas — the contract that
        // form submission handlers rely on.
        expect(onChange).toHaveBeenLastCalledWith('1234');
    });

    it('strips commas from pasted values', async () => {
        const user = userEvent.setup();
        const onChange = vi.fn();
        render(<Controlled onValueChange={onChange} />);
        const input = screen.getByLabelText('amount') as HTMLInputElement;

        await user.click(input);
        await user.paste('1,250,000.00');

        expect(onChange).toHaveBeenLastCalledWith('1250000.00');
        expect(input.value).toBe('1,250,000.00');
    });

    it('handles backspace deleting a digit', async () => {
        const user = userEvent.setup();
        render(<Controlled />);
        const input = screen.getByLabelText('amount') as HTMLInputElement;

        await user.type(input, '12345');
        await user.type(input, '{Backspace}');

        expect(input.value).toBe('1,234');
    });

    it('allows typing a decimal point and fractional digits', async () => {
        const user = userEvent.setup();
        render(<Controlled />);
        const input = screen.getByLabelText('amount') as HTMLInputElement;

        await user.type(input, '1000.50');

        expect(input.value).toBe('1,000.50');
    });

    it('reflects parent-controlled value changes', () => {
        const { rerender } = render(
            <AmountInput value="" onChange={() => {}} aria-label="amount" />,
        );
        const input = screen.getByLabelText('amount') as HTMLInputElement;
        expect(input.value).toBe('');

        rerender(<AmountInput value="9876543" onChange={() => {}} aria-label="amount" />);
        expect(input.value).toBe('9,876,543');
    });

    it('rejects negative input by default', async () => {
        const user = userEvent.setup();
        const onChange = vi.fn();
        render(<Controlled onValueChange={onChange} />);

        await user.type(screen.getByLabelText('amount'), '-500');

        // The minus is stripped; only the positive digits are emitted.
        expect(onChange).toHaveBeenLastCalledWith('500');
    });

    it('honours allowNegative when set', async () => {
        const user = userEvent.setup();

        function NegativeControlled() {
            const [value, setValue] = useState('');
            return (
                <AmountInput
                    value={value}
                    onChange={setValue}
                    allowNegative
                    aria-label="amount"
                />
            );
        }

        render(<NegativeControlled />);
        const input = screen.getByLabelText('amount') as HTMLInputElement;

        await user.type(input, '-1234.50');

        expect(input.value).toBe('-1,234.50');
    });

    it('forwards required, disabled, placeholder, and id props', () => {
        render(
            <AmountInput
                value=""
                onChange={() => {}}
                required
                disabled
                placeholder="Enter amount"
                id="amt"
                aria-label="amount"
            />,
        );
        const input = screen.getByLabelText('amount') as HTMLInputElement;
        expect(input.required).toBe(true);
        expect(input.disabled).toBe(true);
        expect(input.placeholder).toBe('Enter amount');
        expect(input.id).toBe('amt');
    });
});
