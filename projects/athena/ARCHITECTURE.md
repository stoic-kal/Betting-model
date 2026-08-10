# Athena — AI Research Operating System
## Architecture Specification · v1.0

---

## Vision

Athena is not a dashboard. It is an AI Research Operating System that lets a researcher
build, evaluate, diagnose, deploy, monitor, and improve machine learning models through
a conversational, intelligent research interface.

---

## Technology Stack

| Layer            | Technology         | Reason                                          |
|------------------|--------------------|-------------------------------------------------|
| Build Tool       | Vite 5             | Sub-100ms HMR, native ESM, superior DX          |
| Framework        | React 18           | Concurrent rendering, Suspense, Server Components|
| Language         | TypeScript 5       | Full type safety across all layers               |
| Styling          | CSS Variables + Modules | Zero runtime, perfect dark mode, token-driven |
| State            | Zustand 4          | Minimal, composable, devtools-compatible         |
| Routing          | React Router 6     | Nested layouts, data loaders, code splitting     |
| Charts           | Plotly.js          | Interactive, zoomable, exportable, dark theme    |
| Tables           | TanStack Table v8  | Headless, fully customizable data grids          |
| Animations       | Framer Motion      | Production-grade, GPU-accelerated animations     |
| API Client       | Axios + React Query| Cache, refetch, optimistic updates, SSE support  |
| Backend          | Flask (Python)     | Existing — serves /api/diag/* endpoints          |

---

## Directory Structure

```
athena/
├── src/
│   ├── app/
│   │   ├── App.tsx              # Root component, providers, router
│   │   ├── router.tsx           # All route definitions
│   │   └── providers.tsx        # QueryClient, theme, voice providers
│   │
│   ├── design-system/
│   │   ├── tokens.ts            # All design tokens (color, space, type)
│   │   ├── theme.ts             # Computed theme object from tokens
│   │   ├── animations.ts        # Framer Motion variants library
│   │   └── index.ts             # Public exports
│   │
│   ├── components/              # Reusable primitives (Phase 3)
│   │   ├── MetricCard/
│   │   ├── InsightCard/
│   │   ├── ChartContainer/
│   │   ├── AthenaSummary/
│   │   ├── StatusBadge/
│   │   ├── ConfidenceChip/
│   │   ├── DriftIndicator/
│   │   ├── WarningCard/
│   │   ├── RecommendationPanel/
│   │   └── Skeleton/
│   │
│   ├── features/                # Page-level feature modules (Phase 4)
│   │   ├── overview/
│   │   ├── data-health/
│   │   ├── calibration/
│   │   ├── over-under/
│   │   ├── feature-importance/
│   │   ├── edge-analysis/
│   │   ├── clv/
│   │   ├── teams/
│   │   ├── bet-filters/
│   │   ├── temporal/
│   │   ├── root-cause/
│   │   ├── roadmap/
│   │   ├── prediction-db/
│   │   └── athena-voice/
│   │
│   ├── layouts/
│   │   ├── AppLayout.tsx        # Fixed sidebar + main content shell
│   │   ├── Sidebar.tsx          # Navigation, section list
│   │   └── TopBar.tsx           # Model health status bar
│   │
│   ├── hooks/
│   │   ├── useAthenaData.ts     # Main data hook (React Query)
│   │   ├── useVoice.ts          # Web Speech API integration
│   │   ├── useSection.ts        # Active section routing
│   │   ├── useCounter.ts        # Animated number counter
│   │   └── useChartTheme.ts     # Plotly theme hook
│   │
│   ├── services/
│   │   ├── api.ts               # Axios instance, base URL, interceptors
│   │   ├── diagnostics.ts       # /api/diag/* service calls
│   │   └── stream.ts            # SSE stream handler for run output
│   │
│   ├── store/
│   │   ├── athenaStore.ts       # Global model data state (Zustand)
│   │   └── uiStore.ts           # UI state (sidebar, active page, voice)
│   │
│   ├── types/
│   │   └── athena.ts            # All TypeScript interfaces and types
│   │
│   └── utils/
│       ├── format.ts            # Number, percent, currency formatters
│       ├── classnames.ts        # cx() utility
│       └── colors.ts            # Dynamic color from value
│
├── public/
│   └── athena-logo.svg
│
├── ARCHITECTURE.md              # This file
├── package.json
├── tsconfig.json
└── vite.config.ts
```

---

## Data Flow

```
Flask /api/diag/data
        │
        ▼
  services/diagnostics.ts (Axios)
        │
        ▼
  useAthenaData (React Query hook)
   ├── Caches for 5 minutes
   ├── Background refetch on focus
   └── Exposes: { data, isLoading, error, refetch }
        │
        ▼
  athenaStore (Zustand)
   ├── Global filters (version, dateRange, betType)
   └── Derived slices: filteredResolved, filteredOver, filteredUnder
        │
        ▼
  Feature Components (pages)
   └── Read from store, never call API directly
```

---

## State Architecture

```
athenaStore
  ├── raw: AthenaData | null           # Full API response
  ├── filters: GlobalFilters           # Applied filters
  ├── derived: DerivedMetrics          # Computed from raw + filters
  └── actions
      ├── setData(data)
      ├── setFilter(key, value)
      └── resetFilters()

uiStore
  ├── activeSection: SectionId
  ├── sidebarCollapsed: boolean
  ├── voiceActive: boolean
  ├── athenaPanel: boolean
  └── actions
      ├── navigate(section)
      ├── toggleSidebar()
      └── toggleVoice()
```

---

## Voice Architecture (Phase 6)

Commands are registered per-section and globally dispatched via
a lightweight command registry. The Web Speech API captures input;
NLP matching maps utterances to registered commands.

```
VoiceProvider
  └── SpeechRecognition API
        └── CommandParser
              └── CommandRegistry
                    ├── global: ["open {section}", "explain chart"]
                    └── per-section: registered on mount, unregistered on unmount
```

---

## Performance Constraints

- Initial bundle < 200kb gzipped (route-split)
- Chart render < 200ms (Plotly with pre-computed traces)
- API response < 500ms (Flask computes on demand)
- LCP < 1.2s on local network
- All animations: GPU-accelerated (transform + opacity only)
