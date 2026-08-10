/**
 * ChartContainer — standard wrapper for every Plotly chart in Athena
 *
 * Provides:
 *   • Consistent dark frame + header (title, subtitle, badge)
 *   • Ask Athena button (opens AI panel with pre-filled context)
 *   • Fullscreen toggle (CSS-driven, no portal needed)
 *   • CSV / PNG export hooks
 *   • Loading skeleton (shimmer bars)
 *   • Empty state (icon + message)
 *   • Optional last-updated timestamp
 *
 * Usage:
 *   <ChartContainer
 *     title="Win Rate by EV Bucket"
 *     subtitle="Based on 60 resolved picks"
 *     athenaContext="Explain the win rate distribution across EV buckets"
 *     loading={isLoading}
 *     onExportCsv={handleExport}
 *   >
 *     <Plot data={...} layout={...} config={...} style={{ width:'100%', height:'100%' }} />
 *   </ChartContainer>
 */

import { useState, useRef, useCallback, type ReactNode } from 'react';
import { useUiStore }                                     from '@store/uiStore';
import styles                                             from './ChartContainer.module.css';

// ── Types ─────────────────────────────────────────────────────────────────────

export interface ChartContainerProps {
  /** Chart title shown in header */
  title: string;
  /** Optional secondary descriptor */
  subtitle?: string;
  /** Small badge text, e.g. "60 picks" or "Live" */
  badge?: string;
  /** Pre-filled prompt sent to Athena when "Ask Athena" is clicked */
  athenaContext?: string;
  /** Called when user clicks Export CSV */
  onExportCsv?: () => void;
  /** Called when user clicks Export PNG — typically plotly's downloadImage */
  onExportPng?: () => void;
  /** Show shimmer loading skeleton instead of children */
  loading?: boolean;
  /** Show empty state instead of children */
  empty?: boolean;
  /** Custom empty-state message */
  emptyMessage?: string;
  /** ISO date string for "Last updated" label */
  lastUpdated?: string;
  /** Minimum height of the chart area */
  minHeight?: number;
  /** Extra class on the outer wrapper */
  className?: string;
  children: ReactNode;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatUpdated(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  } catch {
    return iso;
  }
}

// ── Component ─────────────────────────────────────────────────────────────────

export function ChartContainer({
  title,
  subtitle,
  badge,
  athenaContext,
  onExportCsv,
  onExportPng,
  loading        = false,
  empty          = false,
  emptyMessage   = 'No data available for this chart.',
  lastUpdated,
  minHeight      = 320,
  className,
  children,
}: ChartContainerProps) {
  const [fullscreen, setFullscreen] = useState(false);
  const [menuOpen,   setMenuOpen]   = useState(false);
  const menuRef                     = useRef<HTMLDivElement>(null);
  const openAthena                  = useUiStore(s => s.openAthenaPanel);

  const toggleFullscreen = useCallback(() => setFullscreen(f => !f), []);

  const handleAthena = useCallback(() => {
    const prompt = athenaContext ?? `Explain the chart: ${title}`;
    openAthena(prompt);
  }, [athenaContext, title, openAthena]);

  const handleMenuToggle = useCallback(() => setMenuOpen(m => !m), []);

  const handleExportCsv = useCallback(() => {
    setMenuOpen(false);
    onExportCsv?.();
  }, [onExportCsv]);

  const handleExportPng = useCallback(() => {
    setMenuOpen(false);
    onExportPng?.();
  }, [onExportPng]);

  // Close menu on outside click
  const handleMenuBlur = useCallback((e: React.FocusEvent) => {
    if (!menuRef.current?.contains(e.relatedTarget as Node)) {
      setMenuOpen(false);
    }
  }, []);

  const hasExport = !!(onExportCsv || onExportPng);

  return (
    <div
      className={[
        styles.container,
        fullscreen ? styles.fullscreen : '',
        className ?? '',
      ].join(' ').trim()}
      data-loading={String(loading)}
    >
      {/* ── Header ── */}
      <div className={styles.header}>
        <div className={styles.titleGroup}>
          <div className={styles.titleRow}>
            <h3 className={styles.title}>{title}</h3>
            {badge && <span className={styles.badge}>{badge}</span>}
          </div>
          {subtitle && <p className={styles.subtitle}>{subtitle}</p>}
        </div>

        <div className={styles.actions}>
          {/* Ask Athena */}
          <button
            className={styles.actionBtn}
            onClick={handleAthena}
            title="Ask Athena about this chart"
            aria-label="Ask Athena"
          >
            <span className={styles.actionIcon}>⚡</span>
            <span className={styles.actionLabel}>Ask Athena</span>
          </button>

          {/* Export menu */}
          {hasExport && (
            <div
              className={styles.menuWrap}
              ref={menuRef}
              onBlur={handleMenuBlur}
            >
              <button
                className={styles.iconBtn}
                onClick={handleMenuToggle}
                aria-haspopup="true"
                aria-expanded={menuOpen}
                title="Export options"
              >
                ⤓
              </button>
              {menuOpen && (
                <div className={styles.menu} role="menu">
                  {onExportCsv && (
                    <button
                      className={styles.menuItem}
                      onClick={handleExportCsv}
                      role="menuitem"
                    >
                      Export CSV
                    </button>
                  )}
                  {onExportPng && (
                    <button
                      className={styles.menuItem}
                      onClick={handleExportPng}
                      role="menuitem"
                    >
                      Export PNG
                    </button>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Fullscreen toggle */}
          <button
            className={styles.iconBtn}
            onClick={toggleFullscreen}
            aria-label={fullscreen ? 'Exit fullscreen' : 'Enter fullscreen'}
            title={fullscreen ? 'Exit fullscreen' : 'Fullscreen'}
          >
            {fullscreen ? '⤡' : '⤢'}
          </button>
        </div>
      </div>

      {/* ── Body ── */}
      <div
        className={styles.body}
        style={{ minHeight }}
      >
        {loading ? (
          <LoadingSkeleton />
        ) : empty ? (
          <EmptyState message={emptyMessage} />
        ) : (
          children
        )}
      </div>

      {/* ── Footer ── */}
      {lastUpdated && !loading && (
        <div className={styles.footer}>
          <span className={styles.updated}>Updated {formatUpdated(lastUpdated)}</span>
        </div>
      )}

      {/* Fullscreen backdrop close */}
      {fullscreen && (
        <div
          className={styles.backdrop}
          onClick={toggleFullscreen}
          aria-hidden
        />
      )}
    </div>
  );
}

// ── Sub-components ────────────────────────────────────────────────────────────

function LoadingSkeleton() {
  return (
    <div className={styles.skeleton} aria-busy="true" aria-label="Loading chart">
      <div className={styles.skeletonBar} style={{ width: '100%',  height: '60%' }} />
      <div className={styles.skeletonRow}>
        <div className={styles.skeletonBar} style={{ width: '18%', height: 6 }} />
        <div className={styles.skeletonBar} style={{ width: '14%', height: 6 }} />
        <div className={styles.skeletonBar} style={{ width: '20%', height: 6 }} />
        <div className={styles.skeletonBar} style={{ width: '12%', height: 6 }} />
      </div>
    </div>
  );
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className={styles.empty} role="status">
      <div className={styles.emptyIcon} aria-hidden>📊</div>
      <p className={styles.emptyMessage}>{message}</p>
    </div>
  );
}
