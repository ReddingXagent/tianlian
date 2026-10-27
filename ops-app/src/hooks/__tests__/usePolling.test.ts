/**
 * usePolling Hook 测试 — 运维APP
 */
import { renderHook, act, waitFor } from '@testing-library/react-native';
import { usePolling } from '../usePolling';

describe('usePolling (Ops App)', () => {
  beforeEach(() => {
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it('应在 immediate=true 时立即执行一次', async () => {
    const fetcher = jest.fn().mockResolvedValue({ count: 5 });
    const { result } = renderHook(() => usePolling(fetcher, { interval: 10000 }));

    await waitFor(() => {
      expect(result.current.data).toEqual({ count: 5 });
    });
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBeNull();
    expect(result.current.tickCount).toBe(1);
  });

  it('应按 interval 自动轮询', async () => {
    const fetcher = jest.fn()
      .mockResolvedValueOnce('a')
      .mockResolvedValueOnce('b');
    const { result } = renderHook(() => usePolling(fetcher, { interval: 5000 }));

    await waitFor(() => expect(result.current.data).toBe('a'));
    act(() => { jest.advanceTimersByTime(5000); });
    await waitFor(() => expect(result.current.data).toBe('b'));
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it('应在 fetcher 抛错时设置 error', async () => {
    const fetcher = jest.fn().mockRejectedValue(new Error('timeout'));
    const { result } = renderHook(() => usePolling(fetcher, { interval: 5000 }));

    await waitFor(() => {
      expect(result.current.error?.message).toBe('timeout');
    });
  });

  it('应在 enabled=false 时不执行', () => {
    const fetcher = jest.fn().mockResolvedValue('data');
    renderHook(() => usePolling(fetcher, { interval: 1000, enabled: false }));
    expect(fetcher).not.toHaveBeenCalled();
  });

  it('refresh 应手动触发获取', async () => {
    const fetcher = jest.fn().mockResolvedValue('data');
    const { result } = renderHook(() => usePolling(fetcher, { interval: 10000 }));

    await waitFor(() => expect(result.current.data).toBe('data'));
    act(() => { result.current.refresh(); });
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2));
  });

  it('连续失败超过 maxRetries 应停止轮询', async () => {
    const fetcher = jest.fn()
      .mockRejectedValueOnce(new Error('e1'))
      .mockRejectedValueOnce(new Error('e2'));

    const { result } = renderHook(() =>
      usePolling(fetcher, { interval: 1000, maxRetries: 2, retryDelay: 1000 })
    );

    await waitFor(() => expect(result.current.error?.message).toBe('e1'));
    act(() => { jest.advanceTimersByTime(1000); });
    await waitFor(() => expect(result.current.error?.message).toBe('e2'));
    act(() => { jest.advanceTimersByTime(5000); });
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it('组件卸载应清理 timer', async () => {
    const fetcher = jest.fn().mockResolvedValue('data');
    const { result, unmount } = renderHook(() => usePolling(fetcher, { interval: 1000 }));
    await waitFor(() => expect(result.current.data).toBe('data'));
    unmount();
    act(() => { jest.advanceTimersByTime(10000); });
    // 卸载后不应继续调用
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
});
