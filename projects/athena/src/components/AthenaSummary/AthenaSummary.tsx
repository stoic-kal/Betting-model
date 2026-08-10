/**
 * AthenaSummary — AI research summary panel
 *
 * Appears at the bottom of every feature page.
 * Displays Athena's analysis: key finding, confidence,
 * expected ROI improvement, suggested experiment, and action buttons.
 *
 * Wrap bold phrases in **double asterisks** inside `finding` — they
 * render as purple-colored emphasis (not markdown bold).
 *
 * Usage:
 *   <AthenaSummary
 *     finding="The model is **overestimating run environments**.
 *              park_factor is hardcoded at 0.990 for every park."
 *     confidence={91}
 *     roiImpact="+8.4pp WR"
 *     experiment="Replace constant park_factor with venue lookup table"
 *     onRunExperiment={() => navigate('/roadmap')}
 *   />
 */

import { useUiStore } from '@store/uiStore';
import styles from './AthenaSummary.module.css';

// ── Types ─────────────────────────────────────────────────────────────────────

export interface AthenaSummaryProps {
  /** Key finding — wrap **text** for purple emphasis */
  finding:         string;
  /** Confidence score 0–100 */
  confidence:      number;
  /** Expected improvement string, e.g. "+8.4pp WR" or "+1.4% ROI" */
  roiImpact:       string;
  /** One-line description of the suggested experiment */
  experiment:      string;
  /** Whether roiImpact is a positive outcome (colors value green) */
  positiveImpact?: boolean;
  /** Called when "Run Experiment" is clicked */
  onRunExperiment?: () => void;
  /** Label override for the primary CTA */
  experimentLabel?: string;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

/** Converts **text** → <em>text</em> for purple styling */
function renderFinding(text: string): string {
  return text.replace(/\*\*(.+?)\*\*/g, '<em>$1</em>');
}

function confidenceColor(c: number): string {
  if (c >= 85) return '#10B981';
  if (c >= 70) return '#F59E0B';
  return '#EF4444';
}

// ── Component ─────────────────────────────────────────────────────────────────

export function AthenaSummary({
  finding,
  confidence,
  roiImpact,
  experiment,
  positiveImpact  = true,
  onRunExperiment,
  experimentLabel = 'Run Experiment',
}: AthenaSummaryProps) {
  const openAthena = useUiStore(s => s.openAthenaPanel);

  return (
    <aside
      className={styles.panel}
      role="complementary"
      aria-label="Athena AI Analysis"
    >
      {/* Header */}
      <div className={styles.header}>
        <div className={styles.identity}>
          <div className={styles.avatar} aria-hidden>⚡</div>
          <div className={styles.nameGroup}>
            <span className={styles.name}>Athena</span>
            <span className={styles.nameTag}>AI Research Analysis</span>
          </div>
        </div>

        <div className={styles.confidence} aria-label={`Confidence: ${confidence}%`}>
          <span className={styles.confLabel}>Confidence</span>
          <span
            className={styles.confValue}
            style={{ color: confidenceColor(confidence) }}
          >
            {confidence}%
          </span>
        </div>
      </div>

      {/* Finding */}
      <p
        className={styles.finding}
        dangerouslySetInnerHTML={{ __html: renderFinding(finding) }}
      />

      {/* Stats row */}
      <div className={styles.stats} role="list">
        <div className={styles.stat} role="listitem">
          <span className={styles.statLabel}>Expected Impact</span>
          <span
            className={styles.statValue}
            data-positive={String(positiveImpact)}
          >
            {roiImpact}
          </span>
        </div>

        <div className={styles.stat} role="listitem">
          <span className={styles.statLabel}>Analysis Type</span>
          <span className={styles.statValue} data-neutral>
            Quantitative
          </span>
        </div>

        <div className={styles.stat} role="listitem">
          <span className={styles.statLabel}>Status</span>
          <span className={styles.statValue} data-neutral>
            Actionable
          </span>
        </div>
      </div>

      {/* Suggested experiment */}
      <p className={styles.experiment}>
        <strong>Suggested Experiment — </strong>
        {experiment}
      </p>

      {/* Actions */}
      <div className={styles.actions}>
        {onRunExperiment && (
          <button
            className={styles.runBtn}
            onClick={onRunExperiment}
            aria-label={experimentLabel}
          >
            ▶ {experimentLabel}
          </button>
        )}

        <button
          className={styles.ghostBtn}
          onClick={() => openAthena(`Explain the finding: ${finding.replace(/\*\*/g, '')}`)}
          aria-label="Ask Athena for more detail"
        >
          💬 Ask Athena
        </button>

        <button
          className={styles.ghostBtn}
          onClick={() => openAthena(`What experiments should I run to fix: ${experiment}`)}
          aria-label="Get experiment suggestions from Athena"
        >
          🔬 Suggest Experiments
        </button>
      </div>
    </aside>
  );
}
