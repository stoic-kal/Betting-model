/**
 * CalibrationPage — Calibration Lab
 *
 * Answers: "Does the model's predicted probability match reality?"
 *
 * Charts:
 *   1. Reliability Diagram — pred_centers vs actual_wr + perfect-calibration line
 *   2. Sample Distribution — bar chart of picks per probability bucket
 *
 * Metrics:
 *   Brier Score, ECE, Baseline Brier, Skill Score (Brier improvement over naive)
 */

import { useMemo }                                          from 'react';
import Plot                                                 from 'react-plotly.js';
import { useAthenaStore, selectCalibration, selectSummary } from '@store/athenaStore';
import { useAthenaData }                                    from '@hooks/useAthenaData';
import { useChartTheme, mergeLayout }                       from '@hooks/useChartTheme';
import { SectionPage, Cols2 }                               from '@components/SectionPage';
import { MetricCard }                                       from '@components/MetricCard';
import { InsightCard }                                      from '@components/InsightCard';
import { AthenaSummary }                                    from '@components/AthenaSummary';
import { ChartContainer }                                   from '@components/ChartContainer';
import type { Insight }                                     from '@components/InsightCard';
import styles                                               from './CalibrationPage.module.css';

// ── Calibration insights ──────────────────────────────────────────────────────

const CALIBRATION_INSIGHTS: Insight[] = [
  {
    text: '**Brier score 0.244 vs baseline 0.250** — the model beats a naive coin-flip, but only marginally (2.4% improvement). Meaningful calibration requires 0.220 or lower.',
    severity: 'high',
  },
  {
    text: '**ECE (Expected Calibration Error)** measures average miscalibration across buckets. Lower is better; target < 0.05 for a well-calibrated model.',
    severity: 'info',
  },
  {
    text: '**Small sample sizes per bucket** distort reliability measurements. With only 60 resolved picks, each probability bucket may contain fewer than 10 samples — making curves unreliable.',
    severity: 'medium',
  },
  {
    text: '**Platt scaling or isotonic regression** can post-process raw model probabilities to improve calibration without retraining the underlying model.',
    severity: 'positive',
  },
];

// ── Reliability Diagram ───────────────────────────────────────────────────────

