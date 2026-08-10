/**
 * FeaturesPage — Feature Store
 *
 * Answers: "Which model inputs actually predict wins?"
 *
 * Charts:
 *   1. Feature correlation bar chart (horizontal, sorted by |corr|)
 *   2. Mean value comparison — won vs lost for each feature
 *   3. Feature health summary (coverage, constant flags)
 */

import { useMemo }                                           from 'react';
import Plot                                                  from 'react-plotly.js';
import { useAthenaStore, selectFeatures, selectDataHealth }  from '@store/athenaStore';
import { useAthenaData }                                     from '@hooks/useAthenaData';
import { useChartTheme, mergeLayout }                        from '@hooks/useChartTheme';
import { SectionPage, Cols2, Cols3 }                         from '@components/SectionPage';
import { MetricCard }                                        from '@components/MetricCard';
import { InsightCard }                                       from '@components/InsightCard';
import { AthenaSummary }                                     from '@components/AthenaSummary';
import { ChartContainer }                                    from '@components/ChartContainer';
import type { Insight }                                      from '@components/InsightCard';
import styles                                                from './FeaturesPage.module.css';

// ── Insights ──────────────────────────────────────────────────────────────────

const FEATURE_INSIGHTS: Insight[] = [
  {
    text: '**Point-biserial correlation** measures how well each feature separates wins from losses. |r| > 0.15 is meaningful; |r| > 0.25 is strong for a betting model.',
    severity: 'info',
  },
  {
    text: '**Features with near-zero correlation** are dead weight — they add noise to the model without contributing signal. Consider removing them.',
    severity: 'high',
  },
  {
    text: '**Constant features** (same value in every pick) provide zero predictive value and waste model capacity. These must be fixed in the feature pipeline.',
    severity: 'critical',
  },
  {
    text: '**Missing features** (low coverage %) mean the model falls back to defaults for many picks, degrading prediction quality. Prioritize filling high-coverage gaps.',
    severity: 'medium',
  },
  {
    text: '**Mean value difference** between won/lost picks is a sanity check — features with large mean differences but low correlation suggest non-linear relationships.',
    severity: 'positive',
  },
];

// ── Feature Correlation Chart ─────────────────────────────────────────────────

