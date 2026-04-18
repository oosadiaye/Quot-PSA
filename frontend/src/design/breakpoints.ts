/**
 * Named breakpoints for Quot PSE.
 *
 * Mobile-first (min-width). Every component that adapts to viewport
 * should import from here — never hard-code a pixel threshold.
 *
 * Part of the responsive rollout (see docs/RESPONSIVE_PLAN.md).
 */
export const BP = {
    xs: 0,        // phones portrait (default)
    sm: 480,      // large phones landscape / small tablets portrait
    md: 768,      // tablets portrait
    lg: 1024,     // tablets landscape / small laptop
    xl: 1280,     // desktop
    xxl: 1536,    // wide desktop / 4K
} as const;

export type Breakpoint = keyof typeof BP;

/**
 * All breakpoints in ascending order. Useful for `gte()` style checks.
 */
export const BP_ORDER: Breakpoint[] = ['xs', 'sm', 'md', 'lg', 'xl', 'xxl'];

/**
 * Returns true when `a` is at or above `b` in the BP ladder.
 *
 * @example  gte('md', 'lg') // false  (md < lg)
 * @example  gte('xl', 'md') // true   (xl >= md)
 */
export function gte(a: Breakpoint, b: Breakpoint): boolean {
    return BP_ORDER.indexOf(a) >= BP_ORDER.indexOf(b);
}
