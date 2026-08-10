/**
 * ClvPage — Closing Line Value Analysis
 *
 * CLV measures whether you're beating the market's final line.
 * Positive CLV is the strongest signal of long-run edge.
 */

import { useMemo }                                                  from 'react';
import Plot                                                         from 'react-plotly.js';
import { useAthenaStore, selectSummary, selectRecentPicks }        from '@store/athenaStore';
import { useAthenaData }                                            from '@hooks/useAthenaData';
import { useCounter }                                               from '@hooks/useCounter';
import { useChartTheme, mergeLayout }                               from '@hooks/useChartTheme';
import { SectionPage, Cols2, Cols3 }                               from '@components/SectionPage';
import { MetricCard }                                               from '@components/MetricCard';
import { AthenaSummary }                                            from '@components/AthenaSummary';
import { ChartContainer }                                           from '@components/ChartContainer';
import { InsightCard }                                              from '@components/InsightCard';
import { StatusBadge }                                              from '@components/StatusBadge';
import type { Insight }                                             from '@components/InsightCard';
import styles                                                       from './ClvPage.module.css';

// ── Types ──────────────────────────────────────────────────────────────────────

interface Pick {
  ev:        number | null;
  clv:       number | null;
  direction: string;
  status:    string;
  matchup:   string;
}

// ── Static insights ────────────────────────────────────────────────────────────

const CLV_INSIGHTS: Insight[] = [
  {
    text: '**Positive CLV is the #1 leading indicator of long-run edge.** A model can have negative WR short-term and still be +EV if consistently beating closing lines.',
    severity: 'positive',
  },
  {
    text: '**Beat rate > 55% with n≥30** is the threshold to trust CLV as a signal. Below that, variance dominates.',
    severity: 'info',
  },
  {
    text: '**CLV requires closing line data** — picks without it are blind spots. Add a CLV capture step to every graded pick.',
    severity: 'medium',
  },
];

// ── CLV Scatter Chart ──────────────────────────────────────────────────────────

function ClvScatterChart({ picks }: { picks: Pick[] }) {
  const { layout, config, colors } = useChartTheme();

  const withData = picks.filter(p => p.ev !== null && p.clv !== null);
  const over  = withData.filter(p => p.direction === 'OVER');
  const under = withData.filter(p => p.direction === 'UNDER');

  return (
    <Plot
      data={[
        {
          type: 'scatter',
          mode: 'markers',
          name: 'OVER',
          x:    over.map(p => p.ev),
          y:    over.map(p => p.clv),
          marker: { color: colors.over, size: 8, opacity: 0.75, symbol: 'circle' },
          hovertemplate: '<b>OVER</b><br>EV: %{x:.1f}%<br>CLV: %{y:.1f}pp<extra></extra>',
        },
        {
          type: 'scatter',
          mode: 'markers',
          name: 'UNDER',
          x:    under.map(p => p.ev),
          y:    under.map(p => p.clv),
          marker: { color: colors.under, size: 8, opacity: 0.75, symbol: 'diamond' },
          hovertemplate: '<b>UNDER</b><br>EV: %{x:.1f}%<br>CLV: %{y:.1f}pp<extra></extra>',
        },
        {
          type: 'scatter',
          mode: 'lines',
          name: 'CLV = 0',
          x:    [-20, 20],
          y:    [0, 0],
          line: { color: colors.zero, width: 1, dash: 'dot' },
          showlegend: false,
          hoverinfo: 'skip' as const,
        },
      ]}
      layout={mergeLayout(layout, {
        height: 320,
        xaxis: {
          ...layout.xaxis,
          title:      { text: 'Expected Value (%)', font: { color: '#6B7280', size: 10 } },
          ticksuffix: '%',
        },
        yaxis: {
          ...layout.yaxis,
          title:      { text: 'CLV (pp)', font: { color: '#6B7280', size: 10 } },
          ticksuffix: 'pp',
        },
        legend: { x: 0.02, y: 0.98, xanchor: 'left', yanchor: 'top', bgcolor: 'rgba(0,0,0,0)', font: { color: '#9CA3AF', size: 10 }, orientation: 'v' as const },
      })}
      config={config}
      style={{ width: '100%' }}
      useResizeHandler
    />
  );
}

// ── CLV Distribution ──────────────────────────────────────────────────────────

