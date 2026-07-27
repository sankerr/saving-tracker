import { useEffect, useMemo, useState } from 'react';
import { t } from '../../copy';
import { fmtIls } from '../../lib/format';
import {
  MINIMUM_PENSION,
  simulate,
  type Gender,
} from '../../lib/retirementSim';
import { usePortfolio } from '../../portfolio/PortfolioProvider';
import HelpButton from '../../shell/HelpButton';
import './retirement.css';

function rsimFmt(n: number): string {
  return fmtIls(Math.round(n));
}

export default function RetirementSection() {
  const { data } = usePortfolio();
  const pensionTotal = data?.pension_summary?.total_value_ils || 0;

  const [birthDate, setBirthDate] = useState('');
  const [gender, setGender] = useState<Gender>('male');
  const [retirementAge, setRetirementAge] = useState('67');
  const [comprehensive, setComprehensive] = useState('');
  const [supplementary, setSupplementary] = useState('0');
  const [targetPension, setTargetPension] = useState('20000');
  const [seededPension, setSeededPension] = useState(false);

  useEffect(() => {
    if (seededPension || pensionTotal <= 0) return;
    setComprehensive(String(Math.round(pensionTotal)));
    setSeededPension(true);
  }, [pensionTotal, seededPension]);

  const result = useMemo(
    () =>
      simulate({
        birthDate,
        gender,
        retirementAge,
        comprehensiveIls: comprehensive,
        supplementaryIls: supplementary,
        targetPensionIls: targetPension,
      }),
    [birthDate, gender, retirementAge, comprehensive, supplementary, targetPension],
  );

  const maxP = result.ok ? Math.floor(result.bounds.maxPension) : 50000;
  const showEmpty = !birthDate && !comprehensive;

  return (
    <section className="card" id="retirement-simulator-card">
      <h2>
        {t('section.retirementSim')} <HelpButton section="retirement-sim" />
      </h2>
      <p className="muted" dangerouslySetInnerHTML={{ __html: t('help.retirementSim.body') }} />

      <div className="rsim-grid">
        <label>
          {t('rsim.birthDate')}
          <input type="date" value={birthDate} onChange={(e) => setBirthDate(e.target.value)} />
        </label>
        <label>
          {t('rsim.gender')}
          <select
            value={gender}
            onChange={(e) => setGender(e.target.value as Gender)}
          >
            <option value="male">{t('rsim.gender.male')}</option>
            <option value="female">{t('rsim.gender.female')}</option>
          </select>
        </label>
        <label>
          {t('rsim.retirementAge')}
          <input
            type="number"
            min={55}
            max={75}
            value={retirementAge}
            onChange={(e) => setRetirementAge(e.target.value)}
          />
        </label>
        <label>
          {t('rsim.comprehensive')}
          <input
            type="number"
            min={0}
            step={1000}
            value={comprehensive}
            onChange={(e) => setComprehensive(e.target.value)}
          />
        </label>
        <label>
          {t('rsim.supplementary')}
          <input
            type="number"
            min={0}
            step={1000}
            value={supplementary}
            onChange={(e) => setSupplementary(e.target.value)}
          />
        </label>
        <label>
          {t('rsim.targetPension')}
          <input
            type="range"
            min={MINIMUM_PENSION}
            max={Math.max(MINIMUM_PENSION, maxP)}
            step={100}
            value={Math.min(Math.max(Number(targetPension) || MINIMUM_PENSION, MINIMUM_PENSION), Math.max(MINIMUM_PENSION, maxP))}
            onChange={(e) => setTargetPension(e.target.value)}
          />
          <input
            type="number"
            min={MINIMUM_PENSION}
            step={100}
            value={targetPension}
            onChange={(e) => setTargetPension(e.target.value)}
          />
          <span className="muted">
            {result.ok
              ? t('rsim.boundsMax', {
                  min: rsimFmt(MINIMUM_PENSION),
                  max: rsimFmt(maxP),
                })
              : t('rsim.boundsDefault', { min: rsimFmt(MINIMUM_PENSION) })}
          </span>
        </label>
      </div>

      {showEmpty ? null : !result.ok ? (
        <p className="auth-error">{result.error}</p>
      ) : (
        <>
          {(result.warnings || []).map((w) => (
            <p key={w} className="rsim-warn">
              {w}
            </p>
          ))}
          <div className="rsim-meta">
            <span>
              {t('rsim.retirement')}{' '}
              <strong>{result.retirementDate?.label || '—'}</strong>
            </span>
            <span>
              {t('rsim.currentAge')} <strong>{result.currentAge ?? '—'}</strong>
            </span>
            <span>
              {t('rsim.multiplier')} <strong>{result.multiplier.toFixed(1)}</strong>
            </span>
            <span>
              {t('rsim.totalBalance')} <strong>{rsimFmt(result.totalBalance)}</strong>
            </span>
          </div>
          <div className="rsim-paths">
            {(
              [
                ['path1', result.path1, false],
                ['path2', result.path2, false],
                ['path3', result.path3, false],
                ['path4', result.path4, true],
              ] as const
            ).map(([key, path, isPath4]) => (
              <article key={key} className="rsim-path">
                <h3>{t(`rsim.${key}`)}</h3>
                <dl className="detail-grid">
                  <div>
                    <dt>{t('rsim.monthlyPension')}</dt>
                    <dd className="highlight">{rsimFmt(path.monthlyPension)}</dd>
                  </div>
                  {isPath4 ? (
                    <>
                      <div>
                        <dt>{t('rsim.lockedMakifa')}</dt>
                        <dd>{rsimFmt(path.lockedCapital)}</dd>
                      </div>
                      {path.cashGross > 0 ? (
                        <>
                          <div>
                            <dt>{t('rsim.mashlimaCashGross')}</dt>
                            <dd>{rsimFmt(path.cashGross)}</dd>
                          </div>
                          <div>
                            <dt>{t('rsim.taxFreePortion')}</dt>
                            <dd>{rsimFmt(path.taxFreeCash)}</dd>
                          </div>
                          <div>
                            <dt>{t('rsim.taxablePortion')}</dt>
                            <dd>{rsimFmt(path.taxableCash)}</dd>
                          </div>
                          <div>
                            <dt>{t('rsim.estTax')}</dt>
                            <dd>{rsimFmt(path.estimatedTax)}</dd>
                          </div>
                          <div>
                            <dt>{t('rsim.mashlimaCashNet')}</dt>
                            <dd className="highlight">{rsimFmt(path.netCash)}</dd>
                          </div>
                        </>
                      ) : (
                        <div>
                          <dt>{t('rsim.mashlimaCash')}</dt>
                          <dd>{rsimFmt(0)}</dd>
                        </div>
                      )}
                    </>
                  ) : path.cashGross > 0 ? (
                    <>
                      <div>
                        <dt>{t('rsim.lockedForPension')}</dt>
                        <dd>{rsimFmt(path.lockedCapital)}</dd>
                      </div>
                      <div>
                        <dt>{t('rsim.cashGross')}</dt>
                        <dd>{rsimFmt(path.cashGross)}</dd>
                      </div>
                      <div>
                        <dt>{t('rsim.taxFreePortion')}</dt>
                        <dd>{rsimFmt(path.taxFreeCash)}</dd>
                      </div>
                      <div>
                        <dt>{t('rsim.taxablePortion')}</dt>
                        <dd>{rsimFmt(path.taxableCash)}</dd>
                      </div>
                      <div>
                        <dt>{t('rsim.estTax')}</dt>
                        <dd>{rsimFmt(path.estimatedTax)}</dd>
                      </div>
                      <div>
                        <dt>{t('rsim.cashNet')}</dt>
                        <dd className="highlight">{rsimFmt(path.netCash)}</dd>
                      </div>
                    </>
                  ) : (
                    <div>
                      <dt>{t('rsim.lockedForPension')}</dt>
                      <dd>{rsimFmt(path.lockedCapital)}</dd>
                    </div>
                  )}
                </dl>
              </article>
            ))}
          </div>
        </>
      )}
    </section>
  );
}
