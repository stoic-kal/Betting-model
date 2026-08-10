/**
 * RootCausePage — Model Root Cause Analysis
 *
 * Synthesizes all diagnostic data into prioritized root causes.
 * Each issue includes: severity, metric evidence, proposed fix,
 * expected impact, engineering cost, and confidence.
 */

import { useMemo }                                                   from 'react';
import { useAthenaStore, selectSummary, selectCalibration,
         selectDataHealth, selectFeatures }                          from '@store/athenaStore';
import { useAthenaData }                                             from '@hooks/useAthenaData';
import { SectionPage, Cols2 }                                        from '@components/SectionPage';
import { MetricCard }                                                from '@components/MetricCard';
import { AthenaSummary }                                             from '@components/AthenaSummary';
import { StatusBadge }                                               from '@components/StatusBadge';
import type { RootCause, Severity }                                  from '@types-athena';
import styles                                                        from './RootCausePage.module.css';

// ── Severity config ───────────────────────────────────────────────────────────

const SEV_CONFIG: Record<Severity, { label: string; color: string; badgeStatus: 'error' | 'warn' | 'info' | 'ok' | 'purple' }> = {
  critical: { label: 'CRITICAL', color: '#EF4444', badgeStatus: 'error' },
  high:     { label: 'HIGH',     color: '#F97316', badgeStatus: 'warn' },
  medium:   { label: 'MEDIUM',   color: '#F59E0B', badgeStatus: 'warn' },
  low:      { label: 'LOW',      color: '#6B7280', badgeStatus: 'info' },
  positive: { label: 'POSITIVE', color: '#10B981', badgeStatus: 'ok' },
};

// ── Generate root causes from live data ───────────────────────────────────────

