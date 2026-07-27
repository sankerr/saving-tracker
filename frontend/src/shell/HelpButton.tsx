import { useState } from 'react';
import { t } from '../copy';
import './help.css';

const HELP_KEYS = {
  dashboard: { title: 'help.dashboard.title', body: 'help.dashboard.body' },
  funds: { title: 'help.funds.title', body: 'help.funds.body' },
  pension: { title: 'help.pension.title', body: 'help.pension.body' },
  'retirement-sim': { title: 'help.retirementSim.title', body: 'help.retirementSim.body' },
  rsu: { title: 'help.rsu.title', body: 'help.rsu.body' },
  espp: { title: 'help.espp.title', body: 'help.espp.body' },
  cash: { title: 'help.cash.title', body: 'help.cash.body' },
  settings: { title: 'help.settings.title', body: 'help.settings.body' },
  chat: { title: 'help.chat.title', body: 'help.chat.body' },
} as const;

export default function HelpButton({ section }: { section: keyof typeof HELP_KEYS }) {
  const [open, setOpen] = useState(false);
  const keys = HELP_KEYS[section];
  return (
    <>
      <button
        type="button"
        className="help-btn"
        title={t('help.aboutSection') || t(keys.title)}
        aria-label={t(keys.title)}
        onClick={() => setOpen(true)}
      >
        ?
      </button>
      {open ? (
        <div className="help-modal" role="dialog">
          <div className="help-modal__card">
            <div className="help-modal__head">
              <h3>{t(keys.title)}</h3>
              <button type="button" className="btn" onClick={() => setOpen(false)}>
                {t('common.close')}
              </button>
            </div>
            <div
              className="help-modal__body"
              dangerouslySetInnerHTML={{ __html: t(keys.body) }}
            />
          </div>
          <button
            type="button"
            className="help-modal__backdrop"
            aria-label={t('common.close')}
            onClick={() => setOpen(false)}
          />
        </div>
      ) : null}
    </>
  );
}
