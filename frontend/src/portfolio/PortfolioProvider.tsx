import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { api } from '../api/client';
import { setToken } from '../auth/token';
import { t } from '../copy';
import type { AppData } from './types';

export type StatusKind = 'idle' | 'pending' | 'ok' | 'error';

type PortfolioContextValue = {
  data: AppData | null;
  status: StatusKind;
  statusMessage: string;
  horizon: number;
  setHorizon: (months: number) => void;
  whatIfPct: number | null;
  setWhatIfPct: (pct: number | null) => void;
  reload: (opts?: { spinner?: boolean }) => Promise<void>;
  sync: () => Promise<void>;
  logout: () => void;
};

const PortfolioContext = createContext<PortfolioContextValue | null>(null);
const WHAT_IF_KEY = 'saving_what_if_pct';

function dataQuery(horizon: number, whatIfPct: number | null): string {
  let q = `horizon=${horizon}`;
  if (whatIfPct !== null && !Number.isNaN(whatIfPct)) {
    q += `&assumed_annual_pct=${whatIfPct}`;
  }
  return q;
}

export function PortfolioProvider({
  children,
  onUnauthorized,
}: {
  children: ReactNode;
  onUnauthorized: () => void;
}) {
  const [data, setData] = useState<AppData | null>(null);
  const [status, setStatus] = useState<StatusKind>('idle');
  const [statusMessage, setStatusMessage] = useState('');
  const [horizon, setHorizon] = useState(24);
  const [whatIfPct, setWhatIfPctState] = useState<number | null>(() => {
    const v = localStorage.getItem(WHAT_IF_KEY);
    return v === null || v === '' ? null : Number(v);
  });
  const epoch = useRef(0);

  const logout = useCallback(() => {
    epoch.current += 1;
    setToken('');
    localStorage.removeItem(WHAT_IF_KEY);
    setWhatIfPctState(null);
    setData(null);
    onUnauthorized();
  }, [onUnauthorized]);

  const setWhatIfPct = useCallback((pct: number | null) => {
    setWhatIfPctState(pct);
    if (pct === null || Number.isNaN(pct)) localStorage.removeItem(WHAT_IF_KEY);
    else localStorage.setItem(WHAT_IF_KEY, String(pct));
  }, []);

  const reload = useCallback(
    async ({ spinner = true }: { spinner?: boolean } = {}) => {
      const myEpoch = epoch.current;
      if (spinner) {
        setStatus('pending');
        setStatusMessage(t('status.loading'));
      }
      const j = await api<AppData>('GET', `/api/data?${dataQuery(horizon, whatIfPct)}`, undefined, {
        retries: 2,
        onUnauthorized: logout,
        onRetry: () => {
          setStatus('pending');
          setStatusMessage(t('status.wakingServer'));
        },
      });
      if (myEpoch !== epoch.current) return;
      if (j.ok === false) {
        setStatus('error');
        setStatusMessage(j.error || t('status.failedLoad'));
        return;
      }
      setData(j);
      const rate = j.cache_status?.current_usdils;
      setStatus('ok');
      setStatusMessage(
        rate != null
          ? t('status.loadedUsdils', { rate: rate.toFixed(3) })
          : t('status.synced'),
      );
    },
    [logout, whatIfPct, horizon],
  );

  const sync = useCallback(async () => {
    const myEpoch = epoch.current;
    setStatus('pending');
    setStatusMessage(t('status.syncing'));
    const j = await api('POST', `/api/sync?${dataQuery(horizon, whatIfPct)}`, undefined, {
      retries: 2,
      onUnauthorized: logout,
      onRetry: () => setStatusMessage(t('status.wakingServer')),
    });
    if (myEpoch !== epoch.current) return;
    if (j.ok === false) {
      setStatus('error');
      setStatusMessage(j.error || t('status.syncFailed'));
      return;
    }
    await reload({ spinner: false });
  }, [logout, reload, whatIfPct, horizon]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const value = useMemo(
    () => ({
      data,
      status,
      statusMessage,
      horizon,
      setHorizon,
      whatIfPct,
      setWhatIfPct,
      reload,
      sync,
      logout,
    }),
    [data, status, statusMessage, horizon, whatIfPct, setWhatIfPct, reload, sync, logout],
  );

  return (
    <PortfolioContext.Provider value={value}>{children}</PortfolioContext.Provider>
  );
}

export function usePortfolio(): PortfolioContextValue {
  const ctx = useContext(PortfolioContext);
  if (!ctx) throw new Error('usePortfolio must be used within PortfolioProvider');
  return ctx;
}
