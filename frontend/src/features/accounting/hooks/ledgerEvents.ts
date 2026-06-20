/**
 * ledgerEvents — cross-tab notification for ledger-affecting mutations.
 *
 * Why this exists alongside ``invalidateLedgerCaches``:
 *
 *   - ``invalidateLedgerCaches`` invalidates React Query keys inside
 *     ONE QueryClient — same tab only.
 *   - When a user posts a journal in tab A and is viewing an
 *     appropriation, budget execution, or report in tab B, tab B's
 *     QueryClient has no idea anything changed. With the global
 *     ``staleTime`` of 5 minutes, tab B keeps serving its cached
 *     snapshot until the user hard-refreshes or 5 min elapse.
 *
 * This module bridges that gap via the platform ``BroadcastChannel``
 * API (Chrome 54+, Firefox 38+, Safari 15.4+, Edge 79+). The contract
 * is intentionally narrow:
 *
 *   - ``broadcastLedgerMutation()`` is called by every posting hook's
 *     ``onSuccess`` (sibling of ``invalidateLedgerCaches``).
 *   - ``useLedgerMutationListener()`` is a React hook that page-level
 *     components subscribe to. It fires a caller-supplied callback
 *     when ANY tab in the same browser profile reports a ledger
 *     mutation — typically the callback runs ``queryClient.invalidate
 *     Queries`` on the page's own keys.
 *
 * Same-tab calls also fire the listener: ``BroadcastChannel`` does NOT
 * echo back to the sender, but the local in-tab invalidation path
 * (``invalidateLedgerCaches``) already handles same-tab refresh, so the
 * cross-tab broadcast is purely additive.
 *
 * Feature detection: tabs in browsers without ``BroadcastChannel``
 * degrade gracefully (broadcast is a no-op, listener never fires).
 * Those users still get same-tab invalidation + ``refetchOnMount``
 * behaviour, which covers the most common workflow.
 */
import { useEffect } from 'react';

const CHANNEL_NAME = 'quot-ledger';

export type LedgerMutationKind =
    | 'journal_posted'
    | 'journal_unposted'
    | 'invoice_posted'
    | 'payment_posted'
    | 'ipc_marked_paid'
    | 'mutation';   // generic catch-all

interface LedgerMutationMessage {
    type: 'ledger-mutation';
    kind: LedgerMutationKind;
    /**
     * Optional timestamp so listeners can dedupe / order events if
     * they ever choose to. Not required by the current contract.
     */
    at: number;
}

/**
 * Notify every other tab in the same browser profile that a ledger-
 * affecting mutation just succeeded. Safe to call from any
 * ``onSuccess`` handler — never throws.
 */
export function broadcastLedgerMutation(kind: LedgerMutationKind = 'mutation'): void {
    if (typeof BroadcastChannel === 'undefined') return;
    let channel: BroadcastChannel | null = null;
    try {
        channel = new BroadcastChannel(CHANNEL_NAME);
        const msg: LedgerMutationMessage = {
            type: 'ledger-mutation',
            kind,
            at: Date.now(),
        };
        channel.postMessage(msg);
    } catch {
        // Best-effort; never break a successful posting flow because a
        // sibling-tab notification couldn't go out.
    } finally {
        try { channel?.close(); } catch { /* ignore */ }
    }
}

/**
 * Subscribe a callback to ledger-mutation broadcasts from sibling tabs.
 *
 * Usage in a page component:
 *
 *     useLedgerMutationListener(() => {
 *         qc.invalidateQueries({ queryKey: ['appropriation-detail'] });
 *         qc.invalidateQueries({ queryKey: ['appropriation-mda-lines'] });
 *     });
 *
 * Mount/unmount lifecycle is handled automatically.
 */
export function useLedgerMutationListener(onMutation: () => void): void {
    useEffect(() => {
        if (typeof BroadcastChannel === 'undefined') return;

        const channel = new BroadcastChannel(CHANNEL_NAME);

        const handle = (event: MessageEvent<unknown>) => {
            const msg = event.data;
            if (
                msg &&
                typeof msg === 'object' &&
                (msg as { type?: unknown }).type === 'ledger-mutation'
            ) {
                onMutation();
            }
        };

        channel.addEventListener('message', handle);
        return () => {
            channel.removeEventListener('message', handle);
            channel.close();
        };
        // Caller is responsible for stable callback references; we
        // intentionally only run this effect on mount/unmount.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);
}
