import { renderHook, act, waitFor } from '@testing-library/react-native';
import { AppState } from 'react-native';
import NetInfo from '@react-native-community/netinfo';
import { chargingApi } from '../../services/api';
import { useChargingPolling, useActiveCharging } from '../../hooks/useChargingPolling';
import { ChargingStatus } from '../../types';

jest.mock('../../services/api', () => ({
  chargingApi: {
    getStatus: jest.fn(),
    getActiveOrder: jest.fn(),
  },
}));

const mockChargingStatus: ChargingStatus = {
  orderId: 1,
  orderNo: 'TL20260601001',
  chargerName: 'A-01',
  stationName: '中心站',
  status: 'charging',
  power: 85.5,
  voltage: 380,
  current: 225,
  energy: 22.3,
  duration: 15,
  amount: 28.99,
  startTime: '2026-06-01T10:00:00Z',
};

describe('useChargingPolling', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it('should fetch initial status on mount', async () => {
    (chargingApi.getStatus as jest.Mock).mockResolvedValue({ data: mockChargingStatus });

    const { result } = renderHook(() =>
      useChargingPolling({ orderId: 1, interval: 3000 })
    );

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(chargingApi.getStatus).toHaveBeenCalledWith(1);
    expect(result.current.status).toEqual(mockChargingStatus);
  });

  it('should poll at specified interval', async () => {
    (chargingApi.getStatus as jest.Mock).mockResolvedValue({ data: mockChargingStatus });

    renderHook(() => useChargingPolling({ orderId: 1, interval: 3000 }));

    // Wait for initial fetch
    await act(async () => {
      jest.advanceTimersByTime(100);
    });

    // Clear initial call count
    (chargingApi.getStatus as jest.Mock).mockClear();

    // Advance past the interval
    await act(async () => {
      jest.advanceTimersByTime(3000);
    });

    expect(chargingApi.getStatus).toHaveBeenCalledTimes(1);

    // Advance another interval
    await act(async () => {
      jest.advanceTimersByTime(3000);
    });

    expect(chargingApi.getStatus).toHaveBeenCalledTimes(2);
  });

  it('should stop polling when charging completes', async () => {
    const completedStatus = { ...mockChargingStatus, status: 'completed' as const };
    (chargingApi.getStatus as jest.Mock).mockResolvedValue({ data: completedStatus });

    const onComplete = jest.fn();

    renderHook(() =>
      useChargingPolling({ orderId: 1, interval: 3000, onComplete })
    );

    await act(async () => {
      jest.advanceTimersByTime(100);
    });

    expect(onComplete).toHaveBeenCalledWith(completedStatus);

    // Clear and advance - should NOT poll again
    (chargingApi.getStatus as jest.Mock).mockClear();
    await act(async () => {
      jest.advanceTimersByTime(3000);
    });

    expect(chargingApi.getStatus).not.toHaveBeenCalled();
  });

  it('should handle error state', async () => {
    (chargingApi.getStatus as jest.Mock).mockRejectedValue(new Error('获取失败'));

    const onError = jest.fn();

    const { result } = renderHook(() =>
      useChargingPolling({ orderId: 1, interval: 3000, onError })
    );

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.error).toBe('获取失败');
    expect(onError).toHaveBeenCalled();
  });

  it('should not poll when disabled', () => {
    (chargingApi.getStatus as jest.Mock).mockResolvedValue({ data: mockChargingStatus });

    renderHook(() => useChargingPolling({ orderId: 1, interval: 3000, enabled: false }));

    expect(chargingApi.getStatus).not.toHaveBeenCalled();
  });

  it('should refresh on demand', async () => {
    (chargingApi.getStatus as jest.Mock).mockResolvedValue({ data: mockChargingStatus });

    const { result } = renderHook(() =>
      useChargingPolling({ orderId: 1, interval: 3000 })
    );

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    const updatedStatus = { ...mockChargingStatus, power: 90 };
    (chargingApi.getStatus as jest.Mock).mockResolvedValue({ data: updatedStatus });

    await act(async () => {
      await result.current.refresh();
    });

    expect(result.current.status?.power).toBe(90);
  });

  it('should call onStatusChange when status updates', async () => {
    (chargingApi.getStatus as jest.Mock).mockResolvedValue({ data: mockChargingStatus });

    const onStatusChange = jest.fn();

    renderHook(() =>
      useChargingPolling({ orderId: 1, interval: 3000, onStatusChange })
    );

    await act(async () => {
      jest.advanceTimersByTime(100);
    });

    expect(onStatusChange).toHaveBeenCalledWith(mockChargingStatus);
  });
});

