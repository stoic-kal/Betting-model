/**
 * MetricCard — Core KPI display component
 *
 * Props:
 *   label      — Metric name (displayed uppercase)
 *   value      — Numeric value to display (animated on mount/change)
 *   suffix     — Unit appended after value: "%", "pp", "u", etc.
 *   decimals   — Decimal places for the counter (default: 1)
 *   color      — Value color: "green" | "red" | "amber" | "purple" | "blue" | "muted" | "default"
 *   colorFn    — Optional function(value) → color — overrides color prop
 *   trend      — Optional trend vs. previous: { value: number; suffix?: string }
 *   trendDir   — "up" | "down" | "neutral" — defaults inferred from trend.value sign
 *   icon       — Optional emoji or character shown top-right
 *   sublabel   — Secondary label below main label
 *   context    — Footer note (e.g. "based on 38 resolved picks")
 *   variant    — Card accent strip color
 *   skeleton   — Show loading skeleton instead of content
 *   onClick    — Makes card clickable
 */

import { useCounter } from '@hooks/useCounter';
import styles from './MetricCard.module.css';

// ── Types ─────────────────────────────────────────────────────────────────────

export type MetricColor =
  | 'green' | 'red' | 'amber' | 'purple' | 'blue' | 'muted' | 'default';

export type MetricVariant =
  | 'purple' | 'blue' | 'green' | 'red' | 'amber' | 'none';

export type TrendDir = 'up' | 'down' | 'neutral';

export interface MetricCardProps {
  label:      string;
  value:      number;
  suffix?:    string;
  decimals?:  number;
  color?:     MetricColor;
  colorFn?:   (v: number) => MetricColor;
  trend?:     { value: number; suffix?: string };
  trendDir?:  TrendDir;
  icon?:      string;
  sublabel?:  string;
  context?:   string;
  variant?:   MetricVariant;
  skeleton?:  boolean;
  onClick?:   () => void;
  className?: string;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const TREND_ARROW: Record<TrendDir, string> = {
  up:      '↑',
  down:    '↓',
  neutral: '→',
};

function inferTrendDir(v: number): TrendDir {
  if (v > 0)  return 'up';
  if (v < 0)  return 'down';
  return 'neutral';
}

function formatTrend(trend: { value: number; suffix?: string }): string {
  const sign = trend.value > 0 ? '+' : '';
  const suf  = trend.suffix ?? '';
  return `${sign}${trend.value.toFixed(1)}${suf}`;
}

// ── Skeleton ──────────────────────────────────────────────────────────────────

function MetricCardSkeleton() {
  return (
    <div className={styles.skeleton} aria-busy="true" aria-label="Loading metric">
      <div className={styles.skeletonLine} style={{ width: '55%', height: 10 }} />
      <div className={styles.skeletonLine} style={{ width: '70%', height: 28 }} />
      <div className={styles.skeletonLine} style={{ width: '40%', height: 10 }} />
    </div>
  );
}

// ── Component ─────────────────────────────────────────────────────────────────

export function MetricCard({
  label,
  value,
  suffix    = '',
  decimals  = 1,
  color     = 'default',
  colorFn,
  trend,
  trendDir,
  icon,
  sublabel,
  context,
  variant   = 'none',
  skeleton  = false,
  onClick,
  className = '',
}: MetricCardProps) {
  // Animated counter — counts up from 0 to `value` on mount/change
  const displayed = useCounter(value, { decimals, duration: 850 });

  if (skeleton) return <MetricCardSkeleton />;

  const resolvedColor = colorFn ? colorFn(value) : color;

  const resolvedTrendDir: TrendDir =
    trendDir ?? (trend ? inferTrendDir(trend.value) : 'neutral');

  return (
    <div
      className={`${styles.card} ${className}`}
      data-variant={variant}
      data-clickable={String(!!onClick)}
      onClick={onClick}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={onClick ? (e) => { if (e.key === 'Enter') onClick(); } : undefined}
      aria-label={`${label}: ${displayed}${suffix}`}
    >
      {/* Header */}
      <div className={styles.header}>
        <div className={styles.labelGroup}>
          <span className={styles.label}>{label}</span>
          {sublabel && <span className={styles.sublabel}>{sublabel}</span>}
        </div>
        {icon && <span className={styles.icon} aria-hidden>{icon}</span>}
      </div>

      {/* Value row */}
      <div className={styles.valueRow}>
        <span className={styles.value} data-color={resolvedColor}>
          {displayed}
        </span>
        {suffix && <span className={styles.suffix}>{suffix}</span>}

        {trend && (
          <span
            className={styles.trend}
            data-dir={resolvedTrendDir}
            aria-label={`Trend: ${formatTrend(trend)}`}
          >
            <span aria-hidden>{TREND_ARROW[resolvedTrendDir]}</span>
            {formatTrend(trend)}
          </span>
        )}
      </div>

      {/* Footer */}
      {context && <p className={styles.context}>{context}</p>}
    </div>
  );
}
