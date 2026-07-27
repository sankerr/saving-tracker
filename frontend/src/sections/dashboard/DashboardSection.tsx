import { useEffect, useMemo, useState } from 'react';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Filler,
  Tooltip,
  Legend,
} from 'chart.js';
import { Line } from 'react-chartjs-2';
import { api } from '../../api/client';
import { t } from '../../copy';
import { fmtIls, fmtPctSigned, fmtUsd } from '../../lib/format';
import { usePortfolio } from '../../portfolio/PortfolioProvider';
import HelpButton from '../../shell/HelpButton';
import { useToast } from '../../shell/ToastProvider';
import './dashboard.css';

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Filler,
  Tooltip,
  Legend,
);

function fmtGoalMonth(dateStr: string): string {
  const [y, m] = dateStr.split('-').map(Number);
  return new Date(y!, (m || 1) - 1, 1).toLocaleDateString('he-IL', {
    month: 'short',
    year: 'numeric',
  });
}

export default function DashboardSection() {
  const { data, status, whatIfPct, setWhatIfPct, horizon, setHorizon, reload } = usePortfolio();
  const { toast } = useToast();
  const [whatIfInput, setWhatIfInput] = useState(
    whatIfPct != null ? String(whatIfPct) : '',
  );
  const [insight, setInsight] = useState<string | null>(null);
  const [insightBusy, setInsightBusy] = useState(false);

  const p = data?.portfolio;
  const goal = data?.goal_status;
  const pension = data?.pension_summary;

  useEffect(() => {
    setWhatIfInput(whatIfPct != null ? String(whatIfPct) : '');
  }, [whatIfPct]);

  useEffect(() => {
    if (!data) return;
    let cancelled = false;
    (async () => {
      setInsightBusy(true);
      const j = await api<{ text?: string; insight?: string }>(
        'GET',
        '/api/insights?lang=he',
        undefined,
        { silent: true, retries: 0 },
      );
      if (cancelled) return;
      setInsightBusy(false);
      if (j.ok === false) {
        setInsight(null);
        return;
      }
      setInsight(j.text || j.insight || null);
    })();
    return () => {
      cancelled = true;
    };
  }, [data?.now]);

  const chartData = useMemo(() => {
    const series = p?.time_series_ils || [];
    const labels = series.map((pt) => pt.label || String(pt.period || ''));
    return {
      labels,
      datasets: [
        {
          label: t('section.dashboard'),
          data: series.map((pt) => pt.total_ils ?? 0),
          borderColor: '#6E5FE0',
          backgroundColor: 'rgba(110, 95, 224, 0.12)',
          fill: true,
          tension: 0.25,
          pointRadius: 0,
        },
      ],
    };
  }, [p?.time_series_ils]);

  const profit = p?.total_profit_ils || 0;
  const invested = p?.total_invested_ils || 0;
  const profitPct = invested ? profit / invested : 0;

  const alloc = [
    { key: 'funds', value: p?.funds_value_ils || 0, color: 'var(--color-funds)' },
    { key: 'rsu', value: p?.rsu_value_ils || 0, color: 'var(--color-rsu)' },
    { key: 'espp', value: p?.espp_value_ils || 0, color: 'var(--color-espp)' },
    { key: 'cash', value: p?.cash_value_ils || 0, color: 'var(--color-cash)' },
  ];
  const allocTotal = alloc.reduce((s, a) => s + a.value, 0) || 1;

  async function saveGoal() {
    const amountRaw = window.prompt(t('goal.amount'), String(goal?.target_amount_ils || ''));
    if (amountRaw == null) return;
    const dateRaw = window.prompt(t('goal.date'), goal?.target_date || '2030-12-01');
    if (dateRaw == null) return;
    const amount = Number(amountRaw);
    if (!Number.isFinite(amount) || amount <= 0) {
      toast(t('goal.errAmount'), 'error');
      return;
    }
    const j = await api('POST', '/api/settings', {
      goal: { target_amount_ils: amount, target_date: dateRaw },
    });
    if (j.ok === false) toast(j.error || t('common.failed'), 'error');
    else {
      toast(t('goal.saved'), 'info');
      await reload({ spinner: false });
    }
  }

  async function clearGoal() {
    const j = await api('POST', '/api/settings', { goal: null });
    if (j.ok === false) toast(j.error || t('common.failed'), 'error');
    else await reload({ spinner: false });
  }

  function applyWhatIf() {
    const v = whatIfInput.trim() === '' ? null : Number(whatIfInput);
    if (v !== null && Number.isNaN(v)) {
      toast(t('common.failed'), 'error');
      return;
    }
    setWhatIfPct(v);
  }

  return (
    <section className="card" id="dashboard-card">
      <h2>
        {t('section.dashboard')} <HelpButton section="dashboard" />
      </h2>

      {status === 'pending' && !p ? (
        <p className="muted">{t('status.loading')}</p>
      ) : (
        <>
          <p className="dash-total" data-testid="dash-total">
            {fmtIls(p?.total_value_ils || 0)}
          </p>
          <p
            className="dash-profit"
            data-sign={profit >= 0 ? 'pos' : 'neg'}
            data-testid="dash-profit"
          >
            {profit >= 0 ? '+' : ''}
            {fmtIls(profit)} ({fmtPctSigned(profitPct)})
          </p>
          <p className="dash-subline">
            {t('label.funds')} <strong>{fmtIls(p?.funds_value_ils || 0)}</strong>
            {' · '}
            {t('label.rsu')} <strong>{fmtUsd(p?.rsu_value_usd || 0)}</strong>
            {' ≈ '}
            <strong>{fmtIls(p?.rsu_value_ils || 0)}</strong>
            {(p?.espp_value_ils || 0) > 0 ? (
              <>
                {' · '}
                {t('label.espp')} <strong>{fmtUsd(p?.espp_value_usd || 0)}</strong>
                {' ≈ '}
                <strong>{fmtIls(p?.espp_value_ils || 0)}</strong>
              </>
            ) : null}
            {(p?.cash_value_ils || 0) > 0 ? (
              <>
                {' · '}
                {t('label.cash')} <strong>{fmtIls(p?.cash_value_ils || 0)}</strong>
              </>
            ) : null}
          </p>

          <div className="alloc-bar" aria-hidden>
            {alloc.map((a) =>
              a.value > 0 ? (
                <span
                  key={a.key}
                  style={{
                    width: `${(a.value / allocTotal) * 100}%`,
                    background: a.color,
                  }}
                />
              ) : null,
            )}
          </div>

          <div className="dash-goal" data-testid="dash-goal">
            {goal ? (
              <>
                <p>
                  {t('goal.headline', {
                    amount: fmtIls(goal.target_amount_ils),
                    date: fmtGoalMonth(goal.target_date),
                  })}
                </p>
                <div className="goal-actions">
                  <button type="button" className="btn" onClick={() => void saveGoal()}>
                    {t('goal.editTitle')}
                  </button>
                  <button type="button" className="btn" onClick={() => void clearGoal()}>
                    {t('goal.clear')}
                  </button>
                </div>
              </>
            ) : (
              <button type="button" className="btn" onClick={() => void saveGoal()}>
                {t('goal.setCta')}
              </button>
            )}
          </div>

          {pension && (pension.count || 0) > 0 ? (
            <p
              className="dash-pension-note"
              dangerouslySetInnerHTML={{
                __html: t('dashboard.pensionNote', {
                  amount: fmtIls(pension.total_value_ils || 0),
                }),
              }}
            />
          ) : null}

          {p?.what_if?.end_value_ils != null ? (
            <p className="summary-line">
              {t('dash.whatIfSummary', {
                pct: p.what_if.annual_pct ?? '',
                months: p.what_if.horizon_months ?? '',
                end: fmtIls(p.what_if.end_value_ils),
                sign:
                  (p.what_if.end_value_ils || 0) - (p.what_if.current_value_ils || 0) >= 0
                    ? '+'
                    : '',
                delta: fmtIls(
                  (p.what_if.end_value_ils || 0) - (p.what_if.current_value_ils || 0),
                ),
              })}
            </p>
          ) : null}

          <div className="what-if-row">
            <span>{t('dashboard.horizon')}</span>
            {[6, 12, 24, 60, 120].map((h) => (
              <button
                key={h}
                type="button"
                className="btn"
                aria-pressed={horizon === h}
                onClick={() => setHorizon(h)}
              >
                {h}m
              </button>
            ))}
          </div>

          <div className="what-if-row">
            <label>
              {t('dashboard.whatIfGrow')}
              <input
                value={whatIfInput}
                onChange={(e) => setWhatIfInput(e.target.value)}
                inputMode="decimal"
                title={t('dashboard.whatIfInputTitle')}
              />
            </label>
            <button type="button" className="btn" onClick={applyWhatIf}>
              {t('common.save')}
            </button>
            <button
              type="button"
              className="btn"
              onClick={() => {
                setWhatIfInput('');
                setWhatIfPct(null);
              }}
            >
              {t('common.cancel')}
            </button>
          </div>

          <div className="chart-wrap">
            {(p?.time_series_ils || []).length ? (
              <Line
                data={chartData}
                options={{
                  responsive: true,
                  maintainAspectRatio: false,
                  plugins: { legend: { display: false } },
                  scales: {
                    x: { ticks: { maxTicksLimit: 8 } },
                    y: {
                      ticks: {
                        callback: (v) => fmtIls(Number(v)),
                      },
                    },
                  },
                }}
              />
            ) : (
              <p className="muted">—</p>
            )}
          </div>

          <div className="ai-insight" id="ai-insight" data-testid="ai-insight">
            <div className="ai-insight__head">
              <strong>{t('insights.title')}</strong>
              <button
                type="button"
                className="btn"
                disabled={insightBusy}
                onClick={async () => {
                  setInsightBusy(true);
                  const j = await api<{ text?: string; insight?: string }>(
                    'GET',
                    '/api/insights?lang=he&force=1',
                    undefined,
                    { silent: true, retries: 0 },
                  );
                  setInsightBusy(false);
                  if (j.ok === false) toast(j.error || t('common.failed'), 'error');
                  else setInsight(j.text || j.insight || null);
                }}
              >
                {t('insights.refresh')}
              </button>
            </div>
            <p className="ai-insight__body">
              {insightBusy ? t('insights.loading') : insight || '—'}
            </p>
          </div>
        </>
      )}
    </section>
  );
}