describe('useActiveCharging', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('should return active order id when charging is in progress', async () => {
    (chargingApi.getActiveOrder as jest.Mock).mockResolvedValue({ data: mockChargingStatus });

    const { result } = renderHook(() => useActiveCharging());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.activeOrderId).toBe(1);
  });

  it('should return null when no active charging', async () => {
    (chargingApi.getActiveOrder as jest.Mock).mockResolvedValue({ data: null });

    const { result } = renderHook(() => useActiveCharging());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.activeOrderId).toBeNull();
  });

  it('should handle API error', async () => {
    (chargingApi.getActiveOrder as jest.Mock).mockRejectedValue(new Error('查询失败'));

    const { result } = renderHook(() => useActiveCharging());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.error).toBe('查询失败');
    expect(result.current.activeOrderId).toBeNull();
  });
});

describe('useChargingPolling 前后台/网络感知 (F32同型补齐)', () => {
  type NetInfoCb = (state: { isConnected: boolean; isInternetReachable: boolean }) => void;
  let appStateCb: ((state: string) => void) | null = null;
  let netInfoCb: NetInfoCb | null = null;

  beforeEach(() => {
    jest.clearAllMocks();
    jest.useFakeTimers();
    appStateCb = null;
    netInfoCb = null;
    jest.spyOn(AppState, 'addEventListener').mockImplementation(((_e: string, cb: unknown) => {
      appStateCb = cb as (state: string) => void;
      return { remove: jest.fn() };
    }) as typeof AppState.addEventListener);
    (NetInfo.addEventListener as jest.Mock).mockImplementation((cb: NetInfoCb) => {
      netInfoCb = cb;
      cb({ isConnected: true, isInternetReachable: true });
      return jest.fn();
    });
    (chargingApi.getStatus as jest.Mock).mockResolvedValue({ data: mockChargingStatus });
  });

  afterEach(() => {
    jest.useRealTimers();
    jest.restoreAllMocks();
  });

  it('切后台: 暂停轮询, paused=true, 不再请求', async () => {
    const { result } = renderHook(() => useChargingPolling({ orderId: 1, interval: 3000 }));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.paused).toBe(false);

    const calls = (chargingApi.getStatus as jest.Mock).mock.calls.length;
    act(() => appStateCb?.('background'));
    expect(result.current.paused).toBe(true);

    await act(async () => {
      jest.advanceTimersByTime(10000);
    });
    expect((chargingApi.getStatus as jest.Mock).mock.calls.length).toBe(calls);
  });

  it('回前台: 立即补拉一次并恢复轮询', async () => {
    const { result } = renderHook(() => useChargingPolling({ orderId: 1, interval: 3000 }));
    await waitFor(() => expect(result.current.loading).toBe(false));
    act(() => appStateCb?.('background'));
    const calls = (chargingApi.getStatus as jest.Mock).mock.calls.length;

    await act(async () => {
      appStateCb?.('active');
    });
    expect(result.current.paused).toBe(false);
    // 立即补拉
    expect((chargingApi.getStatus as jest.Mock).mock.calls.length).toBe(calls + 1);

    // 轮询恢复
    await act(async () => {
      jest.advanceTimersByTime(3000);
    });
    expect((chargingApi.getStatus as jest.Mock).mock.calls.length).toBe(calls + 2);
  });

  it('确认离线: 暂停; 恢复联网: 立即补拉', async () => {
    const { result } = renderHook(() => useChargingPolling({ orderId: 1, interval: 3000 }));
    await waitFor(() => expect(result.current.loading).toBe(false));

    const calls = (chargingApi.getStatus as jest.Mock).mock.calls.length;
    act(() => netInfoCb?.({ isConnected: false, isInternetReachable: false }));
    expect(result.current.paused).toBe(true);
    await act(async () => {
      jest.advanceTimersByTime(9000);
    });
    expect((chargingApi.getStatus as jest.Mock).mock.calls.length).toBe(calls);

    await act(async () => {
      netInfoCb?.({ isConnected: true, isInternetReachable: true });
    });
    expect(result.current.paused).toBe(false);
    expect((chargingApi.getStatus as jest.Mock).mock.calls.length).toBe(calls + 1);
  });

  it('pauseWhenInactive=false: 后台仍轮询', async () => {
    const { result } = renderHook(() =>
      useChargingPolling({ orderId: 1, interval: 3000, pauseWhenInactive: false }),
    );
    await waitFor(() => expect(result.current.loading).toBe(false));

    act(() => appStateCb?.('background'));
    expect(result.current.paused).toBe(false);

    const calls = (chargingApi.getStatus as jest.Mock).mock.calls.length;
    await act(async () => {
      jest.advanceTimersByTime(3000);
    });
    expect((chargingApi.getStatus as jest.Mock).mock.calls.length).toBe(calls + 1);
  });
});