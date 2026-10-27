import { useState, useCallback, useEffect } from 'react';
import { useStationStore } from '../store/stationStore';
import { Station } from '../types';

interface UseStationListReturn {
  stations: Station[];
  loading: boolean;
  refreshing: boolean;
  search: string;
  setSearch: (search: string) => void;
  filteredStations: Station[];
  refresh: () => void;
}

export function useStationList(): UseStationListReturn {
  const { stations, loading, fetchStations } = useStationStore();
  const [refreshing, setRefreshing] = useState(false);
  const [search, setSearch] = useState('');

  const loadData = useCallback(async (searchKey?: string) => {
    setRefreshing(true);
    try {
      await fetchStations({ page: 1, pageSize: 100, search: searchKey });
    } finally {
      setRefreshing(false);
    }
  }, [fetchStations]);

  useEffect(() => {
    Promise.resolve().then(() => loadData());
  }, [loadData]);

  const refresh = useCallback(() => {
    loadData(search);
  }, [loadData, search]);

  const filteredStations = search
    ? stations.filter((s) =>
        s.name.includes(search) || s.code.includes(search) || (s.address?.includes(search) ?? false)
      )
    : stations;

  return { stations, loading, refreshing, search, setSearch, filteredStations, refresh };
}
