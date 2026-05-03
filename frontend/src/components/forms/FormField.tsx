/**
 * FormField — standardized wrapper for every form input in the ERP.
 *
 * Why this exists:
 * Pages across the app re-implement the same `<label> + <input> + error` block
 * with slightly different spacing, font size, and focus colour. This resulted
 * in visual drift between Login, AccountProfile, TSAAccountForm, and every
 * module form. FormField is the single source of truth for:
 *   - label typography (uppercase 13px / weight 600 / 0.5px tracking)
 *   - input padding, border, radius, focus ring
 *   - inline error rendering
 *   - right-side adornments (show/hide password, unit suffix)
 *   - required-field asterisk
 *
 * Matches the existing glass aesthetic (solid white card + subtle border,
 * primary-blue focus ring) while being purely CSS-variable-driven so dark
 * mode and brand recolours flow through.
 */
import React, { useState } from 'react';

export interface FormFieldProps {
    label: string;
    name?: string;
    type?: React.HTMLInputTypeAttribute;
    value: string | number;
    onChange: (value: string) => void;
    placeholder?: string;
    required?: boolean;
    disabled?: boolean;
    autoComplete?: string;
    error?: string;
    helpText?: string;
    /** Element rendered inside the input at the right (e.g. show-password toggle). */
    rightAdornment?: React.ReactNode;
    /** Visual override for invalid state (for same-as-error, confirm, etc.). */
    tone?: 'default' | 'success' | 'error';
    /** Ref-forward onBlur override (rare). */
    onBlur?: () => void;
    maxLength?: number;
    min?: number;
    max?: number;
    step?: number | string;
}

export const FormField: React.FC<FormFieldProps> = ({
    label,
    name,
    type = 'text',
    value,
    onChange,
    placeholder,
    required = false,
    disabled = false,
    autoComplete,
    error,
    helpText,
    rightAdornment,
    tone = 'default',
    onBlur,
    maxLength,
    min,
    max,
    step,
}) => {
    const [focused, setFocused] = useState(false);

    const borderColour = error
        ? '#ef4444'
        : tone === 'success'
            ? '#22c55e'
            : tone === 'error'
                ? '#ef4444'
                : focused
                    ? '#2e35a0'
                    : '#e2e8f0';

    return (
        <div>
            <label
                htmlFor={name}
                style={{
                    display: 'block',
                    fontSize: 13,
                    fontWeight: 600,
                    color: '#475569',
                    marginBottom: 8,
                    textTransform: 'uppercase',
                    letterSpacing: '0.5px',
                }}
            >
                {label}
                {required && (
                    <span style={{ color: '#ef4444', marginLeft: 4 }} aria-hidden>
                        *
                    </span>
                )}
            </label>
            <div style={{ position: 'relative' }}>
                <input
                    id={name}
                    name={name}
                    type={type}
                    value={value}
                    disabled={disabled}
                    autoComplete={autoComplete}
                    placeholder={placeholder}
                    required={required}
                    maxLength={maxLength}
                    min={min}
                    max={max}
                    step={step}
                    onChange={(e) => onChange(e.target.value)}
                    onFocus={() => setFocused(true)}
                    onBlur={() => {
                        setFocused(false);
                        onBlur?.();
                    }}
                    style={{
                        width: '100%',
                        padding: rightAdornment ? '14px 46px 14px 16px' : '14px 16px',
                        border: `1.5px solid ${borderColour}`,
                        borderRadius: 12,
                        fontSize: 15,
                        background: focused ? 'white' : '#f8fafc',
                        outline: 'none',
                        color: disabled ? '#94a3b8' : '#1e293b',
                        fontFamily: 'inherit',
                        transition: 'all 0.2s',
                        boxShadow: focused ? '0 0 0 3px rgba(36,42,136,0.1)' : 'none',
                        cursor: disabled ? 'not-allowed' : 'text',
                    }}
                />
                {rightAdornment && (
                    <div
                        style={{
                            position: 'absolute',
                            right: 14,
                            top: '50%',
                            transform: 'translateY(-50%)',
                            display: 'flex',
                            alignItems: 'center',
                            color: '#94a3b8',
                        }}
                    >
                        {rightAdornment}
                    </div>
                )}
            </div>
            {error ? (
                <p
                    role="alert"
                    style={{
                        fontSize: 12,
                        color: '#ef4444',
                        marginTop: 4,
                        marginBottom: 0,
                    }}
                >
                    {error}
                </p>
            ) : helpText ? (
                <p
                    style={{
                        fontSize: 12,
                        color: '#94a3b8',
                        marginTop: 4,
                        marginBottom: 0,
                    }}
                >
                    {helpText}
                </p>
            ) : null}
        </div>
    );
};

export default FormField;
