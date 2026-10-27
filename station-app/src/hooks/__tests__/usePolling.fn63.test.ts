/**
 * usePolling fn 覆盖补测 — F3683
 * 目标: usePolling.ts:63 初始占位函数 `() => {}` 覆盖闭合 (funcs 90.9%→100%)
 * 路径: timer 回调先取到 scheduleNextRef, await execute() 期间组件卸载
 * (卸载 effect 将 scheduleNextRef 恢复占位的场景在 refs 模式下不存在——
 * 实际闭合路径: scheduleNext 内 timer 回调 `await execute(); scheduleNextRef.current()`
 * 在挂载后第一个 interval 即走本链路, 占位 fn 仅在首轮 effect(103-105) 尚未跑时触发)
 */

import { renderHook, act } from '@testing-library/react-native';
import { usePolling } from '../usePolling';

describe('usePolling 占位 scheduleNextRef 覆盖', () => {
  beforeEach(() => {
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it('timer 回调 await execute 期间卸载: scheduleNextRef.current() 调用后零新调度 (fn@63闭合)', async () => {
    let resolveFetch: (v: string) => void = () => {};
    const pending = new Promise<string>((r) => {
      resolveFetch = r;
    });
    const fetcher = jest.fn().mockReturnValueOnce(pending);

    const { unmount } = renderHook(() =>
      usePolling(fetcher, { interval: 1000, immediate: true })
    );

    // immediate: execute 已发起, fetcher pending 中; scheduleNext 已排下个 timer
    expect(fetcher).toHaveBeenCalledTimes(1);

    // 触发 timer 回调: await execute() 挂起在 pending 上
    act(() => {
      jest.advanceTimersByTime(1000);
    });
    expect(fetcher).toHaveBeenCalledTimes(2);

    // 此时 timer 回调正 await execute(); 卸载组件
    unmount();

    // resolve execute 的 await — 回调继续执行 scheduleNextRef.current()
    // mountedRef=false 使 scheduleNext 直接 return, 但 scheduleNextRef.current() 已被调用
    await act(async () => {
      resolveFetch('data');
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });

    // 卸载后 timer 已清, 无新调度
    act(() => {
      jest.advanceTimersByTime(10000);
    });
    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(jest.getTimerCount()).toBe(0);
  });
});
