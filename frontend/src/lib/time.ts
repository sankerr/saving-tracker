import { t } from '../copy';

export function timeAgo(iso?: string | null): string {
  if (!iso) return t('time.never');
  let s = String(iso);
  if (!/[zZ]|[+-]\d{2}:?\d{2}$/.test(s)) s += 'Z';
  const d = new Date(s);
  const sec = Math.floor((Date.now() - d.getTime()) / 1000);
  if (sec < 60) return t('time.justNow');
  if (sec < 3600) return t('time.minAgo', { n: Math.floor(sec / 60) });
  if (sec < 86400) return t('time.hAgo', { n: Math.floor(sec / 3600) });
  return t('time.dAgo', { n: Math.floor(sec / 86400) });
}

export function periodLabel(period?: number | null): string {
  if (!period) return '—';
  const y = Math.floor(period / 100);
  const m = period % 100;
  return new Date(y, m - 1, 1).toLocaleDateString('he-IL', {
    month: 'short',
    year: 'numeric',
  });
}
