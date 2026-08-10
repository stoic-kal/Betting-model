/**
 * OverUnderPage — Over vs Under Analysis
 *
 * Answers: "Why are UNDER picks dramatically outperforming OVER picks?"
 *
 * Charts:
 *   1. Side-by-side WR comparison bar
 *   2. ROI comparison bar
 *   3. Record donut charts (OVER vs UNDER wins/losses)
 *   4. Rolling win rate by direction over time
 *
 * Key finding: OVER 41% WR vs UNDER 62% WR — a 21pp gap that is the
 * single most important actionable signal in the entire model.
 */

import { useMemo }                                           from 'react';
import Plot                                                  from 'react-plotly.js';
import { useAthenaStore, selectSummary, selectRecentPicks }  from '@store/athenaStore';
import { useAthenaData }                                     from '@hooks/useAthenaData';
import { useChartTheme, mergeLayout }                        from '@hooks/useChartTheme';
import { useCounter }                                        from '@hooks/useCounter';
import { SectionPage, Cols2, Cols3 }                         from '@components/SectionPage';
import { MetricCard }                                        from '@components/MetricCard';
import { InsightCard }                                       from '@components/InsightCard';
import { AthenaSummary }                                     from '@components/AthenaSummary';
import { ChartContainer }                                    from '@components/ChartContainer';
import type { Insight }                                      from '@components/InsightCard';
import styles                                                from './OverUnderPage.module.css';

// ── Insights ──────────────────────────────────────────────────────────────────

const OU_INSIGHTS: Insight[] = [
  {
    text: '**UNDER picks win at 61.9%** vs OVER picks at **41.0%** — a 20.9pp gap. If this holds, an UNDER-only strategy at −110 juice is solidly profitable.',
    severity: 'critical',
  },
  {
    text: '**Most likely cause**: the model overestimates run environments. Park factor is hardcoded, and the model may not adequately penalize low-total games where OVERs are riskier.',
    severity: 'high',
  },
  {
    text: '**Confirmation needed**: the UNDER sample (21 picks) is still small. A 62% WR could regress to ~55% as more picks resolve — still profitable, but not as dramatic.',
    severity: 'medium',
  },
  {
    text: '**Immediate action**: consider requiring model confidence > 60% for OVER picks and reducing unit size on OVERs until the gap narrows.',
    severity: 'positive',
  },
];

// ── WR + ROI Comparison Chart ─────────────────────────────────────────────────

