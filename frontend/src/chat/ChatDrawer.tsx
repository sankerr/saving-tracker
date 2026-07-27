import { useEffect, useState } from 'react';
import { api } from '../api/client';
import { t } from '../copy';
import { useToast } from '../shell/ToastProvider';
import './chat.css';

type Msg = { role: 'user' | 'assistant'; text: string };

export default function ChatDrawer({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const { toast } = useToast();
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [enabled, setEnabled] = useState(true);

  useEffect(() => {
    if (!open) return;
    void (async () => {
      const j = await api<{ enabled?: boolean }>('GET', '/api/chat/status', undefined, {
        silent: true,
        retries: 0,
      });
      if (j.ok === false) setEnabled(false);
      else setEnabled(j.enabled !== false);
    })();
  }, [open]);

  async function send() {
    const text = input.trim();
    if (!text || busy) return;
    setInput('');
    setMessages((m) => [...m, { role: 'user', text }]);
    setBusy(true);
    const j = await api<{ reply?: string; message?: string }>(
      'POST',
      '/api/chat',
      { message: text, lang: 'he' },
      { silent: true, retries: 0 },
    );
    setBusy(false);
    if (j.ok === false) {
      toast(j.error || t('toast.chatRequestFailed'), 'error');
      return;
    }
    setMessages((m) => [
      ...m,
      { role: 'assistant', text: j.reply || j.message || '—' },
    ]);
  }

  if (!open) return null;

  return (
    <>
      <div className="chat-backdrop" onClick={onClose} />
      <aside className="chat-panel" role="dialog" aria-label={t('chrome.aiChat')}>
        <div className="chat-panel__head">
          <strong>{t('chrome.aiChat')}</strong>
          <div className="add-actions">
            <button
              type="button"
              className="btn"
              onClick={() => setMessages([])}
              title={t('chat.clear') || t('common.clear')}
            >
              {t('common.clear')}
            </button>
            <button type="button" className="btn" onClick={onClose}>
              {t('common.close')}
            </button>
          </div>
        </div>
        <p className="chat-disclaimer" dangerouslySetInnerHTML={{ __html: t('chat.disclaimer') }} />
        <div className="chat-thread">
          {!messages.length ? (
            <p className="muted">{t('chat.empty')}</p>
          ) : (
            messages.map((m, i) => (
              <div key={i} className={`chat-msg chat-msg--${m.role}`}>
                {m.text}
              </div>
            ))
          )}
        </div>
        <div className="chat-composer">
          <textarea
            rows={2}
            value={input}
            disabled={!enabled || busy}
            placeholder={t('chat.placeholder')}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                void send();
              }
            }}
          />
          <button type="button" className="btn" disabled={!enabled || busy} onClick={() => void send()}>
            {t('chat.send')}
          </button>
        </div>
      </aside>
    </>
  );
}
