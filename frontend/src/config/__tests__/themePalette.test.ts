import { describe, expect, it } from 'vitest';
import rawCss from '../../index.css?raw';
import { CONTROL, PALETTE, antdTokens } from '../themePalette';

// The file may be checked out with CRLF line endings.
const css = rawCss.replace(/\r\n/g, '\n');

/** The declarations of the first block whose selector starts with ``selector``. */
function block(selector: string): string {
  const start = css.indexOf(selector);
  expect(start, `${selector} block in index.css`).toBeGreaterThanOrEqual(0);
  return css.slice(css.indexOf('{', start), css.indexOf('\n}', start));
}

const valueOf = (body: string, token: string): string | null => {
  const m = new RegExp(`--${token}:\\s*([^;]+);`).exec(body);
  return m ? m[1].trim().toLowerCase() : null;
};

describe('the antd palette mirrors the CSS tokens in index.css', () => {
  const blocks = { light: block(':root,\n[data-theme="light"]'), dark: block('[data-theme="dark"] {') };

  for (const name of ['light', 'dark'] as const) {
    it(`has every ${name} value the stylesheet has`, () => {
      for (const [token, value] of Object.entries(PALETTE[name])) {
        expect(valueOf(blocks[name], token), `--${token} (${name})`).toBe(value);
      }
    });
  }

  it('takes its control sizes from the stylesheet tokens', () => {
    const light = blocks.light;
    expect(valueOf(light, 'control-height')).toBe(`${CONTROL.height}px`);
    expect(valueOf(light, 'control-height-sm')).toBe(`${CONTROL.heightSm}px`);
    expect(valueOf(light, 'radius-control')).toBe(`${CONTROL.radius}px`);
    expect(valueOf(light, 'radius-card')).toBe(`${CONTROL.radiusCard}px`);
  });
});

describe('antdTokens', () => {
  it('maps the palette onto antd tokens for both themes', () => {
    expect(antdTokens('light').colorPrimary).toBe('#101562');
    expect(antdTokens('dark').colorPrimary).toBe('#5b63d3');
    expect(antdTokens('light').colorBgLayout).toBe(PALETTE.light['color-background']);
    expect(antdTokens('dark').controlHeight).toBe(CONTROL.height);
  });

  it('keeps the dark text readable on the dark surface (WCAG AA, 4.5:1)', () => {
    const lum = (hex: string) => {
      const c = (i: number) => { const v = parseInt(hex.slice(1 + i * 2, 3 + i * 2), 16) / 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
      return 0.2126 * c(0) + 0.7152 * c(1) + 0.0722 * c(2);
    };
    const ratio = (a: string, b: string) => { const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x); return (hi + 0.05) / (lo + 0.05); };
    for (const name of ['light', 'dark'] as const) {
      const p = PALETTE[name];
      for (const t of ['color-text', 'color-text-secondary', 'color-text-muted'] as const) {
        expect(ratio(p[t], p['color-surface']), `${t} on surface (${name})`).toBeGreaterThanOrEqual(4.5);
      }
      expect(ratio('#ffffff', p['color-primary']), `white on primary (${name})`).toBeGreaterThanOrEqual(4.5);
    }
  });
});
