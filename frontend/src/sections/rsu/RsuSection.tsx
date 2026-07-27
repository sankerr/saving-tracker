import { useMemo, useState } from 'react';
import { api } from '../../api/client';
import { t } from '../../copy';
import { fmtUsd } from '../../lib/format';
import { usePortfolio } from '../../portfolio/PortfolioProvider';
import { useToast } from '../../shell/ToastProvider';
import {
  EmptyHoldings,
  HoldingRow,
  HoldingsCard,
} from '../holdings/HoldingsShared';

export default function RsuSection() {
  const { data, reload } = usePortfolio();
  const { toast } = useToast();
  const grants = useMemo(
    () => (data?.rsu_grants || []).filter((g) => !g.archived),
    [data?.rsu_grants],
  );
  const [adding, setAdding] = useState(false);
  const [ticker, setTicker] = useState('');
  const [shares, setShares] = useState('');
  const [grantDate, setGrantDate] = useState('');
  const [nickname, setNickname] = useState('');

  async function save() {
    const j = await api('POST', '/api/rsu-grants', {
      ticker: ticker.trim().toUpperCase(),
      shares: Number(shares),
      grant_date: grantDate,
      nickname,
    });
    if (j.ok === false) toast(j.error || t('common.failed'), 'error');
    else {
      toast(t('toast.rsuAdded') || t('common.updated'), 'info');
      setAdding(false);
      await reload({ spinner: false });
    }
  }

  async function remove(id: string) {
    if (!window.confirm(t('common.confirm'))) return;
    const j = await api('DELETE', `/api/rsu-grants/${id}`);
    if (j.ok === false) toast(j.error || t('common.failed'), 'error');
    else await reload({ spinner: false });
  }

  return (
    <HoldingsCard
      id="rsu-card"
      titleKey="section.rsu"
      count={grants.length}
      onAdd={() => setAdding((v) => !v)}
      addLabel={t('rsu.add') || t('common.add')}
    >
      {adding ? (
        <div className="add-panel">
          <label>
            {t('common.tickerSearch')}
            <input value={ticker} onChange={(e) => setTicker(e.target.value)} />
          </label>
          <label>
            {t('rsu.shares') || 'Shares'}
            <input value={shares} onChange={(e) => setShares(e.target.value)} />
          </label>
          <label>
            {t('common.date')}
            <input type="date" value={grantDate} onChange={(e) => setGrantDate(e.target.value)} />
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
      {!grants.length ? (
        <EmptyHoldings />
      ) : (
        grants.map((g) => (
          <HoldingRow
            key={g.id}
            title={g.nickname || g.ticker}
            subtitle={g.grant_date}
            valueIls={g.computed?.current_value_ils}
            profitIls={g.computed?.profit_ils}
            profitPct={g.computed?.profit_pct}
            extraValue={
              g.computed?.value_usd != null ? fmtUsd(g.computed.value_usd) : undefined
            }
            onDelete={() => void remove(g.id)}
          />
        ))
      )}
    </HoldingsCard>
  );
}
