/**
 * The colour, text and form values of the Quot ERP design, as antd needs them (antd's theme takes values,
 * not CSS variables). ``index.css`` holds the same values as ``--color-*`` tokens for everything else;
 * ``__tests__/themePalette.test.ts`` fails if the two drift apart.
 */
import type { ThemeConfig } from 'antd';

export type ThemeName = 'light' | 'dark';

/** Keyed by the CSS custom property they mirror, without the leading ``--``. */
export const PALETTE: Record<ThemeName, Record<string, string>> = {
  light: {
    'color-primary': '#101562',
    'color-background': '#f7f7f8',
    'color-surface': '#ffffff',
    'color-surface-hover': '#f3f3f5',
    'color-text': '#111114',
    'color-text-secondary': '#4b4d57',
    'color-text-muted': '#6b6e79',
    'color-border': '#ececef',
    'color-border-strong': '#dcdce1',
    'color-success': '#0e7a4a',
    'color-error': '#bf3329',
    'color-warning': '#8a5300',
    'color-info': '#2b4fc4',
  },
  dark: {
    'color-primary': '#5b63d3',
    'color-background': '#0c0d10',
    'color-surface': '#15161a',
    'color-surface-hover': '#1c1d22',
    'color-text': '#f2f2f4',
    'color-text-secondary': '#b5b7c0',
    'color-text-muted': '#8c8f9a',
    'color-border': '#24262c',
    'color-border-strong': '#34363e',
    'color-success': '#4cc38a',
    'color-error': '#f0776d',
    'color-warning': '#e9b35c',
    'color-info': '#8ca8ff',
  },
};

/** Sizes shared with the ``--control-height`` and ``--radius-control`` tokens. */
export const CONTROL = { height: 38, heightSm: 30, radius: 9, radiusCard: 14, fontSize: 13 } as const;

export const FONT_SANS = "'Geist Variable', 'Geist', 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";

/** The antd token set for one theme; the algorithm (light or dark) is chosen by the caller. */
export function antdTokens(name: ThemeName): NonNullable<ThemeConfig['token']> {
  const p = PALETTE[name];
  return {
    colorPrimary: p['color-primary'],
    colorSuccess: p['color-success'],
    colorError: p['color-error'],
    colorWarning: p['color-warning'],
    colorInfo: p['color-info'],
    colorText: p['color-text'],
    colorTextSecondary: p['color-text-secondary'],
    colorTextTertiary: p['color-text-muted'],
    colorBorder: p['color-border-strong'],
    colorBorderSecondary: p['color-border'],
    colorBgLayout: p['color-background'],
    colorBgContainer: p['color-surface'],
    colorBgElevated: p['color-surface'],
    fontFamily: FONT_SANS,
    fontSize: CONTROL.fontSize,
    controlHeight: CONTROL.height,
    controlHeightSM: CONTROL.heightSm,
    borderRadius: CONTROL.radius,
    borderRadiusLG: CONTROL.radiusCard,
  };
}
