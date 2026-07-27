import { t } from '../../copy';
import { usePortfolio } from '../../portfolio/PortfolioProvider';
import { fmtIls } from '../../lib/format';

/** Lightweight retirement placeholder wired to live pension totals; full sim port follows. */
export default function RetirementSection() {
  const { data } = usePortfolio();
  const pension = data?.pension_summary;

  return (
    <section className="card" id="retirement-simulator-card">
      <h2>{t('section.retirementSim')}</h2>
      <p className="muted">{t('help.retirementSim.body') || t('hero.subtitle')}</p>
      {pension && (pension.count || 0) > 0 ? (
        <p>
          {t('section.pension')}:{' '}
          <strong>{fmtIls(pension.total_value_ils || 0)}</strong>
        </p>
      ) : (
        <p className="muted">{t('empty.pension.body') || '—'}</p>
      )}
    </section>
  );
}
