/**
 * useMonitorData Hook 测试
 */
import { renderHook, act, waitFor } from '@testing-library/react-native';

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

const MOCK_SUMMARY = { totalDevices: 10, onlineDevices: 8 };
const MOCK_DEVICES = { data: { items: [{ id: 1, name: 'D1' }] } };
const MOCK_FAULTS = { data: { items: [{ id: 2, name: 'F1' }] } };
const MOCK_ALARMS = { data: { items: [{ id: 3, name: 'A1' }] } };
const MOCK_REALTIME = { total: 10, online: 8 };

function setupMocks() {
  mockGetSummary.mockResolvedValue({ data: MOCK_SUMMARY } as never);
  mockGetFaultDevices.mockResolvedValue(MOCK_FAULTS as never);
  mockGetCriticalAlarms.mockResolvedValue(MOCK_ALARMS as never);
  mockGetDeviceStatusList.mockResolvedValue(MOCK_DEVICES as never);
  mockGetRealtimeOverview.mockResolvedValue({ data: MOCK_REALTIME } as never);
}

describe('useMonitorData', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    setupMocks();
  });

  it('初始挂载加载全量数据', async () => {
    const { result } = renderHook(() => useMonitorData());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.summary).toEqual(MOCK_SUMMARY);
    expect(result.current.devices).toEqual([{ id: 1, name: 'D1' }]);
    expect(result.current.faultDevices).toEqual([{ id: 2, name: 'F1' }]);
    expect(result.current.criticalAlarms).toEqual([{ id: 3, name: 'A1' }]);
    expect(result.current.error).toBeNull();
  });

  it('加载失败时设置error', async () => {
    mockGetSummary.mockRejectedValueOnce(new Error('500') as never);
    const { result } = renderHook(() => useMonitorData());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBe('加载监控数据失败，请下拉刷新重试');
  });

  it('fetchAll(isRefresh=true) 设置refreshing', async () => {
    const { result } = renderHook(() => useMonitorData());
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(async () => { await result.current.fetchAll(true); });
    expect(result.current.refreshing).toBe(false);
    expect(mockGetSummary).toHaveBeenCalled();
  });

  it('fetchAll(isRefresh=false) 设置loading', async () => {
    const { result } = renderHook(() => useMonitorData());
    await waitFor(() => expect(result.current.loading).toBe(false));
    mockGetSummary.mockClear();
    await act(async () => { await result.current.fetchAll(false); });
    expect(mockGetSummary).toHaveBeenCalled();
  });

  it('startPolling(true) 启动实时数据轮询', async () => {
    jest.useFakeTimers();
    const { result } = renderHook(() => useMonitorData());
    await waitFor(() => expect(result.current.devices.length).toBeGreaterThan(0));
    let cleanup: () => void;
    act(() => { cleanup = result.current.startPolling(true); });
    await waitFor(() => expect(result.current.realtimeOverview).toEqual(MOCK_REALTIME));
    act(() => { jest.advanceTimersByTime(10000); });
    await waitFor(() => expect(mockGetRealtimeOverview.mock.calls.length).toBeGreaterThanOrEqual(2));
    act(() => cleanup());
    jest.useRealTimers();
  });

  it('startPolling(false) 不启动轮询', async () => {
    const { result } = renderHook(() => useMonitorData());
    await waitFor(() => expect(result.current.loading).toBe(false));
    let cleanup: () => void;
    act(() => { cleanup = result.current.startPolling(false); });
    expect(mockGetRealtimeOverview).not.toHaveBeenCalled();
    cleanup();
  });

  it('设备为空时不轮询', async () => {
    mockGetDeviceStatusList.mockResolvedValueOnce({ data: { items: [] } } as never);
    const { result } = renderHook(() => useMonitorData());
    await waitFor(() => expect(result.current.loading).toBe(false));
    let cleanup: () => void;
    act(() => { cleanup = result.current.startPolling(true); });
    expect(mockGetRealtimeOverview).not.toHaveBeenCalled();
    cleanup();
  });
});
