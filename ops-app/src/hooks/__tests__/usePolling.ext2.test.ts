/**
 * usePolling ext2 — 深度分支覆盖: default args, enabled toggle, retry schedule, refresh
 * 目标: branches 75% → 90%+
 */
import { renderHook, act } from '@testing-library/react-native';
import { usePolling } from '../usePolling';

describe('usePolling.ext2 — deep branch coverage', () => {
  beforeEach(() => {
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  // Line 24 + 27: default args (interval=15000, maxRetries=3)
  it('uses all default args when no options passed', async () => {
    const fetcher = jest.fn().mockResolvedValue('data');
    const { result } = renderHook(() => usePolling(fetcher));

    expect(result.current.loading).toBe(true);

    await act(async () => {
      await Promise.resolve();
    });

    expect(result.current.data).toBe('data');
    expect(result.current.loading).toBe(false);
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  // Line 71: immediate=false branch (enabled=true but no immediate execute)
  it('enabled=true immediate=false: scheduleNext but no immediate execute', async () => {
    const fetcher = jest.fn().mockResolvedValue('data');
    const { result } = renderHook(() =>
      usePolling(fetcher, { enabled: true, immediate: false, interval: 1000 })
    );

    expect(fetcher).not.toHaveBeenCalled();
    expect(result.current.loading).toBe(false);

    await act(async () => {
      jest.advanceTimersByTime(1000);
      await Promise.resolve();
    });

    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(result.current.data).toBe('data');
  });

  // Line 69: enabled=false → no execute, no schedule
  it('enabled=false: neither immediate execute nor scheduleNext', async () => {
    const fetcher = jest.fn().mockResolvedValue('data');
    const { result } = renderHook(() =>
      usePolling(fetcher, { enabled: false, immediate: true, interval: 500 })
    );

    expect(fetcher).not.toHaveBeenCalled();
    expect(result.current.loading).toBe(true);

    await act(async () => {
      jest.advanceTimersByTime(1000);
    });

    expect(fetcher).not.toHaveBeenCalled();
  });

  // Line 54: retryCount >= maxRetries → scheduleNext returns early
  it('maxRetries=0: no retry scheduled at all', async () => {
    const fetcher = jest.fn().mockRejectedValue(new Error('fail'));
    const { result } = renderHook(() =>
      usePolling(fetcher, {
        interval: 500,
        retryDelay: 200,
        maxRetries: 0,
        immediate: true,
      })
    );

    await act(async () => {
      await Promise.resolve();
    });

    expect(result.current.error?.message).toBe('fail');

    // maxRetries=0 → scheduleNext immediately returns (0 >= 0)
    await act(async () => {
      jest.advanceTimersByTime(2000);
    });

    // Only the immediate call, no retries
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  // Line 51: !mountedRef → scheduleNext returns early (unmount scenario)
  it('scheduleNext after unmount: mountedRef false prevents scheduling', async () => {
    const fetcher = jest.fn().mockResolvedValue('data');
    const { unmount } = renderHook(() =>
      usePolling(fetcher, { interval: 500, immediate: false })
    );

    unmount();

    await act(async () => {
      jest.advanceTimersByTime(1000);
    });

    expect(fetcher).not.toHaveBeenCalled();
  });

  // Line 61: scheduleNextRef.current?.() — null/ref changing gracefully
  it('scheduleNextRef: timer callback handles changing ref gracefully', async () => {
    const fetcher = jest.fn().mockResolvedValue('data');
    const { result, rerender } = renderHook(() =>
      usePolling(fetcher, { interval: 500, immediate: true, enabled: true })
    );

    await act(async () => {
      await Promise.resolve();
    });

    expect(result.current.tickCount).toBe(1);

    rerender({});

    await act(async () => {
      jest.advanceTimersByTime(500);
      await Promise.resolve();
    });

    // Should not crash regardless of scheduleNextRef state
    expect(result.current.tickCount).toBeGreaterThanOrEqual(1);
    expect(fetcher).toHaveBeenCalled();
  });

  // Retry path: successful retry resets retryCount
  it('successful retry: fail then recover, data updates', async () => {
    let callCount = 0;
    const fetcher = jest.fn().mockImplementation(() => {
      callCount++;
      if (callCount === 1) return Promise.reject(new Error('first fail'));
      return Promise.resolve('recovered');
    });

    const { result } = renderHook(() =>
      usePolling(fetcher, {
        interval: 1000,
        retryDelay: 200,
        maxRetries: 3,
        immediate: true,
      })
    );

    // First call (immediate) fails
    await act(async () => {
      await jest.runAllTicks();
    });

    expect(result.current.error?.message).toBe('first fail');

    // scheduleNext was called in mount effect with retryCount=0 → uses interval=1000ms
    // Advance interval → timer fires → execute() (2nd call, succeeds)
    await act(async () => {
      jest.advanceTimersByTime(1000);
      await jest.runAllTicks();
    });

    expect(result.current.data).toBe('recovered');
    expect(result.current.error).toBeNull();
  });

  // enabled toggle: false→true triggers mount effect re-run
  it('enabled false→true: mount effect re-runs and starts polling', async () => {
    const fetcher = jest.fn().mockResolvedValue('data');
    let enabled = false;
    const { result, rerender } = renderHook(() =>
      usePolling(fetcher, { enabled, interval: 500, immediate: true })
    );

    expect(fetcher).not.toHaveBeenCalled();

    enabled = true;
    rerender({});

    await act(async () => {
      await Promise.resolve();
    });

    expect(fetcher).toHaveBeenCalled();
    expect(result.current.data).toBe('data');
  });

  // interval change triggers mount effect re-run
  it('interval change: mount effect re-runs with new interval', async () => {
    const fetcher = jest.fn().mockResolvedValue('data');
    const { rerender } = renderHook(({ interval }) =>
      usePolling(fetcher, { interval, immediate: true, enabled: true }),
      { initialProps: { interval: 1000 } }
    );

    await act(async () => {
      await Promise.resolve();
    });

    expect(fetcher).toHaveBeenCalledTimes(1);

    rerender({ interval: 500 });

    await act(async () => {
      await Promise.resolve();
    });

    // Re-run triggers immediate execute again
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  // refresh when not loading
  it('refresh sets Loading=true then clears on success', async () => {
    const fetcher = jest.fn().mockResolvedValue('data2');
    const { result } = renderHook(() =>
      usePolling(fetcher, { immediate: false, interval: 1000 })
    );

    expect(result.current.loading).toBe(false);

    await act(async () => {
      result.current.refresh();
    });

    await act(async () => {
      await Promise.resolve();
    });

    expect(result.current.data).toBe('data2');
    expect(result.current.loading).toBe(false);
  });

  // refresh when fetcher fails: error set, loading cleared
  it('refresh failure: error set, loading cleared', async () => {
    const fetcher = jest.fn().mockRejectedValue(new Error('refresh fail'));
    const { result } = renderHook(() =>
      usePolling(fetcher, { immediate: false, interval: 1000 })
    );

    await act(async () => {
      result.current.refresh();
    });

    await act(async () => {
      await Promise.resolve();
    });

    expect(result.current.error?.message).toBe('refresh fail');
    expect(result.current.loading).toBe(false);
  });
});
