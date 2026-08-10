/**
 * athenaStore — Global model data + filter state
 *
 * Holds raw API data, applied filters, and derived slices.
 * Components never call the API directly — they read from this store.
 * React Query fetches + populates; Zustand distributes.
 */

import { create } from 'zustand';
import { devtools } from 'zustand/middleware';
import type {
  AthenaData,
  FilterResult,
  RecentPick,
  GlobalFilters,
} from '@types-athena';

// ── Derived slice computed from raw + filters ─────────────────────────────────

interface DerivedMetrics {
  filteredResolved:  RecentPick[];
  filteredOver:      RecentPick[];
  filteredUnder:     RecentPick[];
  filteredWR:        number;
  filteredROI:       number;
  topFilters:        FilterResult[];   // ROI > 0, sorted desc
  worstFilters:      FilterResult[];   // ROI < 0, sorted asc
}

// ── Store shape ───────────────────────────────────────────────────────────────

interface AthenaStore {
  // Raw data from /api/diag/data
  raw:     AthenaData | null;
  loading: boolean;
  error:   string | null;

  // Applied global filters
  filters: GlobalFilters;

  // Derived (recomputed whenever raw or filters change)
  derived: DerivedMetrics | null;

  // Actions
  setData:        (data: AthenaData) => void;
  setLoading:     (loading: boolean) => void;
  setError:       (error: string | null) => void;
  setFilter:      <K extends keyof GlobalFilters>(key: K, value: GlobalFilters[K]) => void;
  resetFilters:   () => void;
  clearData:      () => void;
}

// ── Default values ────────────────────────────────────────────────────────────

const DEFAULT_FILTERS: GlobalFilters = {
  modelVersion: null,
  betType:      null,
  dateFrom:     null,
  dateTo:       null,
  minProb:      null,
  minEv:        null,
};

// ── Derivation logic ──────────────────────────────────────────────────────────

function derive(data: AthenaData, filters: GlobalFilters): DerivedMetrics {
  let picks = data.recent_picks.filter(
    p => p.status === 'won' || p.status === 'lost'
  );

  // Apply filters
  if (filters.betType) {
    picks = picks.filter(p => p.direction === filters.betType);
  }
  if (filters.dateFrom) {
    picks = picks.filter(p => p.date >= filters.dateFrom!);
  }
  if (filters.dateTo) {
    picks = picks.filter(p => p.date <= filters.dateTo!);
  }
  if (filters.minProb !== null) {
    picks = picks.filter(p => p.prob !== null && p.prob / 100 >= filters.minProb!);
  }
  if (filters.minEv !== null) {
    picks = picks.filter(p => p.ev !== null && p.ev >= filters.minEv!);
  }

  const won   = picks.filter(p => p.status === 'won');
  const total = picks.length;

  // Recompute ROI from filtered picks (using implied decimal odds ≈ 1.95)
  const roiSum = picks.reduce((acc, p) => {
    return acc + (p.status === 'won' ? (p.odds ?? 1.95) - 1 : -1);
  }, 0);

  const filtersSorted = [...data.filters].sort((a, b) => b.roi - a.roi);

  return {
    filteredResolved: picks,
    filteredOver:     picks.filter(p => p.direction === 'OVER'),
    filteredUnder:    picks.filter(p => p.direction === 'UNDER'),
    filteredWR:       total > 0 ? Math.round((won.length / total) * 1000) / 10 : 0,
    filteredROI:      total > 0 ? Math.round((roiSum / total) * 1000) / 10 : 0,
    topFilters:       filtersSorted.filter(f => f.roi > 0),
    worstFilters:     filtersSorted.filter(f => f.roi < 0).reverse(),
  };
}

// ── Store ─────────────────────────────────────────────────────────────────────

export const useAthenaStore = create<AthenaStore>()(
  devtools(
    (set, get) => ({
      raw:     null,
      loading: false,
      error:   null,
      filters: DEFAULT_FILTERS,
      derived: null,

      setData: (data) => {
        const derived = derive(data, get().filters);
        set({ raw: data, derived, error: null }, false, 'setData');
      },

      setLoading: (loading) => set({ loading }, false, 'setLoading'),

      setError: (error) => set({ error, loading: false }, false, 'setError'),

      setFilter: (key, value) => {
        const newFilters = { ...get().filters, [key]: value };
        const raw = get().raw;
        const derived = raw ? derive(raw, newFilters) : null;
        set({ filters: newFilters, derived }, false, `setFilter/${key}`);
      },

      resetFilters: () => {
        const raw = get().raw;
        const derived = raw ? derive(raw, DEFAULT_FILTERS) : null;
        set({ filters: DEFAULT_FILTERS, derived }, false, 'resetFilters');
      },

      clearData: () =>
        set({ raw: null, derived: null, error: null }, false, 'clearData'),
    }),
    { name: 'AthenaStore' }
  )
);

// ── Selectors ─────────────────────────────────────────────────────────────────
// Use these in components for focused re-renders (avoids subscribing to full store)

export const selectSummary      = (s: AthenaStore) => s.raw?.summary ?? null;
export const selectCalibration  = (s: AthenaStore) => s.raw?.calibration ?? null;
export const selectTemporal     = (s: AthenaStore) => s.raw?.temporal ?? null;
export const selectFeatures     = (s: AthenaStore) => s.raw?.features ?? [];
export const selectTeams        = (s: AthenaStore) => s.raw?.teams ?? [];
export const selectEvBuckets    = (s: AthenaStore) => s.raw?.ev_buckets ?? [];
export const selectFilters      = (s: AthenaStore) => s.raw?.filters ?? [];
export const selectRecentPicks  = (s: AthenaStore) => s.raw?.recent_picks ?? [];
export const selectDataHealth   = (s: AthenaStore) => s.raw?.data_health ?? [];
export const selectDerived      = (s: AthenaStore) => s.derived;
export const selectGlobalFilters = (s: AthenaStore) => s.filters;
export const selectIsLoading    = (s: AthenaStore) => s.loading;
export const selectError        = (s: AthenaStore) => s.error;
