import { useState } from 'react';
import { api } from '../../api/client';
import { t } from '../../copy';
import { fmtIls, fmtUsd } from '../../lib/format';
import { timeAgo } from '../../lib/time';
import type { RsuGrant } from '../../portfolio/types';
import { useToast } from '../../shell/ToastProvider';
import DetailChart from '../holdings/DetailChart';

const fmtUsdPrec = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  maximumFractionDigits: 2,
});

export default function RsuDetail({
  grant,
  onChanged,
}: {
  grant: RsuGrant;
  onChanged: () => Promise<void>;
}) {
  const { toast } = useToast();
  const g = grant;
  const c = g.computed || {};
  const sales = [...(g.sales || [])].sort((a, b) => a.date.localeCompare(b.date));
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [shares, setShares] = useState('');
  const [price, setPrice] = useState('');
  const [note, setNote] = useState('');

  const valueSeries = (c.time_series || []).map((p) => ({
    label: String(p.date ?? p.period ?? ''),
    value: p.value_ils ?? 0,
  }));
  const stockSeries = (g.stock_history || []).map((p) => ({
    label: p.date,
    value: p.close,
  }));

  async function addSale() {
    const j = await api('POST', `/api/rsu-grants/${g.id}/sales`, {
      date,
      shares_sold: Number(shares),
      sale_price_usd: Number(price),
      note,
    });
    if (j.ok === false) toast(j.error || t('common.failed'), 'error');
    else {
      toast(t('toast.saleRecorded'), 'info');
      setShares('');
      setNote('');
      await onChanged();
    }
  }

  async function deleteSale(sid: string) {
    const j = await api('DELETE', `/api/rsu-grants/${g.id}/sales/${sid}`);
    if (j.ok === false) toast(j.error || t('common.failed'), 'error');
    else await onChanged();
  }

  async function rename() {
    const v = window.prompt(t('common.nickname'), g.nickname || '');
    if (v === null) return;
    const j = await api('PATCH', `/api/rsu-grants/${g.id}`, { nickname: v });
    if (j.ok === false) toast(j.error || t('common.failed'), 'error');
    else await onChanged();
  }

  async function editShares() {
    const v = window.prompt(t('action.editShares'), String(g.total_shares ?? ''));
    if (v === null) return;
    const j = await api('PATCH', `/api/rsu-grants/${g.id}`, { total_shares: Number(v) });
    if (j.ok === false) toast(j.error || t('common.failed'), 'error');
    else await onChanged();
  }

  async function setGrantPrice() {
    const v = window.prompt(t('action.setGrantPrice'), '');
    if (v === null) return;
    const j = await api('PATCH', `/api/rsu-grants/${g.id}`, {
      grant_price_override_usd: v.trim() === '' ? null : Number(v),
    });
    if (j.ok === false) toast(j.error || t('common.failed'), 'error');
    else await onChanged();
  }

  async function remove() {
    if (!window.confirm(t('common.confirm'))) return;
    const j = await api('DELETE', `/api/rsu-grants/${g.id}`);
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
          <dt>{t('rsu.currentPrice')}</dt>
          <dd>{c.current_price_usd ? fmtUsdPrec.format(c.current_price_usd) : '—'}</dd>
        </div>
        <div>
          <dt>USDILS</dt>
          <dd>{(c.current_usdils || 0).toFixed(4)}</dd>
        </div>
        <div>
          <dt>{t('rsu.costBasisPerShare')}</dt>
          <dd>
            {c.cost_basis_per_share_usd
              ? fmtUsdPrec.format(c.cost_basis_per_share_usd)
              : '—'}
          </dd>
        </div>
        <div>
          <dt>{t('rsu.heldVestedSold')}</dt>
          <dd>
            {c.shares_held_now ?? 0} / {c.vested_shares_now ?? 0} / {c.shares_sold_total ?? 0}
          </dd>
        </div>
        <div>
          <dt>{t('rsu.realizedGain')}</dt>
          <dd>
            {fmtUsd(c.realized_gain_usd || 0)} / {fmtIls(c.realized_gain_ils || 0)}
          </dd>
        </div>
        <div>
          <dt>{t('detail.lastSync')}</dt>
          <dd>{timeAgo(g.last_synced)}</dd>
        </div>
      </dl>
      <p className="muted">{t('rsu.detailCaption')}</p>
      <DetailChart series={valueSeries} />
      <h3 className="detail-h3">{t('rsu.forecastHeading', { ticker: g.ticker })}</h3>
      <DetailChart series={stockSeries} />

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
                <th>{t('table.proceeds')}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {sales.map((s) => (
                <tr key={s.id}>
                  <td>{s.date}</td>
                  <td>{s.shares_sold}</td>
                  <td>{fmtUsdPrec.format(s.sale_price_usd)}</td>
                  <td>{fmtUsd(s.shares_sold * s.sale_price_usd)}</td>
                  <td>
                    <button type="button" className="btn btn-danger" onClick={() => void deleteSale(s.id)}>
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
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        </label>
        <label>
          {t('rsu.sharesToSell')}
          <input value={shares} onChange={(e) => setShares(e.target.value)} />
        </label>
        <label>
          {t('rsu.salePriceUsd')}
          <input value={price} onChange={(e) => setPrice(e.target.value)} />
        </label>
        <label>
          {t('common.note')}
          <input value={note} onChange={(e) => setNote(e.target.value)} />
        </label>
        <button type="button" className="btn" onClick={() => void addSale()}>
          {t('rsu.sell')}
        </button>
      </div>
      <div className="add-actions" style={{ marginTop: '1rem' }}>
        <button type="button" className="btn" onClick={() => void rename()}>
          {t('action.rename')}
        </button>
        <button type="button" className="btn" onClick={() => void editShares()}>
          {t('action.editShares')}
        </button>
        <button type="button" className="btn" onClick={() => void setGrantPrice()}>
          {t('action.setGrantPrice')}
        </button>
        <button type="button" className="btn btn-danger" onClick={() => void remove()}>
          {t('action.delete')}
        </button>
      </div>
    </div>
  );
}
