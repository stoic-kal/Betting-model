/**
 * SectionPage — Reusable feature page wrapper
 *
 * Every page in Athena renders inside this component.
 * Provides consistent: header, breadcrumb, subtitle, Ask Athena button,
 * optional metric card row, divider, and scrollable content area.
 *
 * Usage:
 *   <SectionPage
 *     icon="🎯"
 *     title="Calibration Lab"
 *     subtitle="Reliability of model probability estimates"
 *     athenaQuery="Why is the model miscalibrated?"
 *     metrics={<>…MetricCards…</>}
 *   >
 *     {children}
 *   </SectionPage>
 */

import { type ReactNode } from 'react';
import { useUiStore } from '@store/uiStore';
import styles from './SectionPage.module.css';

// ── Types ─────────────────────────────────────────────────────────────────────

interface ActionButton {
  label:   string;
  icon?:   string;
  onClick: () => void;
}

export interface SectionPageProps {
  /** Emoji or character displayed before the title */
  icon:         string;
  /** Page title */
  title:        string;
  /** One-line description of what this section shows */
  subtitle?:    string;
  /** Pre-filled question sent to Athena AI panel */
  athenaQuery?: string;
  /** Metric cards rendered in the auto-grid row below the header */
  metrics?:     ReactNode;
  /** Optional extra action buttons next to the Ask Athena button */
  actions?:     ActionButton[];
  /** Main page content */
  children:     ReactNode;
  /** Shows spinner + "Loading data…" instead of children */
  loading?:     boolean;
  /** Shows empty state instead of children */
  empty?:       boolean;
  /** Custom empty state config */
  emptyState?:  { icon?: string; title: string; description?: string };
}

// ── Subcomponents ─────────────────────────────────────────────────────────────

function LoadingState() {
  return (
    <div className={styles.loading} aria-live="polite" aria-busy="true">
      <div className={styles.loadingSpinner} aria-hidden />
      <span>Loading data…</span>
    </div>
  );
}

function EmptyState({
  icon = '📭',
  title,
  description,
}: {
  icon?: string;
  title: string;
  description?: string;
}) {
  return (
    <div className={styles.empty} role="status">
      <div className={styles.emptyIcon} aria-hidden>{icon}</div>
      <p className={styles.emptyTitle}>{title}</p>
      {description && <p className={styles.emptyDesc}>{description}</p>}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export function SectionPage({
  icon,
  title,
  subtitle,
  athenaQuery,
  metrics,
  actions = [],
  children,
  loading = false,
  empty   = false,
  emptyState,
}: SectionPageProps) {
  const openAthena = useUiStore(s => s.openAthenaPanel);

  function handleAskAthena() {
    openAthena(athenaQuery ?? `Explain the ${title} section and its key findings.`);
  }

  return (
    <article className={styles.page}>

      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <header className={styles.header}>
        <div className={styles.headerLeft}>

          {/* Breadcrumb */}
          <nav className={styles.breadcrumb} aria-label="Breadcrumb">
            <span>Athena</span>
            <span className={styles.breadcrumbSep} aria-hidden>/</span>
            <span className={styles.breadcrumbCurrent}>{title}</span>
          </nav>

          {/* Title */}
          <div className={styles.titleRow}>
            <span className={styles.icon} aria-hidden>{icon}</span>
            <h1 className={styles.title}>{title}</h1>
          </div>

          {subtitle && (
            <p className={styles.subtitle}>{subtitle}</p>
          )}
        </div>

        {/* Header actions */}
        <div className={styles.headerActions}>
          {actions.map(btn => (
            <button
              key={btn.label}
              className={styles.actionBtn}
              onClick={btn.onClick}
              aria-label={btn.label}
            >
              {btn.icon && <span aria-hidden>{btn.icon}</span>}
              {btn.label}
            </button>
          ))}

          <button
            className={styles.athenaBtn}
            onClick={handleAskAthena}
            aria-label="Ask Athena AI"
            title={athenaQuery ?? 'Ask Athena about this section'}
          >
            <span className={styles.athenaDot} aria-hidden />
            Ask Athena
          </button>
        </div>
      </header>

      {/* ── Metrics row ────────────────────────────────────────────────────── */}
      {metrics && (
        <div className={styles.metricsRow} role="region" aria-label="Key metrics">
          {metrics}
        </div>
      )}

      {/* ── Divider ────────────────────────────────────────────────────────── */}
      <div className={styles.divider} role="separator" aria-hidden />

      {/* ── Content ────────────────────────────────────────────────────────── */}
      <div className={styles.content} role="region" aria-label={`${title} content`}>
        {loading ? (
          <LoadingState />
        ) : empty ? (
          <EmptyState
            icon={emptyState?.icon}
            title={emptyState?.title ?? 'No data available'}
            description={emptyState?.description ?? 'Run the diagnostic suite to populate this section.'}
          />
        ) : (
          children
        )}
      </div>

    </article>
  );
}

// ── Layout helpers exported for use in feature pages ──────────────────────────

/** Two-column grid: charts side by side */
export function Cols2({ children }: { children: ReactNode }) {
  return <div className={styles.cols2}>{children}</div>;
}

/** Three-column grid */
export function Cols3({ children }: { children: ReactNode }) {
  return <div className={styles.cols3}>{children}</div>;
}
