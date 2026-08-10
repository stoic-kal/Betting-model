/**
 * ConfidenceChip — Animated confidence score display
 *
 * Shows 0–100 confidence with color-coded arc and animated counter.
 *
 * Usage:
 *   <ConfidenceChip value={87} />
 *   <ConfidenceChip value={42} label="Model Confidence" size="lg" />
 */

import { useCounter } from '@hooks/useCounter';
import styles         from './ConfidenceChip.module.css';

export interface ConfidenceChipProps {
  value:   number;   // 0–100
  label?:  string;
  size?:   'sm' | 'md' | 'lg';
  showArc?: boolean;
}

function color(v: number) {
  if (v >= 80) return '#10B981';
  if (v >= 60) return '#F59E0B';
  return '#EF4444';
}

export function ConfidenceChip({ value, label, size = 'md', showArc = false }: ConfidenceChipProps) {
  const animated = useCounter(value, { decimals: 0, duration: 700 });
  const c        = color(value);

  // SVG arc params
  const r   = 14;
  const circ = 2 * Math.PI * r;
  const dash = (value / 100) * circ;

  return (
    <div className={[styles.chip, styles[size]].join(' ')}>
      {showArc && (
        <svg className={styles.arc} viewBox="0 0 36 36" aria-hidden>
          <circle cx="18" cy="18" r={r} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="2.5" />
          <circle
            cx="18" cy="18" r={r}
            fill="none"
            stroke={c}
            strokeWidth="2.5"
            strokeDasharray={`${dash} ${circ}`}
            strokeLinecap="round"
            transform="rotate(-90 18 18)"
            style={{ transition: 'stroke-dasharray 0.7s cubic-bezier(0.4,0,0.2,1)' }}
          />
        </svg>
      )}
      <div className={styles.content}>
        <span className={styles.value} style={{ color: c }}>{animated}%</span>
        {label && <span className={styles.label}>{label}</span>}
      </div>
    </div>
  );
}
