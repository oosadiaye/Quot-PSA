import type { CSSProperties, ComponentType } from 'react';
import { Sun, Moon, Clock } from 'lucide-react';
import { useTheme, type ThemeMode } from '../context/ThemeContext';

/**
 * Three-way theme control: Light, Dark, and Auto ("time of day", which follows
 * the clock — light through the day, dark in the evening). Token-styled so it
 * reads correctly in whichever theme is active.
 */
const OPTIONS: { mode: ThemeMode; label: string; Icon: ComponentType<{ size?: number }> }[] = [
  { mode: 'light', label: 'Light', Icon: Sun },
  { mode: 'dark', label: 'Dark', Icon: Moon },
  { mode: 'auto', label: 'Auto', Icon: Clock },
];

interface ThemeSwitcherProps {
  /** Fill the container width with three equal segments (sidebar footer). */
  block?: boolean;
}

export default function ThemeSwitcher({ block = false }: ThemeSwitcherProps) {
  const { mode, theme, setMode } = useTheme();
  return (
    <div style={wrap} role="group" aria-label="Theme">
      {OPTIONS.map(({ mode: m, label, Icon }) => {
        const active = mode === m;
        return (
          <button
            key={m}
            type="button"
            onClick={() => setMode(m)}
            aria-pressed={active}
            title={m === 'auto' ? `Time of day — currently ${theme}` : `${label} theme`}
            style={{
              ...seg,
              ...(block ? { flex: 1, justifyContent: 'center' } : {}),
              ...(active ? segActive : {}),
            }}
          >
            <Icon size={14} />
            <span style={segLabel}>{label}</span>
          </button>
        );
      })}
    </div>
  );
}

const wrap: CSSProperties = {
  display: 'flex', gap: 2, padding: 3,
  borderRadius: 10,
  border: '1px solid var(--color-border)',
  background: 'var(--color-surface)',
};
const seg: CSSProperties = {
  display: 'inline-flex', alignItems: 'center', gap: 5,
  padding: '5px 9px', borderRadius: 7,
  border: 'none', background: 'transparent',
  color: 'var(--color-text-muted)',
  fontSize: 11.5, fontWeight: 600, cursor: 'pointer',
  transition: 'background 140ms ease, color 140ms ease',
};
const segActive: CSSProperties = {
  background: 'var(--color-primary)',
  color: '#ffffff',
  boxShadow: '0 2px 6px rgba(36, 42, 136, 0.25)',
};
const segLabel: CSSProperties = { lineHeight: 1 };
