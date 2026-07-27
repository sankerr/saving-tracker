import { useState } from 'react';
import { api } from '../../api/client';
import { t } from '../../copy';
import { fmtUsd } from '../../lib/format';
import { timeAgo } from '../../lib/time';
import type { EsppPlan } from '../../portfolio/types';
import { useToast } from '../../shell/ToastProvider';
import DetailChart from '../holdings/DetailChart';

const fmtUsdPrec = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  maximumFractionDigits: 2,
});

export default function EsppDetail({
  plan,
  onChanged,
}: {
  plan: EsppPlan;
  onChanged: () => Promise<void>;
}) {
  const { toast } = useToast();
  const p = plan;
  const c = p.computed || {};
  const purchases = [...(p.purchases || [])].sort((a, b) => a.date.localeCompare(b.date));
  const sales = [...(p.sales || [])].sort((a, b) => a.date.localeCompare(b.date));

  const [purDate, setPurDate] = useState(new Date().toISOString().slice(0, 10));
  const [contribution, setContribution] = useState('');
  const [shares, setShares] = useState('');
  const [periodStart, setPeriodStart] = useState('');
  const [periodEnd, setPeriodEnd] = useState('');
  const [buyPrice, setBuyPrice] = useState('');
  const [periodEndPrice, setPeriodEndPrice] = useState('');
  const [purNote, setPurNote] = useState('');

  const [saleDate, setSaleDate] = useState(new Date().toISOString().slice(0, 10));
  const [saleShares, setSaleShares] = useState('');
  const [salePrice, setSalePrice] = useState('');
  const [saleNote, setSaleNote] = useState('');

  const valueSeries = (c.time_series || []).map((pt) => ({
    label: String(pt.date ?? pt.period ?? ''),
    value: pt.value_ils ?? 0,
  }));
  const stockSeries = (p.stock_history || []).map((pt) => ({
    label: pt.date,
    value: pt.close,
  }));

  async function addPurchase() {
    const j = await api('POST', `/api/espp-plans/${p.id}/purchases`, {
      date: purDate,
      contribution_usd: Number(contribution),
      shares: Number(shares),
      period_start: periodStart || null,
      period_end: periodEnd || null,
      buy_price_usd: buyPrice ? Number(buyPrice) : null,
      period_end_price_usd: periodEndPrice ? Number(periodEndPrice) : null,
      note: purNote,
    });
    if (j.ok === false) toast(j.error || t('common.failed'), 'error');
    else {
      toast(t('toast.loggedShares', { shares, captured: '—' }), 'info');
      setContribution('');
      setShares('');
      setPurNote('');
      await onChanged();
    }
  }

  async function deletePurchase(id: string) {
    const j = await api('DELETE', `/api/espp-plans/${p.id}/purchases/${id}`);
    if (j.ok === false) toast(j.error || t('common.failed'), 'error');
    else await onChanged();
  }

  async function addSale() {
    const j = await api('POST', `/api/espp-plans/${p.id}/sales`, {
      date: saleDate,
      shares_sold: Number(saleShares),
      sale_price_usd: Number(salePrice),
      note: saleNote,
    });
    if (j.ok === false) toast(j.error || t('common.failed'), 'error');
    else {
      toast(t('toast.saleRecorded'), 'info');
      setSaleShares('');
      setSaleNote('');
      await onChanged();
    }
  }

  async function deleteSale(id: string) {
    const j = await api('DELETE', `/api/espp-plans/${p.id}/sales/${id}`);
    if (j.ok === false) toast(j.error || t('common.failed'), 'error');
    else await onChanged();
  }

  async function rename() {
    const v = window.prompt(t('common.nickname'), p.nickname || '');
    if (v === null) return;
    const j = await api('PATCH', `/api/espp-plans/${p.id}`, { nickname: v });
    if (j.ok === false) toast(j.error || t('common.failed'), 'error');
    else await onChanged();
  }

  async function remove() {
    if (!window.confirm(t('common.confirm'))) return;
    const j = await api('DELETE', `/api/espp-plans/${p.id}`);
    if (j.ok === false) toast(j.error || t('common.failed'), 'error');
    else {
      toast(t('common.deleted'), 'info');
      await onChanged();
    }
  }

  return (
    <div className="holding-row__detail">
      <dl className="detail-grid">
        <div>
          <dt>{t('espp.currentPrice')}</dt>
          <dd>{c.current_price_usd ? fmtUsdPrec.format(c.current_price_usd) : '—'}</dd>
        </div>
        <div>
          <dt>USDILS</dt>
          <dd>{(c.current_usdils || 0).toFixed(4)}</dd>
        </div>
        <div>
          <dt>{t('espp.discountLabel')}</dt>
          <dd>
            {p.discount_pct}%{' '}
            <small>{p.has_lookback ? t('espp.plusLookback') : t('espp.noLookback')}</small>
          </dd>
        </div>
        <div>
          <dt>{t('espp.offeringLength')}</dt>
          <dd>
            {p.offering_months} {t('espp.months')}
          </dd>
        </div>
        <div>
          <dt>{t('espp.heldSold')}</dt>
          <dd>
            {c.shares_held_now ?? 0} / {c.shares_sold_total ?? 0}
          </dd>
        </div>
        <div>
          <dt>{t('detail.lastSync')}</dt>
          <dd>{timeAgo(p.last_synced)}</dd>
        </div>
      </dl>
      <p
        className="muted"
        dangerouslySetInnerHTML={{ __html: t('espp.detailCaption') }}
      />
      <DetailChart series={valueSeries} />
      <h3 className="detail-h3">{t('rsu.forecastHeading', { ticker: p.ticker })}</h3>
      <DetailChart series={stockSeries} />

      <h3 className="detail-h3">
        {t('espp.purchases')} <span className="h2-count">{purchases.length}</span>
      </h3>
      {purchases.length ? (
        <div className="table-wrap">
          <table className="event-table">
            <thead>
              <tr>
                <th>{t('table.date')}</th>
                <th>{t('table.contribution')}</th>
                <th>{t('table.shares')}</th>
                <th>{t('table.buyPrice')}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {purchases.map((row) => (
                <tr key={row.id}>
                  <td>{row.date}</td>
                  <td>{fmtUsd(row.contribution_usd)}</td>
                  <td>{row.shares}</td>
                  <td>{row.buy_price_usd != null ? fmtUsdPrec.format(row.buy_price_usd) : '—'}</td>
                  <td>
                    <button
                      type="button"
                      className="btn btn-danger"
                      onClick={() => void deletePurchase(row.id)}
                    >
                      ×
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="muted">{t('espp.noPurchases') || '—'}</p>
      )}
      <div className="add-panel">
        <label>
          {t('table.date')}
          <input type="date" value={purDate} onChange={(e) => setPurDate(e.target.value)} />
        </label>
        <label>
          {t('table.contribution')}
          <input value={contribution} onChange={(e) => setContribution(e.target.value)} />
        </label>
        <label>
          {t('table.shares')}
          <input value={shares} onChange={(e) => setShares(e.target.value)} />
        </label>
        <label>
          {t('table.periodStart')}
          <input type="date" value={periodStart} onChange={(e) => setPeriodStart(e.target.value)} />
        </label>
        <label>
          {t('table.periodEnd')}
          <input type="date" value={periodEnd} onChange={(e) => setPeriodEnd(e.target.value)} />
        </label>
        <label>
          {t('table.buyPrice')}
          <input value={buyPrice} onChange={(e) => setBuyPrice(e.target.value)} />
        </label>
        <label>
          {t('espp.periodEndPrice')}
          <input value={periodEndPrice} onChange={(e) => setPeriodEndPrice(e.target.value)} />
        </label>
        <label>
          {t('common.note')}
          <input value={purNote} onChange={(e) => setPurNote(e.target.value)} />
        </label>
        <button type="button" className="btn" onClick={() => void addPurchase()}>
          {t('espp.logPurchase')}
        </button>
      </div>

      <h3 className="detail-h3">
        {t('rsu.sales')} <span className="h2-count">{sales.length}</span>
      </h3>
      {sales.length ? (
        <div className="table-wrap">
          <table className="event-table">
            <thead>
              <tr>
                <th>{t('table.date')}</th>
                <th>{t('table.shares')}</th>
                <th>{t('table.salePrice')}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {sales.map((s) => (
                <tr key={s.id}>
                  <td>{s.date}</td>
                  <td>{s.shares_sold}</td>
                  <td>{fmtUsdPrec.format(s.sale_price_usd)}</td>
                  <td>
                    <button
                      type="button"
                      className="btn btn-danger"
                      onClick={() => void deleteSale(s.id)}
                    >
                      ×
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="muted">{t('rsu.noSales')}</p>
      )}
      <div className="add-panel">
        <label>
          {t('table.date')}
          <input type="date" value={saleDate} onChange={(e) => setSaleDate(e.target.value)} />
        </label>
        <label>
          {t('rsu.sharesToSell')}
          <input value={saleShares} onChange={(e) => setSaleShares(e.target.value)} />
        </label>
        <label>
          {t('rsu.salePriceUsd')}
          <input value={salePrice} onChange={(e) => setSalePrice(e.target.value)} />
        </label>
        <label>
          {t('common.note')}
          <input value={saleNote} onChange={(e) => setSaleNote(e.target.value)} />
        </label>
        <button type="button" className="btn" onClick={() => void addSale()}>
          {t('rsu.sell')}
        </button>
      </div>

      <div className="add-actions" style={{ marginTop: '1rem' }}>
        <button type="button" className="btn" onClick={() => void rename()}>
          {t('action.rename')}
        </button>
        <button type="button" className="btn btn-danger" onClick={() => void remove()}>
          {t('action.delete')}
        </button>
      </div>
    </div>
  );
}
