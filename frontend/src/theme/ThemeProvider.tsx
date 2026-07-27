import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';

export type ThemePreference = 'system' | 'light' | 'dark';

const THEME_KEY = 'st_theme';

function resolveTheme(pref: ThemePreference): 'light' | 'dark' {
  if (pref === 'light' || pref === 'dark') return pref;
  return window.matchMedia('(prefers-color-scheme: dark)').matches
    ? 'dark'
    : 'light';
}

function applyTheme(resolved: 'light' | 'dark') {
  document.documentElement.dataset.theme = resolved;
  document.documentElement.style.colorScheme = resolved;
  const meta = document.getElementById('meta-theme-color');
  if (meta instanceof HTMLMetaElement) {
    meta.content = resolved === 'dark' ? '#0F0F1A' : '#F4F5F8';
  }
}

type ThemeContextValue = {
  preference: ThemePreference;
  resolved: 'light' | 'dark';
  setPreference: (pref: ThemePreference) => void;
  cyclePreference: () => void;
};

const ThemeContext = createContext<ThemeContextValue | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [preference, setPreferenceState] = useState<ThemePreference>(() => {
    const v = localStorage.getItem(THEME_KEY);
    return v === 'light' || v === 'dark' || v === 'system' ? v : 'system';
  });
  const [resolved, setResolved] = useState<'light' | 'dark'>(() =>
    resolveTheme(preference),
  );

  useEffect(() => {
    const next = resolveTheme(preference);
    setResolved(next);
    applyTheme(next);
    if (preference !== 'system') return;
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const onChange = () => {
      const r = resolveTheme('system');
      setResolved(r);
      applyTheme(r);
    };
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, [preference]);

  const setPreference = useCallback((pref: ThemePreference) => {
    localStorage.setItem(THEME_KEY, pref);
    setPreferenceState(pref);
  }, []);

  const cyclePreference = useCallback(() => {
    const order: ThemePreference[] = ['system', 'light', 'dark'];
    const i = order.indexOf(preference);
    setPreference(order[(i + 1) % order.length]!);
  }, [preference, setPreference]);

  const value = useMemo(
    () => ({ preference, resolved, setPreference, cyclePreference }),
    [preference, resolved, setPreference, cyclePreference],
  );

  return (
    <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
  );
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error('useTheme must be used within ThemeProvider');
  return ctx;
}
