/**
 * Retention ₦ ↔ % conversion for the contract form.
 *
 * The contract stores only ``retention_rate`` (%). The form lets the user
 * enter retention as EITHER a percentage or a naira value; the naira input
 * back-computes the rate through {@link retentionRateFromAmount}, and the
 * reserve readout uses {@link retentionAmountFromRate}. Keeping the maths in
 * one pure, tested place avoids drift between the input handler and the readout.
 *
 * Rate is capped 0–20% to match the model validator + DB CheckConstraint
 * (contracts_contract_retention_rate_0_to_20), rounded to 2 decimals.
 */

export const RETENTION_RATE_MAX = 20;

/** Reserve (₦) implied by a rate. 0 when the amount is not positive. */
export function retentionAmountFromRate(amount: number, rate: number): number {
  const amt = Number(amount) || 0;
  const r = Number(rate) || 0;
  if (amt <= 0) return 0;
  return (amt * r) / 100;
}

/**
 * Rate (%) implied by a naira retention value, capped 0–20 and rounded to
 * 2dp. 0 when the amount is not positive (can't divide) — the caller should
 * disable the ₦ input until an Original Sum exists.
 */
export function retentionRateFromAmount(amount: number, retentionNaira: number): number {
  const amt = Number(amount) || 0;
  const naira = Number(retentionNaira) || 0;
  if (amt <= 0) return 0;
  const rawRate = (naira / amt) * 100;
  const clamped = Math.min(RETENTION_RATE_MAX, Math.max(0, rawRate));
  return Math.round(clamped * 100) / 100;
}
