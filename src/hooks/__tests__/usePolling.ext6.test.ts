/**
 * usePolling ext6 — F1217: 卸载后 timer 回调仍触发 scheduleNext (line 69 true branch)
 * 此前缺口根因(F1217实勘): 卸载 cleanup 会 clearTimeout, 排队中的 timer 永不触发
 * → scheduleNextRef.current?.() 从未在卸载后被调; 而既有测试的 scheduleNext 调用
 * 点(effect 内/maxRetries 的 timer 回调)发生时组件均挂载 → L69 !mountedRef 真臂零计数。
 * 真路径: timer 回调已触发(时钟已过) → await execute() in-flight → 此时卸载
 * (clearTimeout 对已触发 timer 无效) → resolve → execute post-await guard return
 * → callback 继续 → scheduleNextRef.current?.() → L69 !mountedRef 真臂。
 */
import { renderHook, act } from '@testing-library/react-native';
import { usePolling } from '../usePolling';

describe('usePolling.ext6 — scheduleNext unmounted guard', () => {
  it('timer-fires-then-unmount: resolve continues callback into scheduleNext guard (line 69 true branch)', async () => {
    let resolveFn: (v: string) => void;
    const fetcher = jest.fn(
      () =>
        new Promise<string>((resolve) => {
          resolveFn = resolve;
        })
    );

    // immediate=false: 初始只 scheduleNext 排 20ms timer, fetcher 未被调
    const { unmount } = renderHook(() =>
      usePolling(fetcher, { interval: 20, immediate: false, maxRetries: 5 })
    );

    // 等 40ms: timer 回调已触发, execute() in-flight (fetcher 被调, promise pending)
    await act(async () => {
      await new Promise((r) => setTimeout(r, 40));
    });
    expect(fetcher).toHaveBeenCalledTimes(1);

    // 此时卸载 — clearTimeout 对已触发的 timer 无效, 回调仍在 await execute() 处悬挂
    unmount();

    // resolve → execute 走 L54 post-await guard return → 回调继续
    // → scheduleNextRef.current?.() → L69 !mountedRef 真臂 return(不再排新 timer)
    await act(async () => {
      resolveFn!('late-data');
      await new Promise((r) => setTimeout(r, 80));
    });

    // 守卫生效: scheduleNext 未再排 timer, fetcher 维持 1 次
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it('immediate variant: second (timer-driven) execute resolves after unmount, guard blocks reschedule', async () => {
    let resolveFn: (v: string) => void;
    const fetcher = jest.fn(
      () =>
        new Promise<string>((resolve) => {
          resolveFn = resolve;
        })
    );

    const { unmount } = renderHook(() =>
      usePolling(fetcher, { interval: 20, immediate: true, maxRetries: 5 })
    );

    // 等 40ms: immediate execute(call#1) 悬挂未 resolve → timer 回调触发 execute(call#2,
    // resolveFn 被覆盖, call#1 的 promise 永不 resolve — 无碍, 挂起的 await 不影响计数)
    await act(async () => {
      await new Promise((r) => setTimeout(r, 40));
    });
    expect(fetcher.mock.calls.length).toBeGreaterThanOrEqual(2);

    unmount();

    // resolve call#2 → post-await guard return → scheduleNext L69 真臂, 无新 timer
    await act(async () => {
      resolveFn!('late');
      await new Promise((r) => setTimeout(r, 80));
    });

    const callsAfter = fetcher.mock.calls.length;
    await act(async () => {
      await new Promise((r) => setTimeout(r, 100));
    });
    // 再等 100ms(>>interval=20) fetcher 计数不变 = 卸载后未再调度
    expect(fetcher.mock.calls.length).toBe(callsAfter);
  });
});
