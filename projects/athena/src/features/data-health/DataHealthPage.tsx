/**
 * DataHealthPage — Feature Coverage & Data Quality Monitor
 */

import { useMemo }                                        from 'react';
import Plot                                               from 'react-plotly.js';
import { useAthenaStore, selectDataHealth, selectSummary } from '@store/athenaStore';
import { useAthenaData }                                  from '@hooks/useAthenaData';
import { useChartTheme, mergeLayout }                     from '@hooks/useChartTheme';
import { SectionPage, Cols2, Cols3 }                      from '@components/SectionPage';
import { MetricCard }                                     from '@components/MetricCard';
import { AthenaSummary }                                  from '@components/AthenaSummary';
import { ChartContainer }                                 from '@components/ChartContainer';
import { StatusBadge }                                    from '@components/StatusBadge';
import type { FeatureHealthRow }                          from '@types-athena';
import styles                                             from './DataHealthPage.module.css';

// ── Helpers ────────────────────────────────────────────────────────────────────

function coverageStatus(pct: number): 'ok' | 'warn' | 'error' {
  if (pct >= 80) return 'ok';
  if (pct >= 50) return 'warn';
  return 'error';
}

function fmt2(n: number | null): string {
  if (n === null) return '—';
  return n.toFixed(2);
}

// ── Coverage Bar Chart ────────────────────────────────────────────────────────

function CoverageBarChart({ rows }: { rows: FeatureHealthRow[] }) {
  const { layout, config, colors } = useChartTheme();

  const sorted = useMemo(
    () => [...rows].sort((a, b) => a.coverage - b.coverage),
    [rows]
  );

  const barColors = sorted.map(r =>
    r.coverage >= 80 ? colors.green :
    r.coverage >= 50 ? colors.amber :
    colors.red
  );

  return (
    <Plot
      data={[{
        type:        'bar',
        orientation: 'h',
        x:           sorted.map(r => r.coverage),
        y:           sorted.map(r => r.name),
        marker:      { color: barColors, opacity: 0.88 },
        hovertemplate: '<b>%{y}</b><br>Coverage: %{x:.1f}%<extra></extra>',
        text:        sorted.map(r => `${r.coverage.toFixed(0)}%`),
        textposition: 'outside' as const,
        textfont:    { color: '#6B7280', size: 10 },
        cliponaxis:  false,
      }]}
      layout={mergeLayout(layout, {
        height: Math.max(280, sorted.length * 28 + 60),
        margin: { t: 12, b: 40, l: 140, r: 60 },
        xaxis: {
          ...layout.xaxis,
          range:        [0, 110],
          ticksuffix:   '%',
          title:        { text: 'Coverage %', font: { color: '#6B7280', size: 10 } },
        },
        yaxis: { ...layout.yaxis, showgrid: false, automargin: true },
        shapes: [{
          type:  'line',
          x0:    80, x1: 80, y0: -0.5, y1: sorted.length - 0.5,
          line:  { color: colors.amber, width: 1, dash: 'dot' },
        }],
        showlegend: false,
        annotations: [{
          x:         80,
          y:         sorted.length - 0.5,
          text:      '80% threshold',
          showarrow: false,
          font:      { color: colors.amber, size: 9 },
          xanchor:   'left',
          yanchor:   'bottom',
          xshift:    4,
        }],
      })}
      config={config}
      style={{ width: '100%' }}
      useResizeHandler
    />
  );
}

function VarianceBarChart({ rows }: { rows: FeatureHealthRow[] }) {
  const { layout, config, colors } = useChartTheme();

  const sorted = useMemo(
    () => [...rows].filter(r => !r.constant).sort((a, b) => b.std - a.std).slice(0, 15),
    [rows]
  );

  return (
    <Plot
      data={[{
        type:        'bar',
        orientation: 'h',
        x:           sorted.map(r => r.std),
        y:           sorted.map(r => r.name),
        marker: {
          color:   colors.purple,
          opacity: 0.80,
          line:    { color: 'rgba(139,92,246,0.30)', width: 1 },
        },
        hovertemplate: '<b>%{y}</b><br>Std Dev: %{x:.3f}<extra></extra>',
      }]}
      layout={mergeLayout(layout, {
        height: Math.max(240, sorted.length * 28 + 60),
        margin: { t: 12, b: 40, l: 140, r: 16 },
        xaxis: {
          ...layout.xaxis,
          title: { text: 'Standard Deviation', font: { color: '#6B7280', size: 10 } },
        },
        yaxis:      { ...layout.yaxis, showgrid: false, automargin: true },
        showlegend: false,
      })}
      config={config}
      style={{ width: '100%' }}
      useResizeHandler
    />
  );
}

// ── Feature Stats Table ────────────────────────────────────────────────────────

