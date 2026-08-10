/**
 * OverviewPage — Mission Control
 *
 * The top-level dashboard. First thing you see when Athena loads.
 * Shows:
 *   • Hero metric row (WR, ROI, record, EV, CLV, calibration)
 *   • Cumulative P&L chart
 *   • Over vs Under split cards
 *   • Recent picks feed
 *   • Athena AI summary
 *   • Key insights panel
 */

import { useMemo }                                     from 'react';
import Plot                                            from 'react-plotly.js';
import { useAthenaStore, selectSummary, selectTemporal, selectRecentPicks } from '@store/athenaStore';
import { useAthenaData }                               from '@hooks/useAthenaData';
import { useCounter }                                  from '@hooks/useCounter';
import { useChartTheme, mergeLayout }                  from '@hooks/useChartTheme';
import { SectionPage, Cols2, Cols3 }                   from '@components/SectionPage';
import { MetricCard }                                  from '@components/MetricCard';
import { InsightCard }                                 from '@components/InsightCard';
import { AthenaSummary }                               from '@components/AthenaSummary';
import { ChartContainer }                              from '@components/ChartContainer';
import type { Insight }                                from '@components/InsightCard';
import styles                                          from './OverviewPage.module.css';

// ── Static insight data ───────────────────────────────────────────────────────

const KEY_INSIGHTS: Insight[] = [
  {
    text: '**Model is 4.4pp below break-even** on 60 resolved picks — statistically expected given sample size, but calibration drift needs monitoring.',
    severity: 'high',
  },
  {
    text: '**CLV is positive (+1.9pp average)** across 32 picks with closing line data — this is the most important signal. Lines are moving in your direction.',
    severity: 'positive',
  },
  {
    text: '**OVER record: 16-23 (41.0% WR)** vs **UNDER record: 13-8 (61.9% WR)** — a 20pp gap. Under picks are clearly the edge. Investigate what separates them.',
    severity: 'critical',
  },
  {
    text: '**Only 45/74 picks have feature snapshots** — the remaining 29 are model black boxes. Adding snapshot logging across the board is priority zero.',
    severity: 'medium',
  },
  {
    text: '**Brier score 0.244** vs naive baseline 0.250 — marginal calibration edge. The model knows something but not enough.',
    severity: 'info',
  },
];

// ── Recent pick row ───────────────────────────────────────────────────────────

interface PickRowProps {
  date:      string;
  matchup:   string;
  pick:      string;
  direction: string;
  status:    string;
  ev:        number | null;
  odds:      number | null;
}

function PickRow({ date, matchup, pick, direction, status, ev, odds }: PickRowProps) {
  const isWon  = status === 'won';
  const isLost = status === 'lost';

  return (
    <div className={styles.pickRow}>
      <div className={styles.pickDate}>{date.slice(5)}</div>
      <div className={styles.pickMatchup}>{matchup}</div>
      <div className={styles.pickPick}>{pick}</div>
      <div
        className={styles.pickDir}
        data-dir={direction}
      >
        {direction}
      </div>
      {ev !== null
        ? <div className={styles.pickEv}>{ev > 0 ? '+' : ''}{ev.toFixed(1)}%</div>
        : <div className={styles.pickEv} data-empty>—</div>
      }
      {odds !== null
        ? <div className={styles.pickOdds}>{odds > 0 ? '+' : ''}{odds}</div>
        : <div className={styles.pickOdds} data-empty>—</div>
      }
      <div
        className={styles.pickStatus}
        data-status={status}
      >
        {isWon ? 'W' : isLost ? 'L' : status.charAt(0).toUpperCase()}
      </div>
    </div>
  );
}

// ── P&L Chart ─────────────────────────────────────────────────────────────────

