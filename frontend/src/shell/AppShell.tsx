import { useNavigate } from 'react-router-dom';
import { setToken } from '../auth/token';
import { t } from '../copy';
import { useTheme } from '../theme/ThemeProvider';
import './shell.css';

const SECTIONS = [
  { id: 'dashboard-card', key: 'section.dashboard' },
  { id: 'funds-card', key: 'section.funds' },
  { id: 'pension-card', key: 'section.pension' },
  { id: 'retirement-simulator-card', key: 'section.retirementSim' },
  { id: 'rsu-card', key: 'section.rsu' },
  { id: 'espp-card', key: 'section.espp' },
  { id: 'cash-card', key: 'section.cash' },
  { id: 'settings-card', key: 'section.settings' },
] as const;

function SectionPlaceholder({
  id,
  titleKey,
}: {
  id: string;
  titleKey: string;
}) {
  return (
    <section className="card" id={id}>
      <h2>{t(titleKey)}</h2>
      <p className="muted">{t('hero.subtitle')}</p>
    </section>
  );
}

export default function AppShell() {
  const navigate = useNavigate();
  const { cyclePreference } = useTheme();

  function logout() {
    setToken('');
    navigate('/login', { replace: true });
  }

  function scrollTo(id: string) {
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' });
  }

  return (
    <div className="app-shell">
      <header className="top-chrome">
        <strong className="brand">{t('hero.title')}</strong>
        <div className="top-chrome__actions">
          <button
            type="button"
            className="btn"
            onClick={cyclePreference}
            aria-label={t('chrome.toggleTheme')}
            title={t('chrome.toggleTheme')}
          >
            ◐
          </button>
          <button type="button" className="btn" onClick={logout}>
            {t('chrome.signOut')}
          </button>
        </div>
      </header>

      <nav className="section-nav" aria-label={t('nav.aria')}>
        {SECTIONS.map((s) => (
          <button
            key={s.id}
            type="button"
            className="nav-pill"
            onClick={() => scrollTo(s.id)}
          >
            {t(s.key)}
          </button>
        ))}
      </nav>

      <main id="app-main">
        {SECTIONS.map((s) => (
          <SectionPlaceholder key={s.id} id={s.id} titleKey={s.key} />
        ))}
      </main>
    </div>
  );
}
