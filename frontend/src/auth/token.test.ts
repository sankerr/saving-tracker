import { describe, expect, it, beforeEach } from 'vitest';
import { getToken, setToken } from './token';

describe('token', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('stores and reads st_token', () => {
    expect(getToken()).toBe('');
    setToken('abc');
    expect(getToken()).toBe('abc');
    setToken('');
    expect(getToken()).toBe('');
  });
});
