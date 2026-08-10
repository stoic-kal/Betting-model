/**
 * Modal — Accessible overlay dialog
 *
 * Usage:
 *   <Modal open={open} onClose={() => setOpen(false)} title="Confirm">
 *     <p>Are you sure?</p>
 *   </Modal>
 */

import { useEffect, useRef, type ReactNode } from 'react';
import styles from './Modal.module.css';

export interface ModalProps {
  open:       boolean;
  onClose:    () => void;
  title?:     string;
  children:   ReactNode;
  width?:     'sm' | 'md' | 'lg' | 'xl';
  hideClose?: boolean;
  footer?:    ReactNode;
}

export function Modal({ open, onClose, title, children, width = 'md', hideClose, footer }: ModalProps) {
  const dialogRef = useRef<HTMLDivElement>(null);

  // Keyboard: Escape closes
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [open, onClose]);

  // Focus trap on open
  useEffect(() => {
    if (open) dialogRef.current?.focus();
  }, [open]);

  if (!open) return null;

  return (
    <div className={styles.overlay} onClick={onClose} role="presentation">
      <div
        className={[styles.modal, styles[width]].join(' ')}
        onClick={e => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        ref={dialogRef}
        tabIndex={-1}
      >
        {(title || !hideClose) && (
          <div className={styles.header}>
            {title && <h2 className={styles.title}>{title}</h2>}
            {!hideClose && (
              <button className={styles.closeBtn} onClick={onClose} aria-label="Close">✕</button>
            )}
          </div>
        )}
        <div className={styles.body}>{children}</div>
        {footer && <div className={styles.footer}>{footer}</div>}
      </div>
    </div>
  );
}
