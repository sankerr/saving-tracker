import { useMemo, useState } from 'react';
import { api } from '../../api/client';
import { t } from '../../copy';
import { usePortfolio } from '../../portfolio/PortfolioProvider';
import { useToast } from '../../shell/ToastProvider';
import FundLikeDetail from '../holdings/FundLikeDetail';
import {
  EmptyHoldings,
  HoldingRow,
  HoldingsCard,
} from '../holdings/HoldingsShared';
import { fmtIls } from '../../lib/format';

type SearchHit = {
  fund_id: number;
  fund_name: string;
  managing_corporation?: string;
};

export default function PensionSection() {
  const { data, reload } = usePortfolio();
  const { toast } = useToast();
  const holdings = useMemo(
    () => (data?.pension_holdings || []).filter((h) => !h.archived),
    [data?.pension_holdings],
  );
  const summary = data?.pension_summary;
  const [adding, setAdding] = useState(false);
  const [q, setQ] = useState('');
  const [hits, setHits] = useState<SearchHit[]>([]);
  const [selected, setSelected] = useState<SearchHit | null>(null);
  const [nickname, setNickname] = useState('');
  const [balance, setBalance] = useState('');
  const [anchor, setAnchor] = useState('');

  async function search(value: string) {
    setQ(value);
    if (!value.trim()) {
      setHits([]);
      return;
    }
    const j = await api<{ results?: SearchHit[] }>(
      'GET',
      `/api/pension/search?q=${encodeURIComponent(value)}&limit=15`,
      undefined,
      { silent: true, retries: 0 },
    );
    setHits(j.ok === false ? [] : j.results || []);
  }

  async function save() {
    if (!selected) return;
    const bal = Number(balance);
    const period = Number(anchor);
    if (!Number.isFinite(bal) || bal < 0) {
      toast(t('toast.balanceNonNegative'), 'error');
      return;
    }
    if (!period) {
      toast(t('toast.pickBalanceMonth'), 'error');
      return;
    }
    const j = await api('POST', '/api/pension-holdings', {
      fund_id: selected.fund_id,
      nickname,
      anchor_balance_ils: bal,
      yield_is_net_of_fees: true,
      anchor_period: period,
    });
    if (j.ok === false) toast(j.error || t('common.failed'), 'error');
    else {
      toast(t('toast.pensionAdded'), 'info');
      setAdding(false);
      await reload({ spinner: false });
    }
  }

  const pwf = summary?.what_if;

  return (
    <HoldingsCard
      id="pension-card"
      titleKey="section.pension"
      count={holdings.length}
      onAdd={() => setAdding((v) => !v)}
      addLabel={t('pension.add')}
      helpSection="pension"
    >
      {holdings.length && summary?.total_value_ils != null ? (
        <p className="summary-line">
          {t('section.pension')}: <strong>{fmtIls(summary.total_value_ils)}</strong>
        </p>
      ) : null}
      {holdings.length && pwf?.end_value_ils != null ? (
        <p
          className="summary-line"
          dangerouslySetInnerHTML={{
            __html: t('pension.whatIfSummary', {
              pct: pwf.annual_pct ?? '',
              months: pwf.horizon_months ?? '',
              end: fmtIls(pwf.end_value_ils),
              sign: (pwf.end_value_ils || 0) - (pwf.current_value_ils || 0) >= 0 ? '+' : '',
              delta: fmtIls((pwf.end_value_ils || 0) - (pwf.current_value_ils || 0)),
              includes: pwf.includes_recurring
                ? t('pension.includesRecurring')
                : t('pension.noRecurring'),
            }),
          }}
        />
      ) : null}

      {adding ? (
        <div className="add-panel">
          <label>
            {t('common.searchFund')}
            <input value={q} onChange={(e) => void search(e.target.value)} />
          </label>
          <div className="search-results">
            {hits.map((h) => (
              <button
                key={h.fund_id}
                type="button"
                onClick={() => {
                  setSelected(h);
                  setHits([]);
                  setQ(`${h.fund_id} · ${h.fund_name}`);
                }}
              >
                {h.fund_id} · {h.fund_name}
              </button>
            ))}
          </div>
          {selected ? (
            <>
              <label>
                {t('common.nickname')}
                <input value={nickname} onChange={(e) => setNickname(e.target.value)} />
              </label>
              <label>
                {t('common.balanceIls')}
                <input value={balance} onChange={(e) => setBalance(e.target.value)} />
              </label>
              <label>
                {t('common.asOfPeriod')}
                <input
                  value={anchor}
                  onChange={(e) => setAnchor(e.target.value)}
                  placeholder="YYYYMM"
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
            </>
          ) : null}
        </div>
      ) : null}
      {!holdings.length ? (
        <EmptyHoldings />
      ) : (
        holdings.map((h) => (
          <HoldingRow
            key={h.id}
            title={h.nickname || h.fund_name_snapshot || String(h.fund_id)}
            subtitle={h.fund_name_snapshot}
            valueIls={h.computed?.current_value_ils}
            profitIls={h.computed?.profit_ils}
            profitPct={h.computed?.profit_pct}
          >
            <FundLikeDetail
              holding={h}
              kind="pension"
              onChanged={() => reload({ spinner: false })}
            />
          </HoldingRow>
        ))
      )}
    </HoldingsCard>
  );
}
