import { renderHook, act, waitFor } from '@testing-library/react-native';
import { chargingApi } from '../../services/api';
import { useChargingPolling, useActiveCharging } from '../../hooks/useChargingPolling';
import { ChargingStatus } from '../../types';

jest.mock('../../services/api', () => ({
  chargingApi: {
    getStatus: jest.fn(),
    getActiveOrder: jest.fn(),
  },
}));

const mockCompletedStatus: ChargingStatus = {
  orderId: 7,
  orderNo: 'TL20260801007',
  chargerName: 'B-02',
  stationName: '南站',
  status: 'completed',
  power: 0,
  voltage: 380,
  current: 0,
  energy: 30.1,
  duration: 45,
  amount: 36.12,
  startTime: '2026-08-01T10:00:00Z',
};

describe('useChargingPolling.ext4 — intervalRef空分支 + 卸载竞态', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it('manual refresh after polling already stopped (intervalRef=null) still works', async () => {
    // 首次拉取即 completed → 轮询停止并清空 intervalRef;
    // 随后手动 refresh 再次命中 status!=='charging' 且 intervalRef 为 null 的分支
    (chargingApi.getStatus as jest.Mock).mockResolvedValue({ data: mockCompletedStatus });

    const { result } = renderHook(() => useChargingPolling({ orderId: 7 }));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });
    expect(chargingApi.getStatus).toHaveBeenCalledTimes(1);
    expect(result.current.status).toEqual(mockCompletedStatus);

    await act(async () => {
      await result.current.refresh();
    });

    expect(chargingApi.getStatus).toHaveBeenCalledTimes(2);
    expect(result.current.error).toBeNull();
  });

  it('cancels initial fetch when unmounted before microtask flush', async () => {
    (chargingApi.getStatus as jest.Mock).mockReturnValue(new Promise(() => {}));

    const { unmount } = renderHook(() => useChargingPolling({ orderId: 7 }));
    unmount();
    await act(async () => {});

    // 卸载先于微任务冲刷 → cancelled=true, 请求不应发出
    expect(chargingApi.getStatus).not.toHaveBeenCalled();
  });

  it('useActiveCharging cancels check when unmounted before microtask flush', async () => {
    (chargingApi.getActiveOrder as jest.Mock).mockReturnValue(new Promise(() => {}));

    const { unmount } = renderHook(() => useActiveCharging());
    unmount();
    await act(async () => {});

    expect(chargingApi.getActiveOrder).not.toHaveBeenCalled();
  });
});
