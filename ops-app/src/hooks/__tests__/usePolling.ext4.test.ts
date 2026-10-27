/**
 * usePolling ext4 — remaining branch coverage
 * Line 51: execute returns early after unmount (post-await)
 * Line 69: scheduleNext guards (mounted/enabled/retry)
 */
import { renderHook, act } from '@testing-library/react-native';
import { usePolling } from '../usePolling';

describe('usePolling.ext4 — remaining branches', () => {
  beforeEach(() => {
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  // Line 51: execute returns early if unmounted after await
  it('execute after unmount: no state update on resolved promise', async () => {
    const fetcher = jest.fn().mockImplementation(
      () => new Promise(resolve => setTimeout(() => resolve('data'), 1000))
    );

    const { result, unmount } = renderHook(() =>
      usePolling(fetcher, { interval: 5000, immediate: true, maxRetries: 0 })
    );

    // Advance partway so fetcher is in-flight
    await act(async () => {
      await Promise.resolve();
    });

    // Unmount before fetcher resolves
    unmount();

    // Now let the fetcher resolve
    await act(async () => {
      jest.advanceTimersByTime(1000);
      await Promise.resolve();
    });

    // data stays null because unmount prevented setData
    expect(result.current.data).toBeNull();
  });

  // Line 69: scheduleNext returns early when retryCount >= maxRetries
  it('scheduleNext stops after maxRetries exhausted', async () => {
    const fetcher = jest.fn().mockRejectedValue(new Error('fail'));

    const { result } = renderHook(() =>
      usePolling(fetcher, {
        interval: 100,
        maxRetries: 1,
        retryDelay: 50,
        immediate: true,
      })
    );

    // First execute (immediate)
    await act(async () => {
      jest.advanceTimersByTime(50);
      await Promise.resolve();
    });

    // Retry timer fires
    await act(async () => {
      jest.advanceTimersByTime(100);
      await Promise.resolve();
    });

    // After maxRetries=1, no more scheduling
    const callsBefore = fetcher.mock.calls.length;
    await act(async () => {
      jest.advanceTimersByTime(500);
      await Promise.resolve();
    });
    expect(fetcher.mock.calls.length).toBe(callsBefore); // no additional calls
    expect(result.current.error).toBeInstanceOf(Error);
  });

  // Line 69: scheduleNext enabled=false guard
  it('scheduleNext does not schedule when enabled=false', async () => {
    const fetcher = jest.fn().mockResolvedValue('ok');

    renderHook(() =>
      usePolling(fetcher, { interval: 100, enabled: false, immediate: false })
    );

    // Advance timers — no execute should happen
    await act(async () => {
      jest.advanceTimersByTime(500);
      await Promise.resolve();
    });

    expect(fetcher).not.toHaveBeenCalled();
  });
});
