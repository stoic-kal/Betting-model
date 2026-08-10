/**
 * TeamsPage — Team-Level Performance Analysis
 */

import { useMemo, useState }                                      from 'react';
import Plot                                                       from 'react-plotly.js';
import { useAthenaStore, selectTeams }                            from '@store/athenaStore';
import { useAthenaData }                                          from '@hooks/useAthenaData';
import { useChartTheme, mergeLayout }                             from '@hooks/useChartTheme';
import { SectionPage, Cols2, Cols3 }                              from '@components/SectionPage';
import { MetricCard }                                             from '@components/MetricCard';
import { AthenaSummary }                                          from '@components/AthenaSummary';
import { ChartContainer }                                         from '@components/ChartContainer';
import { InsightCard }                                            from '@components/InsightCard';
import type { TeamMetric }                                        from '@types-athena';
import type { Insight }                                           from '@components/InsightCard';
import styles                                                     from './TeamsPage.module.css';

// ── Types ─────────────────────────────────────────────────────────────────────

type SortKey = 'wr' | 'roi' | 'picks' | 'avg_ev';

// ── Static insights ────────────────────────────────────────────────────────────

const TEAM_INSIGHTS: Insight[] = [
  {
    text: '**High picks count does not mean reliable signal.** A team with 2 picks at 100% WR is noise. Focus on teams with n≥5 picks.',
    severity: 'info',
  },
  {
    text: '**Look for teams where your EV estimate and WR disagree** — that gap is your calibration error on specific matchup types.',
    severity: 'medium',
  },
  {
    text: '**Consistently bad team performance** across WR, ROI, and EV suggests the model is systematically wrong about that franchise.',
    severity: 'high',
  },
];

// ── WR Bar Chart ──────────────────────────────────────────────────────────────

function WrBarChart({ teams }: { teams: TeamMetric[] }) {
  const { layout, config, colors } = useChartTheme();
  const sorted = useMemo(() => [...teams].sort((a, b) => a.wr - b.wr), [teams]);

  return (
    <Plot
      data={[{
        type:        'bar',
        orientation: 'h',
        x:           sorted.map(t => t.wr),
        y:           sorted.map(t => t.name),
        marker: {
          color:   sorted.map(t => t.wr >= 52.4 ? colors.green : t.wr >= 45 ? colors.amber : colors.red),
          opacity: 0.85,
          line:    { color: 'rgba(255,255,255,0.06)', width: 1 },
        },
        text:          sorted.map(t => `${t.wr.toFixed(0)}%`),
        textposition:  'outside' as const,
        textfont:      { color: '#6B7280', size: 10 },
        cliponaxis:    false,
        hovertemplate: '<b>%{y}</b><br>WR: %{x:.1f}%<extra></extra>',
      }]}
      layout={mergeLayout(layout, {
        height: Math.max(280, sorted.length * 26 + 60),
        margin: { t: 12, b: 44, l: 110, r: 60 },
        xaxis: {
          ...layout.xaxis,
          range:        [0, 115],
          ticksuffix:   '%',
          title:        { text: 'Win Rate %', font: { color: '#6B7280', size: 10 } },
        },
        yaxis: { ...layout.yaxis, showgrid: false, automargin: true },
        shapes: [{
          type: 'line',
          x0: 52.4, x1: 52.4, y0: -0.5, y1: sorted.length - 0.5,
          line: { color: colors.amber, width: 1, dash: 'dot' },
        }],
        annotations: [{
          x: 52.4, y: sorted.length - 1,
          text: 'break-even', showarrow: false,
          font: { color: colors.amber, size: 9 },
          xanchor: 'left', xshift: 4,
        }],
        showlegend: false,
      })}
      config={config}
      style={{ width: '100%' }}
      useResizeHandler
    />
  );
}

// ── ROI Bar Chart ─────────────────────────────────────────────────────────────

