/**
 * providers.tsx — Root provider tree
 *
 * Wraps the entire app with:
 *   1. CSS variable injection from design tokens
 *   2. React Query client
 *   3. Any future providers (auth, telemetry, etc.)
 *
 * Keep this file minimal — it runs before any route or component.
 */

import { useEffect, type ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cssVariables } from '@design-system';

// ── QueryClient — shared singleton ────────────────────────────────────────────

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Athena data changes only when someone runs the diagnostics — don't
      // refetch on every window focus or network reconnect automatically.
      refetchOnWindowFocus:     false,
      refetchOnReconnect:       false,
      refetchIntervalInBackground: false,
      // Errors surface via the store/notification system — no need to retry
      // aggressively inside React Query as well.
      retry:     2,
      retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 8000),
    },
  },
});

// ── CSS variable injector ─────────────────────────────────────────────────────

function CssTokenInjector() {
  useEffect(() => {
    const root = document.documentElement;
    Object.entries(cssVariables).forEach(([key, value]) => {
      root.style.setProperty(key, value);
    });
  }, []);

  return null;
}

// ── Providers ─────────────────────────────────────────────────────────────────

interface ProvidersProps {
  children: ReactNode;
}

export function Providers({ children }: ProvidersProps) {
  return (
    <QueryClientProvider client={queryClient}>
      <CssTokenInjector />
      {children}
    </QueryClientProvider>
  );
}
