import { create } from 'zustand';
import { Station, Device, Alarm, PaginatedData } from '../types';
import { stationApi } from '../services/api';

interface StationState {
  stations: Station[];
  selectedStation: Station | null;
  devices: Device[];
  alarms: Alarm[];
  total: number;
  page: number;
  loading: boolean;
  error: string | null;
  fetchStations: (params?: { page?: number; pageSize?: number; search?: string }) => Promise<void>;
  fetchStationDetail: (id: number) => Promise<void>;
  fetchStationDevices: (stationId: number) => Promise<void>;
  fetchStationAlarms: (stationId: number, params?: { page?: number; pageSize?: number }) => Promise<void>;
  setSelectedStation: (station: Station | null) => void;
}

export const useStationStore = create<StationState>((set, get) => ({
  stations: [],
  selectedStation: null,
  devices: [],
  alarms: [],
  total: 0,
  page: 1,
  loading: false,
  error: null,

  fetchStations: async (params) => {
    set({ loading: true, error: null });
    try {
      const response = await stationApi.getList(params);
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

  fetchStationDevices: async (stationId: number) => {
    try {
      const response = await stationApi.getDevices(stationId);
      set({ devices: response.data });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : '获取设备列表失败';
      set({ error: message });
    }
  },

  fetchStationAlarms: async (stationId: number, params) => {
    try {
      const response = await stationApi.getAlarms(stationId, params);
      set({ alarms: response.data.items });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : '获取告警列表失败';
      set({ error: message });
    }
  },

  setSelectedStation: (station: Station | null) => {
    set({
      selectedStation: station,
      devices: [],
      alarms: [],
    });
  },
}));