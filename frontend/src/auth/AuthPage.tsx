import { type FormEvent, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import { setToken } from './token';
import { t } from '../copy';
import './auth.css';

export default function AuthPage() {
  const navigate = useNavigate();
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');

  const isLogin = mode === 'login';

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError('');
    setNotice('');
    setBusy(true);
    try {
      if (isLogin) {
        const j = await api<{ token?: string }>(
          'POST',
          '/api/login',
          { username, password },
          { retries: 2 },
        );
        if (j.ok && j.token) {
          setToken(j.token);
          navigate('/', { replace: true });
          return;
        }
        setError(j.error || t('auth.error.signInFailed'));
      } else {
        const j = await api(
          'POST',
          '/api/register',
          { username, password },
          { retries: 2 },
        );
        if (j.ok) {
          setNotice(j.message || t('auth.toast.accountCreated'));
          setMode('login');
          setPassword('');
          return;
        }
        setError(j.error || t('auth.error.registerFailed'));
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-overlay">
      <form className="auth-card" onSubmit={onSubmit}>
        <p className="auth-badge">{t('auth.betaBadge')}</p>
        <h1>{isLogin ? t('auth.title.login') : t('auth.title.register')}</h1>
        <p className="auth-subtitle">
          {isLogin ? t('auth.subtitle.login') : t('auth.subtitle.register')}
        </p>
        <label>
          {t('auth.email')}
          <input
            type="email"
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder={t('auth.emailPlaceholder')}
            required
          />
        </label>
        <label>
          {t('auth.password')}
          <input
            type="password"
            autoComplete={isLogin ? 'current-password' : 'new-password'}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>
        {error ? <p className="auth-error">{error}</p> : null}
        {notice ? <p className="auth-notice">{notice}</p> : null}
        <button className="btn btn-primary" type="submit" disabled={busy}>
          {isLogin ? t('auth.submit.login') : t('auth.submit.register')}
        </button>
        <button
          className="btn btn-link"
          type="button"
          onClick={() => {
            setMode(isLogin ? 'register' : 'login');
            setError('');
            setNotice('');
          }}
        >
          {isLogin ? t('auth.toggle.toRegister') : t('auth.toggle.toLogin')}
        </button>
      </form>
    </div>
  );
}