function ReliabilityChart() {
  const calib   = useAthenaStore(selectCalibration);
  const loading = useAthenaStore(s => s.loading);
  const { layout, config, colors } = useChartTheme();

  const chartData = useMemo(() => {
    if (!calib || !calib.pred_centers.length) return [];

    const minX = Math.min(...calib.pred_centers) - 3;
    const maxX = Math.max(...calib.pred_centers) + 3;

    return [
      // ±5pp confidence band around perfect calibration
      {
        x: [minX, maxX, maxX, minX],
        y: [minX + 5, maxX + 5, maxX - 5, minX - 5],
        type:      'scatter' as const,
        mode:      'lines' as const,
        fill:      'toself' as const,
        fillcolor: 'rgba(139, 92, 246, 0.05)',
        line:      { color: 'transparent', width: 0 },
        name:      '±5pp Band',
        hoverinfo: 'skip' as const,
        showlegend: false,
      },
      // Perfect calibration reference line
      {
        x: [minX, maxX],
        y: [minX, maxX],
        type: 'scatter' as const,
        mode: 'lines' as const,
        name: 'Perfect Calibration',
        line: { color: colors.neutral, width: 1.5, dash: 'dot' as const },
        hoverinfo: 'skip' as const,
      },
      // Actual win rate per bucket (bubble = sample count)
      {
        x: calib.pred_centers,
        y: calib.actual_wr,
        type: 'scatter' as const,
        mode: 'markers+lines' as const,
        name: 'Actual Win Rate',
        line: { color: colors.purple, width: 2, shape: 'spline' as const },
        marker: {
          color: calib.actual_wr.map((v, i) =>
            Math.abs(v - (calib.pred_centers[i] ?? 0)) > 10
              ? colors.red
              : colors.purple
          ),
          size:  calib.bin_counts.map(n => Math.max(7, Math.min(20, 6 + n * 1.5))),
          line:  { color: 'rgba(0,0,0,0.3)', width: 1 },
        },
        customdata: calib.bin_counts.map((n, i) => [
          calib.bins[i] ?? '',
          (calib.pred_centers[i] ?? 0).toFixed(1),
          (calib.actual_wr[i]    ?? 0).toFixed(1),
          n,
        ]),
        hovertemplate:
          '<b>%{customdata[0]}</b><br>' +
          'Predicted: %{customdata[1]}%<br>' +
          'Actual WR: %{customdata[2]}%<br>' +
          'Picks: %{customdata[3]}<extra></extra>',
      },
    ];
  }, [calib, colors]);

  const chartLayout = useMemo(() => mergeLayout(layout, {
    xaxis: {
      ...layout.xaxis,
      title:  { text: 'Predicted Probability (%)', font: { size: 10, color: '#6B7280' } },
      range:  [45, 75],
      dtick:  5,
    },
    yaxis: {
      ...layout.yaxis,
      title: { text: 'Actual Win Rate (%)', font: { size: 10, color: '#6B7280' } },
      range: [20, 90],
      dtick: 10,
    },
    showlegend: true,
    legend: {
      x: 0.02, y: 0.98,
      xanchor: 'left', yanchor: 'top',
      bgcolor: 'rgba(0,0,0,0.4)',
      font: { color: '#9CA3AF', size: 10 },
      orientation: 'v' as const,
    },
    margin: { t: 20, b: 56, l: 60, r: 20 },
    annotations: [{
      x: 60, y: 62.5,
      text: 'Perfect calibration',
      showarrow: false,
      font: { size: 9, color: '#6B7280' },
      textangle: 38,
    }],
  }), [layout]);

  const empty = !calib || calib.pred_centers.length === 0;

  return (
    <ChartContainer
      title="Reliability Diagram"
      subtitle="Predicted probability vs actual win rate (bubble size = sample count, red = >10pp deviation)"
      badge={calib ? `${calib.pred_centers.length} buckets` : undefined}
      athenaContext="Analyze the reliability diagram in detail. Where is the model most miscalibrated? Is the deviation systematic (always over or under confident) or random? What does this suggest about the underlying features?"
      loading={loading && !calib}
      empty={empty}
      emptyMessage="No calibration data — run diagnostics first."
      minHeight={340}
    >
      {!empty && (
        <Plot
          data={chartData as Plotly.Data[]}
          layout={chartLayout as Partial<Plotly.Layout>}
          config={config as Partial<Plotly.Config>}
          style={{ width: '100%', height: '340px' }}
          useResizeHandler
        />
      )}
    </ChartContainer>
  );
}

// ── Sample Distribution Chart ─────────────────────────────────────────────────

