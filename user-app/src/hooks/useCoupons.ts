import { useState, useCallback, useEffect } from 'react';
import { useIsFocused } from '@react-navigation/native';
import { couponApi } from '../services/api';
import { Coupon } from '../types';

const PAGE_SIZE = 20;

interface UseCouponsReturn {
  coupons: Coupon[];
  loading: boolean;
  refreshing: boolean;
  error: string | null;
  hasMore: boolean;
  loadingMore: boolean;
  loadCoupons: () => Promise<void>;
  loadMoreCoupons: () => Promise<void>;
  handleRefresh: () => Promise<void>;
}

export function useCoupons(): UseCouponsReturn {
  const [coupons, setCoupons] = useState<Coupon[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);

  const loadCoupons = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await couponApi.getList({ page: 1, pageSize: PAGE_SIZE });
      setCoupons(response.data.items);
      setPage(response.data.page);
      setHasMore(response.data.items.length < response.data.total);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '获取优惠券失败';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadMoreCoupons = useCallback(async () => {
    if (!hasMore || loadingMore || loading) return;
    setLoadingMore(true);
    try {
      const response = await couponApi.getList({ page: page + 1, pageSize: PAGE_SIZE });
      const data = response.data;
      const seen = new Set(coupons.map((c) => c.id));
      const merged = [...coupons, ...data.items.filter((c) => !seen.has(c.id))];
      setCoupons(merged);
      setPage(data.page);
      setHasMore(merged.length < data.total);
    } catch {
      // 静默处理, 下次触边可重试
    } finally {
      setLoadingMore(false);
    }
  }, [hasMore, loadingMore, loading, page, coupons]);

  const isFocused = useIsFocused();

  useEffect(() => {
    if (isFocused) {
      let cancelled = false;
      Promise.resolve().then(() => {
        if (!cancelled) loadCoupons();
      });
      return () => { cancelled = true; };
    }
  }, [isFocused, loadCoupons]);

  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    await loadCoupons();
    setRefreshing(false);
  }, [loadCoupons]);

  return {
    coupons,
    loading,
    refreshing,
    error,
    hasMore,
    loadingMore,
    loadCoupons,
    loadMoreCoupons,
    handleRefresh,
  };
}
