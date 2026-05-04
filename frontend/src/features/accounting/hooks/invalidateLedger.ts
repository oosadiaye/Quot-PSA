/**
 * invalidateLedgerCaches
 * ----------------------
 * Single source of truth for "this transaction touched the ledger —
 * everything downstream needs to refresh".
 *
 * Posting paths that affect the GL (manual JE, AP invoice, AR invoice,
 * PV pay, IPC accrual, asset capitalisation, retention release, etc.)
 * all converge on the same caches: the journal list, the GLBalance
 * read views, AND the financial reports built on top of them
 * (Trial Balance, Balance Sheet, Income Statement, Cash Flow).
 *
 * The financial-report hooks use a 5-minute ``staleTime`` to keep
 * report rendering snappy on tenants with heavy GL traffic. That
 * stale window is the only thing standing between the user and a
 * real-time view — but only because no one was telling React Query
 * "this report's data is stale RIGHT NOW because we just posted
 * something". This helper closes that gap: every posting hook calls
 * it on success and every report query refetches on next visit.
 *
 * Keep this list aligned with the ``queryKey`` strings used in:
 *   - features/accounting/hooks/useFinancialReports.ts
 *   - features/accounting/hooks/useJournal.ts
 *   - hooks/useGovForms.ts
 *   - features/contracts/hooks/useContracts.ts (contract-balance)
 */
import type { QueryClient } from '@tanstack/react-query';

// Every query key whose data is derived (directly or indirectly) from
// posted GL journals. Keys can be 1- or 2-element prefixes; React
// Query treats them as prefix matches so a key ['ipsas-cash-flow']
// also catches ['ipsas-cash-flow', fy, period].
const LEDGER_KEYS: ReadonlyArray<ReadonlyArray<string>> = [
  // Journal surfaces
  ['journals'],
  ['journal-detail'],
  ['gl-balances'],
  ['gl-report'],

  // Financial reports — the user-visible ones that must reflect the
  // latest posting on next paint.
  ['trial-balance'],
  ['balance-sheet'],
  ['profit-loss'],
  ['income-statement'],
  ['cash-flow'],

  // ── IPSAS reports ───────────────────────────────────────────────
  // Every report listed in the sidebar's "IPSAS Reporting" group is
  // computed from posted journal lines (or appropriation totals that
  // recompute on every posting). All 13 must drop their React Query
  // cache the moment ANY ledger-touching mutation succeeds.
  ['ipsas-financial-position'],
  ['ipsas-financial-performance'],
  ['ipsas-cash-flow'],
  ['ipsas-changes-in-net-assets'],
  ['ipsas-notes'],
  ['ipsas-budget-vs-actual'],
  ['ipsas-budget-performance'],
  ['ipsas-revenue-performance'],
  ['ipsas-tsa-cash-position'],
  ['ipsas-tsa-cash-full'],   // alternate key used by TSACashPositionReport
  ['ipsas-functional-classification'],
  ['ipsas-programme-performance'],
  ['ipsas-geographic-distribution'],
  ['ipsas-fund-performance'],

  // Other budget execution reports
  ['budget-execution-report'],
  ['budget-commitment-report'],
  ['warrant-utilization'],

  // Budget execution — appropriation cards show committed/expended
  // figures that recompute off the same underlying data.
  ['generic-list', '/budget/appropriations/'],
  ['contract-appropriation'],
  ['contract-balance'],

  // Treasury surfaces that summarise cash impact.
  ['gov-tsa-cash-position'],
  ['gov-revenue-summary'],
  ['payment-vouchers'],
  ['generic-list', '/accounting/payment-vouchers/'],
];

/**
 * Invalidate every query key whose data is derived from posted
 * journals. Safe to call after any successful posting mutation.
 *
 * Idempotent — extra calls just trigger a few extra (cheap) refetches.
 * Prefer calling this once at the end of a posting hook's
 * ``onSuccess`` over scattering individual ``invalidateQueries`` calls.
 */
export function invalidateLedgerCaches(qc: QueryClient): void {
  for (const key of LEDGER_KEYS) {
    qc.invalidateQueries({ queryKey: [...key] });
  }
}
