import { renderHook, act } from '@testing-library/react-native';

jest.mock('react-native', () => ({
  Platform: { OS: 'ios' },
}));

import { useNetworkStatus } from '../useNetworkStatus';

describe('useNetworkStatus', () => {
  afterEach(() => {
    jest.clearAllMocks();
    jest.restoreAllMocks();
  });

  it('returns initial connected state', () => {
    const { result } = renderHook(() => useNetworkStatus());
    expect(result.current).toHaveProperty('isConnected');
    expect(result.current).toHaveProperty('isOffline');
    expect(result.current).toHaveProperty('type');
    expect(result.current).toHaveProperty('isInternetReachable');
    expect(result.current).toHaveProperty('refresh');
  });

  it('isOffline is negation of isConnected', () => {
    const { result } = renderHook(() => useNetworkStatus());
    expect(result.current.isOffline).toBe(!result.current.isConnected);
  });

  it('refresh function is callable without throwing', async () => {
    const { result } = renderHook(() => useNetworkStatus());

    await act(async () => {
      await result.current.refresh();
    });

    expect(result.current).toHaveProperty('isConnected');
  });

  it('returns object with all expected properties', () => {
    const { result } = renderHook(() => useNetworkStatus());
    const { isConnected, isInternetReachable, type, isOffline, refresh } = result.current;
    expect(typeof isConnected).toBe('boolean');
    expect(isInternetReachable === null || typeof isInternetReachable === 'boolean').toBe(true);
    expect(typeof type).toBe('string');
    expect(typeof isOffline).toBe('boolean');
    expect(typeof refresh).toBe('function');
  });
});
