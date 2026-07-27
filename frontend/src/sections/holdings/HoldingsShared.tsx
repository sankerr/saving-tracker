import { useState, type ReactNode } from 'react';
import { t } from '../../copy';
import { fmtIls, fmtPctSigned, fmtUsd } from '../../lib/format';
import './holdings.css';

export function HoldingsCard({
  id,
  titleKey,
  count,
  children,
  onAdd,
  addLabel,
}: {
  id: string;
  titleKey: string;
  count: number;
  children: ReactNode;
  onAdd?: () => void;
  addLabel?: string;
}) {
  return (
    <section className="card" id={id}>
      <div className="holdings-head">
        <h2>
          {t(titleKey)}{' '}
          <span className="h2-count" data-testid={`${id}-count`}>
            {count}
          </span>
        </h2>
        {onAdd ? (
          <button type="button" className="btn" onClick={onAdd}>
            {addLabel || t('common.add') || '+'}
          </button>
        ) : null}
      </div>
      <div className="holdings-list">{children}</div>
    </section>
  );
}

export function HoldingRow({
  title,
  subtitle,
  valueIls,
  profitIls,
  profitPct,
  extraValue,
  onDelete,
  children,
}: {
  title: string;
  subtitle?: string;
  valueIls?: number;
  profitIls?: number;
  profitPct?: number;
  extraValue?: string;
  onDelete?: () => void;
  children?: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const profit = profitIls ?? 0;
  return (
    <div className="holding-row" data-expanded={open}>
      <button
        type="button"
        className="holding-row__head"
        onClick={() => setOpen((v) => !v)}
      >
        <div>
          <p className="holding-row__title" dir="auto">
            {title}
          </p>
          {subtitle ? (
            <p className="holding-row__sub" dir="auto">
              {subtitle}
            </p>
          ) : null}
        </div>
        <div className="holding-row__vals">
          <div className="holding-row__value">
            {extraValue || fmtIls(valueIls || 0)}
          </div>
          {profitIls != null ? (
            <div
              className="holding-row__value-sub"
              style={{
                color:
                  profit >= 0 ? 'var(--color-success)' : 'var(--color-danger)',
              }}
            >
              {profit >= 0 ? '+' : ''}
              {fmtIls(profit)} ({fmtPctSigned(profitPct || 0)})
            </div>
          ) : null}
        </div>
      </button>
      {open ? (
        <div className="holding-row__detail">
          {children}
          {onDelete ? (
            <button type="button" className="btn btn-danger" onClick={onDelete}>
              {t('common.delete') || t('common.remove') || 'מחק'}
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

export function EmptyHoldings() {
  return <p className="muted">{t('empty.none') || '—'}</p>;
}

export { fmtUsd };
