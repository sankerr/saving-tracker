import { describe, expect, it } from 'vitest';
import { t } from './index';

describe('t', () => {
  it('returns a known Hebrew string', () => {
    expect(t('auth.title.login')).toBe('התחברות');
  });

  it('interpolates placeholders', () => {
    expect(t('status.loadedUsdils', { rate: '3.700' })).toBe(
      'נטען · USDILS 3.700',
    );
  });
});