function PnlChart() {
  const temporal   = useAthenaStore(selectTemporal);
  const { layout, config, colors } = useChartTheme();
  const isLoading  = useAthenaStore(s => s.loading);

  const chartData = useMemo(() => {
    if (!temporal) return [];
    const lastPnl = temporal.cum_pnl[temporal.cum_pnl.length - 1] ?? 0;
    const lineColor = lastPnl >= 0 ? colors.green : colors.red;

    return [
      {
        x: temporal.dates,
        y: temporal.cum_pnl,
        type:  'scatter' as const,
        mode:  'lines' as const,
        name:  'Cumulative P&L',
        line:  { color: lineColor, width: 2, shape: 'spline' as const },
        fill:  'tozeroy' as const,
        fillcolor: lastPnl >= 0
          ? 'rgba(16, 185, 129, 0.07)'
          : 'rgba(239, 68, 68, 0.07)',
        hovertemplate: '%{x}<br><b>%{y:.1f} units</b><extra></extra>',
      },
      {
        x: temporal.dates,
        y: new Array(temporal.dates.length).fill(0),
        type: 'scatter' as const,
        mode: 'lines' as const,
        name: 'Break-even',
        line: { color: colors.zero, width: 1, dash: 'dot' as const },
        hoverinfo: 'skip' as const,
        showlegend: false,
      },
    ];
  }, [temporal, colors]);

  const chartLayout = useMemo(() => mergeLayout(layout, {
    margin:    { t: 16, b: 44, l: 52, r: 16 },
    xaxis:     { ...layout.xaxis, type: 'category', nticks: 10 },
    yaxis:     { ...layout.yaxis, title: { text: 'Units', font: { size: 10, color: '#6B7280' } } },
    showlegend: false,
  }), [layout]);

  return (
    <ChartContainer
      title="Cumulative P&L"
      subtitle="Units won/lost over time (resolved picks only)"
      athenaContext="Analyze the cumulative P&L trend. Is there a structural improvement or decline? What explains the trajectory?"
      loading={isLoading}
      empty={!temporal || temporal.dates.length === 0}
      emptyMessage="No temporal data yet."
      minHeight={260}
    >
      <Plot
        data={chartData as Plotly.Data[]}
        layout={chartLayout as Partial<Plotly.Layout>}
        config={config as Partial<Plotly.Config>}
        style={{ width: '100%', height: '260px' }}
        useResizeHandler
      />
    </ChartContainer>
  );
}

// ── Direction Split ───────────────────────────────────────────────────────────

