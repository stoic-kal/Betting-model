/**
 * TemporalPage — Time-Series Model Performance
 */

import { useMemo }                                                     from 'react';
import Plot                                                            from 'react-plotly.js';
import { useAthenaStore, selectTemporal, selectSummary, selectRecentPicks } from '@store/athenaStore';
import { useAthenaData }                                               from '@hooks/useAthenaData';
import { useChartTheme, mergeLayout }                                  from '@hooks/useChartTheme';
import { SectionPage, Cols2, Cols3 }                                   from '@components/SectionPage';
import { MetricCard }                                                  from '@components/MetricCard';
import { AthenaSummary }                                               from '@components/AthenaSummary';
import { ChartContainer }                                              from '@components/ChartContainer';
import { InsightCard }                                                 from '@components/InsightCard';
import { DriftIndicator }                                              from '@components/DriftIndicator';
import type { Insight }                                                from '@components/InsightCard';
import styles                                                          from './TemporalPage.module.css';

// ── Static insights ────────────────────────────────────────────────────────────

const TEMPORAL_INSIGHTS: Insight[] = [
  {
    text: '**Rolling win rate should converge toward your true edge** as sample size grows. Wild swings early are expected — stability after 50+ picks matters.',
    severity: 'info',
  },
  {
    text: '**A declining cumulative P&L that suddenly reverses** is often variance, not model improvement. Check if the reversal aligns with a strategy change.',
    severity: 'medium',
  },
  {
    text: '**Bet timing matters.** If early-season picks underperform late-season picks, you may be exploiting market inefficiencies that close as the season progresses.',
    severity: 'high',
  },
];

// ── Cumulative P&L Chart ──────────────────────────────────────────────────────

function CumPnlChart({ dates, cum_pnl }: { dates: string[]; cum_pnl: number[] }) {
  const { layout, config, colors } = useChartTheme();
  const last = cum_pnl[cum_pnl.length - 1] ?? 0;
  const lineColor = last >= 0 ? colors.green : colors.red;
  const fillColor = last >= 0 ? 'rgba(16,185,129,0.08)' : 'rgba(239,68,68,0.08)';

  return (
    <Plot
      data={[
        {
          type:      'scatter',
          mode:      'lines',
          x:         dates,
          y:         cum_pnl,
          fill:      'tozeroy',
          fillcolor: fillColor,
          line:      { color: 'transparent', width: 0 },
          showlegend: false,
          hoverinfo: 'skip' as const,
        },
        {
          type:      'scatter',
          mode:      'lines+markers',
          name:      'Cumulative P&L',
          x:         dates,
          y:         cum_pnl,
          line:      { color: lineColor, width: 2.5, shape: 'spline' as const },
          marker:    { color: lineColor, size: 5, opacity: 0.7 },
          hovertemplate: '<b>%{x}</b><br>Cum P&L: %{y:+.1f}u<extra></extra>',
        },
      ]}
      layout={mergeLayout(layout, {
        height: 280,
        xaxis: {
          ...layout.xaxis,
          type:   'date',
          title:  { text: 'Date', font: { color: '#6B7280', size: 10 } },
        },
        yaxis: {
          ...layout.yaxis,
          title:      { text: 'Units', font: { color: '#6B7280', size: 10 } },
          ticksuffix: 'u',
        },
        shapes: [{
          type: 'line',
          x0: dates[0] ?? '', x1: dates[dates.length - 1] ?? '',
          y0: 0, y1: 0,
          line: { color: 'rgba(255,255,255,0.15)', width: 1 },
        }],
        showlegend: false,
      })}
      config={config}
      style={{ width: '100%' }}
      useResizeHandler
    />
  );
}

// ── Rolling Win Rate Chart ────────────────────────────────────────────────────

