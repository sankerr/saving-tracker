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

export default function CashSection() {
  const { data, reload } = usePortfolio();
  const { toast } = useToast();
  const holdings = useMemo(() => data?.cash_holdings || [], [data?.cash_holdings]);
  const [adding, setAdding] = useState(false);
  const [nickname, setNickname] = useState('');
  const [amount, setAmount] = useState('');
  const [currency, setCurrency] = useState('ILS');
  const [note, setNote] = useState('');

  async function save() {
    const j = await api('POST', '/api/cash', {
      nickname,
      amount: Number(amount),
      currency,
      note,
    });
    if (j.ok === false) toast(j.error || t('common.failed'), 'error');
    else {
      toast(t('toast.cashAdded'), 'info');
      setAdding(false);
      await reload({ spinner: false });
    }
  }

  async function remove(id: string) {
    if (!window.confirm(t('common.confirm'))) return;
    const j = await api('DELETE', `/api/cash/${id}`);
    if (j.ok === false) toast(j.error || t('common.failed'), 'error');
    else await reload({ spinner: false });
  }

  return (
    <HoldingsCard
      id="cash-card"
      titleKey="section.cash"
      count={holdings.length}
      onAdd={() => setAdding((v) => !v)}
      addLabel={t('cash.add')}
    >
      {adding ? (
        <div className="add-panel">
          <label>
            {t('common.nickname')}
            <input
              value={nickname}
              onChange={(e) => setNickname(e.target.value)}
              placeholder={t('cash.nicknamePlaceholder')}
            />
          </label>
          <label>
            {t('cash.amount')}
            <input value={amount} onChange={(e) => setAmount(e.target.value)} />
          </label>
          <label>
            {t('cash.currency')}
            <select value={currency} onChange={(e) => setCurrency(e.target.value)}>
              <option value="ILS">ILS</option>
              <option value="USD">USD</option>
            </select>
          </label>
          <label>
            {t('cash.note')}
            <input value={note} onChange={(e) => setNote(e.target.value)} />
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
      {!holdings.length ? (
        <EmptyHoldings />
      ) : (
        holdings.map((c) => (
          <HoldingRow
            key={c.id}
            title={c.nickname || t('label.cash')}
            subtitle={`${c.currency || 'ILS'} ${c.amount ?? ''}`}
            valueIls={c.computed?.value_ils}
            onDelete={() => void remove(c.id)}
          />
        ))
      )}
    </HoldingsCard>
  );
}
