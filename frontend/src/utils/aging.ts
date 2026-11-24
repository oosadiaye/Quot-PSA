// ───────────────────────────────────────────────────────────────────────────
// aging — days-to-due / days-overdue maths for payable & receivable registers.
//
// One sign convention, used everywhere: **days overdue is positive**.
//   > 0  → overdue by that many days
//   = 0  → due today
//   < 0  → not yet due; |value| days remain until the due date
//
// All arithmetic is date-only in UTC so a time-of-day or timezone shift can
// never move an invoice across the midnight boundary and report the wrong day
// count (a classic off-by-one in aging reports).
// ───────────────────────────────────────────────────────────────────────────

const MS_PER_DAY = 86_400_000;

/** UTC midnight for a `YYYY-MM-DD` string, or null if it isn't one. */
function utcMidnightFromISO(iso: string): number | null {
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
    if (!m) return null;
    return Date.UTC(+m[1], +m[2] - 1, +m[3]);
}

/** UTC midnight for the local calendar day of `d`. */
function utcMidnightOf(d: Date): number {
    return Date.UTC(d.getFullYear(), d.getMonth(), d.getDate());
}

/**
 * Whole days a payable is overdue as of `today` (default: now).
 * Positive = overdue, 0 = due today, negative = days until due.
 * Returns null when `dueISO` is missing or not a valid ISO date.
 */
export function daysOverdue(dueISO: string | null | undefined, today: Date = new Date()): number | null {
    if (!dueISO) return null;
    const due = utcMidnightFromISO(dueISO);
    if (due === null) return null;
    return Math.round((utcMidnightOf(today) - due) / MS_PER_DAY);
}

/** Human phrase for a days-overdue value (see sign convention above). */
export function agingLabel(days: number): string {
    if (days > 0) return `${days} day${days === 1 ? '' : 's'} overdue`;
    if (days === 0) return 'Due today';
    const n = -days;
    return `Due in ${n} day${n === 1 ? '' : 's'}`;
}

export type AgingFilter =
    | 'all'
    | 'notdue'
    | 'due7'
    | 'overdue'
    | 'd1_30'
    | 'd31_60'
    | 'd61_90'
    | 'd90p';

/** Label for each aging filter option (drives the register's filter select). */
export const AGING_FILTER_OPTIONS: ReadonlyArray<{ value: AgingFilter; label: string }> = [
    { value: 'all', label: 'All aging' },
    { value: 'notdue', label: 'Not yet due' },
    { value: 'due7', label: 'Due ≤ 7 days' },
    { value: 'overdue', label: 'Overdue (any)' },
    { value: 'd1_30', label: 'Overdue 1–30' },
    { value: 'd31_60', label: 'Overdue 31–60' },
    { value: 'd61_90', label: 'Overdue 61–90' },
    { value: 'd90p', label: 'Overdue 90+' },
];

/**
 * Does a days-overdue value fall in the selected filter bucket?
 * `days === null` (settled / no due date) matches only 'all'.
 */
export function matchesAging(days: number | null, filter: AgingFilter): boolean {
    if (filter === 'all') return true;
    if (days === null) return false;
    switch (filter) {
        case 'notdue': return days < 0;
        case 'due7': return days <= 0 && days >= -7;
        case 'overdue': return days > 0;
        case 'd1_30': return days >= 1 && days <= 30;
        case 'd31_60': return days >= 31 && days <= 60;
        case 'd61_90': return days >= 61 && days <= 90;
        case 'd90p': return days > 90;
        default: return true;
    }
}
