import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import ChatDrawer from '../chat/ChatDrawer';
import { t } from '../copy';
import { usePortfolio } from '../portfolio/PortfolioProvider';
import CashSection from '../sections/cash/CashSection';
import DashboardSection from '../sections/dashboard/DashboardSection';
import EsppSection from '../sections/espp/EsppSection';
import FundsSection from '../sections/funds/FundsSection';
import PensionSection from '../sections/pension/PensionSection';
import RetirementSection from '../sections/retirement/RetirementSection';
import RsuSection from '../sections/rsu/RsuSection';
import SettingsSection from '../sections/settings/SettingsSection';
import { useTheme } from '../theme/ThemeProvider';
import './shell.css';

const SECTIONS = [
  { id: 'dashboard-card', key: 'section.dashboard' },
  { id: 'funds-card', key: 'section.funds', count: 'funds' as const },
  { id: 'pension-card', key: 'section.pension', count: 'pension' as const },
  { id: 'retirement-simulator-card', key: 'section.retirementSim' },
  { id: 'rsu-card', key: 'section.rsu', count: 'rsu' as const },
  { id: 'espp-card', key: 'section.espp', count: 'espp' as const },
  { id: 'cash-card', key: 'section.cash', count: 'cash' as const },
  { id: 'settings-card', key: 'section.settings' },
] as const;

export default function AppShell() {
  const navigate = useNavigate();
  const { cyclePreference } = useTheme();
  const { data, status, statusMessage, sync, logout } = usePortfolio();
  const [chatOpen, setChatOpen] = useState(false);
  const [active, setActive] = useState('dashboard-card');
  const [disclaimerOpen, setDisclaimerOpen] = useState(() => {
    return localStorage.getItem('st_disclaimer_ack') !== '1';
  });

  const counts = useMemo(
    () => ({
      funds: (data?.fund_holdings || []).filter((h) => !h.archived).length,
      pension: (data?.pension_holdings || []).filter((h) => !h.archived).length,
      rsu: (data?.rsu_grants || []).filter((g) => !g.archived).length,
      espp: (data?.espp_plans || []).filter((p) => !p.archived).length,
      cash: (data?.cash_holdings || []).length,
    }),
    [data],
  );

  useEffect(() => {
    const chromeH = 96;
    const observer = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) setActive(e.target.id);
        }
      },
      { rootMargin: `-${chromeH}px 0px -55% 0px`, threshold: 0 },
    );
    for (const s of SECTIONS) {
      const el = document.getElementById(s.id);
      if (el) observer.observe(el);
    }
    return () => observer.disconnect();
  }, [data]);

  function scrollTo(id: string) {
    const el = document.getElementById(id);
    if (!el) return;
    const y = el.getBoundingClientRect().top + window.scrollY - 100;
    window.scrollTo({ top: Math.max(0, y), behavior: 'smooth' });
    setActive(id);
  }

  function ackDisclaimer() {
    localStorage.setItem('st_disclaimer_ack', '1');
    setDisclaimerOpen(false);
  }

  return (
    <div className="app-shell">
      {status === 'pending' ? <div className="load-bar" aria-hidden /> : null}

      <header className="top-chrome">
        <div className="top-chrome__brand">
          <strong className="brand">{t('hero.title')}</strong>
          <span className={`status-pill status-pill--${status}`} data-testid="status-pill">
            {statusMessage || t('status.loading')}
          </span>
        </div>
        <div className="top-chrome__actions">
          <button
            type="button"
            className="btn"
            onClick={() => setChatOpen(true)}
            aria-label={t('chrome.openAiChat')}
          >
            {t('chrome.aiChat')}
          </button>
          <button
            type="button"
            className="btn"
            onClick={cyclePreference}
            aria-label={t('chrome.toggleTheme')}
            title={t('chrome.toggleTheme')}
          >
            ◐
          </button>
          <button type="button" className="btn" onClick={() => void sync()}>
            {t('chrome.refresh')}
          </button>
          <button
            type="button"
            className="btn"
            onClick={() => {
              logout();
              navigate('/login', { replace: true });
            }}
          >
            {t('chrome.signOut')}
          </button>
        </div>
      </header>

      <div className="disclaimer-bar">
        <button
          type="button"
          className="disclaimer-toggle"
          aria-expanded={disclaimerOpen}
          onClick={() => setDisclaimerOpen((v) => !v)}
        >
          {t('disclaimer.compact')}
        </button>
        {disclaimerOpen ? (
          <div className="disclaimer-details">
            <p>{t('hero.subtitle')}</p>
            <p>
              <strong>{t('disclaimer.title')}</strong>
            </p>
            <ul>
              {(
                [
                  'disclaimer.item.beta',
                  'disclaimer.item.personalUse',
                  'disclaimer.item.notAdvice',
                  'disclaimer.item.noTax',
                  'disclaimer.item.dataStale',
                  'disclaimer.item.projections',
                  'disclaimer.item.ownRisk',
                  'disclaimer.item.responsibility',
                ] as const
              ).map((key) => (
                <li key={key} dangerouslySetInnerHTML={{ __html: t(key) }} />
              ))}
            </ul>
            <button type="button" className="btn" onClick={ackDisclaimer}>
              {t('common.gotIt')}
            </button>
          </div>
        ) : null}
      </div>

      <nav className="section-nav" aria-label={t('nav.aria')}>
        {SECTIONS.map((s) => {
          const count =
            'count' in s && s.count ? counts[s.count as keyof typeof counts] : 0;
          return (
            <button
              key={s.id}
              type="button"
              className="nav-pill"
              data-target={s.id}
              aria-current={active === s.id ? 'page' : undefined}
              onClick={() => scrollTo(s.id)}
            >
              <span>{t(s.key)}</span>
              {'count' in s && s.count ? (
                <span className="nav-pill__badge" hidden={count === 0}>
                  {count}
                </span>
              ) : null}
            </button>
          );
        })}
      </nav>

      <main id="app-main">
        <DashboardSection />
        <FundsSection />
        <PensionSection />
        <RetirementSection />
        <RsuSection />
        <EsppSection />
        <CashSection />
        <SettingsSection />
      </main>

      <ChatDrawer open={chatOpen} onClose={() => setChatOpen(false)} />
    </div>
  );
}
