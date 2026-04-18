/**
 * useBreakpoint — the one hook every responsive Quot PSE component uses.
 *
 * Why a hook instead of CSS media queries? Because most of our components
 * are inline-styled (`style={{...}}`) and media queries don't work in JS
 * style objects. The hook returns the current named breakpoint so the
 * component can pick values conditionally:
 *
 *   const bp = useBreakpoint();
 *   const isMobile = bp === 'xs' || bp === 'sm';
 *   <div style={{ padding: isMobile ? 16 : 40, ... }}>
 *
 * The implementation uses `useSyncExternalStore` so it stays correct
 * under React concurrent rendering and SSR.
 */
import { useSyncExternalStore } from 'react';
import { BP, gte } from './breakpoints';
import type { Breakpoint } from './breakpoints';

function resolveBreakpoint(width: number): Breakpoint {
    if (width >= BP.xxl) return 'xxl';
    if (width >= BP.xl) return 'xl';
    if (width >= BP.lg) return 'lg';
    if (width >= BP.md) return 'md';
    if (width >= BP.sm) return 'sm';
    return 'xs';
}

function subscribe(cb: () => void): () => void {
    if (typeof window === 'undefined') return () => { };
    window.addEventListener('resize', cb, { passive: true });
    window.addEventListener('orientationchange', cb, { passive: true });
    return () => {
        window.removeEventListener('resize', cb);
        window.removeEventListener('orientationchange', cb);
    };
}

function getSnapshot(): Breakpoint {
    if (typeof window === 'undefined') return 'lg';
    return resolveBreakpoint(window.innerWidth);
}

function getServerSnapshot(): Breakpoint {
    // SSR default: assume desktop so markup matches what desktop clients see.
    return 'lg';
}

export function useBreakpoint(): Breakpoint {
    return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}

/**
 * Convenience: true on xs or sm.
 */
export function useIsMobile(): boolean {
    const bp = useBreakpoint();
    return bp === 'xs' || bp === 'sm';
}

/**
 * Convenience: true on md.
 */
export function useIsTablet(): boolean {
    return useBreakpoint() === 'md';
}

/**
 * Convenience: true on lg and above.
 */
export function useIsDesktop(): boolean {
    const bp = useBreakpoint();
    return gte(bp, 'lg');
}
