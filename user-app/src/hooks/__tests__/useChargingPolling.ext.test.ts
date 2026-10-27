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

describe('useChargingPolling.ext — remaining branch coverage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  // line 83: non-Error throw → '获取充电状态失败' message
  it('handles non-Error throw with generic message', async () => {
    (chargingApi.getStatus as jest.Mock).mockRejectedValue('string error');

    const { result } = renderHook(() =>
      useChargingPolling({ orderId: 1, interval: 3000 }),
    );

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.error).toBe('获取充电状态失败');
  });

  // line 86: non-Error throw does NOT call onError
  it('does not call onError for non-Error throw', async () => {
    (chargingApi.getStatus as jest.Mock).mockRejectedValue({ code: 500 });
    const onError = jest.fn();

    renderHook(() =>
      useChargingPolling({ orderId: 1, interval: 3000, onError }),
    );

    await act(async () => {
      jest.advanceTimersByTime(100);
    });

    expect(onError).not.toHaveBeenCalled();
  });

  // line 76: status !== 'charging' AND intervalRef.current is null (already cleared)
  it('does not crash when clearing already-null interval on completion', async () => {
    const completedStatus = { ...mockChargingStatus, status: 'completed' as const };
    (chargingApi.getStatus as jest.Mock).mockResolvedValue({ data: completedStatus });

    renderHook(() =>
      useChargingPolling({ orderId: 1, interval: 3000 }),
    );

    await act(async () => {
      jest.advanceTimersByTime(100);
    });

    // Completed - interval already cleared internally
    expect(chargingApi.getStatus).toHaveBeenCalledTimes(1);

    // Advance time - no more polling
    await act(async () => {
      jest.advanceTimersByTime(6000);
    });

    expect(chargingApi.getStatus).toHaveBeenCalledTimes(1);
  });
});

describe('useActiveCharging.ext — non-Error throw branch', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  // line 136: non-Error throw in useActiveCharging
  it('handles non-Error throw with generic message', async () => {
    (chargingApi.getActiveOrder as jest.Mock).mockRejectedValue('network fail');

    const { result } = renderHook(() => useActiveCharging());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.error).toBe('检查进行中充电失败');
    expect(result.current.activeOrderId).toBeNull();
  });
});
