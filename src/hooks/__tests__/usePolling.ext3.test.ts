/**
 * usePolling ext3 — race condition & unmount branch coverage
 * Target lines: 51 (execute !mounted entry), 54 (execute !mounted post-await),
 *               61 (catch !mounted), 69 (scheduleNext !mounted), 71 (retryDelay cond)
 */
import { renderHook, act } from '@testing-library/react-native';
import { usePolling } from '../usePolling';

describe('usePolling.ext3 — race/unmount branches', () => {
  beforeEach(() => {
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  // Line 54: execute resolves but mounted=false → skip setData
  it('unmount during fetcher resolve: skips state update after await', async () => {
    let resolveFn: (v: string) => void = () => {};
    const slowFetcher = jest.fn(
      () => new Promise<string>((resolve) => { resolveFn = resolve; })
    );

    const { result, unmount } = renderHook(() =>
      usePolling(slowFetcher, { immediate: true, interval: 5000 })
    );

    // Fetcher is in-flight, unmount before resolving
    unmount();

    await act(async () => {
      resolveFn('late-data');
      await Promise.resolve();
    });

    // State should remain initial (data=null) since unmounted before resolve
    expect(result.current.data).toBeNull();
  });

  // Line 61: catch block with !mounted → skip setError
  it('unmount during fetcher reject: skips error set after await', async () => {
    let rejectFn: (e: Error) => void = () => {};
    const slowFailingFetcher = jest.fn(
      () => new Promise<string>((_resolve, reject) => { rejectFn = reject; })
    );

    const { result, unmount } = renderHook(() =>
      usePolling(slowFailingFetcher, { immediate: true, interval: 5000 })
    );

    unmount();

    await act(async () => {
      rejectFn(new Error('late-fail'));
      await Promise.resolve();
    });

    // Error should not be set since unmounted
    expect(result.current.error).toBeNull();
  });

  // Line 51: execute called when mounted=false (manual call via ref)
  // Achieved by: unmount then advance timer that was already scheduled
  it('execute after unmount via timer: early return no state change', async () => {
    const fetcher = jest.fn().mockResolvedValue('timer-data');
    const { result, unmount } = renderHook(() =>
      usePolling(fetcher, { immediate: false, interval: 300 })
    );

    // Timer is scheduled by mount effect
    unmount();

    await act(async () => {
      jest.advanceTimersByTime(500);
      await Promise.resolve();
    });

    // Fetcher not called because mounted=false guard in scheduleNext prevents timer
    // or timer fires but execute returns early
    expect(result.current.data).toBeNull();
  });

  // Line 71: retryDelay branch — retryCount > 0 uses retryDelay instead of interval
  it('retry path uses retryDelay (not interval) for scheduling', async () => {
    let callCount = 0;
    const fetcher = jest.fn().mockImplementation(() => {
      callCount++;
      if (callCount <= 2) return Promise.reject(new Error(`fail-${callCount}`));
      return Promise.resolve('success-on-3rd');
    });

    const { result } = renderHook(() =>
      usePolling(fetcher, {
        interval: 10000,
        retryDelay: 200,
        maxRetries: 5,
        immediate: true,
      })
    );

    // Immediate call fails (callCount=1, retryCount becomes 1)
    await act(async () => {
      await jest.runAllTicks();
    });
    expect(result.current.error?.message).toBe('fail-1');

    // scheduleNext with retryCount=1 → delay=retryDelay=200ms (not interval=10000ms)
    // The mount effect's scheduleNext call was made when retryCount was 0 → delay=interval
    // But retryCount incremented before scheduleNext fires via timer callback chain
    // The timer from mount effect uses interval (10s). Advance that:
    await act(async () => {
      jest.advanceTimersByTime(10000); // first timer uses interval (retryCount was 0 at schedule)
      await jest.runAllTicks();
    });
    // 2nd call fails (callCount=2, retryCount becomes 2)
    expect(result.current.error?.message).toBe('fail-2');

    // Now retryCount=2 → scheduleNext uses retryDelay=200ms
    await act(async () => {
      jest.advanceTimersByTime(200); // retryDelay
      await jest.runAllTicks();
    });
    // 3rd call succeeds
    expect(result.current.data).toBe('success-on-3rd');
    expect(result.current.error).toBeNull();
  });

  // Line 69: scheduleNext called with mounted=false via cleanup
  it('scheduleNext guards: enabled=true but unmounted → no timer set', async () => {
    const fetcher = jest.fn().mockResolvedValue('data');
    const { unmount } = renderHook(() =>
      usePolling(fetcher, { immediate: false, interval: 200, enabled: true })
    );

    unmount();

    // After unmount, advance timers — scheduleNext was called in mount effect
    // but mountedRef.current=false prevents setTimeout
    await act(async () => {
      jest.advanceTimersByTime(1000);
    });

    expect(fetcher).not.toHaveBeenCalled();
  });
});
