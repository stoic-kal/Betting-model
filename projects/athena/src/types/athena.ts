/**
 * Athena — Core Type System
 *
 * Every data structure flowing through Athena is typed here.
 * Services, stores, components, and hooks all import from this file.
 * Never define ad-hoc types inline — always extend from here.
 */

// ── Primitives ────────────────────────────────────────────────────────────────

export type Severity   = 'critical' | 'high' | 'medium' | 'low' | 'positive';
export type Direction  = 'OVER' | 'UNDER';
export type PickStatus = 'won' | 'lost' | 'pending' | 'push' | 'void';
export type PickType   = 'totals' | 'moneyline';
export type SectionId  =
  | 'overview'
  | 'data-health'
  | 'calibration'
  | 'over-under'
  | 'features'
  | 'edge'
  | 'clv'
  | 'teams'
  | 'filters'
  | 'temporal'
  | 'root-cause'
  | 'roadmap'
  | 'prediction-db'
  // Coming soon
  | 'shap'
  | 'umpires'
  | 'weather'
  | 'ballparks'
  | 'journal'
  | 'experiments'
  | 'registry';


// ── API Response — /api/diag/data ─────────────────────────────────────────────

export interface AthenaData {
  summary:      SummaryMetrics;
  calibration:  CalibrationData;
  temporal:     TemporalData;
  features:     FeatureMetric[];
  teams:        TeamMetric[];
  ev_buckets:   EvBucket[];
  filters:      FilterResult[];
  recent_picks: RecentPick[];
  data_health:  FeatureHealthRow[];
}

export interface SummaryMetrics {
  total_picks:    number;
  resolved:       number;
  with_snapshot:  number;
  won:            number;
  date_min:       string | null;
  date_max:       string | null;
  overall_wr:     number;   // percent, e.g. 48.3
  overall_roi:    number;   // percent, e.g. -6.7
  over_record:    [number, number];   // [won, lost]
  over_wr:        number;
  over_roi:       number;
  under_record:   [number, number];
  under_wr:       number;
  under_roi:      number;
  avg_ev:         number | null;
  avg_prob:       number | null;   // 0–1
  avg_clv:        number;          // percentage points
  beat_close:     number;          // percent
  clv_picks:      number;
}

export interface CalibrationData {
  bins:           string[];       // ["50-55%", "55-60%", ...]
  pred_centers:   number[];       // [52.5, 57.5, ...]
  actual_wr:      number[];       // actual win rate per bucket
  bin_counts:     number[];
  brier:          number | null;
  ece:            number | null;
  baseline_brier: number | null;
}

export interface TemporalData {
  dates:       string[];
  cum_pnl:     number[];
  rolling_wr:  number[];
}

export interface FeatureMetric {
  name:       string;   // Human-readable, e.g. "Home Fip"
  key:        string;   // Snake case, e.g. "home_fip"
  corr:       number;   // Point-biserial correlation
  n:          number;
  mean_won:   number | null;
  mean_lost:  number | null;
}

export interface TeamMetric {
  name:    string;
  picks:   number;
  wr:      number;    // percent
  roi:     number;    // percent
  avg_ev:  number | null;
}

export interface EvBucket {
  label:  string;   // "0-5%", "5-10%", ...
  n:      number;
  wr:     number;   // percent
  roi:    number;   // percent
}

export interface FilterResult {
  label:   string;
  n:       number;
  wr:      number;   // percent
  roi:     number;   // percent
  avg_ev:  number | null;
}

export interface RecentPick {
  date:      string;
  matchup:   string;
  pick:      string;
  direction: Direction;
  status:    PickStatus;
  prob:      number | null;    // percent
  ev:        number | null;    // percent
  odds:      number | null;    // decimal
  clv:       number | null;    // percentage points
  version:   string;
}

export interface FeatureHealthRow {
  name:      string;
  coverage:  number;   // percent available
  mean:      number | null;
  std:       number;
  constant:  boolean;
}


// ── UI State ──────────────────────────────────────────────────────────────────

