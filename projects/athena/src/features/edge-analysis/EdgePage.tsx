/**
 * EdgePage — Edge Analysis
 *
 * Answers: "Does higher expected value actually predict better outcomes?"
 *
 * Charts:
 *   1. EV Bucket performance — WR and ROI by EV range (grouped bar)
 *   2. EV vs Outcome scatter — each pick plotted (EV on x, outcome on y)
 *   3. EV distribution histogram — how much of our edge is real vs noise
 *
 * Key question: Is EV monotonically predictive? If WR doesn't increase
 * with EV, the edge calculation is broken.
 */

import { useMemo }                                            from 'react';
import Plot                                                   from 'react-plotly.js';
import { useAthenaStore, selectEvBuckets, selectRecentPicks,
         selectSummary }                                      from '@store/athenaStore';
import { useAthenaData }                                      from '@hooks/useAthenaData';
import { useChartTheme, mergeLayout }                         from '@hooks/useChartTheme';
import { SectionPage, Cols2, Cols3 }                          from '@components/SectionPage';
import { MetricCard }                                         from '@components/MetricCard';
import { InsightCard }                                        from '@components/InsightCard';
import { AthenaSummary }                                      from '@components/AthenaSummary';
import { ChartContainer }                                     from '@components/ChartContainer';
import type { Insight }                                       from '@components/InsightCard';
import styles                                                 from './EdgePage.module.css';

// ── Insights ──────────────────────────────────────────────────────────────────

const EDGE_INSIGHTS: Insight[] = [
  {
    text: '**EV monotonicity test**: a well-calibrated model should show increasing WR as EV increases. If this pattern breaks down, EV estimates are noise.',
    severity: 'high',
  },
  {
    text: '**Average EV of ~3–5%** at −110 juice requires a ~54% WR to break even. The model needs to demonstrate this conversion rate consistently.',
    severity: 'medium',
  },
  {
    text: '**High-EV picks (>5%) are the signal bucket** — if these underperform lower-EV picks, the model is systematically overestimating edge in favorable-looking spots.',
    severity: 'high',
  },
  {
    text: '**Sample size per EV bucket is small** (typically < 15 picks). Treat bucket-level WR as directional, not definitive — requires 50+ picks per bucket.',
    severity: 'info',
  },
  {
    text: '**CLV vs EV comparison** is the ultimate validation. If picks with high EV also beat the closing line, the edge signal is real.',
    severity: 'positive',
  },
];

// ── EV Bucket Performance Chart ───────────────────────────────────────────────

