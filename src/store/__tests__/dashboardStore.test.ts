import { act } from '@testing-library/react-native';
import { useDashboardStore } from '../dashboardStore';
import { dashboardApi } from '../../services/api';
import { DashboardData } from '../../types';

jest.mock('../../services/api', () => ({
  dashboardApi: {
    getDashboard: jest.fn(),
  },
}));

const MOCK_DASHBOARD_DATA: DashboardData = {
  stats: {
    totalOrders: 150,
    completedOrders: 120,
    pendingOrders: 30,
    avgCompletionHours: 4.5,
    onTimeRate: 85,
  },
  deviceHealth: {
    total: 100,
    online: 85,
    offline: 5,
    fault: 8,
    maintenance: 2,
    onlineRate: 85,
  },
  alarmTrends: [
    { date: '2024-01-01', total: 10, critical: 2, warning: 5, info: 3 },
    { date: '2024-01-02', total: 8, critical: 1, warning: 4, info: 3 },
  ],
  workOrderTrends: [
    { date: '2024-01-01', created: 15, completed: 12 },
    { date: '2024-01-02', created: 12, completed: 10 },
  ],
  topFaultDevices: [
    { deviceId: 1, deviceName: '充电桩CH001', stationName: '充电站A', faultCount: 5 },
    { deviceId: 2, deviceName: '逆变器INV001', stationName: '充电站B', faultCount: 3 },
  ],
};

describe('useDashboardStore', () => {
  beforeEach(() => {
    useDashboardStore.getState().reset();
    jest.clearAllMocks();
  });

  describe('initial state', () => {
    it('should have correct initial state', () => {
      const state = useDashboardStore.getState();
      expect(state.data).toBeNull();
      expect(state.loading).toBe(false);
      expect(state.error).toBeNull();
      expect(state.selectedPeriod).toBe('week');
    });
  });

  describe('fetchDashboard', () => {
    it('should fetch dashboard data successfully', async () => {
      (dashboardApi.getDashboard as jest.Mock).mockResolvedValue({ data: MOCK_DASHBOARD_DATA });

      await act(async () => {
        await useDashboardStore.getState().fetchDashboard();
      });

      const state = useDashboardStore.getState();
      expect(state.data).toEqual(MOCK_DASHBOARD_DATA);
      expect(state.loading).toBe(false);
      expect(state.error).toBeNull();
    });

    it('should handle fetch failure', async () => {
      (dashboardApi.getDashboard as jest.Mock).mockRejectedValue(new Error('Network error'));

      await act(async () => {
        await useDashboardStore.getState().fetchDashboard();
      });

      const state = useDashboardStore.getState();
      expect(state.data).toBeNull();
      expect(state.loading).toBe(false);
      expect(state.error).toBe('Network error');
    });

    it('should handle non-Error failure', async () => {
      (dashboardApi.getDashboard as jest.Mock).mockRejectedValue('Unknown error');

      await act(async () => {
        await useDashboardStore.getState().fetchDashboard();
      });

      const state = useDashboardStore.getState();
      expect(state.error).toBe('获取看板数据失败');
    });
  });

  describe('setPeriod', () => {
    it('should change period', () => {
      useDashboardStore.getState().setPeriod('month');
      expect(useDashboardStore.getState().selectedPeriod).toBe('month');

      useDashboardStore.getState().setPeriod('quarter');
      expect(useDashboardStore.getState().selectedPeriod).toBe('quarter');

      useDashboardStore.getState().setPeriod('week');
      expect(useDashboardStore.getState().selectedPeriod).toBe('week');
    });
  });

  describe('reset', () => {
    it('should reset all state', () => {
      useDashboardStore.setState({
        data: MOCK_DASHBOARD_DATA,
        loading: true,
        error: 'error',
        selectedPeriod: 'quarter',
      });

      useDashboardStore.getState().reset();

      const state = useDashboardStore.getState();
      expect(state.data).toBeNull();
      expect(state.loading).toBe(false);
      expect(state.error).toBeNull();
      expect(state.selectedPeriod).toBe('week');
    });
  });
});