function ClvDistChart({ picks }: { picks: Pick[] }) {
  const { layout, config, colors } = useChartTheme();

  const clvValues = picks.filter(p => p.clv !== null).map(p => p.clv as number);

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const histData: any[] = [{
    type:          'histogram',
    x:             clvValues,
    nbinsx:        12,
    marker: {
      color:   colors.cyan,
      opacity: 0.75,
      line:    { color: 'rgba(6,182,212,0.30)', width: 1 },
    },
    name:          'CLV distribution',
    hovertemplate: 'CLV: %{x:.1f}pp<br>Count: %{y}<extra></extra>',
  }];

  return (
    <Plot
      data={histData}
      layout={mergeLayout(layout, {
        height: 240,
        margin: { t: 12, b: 44, l: 44, r: 16 },
        xaxis: {
          ...layout.xaxis,
          title:      { text: 'CLV (pp)', font: { color: '#6B7280', size: 10 } },
          ticksuffix: 'pp',
        },
        yaxis: {
          ...layout.yaxis,
          title: { text: 'Count', font: { color: '#6B7280', size: 10 } },
        },
        shapes: [{
          type: 'line',
          x0: 0, x1: 0, y0: 0, y1: 1,
          yref: 'paper',
          line: { color: colors.amber, width: 1.5, dash: 'dot' },
        }],
        showlegend: false,
      })}
      config={config}
      style={{ width: '100%' }}
      useResizeHandler
    />
  );
}

// ── CLV by Direction ──────────────────────────────────────────────────────────