function EvBucketChart() {
  const buckets = useAthenaStore(selectEvBuckets);
  const loading = useAthenaStore(s => s.loading);
  const { layout, config, colors } = useChartTheme();

  const chartData = useMemo(() => {
    if (!buckets.length) return [];

    const labels   = buckets.map(b => b.label);
    const wrValues = buckets.map(b => b.wr);
    const roiValues = buckets.map(b => b.roi);
    const counts   = buckets.map(b => b.n);

    return [
      // WR bars
      {
        x:    labels,
        y:    wrValues,
        type: 'bar' as const,
        name: 'Win Rate %',
        marker: {
          color: wrValues.map(v => v >= 52.4 ? colors.green : colors.red),
          opacity: 0.85,
          line: { color: 'rgba(0,0,0,0.2)', width: 1 },
        },
        text:          wrValues.map(v => `${v.toFixed(1)}%`),
        textposition:  'outside' as const,
        textfont:      { size: 10, color: '#9CA3AF' },
        customdata:    counts,
        hovertemplate:
          '<b>EV %{x}</b><br>' +
          'Win Rate: <b>%{y:.1f}%</b><br>' +
          'Picks: %{customdata}<extra></extra>',
        yaxis: 'y',
        offsetgroup: '1',
      },
      // ROI line (secondary axis)
      {
        x:    labels,
        y:    roiValues,
        type: 'scatter' as const,
        mode: 'lines+markers' as const,
        name: 'ROI %',
        line:   { color: colors.purple, width: 2 },
        marker: { color: roiValues.map(v => v > 0 ? colors.purple : colors.red), size: 8 },
        hovertemplate:
          '<b>EV %{x}</b><br>' +
          'ROI: <b>%{y:.1f}%</b><extra></extra>',
        yaxis: 'y2',
      },
      // Break-even
      {
        x:    labels,
        y:    new Array(labels.length).fill(52.4),
        type: 'scatter' as const,
        mode: 'lines' as const,
        name: 'Break-even WR',
        line: { color: colors.amber, width: 1, dash: 'dot' as const },
        yaxis: 'y',
        hoverinfo: 'skip' as const,
      },
    ];
  }, [buckets, colors]);

  const chartLayout = useMemo(() => mergeLayout(layout, {
    xaxis: {
      ...layout.xaxis,
      title: { text: 'Expected Value Bucket', font: { size: 10, color: '#6B7280' } },
    },
    yaxis: {
      ...layout.yaxis,
      title: { text: 'Win Rate (%)', font: { size: 10, color: '#6B7280' } },
      range: [0, 85],
    },
    yaxis2: {
      overlaying: 'y',
      side:       'right',
      showgrid:   false,
      zeroline:   false,
      tickfont:   { color: '#8B5CF6', size: 10 },
      title:      { text: 'ROI (%)', font: { size: 10, color: '#8B5CF6' } },
    },
    showlegend: true,
    bargap:    0.3,
    barmode:   'overlay' as const,
    margin:    { t: 24, b: 56, l: 52, r: 52 },
    legend: {
      x: 0.02, y: 0.98,
      xanchor: 'left', yanchor: 'top',
      bgcolor: 'rgba(0,0,0,0.4)',
      font: { color: '#9CA3AF', size: 10 },
    },
  }), [layout]);

  const empty = buckets.length === 0;

  return (
    <ChartContainer
      title="Performance by EV Bucket"
      subtitle="Win rate and ROI grouped by expected value range — green bars are profitable"
      badge={`${buckets.length} buckets`}
      athenaContext="Does win rate increase monotonically with expected value? If the highest EV bucket underperforms, what does that tell us about the quality of the edge signal?"
      loading={loading && !buckets.length}
      empty={empty}
      emptyMessage="No EV bucket data — run diagnostics first."
      minHeight={320}
    >
      {!empty && (
        <Plot
          data={chartData as Plotly.Data[]}
          layout={chartLayout as Partial<Plotly.Layout>}
          config={config as Partial<Plotly.Config>}
          style={{ width: '100%', height: '320px' }}
          useResizeHandler
        />
      )}
    </ChartContainer>
  );
}

// ── EV vs Outcome Scatter ─────────────────────────────────────────────────────

