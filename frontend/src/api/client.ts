import { getToken, setToken } from '../auth/token';
import { t } from '../copy';

export type ApiResult<T = Record<string, unknown>> = T & {
  ok?: boolean;
  error?: string;
  token?: string;
  message?: string;
};

export type ApiOptions = {
  retries?: number;
  silent?: boolean;
  onUnauthorized?: () => void;
  onRetry?: () => void;
};

export function apiUrl(path: string): string {
  const base = (import.meta.env.VITE_API_BASE || '').replace(/\/$/, '');
  return `${base}${path}`;
}

export async function api<T = Record<string, unknown>>(
  method: string,
  path: string,
  body?: unknown,
  opts: ApiOptions = {},
): Promise<ApiResult<T>> {
  const { retries = 1, silent = false, onUnauthorized, onRetry } = opts;
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers['Content-Type'] = 'application/json';

  const init: RequestInit = {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  };

  let lastError: string | null = null;
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      if (attempt > 0) {
        if (!silent) onRetry?.();
        await new Promise((r) => setTimeout(r, 3000));
      }
      const r = await fetch(apiUrl(path), init);
      if (r.status === 401) {
        setToken('');
        onUnauthorized?.();
        return { ok: false, error: t('api.unauthorized') } as ApiResult<T>;
      }
      if (!r.ok && r.status >= 500) {
        lastError = `HTTP ${r.status}`;
        continue;
      }
      try {
        return (await r.json()) as ApiResult<T>;
      } catch {
        return { ok: false, error: t('api.invalidJson') } as ApiResult<T>;
      }
    } catch (err) {
      lastError =
        err instanceof Error ? err.message : t('api.networkError');
    }
  }
  return {
    ok: false,
    error: lastError || t('api.requestFailed'),
  } as ApiResult<T>;
}
