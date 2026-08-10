/**
 * useChartTheme — Plotly dark theme configuration
 *
 * Returns a consistent Plotly layout + config object.
 * All charts import this hook — one place to update the entire
 * chart aesthetic across Athena.
 *
 * Usage:
 *   const { layout, config, colors } = useChartTheme();
 *   <Plot layout={{ ...layout, title: 'My Chart' }} config={config} />
 */

import { useMemo } from 'react';
import type { PlotlyTheme } from '@types-athena';

// ── Athena chart color palette (ordered for sequential use) ───────────────────

export const CHART_COLORS = {
  purple:  '#8B5CF6',
  blue:    '#3B82F6',
  green:   '#10B981',
  orange:  '#F97316',
  red:     '#EF4444',
  cyan:    '#06B6D4',
  pink:    '#EC4899',
  amber:   '#F59E0B',
  lime:    '#84CC16',
  teal:    '#14B8A6',
  // Semantic
  over:    '#EF4444',
  under:   '#10B981',
  neutral: '#6B7280',
  grid:    'rgba(255,255,255,0.06)',
  zero:    'rgba(255,255,255,0.12)',
} as const;

export const COLORWAY = [
  CHART_COLORS.purple,
  CHART_COLORS.blue,
  CHART_COLORS.green,
  CHART_COLORS.orange,
  CHART_COLORS.red,
  CHART_COLORS.cyan,
  CHART_COLORS.pink,
  CHART_COLORS.amber,
];

// ── Base axis config (reusable) ───────────────────────────────────────────────

const BASE_AXIS = {
  gridcolor:     CHART_COLORS.grid,
  linecolor:     'rgba(255,255,255,0.08)',
  tickcolor:     'rgba(255,255,255,0)',
  tickfont:      { color: '#6B7280', size: 10, family: 'SF Mono, JetBrains Mono, monospace' },
  zerolinecolor: CHART_COLORS.zero,
  zerolinewidth: 1,
  showgrid:      true,
};

// ── Hook ──────────────────────────────────────────────────────────────────────

export function useChartTheme() {
  const layout = useMemo<Partial<PlotlyTheme> & Record<string, unknown>>(
    () => ({
      paper_bgcolor: 'transparent',
      plot_bgcolor:  '#0D0F14',
      font: {
        color:  '#9CA3AF',
        family: '-apple-system, "SF Pro Display", "Inter", sans-serif',
        size:   11,
      },
      margin:  { t: 24, b: 44, l: 52, r: 16 },
      xaxis:   { ...BASE_AXIS },
      yaxis:   { ...BASE_AXIS },
      colorway: COLORWAY,
      hoverlabel: {
        bgcolor:     '#1C1F28',
        bordercolor: 'rgba(255,255,255,0.12)',
        font:        { color: '#E6EDF3', size: 12, family: 'SF Mono, monospace' },
      },
      legend: {
        bgcolor:     'rgba(0,0,0,0)',
        bordercolor: 'rgba(255,255,255,0)',
        font:        { color: '#9CA3AF', size: 10 },
        orientation: 'h' as const,
        x: 0,
        y: -0.18,
      },
      hovermode:    'closest' as const,
      showlegend:   true,
      dragmode:     'zoom' as const,
    }),
    []
  );

  const config = useMemo(
    () => ({
      displayModeBar:    true,
      displaylogo:       false,
      responsive:        true,
      modeBarButtonsToRemove: [
        'select2d',
        'lasso2d',
        'autoScale2d',
        'hoverClosestCartesian',
        'hoverCompareCartesian',
        'toggleSpikelines',
      ] as Plotly.ModeBarDefaultButtons[],
      toImageButtonOptions: {
        format:   'png' as const,
        filename: `athena_chart_${Date.now()}`,
        scale:    2,
      },
    }),
    []
  );

  return { layout, config, colors: CHART_COLORS, colorway: COLORWAY };
}

/**
 * Merge a partial layout override into the base theme layout.
 * Use this in chart components to extend without mutation.
 */
export function mergeLayout(
  base: ReturnType<typeof useChartTheme>['layout'],
  overrides: Record<string, unknown>
): Record<string, unknown> {
  return { ...base, ...overrides };
}