function useRootCauses(): RootCause[] {
  const summary    = useAthenaStore(selectSummary);
  const calibration = useAthenaStore(selectCalibration);
  const health     = useAthenaStore(selectDataHealth);
  const features   = useAthenaStore(selectFeatures);

  return useMemo(() => {
    const causes: RootCause[] = [];

    if (!summary) return causes;

    // 1. OVER/UNDER gap
    const wrGap = summary.under_wr - summary.over_wr;
    if (wrGap > 10) {
      causes.push({
        id:         'over-under-gap',
        severity:   'critical',
        title:      'OVER/UNDER Win Rate Divergence',
        metric:     `UNDER ${summary.under_wr.toFixed(1)}% vs OVER ${summary.over_wr.toFixed(1)}% (${wrGap.toFixed(1)}pp gap)`,
        evidence:   `${summary.under_record[0]}-${summary.under_record[1]} UNDER vs ${summary.over_record[0]}-${summary.over_record[1]} OVER. Gap of ${wrGap.toFixed(1)}pp is statistically large and directional.`,
        fix:        'Investigate what the model uses differently for OVER vs UNDER. Check if run-environment features (park factor, wind, temp) drive UNDER edge. Consider UNDER-only filter.',
        impact:     `+${(wrGap * 0.3).toFixed(1)}pp WR if UNDER-only filter applied`,
        confidence: 88,
        engCost:    'Low',
        roiGain:    `+${(wrGap * 0.05).toFixed(1)}%`,
      });
    }

    // 2. Snapshot coverage
    const snapPct = (summary.with_snapshot / summary.total_picks) * 100;
    if (snapPct < 80) {
      causes.push({
        id:         'snapshot-gap',
        severity:   snapPct < 50 ? 'critical' : 'high',
        title:      'Feature Snapshot Coverage Gap',
        metric:     `${snapPct.toFixed(0)}% of picks have feature snapshots`,
        evidence:   `Only ${summary.with_snapshot} of ${summary.total_picks} picks recorded feature values at bet time. Unsnapshotted picks cannot be diagnosed or learned from.`,
        fix:        'Add snapshot logging middleware to every pick insert path. Log all feature values + model probability at time of bet.',
        impact:     'Unlocks per-pick diagnosis and model improvement loop',
        confidence: 95,
        engCost:    'Low',
        roiGain:    '+1.5% (indirect via faster iteration)',
      });
    }

    // 3. Below break-even overall
    if (summary.overall_wr < 50) {
      causes.push({
        id:         'below-breakeven',
        severity:   'high',
        title:      'Overall WR Below Break-Even',
        metric:     `${summary.overall_wr.toFixed(1)}% WR vs 52.4% break-even`,
        evidence:   `With ${summary.resolved} resolved picks, the model is ${(52.4 - summary.overall_wr).toFixed(1)}pp below break-even. Sample size is small — may be variance, but needs monitoring.`,
        fix:        'Track rolling 20-pick WR. If still below 48% after 100 picks, investigate feature engineering and probability calibration.',
        impact:     'Core model health signal',
        confidence: 55,
        engCost:    'High',
        roiGain:    '+4.1%',
      });
    }

    // 4. Calibration
    if (calibration?.brier !== null && calibration?.brier !== undefined) {
      const brierImprovement = calibration.baseline_brier !== null
        ? ((calibration.baseline_brier - calibration.brier) / calibration.baseline_brier * 100)
        : 0;
      if (brierImprovement < 3) {
        causes.push({
          id:         'weak-calibration',
          severity:   'medium',
          title:      'Weak Probability Calibration',
          metric:     `Brier ${calibration.brier.toFixed(3)} (only ${brierImprovement.toFixed(1)}% vs naive)`,
          evidence:   'Model probabilities are barely better than a coin flip when used directly. Raw probabilities need post-processing or better features.',
          fix:        'Implement Platt scaling on held-out calibration set. Consider isotonic regression if n>200. Evaluate ECE after tuning.',
          impact:     '+2-4pp WR on high-probability picks',
          confidence: 72,
          engCost:    'Medium',
          roiGain:    '+0.8%',
        });
      }
    }

    // 5. Missing features
    const missingFeatures = health.filter(r => r.coverage < 50);
    if (missingFeatures.length > 0) {
      causes.push({
        id:         'missing-features',
        severity:   'medium',
        title:      `${missingFeatures.length} Features Below 50% Coverage`,
        metric:     `${missingFeatures.map(r => r.name).slice(0, 3).join(', ')}${missingFeatures.length > 3 ? '…' : ''}`,
        evidence:   'Features with <50% coverage provide unreliable signal and may introduce selection bias. The model trains differently from how it predicts.',
        fix:        'Fix data pipeline for each missing feature. If data unavailable, remove from feature set. Add data validation checks to ETL.',
        impact:     'Removes noise from model training',
        confidence: 80,
        engCost:    'Medium',
        roiGain:    '+0.5%',
      });
    }

    // 6. Low EV
    if (summary.avg_ev !== null && summary.avg_ev < 3) {
      causes.push({
        id:         'low-avg-ev',
        severity:   'medium',
        title:      'Low Average EV per Pick',
        metric:     `Avg EV: ${summary.avg_ev.toFixed(1)}%`,
        evidence:   'Picks below 3% EV have high noise-to-signal ratio. A filter for minimum EV may improve realized ROI even if it reduces volume.',
        fix:        'Test a minimum 3% EV filter on historical picks. Compare WR and ROI to unfiltered set.',
        impact:     '-30% pick volume, +2pp WR estimated',
        confidence: 65,
        engCost:    'Low',
        roiGain:    '+1.2%',
      });
    }

    // 7. CLV positive (this is good — a positive finding)
    if (summary.avg_clv > 0 && summary.clv_picks >= 10) {
      causes.push({
        id:         'positive-clv',
        severity:   'positive',
        title:      'Positive CLV Signal Confirmed',
        metric:     `Avg CLV +${summary.avg_clv.toFixed(2)}pp, ${summary.beat_close.toFixed(1)}% beat rate`,
        evidence:   `${summary.clv_picks} picks with closing line data. Consistently beating the close means the model is capturing genuine market inefficiencies.`,
        fix:        'Protect this signal: avoid model changes that reduce CLV. Expand CLV tracking to 100% of picks.',
        impact:     'Confirms genuine long-run edge',
        confidence: summary.clv_picks >= 30 ? 82 : 55,
        engCost:    'Low',
        roiGain:    'Sustain +1.4%',
      });
    }

    // 8. Top feature
    if (features.length > 0) {
      const top = [...features].sort((a, b) => Math.abs(b.corr) - Math.abs(a.corr))[0];
      if (top && Math.abs(top.corr) > 0.15) {
        causes.push({
          id:         'top-feature-signal',
          severity:   'low',
          title:      `Strong Signal: ${top.name}`,
          metric:     `Point-biserial corr: ${top.corr.toFixed(3)}`,
          evidence:   `${top.name} is your strongest feature. Mean won: ${top.mean_won?.toFixed(3) ?? '—'} vs mean lost: ${top.mean_lost?.toFixed(3) ?? '—'}. Consider engineering interaction features from this.`,
          fix:        'Build interaction terms between top 3 features. Test polynomial transformation.',
          impact:     '+1-2pp WR if interaction captures nonlinearity',
          confidence: 60,
          engCost:    'Medium',
          roiGain:    '+0.6%',
        });
      }
    }

    // Sort: critical > high > medium > low > positive
    const ORDER: Severity[] = ['critical', 'high', 'medium', 'low', 'positive'];
    return causes.sort((a, b) => ORDER.indexOf(a.severity) - ORDER.indexOf(b.severity));
  }, [summary, calibration, health, features]);
}

