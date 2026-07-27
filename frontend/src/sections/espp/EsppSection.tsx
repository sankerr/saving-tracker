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
import EsppDetail from './EsppDetail';

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
  const [discount, setDiscount] = useState('15');
  const [offering, setOffering] = useState('6');
  const [lookback, setLookback] = useState(true);

  async function save() {
    const tk = ticker.trim().toUpperCase();
    if (!tk) {
      toast(t('toast.pickTicker'), 'error');
      return;
    }
    const j = await api('POST', '/api/espp-plans', {
      ticker: tk,
      nickname,
      discount_pct: Number(discount),
      has_lookback: lookback,
      offering_months: Number(offering),
    });
    if (j.ok === false) toast(j.error || t('common.failed'), 'error');
    else {
      toast(t('toast.esppAdded'), 'info');
      setAdding(false);
      await reload({ spinner: false });
    }
  }

  return (
    <HoldingsCard
      id="espp-card"
      titleKey="section.espp"
      count={plans.length}
      onAdd={() => setAdding((v) => !v)}
      addLabel={t('espp.add')}
      helpSection="espp"
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
          <label>
            {t('espp.discountLabel')}
            <input value={discount} onChange={(e) => setDiscount(e.target.value)} />
          </label>
          <label>
            {t('espp.offeringLength')}
            <input value={offering} onChange={(e) => setOffering(e.target.value)} />
          </label>
          <label>
            <span>{t('espp.plusLookback')}</span>
            <input
              type="checkbox"
              checked={lookback}
              onChange={(e) => setLookback(e.target.checked)}
            />
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
            subtitle={`${p.discount_pct ?? ''}% · ${p.offering_months ?? ''}m`}
            valueIls={p.computed?.current_value_ils}
            profitIls={p.computed?.profit_ils}
            profitPct={p.computed?.profit_pct}
            extraValue={
              p.computed?.current_value_usd != null
                ? fmtUsd(p.computed.current_value_usd)
                : undefined
            }
          >
            <EsppDetail plan={p} onChanged={() => reload({ spinner: false })} />
          </HoldingRow>
        ))
      )}
    </HoldingsCard>
  );
}
