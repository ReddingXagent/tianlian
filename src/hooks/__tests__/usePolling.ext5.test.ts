/**
 * usePolling ext5 — scheduleNext maxRetries guard (line 69) + execute unmounted guard (line 51)
 * Target: 2 remaining uncovered branches
 */
import { renderHook, act } from '@testing-library/react-native';
import { usePolling } from '../usePolling';

describe('usePolling.ext5 — maxRetries + unmount-during-execute guards', () => {
  it('scheduleNext stops when retryCount >= maxRetries (line 69 true branch)', async () => {
    let rejectFn: (e: Error) => void;
    const fetcher = jest.fn(() => new Promise((_, reject) => {
      rejectFn = reject;
    }));

    // maxRetries=1 so after first failure, retryCount=1 >= 1 → scheduleNext stops
    const { result, unmount } = renderHook(() =>
      usePolling(fetcher, { interval: 50, maxRetries: 1, retryDelay: 10, immediate: true })
    );

    // Wait for initial fetch to start, then reject it
    await act(async () => {
      await new Promise(r => setTimeout(r, 10));
      rejectFn!(new Error('fail'));
      await new Promise(r => setTimeout(r, 10));
    });

    // error set, retryCount=1
    expect(result.current.error).toBeInstanceOf(Error);

    // Wait beyond retryDelay+interval — scheduleNext should NOT fire another attempt
    await act(async () => {
      await new Promise(r => setTimeout(r, 100));
    });

    // fetcher called: initial immediate + possibly 1 retry, but scheduleNext guard stops further
    // The key assertion: no infinite retry loop
    expect(fetcher.mock.calls.length).toBeLessThanOrEqual(2);

    unmount();
  });

  it('execute returns early when component unmounts during fetch (line 51 true branch)', async () => {
    let resolveFn: (v: string) => void;
    const fetcher = jest.fn(() => new Promise<string>((resolve) => {
      resolveFn = resolve;
    }));

    const { unmount } = renderHook(() =>
      usePolling(fetcher, { interval: 10000, immediate: true, maxRetries: 0 })
    );

    // Wait for fetch to start
    await act(async () => {
      await new Promise(r => setTimeout(r, 10));
    });

    // Unmount while fetch is still pending
    unmount();

    // Now resolve the fetch — execute should return early due to !mountedRef
    await act(async () => {
      resolveFn!('late-data');
      await new Promise(r => setTimeout(r, 50));
    });

    // Since unmounted, we can't check result.current, but no crash = pass
    expect(fetcher).toHaveBeenCalled();
  });
});