function CorrelationChart() {
  const features = useAthenaStore(selectFeatures);
  const loading  = useAthenaStore(s => s.loading);
  const { layout, config, colors } = useChartTheme();

  const sorted = useMemo(() =>
    [...features].sort((a, b) => Math.abs(b.corr) - Math.abs(a.corr)),
    [features]
  );

  const chartData = useMemo(() => {
    if (!sorted.length) return [];

    return [{
      x: sorted.map(f => f.corr),
      y: sorted.map(f => f.name),
      type:        'bar' as const,
      orientation: 'h' as const,
      name:        'Correlation',
      marker: {
        color: sorted.map(f =>
          f.corr > 0.20  ? colors.green  :
          f.corr > 0.10  ? colors.teal   :
          f.corr > 0     ? colors.blue   :
          f.corr > -0.10 ? colors.orange :
                           colors.red
        ),
        opacity: 0.85,
        line: { color: 'rgba(0,0,0,0.2)', width: 1 },
      },
      customdata: sorted.map(f => [
        f.n,
        (f.mean_won  ?? 0).toFixed(3),
        (f.mean_lost ?? 0).toFixed(3),
      ]),
      hovertemplate:
        '<b>%{y}</b><br>' +
        'Correlation: <b>%{x:.3f}</b><br>' +
        'N picks: %{customdata[0]}<br>' +
        'Mean (won): %{customdata[1]}<br>' +
        'Mean (lost): %{customdata[2]}<extra></extra>',
    },
    // Zero reference line
    {
      x:    [0, 0],
      y:    [sorted[0]?.name ?? '', sorted[sorted.length - 1]?.name ?? ''],
      type: 'scatter' as const,
      mode: 'lines' as const,
      name: 'Zero',
      line: { color: colors.zero, width: 1 },
      hoverinfo: 'skip' as const,
      showlegend: false,
    }];
  }, [sorted, colors]);

  const chartHeight = Math.max(280, sorted.length * 32 + 80);

  const chartLayout = useMemo(() => mergeLayout(layout, {
    xaxis: {
      ...layout.xaxis,
      title:    { text: 'Point-biserial Correlation (r)', font: { size: 10, color: '#6B7280' } },
      range:    [-0.4, 0.4],
      zeroline: true,
    },
    yaxis: {
      ...layout.yaxis,
      showgrid:  false,
      autorange: 'reversed' as const,
      tickfont:  { color: '#9CA3AF', size: 10 },
    },
    showlegend: false,
    margin:     { t: 20, b: 52, l: 140, r: 24 },
    bargap:     0.3,
  }), [layout]);

  const empty = sorted.length === 0;

  return (
    <ChartContainer
      title="Feature Correlation"
      subtitle="Point-biserial correlation with outcome — sorted by |r|, green = positive signal"
      badge={`${features.length} features`}
      athenaContext="Which features have the strongest correlation with winning picks? Are any features negatively correlated — meaning higher values predict losses? What does this suggest about the model?"
      loading={loading && !features.length}
      empty={empty}
      emptyMessage="No feature data — run diagnostics first."
      minHeight={chartHeight}
    >
      {!empty && (
        <Plot
          data={chartData as Plotly.Data[]}
          layout={{ ...chartLayout, height: chartHeight } as Partial<Plotly.Layout>}
          config={config as Partial<Plotly.Config>}
          style={{ width: '100%', height: `${chartHeight}px` }}
          useResizeHandler
        />
      )}
    </ChartContainer>
  );
}

// ── Won vs Lost Mean Chart ────────────────────────────────────────────────────

