/**
 * useAsyncData Hook 测试
 */
import { renderHook, waitFor, act } from '@testing-library/react';
import { useAsyncData } from '../useAsyncData';

describe('useAsyncData', () => {
  it('should start loading on mount', () => {
    const fetcher = vi.fn().mockResolvedValue('result');
    const { result } = renderHook(() => useAsyncData(fetcher, []));
    expect(result.current.loading).toBe(true);
    expect(result.current.data).toBeNull();
    expect(result.current.error).toBeNull();
    expect(result.current.settled).toBe(false);
  });

  it('should return data after successful fetch', async () => {
    const fetcher = vi.fn().mockResolvedValue('test-data');
    const { result } = renderHook(() => useAsyncData(fetcher, []));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.data).toBe('test-data');
    expect(result.current.error).toBeNull();
    expect(result.current.settled).toBe(true);
  });

  it('should set error on fetch failure', async () => {
    const testError = new Error('Network Error');
    const fetcher = vi.fn().mockRejectedValue(testError);
    const { result } = renderHook(() => useAsyncData(fetcher, []));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.data).toBeNull();
    expect(result.current.error).toBe(testError);
    expect(result.current.settled).toBe(true);
  });

  it('should not set error on silent failure', async () => {
    const testError = new Error('Silent Error');
    const fetcher = vi.fn().mockRejectedValue(testError);
    const { result } = renderHook(() =>
      useAsyncData(fetcher, [], { silent: true })
    );

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.error).toBeNull();
    expect(result.current.settled).toBe(true);
  });

  it('should refetch when refetch is called', async () => {
    let callCount = 0;
    const fetcher = vi.fn().mockImplementation(() => {
      callCount++;
      return Promise.resolve(`data-${callCount}`);
    });

    const { result } = renderHook(() => useAsyncData(fetcher, []));

    await waitFor(() => {
      expect(result.current.data).toBe('data-1');
    });

    result.current.refetch();

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.data).toBe('data-2');
    expect(callCount).toBe(2);
  });

  it('should handle setData for optimistic updates', async () => {
    const fetcher = vi.fn().mockResolvedValue('original');
    const { result } = renderHook(() => useAsyncData(fetcher, []));

    await waitFor(() => {
      expect(result.current.data).toBe('original');
    });

    act(() => {
      result.current.setData('optimistic');
    });
    expect(result.current.data).toBe('optimistic');
  });

  it('should not update state after unmount', async () => {
    const fetcher = vi.fn().mockImplementation(
      () => new Promise(resolve => setTimeout(() => resolve('data'), 100))
    );

    const { result, unmount } = renderHook(() => useAsyncData(fetcher, []));
    unmount();

    // 等待异步完成
    await new Promise(resolve => setTimeout(resolve, 200));

    // 卸载后状态不应更新
    expect(result.current.loading).toBe(true); // 卸载前的状态
  });

  it('should handle immediate=false', () => {
    const fetcher = vi.fn().mockResolvedValue('data');
    const { result } = renderHook(() =>
      useAsyncData(fetcher, [], { immediate: false })
    );

    expect(result.current.loading).toBe(false);
    expect(result.current.data).toBeNull();
    expect(fetcher).not.toHaveBeenCalled();
  });

  it('should handle null fetcher result', async () => {
    const fetcher = vi.fn().mockResolvedValue(null);
    const { result } = renderHook(() => useAsyncData(fetcher, []));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.data).toBeNull();
    expect(result.current.settled).toBe(true);
  });

  it('should ignore stale responses (race condition)', async () => {
    let resolve1: (v: string) => void;
    const promise1 = new Promise<string>(resolve => { resolve1 = resolve; });

    const fetcher = vi.fn()
      .mockReturnValueOnce(promise1)
      .mockReturnValueOnce(Promise.resolve('result-2'));

    const { result } = renderHook(() => useAsyncData(fetcher, [undefined]));
    // 等第一次触发
    await new Promise(resolve => setTimeout(resolve, 0));

    // 触发第二次（此时第一次尚未 resolve）
    result.current.refetch();

    await waitFor(() => {
      expect(result.current.data).toBe('result-2');
    });

    // resolve 第一次 (应该被忽略)
    resolve1!('result-1');
    await new Promise(resolve => setTimeout(resolve, 0));

    // 数据应该还是 result-2
    expect(result.current.data).toBe('result-2');
  });
});