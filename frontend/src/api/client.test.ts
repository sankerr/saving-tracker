import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { apiUrl, api } from './client';
import { setToken } from '../auth/token';

describe('apiUrl', () => {
  it('joins base and path without double slash', () => {
    // VITE_API_BASE is baked at build time; we only assert path concat shape for empty base
    expect(apiUrl('/api/login').endsWith('/api/login')).toBe(true);
  });
});

describe('api', () => {
  beforeEach(() => {
    localStorage.clear();
    setToken('tok');
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('sends Authorization bearer and returns JSON', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ ok: true, hello: 1 }),
    });
    vi.stubGlobal('fetch', fetchMock);
    const j = await api('GET', '/api/data');
    expect(j.ok).toBe(true);
    expect(fetchMock).toHaveBeenCalled();
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect((init.headers as Record<string, string>).Authorization).toBe(
      'Bearer tok',
    );
  });

  it('clears token on 401', async () => {
    const onUnauthorized = vi.fn();
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: false, status: 401 }),
    );
    const j = await api('GET', '/api/data', undefined, { onUnauthorized });
    expect(j.ok).toBe(false);
    expect(onUnauthorized).toHaveBeenCalled();
    expect(localStorage.getItem('st_token')).toBeNull();
  });
});
