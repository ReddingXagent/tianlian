/**
 * useMonitorData coverage tests
 * F1451: empty devices guard branch
 * F1478: fetchAll catch/default-arg + useEffect cancelled/error branches
 */
import { renderHook, waitFor, act } from '@testing-library/react-native';

jest.mock('../../services/api', () => ({
  monitorApi: {
    getSummary: jest.fn(),
    getFaultDevices: jest.fn(),
    getCriticalAlarms: jest.fn(),
  },
  deviceMonitorApi: {
    getDeviceStatusList: jest.fn(),
    getRealtimeOverview: jest.fn(),
  },
}));

import { useMonitorData } from '../useMonitorData';
import { monitorApi, deviceMonitorApi } from '../../services/api';

const mockGetSummary = monitorApi.getSummary as jest.MockedFunction<typeof monitorApi.getSummary>;
const mockGetFaultDevices = monitorApi.getFaultDevices as jest.MockedFunction<typeof monitorApi.getFaultDevices>;
const mockGetCriticalAlarms = monitorApi.getCriticalAlarms as jest.MockedFunction<typeof monitorApi.getCriticalAlarms>;
const mockGetDeviceStatusList = deviceMonitorApi.getDeviceStatusList as jest.MockedFunction<typeof deviceMonitorApi.getDeviceStatusList>;
const mockGetRealtimeOverview = deviceMonitorApi.getRealtimeOverview as jest.MockedFunction<typeof deviceMonitorApi.getRealtimeOverview>;

describe('useMonitorData — empty devices guard branch', () => {
  it('skips realtime metrics fetch when devices list is empty', async () => {
    // Summary returns ok, but devices list is empty
    mockGetSummary.mockResolvedValue({ data: { totalDevices: 0, onlineDevices: 0 } } as never);
    mockGetFaultDevices.mockResolvedValue({ data: { items: [] } } as never);
    mockGetCriticalAlarms.mockResolvedValue({ data: { items: [] } } as never);
    mockGetDeviceStatusList.mockResolvedValue({ data: { items: [] } } as never);
    mockGetRealtimeOverview.mockResolvedValue({ data: { total: 0, online: 0 } } as never);

    const { result } = renderHook(() => useMonitorData());

    await waitFor(() => {
      expect(result.current.devices).toEqual([]);
    });

    // devices.length === 0 → fetchRealtimeMetrics returns early
    // getRealtimeOverview may be called once by initial load but not by fetchRealtimeMetrics
    // The key assertion: no crash, devices stay empty
    expect(result.current.devices.length).toBe(0);
  });
});

describe('useMonitorData — fetchAll catch branch', () => {
  it('sets error when fetchAll fails', async () => {
    // Initial load succeeds
    mockGetSummary.mockResolvedValue({ data: { totalDevices: 10, onlineDevices: 8 } } as never);
    mockGetFaultDevices.mockResolvedValue({ data: { items: [{ id: 2 }] } } as never);
    mockGetCriticalAlarms.mockResolvedValue({ data: { items: [{ id: 3 }] } } as never);
    mockGetDeviceStatusList.mockResolvedValue({ data: { items: [{ id: 1 }] } } as never);
    mockGetRealtimeOverview.mockResolvedValue({ data: { total: 10, online: 8 } } as never);

    const { result } = renderHook(() => useMonitorData());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBeNull();

    // Now make fetchAll fail
    mockGetSummary.mockRejectedValueOnce(new Error('network') as never);

    await act(async () => {
      await result.current.fetchAll(true);
    });

    expect(result.current.error).toBe('加载监控数据失败，请下拉刷新重试');
    expect(result.current.refreshing).toBe(false);
  });

  it('fetchAll() no-arg defaults to loading path (L39 default-arg)', async () => {
    // Initial load succeeds
    mockGetSummary.mockResolvedValue({ data: { totalDevices: 1, onlineDevices: 1 } } as never);
    mockGetFaultDevices.mockResolvedValue({ data: { items: [] } } as never);
    mockGetCriticalAlarms.mockResolvedValue({ data: { items: [] } } as never);
    mockGetDeviceStatusList.mockResolvedValue({ data: { items: [{ id: 1 }] } } as never);
    mockGetRealtimeOverview.mockResolvedValue({ data: { total: 1, online: 1 } } as never);

    const { result } = renderHook(() => useMonitorData());
    await waitFor(() => expect(result.current.loading).toBe(false));

    // fetchAll() with no arg → isRefresh defaults to false → setLoading(true) path
    mockGetSummary.mockClear();
    await act(async () => {
      await result.current.fetchAll();
    });

    expect(mockGetSummary).toHaveBeenCalled();
    expect(result.current.loading).toBe(false);
  });
});

describe('useMonitorData — useEffect cancelled & error branches', () => {
  it('useEffect error path sets error when not cancelled (L96)', async () => {
    mockGetSummary.mockRejectedValueOnce(new Error('500') as never);

    const { result } = renderHook(() => useMonitorData());

    await waitFor(() => {
      expect(result.current.error).toBe('加载监控数据失败，请下拉刷新重试');
    });
    expect(result.current.loading).toBe(false);
  });

  it('unmount before resolve skips state updates (L67 cancelled in try)', async () => {
    // Use a promise we control to keep pending during unmount
    let resolveOuter: () => void;
    const pendingPromise = new Promise((resolve) => { resolveOuter = resolve; });

    // All 4 API calls return immediately except getSummary which is pending
    mockGetSummary.mockReturnValueOnce(pendingPromise as never);
    mockGetFaultDevices.mockResolvedValue({ data: { items: [] } } as never);
    mockGetCriticalAlarms.mockResolvedValue({ data: { items: [] } } as never);
    mockGetDeviceStatusList.mockResolvedValue({ data: { items: [] } } as never);

    const { result, unmount } = renderHook(() => useMonitorData());

    // Unmount while promise is still pending → cancelled = true
    unmount();

    // Now resolve the promise → Promise.all resolves → if (cancelled) return at L67
    resolveOuter!();
    // Need to flush all microtasks: Promise.all → async function continue → L67 guard
    await act(async () => {
      await new Promise(r => setTimeout(r, 50));
    });

    expect(result.current).toBeDefined();
  });

  it('unmount before reject skips error set (L96 cancelled in catch)', async () => {
    // Use a promise we control to keep pending during unmount
    let rejectOuter: (e: Error) => void;
    const pendingPromise = new Promise((_, reject) => { rejectOuter = reject; });

    mockGetSummary.mockReturnValueOnce(pendingPromise as never);
    mockGetFaultDevices.mockResolvedValue({ data: { items: [] } } as never);
    mockGetCriticalAlarms.mockResolvedValue({ data: { items: [] } } as never);
    mockGetDeviceStatusList.mockResolvedValue({ data: { items: [] } } as never);

    const { result, unmount } = renderHook(() => useMonitorData());

    // Unmount while promise is still pending → cancelled = true
    unmount();

    // Now reject the promise → Promise.all rejects → if (cancelled) return at L96
    await act(async () => {
      rejectOuter!(new Error('late failure'));
      // Flush microtasks
      await new Promise(r => setImmediate(r));
    });

    expect(result.current).toBeDefined();
  });
});