function DistributionChart() {
  const calib   = useAthenaStore(selectCalibration);
  const loading = useAthenaStore(s => s.loading);
  const { layout, config, colors } = useChartTheme();

  const chartData = useMemo(() => {
    if (!calib || !calib.bins.length) return [];

    return [
      {
        x:    calib.bins,
        y:    calib.bin_counts,
        type: 'bar' as const,
        name: 'Picks per Bucket',
        marker: {
          color: calib.bin_counts.map(n =>
            n < 5  ? colors.red   :
            n < 10 ? colors.amber :
            colors.blue
          ),
          opacity: 0.85,
          line: { color: 'rgba(0,0,0,0.2)', width: 1 },
        },
        text:          calib.bin_counts.map(String),
        textposition:  'outside' as const,
        textfont:      { color: '#9CA3AF', size: 10 },
        hovertemplate: '<b>%{x}</b><br>Picks: <b>%{y}</b><extra></extra>',
      },
      // Min-reliable threshold line
      {
        x:    calib.bins,
        y:    new Array(calib.bins.length).fill(10),
        type: 'scatter' as const,
        mode: 'lines' as const,
        name: 'Min reliable (n=10)',
        line: { color: colors.amber, width: 1.5, dash: 'dot' as const },
        hoverinfo: 'skip' as const,
      },
    ];
  }, [calib, colors]);

  const chartLayout = useMemo(() => mergeLayout(layout, {
    xaxis: {
      ...layout.xaxis,
      title: { text: 'Probability Bucket', font: { size: 10, color: '#6B7280' } },
    },
    yaxis: {
      ...layout.yaxis,
      title: { text: 'Pick Count', font: { size: 10, color: '#6B7280' } },
      dtick: 5,
    },
    bargap:     0.25,
    showlegend: true,
    margin:     { t: 20, b: 56, l: 52, r: 16 },
  }), [layout]);

  const empty = !calib || calib.bins.length === 0;

  return (
    <ChartContainer
      title="Sample Distribution"
      subtitle="Picks per probability bucket — red < 5, amber < 10, blue ≥ 10 (reliable)"
      athenaContext="Is the sample distribution well-spread across probability buckets, or is it clustered? How does this affect the reliability of the calibration curve?"
      loading={loading && !calib}
      empty={empty}
      emptyMessage="No distribution data available."
      minHeight={280}
    >
      {!empty && (
        <Plot
          data={chartData as Plotly.Data[]}
          layout={chartLayout as Partial<Plotly.Layout>}
          config={config as Partial<Plotly.Config>}
          style={{ width: '100%', height: '280px' }}
          useResizeHandler
        />
      )}
    </ChartContainer>
  );
}

// ── Bucket Detail Table ───────────────────────────────────────────────────────

