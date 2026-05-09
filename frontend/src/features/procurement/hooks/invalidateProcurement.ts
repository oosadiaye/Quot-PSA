/**
 * invalidateProcurementCaches
 *
 * Single helper for fan-out invalidation after a P2P state change
 * (PR create/approve, PO create/approve, GRN post, Invoice match).
 *
 * Mirrors `features/accounting/hooks/invalidateLedger.ts`. Use this in
 * every procurement mutation `onSuccess` so PR -> PO -> GRN -> Invoice
 * stays consistent across screens.
 */
import type { QueryClient } from '@tanstack/react-query';

const PROCUREMENT_KEYS = [
  ['purchase-requests'],
  ['purchase-request'],
  ['purchase-orders'],
  ['purchase-order'],
  ['grns'],
  ['grn'],
  ['invoice-matchings'],
  ['invoice-matching'],
  ['vendors'],
  ['vendor-history'],
  ['vendor-performance'],
] as const;

const BUDGET_DEPENDENT_KEYS = [
  ['budget-summary'],
  ['budget-utilization'],
  ['budget-alerts'],
  ['budget-encumbrances'],
  ['appropriations'],
  ['appropriations-admin'],
  ['appropriation-detail'],
] as const;

const GL_DEPENDENT_KEYS = [
  ['journals'],
  ['trial-balance'],
  ['general-ledger'],
] as const;

export function invalidateProcurementCaches(qc: QueryClient): void {
  for (const key of [
    ...PROCUREMENT_KEYS,
    ...BUDGET_DEPENDENT_KEYS,
    ...GL_DEPENDENT_KEYS,
  ]) {
    qc.invalidateQueries({ queryKey: [...key] });
  }
}
