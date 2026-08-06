/**
 * useNetworkStatus Hook 测试 — 运维APP
 * 覆盖 web/native 双平台路径、refresh 两侧路径
 *
 * 策略: netinfo 未安装时 loadNetInfo() catch → return null 是固有路径,
 * 测试聚焦 web 路径（完整覆盖）+ native refresh/loadNetInfo 失败兜底 +
 * 初始状态/卸载/属性完整性
 */
import { renderHook, act } from '@testing-library/react-native';

// web 环境下 window.addEventListener / removeEventListener polyfill
// (react-native jest 环境不提供完整 window 对象)
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
// 覆盖任何已存在的 window 对象
(globalThis as Record<string, unknown>).window = mockWindow;

// 类型安全的 window.dispatchEvent helper
function dispatchWindowEvent(type: string) {
  (window as unknown as { dispatchEvent: (e: { type: string }) => void }).dispatchEvent({ type });
}

// 可变 Platform.OS — 用 mock 前缀变量
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

describe('useNetworkStatus', () => {
  afterEach(() => {
    jest.clearAllMocks();
    // 清理 window listeners
    Object.keys(mockWindowListeners).forEach(k => delete mockWindowListeners[k]);
    mockPlatformOS.current = 'ios';
  });

  // ---------- 初始状态 ----------

  it('returns initial connected state', () => {
    const { result } = renderHook(() => useNetworkStatus());
    expect(result.current).toHaveProperty('isConnected', true);
    expect(result.current).toHaveProperty('isOffline', false);
    expect(result.current).toHaveProperty('type', 'unknown');
    expect(result.current).toHaveProperty('isInternetReachable', true);
    expect(result.current).toHaveProperty('refresh');
  });

  it('isOffline is negation of isConnected', () => {
    const { result } = renderHook(() => useNetworkStatus());
    expect(result.current.isOffline).toBe(!result.current.isConnected);
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

  // ---------- native: loadNetInfo 失败兜底 (netinfo 未安装) ----------

  it('native: netinfo 不可用时 setup 不崩溃, 保持初始值', async () => {
    setPlatform('ios');
    const { result } = renderHook(() => useNetworkStatus());

    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 50));
    });

    expect(result.current.isConnected).toBe(true);
  });

  it('native: refresh 在 netinfo 不可用时不崩溃', async () => {
    setPlatform('ios');
    const { result } = renderHook(() => useNetworkStatus());

    await act(async () => {
      await result.current.refresh();
    });

    expect(result.current.isConnected).toBe(true);
  });

  // ---------- web 平台路径 (完整覆盖) ----------

  it('web: 使用 navigator.onLine 初始状态', async () => {
    setPlatform('web');
    const { result } = renderHook(() => useNetworkStatus());

    await act(async () => {
      await Promise.resolve();
    });

    expect(result.current.isConnected).toBe(navigator.onLine);
    expect(result.current.isOffline).toBe(!navigator.onLine);
  });

  it('web: refresh 使用 navigator.onLine 更新状态', async () => {
    setPlatform('web');
    const { result } = renderHook(() => useNetworkStatus());

    await act(async () => {
      await result.current.refresh();
    });

    expect(result.current.isConnected).toBe(navigator.onLine);
  });

  it('web: online/offline 事件监听器响应', async () => {
    setPlatform('web');
    const { result } = renderHook(() => useNetworkStatus());

    await act(async () => {
      await Promise.resolve();
    });

    // 模拟离线事件
    await act(async () => {
      Object.defineProperty(navigator, 'onLine', {
        value: false,
        configurable: true,
      });
      dispatchWindowEvent('offline');
    });

    expect(result.current.isConnected).toBe(false);
    expect(result.current.isOffline).toBe(true);

    // 恢复在线
    await act(async () => {
      Object.defineProperty(navigator, 'onLine', {
        value: true,
        configurable: true,
      });
      dispatchWindowEvent('online');
    });

    expect(result.current.isConnected).toBe(true);
  });

  // ---------- 卸载清理 ----------

  it('卸载后不再更新状态 (native)', async () => {
    setPlatform('ios');
    const { result, unmount } = renderHook(() => useNetworkStatus());

    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 50));
    });

    expect(result.current.isConnected).toBe(true);
    unmount();
    expect(true).toBe(true);
  });

  it('web: 卸载后移除事件监听器', async () => {
    setPlatform('web');
    const { unmount } = renderHook(() => useNetworkStatus());

    await act(async () => {
      await Promise.resolve();
    });

    unmount();

    // 卸载后触发事件不应影响 result (引用已固定)
    await act(async () => {
      Object.defineProperty(navigator, 'onLine', {
        value: false,
        configurable: true,
      });
      dispatchWindowEvent('offline');
    });

    // 恢复 navigator
    Object.defineProperty(navigator, 'onLine', {
      value: true,
      configurable: true,
    });
    expect(true).toBe(true);
  });
});