function ClvByDirection({ picks }: { picks: Pick[] }) {
  const { layout, config, colors } = useChartTheme();

  const directions = ['OVER', 'UNDER'];
  const avgByDir = directions.map(d => {
    const group = picks.filter(p => p.direction === d && p.clv !== null);
    if (!group.length) return 0;
    return group.reduce((s, p) => s + (p.clv as number), 0) / group.length;
  });
  const countByDir = directions.map(d =>
    picks.filter(p => p.direction === d && p.clv !== null).length
  );

  return (
    <Plot
      data={[{
        type:  'bar',
        x:     directions,
        y:     avgByDir,
        text:  avgByDir.map((v, i) => `${v > 0 ? '+' : ''}${v.toFixed(2)}pp\nn=${countByDir[i]}`),
        textposition: 'outside' as const,
        textfont: { color: '#9CA3AF', size: 10 },
        marker: {
          color:   directions.map((_, i) => (avgByDir[i] ?? 0) >= 0 ? colors.green : colors.red),
          opacity: 0.85,
          line:    { color: 'rgba(255,255,255,0.08)', width: 1 },
        },
        hovertemplate: '<b>%{x}</b><br>Avg CLV: %{y:.2f}pp<extra></extra>',
      }]}
      layout={mergeLayout(layout, {
        height: 240,
        margin: { t: 32, b: 44, l: 52, r: 16 },
        xaxis: { ...layout.xaxis, showgrid: false },
        yaxis: {
          ...layout.yaxis,
          title:      { text: 'Avg CLV (pp)', font: { color: '#6B7280', size: 10 } },
          ticksuffix: 'pp',
        },
        shapes: [{
          type: 'line',
          x0: -0.5, x1: 1.5, y0: 0, y1: 0,
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

// ── Picks Table ────────────────────────────────────────────────────────────────

function ClvPicksTable({ picks }: { picks: Pick[] }) {
  const withClv = useMemo(
    () => picks.filter((p): p is Pick & { clv: number } => p.clv !== null)
              .sort((a, b) => (b.clv as number) - (a.clv as number)),
    [picks]
  );

  if (!withClv.length) {
    return (
      <div className={styles.empty}>
        No picks with CLV data. Add closing line capture to the grading step.
      </div>
    );
  }

  return (
    <div className={styles.tableWrap}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th>Matchup</th>
            <th className={styles.center}>Dir</th>
            <th className={styles.right}>EV</th>
            <th className={styles.right}>CLV</th>
            <th className={styles.center}>Beat Line?</th>
          </tr>
        </thead>
        <tbody>
          {withClv.map((p, i) => {
            const beat = (p.clv as number) > 0;
            return (
              <tr key={i} className={styles.row}>
                <td className={styles.matchup}>{p.matchup}</td>
                <td className={styles.center}>
                  <span className={p.direction === 'OVER' ? styles.over : styles.under}>
                    {p.direction}
                  </span>
                </td>
                <td className={`${styles.right} ${styles.mono}`}>
                  {p.ev !== null ? `${p.ev > 0 ? '+' : ''}${p.ev.toFixed(1)}%` : '—'}
                </td>
                <td className={`${styles.right} ${styles.mono} ${beat ? styles.pos : styles.neg}`}>
                  {beat ? '+' : ''}{(p.clv as number).toFixed(2)}pp
                </td>
                <td className={styles.center}>
                  <StatusBadge
                    status={beat ? 'ok' : 'error'}
                    label={beat ? '✓ Yes' : '✗ No'}
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

// ── Page ───────────────────────────────────────────────────────────────────────

export default function ClvPage() {
  const { isLoading } = useAthenaData();
  const summary = useAthenaStore(selectSummary);
  const picks   = useAthenaStore(selectRecentPicks) as Pick[];

  const beatStr   = useCounter(summary?.beat_close ?? 0, { decimals: 1 });
  const avgClv    = summary?.avg_clv ?? 0;
  const beatClose = summary?.beat_close ?? 0;
  const clvPicks  = summary?.clv_picks ?? 0;

  return (
    <SectionPage
      icon="📊"
      title="CLV Analysis"
      subtitle={`Closing Line Value — ${avgClv >= 0 ? '+' : ''}${avgClv.toFixed(2)}pp avg · ${beatClose.toFixed(1)}% beat rate`}
      athenaQuery="Analyze my CLV data and explain whether my model has genuine market edge"
    >
      {/* Summary cards */}
      <Cols3>
        <MetricCard
          label="Avg CLV"
          value={avgClv}
          suffix="pp"
          decimals={2}
          color={avgClv > 0 ? 'green' : 'red'}
          context="Avg percentage points vs closing line"
          skeleton={isLoading}
        />
        <MetricCard
          label="Beat Rate"
          value={beatClose}
          suffix="%"
          decimals={1}
          color={beatClose > 52 ? 'green' : beatClose > 48 ? 'amber' : 'red'}
          context={`${clvPicks} picks with line data`}
          skeleton={isLoading}
        />
        <MetricCard
          label="CLV Coverage"
          value={clvPicks}
          decimals={0}
          context={`${summary ? ((clvPicks / (summary.total_picks || 1)) * 100).toFixed(0) : 0}% of all picks`}
          color={clvPicks > 20 ? 'default' : 'amber'}
          skeleton={isLoading}
        />
      </Cols3>

      {/* EV vs CLV scatter */}
      <ChartContainer
        title="EV vs CLV Scatter"
        subtitle="Is your EV estimate predictive of how much you beat the close?"
        athenaContext="Analyze the correlation between EV and CLV in my picks"
        loading={isLoading}
        empty={picks.filter(p => p.clv !== null).length === 0}
        emptyMessage="No CLV data yet — add closing line capture to the grading pipeline"
      >
        <ClvScatterChart picks={picks} />
      </ChartContainer>

      {/* Distribution + Direction */}
      <Cols2>
        <ChartContainer
          title="CLV Distribution"
          subtitle="How often do you beat the close vs lag it?"
          loading={isLoading}
          empty={picks.filter(p => p.clv !== null).length === 0}
        >
          <ClvDistChart picks={picks} />
        </ChartContainer>

        <ChartContainer
          title="Avg CLV by Direction"
          subtitle="Do OVER or UNDER picks beat the line more?"
          loading={isLoading}
          empty={picks.filter(p => p.clv !== null).length === 0}
        >
          <ClvByDirection picks={picks} />
        </ChartContainer>
      </Cols2>

      {/* Insights + Athena */}
      <Cols2>
        <InsightCard title="CLV Theory" insights={CLV_INSIGHTS} />
        <AthenaSummary
          finding={`With **${clvPicks} picks** having closing line data: avg CLV is **${avgClv >= 0 ? '+' : ''}${avgClv.toFixed(2)}pp**, beat rate **${beatStr}%**. ${avgClv > 0 ? 'Positive CLV confirms genuine market edge — lines are moving in your direction.' : 'Negative CLV is a red flag — you may be a price-taker rather than price-maker.'}`}
          confidence={clvPicks >= 30 ? 78 : 45}
          roiImpact="+1.4% ROI"
          experiment="Track CLV by time-of-bet (early vs late line) to find optimal bet timing"
        />
      </Cols2>

      {/* Picks table */}
      <ChartContainer
        title="Picks with CLV Data"
        subtitle="Individual pick performance sorted by CLV"
        loading={isLoading}
        minHeight={160}
      >
        <ClvPicksTable picks={picks} />
      </ChartContainer>
    </SectionPage>
  );
}
