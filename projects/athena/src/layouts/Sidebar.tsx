/**
 * Sidebar — Fixed left navigation
 *
 * Renders all NAV_SECTIONS. Active section highlighted via React Router.
 * Collapse state toggled via uiStore (persisted).
 * Coming-soon items are visually dimmed and non-interactive.
 */

import { useNavigate, useLocation } from 'react-router-dom';
import { useUiStore, selectSidebarCollapsed } from '@store/uiStore';
import { NAV_SECTIONS } from '@types-athena';
import styles from './Sidebar.module.css';

// Sections that appear under a "Coming Soon" divider
const COMING_SOON_IDS = new Set([
  'shap', 'umpires', 'weather', 'ballparks',
  'journal', 'experiments', 'registry',
]);

const CORE_SECTIONS  = NAV_SECTIONS.filter(s => !COMING_SOON_IDS.has(s.id));
const FUTURE_SECTIONS = NAV_SECTIONS.filter(s => COMING_SOON_IDS.has(s.id));

export function Sidebar() {
  const collapsed    = useUiStore(selectSidebarCollapsed);
  const toggleSidebar = useUiStore(s => s.toggleSidebar);
  const navigate     = useNavigate();
  const location     = useLocation();

  const activePath = location.pathname.replace('/', '') || 'overview';

  return (
    <nav
      className={styles.sidebar}
      data-collapsed={String(collapsed)}
      aria-label="Research navigation"
    >
      {/* Brand */}
      <div className={styles.brand}>
        <div className={styles.brandMark} aria-hidden>⚡</div>
        <span className={styles.brandName}>Athena</span>
      </div>

      {/* Nav list */}
      <div className={styles.nav} role="list">
        {/* Research sections */}
        {!collapsed && (
          <div className={styles.section}>
            <span className={styles.sectionLabel}>Research</span>
          </div>
        )}

        {CORE_SECTIONS.map(sec => (
          <div
            key={sec.id}
            role="listitem"
            className={styles.item}
            data-active={String(activePath === sec.id)}
            data-coming-soon="false"
            onClick={() => navigate(`/${sec.id}`)}
            title={collapsed ? sec.label : undefined}
            aria-label={sec.label}
            aria-current={activePath === sec.id ? 'page' : undefined}
          >
            <span className={styles.itemIcon} aria-hidden>{sec.icon}</span>
            <span className={styles.itemLabel}>{sec.label}</span>
          </div>
        ))}

        {/* Divider before coming soon */}
        <div className={styles.divider} aria-hidden />

        {!collapsed && (
          <div className={styles.section}>
            <span className={styles.sectionLabel}>Coming Soon</span>
          </div>
        )}

        {FUTURE_SECTIONS.map(sec => (
          <div
            key={sec.id}
            role="listitem"
            className={styles.item}
            data-active="false"
            data-coming-soon="true"
            title={collapsed ? `${sec.label} (coming soon)` : undefined}
            aria-label={`${sec.label} — coming soon`}
            aria-disabled="true"
          >
            <span className={styles.itemIcon} aria-hidden>{sec.icon}</span>
            <span className={styles.itemLabel}>{sec.label}</span>
            {!collapsed && (
              <span className={styles.comingSoonBadge} aria-hidden>SOON</span>
            )}
          </div>
        ))}
      </div>

      {/* Footer — collapse toggle */}
      <div className={styles.footer}>
        <button
          className={styles.collapseBtn}
          onClick={toggleSidebar}
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          title={collapsed ? 'Expand' : 'Collapse'}
        >
          <span className={styles.collapseArrow} aria-hidden>‹</span>
          {!collapsed && (
            <span style={{ marginLeft: 6, fontSize: 11, color: 'var(--text-disabled)' }}>
              Collapse
            </span>
          )}
        </button>
      </div>
    </nav>
  );
}
