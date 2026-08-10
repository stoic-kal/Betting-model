/**
 * router.tsx — All route definitions
 *
 * Uses React Router v6 with lazy-loaded page components.
 * Every feature page is code-split — initial bundle stays small.
 *
 * Route structure:
 *   /          → AppLayout (shell, sidebar, topbar)
 *   /:section  → Renders the matching section inside AppLayout
 *
 * Section routing is handled client-side via uiStore.navigate()
 * rather than URL params — this keeps the URL clean ("/diagnostics")
 * while the SPA manages internal section state.
 */

import { lazy, Suspense } from 'react';
import { createBrowserRouter, RouterProvider, Navigate } from 'react-router-dom';

// Layouts — not lazy, they're always needed
import { AppLayout } from '@/layouts/AppLayout';

// Pages — all lazy loaded for code splitting
const OverviewPage       = lazy(() => import('@features/overview/OverviewPage'));
const DataHealthPage     = lazy(() => import('@features/data-health/DataHealthPage'));
const CalibrationPage    = lazy(() => import('@features/calibration/CalibrationPage'));
const OverUnderPage      = lazy(() => import('@features/over-under/OverUnderPage'));
const FeaturesPage       = lazy(() => import('@features/feature-importance/FeaturesPage'));
const EdgePage           = lazy(() => import('@features/edge-analysis/EdgePage'));
const ClvPage            = lazy(() => import('@features/clv/ClvPage'));
const TeamsPage          = lazy(() => import('@features/teams/TeamsPage'));
const FiltersPage        = lazy(() => import('@features/bet-filters/FiltersPage'));
const TemporalPage       = lazy(() => import('@features/temporal/TemporalPage'));
const RootCausePage      = lazy(() => import('@features/root-cause/RootCausePage'));
const RoadmapPage        = lazy(() => import('@features/roadmap/RoadmapPage'));
const PredictionDbPage   = lazy(() => import('@features/prediction-db/PredictionDbPage'));
const ComingSoonPage     = lazy(() => import('@features/coming-soon/ComingSoonPage'));

// ── Page fallback (shown while lazy chunk loads) ──────────────────────────────

function PageLoader() {
  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      height: '100%',
      color: 'var(--text-muted)',
      fontSize: '12px',
      letterSpacing: '0.08em',
      fontFamily: 'var(--font-mono)',
    }}>
      <span style={{ opacity: 0.5 }}>Loading…</span>
    </div>
  );
}

// ── Route definitions ─────────────────────────────────────────────────────────

const router = createBrowserRouter([
  {
    path: '/',
    element: <AppLayout />,
    children: [
      // Default redirect
      { index: true, element: <Navigate to="/overview" replace /> },

      // Core research sections
      {
        path: 'overview',
        element: (
          <Suspense fallback={<PageLoader />}>
            <OverviewPage />
          </Suspense>
        ),
      },
      {
        path: 'data-health',
        element: (
          <Suspense fallback={<PageLoader />}>
            <DataHealthPage />
          </Suspense>
        ),
      },
      {
        path: 'calibration',
        element: (
          <Suspense fallback={<PageLoader />}>
            <CalibrationPage />
          </Suspense>
        ),
      },
      {
        path: 'over-under',
        element: (
          <Suspense fallback={<PageLoader />}>
            <OverUnderPage />
          </Suspense>
        ),
      },
      {
        path: 'features',
        element: (
          <Suspense fallback={<PageLoader />}>
            <FeaturesPage />
          </Suspense>
        ),
      },
      {
        path: 'edge',
        element: (
          <Suspense fallback={<PageLoader />}>
            <EdgePage />
          </Suspense>
        ),
      },
      {
        path: 'clv',
        element: (
          <Suspense fallback={<PageLoader />}>
            <ClvPage />
          </Suspense>
        ),
      },
      {
        path: 'teams',
        element: (
          <Suspense fallback={<PageLoader />}>
            <TeamsPage />
          </Suspense>
        ),
      },
      {
        path: 'filters',
        element: (
          <Suspense fallback={<PageLoader />}>
            <FiltersPage />
          </Suspense>
        ),
      },
      {
        path: 'temporal',
        element: (
          <Suspense fallback={<PageLoader />}>
            <TemporalPage />
          </Suspense>
        ),
      },
      {
        path: 'root-cause',
        element: (
          <Suspense fallback={<PageLoader />}>
            <RootCausePage />
          </Suspense>
        ),
      },
      {
        path: 'roadmap',
        element: (
          <Suspense fallback={<PageLoader />}>
            <RoadmapPage />
          </Suspense>
        ),
      },
      {
        path: 'prediction-db',
        element: (
          <Suspense fallback={<PageLoader />}>
            <PredictionDbPage />
          </Suspense>
        ),
      },

      // Coming soon sections — share one placeholder page
      {
        path: ':comingSoon',
        element: (
          <Suspense fallback={<PageLoader />}>
            <ComingSoonPage />
          </Suspense>
        ),
      },
    ],
  },
]);

// ── Export ────────────────────────────────────────────────────────────────────

export function AthenaRouter() {
  return <RouterProvider router={router} />;
}
