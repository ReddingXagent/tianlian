import { useState, useCallback, useEffect } from 'react';
import { useIsFocused } from '@react-navigation/native';
import { energyApi } from '../services/api';
import { EnergySummary } from '../types';

interface UseEnergyReturn {
  summary: EnergySummary | null;
  loading: boolean;
  refreshing: boolean;
  error: string | null;
  refresh: () => Promise<void>;
}

export function useEnergy(): UseEnergyReturn {
  const [summary, setSummary] = useState<EnergySummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isFocused = useIsFocused();

  const fetchSummary = useCallback(async (isRefresh = false) => {
    if (isRefresh) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    setError(null);
    try {
      const response = await energyApi.getSummary();
      setSummary(response.data);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : '获取能源数据失败';
      setError(message);
    } finally {
      if (isRefresh) {
        setRefreshing(false);
      } else {
        setLoading(false);
      }
    }
  }, []);

  const refresh = useCallback(async () => {
    await fetchSummary(true);
  }, [fetchSummary]);

  useEffect(() => {
    if (isFocused) {
      let cancelled = false;
      Promise.resolve().then(() => {
        if (!cancelled) fetchSummary();
      });
      return () => { cancelled = true; };
    }
  }, [isFocused, fetchSummary]);

  return { summary, loading, refreshing, error, refresh };
}
