/**
 * useNetworkStatus 扩展测试 — branch覆盖率提升
 * 目标: 43% → 70%+ branches
 *
 * 注意: useNetworkStatus 使用 dynamic import('@react-native-community/netinfo')
 * 在Jest环境中，该模块未安装，loadNetInfo() catch → return null 是固有路径。
 * 原生成功路径无法在当前环境中测试（需要实际模块安装）。
 * 本测试聚焦: web路径完整覆盖 + native兜底路径 + refresh + 属性完整性
 */
import { renderHook, act } from '@testing-library/react-native';

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

const mockPlatformOS = { current: 'ios' as 'ios' | 'web' };

jest.mock('react-native', () => ({
  Platform: {
    get OS() { return mockPlatformOS.current; },
  },
}));

import { useNetworkStatus } from '../useNetworkStatus';

function setPlatform(os: 'ios' | 'web') {
  mockPlatformOS.current = os;
}

describe('useNetworkStatus.ext — additional branch coverage', () => {
  afterEach(() => {
    jest.clearAllMocks();
    Object.keys(mockWindowListeners).forEach(k => delete mockWindowListeners[k]);
    mockPlatformOS.current = 'ios';
    Object.defineProperty(navigator, 'onLine', { value: true, configurable: true });
  });

  // ---------- native: loadNetInfo returns null (module not installed) ----------

  it('native: loadNetInfo returns null → setup no-ops, state stays default', async () => {
    setPlatform('ios');
    const { result } = renderHook(() => useNetworkStatus());

    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 100));
    });

    // NetInfo not installed → state remains initial
    expect(result.current.isConnected).toBe(true);
    expect(result.current.type).toBe('unknown');
  });

  it('native: loadNetInfo returns null → refresh no-ops', async () => {
    setPlatform('ios');
    const { result } = renderHook(() => useNetworkStatus());

    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 50));
    });

    await act(async () => {
      await result.current.refresh();
    });

    // No crash, state unchanged
    expect(result.current.isConnected).toBe(true);
  });

  // ---------- web: full event lifecycle ----------

  it('web: initial Promise.resolve sets state via microtask', async () => {
    setPlatform('web');
    Object.defineProperty(navigator, 'onLine', { value: true, configurable: true });

    const { result } = renderHook(() => useNetworkStatus());

    // Before microtask: still initial state
    expect(result.current.isConnected).toBe(true);

    await act(async () => {
      await Promise.resolve();
    });

    // After microtask: state from navigator.onLine
    expect(result.current.isConnected).toBe(true);
    expect(result.current.type).toBe('wifi');
    expect(result.current.isInternetReachable).toBe(true);
  });

  it('web: navigator.onLine=false initial', async () => {
    setPlatform('web');
    Object.defineProperty(navigator, 'onLine', { value: false, configurable: true });

    const { result } = renderHook(() => useNetworkStatus());

    await act(async () => {
      await Promise.resolve();
    });

    expect(result.current.isConnected).toBe(false);
    expect(result.current.isOffline).toBe(true);
    expect(result.current.type).toBe('none');
    expect(result.current.isInternetReachable).toBe(false);
  });

  it('web: offline→online→offline transition', async () => {
    setPlatform('web');
    Object.defineProperty(navigator, 'onLine', { value: true, configurable: true });

    const { result } = renderHook(() => useNetworkStatus());

    await act(async () => {
      await Promise.resolve();
    });

    expect(result.current.isConnected).toBe(true);

    // Go offline
    Object.defineProperty(navigator, 'onLine', { value: false, configurable: true });
    await act(async () => {
      dispatchWindowEvent('offline');
    });
    expect(result.current.isConnected).toBe(false);
    expect(result.current.type).toBe('none');

    // Go online
    Object.defineProperty(navigator, 'onLine', { value: true, configurable: true });
    await act(async () => {
      dispatchWindowEvent('online');
    });
    expect(result.current.isConnected).toBe(true);
    expect(result.current.type).toBe('wifi');

    // Go offline again
    Object.defineProperty(navigator, 'onLine', { value: false, configurable: true });
    await act(async () => {
      dispatchWindowEvent('offline');
    });
    expect(result.current.isConnected).toBe(false);
  });

  it('web: refresh after state change', async () => {
    setPlatform('web');
    Object.defineProperty(navigator, 'onLine', { value: true, configurable: true });

    const { result } = renderHook(() => useNetworkStatus());

    await act(async () => {
      await Promise.resolve();
    });

    // Change navigator state and refresh
    Object.defineProperty(navigator, 'onLine', { value: false, configurable: true });
    await act(async () => {
      await result.current.refresh();
    });

    expect(result.current.isConnected).toBe(false);
    expect(result.current.type).toBe('none');
  });

  it('web: cleanup removes event listeners (unmount)', async () => {
    setPlatform('web');
    const { unmount } = renderHook(() => useNetworkStatus());

    await act(async () => {
      await Promise.resolve();
    });

    // Track listener removal
    const onlineListeners = mockWindowListeners['online'];
    expect(onlineListeners).toBeDefined();
    expect(onlineListeners!.size).toBeGreaterThan(0);

    unmount();

    // After unmount, listeners should be removed
    expect(mockWindowListeners['online']?.size ?? 0).toBe(0);
    expect(mockWindowListeners['offline']?.size ?? 0).toBe(0);
  });

  it('web: mounted=false prevents state update after unmount', async () => {
    setPlatform('web');
    Object.defineProperty(navigator, 'onLine', { value: true, configurable: true });

    const { result, unmount } = renderHook(() => useNetworkStatus());

    await act(async () => {
      await Promise.resolve();
    });

    unmount();

    // Trigger event after unmount — should not affect result
    Object.defineProperty(navigator, 'onLine', { value: false, configurable: true });
    await act(async () => {
      dispatchWindowEvent('offline');
    });

    // State was frozen at time of unmount
    expect(result.current.isConnected).toBe(true);
  });
});
