/**
 * Drawer — Sliding side panel
 *
 * Usage:
 *   <Drawer open={open} onClose={() => setOpen(false)} title="Details" side="right">
 *     <p>Content</p>
 *   </Drawer>
 */

import { useEffect, type ReactNode } from 'react';
import styles from './Drawer.module.css';

export interface DrawerProps {
  open:     boolean;
  onClose:  () => void;
  title?:   string;
  children: ReactNode;
  side?:    'left' | 'right';
  width?:   number | string;
  footer?:  ReactNode;
}

export function Drawer({
  open,
  onClose,
  title,
  children,
  side  = 'right',
  width = 480,
  footer,
}: DrawerProps) {
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [open, onClose]);

  return (
    <>
      {/* Backdrop */}
      <div
        className={[styles.backdrop, open ? styles.backdropVisible : ''].join(' ')}
        onClick={onClose}
        aria-hidden
      />
      {/* Panel */}
      <aside
        className={[styles.drawer, styles[side], open ? styles.open : ''].join(' ')}
        style={{ width }}
        role="complementary"
        aria-label={title}
        aria-hidden={!open}
      >
        <div className={styles.header}>
          {title && <h2 className={styles.title}>{title}</h2>}
          <button className={styles.closeBtn} onClick={onClose} aria-label="Close drawer">✕</button>
        </div>
        <div className={styles.body}>{children}</div>
        {footer && <div className={styles.footer}>{footer}</div>}
      </aside>
    </>
  );
}
