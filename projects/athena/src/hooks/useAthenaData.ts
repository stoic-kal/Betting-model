/**
 * useAthenaData — Primary data hook
 *
 * Wraps React Query around fetchDiagData().
 * On success, populates athenaStore so every component
 * can read from the store without re-fetching.
 *
 * Usage:
 *   const { isLoading, error, refetch } = useAthenaData();
 *   const summary = useAthenaStore(selectSummary);
 */

import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useAthenaStore } from '@store/athenaStore';
import { useUiStore } from '@store/uiStore';
import { fetchDiagData, QUERY_KEYS, STALE_TIMES } from '@services/diagnostics';
import { AthenaApiError } from '@services/api';

export function useAthenaData() {
  const setData    = useAthenaStore(s => s.setData);
  const setLoading = useAthenaStore(s => s.setLoading);
  const setError   = useAthenaStore(s => s.setError);
  const notify     = useUiStore(s => s.notify);

  const query = useQuery({
    queryKey:  QUERY_KEYS.diagData,
    queryFn:   fetchDiagData,
    staleTime: STALE_TIMES.diagData,
    retry:     2,
    retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 8000),
  });

  // Sync React Query state → Zustand store
  useEffect(() => {
    setLoading(query.isLoading);
  }, [query.isLoading, setLoading]);

  useEffect(() => {
    if (query.data) {
      setData(query.data);
    }
  }, [query.data, setData]);

  useEffect(() => {
    if (query.error) {
      const msg = query.error instanceof AthenaApiError
        ? query.error.message
        : 'Failed to load diagnostic data';

      setError(msg);

      notify({
        level:   'error',
        title:   'Data Load Failed',
        message: msg,
        ttl:     8000,
      });
    }
  }, [query.error, setError, notify]);

  return {
    isLoading:  query.isLoading,
    isFetching: query.isFetching,
    error:      query.error,
    refetch:    query.refetch,
    dataUpdatedAt: query.dataUpdatedAt,
  };
}