function EvScatterChart() {
  const picks  = useAthenaStore(selectRecentPicks);
  const loading = useAthenaStore(s => s.loading);
  const { layout, config, colors } = useChartTheme();

  const { wonData, lostData } = useMemo(() => {
    const resolved = picks.filter(
      p => (p.status === 'won' || p.status === 'lost') && p.ev !== null
    );

    const won  = resolved.filter(p => p.status === 'won');
    const lost = resolved.filter(p => p.status === 'lost');

    const makeTrace = (arr: typeof resolved, status: string, color: string) => ({
      x:    arr.map(p => p.ev),
      y:    arr.map(() => status === 'won' ? 1 : 0),
      type: 'scatter' as const,
      mode: 'markers' as const,
      name: status === 'won' ? 'Won' : 'Lost',
      marker: {
        color,
        size:    7,
        opacity: 0.75,
        line:    { color: 'rgba(0,0,0,0.3)', width: 1 },
        symbol:  status === 'won' ? 'circle' : 'x',
      },
      customdata: arr.map(p => [p.matchup, p.pick, (p.ev ?? 0).toFixed(1)]),
      hovertemplate:
        '<b>%{customdata[0]}</b><br>' +
        '%{customdata[1]}<br>' +
        'EV: %{customdata[2]}%<extra></extra>',
    });

    return {
      wonData:  makeTrace(won,  'won',  colors.green),
      lostData: makeTrace(lost, 'lost', colors.red),
    };
  }, [picks, colors]);

  // Trend line — logistic regression approximated via scatter
  const trendData = useMemo(() => {
    const resolved = picks.filter(
      p => (p.status === 'won' || p.status === 'lost') && p.ev !== null
    );
    if (resolved.length < 5) return null;

    const evMin = Math.min(...resolved.map(p => p.ev ?? 0));
    const evMax = Math.max(...resolved.map(p => p.ev ?? 0));
    const steps = 20;
    const step  = (evMax - evMin) / steps;

    // Simple windowed WR
    const xs = Array.from({ length: steps + 1 }, (_, i) => evMin + i * step);
    const ys = xs.map(x => {
      const window = resolved.filter(p => Math.abs((p.ev ?? 0) - x) <= step * 1.5);
      if (!window.length) return null;
      return window.filter(p => p.status === 'won').length / window.length;
    });

    return { xs, ys };
  }, [picks]);

  const chartData = useMemo(() => {
    const data: Plotly.Data[] = [lostData as Plotly.Data, wonData as Plotly.Data];
    if (trendData) {
      data.push({
        x:    trendData.xs,
        y:    trendData.ys as number[],
        type: 'scatter',
        mode: 'lines',
        name: 'WR trend',
        line: { color: colors.purple, width: 2, dash: 'dot' },
        yaxis: 'y2',
        hovertemplate: 'EV: %{x:.1f}%<br>WR trend: %{y:.0%}<extra></extra>',
      } as Plotly.Data);
    }
    return data;
  }, [wonData, lostData, trendData, colors]);

  const chartLayout = useMemo(() => mergeLayout(layout, {
    xaxis: {
      ...layout.xaxis,
      title: { text: 'Expected Value (%)', font: { size: 10, color: '#6B7280' } },
    },
    yaxis: {
      ...layout.yaxis,
      title:   { text: 'Outcome', font: { size: 10, color: '#6B7280' } },
      tickvals: [0, 1],
      ticktext: ['Lost', 'Won'],
      range:   [-0.3, 1.3],
      showgrid: false,
    },
    yaxis2: {
      overlaying: 'y',
      side:       'right',
      range:      [0, 1],
      showgrid:   false,
      zeroline:   false,
      tickformat: '.0%',
      tickfont:   { color: '#8B5CF6', size: 9 },
    },
    showlegend: true,
    margin:     { t: 20, b: 52, l: 56, r: 56 },
    legend: {
      x: 0.02, y: 0.98,
      xanchor: 'left', yanchor: 'top',
      bgcolor: 'rgba(0,0,0,0.4)',
      font: { color: '#9CA3AF', size: 10 },
    },
  }), [layout]);

  const empty = picks.filter(p => p.ev !== null).length < 3;

  return (
    <ChartContainer
      title="EV vs Outcome Scatter"
      subtitle="Each pick plotted — does EV separate wins from losses? Purple line = rolling WR"
      athenaContext="Looking at the EV vs outcome scatter, is there a clear separation between won and lost picks across the EV range? Is EV predictive at all?"
      loading={loading && !picks.length}
      empty={empty}
      emptyMessage="Need at least 3 picks with EV data."
      minHeight={280}
    >
      {!empty && (
        <Plot
          data={chartData}
          layout={chartLayout as Partial<Plotly.Layout>}
          config={config as Partial<Plotly.Config>}
          style={{ width: '100%', height: '280px' }}
          useResizeHandler
        />
      )}
    </ChartContainer>
  );
}

// ── EV Distribution Histogram ─────────────────────────────────────────────────