function RollingWrChart({ dates, rolling_wr }: { dates: string[]; rolling_wr: number[] }) {
  const { layout, config, colors } = useChartTheme();

  return (
    <Plot
      data={[{
        type:      'scatter',
        mode:      'lines+markers',
        name:      'Rolling 10-pick WR',
        x:         dates,
        y:         rolling_wr,
        line:      { color: colors.purple, width: 2, shape: 'spline' as const },
        marker:    { color: colors.purple, size: 4, opacity: 0.6 },
        hovertemplate: '<b>%{x}</b><br>WR (10-pick): %{y:.1f}%<extra></extra>',
      }]}
      layout={mergeLayout(layout, {
        height: 240,
        xaxis: {
          ...layout.xaxis,
          type:  'date',
          title: { text: 'Date', font: { color: '#6B7280', size: 10 } },
        },
        yaxis: {
          ...layout.yaxis,
          title:      { text: 'Win Rate %', font: { color: '#6B7280', size: 10 } },
          ticksuffix: '%',
          range:      [20, 90],
        },
        shapes: [
          {
            type: 'line',
            x0: dates[0] ?? '', x1: dates[dates.length - 1] ?? '',
            y0: 52.4, y1: 52.4,
            line: { color: colors.amber, width: 1.5, dash: 'dot' },
          },
          {
            type: 'rect',
            x0: dates[0] ?? '', x1: dates[dates.length - 1] ?? '',
            y0: 48, y1: 57,
            fillcolor: 'rgba(245,158,11,0.04)',
            line: { width: 0 },
          },
        ],
        annotations: [{
          x: dates[Math.floor(dates.length / 2)] ?? '',
          y: 52.4,
          text: 'break-even zone',
          showarrow: false,
          font: { color: colors.amber, size: 9 },
          yshift: 10,
        }],
        showlegend: false,
      })}
      config={config}
      style={{ width: '100%' }}
      useResizeHandler
    />
  );
}

// ── Monthly P&L Chart ─────────────────────────────────────────────────────────

function MonthlyChart({ dates, cum_pnl }: { dates: string[]; cum_pnl: number[] }) {
  const { layout, config, colors } = useChartTheme();

  const monthly = useMemo(() => {
    const byMonth: Record<string, number[]> = {};
    dates.forEach((d, i) => {
      const m = d.slice(0, 7);
      if (!byMonth[m]) byMonth[m] = [];
      byMonth[m].push(i);
    });
    return Object.entries(byMonth).map(([month, indices]) => {
      const first = indices[0] ?? 0;
      const last  = indices[indices.length - 1] ?? 0;
      const gain  = (cum_pnl[last] ?? 0) - (first > 0 ? (cum_pnl[first - 1] ?? 0) : 0);
      return { month, gain };
    });
  }, [dates, cum_pnl]);

  return (
    <Plot
      data={[{
        type:  'bar',
        x:     monthly.map(m => m.month),
        y:     monthly.map(m => m.gain),
        marker: {
          color: monthly.map(m => m.gain >= 0 ? colors.green : colors.red),
          opacity: 0.85,
        },
        text:          monthly.map(m => `${m.gain > 0 ? '+' : ''}${m.gain.toFixed(1)}u`),
        textposition:  'outside' as const,
        textfont:      { color: '#6B7280', size: 10 },
        cliponaxis:    false,
        hovertemplate: '<b>%{x}</b><br>P&L: %{y:+.1f}u<extra></extra>',
      }]}
      layout={mergeLayout(layout, {
        height: 240,
        margin: { t: 24, b: 44, l: 52, r: 16 },
        xaxis:  { ...layout.xaxis, type: 'category', tickangle: -30 },
        yaxis: {
          ...layout.yaxis,
          title:      { text: 'Units', font: { color: '#6B7280', size: 10 } },
          ticksuffix: 'u',
        },
        shapes: [{
          type: 'line',
          x0: -0.5, x1: monthly.length - 0.5,
          y0: 0, y1: 0,
          line: { color: 'rgba(255,255,255,0.12)', width: 1 },
        }],
        showlegend: false,
      })}
      config={config}
      style={{ width: '100%' }}
      useResizeHandler
    />
  );
}

// ── Streak analysis ───────────────────────────────────────────────────────────

function computeStreaks(picks: Array<{ status: string }>) {
  let runWin = 0, runLoss = 0, bestWin = 0, worstLoss = 0;

  picks.forEach(p => {
    if (p.status === 'won') {
      runWin++;
      runLoss = 0;
      if (runWin  > bestWin)   bestWin  = runWin;
    } else if (p.status === 'lost') {
      runLoss++;
      runWin = 0;
      if (runLoss > worstLoss) worstLoss = runLoss;
    } else {
      runWin = 0; runLoss = 0;
    }
  });

  const last = picks[picks.length - 1];
  const currentStreak = last?.status === 'won' ? runWin : last?.status === 'lost' ? runLoss : 0;
  const currentType   = last?.status === 'won' ? 'W'    : last?.status === 'lost' ? 'L'    : '';

  return { currentStreak, currentType, bestWin, worstLoss };
}

// ── Page ───────────────────────────────────────────────────────────────────────