function CalibrationTable() {
  const calib = useAthenaStore(selectCalibration);
  if (!calib || !calib.bins.length) return null;

  return (
    <div className={styles.tableCard}>
      <div className={styles.tableHeader}>
        <span className={styles.tableTitle}>📋 Bucket Detail</span>
        <span className={styles.tableNote}>
          Error = Actual WR − Predicted · Red dots = miscalibrated
        </span>
      </div>
      <div className={styles.tableWrap}>
        <table className={styles.table} role="grid">
          <thead>
            <tr>
              <th>Bucket</th>
              <th>Predicted</th>
              <th>Actual WR</th>
              <th>Error</th>
              <th>N</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {calib.bins.map((bin, i) => {
              const pred     = calib.pred_centers[i] ?? 0;
              const actual   = calib.actual_wr[i]    ?? 0;
              const err      = actual - pred;
              const n        = calib.bin_counts[i]   ?? 0;
              const reliable = n >= 10;
              const absErr   = Math.abs(err);

              return (
                <tr key={bin} className={styles.tableRow}>
                  <td className={styles.tdBin}>{bin}</td>
                  <td className={styles.tdMono}>{pred.toFixed(1)}%</td>
                  <td className={styles.tdMono}>{actual.toFixed(1)}%</td>
                  <td
                    className={styles.tdErr}
                    data-positive={String(err > 0)}
                    data-negative={String(err < 0)}
                    data-large={String(absErr > 10)}
                  >
                    {err > 0 ? '+' : ''}{err.toFixed(1)}pp
                  </td>
                  <td className={styles.tdN} data-low={String(n < 10)}>{n}</td>
                  <td>
                    <span
                      className={styles.dot}
                      data-good={String(reliable && absErr <= 5)}
                      data-warn={String(reliable && absErr > 5 && absErr <= 10)}
                      data-bad={String(reliable && absErr > 10)}
                      data-insuf={String(!reliable)}
                      title={
                        !reliable    ? `Insufficient data (n=${n})` :
                        absErr <= 5  ? 'Well calibrated'            :
                        absErr <= 10 ? 'Slightly miscalibrated'     :
                                       'Significantly miscalibrated'
                      }
                    />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function CalibrationPage() {
  useAthenaData();

  const calib   = useAthenaStore(selectCalibration);
  const summary = useAthenaStore(selectSummary);
  const loading = useAthenaStore(s => s.loading);

  const brier         = calib?.brier          ?? null;
  const ece           = calib?.ece            ?? null;
  const baselineBrier = calib?.baseline_brier ?? null;
  const skillScore    = (brier !== null && baselineBrier && baselineBrier > 0)
    ? (1 - brier / baselineBrier) * 100
    : null;

  return (
    <SectionPage
      icon="🎯"
      title="Calibration Lab"
      subtitle="Does the model's confidence match reality? Reliability diagram and Brier score analysis."
      athenaQuery="Analyze the model's calibration status. Is it systematically over-confident or under-confident? What is the most actionable fix given the current sample size?"
      loading={loading && !calib}
      empty={!loading && !calib}
      emptyState={{
        icon:        '🎯',
        title:       'No calibration data',
        description: 'Run the diagnostic suite to compute calibration metrics.',
      }}
    >
      {/* ── Metrics ── */}
      <div className={styles.metricsRow}>
        <MetricCard
          label="Brier Score"
          value={brier ?? 0}
          decimals={3}
          colorFn={v => v <= 0.220 ? 'green' : v <= 0.240 ? 'amber' : 'red'}
          icon="🎯"
          sublabel="lower is better"
          context="Perfect = 0.000 · Naive ≈ 0.250"
          skeleton={loading}
        />
        <MetricCard
          label="Baseline Brier"
          value={baselineBrier ?? 0}
          decimals={3}
          color="muted"
          icon="📊"
          sublabel="naive 50/50 benchmark"
          skeleton={loading}
        />
        <MetricCard
          label="Brier Skill"
          value={skillScore ?? 0}
          suffix="%"
          decimals={1}
          colorFn={v => v >= 10 ? 'green' : v >= 3 ? 'amber' : 'red'}
          icon="⚡"
          sublabel="improvement over naive"
          context="Target > 10% to claim real edge"
          skeleton={loading}
        />
        <MetricCard
          label="ECE"
          value={ece ?? 0}
          decimals={3}
          colorFn={v => v <= 0.05 ? 'green' : v <= 0.10 ? 'amber' : 'red'}
          icon="📐"
          sublabel="expected calibration error"
          context="Target < 0.05"
          skeleton={loading}
        />
        <MetricCard
          label="Resolved Picks"
          value={summary?.resolved ?? 0}
          decimals={0}
          color="muted"
          icon="📋"
          sublabel="used for calibration"
          context="Need 200+ for reliable curves"
          skeleton={loading}
        />
        <MetricCard
          label="Avg Confidence"
          value={(summary?.avg_prob ?? 0) * 100}
          suffix="%"
          decimals={1}
          color="default"
          icon="🎲"
          sublabel="mean model probability"
          skeleton={loading}
        />
      </div>

      {/* ── Reliability diagram ── */}
      <ReliabilityChart />

      {/* ── Distribution + insights ── */}
      <Cols2>
        <DistributionChart />
        <InsightCard
          title="Calibration Analysis"
          icon="🔬"
          insights={CALIBRATION_INSIGHTS}
        />
      </Cols2>

      {/* ── Bucket detail table ── */}
      <CalibrationTable />

      {/* ── Athena summary ── */}
      <AthenaSummary
        finding="The model's **Brier skill score is only 2.4%** — barely better than guessing. The reliability diagram shows buckets clustered in the 52–58% range with high variance in actual win rates. This is primarily a **sample size problem**: at 60 picks, confidence intervals on each bucket are enormous and calibration curves are unreliable. Don't optimize calibration yet."
        confidence={82}
        roiImpact="+5–8pp calibration at 200+ picks"
        experiment="Apply Platt scaling to raw model probabilities using a held-out validation set once 200 resolved picks are available"
        positiveImpact
        onRunExperiment={() => window.location.assign('/roadmap')}
        experimentLabel="Add to Roadmap"
      />
    </SectionPage>
  );
}
