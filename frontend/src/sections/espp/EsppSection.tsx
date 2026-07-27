import { useMemo, useState } from 'react';
import { api } from '../../api/client';
import { t } from '../../copy';
import { usePortfolio } from '../../portfolio/PortfolioProvider';
import { useToast } from '../../shell/ToastProvider';
import {
  EmptyHoldings,
  HoldingRow,
  HoldingsCard,
} from '../holdings/HoldingsShared';

export default function EsppSection() {
  const { data, reload } = usePortfolio();
  const { toast } = useToast();
  const plans = useMemo(
    () => (data?.espp_plans || []).filter((p) => !p.archived),
    [data?.espp_plans],
  );
  const [adding, setAdding] = useState(false);
  const [ticker, setTicker] = useState('');
  const [nickname, setNickname] = useState('');

  async function save() {
    const j = await api('POST', '/api/espp-plans', {
      ticker: ticker.trim().toUpperCase(),
      nickname,
    });
    if (j.ok === false) toast(j.error || t('common.failed'), 'error');
    else {
      toast(t('toast.esppAdded') || t('common.updated'), 'info');
      setAdding(false);
      await reload({ spinner: false });
    }
  }

  async function remove(id: string) {
    if (!window.confirm(t('common.confirm'))) return;
    const j = await api('DELETE', `/api/espp-plans/${id}`);
    if (j.ok === false) toast(j.error || t('common.failed'), 'error');
    else await reload({ spinner: false });
  }

  return (
    <HoldingsCard
      id="espp-card"
      titleKey="section.espp"
      count={plans.length}
      onAdd={() => setAdding((v) => !v)}
      addLabel={t('espp.add') || t('common.add')}
    >
      {adding ? (
        <div className="add-panel">
          <label>
            {t('common.tickerSearch')}
            <input value={ticker} onChange={(e) => setTicker(e.target.value)} />
          </label>
          <label>
            {t('common.nickname')}
            <input value={nickname} onChange={(e) => setNickname(e.target.value)} />
          </label>
          <div className="add-actions">
            <button type="button" className="btn" onClick={() => void save()}>
              {t('common.save')}
            </button>
            <button type="button" className="btn" onClick={() => setAdding(false)}>
              {t('common.cancel')}
            </button>
          </div>
        </div>
      ) : null}
      {!plans.length ? (
        <EmptyHoldings />
      ) : (
        plans.map((p) => (
          <HoldingRow
            key={p.id}
            title={p.nickname || p.ticker}
            valueIls={p.computed?.current_value_ils}
            profitIls={p.computed?.profit_ils}
            profitPct={p.computed?.profit_pct}
            onDelete={() => void remove(p.id)}
          />
        ))
      )}
    </HoldingsCard>
  );
}