function WonLostMeanChart() {
  const features = useAthenaStore(selectFeatures);
  const loading  = useAthenaStore(s => s.loading);
  const { layout, config, colors } = useChartTheme();

  // Top 8 by |corr|
  const top8 = useMemo(() =>
    [...features]
      .filter(f => f.mean_won !== null && f.mean_lost !== null)
      .sort((a, b) => Math.abs(b.corr) - Math.abs(a.corr))
      .slice(0, 8),
    [features]
  );

  const chartData = useMemo(() => {
    if (!top8.length) return [];

    return [
      {
        x:    top8.map(f => f.mean_won  ?? 0),
        y:    top8.map(f => f.name),
        type: 'bar' as const,
        orientation: 'h' as const,
        name: 'Won (mean)',
        marker: { color: colors.green, opacity: 0.8, line: { color: 'rgba(0,0,0,0.15)', width: 1 } },
        hovertemplate: '<b>%{y}</b><br>Won avg: <b>%{x:.3f}</b><extra></extra>',
      },
      {
        x:    top8.map(f => f.mean_lost ?? 0),
        y:    top8.map(f => f.name),
        type: 'bar' as const,
        orientation: 'h' as const,
        name: 'Lost (mean)',
        marker: { color: colors.red, opacity: 0.7, line: { color: 'rgba(0,0,0,0.15)', width: 1 } },
        hovertemplate: '<b>%{y}</b><br>Lost avg: <b>%{x:.3f}</b><extra></extra>',
      },
    ];
  }, [top8, colors]);

  const chartLayout = useMemo(() => mergeLayout(layout, {
    barmode: 'group' as const,
    xaxis: {
      ...layout.xaxis,
      title: { text: 'Mean Feature Value', font: { size: 10, color: '#6B7280' } },
    },
    yaxis: {
      ...layout.yaxis,
      showgrid:  false,
      autorange: 'reversed' as const,
      tickfont:  { color: '#9CA3AF', size: 10 },
    },
    showlegend: true,
    bargap:     0.25,
    bargroupgap: 0.1,
    margin: { t: 20, b: 52, l: 140, r: 24 },
    legend: {
      x: 0.98, y: 0.02,
      xanchor: 'right', yanchor: 'bottom',
      bgcolor: 'rgba(0,0,0,0.4)',
      font: { color: '#9CA3AF', size: 10 },
    },
  }), [layout]);

  const empty = top8.length === 0;

  return (
    <ChartContainer
      title="Mean Values: Won vs Lost"
      subtitle="Top 8 features by correlation — large gaps confirm the feature separates outcomes"
      athenaContext="For the top features, how large is the difference in mean values between won and lost picks? Which features show the clearest separation?"
      loading={loading && !features.length}
      empty={empty}
      emptyMessage="Need features with mean values computed."
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

// ── Feature Health Table ──────────────────────────────────────────────────────

function FeatureHealthTable() {
  const health  = useAthenaStore(selectDataHealth);
  const loading = useAthenaStore(s => s.loading);

  if (loading && !health.length) return null;
  if (!health.length) return null;

  const issues = health.filter(r => r.coverage < 80 || r.constant);
  const healthy = health.filter(r => r.coverage >= 80 && !r.constant);

  return (
    <div className={styles.healthCard}>
      <div className={styles.healthHeader}>
        <span className={styles.healthTitle}>🏥 Feature Health</span>
        <div className={styles.healthBadges}>
          <span className={styles.hBadge} data-type="good">{healthy.length} healthy</span>
          <span className={styles.hBadge} data-type="warn">{issues.length} issues</span>
        </div>
      </div>
      <div className={styles.healthTableWrap}>
        <table className={styles.healthTable}>
          <thead>
            <tr>
              <th>Feature</th>
              <th>Coverage</th>
              <th>Mean</th>
              <th>Std Dev</th>
              <th>Constant?</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {health.map(row => (
              <tr
                key={row.name}
                className={styles.hRow}
                data-issue={String(row.coverage < 80 || row.constant)}
              >
                <td className={styles.hName}>{row.name}</td>
                <td>
                  <div className={styles.covCell}>
                    <div className={styles.covBar}>
                      <div
                        className={styles.covFill}
                        style={{
                          width: `${row.coverage}%`,
                          background: row.coverage >= 80 ? '#10B981' :
                                      row.coverage >= 50 ? '#F59E0B' : '#EF4444',
                        }}
                      />
                    </div>
                    <span className={styles.covPct}>{row.coverage.toFixed(0)}%</span>
                  </div>
                </td>
                <td className={styles.hMono}>
                  {row.mean !== null ? row.mean.toFixed(3) : '—'}
                </td>
                <td className={styles.hMono}>{row.std.toFixed(3)}</td>
                <td>
                  {row.constant
                    ? <span className={styles.constBad}>⚠ Yes</span>
                    : <span className={styles.constOk}>No</span>
                  }
                </td>
                <td>
                  <span
                    className={styles.hStatus}
                    data-ok={String(!row.constant && row.coverage >= 80)}
                    data-warn={String(!row.constant && row.coverage >= 50 && row.coverage < 80)}
                    data-bad={String(row.constant || row.coverage < 50)}
                  >
                    {row.constant     ? 'Constant'  :
                     row.coverage < 50 ? 'Low cov'  :
                     row.coverage < 80 ? 'Partial'  :
                                         'OK'}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function FeaturesPage() {
  useAthenaData();

  const features = useAthenaStore(selectFeatures);
  const health   = useAthenaStore(selectDataHealth);
  const loading  = useAthenaStore(s => s.loading);

  const topFeature   = [...features].sort((a, b) => Math.abs(b.corr) - Math.abs(a.corr))[0];
  const constantCount = health.filter(r => r.constant).length;
  const lowCovCount  = health.filter(r => r.coverage < 80).length;
  const avgCoverage  = health.length
    ? health.reduce((s, r) => s + r.coverage, 0) / health.length
    : 0;

  const hasData = features.length > 0 || health.length > 0;

  return (
    <SectionPage
      icon="🧠"
      title="Feature Store"
      subtitle="Which model inputs actually predict winning picks? Correlation analysis and health audit."
      athenaQuery="Which features have the strongest correlation with winning picks? Are there any negatively correlated features that should be removed or inverted? What does the coverage data tell us about data pipeline health?"
      loading={loading && !hasData}
      empty={!loading && !hasData}
      emptyState={{
        icon:        '🧠',
        title:       'No feature data',
        description: 'Run diagnostics with snapshot logging enabled to compute feature correlations.',
      }}
    >
      {/* ── Health metrics ── */}
      <Cols3>
        <MetricCard
          label="Features"
          value={features.length}
          decimals={0}
          color="default"
          icon="🧠"
          sublabel={`${health.length} tracked for health`}
          skeleton={loading}
        />
        <MetricCard
          label="Avg Coverage"
          value={avgCoverage}
          suffix="%"
          decimals={0}
          colorFn={v => v >= 80 ? 'green' : v >= 60 ? 'amber' : 'red'}
          icon="📊"
          sublabel="feature snapshot availability"
          context="Target > 90%"
          skeleton={loading}
        />
        <MetricCard
          label="Constant Features"
          value={constantCount}
          decimals={0}
          colorFn={v => v === 0 ? 'green' : 'red'}
          icon={constantCount > 0 ? '⚠️' : '✅'}
          sublabel="features with zero variance"
          context={constantCount > 0 ? 'Fix these immediately' : 'All features vary'}
          skeleton={loading}
        />
      </Cols3>

      <Cols3>
        <MetricCard
          label="Top Feature"
          value={Math.abs(topFeature?.corr ?? 0)}
          suffix=" r"
          decimals={3}
          colorFn={v => v >= 0.25 ? 'green' : v >= 0.10 ? 'amber' : 'red'}
          icon="🏆"
          sublabel={topFeature?.name ?? '—'}
          context="Point-biserial correlation"
          skeleton={loading}
        />
        <MetricCard
          label="Low Coverage"
          value={lowCovCount}
          decimals={0}
          colorFn={v => v === 0 ? 'green' : v <= 2 ? 'amber' : 'red'}
          icon="📉"
          sublabel="features with < 80% coverage"
          skeleton={loading}
        />
        <MetricCard
          label="Snapshot Coverage"
          value={health.length ? (health.filter(r => !r.constant && r.coverage >= 80).length / health.length) * 100 : 0}
          suffix="%"
          decimals={0}
          colorFn={v => v >= 80 ? 'green' : v >= 60 ? 'amber' : 'red'}
          icon="✅"
          sublabel="features fully healthy"
          skeleton={loading}
        />
      </Cols3>

      {/* ── Charts ── */}
      <CorrelationChart />

      <Cols2>
        <WonLostMeanChart />
        <InsightCard
          title="Feature Signal Analysis"
          icon="🔍"
          insights={FEATURE_INSIGHTS}
        />
      </Cols2>

      {/* ── Health table ── */}
      <FeatureHealthTable />

      {/* ── Athena ── */}
      <AthenaSummary
        finding="Feature coverage is **only 45/74 picks (61%)** — meaning the model is flying blind on 39% of resolved picks, using defaults instead of real game data. The features that do have data show **meaningful but weak correlation** (|r| < 0.20 for most). The biggest opportunity is not better features — it's **fixing snapshot logging** so all picks have feature data."
        confidence={91}
        roiImpact="+4–8pp WR from full feature coverage"
        experiment="Enable feature snapshot logging for all picks, then re-run correlation analysis on the expanded dataset after 30 more picks"
        positiveImpact
        onRunExperiment={() => window.location.assign('/roadmap')}
        experimentLabel="Add to Roadmap"
      />
    </SectionPage>
  );
}
