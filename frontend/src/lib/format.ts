/** Hebrew-locale money / percent helpers (ported from legacy). */

const fmtIls0 = new Intl.NumberFormat('he-IL', {
  style: 'currency',
  currency: 'ILS',
  maximumFractionDigits: 0,
});

const fmtIls2 = new Intl.NumberFormat('he-IL', {
  style: 'currency',
  currency: 'ILS',
  maximumFractionDigits: 2,
});

const fmtUsd0 = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  maximumFractionDigits: 0,
});

/** Format ILS. `n` is a currency amount (not minor units). */
export function fmtIls(n: number, digits = 0): string {
  if (!Number.isFinite(n)) return '—';
  return (digits === 0 ? fmtIls0 : fmtIls2).format(n);
}

export function fmtUsd(n: number): string {
  if (!Number.isFinite(n)) return '—';
  return fmtUsd0.format(n);
}

/** Format a fraction as percent (0.123 → "12.30%"). */
export function fmtPct(n: number | null | undefined, digits = 2): string {
  if (n === null || n === undefined || Number.isNaN(n)) return '—';
  return `${(n * 100).toFixed(digits)}%`;
}

/** Signed percent with LTR isolate so +/- stays on the left in RTL. */
export function fmtPctSigned(n: number | null | undefined, digits = 2): string {
  if (n === null || n === undefined || Number.isNaN(n)) return '—';
  const s = `${n >= 0 ? '+' : ''}${(n * 100).toFixed(digits)}%`;
  return `\u2066${s}\u2069`;
}
