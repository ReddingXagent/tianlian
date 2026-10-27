import { renderHook, act, waitFor } from '@testing-library/react-native';
import { chargingApi } from '../../services/api';
import { useChargingPolling } from '../../hooks/useChargingPolling';
import { ChargingStatus } from '../../types';

jest.mock('../../services/api', () => ({
  chargingApi: {
    getStatus: jest.fn(),
    getActiveOrder: jest.fn(),
  },
}));

jest.mock('../../hooks/useAppLifecycle', () => ({
  useAppLifecycle: () => ({ isForeground: true, isConnected: true }),
}));

const chargingStatus: ChargingStatus = {
  orderId: 1, orderNo: 'TL001', chargerName: 'A-01', stationName: '中心站',
  status: 'charging', power: 85, voltage: 380, current: 225,
  energy: 22.3, duration: 15, amount: 28.99, startTime: '2026-06-01T10:00:00Z',
};

const completedStatus: ChargingStatus = {
  ...chargingStatus,
  status: 'completed',
};

describe('useChargingPolling.ext2 — interval clear branch (L76)', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it('clears interval when poll returns non-charging after interval starts', async () => {
    // First call: charging (interval gets set up after this returns)
    // Second call (from interval tick): completed → hits L76 if(intervalRef.current)
    (chargingApi.getStatus as jest.Mock)
      .mockResolvedValueOnce({ data: chargingStatus })   // initial fetchStatus
      .mockResolvedValueOnce({ data: completedStatus }); // interval tick

    const onComplete = jest.fn();

    const { result } = renderHook(() =>
      useChargingPolling({ orderId: 1, interval: 1000, onComplete }),
    );

    // Wait for initial fetch to resolve
    await waitFor(() => {
      expect(result.current.status?.status).toBe('charging');
    });

    // Advance timers to trigger interval tick → second getStatus call
    await act(async () => {
      jest.advanceTimersByTime(1000);
      await Promise.resolve();
    });

    // After completed status, onComplete should fire and interval should be cleared
    await waitFor(() => {
      expect(onComplete).toHaveBeenCalledWith(completedStatus);
    });

    // Advance more time — no more API calls should happen (interval cleared)
    const callCount = (chargingApi.getStatus as jest.Mock).mock.calls.length;
    await act(async () => {
      jest.advanceTimersByTime(3000);
    });
    expect((chargingApi.getStatus as jest.Mock).mock.calls.length).toBe(callCount);
  });
});
