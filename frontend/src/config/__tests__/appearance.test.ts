import { beforeEach, describe, expect, it } from 'vitest';
import {
  BACKGROUND_PRESETS, BACKGROUND_STORAGE_KEY, applyBackground, loadBackground, luminance, normalizeHex, readableOn, saveBackground,
} from '../appearance';

const memory = () => {
  const m = new Map<string, string>();
  return { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => void m.set(k, v), removeItem: (k: string) => void m.delete(k) };
};

describe('normalizeHex', () => {
  it('accepts 3 and 6 digit colours in any case, with or without #', () => {
    expect(normalizeHex('#ABC')).toBe('#aabbcc');
    expect(normalizeHex('1A2b3C')).toBe('#1a2b3c');
    expect(normalizeHex('  #eef2f7 ')).toBe('#eef2f7');
  });
  it('rejects things that are not colours, including css that could be injected', () => {
    for (const bad of ['', 'red', '#12', '#12345', '#gggggg', 'url(x)', '#fff;background:red', 'rgb(0,0,0)']) expect(normalizeHex(bad)).toBeNull();
  });
});

describe('readableOn', () => {
  it('uses dark text on light backgrounds and white on dark ones', () => {
    expect(readableOn('#ffffff')).toBe('#0f172a');
    expect(readableOn('#eef2f7')).toBe('#0f172a');
    expect(readableOn('#000000')).toBe('#ffffff');
    expect(readableOn('#1a1f66')).toBe('#ffffff');
  });
  it('reads every preset at WCAG AA (4.5:1) or better', () => {
    for (const p of BACKGROUND_PRESETS) {
      const fg = readableOn(p.value);
      const [hi, lo] = [luminance(p.value), luminance(fg)].sort((a, b) => b - a);
      expect((hi + 0.05) / (lo + 0.05), p.name).toBeGreaterThanOrEqual(4.5);
    }
  });
});

describe('storage', () => {
  let store: ReturnType<typeof memory>;
  beforeEach(() => { store = memory(); });

  it('round-trips a colour and forgets it on null', () => {
    expect(saveBackground('#e8f1ea', store)).toBe(true);
    expect(loadBackground(store)).toBe('#e8f1ea');
    saveBackground(null, store);
    expect(loadBackground(store)).toBeNull();
  });
  it('ignores a stored value that is not a colour', () => {
    store.setItem(BACKGROUND_STORAGE_KEY, 'javascript:alert(1)');
    expect(loadBackground(store)).toBeNull();
  });
  it('reports a browser that refuses to store, and a storage that throws on read', () => {
    const full = { setItem: () => { throw new Error('quota'); }, removeItem: () => undefined };
    expect(saveBackground('#fff', full)).toBe(false);
    expect(loadBackground({ getItem: () => { throw new Error('denied'); } })).toBeNull();
  });
});

describe('applyBackground', () => {
  it('sets the colour, its text colour and the marker, and clears all three', () => {
    const root = document.createElement('div');
    applyBackground('#1a1f66', root);
    expect(root.hasAttribute('data-user-bg')).toBe(true);
    expect(root.style.getPropertyValue('--user-bg')).toBe('#1a1f66');
    expect(root.style.getPropertyValue('--user-bg-fg')).toBe('#ffffff');
    applyBackground(null, root);
    expect(root.hasAttribute('data-user-bg')).toBe(false);
    expect(root.style.getPropertyValue('--user-bg')).toBe('');
  });
  it('does nothing for a value that is not a colour', () => {
    const root = document.createElement('div');
    applyBackground('nope', root);
    expect(root.hasAttribute('data-user-bg')).toBe(false);
  });
});
