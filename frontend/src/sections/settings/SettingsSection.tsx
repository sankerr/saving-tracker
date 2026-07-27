import { useEffect, useState } from 'react';
import { api } from '../../api/client';
import { t } from '../../copy';
import { usePortfolio } from '../../portfolio/PortfolioProvider';
import { useToast } from '../../shell/ToastProvider';

export default function SettingsSection() {
  const { data, reload, sync } = usePortfolio();
  const { toast } = useToast();
  const [netOfFees, setNetOfFees] = useState(true);
  const [fxOverride, setFxOverride] = useState('');

  useEffect(() => {
    setNetOfFees(data?.settings?.yield_is_net_of_fees !== false);
    const o = data?.settings?.usdils_rate_override;
    setFxOverride(o == null ? '' : String(o));
  }, [data?.settings]);

  async function save() {
    const j = await api('PUT', '/api/settings', {
      yield_is_net_of_fees: netOfFees,
      usdils_rate_override: fxOverride.trim() === '' ? null : Number(fxOverride),
    });
    if (j.ok === false) toast(j.error || t('common.failed'), 'error');
    else {
      toast(t('common.updated'), 'info');
      await reload({ spinner: false });
    }
  }

  async function clearCache() {
    const j = await api('POST', '/api/cache/clear');
    if (j.ok === false) toast(j.error || t('common.failed'), 'error');
    else {
      toast(t('toast.cacheCleared'), 'info');
      await reload({ spinner: false });
    }
  }

  async function downloadExport() {
    const j = await api<Record<string, unknown>>('GET', '/api/export');
    if (j.ok === false) {
      toast(j.error || t('common.failed'), 'error');
      return;
    }
    const blob = new Blob([JSON.stringify(j, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'saving-tracker-export.json';
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <section className="card" id="settings-card">
      <h2>{t('section.settings')}</h2>
      <div className="add-panel">
        <label>
          <span>{t('settings.netOfFees')}</span>
          <input
            type="checkbox"
            checked={netOfFees}
            onChange={(e) => setNetOfFees(e.target.checked)}
          />
        </label>
        <label>
          {t('settings.usdilsOverride')}
          <input value={fxOverride} onChange={(e) => setFxOverride(e.target.value)} />
        </label>
        <div className="add-actions">
          <button type="button" className="btn" onClick={() => void save()}>
            {t('common.save')}
          </button>
          <button type="button" className="btn" onClick={() => void sync()}>
            {t('chrome.refresh')}
          </button>
          <button type="button" className="btn" onClick={() => void downloadExport()}>
            {t('settings.exportJson')}
          </button>
          <button type="button" className="btn" onClick={() => void clearCache()}>
            {t('settings.clearCache')}
          </button>
        </div>
      </div>
    </section>
  );
}
