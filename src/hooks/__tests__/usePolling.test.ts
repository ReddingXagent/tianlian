/**
 * usePolling Hook 测试
 */
import { renderHook, act, waitFor } from '@testing-library/react-native';
import { usePolling } from '../usePolling';

describe('usePolling', () => {
  beforeEach(() => {
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it('应在 immediate=true 时立即执行一次', async () => {
    const fetcher = jest.fn().mockResolvedValue({ value: 42 });
    const { result } = renderHook(() => usePolling(fetcher, { interval: 5000, immediate: true }));

    await waitFor(() => {
      expect(result.current.data).toEqual({ value: 42 });
    });
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBeNull();
    expect(result.current.tickCount).toBe(1);
  });

  it('应在 immediate=false 时不立即执行', () => {
    const fetcher = jest.fn().mockResolvedValue('data');
    renderHook(() => usePolling(fetcher, { interval: 5000, immediate: false }));
    expect(fetcher).not.toHaveBeenCalled();
  });

  it('应按 interval 自动轮询', async () => {
    const fetcher = jest.fn()
      .mockResolvedValueOnce(1)
      .mockResolvedValueOnce(2)
      .mockResolvedValueOnce(3);
    const { result } = renderHook(() => usePolling(fetcher, { interval: 1000 }));

    await waitFor(() => expect(result.current.data).toBe(1));

    act(() => { jest.advanceTimersByTime(1000); });
    await waitFor(() => expect(result.current.data).toBe(2));

    act(() => { jest.advanceTimersByTime(1000); });
    await waitFor(() => expect(result.current.data).toBe(3));

    expect(fetcher).toHaveBeenCalledTimes(3);
  });

  it('应在 fetcher 抛错时设置 error', async () => {
    const fetcher = jest.fn().mockRejectedValue(new Error('Network error'));
    const { result } = renderHook(() => usePolling(fetcher, { interval: 5000 }));

    await waitFor(() => {
      expect(result.current.error).toBeInstanceOf(Error);
      expect(result.current.error?.message).toBe('Network error');
    });
    expect(result.current.loading).toBe(false);
  });

  it('应在 enabled=false 时不轮询', async () => {
    const fetcher = jest.fn().mockResolvedValue('data');
    renderHook(() => usePolling(fetcher, { interval: 1000, enabled: false }));
    expect(fetcher).not.toHaveBeenCalled();
  });

  it('应在组件卸载时清除 timer', () => {
    const fetcher = jest.fn().mockResolvedValue('data');
    const { unmount } = renderHook(() => usePolling(fetcher, { interval: 1000 }));
    unmount();
    // 推进时间不应触发额外调用（但 immediate 的第一次已入队）
    act(() => { jest.advanceTimersByTime(5000); });
    // 如果 timer 未清理，fetcher 至少被调 5 次
    expect(fetcher).toHaveBeenCalledTimes(1); // immediate call already fired before unmount
  });

  it('refresh 应手动触发一次获取', async () => {
    const fetcher = jest.fn().mockResolvedValue('refreshed');
    const { result } = renderHook(() => usePolling(fetcher, { interval: 10000 }));

    await waitFor(() => expect(result.current.data).toBe('refreshed'));

    act(() => { result.current.refresh(); });
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2));
  });

  it('连续失败应触发重试退避', async () => {
    const fetcher = jest.fn()
      .mockRejectedValueOnce(new Error('fail1'))
      .mockRejectedValueOnce(new Error('fail2'))
      .mockRejectedValueOnce(new Error('fail3'));

    const { result } = renderHook(() =>
      usePolling(fetcher, {
        interval: 1000,
        maxRetries: 3,
        retryDelay: 2000,
      })
    );

    // 第一次失败
    await waitFor(() => expect(result.current.error?.message).toBe('fail1'));

    // 推进到第一次重试（retryDelay=2000）
    act(() => { jest.advanceTimersByTime(2000); });
    await waitFor(() => expect(result.current.error?.message).toBe('fail2'));

    // 推进到第二次重试
    act(() => { jest.advanceTimersByTime(2000); });
    await waitFor(() => expect(result.current.error?.message).toBe('fail3'));

    // 超过 maxRetries 后不再调度
    act(() => { jest.advanceTimersByTime(5000); });
    expect(fetcher).toHaveBeenCalledTimes(3);
  });
});
