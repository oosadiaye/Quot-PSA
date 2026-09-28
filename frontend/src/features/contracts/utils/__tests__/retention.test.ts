import { describe, it, expect } from 'vitest';
import {
  retentionAmountFromRate,
  retentionRateFromAmount,
  RETENTION_RATE_MAX,
} from '../retention';

describe('retentionAmountFromRate', () => {
  it('computes the reserve from a rate', () => {
    // Arrange / Act
    const reserve = retentionAmountFromRate(100_000_000, 5);
    // Assert
    expect(reserve).toBe(5_000_000);
  });

  it('returns 0 when the amount is not positive', () => {
    expect(retentionAmountFromRate(0, 5)).toBe(0);
    expect(retentionAmountFromRate(-100, 5)).toBe(0);
  });

  it('returns 0 for a zero or missing rate', () => {
    expect(retentionAmountFromRate(1_000_000, 0)).toBe(0);
    expect(retentionAmountFromRate(1_000_000, NaN)).toBe(0);
  });
});

describe('retentionRateFromAmount', () => {
  it('back-computes the rate from a naira value', () => {
    expect(retentionRateFromAmount(100_000_000, 5_000_000)).toBe(5);
  });

  it('caps the rate at the 20% model limit', () => {
    // 50M on a 100M contract would be 50% — must clamp to 20.
    expect(retentionRateFromAmount(100_000_000, 50_000_000)).toBe(RETENTION_RATE_MAX);
  });

  it('rounds to 2 decimals', () => {
    // 1,000 on 30,000 = 3.333…% → 3.33
    expect(retentionRateFromAmount(30_000, 1_000)).toBe(3.33);
  });

  it('returns 0 when the amount is not positive (cannot divide)', () => {
    expect(retentionRateFromAmount(0, 1_000)).toBe(0);
  });

  it('never goes negative', () => {
    expect(retentionRateFromAmount(1_000_000, -50)).toBe(0);
  });
});

describe('₦ ↔ % round-trip', () => {
  it('is stable for a clean rate', () => {
    const amount = 100_000_000;
    const reserve = retentionAmountFromRate(amount, 5); // 5,000,000
    const rate = retentionRateFromAmount(amount, reserve); // back to 5
    expect(rate).toBe(5);
  });
});
