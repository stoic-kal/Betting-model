/**
 * App.tsx — Root application component
 *
 * Responsibilities:
 *   1. Boot data fetch via useAthenaData
 *   2. Register global voice navigation commands
 *   3. Render the router
 *
 * Intentionally thin — all layout is in AppLayout, all state in stores.
 */

import { useEffect } from 'react';
import { useAthenaData } from '@hooks/useAthenaData';
import { useVoiceNavigation } from '@hooks/useSection';
import { AthenaRouter } from './router';

export function App() {
  // Boot: fetch diagnostic data and populate store
  useAthenaData();

  // Register voice navigation commands globally
  const { registerAll } = useVoiceNavigation();
  useEffect(() => { registerAll(); }, [registerAll]);

  return <AthenaRouter />;
}
