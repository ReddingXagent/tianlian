/**
 * useDashboard Hook 测试
 */
import { renderHook, act, waitFor } from '@testing-library/react-native';
import { useDashboard } from '../useDashboard';

// Stable mock functions to prevent re-render loops
const mockFetchStations = jest.fn().mockResolvedValue(undefined);
const mockFetchOrders = jest.fn().mockResolvedValue(undefined);

jest.mock('../../store/stationStore', () => ({
  useStationStore: () => ({
    stations: [{ id: 1, name: '站点A', code: 'S001' }],
    fetchStations: mockFetchStations,
  }),
}));
jest.mock('../../store/workOrderStore', () => ({
  useWorkOrderStore: () => ({
    fetchOrders: mockFetchOrders,
  }),
}));
jest.mock('../../services/api', () => ({
  dashboardApi: {
    getStats: jest.fn(),
  },
}));

// eslint-disable-next-line import/first
import { dashboardApi } from '../../services/api';

const mockStats = { totalStations: 5, activeAlarms: 3, pendingOrders: 7 };

describe('useDashboard', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockFetchStations.mockResolvedValue(undefined);
    mockFetchOrders.mockResolvedValue(undefined);
    (dashboardApi.getStats as jest.Mock).mockResolvedValue({ data: mockStats });
  });

  it('初始加载: stores+stats获取成功', async () => {
    const { result } = renderHook(() => useDashboard());
    await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 10000 });
    expect(result.current.stats).toEqual(mockStats);
    expect(result.current.stations).toHaveLength(1);
  });

  it('stats API失败 → stats=null但loading=false', async () => {
    (dashboardApi.getStats as jest.Mock).mockRejectedValue(new Error('404'));
    const { result } = renderHook(() => useDashboard());
    await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 10000 });
    expect(result.current.stats).toBeNull();
  });

  it('refresh → 重新加载', async () => {
    const { result } = renderHook(() => useDashboard());
    await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 10000 });
    const statsCallsBefore = (dashboardApi.getStats as jest.Mock).mock.calls.length;
    await act(async () => { result.current.refresh(); });
    await waitFor(() => expect((dashboardApi.getStats as jest.Mock).mock.calls.length).toBeGreaterThan(statsCallsBefore), { timeout: 10000 });
  });

  it('refreshing → 初始false, 加载结束false', async () => {
    const { result } = renderHook(() => useDashboard());
    await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 10000 });
    expect(result.current.refreshing).toBe(false);
  });
});
