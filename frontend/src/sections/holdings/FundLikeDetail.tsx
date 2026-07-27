import { useState } from 'react';
import { api } from '../../api/client';
import { t } from '../../copy';
import { fmtIls, fmtPctSigned } from '../../lib/format';
import { periodLabel, timeAgo } from '../../lib/time';
import type { FundHolding } from '../../portfolio/types';
import { useToast } from '../../shell/ToastProvider';
import DetailChart from './DetailChart';

type Kind = 'fund' | 'pension';

function baseUrl(kind: Kind) {
  return kind === 'fund' ? '/api/fund-holdings' : '/api/pension-holdings';
}

export default function FundLikeDetail({
  holding,
  kind,
  onChanged,
}: {
  holding: FundHolding;
  kind: Kind;
  onChanged: () => Promise<void>;
}) {
  const { toast } = useToast();
  const h = holding;
  const c = h.computed || {};
  const rules = [...(h.recurring_rules || [])].sort((a, b) =>
    a.start_date.localeCompare(b.start_date),
  );
  const events = [...(c.expanded_events || [])].sort((a, b) =>
    (a.date || '').localeCompare(b.date || ''),
  );
  const [showRuleForm, setShowRuleForm] = useState(false);
  const [ruleStart, setRuleStart] = useState(new Date().toISOString().slice(0, 10));
  const [ruleEnd, setRuleEnd] = useState('');
  const [ruleEmp, setRuleEmp] = useState('');
  const [ruleEmpr, setRuleEmpr] = useState('');
  const [ruleDom, setRuleDom] = useState('10');
  const [ruleNote, setRuleNote] = useState('');
  const [evDate, setEvDate] = useState(new Date().toISOString().slice(0, 10));
  const [evKind, setEvKind] = useState('deposit');
  const [evAmount, setEvAmount] = useState('');
  const [evNote, setEvNote] = useState('');

  const series = (c.time_series || []).map((p) => ({
    label: String(p.period ?? p.date ?? ''),
    value: p.value_ils ?? 0,
  }));

  async function saveRule() {
    const j = await api('POST', `${baseUrl(kind)}/${h.id}/rules`, {
      start_date: ruleStart,
      end_date: ruleEnd || null,
      employee: Number(ruleEmp) || 0,
      employer: Number(ruleEmpr) || 0,
      day_of_month: Number(ruleDom) || 10,
      note: ruleNote,
    });
    if (j.ok === false) toast(j.error || t('common.failed'), 'error');
    else {
      toast(t('toast.ruleSaved'), 'info');
      setShowRuleForm(false);
      await onChanged();
    }
  }

  async function deleteRule(rid: string) {
    if (!window.confirm(t('modal.deleteRule.desc'))) return;
    const j = await api('DELETE', `${baseUrl(kind)}/${h.id}/rules/${rid}`);
    if (j.ok === false) toast(j.error || t('common.failed'), 'error');
    else {
      toast(t('toast.ruleDeleted'), 'info');
      await onChanged();
    }
  }

  async function endRule(rid: string) {
    const v = window.prompt(t('modal.setRuleEnd.label'), '');
    if (v === null) return;
    const j = await api('PATCH', `${baseUrl(kind)}/${h.id}/rules/${rid}`, {
      end_date: v.trim() || null,
    });
    if (j.ok === false) toast(j.error || t('common.failed'), 'error');
    else await onChanged();
  }

  async function addEvent() {
    const j = await api('POST', `${baseUrl(kind)}/${h.id}/events`, {
      date: evDate,
      kind: evKind,
      amount_ils: Number(evAmount) || 0,
      note: evNote,
    });
    if (j.ok === false) toast(j.error || t('common.failed'), 'error');
    else {
      toast(t('toast.eventAdded') || t('common.updated'), 'info');
      setEvAmount('');
      setEvNote('');
      await onChanged();
    }
  }

  async function deleteEvent(eid: string) {
    const j = await api('DELETE', `${baseUrl(kind)}/${h.id}/events/${eid}`);
    if (j.ok === false) toast(j.error || t('common.failed'), 'error');
    else {
      toast(t('toast.eventDeleted'), 'info');
      await onChanged();
    }
  }

  async function rename() {
    const v = window.prompt(t('common.nickname'), h.nickname || '');
    if (v === null) return;
    const j = await api('PATCH', `${baseUrl(kind)}/${h.id}`, { nickname: v });
    if (j.ok === false) toast(j.error || t('common.failed'), 'error');
    else {
      toast(t('toast.renamed'), 'info');
      await onChanged();
    }
  }

  async function editBalance() {
    const v = window.prompt(t('common.balanceIls'), String(h.anchor_balance_ils ?? ''));
    if (v === null) return;
    const j = await api('PATCH', `${baseUrl(kind)}/${h.id}`, {
      anchor_balance_ils: Number(v),
    });
    if (j.ok === false) toast(j.error || t('common.failed'), 'error');
    else await onChanged();
  }

  async function toggleDashboard() {
    if (kind !== 'fund') return;
    const j = await api('PATCH', `${baseUrl(kind)}/${h.id}`, {
      included_in_dashboard: h.included_in_dashboard === false,
    });
    if (j.ok === false) toast(j.error || t('common.failed'), 'error');
    else await onChanged();
  }

  async function remove() {
    if (!window.confirm(t('common.confirm'))) return;
    const j = await api('DELETE', `${baseUrl(kind)}/${h.id}`);
    if (j.ok === false) toast(j.error || t('common.failed'), 'error');
    else {
      toast(t('common.deleted'), 'info');
      await onChanged();
    }
  }

  return (
    <div className="holding-row__detail">
      <details>
        <summary>{t('detail.moreDetails')}</summary>
        <dl className="detail-grid">
          <div>
            <dt>{t('detail.anchorPeriod')}</dt>
            <dd>{periodLabel(h.anchor_period)}</dd>
          </div>
          <div>
            <dt>{t('detail.anchorBalance')}</dt>
            <dd>{fmtIls(h.anchor_balance_ils || 0)}</dd>
          </div>
          <div>
            <dt>{t('detail.depositedTotal')}</dt>
            <dd>{fmtIls(c.total_deposited_ils || 0)}</dd>
          </div>
          <div>
            <dt>{t('detail.withdrawn')}</dt>
            <dd>{fmtIls(c.total_withdrawn_ils || 0)}</dd>
          </div>
          <div>
            <dt>{t('detail.mgmtFeesPaid')}</dt>
            <dd>{fmtIls(c.cumulative_mgmt_fee_ils || 0)}</dd>
          </div>
          <div>
            <dt>{t('detail.lastSync')}</dt>
            <dd>{timeAgo(h.last_synced)}</dd>
          </div>
        </dl>
        <dl className="detail-grid">
          <div>
            <dt>3m</dt>
            <dd>{fmtPctSigned(c.three_m_return_pct)}</dd>
          </div>
          <div>
            <dt>6m</dt>
            <dd>{fmtPctSigned(c.six_m_return_pct)}</dd>
          </div>
          <div>
            <dt>12m</dt>
            <dd>{fmtPctSigned(c.twelve_m_return_pct)}</dd>
          </div>
          <div>
            <dt>24m</dt>
            <dd>{fmtPctSigned(c.twentyfour_m_return_pct)}</dd>
          </div>
        </dl>
      </details>

      <DetailChart series={series} />

      <h3 className="detail-h3">{t('detail.recurringContributions')}</h3>
      {rules.length ? (
        <div className="rule-list">
          {rules.map((r) => (
            <div key={r.id} className="rule-row">
              <div>
                <div>
                  📅 {r.start_date} → {r.end_date || t('rule.ongoing')}
                </div>
                <div>
                  {t('rule.you')} <strong>{fmtIls(r.employee || 0)}</strong> · {t('rule.employer')}{' '}
                  <strong>{fmtIls(r.employer || 0)}</strong> · {t('rule.day')} {r.day_of_month}
                </div>
                {r.note ? <div className="muted" dir="auto">{r.note}</div> : null}
              </div>
              <div className="add-actions">
                <button type="button" className="btn" onClick={() => void endRule(r.id)}>
                  {t('rule.setEndDate')}
                </button>
                <button type="button" className="btn btn-danger" onClick={() => void deleteRule(r.id)}>
                  {t('action.delete')}
                </button>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <p className="muted">{t('detail.noRecurringRule')}</p>
      )}
      <button type="button" className="btn" onClick={() => setShowRuleForm((v) => !v)}>
        {t('detail.addChangePoint')}
      </button>
      {showRuleForm ? (
        <div className="add-panel">
          <label>
            {t('rule.effectiveFrom')}
            <input type="date" value={ruleStart} onChange={(e) => setRuleStart(e.target.value)} />
          </label>
          <label>
            {t('rule.effectiveUntil')}
            <input type="date" value={ruleEnd} onChange={(e) => setRuleEnd(e.target.value)} />
          </label>
          <label>
            {t('rule.youPerMo')}
            <input value={ruleEmp} onChange={(e) => setRuleEmp(e.target.value)} />
          </label>
          <label>
            {t('rule.employerPerMo')}
            <input value={ruleEmpr} onChange={(e) => setRuleEmpr(e.target.value)} />
          </label>
          <label>
            {t('rule.dayOfMonth')}
            <input value={ruleDom} onChange={(e) => setRuleDom(e.target.value)} />
          </label>
          <label>
            {t('common.note')}
            <input value={ruleNote} onChange={(e) => setRuleNote(e.target.value)} />
          </label>
          <div className="add-actions">
            <button type="button" className="btn" onClick={() => void saveRule()}>
              {t('rule.saveRule')}
            </button>
            <button type="button" className="btn" onClick={() => setShowRuleForm(false)}>
              {t('common.cancel')}
            </button>
          </div>
        </div>
      ) : null}

      <h3 className="detail-h3">
        {t('detail.events')} <span className="h2-count">{events.length}</span>
      </h3>
      {events.length ? (
        <div className="table-wrap">
          <table className="event-table">
            <thead>
              <tr>
                <th>{t('table.date')}</th>
                <th>{t('table.kind')}</th>
                <th>{t('table.amount')}</th>
                <th>{t('table.note')}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {events.map((e) => (
                <tr key={e.id || `${e.date}-${e.kind}-${e.amount_ils}`}>
                  <td>{e.date}</td>
                  <td>{e.kind}</td>
                  <td>{fmtIls(e.amount_ils || 0)}</td>
                  <td dir="auto">{e.note || ''}</td>
                  <td>
                    {!e.synthetic && e.id ? (
                      <button type="button" className="btn btn-danger" onClick={() => void deleteEvent(e.id!)}>
                        ×
                      </button>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="muted">{t('detail.noEvents')}</p>
      )}
      <div className="add-panel">
        <label>
          {t('table.date')}
          <input type="date" value={evDate} onChange={(e) => setEvDate(e.target.value)} />
        </label>
        <label>
          {t('common.kind')}
          <select value={evKind} onChange={(e) => setEvKind(e.target.value)}>
            <option value="deposit">{t('ev.kind.deposit')}</option>
            <option value="withdrawal">{t('ev.kind.withdrawal')}</option>
            <option value="correction">{t('ev.kind.correction')}</option>
          </select>
        </label>
        <label>
          {t('ev.amountIls')}
          <input value={evAmount} onChange={(e) => setEvAmount(e.target.value)} />
        </label>
        <label>
          {t('common.note')}
          <input value={evNote} onChange={(e) => setEvNote(e.target.value)} />
        </label>
        <button type="button" className="btn" onClick={() => void addEvent()}>
          {t('common.add')}
        </button>
      </div>

      <div className="add-actions" style={{ marginTop: '1rem' }}>
        <button type="button" className="btn" onClick={() => void rename()}>
          {t('action.rename')}
        </button>
        <button type="button" className="btn" onClick={() => void editBalance()}>
          {t('action.editAnchorBalance')}
        </button>
        {kind === 'fund' ? (
          <button type="button" className="btn" onClick={() => void toggleDashboard()}>
            {h.included_in_dashboard === false
              ? t('funds.includeInDashboard')
              : t('funds.excludeFromDashboard')}
          </button>
        ) : null}
        <button
          type="button"
          className="btn"
          onClick={async () => {
            const bal = window.prompt(t('spot.newBalance') || t('common.balanceIls'), '');
            if (bal === null) return;
            const period = window.prompt(t('common.asOfPeriod'), '');
            if (period === null) return;
            const j = await api('POST', `${baseUrl(kind)}/${h.id}/spot-check`, {
              new_balance_ils: Number(bal),
              new_period: Number(period),
            });
            if (j.ok === false) toast(j.error || t('common.failed'), 'error');
            else {
              const msg =
                typeof j === 'object' && j && 'summary' in j
                  ? String((j as { summary?: string }).summary)
                  : t('common.updated');
              toast(msg || t('common.updated'), 'info');
            }
          }}
        >
          {t('action.spotCheck')}
        </button>
        <button type="button" className="btn btn-danger" onClick={() => void remove()}>
          {t('action.delete')}
        </button>
      </div>
    </div>
  );
}
