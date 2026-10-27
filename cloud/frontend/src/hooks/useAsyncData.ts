/**
 * useAsyncData - 统一数据请求 Hook
 *
 * 整合 loading / error / empty 状态管理
 * 配合 PageWrapper / SkeletonPage / EmptyState 使用
 *
 * 用法:
 *   const { data, loading, error, refetch } = useAsyncData(() => api.fetchList(), []);
 *   if (loading) return <SkeletonPage type="table" />;
 *   if (error) return <ErrorResult onRetry={refetch} />;
 *   if (!data.length) return <EmptyState type="device" actionText="添加设备" onAction={...} />;
 */
import { useState, useEffect, useCallback, useRef } from 'react';

export interface AsyncState<T> {
  /** 请求返回的数据 */
  data: T | null;
  /** 是否正在加载 */
  loading: boolean;
  /** 错误信息 */
  error: Error | null;
  /** 请求是否已完成 (成功或失败) */
  settled: boolean;
  /** 重新请求 */
  refetch: () => void;
  /** 手动设置数据 (用于乐观更新) */
  setData: (data: T | ((prev: T | null) => T)) => void;
}

/**
 * 通用的带 Loading/Error/Empty 状态管理的数据请求 Hook
 *
 * @param fetcher 异步数据获取函数
 * @param deps 依赖数组 (变化时自动重新请求)
 * @param options 可选配置
 * @returns { data, loading, error, settled, refetch, setData }
 */
export function useAsyncData<T = unknown>(
  fetcher: () => Promise<T>,
  deps: any[] = [],
  options?: {
    /** 是否立即请求 (默认 true) */
    immediate?: boolean;
    /** 请求失败时是否静默 (不触发 error 状态) */
    silent?: boolean;
    /** 缓存键 - 相同 key 在组件卸载前复用上次结果 */
    cacheKey?: string;
  }
): AsyncState<T> {
  const { immediate = true, silent = false } = options || {};

  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(immediate);
  const [error, setError] = useState<Error | null>(null);
  const [settled, setSettled] = useState(false);

  const mountedRef = useRef(true);
  const fetcherRef = useRef(fetcher);
  // 追踪请求序号，防止竞态
  const seqRef = useRef(0);

  // 保持 fetcher 引用最新
  fetcherRef.current = fetcher;

  const request = useCallback(async () => {
    const seq = ++seqRef.current;
    setLoading(true);
    setError(null);
    setSettled(false);

    try {
      const result = await fetcherRef.current();
      // 只有最新请求的结果才生效
      if (mountedRef.current && seq === seqRef.current) {
        setData(result);
        setLoading(false);
        setSettled(true);
      }
    } catch (err) {
      if (mountedRef.current && seq === seqRef.current) {
        const error = err instanceof Error ? err : new Error(String(err));
        if (!silent) {
          setError(error);
        }
        setLoading(false);
        setSettled(true);
      }
    }
  }, [silent]);

  useEffect(() => {
    mountedRef.current = true;
    if (immediate) {
      request();
    } else {
      setLoading(false);
      setSettled(true);
    }
    return () => {
      mountedRef.current = false;
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  const refetch = useCallback(() => {
    request();
  }, [request]);

  const setDataWrapper = useCallback((updater: T | ((prev: T | null) => T)) => {
    setData(prev => typeof updater === 'function' ? (updater as (prev: T | null) => T)(prev) : updater);
  }, []);

  return {
    data,
    loading,
    error,
    settled,
    refetch,
    setData: setDataWrapper,
  };
}

export default useAsyncData;