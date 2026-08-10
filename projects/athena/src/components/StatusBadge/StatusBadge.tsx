/**
 * StatusBadge — Semantic status pill
 *
 * Usage:
 *   <StatusBadge status="ok" label="Live" />
 *   <StatusBadge status="warn" label="Drifting" dot />
 *   <StatusBadge status="error" label="Down" pulse />
 */

import styles from './StatusBadge.module.css';

export type BadgeStatus = 'ok' | 'warn' | 'error' | 'info' | 'muted' | 'purple' | 'pending';

export interface StatusBadgeProps {
  status:   BadgeStatus;
  label:    string;
  /** Show animated pulse ring (use for live/active states) */
  pulse?:   boolean;
  /** Show colored dot prefix */
  dot?:     boolean;
  size?:    'sm' | 'md' | 'lg';
  onClick?: () => void;
}

const STATUS_ICONS: Record<BadgeStatus, string> = {
  ok:      '●',
  warn:    '●',
  error:   '●',
  info:    '●',
  muted:   '●',
  purple:  '●',
  pending: '○',
};

export function StatusBadge({
  status,
  label,
  pulse  = false,
  dot    = false,
  size   = 'md',
  onClick,
}: StatusBadgeProps) {
  return (
    <span
      className={[
        styles.badge,
        styles[status],
        styles[size],
        pulse   ? styles.pulse   : '',
        onClick ? styles.clickable : '',
      ].join(' ').trim()}
      onClick={onClick}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      aria-label={`Status: ${status} — ${label}`}
    >
      {dot && (
        <span className={styles.dot} aria-hidden>
          {STATUS_ICONS[status]}
        </span>
      )}
      {label}
    </span>
  );
}