function FeatureStatsTable({ rows }: { rows: FeatureHealthRow[] }) {
  const sorted = useMemo(
    () => [...rows].sort((a, b) => a.coverage - b.coverage),
    [rows]
  );

  return (
    <div className={styles.tableWrap}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th>Feature</th>
            <th className={styles.right}>Coverage</th>
            <th className={styles.right}>Mean</th>
            <th className={styles.right}>Std Dev</th>
            <th className={styles.center}>Status</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map(row => {
            const st = coverageStatus(row.coverage);
            return (
              <tr key={row.name} className={styles.row}>
                <td className={styles.featureName}>
                  {row.constant && <span className={styles.constBadge}>CONST</span>}
                  {row.name}
                </td>
                <td className={styles.right}>
                  <div className={styles.coverageCell}>
                    <div className={styles.coverageBar}>
                      <div
                        className={styles.coverageFill}
                        style={{
                          width: `${row.coverage}%`,
                          background: st === 'ok' ? '#10B981' : st === 'warn' ? '#F59E0B' : '#EF4444',
                        }}
                      />
                    </div>
                    <span className={styles.coveragePct}>{row.coverage.toFixed(0)}%</span>
                  </div>
                </td>
                <td className={`${styles.right} ${styles.mono}`}>{fmt2(row.mean)}</td>
                <td className={`${styles.right} ${styles.mono}`}>{fmt2(row.std)}</td>
                <td className={styles.center}>
                  <StatusBadge
                    status={st}
                    label={st === 'ok' ? 'Healthy' : st === 'warn' ? 'Partial' : 'Missing'}
                    size="sm"
                  />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function DataHealthPage() {
  const { isLoading } = useAthenaData();
  const rows    = useAthenaStore(selectDataHealth);
  const summary = useAthenaStore(selectSummary);

  const { healthy, partial, missing, constantCount, avgCoverage } = useMemo(() => {
    if (!rows.length) return { healthy: 0, partial: 0, missing: 0, constantCount: 0, avgCoverage: 0 };
    const h   = rows.filter(r => r.coverage >= 80).length;
    const p   = rows.filter(r => r.coverage >= 50 && r.coverage < 80).length;
    const m   = rows.filter(r => r.coverage < 50).length;
    const c   = rows.filter(r => r.constant).length;
    const avg = rows.reduce((s, r) => s + r.coverage, 0) / rows.length;
    return { healthy: h, partial: p, missing: m, constantCount: c, avgCoverage: avg };
  }, [rows]);

  const snapshotCoverage = summary
    ? Math.round((summary.with_snapshot / summary.total_picks) * 100)
    : 0;

  const overallStatus = avgCoverage >= 80 ? 'ok' : avgCoverage >= 60 ? 'warn' : 'error';

  return (
    <SectionPage
      icon="🏥"
      title="Data Health"
      subtitle={`Feature coverage, data completeness, and pipeline quality — ${avgCoverage.toFixed(0)}% avg coverage`}
      athenaQuery="Which features are missing data and how does it affect model quality?"
    >
      {/* Metric cards */}
      <Cols3>
        <MetricCard
          label="Healthy Features"
          value={healthy}
          context={`${rows.length} total features`}
          color={healthy === rows.length ? 'green' : 'default'}
          skeleton={isLoading}
        />
        <MetricCard
          label="Snapshot Coverage"
          value={snapshotCoverage}
          suffix="%"
          color={snapshotCoverage >= 80 ? 'green' : snapshotCoverage >= 50 ? 'amber' : 'red'}
          context={`${summary?.with_snapshot ?? 0} / ${summary?.total_picks ?? 0} picks`}
          skeleton={isLoading}
        />
        <MetricCard
          label="Missing / Partial"
          value={missing + partial}
          context={`${missing} critical · ${partial} partial`}
          color={missing > 0 ? 'red' : partial > 0 ? 'amber' : 'green'}
          skeleton={isLoading}
        />
      </Cols3>

      {/* Coverage chart */}
      <ChartContainer
        title="Feature Coverage"
        subtitle="% of picks where each feature had a recorded value"
        athenaContext="Which features are missing data and why?"
        badge={`${rows.length} features`}
        loading={isLoading}
        empty={rows.length === 0}
        emptyMessage="No feature health data — run diagnostics to populate"
      >
        <CoverageBarChart rows={rows} />
      </ChartContainer>

      {/* Variance chart + Athena side by side */}
      <Cols2>
        <ChartContainer
          title="Feature Variance"
          subtitle="Top 15 features by standard deviation (constants excluded)"
          loading={isLoading}
          empty={rows.length === 0}
        >
          <VarianceBarChart rows={rows} />
        </ChartContainer>

        <div>
          {constantCount > 0 && (
            <div className={styles.warningBanner}>
              <span>⚠</span>
              <span>
                <strong>{constantCount} constant feature{constantCount > 1 ? 's' : ''}</strong> detected —
                zero predictive signal, wasting model capacity. Drop them from the feature set.
              </span>
            </div>
          )}
          <AthenaSummary
            finding={`Feature pipeline is ${overallStatus === 'ok' ? 'healthy' : overallStatus === 'warn' ? '**partially degraded**' : '**critically degraded**'} with **${avgCoverage.toFixed(0)}% average coverage**. ${missing} features below 50% threshold. Snapshot logging captures only **${snapshotCoverage}%** of picks — black-box picks cannot be diagnosed.`}
            confidence={72}
            roiImpact="+0.8% ROI"
            experiment="Add snapshot logging to every pick write path"
          />
        </div>
      </Cols2>

      {/* Full stats table */}
      <ChartContainer
        title="Feature Statistics"
        subtitle="Coverage, mean, and variance for every feature in the pipeline"
        loading={isLoading}
        empty={rows.length === 0}
        minHeight={200}
      >
        <FeatureStatsTable rows={rows} />
      </ChartContainer>
    </SectionPage>
  );
}
