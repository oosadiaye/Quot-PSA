/**
 * Safe decimal arithmetic utilities for currency values.
 * Works in cents (integer math) to avoid floating-point rounding errors.
 */

export function safeAdd(...values: (string | number)[]): number {
  return values.reduce<number>((sum, v) => {
    const cents = Math.round(Number(v || 0) * 100);
    return sum + cents;
  }, 0) / 100;
}

export function safeMultiply(a: string | number, b: string | number): number {
  return Math.round(Number(a || 0) * 100) * Number(b || 0) / 100;
}

export function safeSum(items: any[], field: string): number {
  return items.reduce((sum, item) => {
    const cents = Math.round(Number(item[field] || 0) * 100);
    return sum + cents;
  }, 0) / 100;
}
