import {
  createContext, useContext, useState, useEffect, useCallback, type ReactNode,
} from 'react';

/** What the user picked. `auto` = "time of day" (see themeForNow). */
export type ThemeMode = 'light' | 'dark' | 'auto';
/** The theme actually applied to the document. */
export type Theme = 'light' | 'dark';

// "Time of day" mode: dark in the evening/night, light through the day.
export const DARK_FROM_HOUR = 18;   // 18:00 onward → dark
export const DARK_UNTIL_HOUR = 6;   // …until 06:00 → then light

function themeForNow(now = new Date()): Theme {
  const h = now.getHours();
  return h >= DARK_FROM_HOUR || h < DARK_UNTIL_HOUR ? 'dark' : 'light';
}

interface ThemeContextType {
  /** The user's selection: light | dark | auto. */
  mode: ThemeMode;
  /** The effective theme currently applied (auto resolves to one of these). */
  theme: Theme;
  setMode: (mode: ThemeMode) => void;
  // Back-compat helpers for existing callers.
  setTheme: (theme: Theme) => void;
  toggleTheme: () => void;
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

function readInitialMode(): ThemeMode {
  try {
    const saved = localStorage.getItem('theme-mode');
    if (saved === 'light' || saved === 'dark' || saved === 'auto') return saved;
    // Migrate the old boolean 'theme' key.
    const legacy = localStorage.getItem('theme');
    if (legacy === 'dark') return 'dark';
  } catch { /* storage blocked — fall through */ }
  return 'light';
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<ThemeMode>(readInitialMode);
  const [theme, setThemeEffective] = useState<Theme>(() =>
    mode === 'auto' ? themeForNow() : mode,
  );

  // Resolve the effective theme from the mode; in `auto`, keep it in step with
  // the clock — re-check on a timer and whenever the tab regains focus.
  useEffect(() => {
    try { localStorage.setItem('theme-mode', mode); } catch { /* ignore */ }
    const apply = () => setThemeEffective(mode === 'auto' ? themeForNow() : mode);
    apply();
    if (mode !== 'auto') return;
    const id = window.setInterval(apply, 5 * 60 * 1000); // every 5 min
    window.addEventListener('focus', apply);
    document.addEventListener('visibilitychange', apply);
    return () => {
      window.clearInterval(id);
      window.removeEventListener('focus', apply);
      document.removeEventListener('visibilitychange', apply);
    };
  }, [mode]);

  // Reflect the effective theme on <html> so the CSS token sets swap over.
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
  }, [theme]);

  const setMode = useCallback((m: ThemeMode) => setModeState(m), []);
  const setTheme = useCallback((t: Theme) => setModeState(t), []);
  const toggleTheme = useCallback(
    () => setModeState((prev) => (prev === 'dark' ? 'light' : 'dark')),
    [],
  );

  return (
    <ThemeContext.Provider value={{ mode, theme, setMode, setTheme, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error('useTheme must be used within a ThemeProvider');
  }
  return context;
}