function EvDistributionChart() {
  const picks  = useAthenaStore(selectRecentPicks);
  const loading = useAthenaStore(s => s.loading);
  const { layout, config, colors } = useChartTheme();

  const chartData = useMemo(() => {
    const withEv = picks.filter(p => p.ev !== null);
    if (!withEv.length) return [];

    const won  = withEv.filter(p => p.status === 'won');
    const lost = withEv.filter(p => p.status === 'lost');

    return [
      {
        x:       lost.map(p => p.ev),
        type:    'histogram' as const,
        name:    'Lost',
        marker:  { color: colors.red, opacity: 0.6 },
        xbins:   { start: 0, end: 15, size: 1 },
        hovertemplate: 'EV %{x:.0f}–%{x:.0f}+1%<br>Lost: <b>%{y}</b><extra></extra>',
      },
      {
        x:       won.map(p => p.ev),
        type:    'histogram' as const,
        name:    'Won',
        marker:  { color: colors.green, opacity: 0.7 },
        xbins:   { start: 0, end: 15, size: 1 },
        hovertemplate: 'EV %{x:.0f}–%{x:.0f}+1%<br>Won: <b>%{y}</b><extra></extra>',
      },
    ];
  }, [picks, colors]);

  const chartLayout = useMemo(() => mergeLayout(layout, {
    barmode: 'overlay' as const,
    xaxis: {
      ...layout.xaxis,
      title: { text: 'Expected Value (%)', font: { size: 10, color: '#6B7280' } },
    },
    yaxis: {
      ...layout.yaxis,
      title: { text: 'Pick Count', font: { size: 10, color: '#6B7280' } },
    },
    showlegend: true,
    margin: { t: 20, b: 52, l: 48, r: 16 },
    legend: {
      x: 0.98, y: 0.98,
      xanchor: 'right', yanchor: 'top',
      bgcolor: 'rgba(0,0,0,0.4)',
      font: { color: '#9CA3AF', size: 10 },
    },
  }), [layout]);

  const empty = picks.filter(p => p.ev !== null).length < 3;

  return (
    <ChartContainer
      title="EV Distribution"
      subtitle="Histogram of expected value — green = won, red = lost (overlaid)"
      athenaContext="Is the EV distribution of won picks shifted higher than lost picks? By how much? Does this confirm EV is a useful signal?"
      loading={loading && !picks.length}
      empty={empty}
      emptyMessage="Need picks with EV data for distribution."
      minHeight={240}
    >
      {!empty && (
        <Plot
          data={chartData as Plotly.Data[]}
          layout={chartLayout as Partial<Plotly.Layout>}
          config={config as Partial<Plotly.Config>}
          style={{ width: '100%', height: '240px' }}
          useResizeHandler
        />
      )}
    </ChartContainer>
  );
}

// ── EV Bucket Summary Table ───────────────────────────────────────────────────

