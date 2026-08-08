import { renderHook, act } from '@testing-library/react-native';

// Mock useAppLifecycle
jest.mock('../useAppLifecycle', () => ({
  useAppLifecycle: () => ({
    appState: 'active',
    isForeground: true,
    isConnected: true,
  }),
}));

jest.mock('../../services/api', () => ({
  chargingApi: {
    getStatus: jest.fn(),
    getActiveOrder: jest.fn(),
  },
}));

// eslint-disable-next-line import/first
import { useChargingPolling } from '../useChargingPolling';

describe('useChargingPolling.ext3 — L76 non-Error throw in fetchStatus', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  // L76: `if (err instanceof Error)` false branch — non-Error throw
  it('sets fallback error message when fetchStatus throws non-Error', async () => {
    const { chargingApi } = require('../../services/api');
    chargingApi.getStatus.mockRejectedValue('network down');

    const { result, unmount } = renderHook(() =>
      useChargingPolling({ orderId: 1 }),
    );

    await act(async () => {
      // Flush the microtask queue to let the rejected promise settle
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(result.current.error).toBe('获取充电状态失败');
    expect(result.current.loading).toBe(false);

    unmount();
  });
});
