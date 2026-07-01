/**
 * 轮询 Hook — 用于实时数据自动刷新
 * 支持动态间隔、暂停/恢复、组件卸载自动清理
 */
import { useEffect, useRef, useCallback, useState } from 'react';

interface UsePollingOptions {
  /** 轮询间隔 ms，默认 15000 */
  interval?: number;
  /** 是否启用轮询，默认 true */
  enabled?: boolean;
  /** 立即执行一次 */
  immediate?: boolean;
  /** 错误重试最大次数，默认 3 */
  maxRetries?: number;
  /** 错误重试延迟 ms，默认 5000 */
  retryDelay?: number;
}

interface UsePollingResult<T> {
  data: T | null;
  loading: boolean;
  error: Error | null;
  refresh: () => void;
  /** 轮询执行次数 */
  tickCount: number;
}

/**
 * 轮询 Hook
 * @param fetcher 异步数据获取函数
 * @param options 轮询配置
 *
 * @example
 * const { data, loading, error, refresh } = usePolling(
 *   () => chargerApi.getMonitorList(stationId),
 *   { interval: 10000, enabled: !!stationId }
 * );
 */
export function usePolling<T>(
  fetcher: () => Promise<T>,
  options: UsePollingOptions = {}
): UsePollingResult<T> {
  const {
    interval = 15000,
    enabled = true,
    immediate = true,
    maxRetries = 3,
    retryDelay = 5000,
  } = options;

  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState<boolean>(immediate);
  const [error, setError] = useState<Error | null>(null);
  const [tickCount, setTickCount] = useState(0);

  // 使用 ref 避免闭包陷阱
  const fetcherRef = useRef(fetcher);
  const mountedRef = useRef(true);
  const retryCountRef = useRef(0);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  fetcherRef.current = fetcher;

  const execute = useCallback(async () => {
    if (!mountedRef.current) return;
    try {
      const result = await fetcherRef.current();
      if (!mountedRef.current) return;
      setData(result);
      setError(null);
      setLoading(false);
      setTickCount((c) => c + 1);
      retryCountRef.current = 0; // 成功重置重试计数
    } catch (err) {
      if (!mountedRef.current) return;
      setError(err instanceof Error ? err : new Error(String(err)));
      setLoading(false);
      retryCountRef.current += 1;
    }
  }, []);

  const scheduleNext = useCallback(() => {
    if (!mountedRef.current || !enabled) return;

    // 超过重试次数则暂停
    if (retryCountRef.current >= maxRetries) {
      return;
    }

    const delay = retryCountRef.current > 0 ? retryDelay : interval;
    timerRef.current = setTimeout(async () => {
      await execute();
      scheduleNext();
    }, delay);
  }, [enabled, interval, maxRetries, retryDelay, execute]);

  const refresh = useCallback(() => {
    setLoading(true);
    execute();
  }, [execute]);

  useEffect(() => {
    mountedRef.current = true;

    if (enabled) {
      if (immediate) {
        execute();
      }
      scheduleNext();
    }

    return () => {
      mountedRef.current = false;
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, interval]);

  return { data, loading, error, refresh, tickCount };
}
