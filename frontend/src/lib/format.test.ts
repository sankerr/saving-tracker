import { describe, expect, it } from 'vitest';
import { fmtIls, fmtPct, fmtPctSigned } from './format';

describe('fmtIls', () => {
  it('formats ILS with grouping for he-IL', () => {
    const s = fmtIls(1234);
    expect(s).toMatch(/1.?234/);
    expect(s).toContain('₪');
  });
});

describe('fmtPct', () => {
  it('formats fraction as percent with fixed digits', () => {
    expect(fmtPct(0.12345, 1)).toBe('12.3%');
  });
});

describe('fmtPctSigned', () => {
  it('prefixes plus and wraps in LTR isolate', () => {
    const s = fmtPctSigned(0.0255, 2);
    expect(s).toContain('+2.55%');
    expect(s.startsWith('\u2066')).toBe(true);
  });
});
