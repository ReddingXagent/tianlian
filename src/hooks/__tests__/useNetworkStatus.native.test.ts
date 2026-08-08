/**
 * useNetworkStatus native success path — covers loadNetInfo → fetch → addEventListener → refresh
 * Uses moduleNameMapper to mock @react-native-community/netinfo
 */
import { renderHook, act } from '@testing-library/react-native';

// Mock Platform
const mockPlatformOS = { current: 'ios' as string };
jest.mock('react-native', () => ({
  Platform: {
    get OS() { return mockPlatformOS.current; },
  },
}));

import { useNetworkStatus } from '../useNetworkStatus';

// Access the mock for assertions
// eslint-disable-next-line @typescript-eslint/no-require-imports
const netInfoMock = require('@react-native-community/netinfo');

describe('useNetworkStatus.native — NetInfo success path', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockPlatformOS.current = 'ios';
    netInfoMock.fetch.mockResolvedValue({
      isConnected: true,
      isInternetReachable: true,
      type: 'wifi',
    });
    netInfoMock.addEventListener.mockReturnValue(jest.fn());
  });

  it('native: NetInfo fetches initial state and sets up listener', async () => {
    const { result } = renderHook(() => useNetworkStatus());

    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 200));
    });

    expect(netInfoMock.fetch).toHaveBeenCalled();
    expect(netInfoMock.addEventListener).toHaveBeenCalled();
    expect(result.current.isConnected).toBe(true);
    expect(result.current.type).toBe('wifi');
    expect(result.current.isInternetReachable).toBe(true);
  });

  it('native: fetch with isConnected=null → fallback false', async () => {
    netInfoMock.fetch.mockResolvedValue({
      isConnected: null,
      isInternetReachable: null,
      type: 'cellular',
    });

    const { result } = renderHook(() => useNetworkStatus());

    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 200));
    });

    expect(result.current.isConnected).toBe(false);
    expect(result.current.isOffline).toBe(true);
    expect(result.current.type).toBe('cellular');
    expect(result.current.isInternetReachable).toBe(null);
  });

  it('native: addEventListener callback updates state', async () => {
    let listenerCb: ((s: { isConnected: boolean | null; isInternetReachable: boolean | null; type: string }) => void) | null = null;
    const unsub = jest.fn();
    netInfoMock.addEventListener.mockImplementation((cb: (s: { isConnected: boolean | null; isInternetReachable: boolean | null; type: string }) => void) => {
      listenerCb = cb;
      return unsub;
    });

    const { result } = renderHook(() => useNetworkStatus());

    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 200));
    });

    expect(result.current.isConnected).toBe(true);

    await act(async () => {
      listenerCb?.({ isConnected: false, isInternetReachable: false, type: 'none' });
    });

    expect(result.current.isConnected).toBe(false);
    expect(result.current.isOffline).toBe(true);
    expect(result.current.type).toBe('none');
  });

  it('native: addEventListener callback with isConnected=null → fallback false', async () => {
    let listenerCb: ((s: { isConnected: boolean | null; isInternetReachable: boolean | null; type: string }) => void) | null = null;
    const unsub = jest.fn();
    netInfoMock.addEventListener.mockImplementation((cb: (s: { isConnected: boolean | null; isInternetReachable: boolean | null; type: string }) => void) => {
      listenerCb = cb;
      return unsub;
    });

    const { result } = renderHook(() => useNetworkStatus());

    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 200));
    });

    await act(async () => {
      listenerCb?.({ isConnected: null, isInternetReachable: null, type: 'unknown' });
    });

    expect(result.current.isConnected).toBe(false);
    expect(result.current.isOffline).toBe(true);
  });

  it('native: refresh calls fetch and updates state', async () => {
    netInfoMock.fetch
      .mockResolvedValueOnce({ isConnected: true, isInternetReachable: true, type: 'wifi' })
      .mockResolvedValueOnce({ isConnected: false, isInternetReachable: false, type: 'none' });

    const { result } = renderHook(() => useNetworkStatus());

    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 200));
    });

    expect(result.current.isConnected).toBe(true);

    await act(async () => {
      await result.current.refresh();
    });

    expect(result.current.isConnected).toBe(false);
    expect(result.current.isOffline).toBe(true);
    expect(result.current.type).toBe('none');
  });

  it('native: refresh with isConnected=null → fallback false', async () => {
    netInfoMock.fetch
      .mockResolvedValueOnce({ isConnected: true, isInternetReachable: true, type: 'wifi' })
      .mockResolvedValueOnce({ isConnected: null, isInternetReachable: null, type: 'unknown' });

    const { result } = renderHook(() => useNetworkStatus());

    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 200));
    });

    await act(async () => {
      await result.current.refresh();
    });

    expect(result.current.isConnected).toBe(false);
    expect(result.current.isOffline).toBe(true);
  });

  it('native: unmount calls unsubscribe', async () => {
    const unsub = jest.fn();
    netInfoMock.addEventListener.mockReturnValue(unsub);

    const { unmount } = renderHook(() => useNetworkStatus());

    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 200));
    });

    unmount();

    expect(unsub).toHaveBeenCalled();
  });

  it('native: unmount before fetch completes prevents state update', async () => {
    netInfoMock.fetch.mockImplementation(() => new Promise(resolve => setTimeout(() => resolve({
      isConnected: false,
      isInternetReachable: false,
      type: 'none',
    }), 300)));

    const { result, unmount } = renderHook(() => useNetworkStatus());

    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 50));
    });
    unmount();

    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 400));
    });

    expect(result.current.isConnected).toBe(true);
  });

  it('native: unmount before addEventListener setup prevents subscription', async () => {
    netInfoMock.fetch.mockImplementation(() => new Promise(resolve => setTimeout(() => resolve({
      isConnected: true,
      isInternetReachable: true,
      type: 'wifi',
    }), 300)));

    const { unmount } = renderHook(() => useNetworkStatus());

    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 50));
    });
    unmount();

    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 400));
    });

    expect(netInfoMock.addEventListener).not.toHaveBeenCalled();
  });

  it('native: addEventListener callback after unmount is no-op', async () => {
    let listenerCb: ((s: { isConnected: boolean | null; isInternetReachable: boolean | null; type: string }) => void) | null = null;
    netInfoMock.addEventListener.mockImplementation((cb: (s: { isConnected: boolean | null; isInternetReachable: boolean | null; type: string }) => void) => {
      listenerCb = cb;
      return jest.fn();
    });

    const { result, unmount } = renderHook(() => useNetworkStatus());

    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 200));
    });

    unmount();

    await act(async () => {
      listenerCb?.({ isConnected: false, isInternetReachable: false, type: 'none' });
    });

    expect(result.current.isConnected).toBe(true);
  });
});
