/**
 * useNetworkStatus ext4 — L41/L42/L63/L71 branch closure
 * F1216: branchMap实勘 —
 *   b2 arm1 (L42 `mod.default ?? mod` else臂): 既有mock有default导出, else臂从未走 — 本文件mock无default → require返回裸模块对象
 *   b4 arm1 (L63 `if (mounted)` false臂): handler挂载后卸载前从未触发过事件
 *   b5 arm1 (L71 `if (mounted)` false臂): 卸载后微任务才resolve从未覆盖
 * 手法: netinfo mock工厂返回无default对象 → loadNetInfo走L42 else臂; web事件在卸载后触发 → L63 false臂;
 *       卸载后flush微任务 → L71 false臂。
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

const mockPlatformOS = { current: 'ios' as 'ios' | 'web' };

jest.mock('react-native', () => ({
  Platform: {
    get OS() { return mockPlatformOS.current; },
  },
}));

// 无default导出的裸模块mock → loadNetInfo L41-42 `mod.default ?? mod` 走 else 臂
const mockNetInfoModule = {
  fetch: jest.fn().mockResolvedValue({
    isConnected: false,
    isInternetReachable: false,
    type: 'cellular',
  }),
  addEventListener: jest.fn().mockReturnValue(jest.fn()),
};
jest.mock('@react-native-community/netinfo', () => mockNetInfoModule);

import { useNetworkStatus } from '../useNetworkStatus';

describe('useNetworkStatus.ext4 — L41/L63/L71 branch closure', () => {
  afterEach(() => {
    jest.clearAllMocks();
    Object.keys(mockWindowListeners).forEach(k => delete mockWindowListeners[k]);
    mockPlatformOS.current = 'ios';
    Object.defineProperty(navigator, 'onLine', { value: true, configurable: true });
  });

  it('native: 裸模块无default导出 → L42 `mod.default ?? mod` else臂 + fetch/subscribe全链', async () => {
    setPlatform('ios');

    const { result } = renderHook(() => useNetworkStatus());

    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 100));
    });

    // loadNetInfo: mod.default=undefined → else臂取裸模块 → fetch返回mock state
    expect(mockNetInfoModule.fetch).toHaveBeenCalled();
    expect(mockNetInfoModule.addEventListener).toHaveBeenCalled();
    expect(result.current.isConnected).toBe(false);
    expect(result.current.type).toBe('cellular');
    expect(result.current.isOffline).toBe(true);
  });

  it('web: navigator.onLine=false → type:"none", isOffline=true (initial microtask)', async () => {
    setPlatform('web');
    Object.defineProperty(navigator, 'onLine', { value: false, configurable: true });

    const { result } = renderHook(() => useNetworkStatus());

    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 50));
    });

    // initial microtask 走 getWebNetworkState() → onLine=false → else 臂
    expect(result.current.isConnected).toBe(false);
    expect(result.current.type).toBe('none');
    expect(result.current.isInternetReachable).toBe(false);
    expect(result.current.isOffline).toBe(true);
  });

  it('web: offline event while mounted → L63 mounted=true 臂 + else 臂再覆盖', async () => {
    setPlatform('web');
    Object.defineProperty(navigator, 'onLine', { value: true, configurable: true });

    const { result } = renderHook(() => useNetworkStatus());

    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 50));
    });

    expect(result.current.type).toBe('wifi'); // 前置确认: 初始走 then 臂

    // online → offline 转换: handler 内 getWebNetworkState() 走 else 臂
    Object.defineProperty(navigator, 'onLine', { value: false, configurable: true });
    await act(async () => {
      (window as unknown as { dispatchEvent: (e: { type: string }) => void }).dispatchEvent({ type: 'offline' });
    });

    expect(result.current.isConnected).toBe(false);
    expect(result.current.type).toBe('none');
    expect(result.current.isOffline).toBe(true);
    expect(result.current.isOffline).toBe(true);
  });

  it('web: event after unmount → L63 mounted=false false臂 (状态冻结)', async () => {
    setPlatform('web');
    Object.defineProperty(navigator, 'onLine', { value: true, configurable: true });

    const { result, unmount } = renderHook(() => useNetworkStatus());

    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 50));
    });
    expect(result.current.type).toBe('wifi');

    unmount();

    // 卸载后触发事件: handler 内 if(mounted) 走 false 臂 → 状态不变
    Object.defineProperty(navigator, 'onLine', { value: false, configurable: true });
    await act(async () => {
      (window as unknown as { dispatchEvent: (e: { type: string }) => void }).dispatchEvent({ type: 'offline' });
    });

    expect(result.current.isConnected).toBe(true); // 冻结在卸载时状态
    expect(result.current.type).toBe('wifi');
  });

  it('web: microtask resolve after unmount → L71 mounted=false false臂', async () => {
    setPlatform('web');
    Object.defineProperty(navigator, 'onLine', { value: false, configurable: true });

    const { result, unmount } = renderHook(() => useNetworkStatus());

    // 不等微任务完成直接卸载
    unmount();

    // 微任务在卸载后才resolve → Promise.resolve().then 内 if(mounted) 走 false 臂
    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 50));
    });

    // 状态停留在初始 useState 默认值 (isConnected: true, type: 'unknown')
    expect(result.current.isConnected).toBe(true);
    expect(result.current.type).toBe('unknown');
  });

  it('web: handler called after unmount → L63 if(mounted) false臂 (闭包handler直接调用)', async () => {
    setPlatform('web');
    Object.defineProperty(navigator, 'onLine', { value: true, configurable: true });

    const { result, unmount } = renderHook(() => useNetworkStatus());

    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 50));
    });
    expect(result.current.type).toBe('wifi'); // 前置: mounted期间走true臂

    // 持有handler闭包引用 (web路径注册的online/offline监听函数)
    const offlineHandlers = Array.from(mockWindowListeners['offline'] ?? []);
    expect(offlineHandlers.length).toBeGreaterThan(0);

    unmount(); // mounted=false, cleanup移除window监听但handler闭包仍在测试手里

    Object.defineProperty(navigator, 'onLine', { value: false, configurable: true });
    // 手动直接调用已卸载的handler → 进入函数体但 if(mounted) 走 false 臂
    await act(async () => {
      offlineHandlers.forEach(h => (h as () => void)());
    });

    // 状态冻结: false臂跳过setNetworkState
    expect(result.current.isConnected).toBe(true);
    expect(result.current.type).toBe('wifi');
  });

  it('web: refresh() with onLine=false → sync setState 走 else 臂', async () => {
    setPlatform('web');
    Object.defineProperty(navigator, 'onLine', { value: false, configurable: true });

    const { result } = renderHook(() => useNetworkStatus());

    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 50));
    });
    expect(result.current.type).toBe('none');

    // refresh web 分支: setNetworkState(getWebNetworkState()) 同步走 else 臂
    await act(async () => {
      await result.current.refresh();
    });

    expect(result.current.isConnected).toBe(false);
    expect(result.current.type).toBe('none');
  });
});

function setPlatform(os: 'ios' | 'web') {
  mockPlatformOS.current = os;
}
