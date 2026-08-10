/**
 * TopBar — Persistent model health status bar
 *
 * Shows live-computed health signals from athenaStore.
 * Never refreshes independently — reads from the store that
 * useAthenaData already populated.
 */

import { useNavigate } from 'react-router-dom';
import { useAthenaStore, selectSummary, selectIsLoading } from '@store/athenaStore';
import { useUiStore, selectStreamRunning } from '@store/uiStore';
import { openDiagStream } from '@services/stream';
import styles from './TopBar.module.css';

// ── Helpers ───────────────────────────────────────────────────────────────────

function calibrationGrade(ece: number | null): { grade: string; ok: boolean; warn: boolean } {
  if (ece === null) return { grade: '—',  ok: false, warn: false };
  if (ece < 0.05)   return { grade: 'A+', ok: true,  warn: false };
  if (ece < 0.08)   return { grade: 'A',  ok: true,  warn: false };
  if (ece < 0.12)   return { grade: 'B',  ok: false, warn: true  };
  if (ece < 0.18)   return { grade: 'C',  ok: false, warn: true  };
  return              { grade: 'F',  ok: false, warn: false };
}

function fmt(n: number | null | undefined, suffix = '%'): string {
  if (n == null) return '—';
  const sign = n > 0 ? '+' : '';
  return `${sign}${n.toFixed(1)}${suffix}`;
}

// ── Component ─────────────────────────────────────────────────────────────────

export function TopBar() {
  const summary      = useAthenaStore(selectSummary);
  const isLoading    = useAthenaStore(selectIsLoading);
  const streamRunning = useUiStore(selectStreamRunning);
  const startStream  = useUiStore(s => s.startStream);
  const appendLine   = useUiStore(s => s.appendStreamLine);
  const endStream    = useUiStore(s => s.endStream);
  const notify       = useUiStore(s => s.notify);
  const navigate     = useNavigate();

  const ece    = summary ? null : null;  // ECE not in summary; shown as N/A until Phase 4 page computes it
  const grade  = calibrationGrade(ece);
  const overWr  = summary?.over_wr  ?? null;
  const underWr = summary?.under_wr ?? null;
  const roi     = summary?.overall_roi ?? null;

  function handleRunDiagnostics() {
    if (streamRunning) return;
    startStream();
    navigate('/overview');

    const ctrl = openDiagStream({
      onLine:  (line) => appendLine(line),
      onDone:  (code) => {
        endStream();
        notify({
          level:   code === 0 ? 'success' : 'error',
          title:   code === 0 ? 'Diagnostics complete' : 'Diagnostics failed',
          message: code === 0 ? 'All figures saved. Data refreshed.' : `Exit code ${code}`,
          ttl:     5000,
        });
      },
      onError: () => {
        endStream();
        notify({ level: 'error', title: 'Stream error', message: 'Lost connection to Flask.', ttl: 6000 });
      },
    });

    // Safety: close stream if component unmounts (shouldn't happen for TopBar)
    return () => ctrl.close();
  }

  return (
    <header className={styles.bar} role="banner">
      <div className={styles.pills}>

        {/* System status */}
        <div className={styles.pill} title="Model system status">
          <span className={`${styles.dot} ${styles.dotPulse}`} data-ok="true" aria-hidden />
          <span className={styles.pillLabel}>Status</span>
          <span className={styles.pillValue} data-ok="true">
            {isLoading ? 'Loading…' : 'Operational'}
          </span>
        </div>

        {/* Overall WR */}
        <div className={styles.pill} title="Overall win rate">
          <span className={styles.pillLabel}>WR</span>
          <span
            className={styles.pillValue}
            data-ok={String((summary?.overall_wr ?? 0) >= 52.4)}
            data-warn={String((summary?.overall_wr ?? 0) >= 50 && (summary?.overall_wr ?? 0) < 52.4)}
          >
            {summary ? `${summary.overall_wr.toFixed(1)}%` : '—'}
          </span>
        </div>

        {/* OVER WR */}
        <div className={styles.pill} title="OVER win rate">
          <span className={styles.pillLabel}>OVER</span>
          <span className={styles.pillValue} data-ok={String((overWr ?? 0) >= 52.4)}>
            {overWr != null ? `${overWr.toFixed(1)}%` : '—'}
          </span>
        </div>

        {/* UNDER WR */}
        <div className={styles.pill} title="UNDER win rate">
          <span className={styles.pillLabel}>UNDER</span>
          <span className={styles.pillValue} data-ok={String((underWr ?? 0) >= 52.4)}>
            {underWr != null ? `${underWr.toFixed(1)}%` : '—'}
          </span>
        </div>

        {/* ROI */}
        <div className={styles.pill} title="Overall ROI">
          <span className={styles.pillLabel}>ROI</span>
          <span
            className={styles.pillValue}
            data-ok={String((roi ?? 0) > 0)}
            data-warn={String((roi ?? 0) === 0)}
          >
            {roi != null ? fmt(roi) : '—'}
          </span>
        </div>

        {/* Calibration */}
        <div className={styles.pill} title="Calibration grade (ECE-based)">
          <span className={styles.pillLabel}>Calibration</span>
          <span
            className={styles.pillValue}
            data-ok={String(grade.ok)}
            data-warn={String(grade.warn)}
          >
            {grade.grade}
          </span>
        </div>

        {/* Resolved picks */}
        <div className={styles.pill} title="Total resolved picks">
          <span className={styles.pillLabel}>Resolved</span>
          <span className={styles.pillValue} data-neutral>
            {summary?.resolved ?? '—'}
          </span>
        </div>

      </div>

      {/* Actions */}
      <div className={styles.actions}>
        <button
          className={styles.runBtn}
          onClick={handleRunDiagnostics}
          disabled={streamRunning || isLoading}
          aria-label="Run diagnostic suite"
          title="Run full diagnostic suite"
        >
          {streamRunning ? '⏳ Running…' : '▶ Run Diagnostics'}
        </button>

        <span className={styles.timestamp}>
          {summary?.date_max ? `Last pick: ${summary.date_max}` : 'Athena v1.0'}
        </span>
      </div>
    </header>
  );
}