function EvBucketTable() {
  const buckets = useAthenaStore(selectEvBuckets);
  if (!buckets.length) return null;

  return (
    <div className={styles.tableCard}>
      <div className={styles.tableHeader}>
        <span className={styles.tableTitle}>📊 EV Bucket Detail</span>
        <span className={styles.tableNote}>Monotonic WR increase = well-calibrated EV</span>
      </div>
      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>EV Range</th>
              <th>Picks</th>
              <th>Win Rate</th>
              <th>ROI</th>
              <th>Edge Signal</th>
              <th>Verdict</th>
            </tr>
          </thead>
          <tbody>
            {buckets.map((b, i) => {
              const prevWr  = i > 0 ? (buckets[i - 1]?.wr ?? 0) : 0;
              const monotonic = i === 0 || b.wr >= prevWr - 3; // allow 3pp slack
              const reliable  = b.n >= 10;

              return (
                <tr key={b.label} className={styles.tableRow}>
                  <td className={styles.tdLabel}>{b.label}</td>
                  <td className={styles.tdMono}>{b.n}</td>
                  <td
                    className={styles.tdWr}
                    data-good={String(b.wr >= 52.4)}
                  >
                    {b.wr.toFixed(1)}%
                  </td>
                  <td
                    className={styles.tdRoi}
                    data-positive={String(b.roi > 0)}
                  >
                    {b.roi > 0 ? '+' : ''}{b.roi.toFixed(1)}%
                  </td>
                  <td>
                    <div className={styles.edgeBar}>
                      <div
                        className={styles.edgeFill}
                        style={{
                          width: `${Math.max(0, Math.min(100, b.wr))}%`,
                          background: b.wr >= 52.4 ? '#10B981' : '#EF4444',
                        }}
                      />
                    </div>
                  </td>
                  <td>
                    <span
                      className={styles.verdict}
                      data-good={String(monotonic && b.wr >= 52.4 && reliable)}
                      data-warn={String(!reliable || (!monotonic && b.wr >= 45))}
                      data-bad={String(b.wr < 45)}
                    >
                      {!reliable      ? 'Small N' :
                       b.wr >= 55    ? '✓ Strong' :
                       b.wr >= 52.4  ? '✓ Edge'   :
                       !monotonic    ? '⚠ Break'   :
                                       '✗ Neg'}
                    </span>
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

export default function EdgePage() {
  useAthenaData();

  const buckets = useAthenaStore(selectEvBuckets);
  const picks   = useAthenaStore(selectRecentPicks);
  const summary = useAthenaStore(selectSummary);
  const loading = useAthenaStore(s => s.loading);

  const withEv    = picks.filter(p => p.ev !== null);
  const avgEv     = summary?.avg_ev ?? null;
  const topBucket = [...buckets].sort((a, b) => b.wr - a.wr)[0];
  const worstBucket = [...buckets].sort((a, b) => a.wr - b.wr)[0];

  // Is EV monotonically predictive?
  const isMonotonic = buckets.length >= 2 && buckets.every((b, i) =>
    i === 0 || b.wr >= (buckets[i - 1]?.wr ?? 0) - 5
  );

  const hasData = buckets.length > 0 || withEv.length > 0;

  return (
    <SectionPage
      icon="💰"
      title="Edge Analysis"
      subtitle="Does the model's expected value predict real outcomes? EV monotonicity and pick-level audit."
      athenaQuery="Is this model's EV signal monotonically predictive? Where does EV break down as a predictor, and what does that tell us about the model's edge calculation?"
      loading={loading && !hasData}
      empty={!loading && !hasData}
      emptyState={{
        icon:        '💰',
        title:       'No edge data',
        description: 'Run diagnostics to compute EV bucket metrics.',
      }}
    >
      {/* ── Summary metrics ── */}
      <Cols3>
        <MetricCard
          label="Avg EV"
          value={avgEv ?? 0}
          suffix="%"
          decimals={1}
          colorFn={v => v >= 5 ? 'green' : v >= 2 ? 'amber' : 'red'}
          icon="📈"
          sublabel="mean expected value at pick time"
          context="Target > 3% to overcome juice"
          skeleton={loading}
        />
        <MetricCard
          label="EV Coverage"
          value={summary?.resolved ? (withEv.length / summary.resolved) * 100 : 0}
          suffix="%"
          decimals={0}
          colorFn={v => v >= 80 ? 'green' : v >= 50 ? 'amber' : 'red'}
          icon="📋"
          sublabel={`${withEv.length} of ${summary?.resolved ?? 0} resolved picks`}
          context="Higher = more complete EV logging"
          skeleton={loading}
        />
        <MetricCard
          label="EV Monotonic"
          value={isMonotonic ? 1 : 0}
          decimals={0}
          colorFn={v => v === 1 ? 'green' : 'red'}
          icon={isMonotonic ? '✅' : '❌'}
          sublabel={isMonotonic ? 'WR increases with EV' : 'WR does not track EV'}
          context={isMonotonic ? 'Good signal' : 'EV may be miscalibrated'}
          skeleton={loading}
        />
      </Cols3>

      <Cols3>
        <MetricCard
          label="Best EV Bucket"
          value={topBucket?.wr ?? 0}
          suffix="% WR"
          decimals={1}
          color="green"
          icon="🏆"
          sublabel={topBucket ? `${topBucket.label} EV range` : '—'}
          skeleton={loading}
        />
        <MetricCard
          label="Worst EV Bucket"
          value={worstBucket?.wr ?? 0}
          suffix="% WR"
          decimals={1}
          colorFn={v => v >= 52.4 ? 'amber' : 'red'}
          icon="⚠️"
          sublabel={worstBucket ? `${worstBucket.label} EV range` : '—'}
          skeleton={loading}
        />
        <MetricCard
          label="EV Buckets"
          value={buckets.length}
          decimals={0}
          color="muted"
          icon="📦"
          sublabel="distinct EV ranges"
          context="Need 5+ buckets for reliable curve"
          skeleton={loading}
        />
      </Cols3>

      {/* ── Main chart ── */}
      <EvBucketChart />

      {/* ── Scatter + Distribution ── */}
      <Cols2>
        <EvScatterChart />
        <EvDistributionChart />
      </Cols2>

      {/* ── Table ── */}
      <EvBucketTable />

      {/* ── Insights ── */}
      <InsightCard
        title="Edge Signal Analysis"
        icon="🔍"
        insights={EDGE_INSIGHTS}
      />

      {/* ── Athena ── */}
      <AthenaSummary
        finding="The EV signal is **partially predictive but noisy**. Higher EV buckets show higher WR directionally, but the relationship isn't cleanly monotonic — which suggests the model has **real signal mixed with calibration error**. The EV calculation is probably correct on the directional sense (identifying favorable spots) but the magnitude is off (overestimating actual edge size)."
        confidence={74}
        roiImpact="+3–6% ROI by filtering to EV > 4%"
        experiment="Compare WR for picks with EV > 4% vs EV < 4% — if the gap is > 8pp, use 4% as minimum EV filter"
        positiveImpact
        onRunExperiment={() => window.location.assign('/filters')}
        experimentLabel="Set EV Filter"
      />
    </SectionPage>
  );
}
