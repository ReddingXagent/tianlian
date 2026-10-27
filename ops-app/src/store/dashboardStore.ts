import { create } from 'zustand';
import { DashboardData } from '../types';
import { dashboardApi } from '../services/api';

interface DashboardState {
  data: DashboardData | null;
  loading: boolean;
  error: string | null;
  selectedPeriod: 'week' | 'month' | 'quarter';

  fetchDashboard: () => Promise<void>;
  setPeriod: (period: 'week' | 'month' | 'quarter') => void;
  reset: () => void;
}

export const useDashboardStore = create<DashboardState>((set) => ({
  data: null,
  loading: false,
  error: null,
  selectedPeriod: 'week',

  fetchDashboard: async () => {
    set({ loading: true, error: null });
    try {
      const response = await dashboardApi.getDashboard();
      set({ data: response.data, loading: false });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : '获取看板数据失败';
      set({ loading: false, error: message });
    }
  },

  setPeriod: (period) => {
    set({ selectedPeriod: period });
  },

  reset: () => {
    set({
      data: null,
      loading: false,
      error: null,
      selectedPeriod: 'week',
    });
  },
}));
