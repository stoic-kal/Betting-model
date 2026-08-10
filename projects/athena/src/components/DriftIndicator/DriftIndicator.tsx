/**
 * DriftIndicator — Shows a metric delta with directional arrow
 *
 * Usage:
 *   <DriftIndicator value={+2.3} unit="pp" label="vs last week" />
 *   <DriftIndicator value={-0.4} unit="%" positive={false} />
 */

import styles from './DriftIndicator.module.css';

export interface DriftIndicatorProps {
  /** Numeric change (positive or negative) */
  value:     number;
  unit?:     string;
  label?:    string;
  decimals?: number;
  /** When true, positive drift is good (green). Default true. */
  positiveIsGood?: boolean;
  size?: 'sm' | 'md' | 'lg';
}

export function DriftIndicator({
  value,
  unit            = '',
  label,
  decimals        = 1,
  positiveIsGood  = true,
  size            = 'md',
}: DriftIndicatorProps) {
  const isPositive = value > 0;
  const isNeutral  = value === 0;
  const isGood     = isNeutral ? null : (positiveIsGood ? isPositive : !isPositive);

  const arrow = isNeutral ? '→' : isPositive ? '↑' : '↓';
  const colorClass = isNeutral
    ? styles.neutral
    : isGood
      ? styles.good
      : styles.bad;

  return (
    <span className={[styles.root, styles[size], colorClass].join(' ')}>
      <span className={styles.arrow} aria-hidden>{arrow}</span>
      <span className={styles.value}>
        {!isNeutral && (isPositive ? '+' : '')}
        {Math.abs(value).toFixed(decimals)}{unit}
      </span>
      {label && <span className={styles.label}>{label}</span>}
    </span>
  );
}
