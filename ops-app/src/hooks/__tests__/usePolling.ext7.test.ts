/**
 * usePolling coverage test — targets mountedRef.current=false guard in execute
 * F1451: usePolling.ts branches 96.42%→100%
 */
import { renderHook, act } from '@testing-library/react-native';
import { usePolling } from '../usePolling';

describe('usePolling — unmount guard branch', () => {
  it('skips state update when component unmounts during fetch', async () => {
    let resolveFetch: (value: string) => void = () => {};
    const fetcher = jest.fn(
      () =>
        new Promise<string>((resolve) => {
          resolveFetch = resolve;
        })
    );

    const { result, unmount } = renderHook(() =>
      usePolling(fetcher, { interval: 60000, immediate: true, enabled: true })
    );

    // Fetcher is called (immediate=true)
    expect(fetcher).toHaveBeenCalledTimes(1);

    // Unmount while fetch is in-flight
    unmount();

    // Now resolve the fetch — execute() should see mountedRef.current=false and return early
    act(() => {
      resolveFetch('result');
    });

    // data should still be null because mountedRef was false when resolve came back
    expect(result.current.data).toBeNull();
  });
});
