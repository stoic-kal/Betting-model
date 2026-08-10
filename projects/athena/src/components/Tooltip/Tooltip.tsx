/**
 * Tooltip — Hover info popover
 *
 * Pure CSS tooltip using data-attr — no JS positioning needed.
 *
 * Usage:
 *   <Tooltip content="Brier score measures calibration quality">
 *     <span>ℹ️</span>
 *   </Tooltip>
 */

import { type ReactNode } from 'react';
import styles from './Tooltip.module.css';

export interface TooltipProps {
  content:    string | ReactNode;
  children:   ReactNode;
  placement?: 'top' | 'bottom' | 'left' | 'right';
  delay?:     number;
}

export function Tooltip({ content, children, placement = 'top' }: TooltipProps) {
  return (
    <span className={[styles.wrap, styles[placement]].join(' ')}>
      {children}
      <span className={styles.tip} role="tooltip">
        {content}
      </span>
    </span>
  );
}
