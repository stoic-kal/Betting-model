/**
 * Accordion — Expandable/collapsible panel list
 *
 * Usage:
 *   <Accordion items={[
 *     { id: 'a', title: 'Section A', content: <p>...</p> },
 *     { id: 'b', title: 'Section B', badge: 'NEW', content: <p>...</p> },
 *   ]} />
 */

import { useState, type ReactNode } from 'react';
import styles from './Accordion.module.css';

export interface AccordionItem {
  id:       string;
  title:    string;
  icon?:    string;
  badge?:   string;
  content:  ReactNode;
  defaultOpen?: boolean;
}

export interface AccordionProps {
  items:    AccordionItem[];
  multiple?: boolean;  // allow multiple open at once
}

export function Accordion({ items, multiple = false }: AccordionProps) {
  const [open, setOpen] = useState<Set<string>>(
    () => new Set(items.filter(i => i.defaultOpen).map(i => i.id))
  );

  const toggle = (id: string) => {
    setOpen(prev => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        if (!multiple) next.clear();
        next.add(id);
      }
      return next;
    });
  };

  return (
    <div className={styles.accordion} role="list">
      {items.map(item => {
        const isOpen = open.has(item.id);
        return (
          <div key={item.id} className={[styles.item, isOpen ? styles.expanded : ''].join(' ')} role="listitem">
            <button
              className={styles.trigger}
              onClick={() => toggle(item.id)}
              aria-expanded={isOpen}
              aria-controls={`acc-${item.id}`}
            >
              <div className={styles.triggerLeft}>
                {item.icon && <span className={styles.icon} aria-hidden>{item.icon}</span>}
                <span className={styles.triggerTitle}>{item.title}</span>
                {item.badge && <span className={styles.triggerBadge}>{item.badge}</span>}
              </div>
              <span className={[styles.chevron, isOpen ? styles.chevronOpen : ''].join(' ')} aria-hidden>
                ›
              </span>
            </button>
            <div
              id={`acc-${item.id}`}
              className={[styles.panel, isOpen ? styles.panelOpen : ''].join(' ')}
              role="region"
            >
              <div className={styles.panelInner}>{item.content}</div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