export default function TemporalPage() {
  const { isLoading } = useAthenaData();
  const temporal = useAthenaStore(selectTemporal);
  const summary  = useAthenaStore(selectSummary);
  const picks    = useAthenaStore(selectRecentPicks);

  const dates      = temporal?.dates      ?? [];
  const cum_pnl    = temporal?.cum_pnl    ?? [];
  const rolling_wr = temporal?.rolling_wr ?? [];

  const finalPnl  = cum_pnl.length  > 0 ? (cum_pnl[cum_pnl.length - 1] ?? 0)       : 0;
  const latestWr  = rolling_wr.length > 0 ? (rolling_wr[rolling_wr.length - 1] ?? 0) : 0;

  const { currentStreak, currentType, bestWin, worstLoss } = useMemo(
    () => computeStreaks(picks),
    [picks]
  );

  const trend = latestWr >= 52.4 ? 'up' : latestWr >= 45 ? 'neutral' : 'down';

  const dateRange = dates.length >= 2
    ? `${dates[0]} → ${dates[dates.length - 1]}`
    : summary?.date_min && summary?.date_max
      ? `${summary.date_min} → ${summary.date_max}`
      : 'No date range';

  return (
    <SectionPage
      icon="📅"
      title="Temporal Analysis"
      subtitle="Cumulative performance, trend stability, and pick timing"
      athenaQuery="Analyze my P&L trend and identify if my model performance is improving or declining"
    >
      {/* Summary cards */}
      <Cols3>
        <MetricCard
          label="Cumulative P&L"
          value={finalPnl}
          suffix="u"
          decimals={1}
          color={finalPnl >= 0 ? 'green' : 'red'}
          context={dateRange}
          skeleton={isLoading}
        />
        <MetricCard
          label="Latest Rolling WR"
          value={latestWr}
          suffix="%"
          decimals={1}
          color={trend === 'up' ? 'green' : trend === 'down' ? 'red' : 'amber'}
          context="10-pick rolling window"
          skeleton={isLoading}
        />
        <MetricCard
          label="Current Streak"
          value={currentStreak}
          suffix={currentType}
          decimals={0}
          color={currentType === 'W' ? 'green' : currentType === 'L' ? 'red' : 'muted'}
          context={`Best win: ${bestWin}W · Worst: ${worstLoss}L`}
          skeleton={isLoading}
        />
      </Cols3>

      {/* Drift indicators */}
      <div className={styles.driftRow}>
        <DriftIndicator
          value={finalPnl}
          unit=" units"
          label="Total P&L"
          decimals={1}
          positiveIsGood
        />
        <DriftIndicator
          value={latestWr - 52.4}
          unit="pp"
          label="vs Break-even"
          decimals={1}
          positiveIsGood
        />
        <DriftIndicator
          value={latestWr - (summary?.overall_wr ?? 50)}
          unit="pp"
          label="Recent vs Season WR"
          decimals={1}
          positiveIsGood
        />
      </div>

      {/* Cumulative P&L */}
      <ChartContainer
        title="Cumulative P&L"
        subtitle="Season bankroll trajectory in units (flat-betting 1 unit per pick)"
        athenaContext="Analyze my cumulative P&L trend and identify inflection points"
        loading={isLoading}
        empty={dates.length < 2}
        emptyMessage="Need at least 2 picks with dates for temporal analysis"
      >
        <CumPnlChart dates={dates} cum_pnl={cum_pnl} />
      </ChartContainer>

      {/* Rolling WR + Monthly */}
      <Cols2>
        <ChartContainer
          title="Rolling Win Rate (10-pick)"
          subtitle="Is recent performance converging or diverging from break-even?"
          loading={isLoading}
          empty={rolling_wr.length < 5}
        >
          <RollingWrChart dates={dates} rolling_wr={rolling_wr} />
        </ChartContainer>

        <ChartContainer
          title="Monthly P&L"
          subtitle="Which months contributed positive vs negative returns?"
          loading={isLoading}
          empty={dates.length < 2}
        >
          <MonthlyChart dates={dates} cum_pnl={cum_pnl} />
        </ChartContainer>
      </Cols2>

      {/* Insights + Athena */}
      <Cols2>
        <InsightCard title="Reading the Temporal Charts" insights={TEMPORAL_INSIGHTS} />
        <AthenaSummary
          finding={
            dates.length > 0
              ? `Over **${dates.length} picks** (${dateRange}): cumulative P&L is **${finalPnl >= 0 ? '+' : ''}${finalPnl.toFixed(1)} units**. Latest rolling WR is **${latestWr.toFixed(1)}%** (break-even: 52.4%). ${trend === 'up' ? 'Recent trend is **positive**.' : trend === 'down' ? 'Recent trend is **declining** — investigate recent picks.' : 'Performance is **flat** near break-even.'}`
              : 'No temporal data available. Run full diagnostics to generate time-series analysis.'
          }
          confidence={dates.length >= 20 ? 72 : 40}
          roiImpact="+0.3% ROI"
          experiment="Segment picks by month and test whether late-season bets outperform early-season"
        />
      </Cols2>
    </SectionPage>
  );
}
