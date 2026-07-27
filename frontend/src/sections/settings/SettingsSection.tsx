import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api, apiUrl } from '../../api/client';
import { getToken, setToken } from '../../auth/token';
import { t } from '../../copy';
import { usePortfolio } from '../../portfolio/PortfolioProvider';
import { useTheme } from '../../theme/ThemeProvider';
import HelpButton from '../../shell/HelpButton';
import { useToast } from '../../shell/ToastProvider';

export default function SettingsSection() {
  const navigate = useNavigate();
  const { data, reload, sync, logout } = usePortfolio();
  const { toast } = useToast();
  const { preference, setPreference } = useTheme();
  const [netOfFees, setNetOfFees] = useState(true);
  const [fxOverride, setFxOverride] = useState('');
  const importRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setNetOfFees(data?.settings?.yield_is_net_of_fees !== false);
    const o = data?.settings?.usdils_rate_override;
    setFxOverride(o == null ? '' : String(o));
  }, [data?.settings]);

  const cs = data?.cache_status;
  const cacheParts: string[] = [];
  if (cs?.current_usdils) {
    cacheParts.push(
      t('settings.usdilsInfo', {
        rate: cs.current_usdils.toFixed(4),
        override: cs.usdils_override ? t('settings.overrideSuffix') : '',
      }),
    );
  }
  if (cs?.package_show_age_seconds != null) {
    cacheParts.push(
      t('settings.gemelnetAge', { n: Math.floor(cs.package_show_age_seconds / 60) }),
    );
  }

  async function saveSettings(patch: Record<string, unknown>) {
    const j = await api('POST', '/api/settings', patch);
    if (j.ok === false) toast(j.error || t('common.failed'), 'error');
    else {
      toast(t('common.updated'), 'info');
      await reload({ spinner: false });
    }
  }

  async function downloadExport() {
    const token = getToken();
    const r = await fetch(apiUrl('/api/export'), {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!r.ok) {
      toast(t('toast.exportFailed'), 'error');
      return;
    }
    const blob = await r.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `saving-tracker-export-${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  async function onImportFile(file: File) {
    const text = await file.text();
    let payload: unknown;
    try {
      payload = JSON.parse(text);
    } catch {
      toast(t('toast.invalidJson'), 'error');
      return;
    }
    const j = await api('POST', '/api/import', payload);
    if (j.ok === false) toast(j.error || t('toast.importFailed'), 'error');
    else {
      toast(t('toast.imported'), 'info');
      await reload({ spinner: false });
    }
  }

  async function changePassword() {
    const current = window.prompt(t('modal.changePassword.current'), '');
    if (current === null) return;
    const next = window.prompt(t('modal.changePassword.new'), '');
    if (next === null) return;
    const confirm = window.prompt(t('modal.changePassword.confirm'), '');
    if (confirm === null) return;
    if (!next || next !== confirm) {
      toast(t('toast.passwordsMismatch'), 'error');
      return;
    }
    const j = await api('POST', '/api/account/password', {
      current_password: current,
      new_password: next,
    });
    if (j.ok === false) toast(j.error || t('toast.couldNotUpdatePassword'), 'error');
    else toast(j.message || t('toast.passwordUpdated'), 'info');
  }

  async function clearCache() {
    if (!window.confirm(t('modal.clearCache.desc'))) return;
    const j = await api('POST', '/api/cache/clear', {});
    if (j.ok === false) toast(j.error || t('common.failed'), 'error');
    else {
      toast(t('toast.cacheCleared'), 'info');
      await reload({ spinner: false });
    }
  }

  async function deleteAccount() {
    if (!window.confirm(t('modal.deleteAccount.desc'))) return;
    const password = window.prompt(t('modal.deleteAccount.confirmPw'), '');
    if (password === null) return;
    const j = await api('DELETE', '/api/account', { password });
    if (j.ok === false) toast(j.error || t('common.failed'), 'error');
    else {
      toast(t('toast.accountDeleted'), 'info');
      setToken('');
      logout();
      navigate('/login', { replace: true });
    }
  }

  return (
    <section className="card" id="settings-card">
      <h2>
        {t('section.settings')} <HelpButton section="settings" />
      </h2>
      <div className="add-panel">
        <label>
          {t('settings.appearance')}
          <select
            value={preference}
            onChange={(e) =>
              setPreference(e.target.value as 'system' | 'light' | 'dark')
            }
          >
            <option value="system">{t('settings.theme.system')}</option>
            <option value="light">{t('settings.theme.light')}</option>
            <option value="dark">{t('settings.theme.dark')}</option>
          </select>
        </label>
        <label>
          <span>{t('settings.netOfFees')}</span>
          <input
            type="checkbox"
            checked={netOfFees}
            onChange={(e) => {
              setNetOfFees(e.target.checked);
              void saveSettings({ yield_is_net_of_fees: e.target.checked });
            }}
          />
        </label>
        <label>
          {t('settings.usdilsOverride')}
          <input
            value={fxOverride}
            placeholder={t('settings.usdilsPlaceholder')}
            onChange={(e) => setFxOverride(e.target.value)}
            onBlur={() =>
              void saveSettings({
                usdils_rate_override: fxOverride.trim() === '' ? null : Number(fxOverride),
              })
            }
          />
        </label>
        <p className="muted" id="cache-info">
          {cacheParts.join(' · ')}
        </p>
        <div className="add-actions">
          <button type="button" className="btn" onClick={() => void sync()}>
            {t('chrome.refresh')}
          </button>
          <button type="button" className="btn" onClick={() => void downloadExport()}>
            {t('settings.exportJson')}
          </button>
          <button type="button" className="btn" onClick={() => importRef.current?.click()}>
            {t('settings.importJson')}
          </button>
          <input
            ref={importRef}
            type="file"
            accept="application/json,.json"
            hidden
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void onImportFile(f);
              e.target.value = '';
            }}
          />
          <button type="button" className="btn" onClick={() => void changePassword()}>
            {t('settings.changePassword')}
          </button>
          <button type="button" className="btn" onClick={() => void clearCache()}>
            {t('settings.clearCache')}
          </button>
        </div>
        <div className="add-actions">
          <button type="button" className="btn btn-danger" onClick={() => void deleteAccount()}>
            {t('settings.deleteAccount')}
          </button>
        </div>
        <p
          className="muted"
          dangerouslySetInnerHTML={{ __html: t('settings.deleteAccountBlurb') }}
        />
      </div>
    </section>
  );
}