function DirectionCard({
  dir, wr, roi, wins, losses,
}: { dir: 'OVER' | 'UNDER'; wr: number; roi: number; wins: number; losses: number }) {
  const animWr  = useCounter(wr,             { decimals: 1 });
  const animRoi = useCounter(Math.abs(roi), { decimals: 1 });
  const isOver  = dir === 'OVER';

  return (
    <div className={styles.dirCard} data-dir={dir}>
      <div className={styles.dirHeader}>
        <span className={styles.dirLabel} data-dir={dir}>{dir}</span>
        <span className={styles.dirRecord}>{wins}–{losses}</span>
      </div>
      <div className={styles.dirMetrics}>
        <div className={styles.dirMetric}>
          <span className={styles.dirMetricLabel}>WR</span>
          <span
            className={styles.dirMetricValue}
            data-good={String(wr >= 52.4)}
          >
            {animWr}%
          </span>
        </div>
        <div className={styles.dirMetric}>
          <span className={styles.dirMetricLabel}>ROI</span>
          <span
            className={styles.dirMetricValue}
            data-good={String(roi > 0)}
          >
            {roi > 0 ? '+' : roi < 0 ? '-' : ''}{animRoi}%
          </span>
        </div>
      </div>
      {!isOver && wr >= 55 && (
        <div className={styles.dirBadge}>⭐ Edge</div>
      )}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function OverviewPage() {
  // Trigger data fetch
  useAthenaData();

  const summary     = useAthenaStore(selectSummary);
  const recentPicks = useAthenaStore(selectRecentPicks);
  const isLoading   = useAthenaStore(s => s.loading);
  const error       = useAthenaStore(s => s.error);

  // Animated metric values
  const wr         = summary?.overall_wr  ?? 0;
  const roi        = summary?.overall_roi ?? 0;
  const totalPicks = summary?.total_picks ?? 0;
  const resolved   = summary?.resolved    ?? 0;
  const avgEv      = summary?.avg_ev      ?? 0;
  const avgClv     = summary?.avg_clv     ?? 0;
  const beatClose  = summary?.beat_close  ?? 0;

  const last20 = recentPicks.slice(0, 20);

  const overRecord  = summary?.over_record  ?? [0, 0];
  const underRecord = summary?.under_record ?? [0, 0];

  return (
    <SectionPage
      icon="⚡"
      title="Mission Control"
      subtitle="Model performance overview — all resolved picks"
      athenaQuery="Give me a one-paragraph executive summary of this model's current performance, biggest weakness, and most actionable next step."
      loading={isLoading && !summary}
      empty={!isLoading && !summary && !error}
      emptyState={{
        icon: '⚡',
        title: 'No data loaded',
        description: 'Connect to the Flask server and run diagnostics to populate Mission Control.',
      }}
    >
      {/* ── Hero metrics ── */}
      <Cols3>
        <MetricCard
          label="Win Rate"
          value={wr}
          suffix="%"
          decimals={1}
          colorFn={v => v >= 55 ? 'green' : v >= 50 ? 'amber' : 'red'}
          trend={{ value: wr - 50, suffix: 'pp vs BEP' }}
          trendDir={wr >= 52.4 ? 'up' : 'down'}
          icon="🎯"
          sublabel={`${resolved} resolved`}
          context="Break-even at 52.4% (−110 juice)"
          skeleton={isLoading}
        />
        <MetricCard
          label="ROI"
          value={Math.abs(roi)}
          suffix="%"
          decimals={1}
          colorFn={() => roi > 0 ? 'green' : roi > -5 ? 'amber' : 'red'}
          trend={{ value: roi }}
          trendDir={roi > 0 ? 'up' : 'down'}
          icon="💰"
          sublabel="per unit wagered"
          context={roi > 0 ? 'Profitable' : 'Below break-even'}
          skeleton={isLoading}
        />
        <MetricCard
          label="Total Picks"
          value={totalPicks}
          decimals={0}
          color="default"
          icon="📋"
          sublabel={`${resolved} resolved · ${totalPicks - resolved} pending`}
          skeleton={isLoading}
        />
      </Cols3>

      <Cols3>
        <MetricCard
          label="Avg EV"
          value={avgEv}
          suffix="%"
          decimals={1}
          colorFn={v => v > 3 ? 'green' : v > 0 ? 'amber' : 'red'}
          icon="📈"
          sublabel="expected value at pick time"
          skeleton={isLoading}
        />
        <MetricCard
          label="Avg CLV"
          value={avgClv}
          suffix=" pp"
          decimals={1}
          colorFn={v => v > 0 ? 'green' : v > -2 ? 'amber' : 'red'}
          icon="📊"
          sublabel="closing line value"
          context="Positive = lines moving your way"
          skeleton={isLoading}
        />
        <MetricCard
          label="Beat Close"
          value={beatClose}
          suffix="%"
          decimals={1}
          colorFn={v => v > 55 ? 'green' : v >= 50 ? 'amber' : 'red'}
          icon="⚡"
          sublabel="of picks with CLV data"
          context="Target > 55%"
          skeleton={isLoading}
        />
      </Cols3>

      {/* ── P&L Chart ── */}
      <PnlChart />

      {/* ── Over / Under split ── */}
      <div className={styles.dirRow}>
        <DirectionCard
          dir="OVER"
          wins={overRecord[0]}
          losses={overRecord[1]}
          wr={summary?.over_wr  ?? 0}
          roi={summary?.over_roi ?? 0}
        />
        <DirectionCard
          dir="UNDER"
          wins={underRecord[0]}
          losses={underRecord[1]}
          wr={summary?.under_wr  ?? 0}
          roi={summary?.under_roi ?? 0}
        />
      </div>

      {/* ── Insights + Recent Picks ── */}
      <Cols2>
        <InsightCard
          title="Key Findings"
          icon="🔍"
          insights={KEY_INSIGHTS}
        />

        {/* Recent picks feed */}
        <div className={styles.picksCard}>
          <div className={styles.picksHeader}>
            <span className={styles.picksTitle}>📋 Recent Picks</span>
            <span className={styles.picksCount}>{last20.length} shown</span>
          </div>
          <div className={styles.picksTableHead}>
            <span>Date</span>
            <span>Matchup</span>
            <span>Pick</span>
            <span>Dir</span>
            <span>EV</span>
            <span>Odds</span>
            <span>Result</span>
          </div>
          <div className={styles.picksList}>
            {isLoading
              ? Array.from({ length: 8 }, (_, i) => (
                  <div key={i} className={styles.pickRowSkeleton} />
                ))
              : last20.length === 0
                ? <p className={styles.picksEmpty}>No picks yet</p>
                : last20.map((p, i) => (
                    <PickRow
                      key={i}
                      date={p.date}
                      matchup={p.matchup}
                      pick={p.pick}
                      direction={p.direction}
                      status={p.status}
                      ev={p.ev}
                      odds={p.odds}
                    />
                  ))
            }
          </div>
        </div>
      </Cols2>

      {/* ── Athena AI Summary ── */}
      <AthenaSummary
        finding="The model has a **20pp OVER/UNDER split** (41% vs 62% WR). Under picks are the clear edge while Over picks are losing money. The model may be **overestimating offensive run environments** — park factors, weather, and lineup adjustments likely need recalibration."
        confidence={87}
        roiImpact="+8–12pp WR on filtered UNDER picks"
        experiment="Filter to UNDER-only for next 30 picks and compare WR vs full dataset"
        positiveImpact
        onRunExperiment={() => window.location.assign('/filters')}
        experimentLabel="Open Bet Optimizer"
      />
    </SectionPage>
  );
}