export interface GlobalFilters {
  modelVersion:  string | null;    // null = all
  betType:       Direction | null; // null = all
  dateFrom:      string | null;
  dateTo:        string | null;
  minProb:       number | null;    // 0–1
  minEv:         number | null;    // percent
}

export interface UiState {
  activeSection:    SectionId;
  sidebarCollapsed: boolean;
  voiceActive:      boolean;
  athenaPanelOpen:  boolean;
  loadingData:      boolean;
  dataError:        string | null;
}


// ── Navigation ────────────────────────────────────────────────────────────────

export interface NavSection {
  id:          SectionId;
  label:       string;
  icon:        string;
  comingSoon?: boolean;
  badge?:      string;           // e.g. "NEW", "BETA"
}

export const NAV_SECTIONS: NavSection[] = [
  // Core research
  { id: 'overview',     label: 'Mission Control', icon: '⚡' },
  { id: 'data-health',  label: 'Data Health',     icon: '🏥' },
  { id: 'calibration',  label: 'Calibration Lab', icon: '🎯' },
  { id: 'over-under',   label: 'Over vs Under',   icon: '⚾' },
  { id: 'features',     label: 'Feature Store',   icon: '🧠' },
  { id: 'edge',         label: 'Edge Analysis',   icon: '💰' },
  { id: 'clv',          label: 'CLV',             icon: '📊' },
  { id: 'teams',        label: 'Team Analysis',   icon: '🏟' },
  { id: 'filters',      label: 'Bet Optimizer',   icon: '🎲' },
  { id: 'temporal',     label: 'Temporal',        icon: '📅' },
  { id: 'root-cause',   label: 'Root Cause',      icon: '🚨' },
  { id: 'roadmap',      label: 'Roadmap',         icon: '🚀' },
  { id: 'prediction-db',label: 'Prediction DB',   icon: '🗄️' },
  // Coming soon
  { id: 'shap',         label: 'SHAP Analysis',   icon: '💥', comingSoon: true },
  { id: 'umpires',      label: 'Umpires',         icon: '👨‍⚖️', comingSoon: true },
  { id: 'weather',      label: 'Weather',         icon: '🌦',  comingSoon: true },
  { id: 'ballparks',    label: 'Ballparks',       icon: '🏟',  comingSoon: true },
  { id: 'journal',      label: 'Research Journal',icon: '📓',  comingSoon: true },
  { id: 'experiments',  label: 'Experiments',     icon: '🔬',  comingSoon: true },
  { id: 'registry',     label: 'Model Registry',  icon: '📦',  comingSoon: true },
];


// ── Root Cause & Roadmap ──────────────────────────────────────────────────────

export interface RootCause {
  id:            string;
  severity:      Severity;
  title:         string;
  metric:        string;     // e.g. "38.9% WR"
  evidence:      string;
  fix:           string;
  impact:        string;     // e.g. "+8pp WR"
  confidence:    number;     // 0–100
  engCost:       'Low' | 'Medium' | 'High';
  roiGain:       string;     // e.g. "+1.4%"
}

export interface RoadmapPhase {
  phase:      number;
  title:      string;
  duration:   string;
  status:     'todo' | 'in-progress' | 'done';
  tasks:      RoadmapTask[];
}

export interface RoadmapTask {
  id:          string;
  title:       string;
  description: string;
  impact:      string;
  priority:    number;
}


// ── Athena AI ─────────────────────────────────────────────────────────────────

export interface AthenaInsight {
  finding:     string;
  confidence:  number;    // 0–100
  roiImpact:   string;    // e.g. "+1.4%"
  experiment:  string;
  action:      string;
}

export type AthenaSectionInsights = Record<SectionId, AthenaInsight>;


// ── Chart ─────────────────────────────────────────────────────────────────────

export interface PlotlyTheme {
  paper_bgcolor: string;
  plot_bgcolor:  string;
  font:          { color: string; family: string; size: number };
  margin:        { t: number; b: number; l: number; r: number };
  xaxis:         Record<string, unknown>;
  yaxis:         Record<string, unknown>;
  colorway:      string[];
}
