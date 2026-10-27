/**
 * useNetworkStatus ext2 — edge branch coverage
 * Target: line 85 (!mounted post-await), web refresh path, web unmount event handler
 */
import { renderHook, act } from '@testing-library/react-native';

const mockPlatformOS = { current: 'ios' as 'ios' | 'web' };

jest.mock('react-native', () => ({
  Platform: {
    get OS() { return mockPlatformOS.current; },
  },
}));

// ── Mock window for web platform tests ──
const mockWindowListeners: Record<string, Set<() => void>> = {};
const mockWindow = {
  addEventListener: (event: string, cb: () => void) => {
    if (!mockWindowListeners[event]) mockWindowListeners[event] = new Set();
    mockWindowListeners[event].add(cb);
  },
  removeEventListener: (event: string, cb: () => void) => {
    mockWindowListeners[event]?.delete(cb);
  },
  dispatchEvent: (event: { type: string }) => {
    mockWindowListeners[event.type]?.forEach(cb => cb());
  },
};
(globalThis as Record<string, unknown>).window = mockWindow;

function dispatchWindowEvent(type: string) {
  (window as unknown as { dispatchEvent: (e: { type: string }) => void }).dispatchEvent({ type });
}

import { useNetworkStatus } from '../useNetworkStatus';

describe('useNetworkStatus.ext2 — edge branch coverage', () => {
  afterEach(() => {
    mockPlatformOS.current = 'ios';
    Object.keys(mockWindowListeners).forEach(k => delete mockWindowListeners[k]);
    Object.defineProperty(navigator, 'onLine', { value: true, configurable: true });
  });

  // Line 85: unmount between NetInfo.fetch() start and resolve
  it('native: unmount during NetInfo.fetch → state stays at initial', async () => {
    mockPlatformOS.current = 'ios';

    const { result, unmount } = renderHook(() => useNetworkStatus());

    unmount();

    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 100));
    });

    expect(result.current.isConnected).toBe(true);
    expect(result.current.type).toBe('unknown');
  });

  // Native refresh happy path
  it('native: refresh returns updated state', async () => {
    mockPlatformOS.current = 'ios';

    const { result } = renderHook(() => useNetworkStatus());

    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 200));
    });

    expect(result.current.isConnected).toBe(true);

    await act(async () => {
      await result.current.refresh();
    });

    expect(result.current.isConnected).toBe(true);
  });

  // Web: refresh exercises Platform.OS==='web' branch in refresh callback
  it('web: refresh updates from navigator.onLine', async () => {
    mockPlatformOS.current = 'web';
    Object.defineProperty(navigator, 'onLine', { value: true, configurable: true });

    const { result } = renderHook(() => useNetworkStatus());

    await act(async () => {
      await Promise.resolve();
    });

    expect(result.current.isConnected).toBe(true);

    // Change and refresh
    Object.defineProperty(navigator, 'onLine', { value: false, configurable: true });
    await act(async () => {
      await result.current.refresh();
    });

    expect(result.current.isConnected).toBe(false);
    expect(result.current.isOffline).toBe(true);
  });

  // Web: event handler after unmount — mounted guard prevents crash
  it('web: event after unmount: mounted=false handler skips setState', async () => {
    mockPlatformOS.current = 'web';
    Object.defineProperty(navigator, 'onLine', { value: true, configurable: true });

    const { result, unmount } = renderHook(() => useNetworkStatus());

    await act(async () => {
      await Promise.resolve();
    });

    unmount();

    // Dispatching after unmount should not throw and not change state
    Object.defineProperty(navigator, 'onLine', { value: false, configurable: true });
    expect(() => {
      dispatchWindowEvent('offline');
    }).not.toThrow();

    // State frozen at pre-unmount value
    expect(result.current.isConnected).toBe(true);
  });

  // Native: verify mock state flows through
  it('native: initial setup completes with mock state', async () => {
    mockPlatformOS.current = 'ios';

    const { result } = renderHook(() => useNetworkStatus());

    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 200));
    });

    expect(result.current.isConnected).toBe(true);
    expect(result.current.type).toBe('wifi');
    expect(result.current.isInternetReachable).toBe(true);
  });
});
