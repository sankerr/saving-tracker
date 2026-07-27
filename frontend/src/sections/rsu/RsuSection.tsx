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
import RsuDetail from './RsuDetail';

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
  const [vestStart, setVestStart] = useState('');
  const [vestMonths, setVestMonths] = useState('48');
  const [cliff, setCliff] = useState('12');
  const [cadence, setCadence] = useState('monthly');
  const [nickname, setNickname] = useState('');
  const [grantPriceOverride, setGrantPriceOverride] = useState('');

  async function save() {
    const tk = ticker.trim().toUpperCase();
    if (!tk) {
      toast(t('toast.pickTicker'), 'error');
      return;
    }
    if (!grantDate || !shares) {
      toast(t('toast.dateSharesRequired'), 'error');
      return;
    }
    const j = await api('POST', '/api/rsu-grants', {
      ticker: tk,
      nickname,
      grant_date: grantDate,
      total_shares: Number(shares),
      vesting_start: vestStart || grantDate,
      vesting_months: Number(vestMonths),
      cliff_months: Number(cliff),
      vesting_cadence: cadence,
      grant_price_override_usd: grantPriceOverride.trim()
        ? Number(grantPriceOverride)
        : null,
    });
    if (j.ok === false) toast(j.error || t('common.failed'), 'error');
    else {
      toast(t('toast.grantAdded'), 'info');
      setAdding(false);
      await reload({ spinner: false });
    }
  }

  return (
    <HoldingsCard
      id="rsu-card"
      titleKey="section.rsu"
      count={grants.length}
      onAdd={() => setAdding((v) => !v)}
      addLabel={t('rsu.add')}
      helpSection="rsu"
    >
      {adding ? (
        <div className="add-panel">
          <label>
            {t('common.tickerSearch')}
            <input value={ticker} onChange={(e) => setTicker(e.target.value)} />
          </label>
          <label>
            {t('table.shares')}
            <input value={shares} onChange={(e) => setShares(e.target.value)} />
          </label>
          <label>
            {t('common.date')}
            <input type="date" value={grantDate} onChange={(e) => setGrantDate(e.target.value)} />
          </label>
          <label>
            {t('rsu.vestingStart') || t('common.date')}
            <input type="date" value={vestStart} onChange={(e) => setVestStart(e.target.value)} />
          </label>
          <label>
            {t('rsu.vestingMonths') || 'Months'}
            <input value={vestMonths} onChange={(e) => setVestMonths(e.target.value)} />
          </label>
          <label>
            {t('rsu.cliffMonths') || 'Cliff'}
            <input value={cliff} onChange={(e) => setCliff(e.target.value)} />
          </label>
          <label>
            {t('rsu.vestingCadence')}
            <select value={cadence} onChange={(e) => setCadence(e.target.value)}>
              <option value="monthly">monthly</option>
              <option value="quarterly">quarterly</option>
            </select>
          </label>
          <label>
            {t('action.setGrantPrice')}
            <input
              value={grantPriceOverride}
              onChange={(e) => setGrantPriceOverride(e.target.value)}
            />
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
              g.computed?.current_value_usd != null
                ? fmtUsd(g.computed.current_value_usd)
                : g.computed?.value_usd != null
                  ? fmtUsd(g.computed.value_usd)
                  : undefined
            }
          >
            <RsuDetail grant={g} onChanged={() => reload({ spinner: false })} />
          </HoldingRow>
        ))
      )}
    </HoldingsCard>
  );
}
