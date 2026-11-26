/**
 * The background colour a user chooses for the app. Stored per browser; applied as ``--user-bg`` on the root element, which
 * ``styles/appearance.css`` turns into the page background (light theme) and the launcher.
 */

export const BACKGROUND_STORAGE_KEY = 'quotpse.appearance.background.v1';

export interface BackgroundPreset { name: string; value: string }

/** Offered swatches. Each one applies its own colour; only "Reset to default" returns to the app's built-in look. */
export const BACKGROUND_PRESETS: readonly BackgroundPreset[] = [
  // Soft
  { name: 'Mist', value: '#eef2f7' },
  { name: 'Paper', value: '#faf7f0' },
  { name: 'Sage', value: '#e8f1ea' },
  { name: 'Sky', value: '#e6f0fa' },
  { name: 'Blush', value: '#f8ecee' },
  // Bright
  { name: 'Royal', value: '#2563eb' },
  { name: 'Azure', value: '#0ea5e9' },
  { name: 'Emerald', value: '#10b981' },
  { name: 'Amber', value: '#f59e0b' },
  { name: 'Rose', value: '#f43f5e' },
  // Bold
  { name: 'Violet', value: '#7c3aed' },
  { name: 'Teal', value: '#0d9488' },
  { name: 'Slate', value: '#475569' },
  { name: 'Navy', value: '#1a1f66' },
  { name: 'Forest', value: '#14532d' },
];

/** What the colour inputs show while nothing is chosen. */
export const DEFAULT_BACKGROUND = BACKGROUND_PRESETS[0].value;

/** "#abc" or "#aabbcc" (any case) to "#aabbcc"; anything else is not a colour and gives null. */
export function normalizeHex(input: string): string | null {
  const m = /^#?([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(input.trim());
  if (!m) return null;
  const h = m[1].length === 3 ? m[1].split('').map((c) => c + c).join('') : m[1];
  return `#${h.toLowerCase()}`;
}

/** WCAG relative luminance, 0 (black) to 1 (white). */
export function luminance(hex: string): number {
  const n = normalizeHex(hex);
  if (!n) return 1;
  const channel = (i: number) => {
    const v = parseInt(n.slice(1 + i * 2, 3 + i * 2), 16) / 255;
    return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * channel(0) + 0.7152 * channel(1) + 0.0722 * channel(2);
}

/** Text colour that reads on this background: whichever of white and near-black has the higher contrast. */
export function readableOn(hex: string): '#ffffff' | '#0f172a' {
  const l = luminance(hex);
  const contrastWhite = 1.05 / (l + 0.05);
  const contrastDark = (l + 0.05) / (luminance('#0f172a') + 0.05);
  return contrastWhite >= contrastDark ? '#ffffff' : '#0f172a';
}

export function loadBackground(storage: Pick<Storage, 'getItem'> = window.localStorage): string | null {
  try {
    const raw = storage.getItem(BACKGROUND_STORAGE_KEY);
    return raw ? normalizeHex(raw) : null;
  } catch {
    return null;
  }
}

/** Saves the colour, or forgets it when ``hex`` is null. Returns whether the browser kept it. */
export function saveBackground(hex: string | null, storage: Pick<Storage, 'setItem' | 'removeItem'> = window.localStorage): boolean {
  try {
    if (hex === null) storage.removeItem(BACKGROUND_STORAGE_KEY);
    else storage.setItem(BACKGROUND_STORAGE_KEY, hex);
    return true;
  } catch {
    return false;
  }
}

/** Puts the colour on the page (or takes it off, for null). */
export function applyBackground(hex: string | null, root: HTMLElement = document.documentElement): void {
  const n = hex ? normalizeHex(hex) : null;
  if (!n) {
    root.removeAttribute('data-user-bg');
    root.style.removeProperty('--user-bg');
    root.style.removeProperty('--user-bg-fg');
    return;
  }
  root.setAttribute('data-user-bg', '');
  root.style.setProperty('--user-bg', n);
  root.style.setProperty('--user-bg-fg', readableOn(n));
}

/** Called before the app mounts, so the saved colour shows from the first paint. */
export function applyStoredBackground(): void {
  applyBackground(loadBackground());
}
