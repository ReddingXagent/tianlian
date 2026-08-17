import { useState, useCallback, useEffect } from 'react';
import { useStationStore } from '../store/stationStore';
import { useWorkOrderStore } from '../store/workOrderStore';
import { dashboardApi } from '../services/api';
import { DashboardStats, Station } from '../types';

interface UseDashboardReturn {
  stats: DashboardStats | null;
  refreshing: boolean;
  loading: boolean;
  refresh: () => void;
  stations: Station[];
}

export function useDashboard(): UseDashboardReturn {
  const { stations, fetchStations } = useStationStore();
  const { fetchOrders } = useWorkOrderStore();
  const [refreshing, setRefreshing] = useState(false);
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [loading, setLoading] = useState(true);

  const loadDashboard = useCallback(async () => {
    setRefreshing(true);
    try {
      await Promise.all([
        fetchStations({ page: 1, pageSize: 100 }),
        fetchOrders({ page: 1, pageSize: 5 }),
      ]);
      try {
        const resp = await dashboardApi.getStats();
        setStats(resp.data);
      } catch {
        // Stats API may not be ready
      }
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [fetchStations, fetchOrders]);

  useEffect(() => {
    Promise.resolve().then(() => loadDashboard());
  }, [loadDashboard]);

  const refresh = useCallback(() => {
    loadDashboard();
  }, [loadDashboard]);

  return { stats, refreshing, loading, refresh, stations };
}