// ── Root Cause Card ───────────────────────────────────────────────────────────

function RootCauseCard({ cause }: { cause: RootCause }) {
  const sev = SEV_CONFIG[cause.severity];

  return (
    <div className={styles.card} style={{ borderColor: `${sev.color}22` }}>
      {/* Header */}
      <div className={styles.cardHeader}>
        <div className={styles.cardLeft}>
          <StatusBadge status={sev.badgeStatus} label={sev.label} size="sm" />
          <h3 className={styles.cardTitle}>{cause.title}</h3>
        </div>
        <div className={styles.cardRight}>
          <span className={styles.confidence} title="Athena confidence in this diagnosis">
            {cause.confidence}% conf
          </span>
        </div>
      </div>

      {/* Metric */}
      <div className={styles.metricRow}>
        <span className={styles.metricLabel}>Metric</span>
        <code className={styles.metricValue} style={{ color: sev.color }}>{cause.metric}</code>
      </div>

      {/* Evidence */}
      <p className={styles.evidence}>{cause.evidence}</p>

      {/* Fix */}
      <div className={styles.fixBox}>
        <div className={styles.fixLabel}>Proposed Fix</div>
        <p className={styles.fixText}>{cause.fix}</p>
      </div>

      {/* Footer */}
      <div className={styles.cardFooter}>
        <div className={styles.footerItem}>
          <span className={styles.footerLabel}>Impact</span>
          <span className={styles.footerValue}>{cause.impact}</span>
        </div>
        <div className={styles.footerItem}>
          <span className={styles.footerLabel}>Eng Cost</span>
          <span className={[
            styles.footerValue,
            cause.engCost === 'Low' ? styles.costLow : cause.engCost === 'High' ? styles.costHigh : styles.costMed,
          ].join(' ')}>{cause.engCost}</span>
        </div>
        <div className={styles.footerItem}>
          <span className={styles.footerLabel}>Est. ROI Gain</span>
          <span className={styles.footerValue + ' ' + styles.roiGain}>{cause.roiGain}</span>
        </div>
      </div>
    </div>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────────

export default function RootCausePage() {
  const { isLoading } = useAthenaData();
  const causes = useRootCauses();
  const summary = useAthenaStore(selectSummary);

  const critical = causes.filter(c => c.severity === 'critical').length;
  const high     = causes.filter(c => c.severity === 'high').length;
  const positive = causes.filter(c => c.severity === 'positive').length;
  const totalGain = causes
    .map(c => parseFloat(c.roiGain.replace(/[^0-9.-]/g, '')))
    .filter(n => !isNaN(n) && n > 0)
    .reduce((s, n) => s + n, 0);

  return (
    <SectionPage
      icon="🚨"
      title="Root Cause Analysis"
      subtitle="Athena's diagnosis: prioritized issues, evidence, and proposed fixes"
      athenaQuery="Walk me through the most critical model issues and what to fix first"
    >
      {/* Summary */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
        <MetricCard
          label="Critical Issues"
          value={critical}
          decimals={0}
          color={critical > 0 ? 'red' : 'green'}
          skeleton={isLoading}
        />
        <MetricCard
          label="High Issues"
          value={high}
          decimals={0}
          color={high > 0 ? 'amber' : 'green'}
          skeleton={isLoading}
        />
        <MetricCard
          label="Positives"
          value={positive}
          decimals={0}
          color="green"
          skeleton={isLoading}
        />
        <MetricCard
          label="Est. Total ROI Gain"
          value={totalGain}
          suffix="%"
          decimals={1}
          color="purple"
          context="if all issues resolved"
          skeleton={isLoading}
        />
      </div>

      {/* Root cause cards */}
      <div className={styles.cardList}>
        {causes.map(cause => (
          <RootCauseCard key={cause.id} cause={cause} />
        ))}
        {!isLoading && causes.length === 0 && (
          <div className={styles.empty}>
            No root causes generated — load diagnostic data first.
          </div>
        )}
      </div>

      {/* Athena summary */}
      <AthenaSummary
        finding={
          causes.length > 0
            ? `Athena identified **${causes.length} issues** (${critical} critical, ${high} high). The single highest-impact fix is: **${causes[0]?.title ?? '—'}**. Addressing all issues could yield an estimated **+${totalGain.toFixed(1)}% ROI** improvement.`
            : 'No diagnostic data loaded. Run the full diagnostic suite to generate root cause analysis.'
        }
        confidence={summary ? 78 : 30}
        roiImpact={`+${totalGain.toFixed(1)}% ROI`}
        experiment="Start with the snapshot coverage fix — it unlocks the entire diagnosis loop at zero model risk"
      />
    </SectionPage>
  );
}
