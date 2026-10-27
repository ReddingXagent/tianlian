import { create } from 'zustand';
import { Station, Charger, StationQuery, PaginatedData } from '../types';
import { stationApi } from '../services/api';

interface StationState {
  stations: Station[];
  selectedStation: Station | null;
  chargers: Charger[];
  total: number;
  page: number;
  loading: boolean;
  refreshing: boolean;
  error: string | null;
  fetchStations: (query?: StationQuery) => Promise<void>;
  refreshStations: (query?: StationQuery) => Promise<void>;
  fetchStationDetail: (id: number) => Promise<void>;
  fetchChargers: (stationId: number) => Promise<void>;
  searchStations: (keyword: string) => Promise<void>;
  setSelectedStation: (station: Station | null) => void;
}

export const useStationStore = create<StationState>((set, get) => ({
  stations: [],
  selectedStation: null,
  chargers: [],
  total: 0,
  page: 1,
  loading: false,
  refreshing: false,
  error: null,

  fetchStations: async (query) => {
    set({ loading: true, error: null });
    try {
      const response = await stationApi.getList(query);
      const data: PaginatedData<Station> = response.data;
      set({
        stations: data.items,
        total: data.total,
        page: data.page,
        loading: false,
      });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : '获取站点列表失败';
      set({ loading: false, error: message });
    }
  },

  refreshStations: async (query) => {
    set({ refreshing: true, error: null });
    try {
      const response = await stationApi.getList(query);
      const data: PaginatedData<Station> = response.data;
      set({
        stations: data.items,
        total: data.total,
        page: data.page,
        refreshing: false,
      });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : '刷新站点列表失败';
      set({ refreshing: false, error: message });
    }
  },

  fetchStationDetail: async (id: number) => {
    set({ loading: true, error: null });
    try {
      const response = await stationApi.getDetail(id);
      set({ selectedStation: response.data, loading: false });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : '获取站点详情失败';
      set({ loading: false, error: message });
    }
  },

  fetchChargers: async (stationId: number) => {
    try {
      const response = await stationApi.getChargers(stationId);
      set({ chargers: response.data });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : '获取充电桩列表失败';
      set({ error: message });
    }
  },

  searchStations: async (keyword: string) => {
    set({ loading: true, error: null });
    try {
      const response = await stationApi.search(keyword);
      const data: PaginatedData<Station> = response.data;
      set({
        stations: data.items,
        total: data.total,
        page: data.page,
        loading: false,
      });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : '搜索站点失败';
      set({ loading: false, error: message });
    }
  },

  setSelectedStation: (station: Station | null) => {
    set({
      selectedStation: station,
      chargers: [],
    });
  },
}));