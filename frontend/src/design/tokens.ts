/**
 * Design tokens that adapt to the current breakpoint.
 *
 * Not every value needs to be a token — only the ones that *should*
 * change with viewport. Static brand colours live in LandingPage
 * constants; changing spacing / type scale lives here.
 */
import type { Breakpoint } from './breakpoints';

export interface SpaceTokens {
    page: number;    // outer page padding
    card: number;    // inner card padding
    gutter: number;  // gap between grid items
    section: number; // vertical rhythm between sections
}

export function spaceFor(bp: Breakpoint): SpaceTokens {
    if (bp === 'xs') return { page: 14, card: 14, gutter: 10, section: 28 };
    if (bp === 'sm') return { page: 18, card: 16, gutter: 12, section: 36 };
    if (bp === 'md') return { page: 24, card: 20, gutter: 14, section: 44 };
    return { page: 40, card: 24, gutter: 16, section: 56 };
}

export interface TypeTokens {
    h1: string;
    h2: string;
    h3: string;
    body: string;
    small: string;
}

export function typeFor(bp: Breakpoint): TypeTokens {
    if (bp === 'xs') return { h1: '24px', h2: '20px', h3: '16px', body: '15px', small: '12px' };
    if (bp === 'sm') return { h1: '28px', h2: '22px', h3: '17px', body: '15px', small: '12px' };
    if (bp === 'md') return { h1: '32px', h2: '24px', h3: '18px', body: '15px', small: '12.5px' };
    return { h1: '36px', h2: '28px', h3: '20px', body: '15px', small: '13px' };
}