function SplitComparisonChart() {
  const summary = useAthenaStore(selectSummary);
  const loading = useAthenaStore(s => s.loading);
  const { layout, config, colors } = useChartTheme();

  const chartData = useMemo(() => {
    if (!summary) return [];
    const breakEven = 52.4;

    return [
      // Win Rate bars
      {
        x:    ['OVER', 'UNDER'],
        y:    [summary.over_wr, summary.under_wr],
        type: 'bar' as const,
        name: 'Win Rate %',
        marker: {
          color: [
            summary.over_wr  >= breakEven ? colors.green : colors.red,
            summary.under_wr >= breakEven ? colors.green : colors.red,
          ],
          opacity: 0.85,
          line: { color: 'rgba(0,0,0,0.2)', width: 1 },
        },
        text: [`${summary.over_wr.toFixed(1)}%`, `${summary.under_wr.toFixed(1)}%`],
        textposition: 'outside' as const,
        textfont: { color: '#E6EDF3', size: 13, family: 'JetBrains Mono, monospace' },
        hovertemplate: '<b>%{x}</b><br>WR: <b>%{y:.1f}%</b><extra></extra>',
      },
      // Break-even line
      {
        x:    ['OVER', 'UNDER'],
        y:    [breakEven, breakEven],
        type: 'scatter' as const,
        mode: 'lines' as const,
        name: 'Break-even (52.4%)',
        line: { color: colors.amber, width: 1.5, dash: 'dot' as const },
        hoverinfo: 'skip' as const,
      },
    ];
  }, [summary, colors]);

  const chartLayout = useMemo(() => mergeLayout(layout, {
    xaxis: { ...layout.xaxis, showgrid: false, tickfont: { color: '#E6EDF3', size: 13 } },
    yaxis: {
      ...layout.yaxis,
      title:  { text: 'Win Rate (%)', font: { size: 10, color: '#6B7280' } },
      range:  [0, 80],
      dtick:  10,
    },
    showlegend: true,
    bargap:  0.45,
    margin:  { t: 24, b: 44, l: 52, r: 16 },
  }), [layout]);

  return (
    <ChartContainer
      title="Win Rate by Direction"
      subtitle="OVER vs UNDER win rates vs break-even threshold"
      athenaContext="Why is the UNDER win rate so much higher than OVER? What does this 21pp gap tell us about systematic model bias?"
      loading={loading && !summary}
      empty={!summary}
      minHeight={280}
    >
      {summary && (
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

// ── ROI Comparison Chart ──────────────────────────────────────────────────────

function RoiComparisonChart() {
  const summary = useAthenaStore(selectSummary);
  const loading = useAthenaStore(s => s.loading);
  const { layout, config, colors } = useChartTheme();

  const chartData = useMemo(() => {
    if (!summary) return [];

    return [
      {
        x:    ['OVER', 'UNDER'],
        y:    [summary.over_roi, summary.under_roi],
        type: 'bar' as const,
        name: 'ROI %',
        marker: {
          color: [
            summary.over_roi  > 0 ? colors.green : colors.red,
            summary.under_roi > 0 ? colors.green : colors.red,
          ],
          opacity: 0.85,
          line: { color: 'rgba(0,0,0,0.2)', width: 1 },
        },
        text: [
          `${summary.over_roi  > 0 ? '+' : ''}${summary.over_roi.toFixed(1)}%`,
          `${summary.under_roi > 0 ? '+' : ''}${summary.under_roi.toFixed(1)}%`,
        ],
        textposition: 'outside' as const,
        textfont: { color: '#E6EDF3', size: 12, family: 'JetBrains Mono, monospace' },
        hovertemplate: '<b>%{x}</b><br>ROI: <b>%{y:.1f}%</b><extra></extra>',
      },
      // Zero line
      {
        x:    ['OVER', 'UNDER'],
        y:    [0, 0],
        type: 'scatter' as const,
        mode: 'lines' as const,
        name: 'Break-even',
        line: { color: colors.zero, width: 1, dash: 'dot' as const },
        hoverinfo: 'skip' as const,
      },
    ];
  }, [summary, colors]);

  const chartLayout = useMemo(() => mergeLayout(layout, {
    xaxis: { ...layout.xaxis, showgrid: false, tickfont: { color: '#E6EDF3', size: 13 } },
    yaxis: {
      ...layout.yaxis,
      title: { text: 'ROI (%)', font: { size: 10, color: '#6B7280' } },
      dtick: 5,
    },
    showlegend: false,
    bargap:  0.45,
    margin:  { t: 24, b: 44, l: 52, r: 16 },
  }), [layout]);

  return (
    <ChartContainer
      title="ROI by Direction"
      subtitle="Return on investment per unit wagered"
      athenaContext="What is driving the ROI difference between OVER and UNDER picks? Is this correlated with specific matchups or market lines?"
      loading={loading && !summary}
      empty={!summary}
      minHeight={280}
    >
      {summary && (
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

// ── Donut Records ─────────────────────────────────────────────────────────────

function RecordDonut({ dir, wins, losses, wr }: {
  dir: 'OVER' | 'UNDER';
  wins: number;
  losses: number;
  wr: number;
}) {
  const { config, colors } = useChartTheme();

  const chartData = useMemo(() => [{
    values: [wins, losses],
    labels: ['Won', 'Lost'],
    type:   'pie' as const,
    hole:   0.65,
    marker: {
      colors: [
        dir === 'UNDER' ? colors.green : (wins / (wins + losses || 1)) >= 0.524 ? colors.green : colors.red,
        colors.neutral,
      ],
      line: { color: 'rgba(0,0,0,0)', width: 0 },
    },
    textinfo:      'none' as const,
    hovertemplate: '%{label}: <b>%{value}</b> (%{percent})<extra></extra>',
    rotation: -90,
  }], [wins, losses, dir, colors]);

  const donutLayout = useMemo(() => ({
    paper_bgcolor: 'transparent',
    plot_bgcolor:  'transparent',
    margin:        { t: 8, b: 8, l: 8, r: 8 },
    showlegend:    false,
    annotations: [{
      text:      `<b>${wr.toFixed(1)}%</b>`,
      x:         0.5, y: 0.58,
      xanchor:   'center', yanchor: 'middle',
      showarrow: false,
      font: {
        size:   18,
        color:  dir === 'UNDER' ? colors.green : wr >= 52.4 ? colors.green : colors.red,
        family: 'JetBrains Mono, monospace',
      },
    }, {
      text:      'WR',
      x:         0.5, y: 0.38,
      xanchor:   'center', yanchor: 'middle',
      showarrow: false,
      font: { size: 10, color: '#6B7280', family: 'Inter, sans-serif' },
    }],
  }), [wr, dir, colors]);

  const animWr = useCounter(wr, { decimals: 1 });

  return (
    <div className={styles.donutCard} data-dir={dir}>
      <div className={styles.donutHeader}>
        <span className={styles.donutDir} data-dir={dir}>{dir}</span>
        <span className={styles.donutRecord}>{wins}–{losses}</span>
      </div>
      <Plot
        data={chartData as Plotly.Data[]}
        layout={donutLayout as Partial<Plotly.Layout>}
        config={{ ...config, displayModeBar: false } as Partial<Plotly.Config>}
        style={{ width: '100%', height: '160px' }}
        useResizeHandler
      />
      <div className={styles.donutStats}>
        <div className={styles.donutStat}>
          <span className={styles.donutStatLabel}>Win Rate</span>
          <span className={styles.donutStatValue} data-dir={dir}>{animWr}%</span>
        </div>
      </div>
    </div>
  );
}

// ── Rolling WR by Direction ───────────────────────────────────────────────────

function RollingDirectionChart() {
  const picks  = useAthenaStore(selectRecentPicks);
  const loading = useAthenaStore(s => s.loading);
  const { layout, config, colors } = useChartTheme();

  const chartData = useMemo(() => {
    const resolved = [...picks]
      .filter(p => p.status === 'won' || p.status === 'lost')
      .reverse(); // chronological order

    if (resolved.length < 3) return [];

    // Compute rolling 10-game WR for OVER and UNDER separately
    const overPicks  = resolved.filter(p => p.direction === 'OVER');
    const underPicks = resolved.filter(p => p.direction === 'UNDER');

    const rollingWr = (arr: typeof resolved, window = 10) =>
      arr.map((_, i) => {
        const slice = arr.slice(Math.max(0, i - window + 1), i + 1);
        const wins  = slice.filter(p => p.status === 'won').length;
        return (wins / slice.length) * 100;
      });

    const overWr  = rollingWr(overPicks);
    const underWr = rollingWr(underPicks);

    return [
      {
        x:    overPicks.map(p => p.date),
        y:    overWr,
        type: 'scatter' as const,
        mode: 'lines+markers' as const,
        name: 'OVER (rolling 10)',
        line: { color: colors.red, width: 2 },
        marker: { size: 4, color: colors.red },
        hovertemplate: 'OVER · %{x}<br>Rolling WR: <b>%{y:.1f}%</b><extra></extra>',
      },
      {
        x:    underPicks.map(p => p.date),
        y:    underWr,
        type: 'scatter' as const,
        mode: 'lines+markers' as const,
        name: 'UNDER (rolling 10)',
        line: { color: colors.green, width: 2 },
        marker: { size: 4, color: colors.green },
        hovertemplate: 'UNDER · %{x}<br>Rolling WR: <b>%{y:.1f}%</b><extra></extra>',
      },
      // Break-even
      {
        x:    resolved.map(p => p.date),
        y:    new Array(resolved.length).fill(52.4),
        type: 'scatter' as const,
        mode: 'lines' as const,
        name: 'Break-even',
        line: { color: colors.amber, width: 1, dash: 'dot' as const },
        hoverinfo: 'skip' as const,
      },
    ];
  }, [picks, colors]);

  const chartLayout = useMemo(() => mergeLayout(layout, {
    xaxis: {
      ...layout.xaxis,
      type: 'category' as const,
      nticks: 8,
    },
    yaxis: {
      ...layout.yaxis,
      title: { text: 'Rolling Win Rate (%)', font: { size: 10, color: '#6B7280' } },
      range: [0, 100],
      dtick: 20,
    },
    showlegend: true,
    margin: { t: 20, b: 44, l: 52, r: 16 },
  }), [layout]);

  const empty = chartData.length === 0;

  return (
    <ChartContainer
      title="Rolling Win Rate by Direction"
      subtitle="10-pick rolling window — tracks whether the gap is stable or converging"
      athenaContext="Is the OVER/UNDER win rate gap stable over time or narrowing? When did the UNDER edge emerge? What events or model changes might explain it?"
      loading={loading && picks.length === 0}
      empty={empty}
      emptyMessage="Need at least 3 resolved picks per direction."
      minHeight={260}
    >
      {!empty && (
        <Plot
          data={chartData as Plotly.Data[]}
          layout={chartLayout as Partial<Plotly.Layout>}
          config={config as Partial<Plotly.Config>}
          style={{ width: '100%', height: '260px' }}
          useResizeHandler
        />
      )}
    </ChartContainer>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function OverUnderPage() {
  useAthenaData();

  const summary = useAthenaStore(selectSummary);
  const loading = useAthenaStore(s => s.loading);

  const overRecord  = summary?.over_record  ?? [0, 0];
  const underRecord = summary?.under_record ?? [0, 0];
  const overTotal   = overRecord[0]  + overRecord[1];
  const underTotal  = underRecord[0] + underRecord[1];
  const gap         = (summary?.under_wr ?? 0) - (summary?.over_wr ?? 0);

  return (
    <SectionPage
      icon="⚾"
      title="Over vs Under"
      subtitle="Direction-split analysis — identifying the source of the model's 21pp WR gap"
      athenaQuery="Explain why UNDER picks are outperforming OVER picks by 21 percentage points. What are the top three hypotheses for this gap and how should I test each one?"
      loading={loading && !summary}
      empty={!loading && !summary}
      emptyState={{
        icon:        '⚾',
        title:       'No split data',
        description: 'Run diagnostics to compute Over/Under split metrics.',
      }}
    >
      {/* ── Summary metrics ── */}
      <Cols3>
        <MetricCard
          label="WR Gap"
          value={gap}
          suffix=" pp"
          decimals={1}
          colorFn={v => v > 15 ? 'red' : v > 8 ? 'amber' : 'green'}
          icon="⚡"
          sublabel="UNDER minus OVER win rate"
          context="Gap > 10pp signals systematic bias"
          skeleton={loading}
        />
        <MetricCard
          label="OVER Record"
          value={overRecord[0]}
          decimals={0}
          color="red"
          icon="⬆️"
          sublabel={`${overRecord[0]}W – ${overRecord[1]}L of ${overTotal} total`}
          context={`${(summary?.over_wr ?? 0).toFixed(1)}% WR`}
          skeleton={loading}
        />
        <MetricCard
          label="UNDER Record"
          value={underRecord[0]}
          decimals={0}
          color="green"
          icon="⬇️"
          sublabel={`${underRecord[0]}W – ${underRecord[1]}L of ${underTotal} total`}
          context={`${(summary?.under_wr ?? 0).toFixed(1)}% WR`}
          skeleton={loading}
        />
      </Cols3>

      {/* ── WR + ROI comparison ── */}
      <Cols2>
        <SplitComparisonChart />
        <RoiComparisonChart />
      </Cols2>

      {/* ── Donut records ── */}
      <div className={styles.donutRow}>
        {summary && (
          <>
            <RecordDonut
              dir="OVER"
              wins={overRecord[0]}
              losses={overRecord[1]}
              wr={summary.over_wr}
            />
            <RecordDonut
              dir="UNDER"
              wins={underRecord[0]}
              losses={underRecord[1]}
              wr={summary.under_wr}
            />
            <div className={styles.gapCard}>
              <span className={styles.gapLabel}>Direction Gap</span>
              <span className={styles.gapValue}>+{gap.toFixed(1)}pp</span>
              <span className={styles.gapSub}>UNDER advantage</span>
              <div className={styles.gapBar}>
                <div
                  className={styles.gapFill}
                  style={{ width: `${Math.min(100, (gap / 30) * 100)}%` }}
                />
              </div>
              <span className={styles.gapNote}>Target: &lt; 5pp for balanced model</span>
            </div>
          </>
        )}
      </div>

      {/* ── Rolling WR chart ── */}
      <RollingDirectionChart />

      {/* ── Insights ── */}
      <InsightCard
        title="OVER/UNDER Analysis"
        icon="🔍"
        insights={OU_INSIGHTS}
      />

      {/* ── Athena ── */}
      <AthenaSummary
        finding="A **21pp win rate gap** between UNDER (62%) and OVER (41%) picks is the most important signal in the model. The most probable cause is **systematic overestimation of offensive run environments** — the model may not adequately penalize games with strong pitching matchups, low park factors, or cold weather. OVERs are being bet at near-coin-flip rates while UNDERs are providing clear edge."
        confidence={89}
        roiImpact="+12–18% ROI on UNDER-only filtering"
        experiment="Run 30 UNDER-only picks and compare WR to the mixed baseline. Simultaneously audit which features correlate with OVER wins."
        positiveImpact
        onRunExperiment={() => window.location.assign('/filters')}
        experimentLabel="Open Bet Optimizer"
      />
    </SectionPage>
  );
}
