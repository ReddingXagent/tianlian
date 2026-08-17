import { useState, useCallback, useEffect } from 'react';
import { useRoute } from '@react-navigation/native';
import { alarmApi } from '../services/api';
import { Alarm, AlarmStatus } from '../types';

interface UseAlarmsReturn {
  alarms: Alarm[];
  loading: boolean;
  refreshing: boolean;
  filter: AlarmStatus | 'all';
  setFilter: (filter: AlarmStatus | 'all') => void;
  refresh: () => void;
}

export function useAlarms(): UseAlarmsReturn {
  const route = useRoute();
  const params = route.params as { stationId?: number } | undefined;
  const stationId = params?.stationId;

  const [alarms, setAlarms] = useState<Alarm[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [filter, setFilter] = useState<AlarmStatus | 'all'>('all');

  const loadData = useCallback(async () => {
    setRefreshing(true);
    try {
      const resp = await alarmApi.getList({
        stationId,
        status: filter === 'all' ? undefined : filter,
        page: 1, pageSize: 50,
      });
      setAlarms(resp.data.items);
    } catch {
      // API not ready
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [stationId, filter]);

  useEffect(() => {
    Promise.resolve().then(() => loadData());
  }, [loadData]);

  const refresh = useCallback(() => {
    loadData();
  }, [loadData]);

  return { alarms, loading, refreshing, filter, setFilter, refresh };
}