function RoiBarChart({ teams }: { teams: TeamMetric[] }) {
  const { layout, config, colors } = useChartTheme();
  const sorted = useMemo(() => [...teams].sort((a, b) => a.roi - b.roi), [teams]);

  return (
    <Plot
      data={[{
        type:        'bar',
        orientation: 'h',
        x:           sorted.map(t => t.roi),
        y:           sorted.map(t => t.name),
        marker: {
          color:   sorted.map(t => t.roi >= 0 ? colors.green : colors.red),
          opacity: 0.80,
          line:    { color: 'rgba(255,255,255,0.06)', width: 1 },
        },
        text:          sorted.map(t => `${t.roi > 0 ? '+' : ''}${t.roi.toFixed(1)}%`),
        textposition:  'outside' as const,
        textfont:      { color: '#6B7280', size: 10 },
        cliponaxis:    false,
        hovertemplate: '<b>%{y}</b><br>ROI: %{x:.1f}%<extra></extra>',
      }]}
      layout={mergeLayout(layout, {
        height: Math.max(280, sorted.length * 26 + 60),
        margin: { t: 12, b: 44, l: 110, r: 60 },
        xaxis: {
          ...layout.xaxis,
          ticksuffix: '%',
          title: { text: 'ROI %', font: { color: '#6B7280', size: 10 } },
        },
        yaxis: { ...layout.yaxis, showgrid: false, automargin: true },
        shapes: [{
          type: 'line',
          x0: 0, x1: 0, y0: -0.5, y1: sorted.length - 0.5,
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

// ── EV vs WR Scatter ──────────────────────────────────────────────────────────

function EvWrScatter({ teams }: { teams: TeamMetric[] }) {
  const { layout, config, colors } = useChartTheme();
  const withEv = teams.filter(t => t.avg_ev !== null);

  const abbrevs = withEv.map(t => t.name.split(' ').pop() ?? t.name);

  return (
    <Plot
      data={[{
        type: 'scatter',
        mode: 'markers+text' as unknown as 'markers',
        x:    withEv.map(t => t.avg_ev),
        y:    withEv.map(t => t.wr),
        text: abbrevs,
        textposition: 'top center',
        textfont: { color: '#6B7280', size: 9 },
        marker: {
          color:   withEv.map(t => t.roi >= 0 ? colors.green : colors.red),
          size:    withEv.map(t => Math.max(8, Math.sqrt(t.picks) * 4)),
          opacity: 0.80,
          line:    { color: 'rgba(255,255,255,0.10)', width: 1 },
        },
        hovertext: withEv.map(t => `${t.name}<br>EV: ${(t.avg_ev ?? 0).toFixed(1)}%<br>WR: ${t.wr.toFixed(1)}%`),
        hoverinfo: 'text' as const,
      }]}
      layout={mergeLayout(layout, {
        height: 320,
        xaxis: {
          ...layout.xaxis,
          title:      { text: 'Avg EV (%)', font: { color: '#6B7280', size: 10 } },
          ticksuffix: '%',
        },
        yaxis: {
          ...layout.yaxis,
          title:      { text: 'Win Rate (%)', font: { color: '#6B7280', size: 10 } },
          ticksuffix: '%',
        },
        shapes: [{
          type: 'line',
          x0: -10, x1: 20, y0: 52.4, y1: 52.4,
          line: { color: colors.amber, width: 1, dash: 'dot' },
        }],
        annotations: [{
          x: 15, y: 52.4,
          text: 'break-even', showarrow: false,
          font: { color: colors.amber, size: 9 },
          yshift: 8,
        }],
        showlegend: false,
      })}
      config={config}
      style={{ width: '100%' }}
      useResizeHandler
    />
  );
}

// ── Teams Table ────────────────────────────────────────────────────────────────

function TeamsTable({ teams }: { teams: TeamMetric[] }) {
  const [sortKey,  setSortKey]  = useState<SortKey>('wr');
  const [sortDesc, setSortDesc] = useState(true);

  const sorted = useMemo(() => {
    return [...teams].sort((a, b) => {
      const av = sortKey === 'avg_ev' ? (a.avg_ev ?? -999) : a[sortKey];
      const bv = sortKey === 'avg_ev' ? (b.avg_ev ?? -999) : b[sortKey];
      return sortDesc ? bv - av : av - bv;
    });
  }, [teams, sortKey, sortDesc]);

  function handleSort(key: SortKey) {
    if (key === sortKey) setSortDesc(d => !d);
    else { setSortKey(key); setSortDesc(true); }
  }

  function colHeader(key: SortKey, label: string) {
    const active = sortKey === key;
    return (
      <th
        className={`${styles.right} ${styles.sortable} ${active ? styles.active : ''}`}
        onClick={() => handleSort(key)}
      >
        {label} {active ? (sortDesc ? '↓' : '↑') : ''}
      </th>
    );
  }

  return (
    <div className={styles.tableWrap}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th>Team</th>
            {colHeader('picks', 'Picks')}
            {colHeader('wr',    'WR')}
            {colHeader('roi',   'ROI')}
            {colHeader('avg_ev','Avg EV')}
          </tr>
        </thead>
        <tbody>
          {sorted.map(t => (
            <tr key={t.name} className={styles.row}>
              <td className={styles.teamName}>{t.name}</td>
              <td className={`${styles.right} ${styles.mono}`}>{t.picks}</td>
              <td className={`${styles.right} ${styles.mono} ${t.wr >= 52.4 ? styles.pos : styles.neg}`}>
                {t.wr.toFixed(1)}%
              </td>
              <td className={`${styles.right} ${styles.mono} ${t.roi >= 0 ? styles.pos : styles.neg}`}>
                {t.roi > 0 ? '+' : ''}{t.roi.toFixed(1)}%
              </td>
              <td className={`${styles.right} ${styles.mono}`}>
                {t.avg_ev !== null ? `${t.avg_ev > 0 ? '+' : ''}${t.avg_ev.toFixed(1)}%` : '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────────

export default function TeamsPage() {
  const { isLoading } = useAthenaData();
  const teams = useAthenaStore(selectTeams);

  const { bestTeam, worstTeam, avgWr } = useMemo(() => {
    if (!teams.length) return { bestTeam: null, worstTeam: null, avgWr: 0 };
    const s   = [...teams].sort((a, b) => b.wr - a.wr);
    const avg = teams.reduce((acc, t) => acc + t.wr, 0) / teams.length;
    return { bestTeam: s[0], worstTeam: s[s.length - 1], avgWr: avg };
  }, [teams]);

  return (
    <SectionPage
      icon="🏟"
      title="Team Analysis"
      subtitle="Win rate, ROI, and edge breakdown by franchise"
      athenaQuery="Which teams are performing best and worst, and why?"
    >
      {/* Summary cards */}
      <Cols3>
        <MetricCard
          label="Teams Tracked"
          value={teams.length}
          decimals={0}
          context="franchises with at least 1 pick"
          skeleton={isLoading}
        />
        <MetricCard
          label="Best Team WR"
          value={bestTeam?.wr ?? 0}
          suffix="%"
          decimals={1}
          color="green"
          context={bestTeam?.name ?? '—'}
          skeleton={isLoading}
        />
        <MetricCard
          label="Worst Team WR"
          value={worstTeam?.wr ?? 0}
          suffix="%"
          decimals={1}
          color="red"
          context={worstTeam?.name ?? '—'}
          skeleton={isLoading}
        />
      </Cols3>

      {/* WR + ROI charts */}
      <Cols2>
        <ChartContainer
          title="Win Rate by Team"
          subtitle="Teams sorted ascending — green = above break-even (52.4%)"
          loading={isLoading}
          empty={teams.length === 0}
          emptyMessage="No team data — run the full diagnostics"
        >
          <WrBarChart teams={teams} />
        </ChartContainer>

        <ChartContainer
          title="ROI by Team"
          subtitle="Which teams generate positive return?"
          loading={isLoading}
          empty={teams.length === 0}
        >
          <RoiBarChart teams={teams} />
        </ChartContainer>
      </Cols2>

      {/* EV vs WR scatter + insights */}
      <Cols2>
        <ChartContainer
          title="EV vs Win Rate"
          subtitle="Do high-EV teams actually win more? Bubble size = pick count"
          athenaContext="Analyze whether EV predicts team win rate in my data"
          loading={isLoading}
          empty={teams.filter(t => t.avg_ev !== null).length < 2}
          emptyMessage="Not enough EV data across teams"
        >
          <EvWrScatter teams={teams} />
        </ChartContainer>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <InsightCard title="Team Analysis Theory" insights={TEAM_INSIGHTS} />
          <AthenaSummary
            finding={
              teams.length > 0
                ? `**${teams.length} teams** tracked. Best: **${bestTeam?.name}** (${bestTeam?.wr.toFixed(1)}% WR). Worst: **${worstTeam?.name}** (${worstTeam?.wr.toFixed(1)}% WR). Season average WR: **${avgWr.toFixed(1)}%**.`
                : 'No team data available. Run diagnostics to populate team performance.'
            }
            confidence={teams.length >= 10 ? 70 : 40}
            roiImpact="+0.5% ROI"
            experiment="Build team-specific probability adjustments for franchises with 5+ pick samples"
          />
        </div>
      </Cols2>

      {/* Full sortable table */}
      <ChartContainer
        title="Team Stats Table"
        subtitle="Click column headers to sort. Focus on teams with 5+ picks for reliable signal."
        loading={isLoading}
        minHeight={200}
      >
        <TeamsTable teams={teams} />
      </ChartContainer>
    </SectionPage>
  );
}
