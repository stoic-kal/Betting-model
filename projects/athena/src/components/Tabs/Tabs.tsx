/**
 * Tabs — Segmented tab switcher
 *
 * Usage:
 *   const [tab, setTab] = useState('overview');
 *   <Tabs value={tab} onChange={setTab} tabs={[
 *     { id: 'overview', label: 'Overview' },
 *     { id: 'detail',   label: 'Detail', badge: '3' },
 *   ]} />
 */

import { type ReactNode } from 'react';
import styles from './Tabs.module.css';

export interface Tab {
  id:       string;
  label:    string;
  icon?:    string;
  badge?:   string;
  disabled?: boolean;
}

export interface TabsProps {
  tabs:      Tab[];
  value:     string;
  onChange:  (id: string) => void;
  children?: ReactNode;
  variant?:  'line' | 'pill' | 'card';
  size?:     'sm' | 'md' | 'lg';
}

export function Tabs({ tabs, value, onChange, variant = 'line', size = 'md' }: TabsProps) {
  return (
    <div
      className={[styles.tabs, styles[variant], styles[size]].join(' ')}
      role="tablist"
    >
      {tabs.map(tab => (
        <button
          key={tab.id}
          role="tab"
          aria-selected={tab.id === value}
          aria-disabled={tab.disabled}
          className={[
            styles.tab,
            tab.id === value ? styles.active : '',
            tab.disabled    ? styles.disabled : '',
          ].join(' ').trim()}
          onClick={() => !tab.disabled && onChange(tab.id)}
          tabIndex={tab.disabled ? -1 : 0}
        >
          {tab.icon && <span className={styles.tabIcon} aria-hidden>{tab.icon}</span>}
          <span className={styles.tabLabel}>{tab.label}</span>
          {tab.badge && <span className={styles.badge}>{tab.badge}</span>}
        </button>
      ))}
    </div>
  );
}
