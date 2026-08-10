/**
 * NotificationCenter — Toast notification display
 * Reads from uiStore notification queue, auto-dismisses on TTL.
 */

import { useEffect }    from 'react';
import { useUiStore }   from '@store/uiStore';
import styles           from './NotificationCenter.module.css';

const LEVEL_ICONS: Record<string, string> = {
  info:    'ℹ',
  success: '✓',
  warning: '⚠',
  error:   '✕',
};

export function NotificationCenter() {
  const notifications = useUiStore(s => s.notifications);
  const dismiss       = useUiStore(s => s.dismissNotif);

  // Auto-dismiss on TTL
  useEffect(() => {
    if (!notifications.length) return;
    const timers = notifications.map(n =>
      setTimeout(() => dismiss(n.id), n.ttl ?? 4000)
    );
    return () => timers.forEach(clearTimeout);
  }, [notifications, dismiss]);

  if (!notifications.length) return null;

  return (
    <div className={styles.center} role="region" aria-label="Notifications" aria-live="polite">
      {notifications.map(n => (
        <div key={n.id} className={[styles.toast, styles[n.level]].join(' ')} role="alert">
          <span className={styles.icon} aria-hidden>{LEVEL_ICONS[n.level]}</span>
          <div className={styles.content}>
            {n.title && <strong className={styles.title}>{n.title}</strong>}
            {n.message && <p className={styles.message}>{n.message}</p>}
          </div>
          <button className={styles.close} onClick={() => dismiss(n.id)} aria-label="Dismiss">✕</button>
        </div>
      ))}
    </div>
  );
}
