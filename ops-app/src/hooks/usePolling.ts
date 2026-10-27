/**
 * 轮询 Hook — 运维APP使用（独立副本避免跨项目依赖）
 */
import { useEffect, useRef, useCallback, useState } from 'react';

interface UsePollingOptions {
  interval?: number;
  enabled?: boolean;
  immediate?: boolean;
  maxRetries?: number;
  retryDelay?: number;
}

interface UsePollingResult<T> {
  data: T | null;
  loading: boolean;
  error: Error | null;
  refresh: () => void;
  tickCount: number;
}

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

  const fetcherRef = useRef(fetcher);
  const mountedRef = useRef(true);
  const retryCountRef = useRef(0);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const scheduleNextRef = useRef<(() => void) | null>(null);

  // ref同步放effect内, 避免render期间写ref (react-hooks/refs)
  useEffect(() => {
    fetcherRef.current = fetcher;
  });

  const execute = useCallback(async () => {
    if (!mountedRef.current) return;
    try {
      const result = await fetcherRef.current();
      if (!mountedRef.current) return;
      setData(result);
      setError(null);
      setLoading(false);
      setTickCount((c) => c + 1);
      retryCountRef.current = 0;
    } catch (err) {
      if (!mountedRef.current) return;
      setError(err instanceof Error ? err : new Error(String(err)));
      setLoading(false);
      retryCountRef.current += 1;
    }
  }, []);

  const scheduleNext = useCallback(() => {
    if (!mountedRef.current || !enabled) return;
    if (retryCountRef.current >= maxRetries) return;
    const delay = retryCountRef.current > 0 ? retryDelay : interval;
    timerRef.current = setTimeout(async () => {
      await execute();
      scheduleNextRef.current?.();
    }, delay);
  }, [enabled, interval, maxRetries, retryDelay, execute]);

  // 自调度用ref间接调用, 消除声明前自引用 (react-hooks/refs)
  useEffect(() => {
    scheduleNextRef.current = scheduleNext;
  }, [scheduleNext]);

  const refresh = useCallback(() => {
    setLoading(true);
    execute();
  }, [execute]);

  useEffect(() => {
    mountedRef.current = true;
    if (enabled) {
      if (immediate) execute();
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
