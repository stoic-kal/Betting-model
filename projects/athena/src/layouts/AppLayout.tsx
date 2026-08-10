/**
 * AppLayout — Root visual shell
 *
 * CSS Grid: TopBar (full width) + Sidebar + Main content.
 * Sidebar collapse state is read from uiStore (persisted to localStorage).
 * Renders <Outlet /> for all child routes inside the main scrollable area.
 */

import { Outlet }              from 'react-router-dom';
import { useUiStore, selectSidebarCollapsed } from '@store/uiStore';
import { Sidebar }            from './Sidebar';
import { TopBar }             from './TopBar';
import { CommandPalette }     from '@components/CommandPalette';
import { AthenaPanel }        from '@components/AthenaPanel';
import { NotificationCenter } from './NotificationCenter';
import styles from './AppLayout.module.css';

export function AppLayout() {
  const collapsed = useUiStore(selectSidebarCollapsed);

  return (
    <div
      className={styles.root}
      data-collapsed={String(collapsed)}
    >
      <div className={styles.topbar}>
        <TopBar />
      </div>

      <div className={styles.sidebar}>
        <Sidebar />
      </div>

      <main
        className={styles.main}
        id="athena-main"
        role="main"
        aria-label="Research content"
      >
        <Outlet />
      </main>

      {/* Global overlays — mounted once, driven by uiStore */}
      <CommandPalette />
      <AthenaPanel />
      <NotificationCenter />
    </div>
  );
}
