/**
 * CurrencySwitcher — dropdown for visitors to pick their preferred currency.
 * Shows flag emoji + code, highlights the auto-detected one.
 */
import type { PlatformCurrency } from '../../hooks/usePricingCurrency';

interface Props {
  currencies: PlatformCurrency[];
  selectedCode: string;
  onChange: (code: string) => void;
  detectedCountry?: string | null;
}

export default function CurrencySwitcher({ currencies, selectedCode, onChange, detectedCountry }: Props) {
  if (currencies.length <= 1) return null;

  return (
    <div style={{ position: 'relative', display: 'inline-block' }}>
      <select
        value={selectedCode}
        onChange={(e) => onChange(e.target.value)}
        style={{
          appearance: 'none',
          WebkitAppearance: 'none',
          background: 'rgba(255,255,255,0.9)',
          backdropFilter: 'blur(8px)',
          border: '1px solid #e2e8f0',
          borderRadius: 8,
          padding: '8px 36px 8px 12px',
          fontSize: '0.875rem',
          fontWeight: 500,
          color: '#191c1e',
          cursor: 'pointer',
          fontFamily: 'inherit',
          minWidth: 140,
          boxShadow: '0 1px 3px rgba(0,0,0,0.06)',
          transition: 'border-color 0.15s ease',
        }}
        onFocus={(e) => { e.currentTarget.style.borderColor = '#242a88'; }}
        onBlur={(e) => { e.currentTarget.style.borderColor = '#e2e8f0'; }}
      >
        {currencies.map((c) => {
          const isDetected = detectedCountry && (c.country_codes || []).includes(detectedCountry);
          return (
            <option key={c.currency_code} value={c.currency_code}>
              {c.flag_emoji} {c.currency_code} — {c.symbol}{isDetected ? ' (detected)' : ''}
            </option>
          );
        })}
      </select>
      {/* Chevron icon */}
      <svg
        style={{
          position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)',
          width: 16, height: 16, pointerEvents: 'none', color: '#94a3b8',
        }}
        fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
      >
        <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
      </svg>
    </div>
  );
}
