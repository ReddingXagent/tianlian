import { useState, useCallback, useEffect } from 'react';
import { useIsFocused } from '@react-navigation/native';
import { useAuthStore } from '../store/authStore';
import { authApi, walletApi } from '../services/api';
import { WalletRecord } from '../types';

const PAGE_SIZE = 20;

interface UseWalletReturn {
  records: WalletRecord[];
  loading: boolean;
  error: string | null;
  refreshing: boolean;
  recharging: boolean;
  loadingMore: boolean;
  hasMore: boolean;
  loadRecords: () => Promise<void>;
  loadMoreRecords: () => Promise<void>;
  handleRefresh: () => Promise<void>;
  recharge: (amount: number) => Promise<boolean>;
  refreshProfile: () => Promise<void>;
}

export function useWallet(): UseWalletReturn {
  const { setUser } = useAuthStore();
  const [records, setRecords] = useState<WalletRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [recharging, setRecharging] = useState(false);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);

  const loadRecords = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await walletApi.getRecords({ page: 1, pageSize: PAGE_SIZE });
      setRecords(response.data.items);
      setPage(response.data.page);
      setHasMore(response.data.items.length < response.data.total);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '获取交易记录失败';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadMoreRecords = useCallback(async () => {
    if (!hasMore || loadingMore || loading) return;
    setLoadingMore(true);
    try {
      const response = await walletApi.getRecords({ page: page + 1, pageSize: PAGE_SIZE });
      const data = response.data;
      setRecords((prev) => {
        const seen = new Set(prev.map((r) => r.id));
        const merged = [...prev, ...data.items.filter((r) => !seen.has(r.id))];
        setHasMore(merged.length < data.total);
        return merged;
      });
      setPage(data.page);
    } catch {
      // 静默处理
    } finally {
      setLoadingMore(false);
    }
  }, [hasMore, loadingMore, loading, page]);

  const refreshProfile = useCallback(async () => {
    try {
      const response = await authApi.getProfile();
      setUser(response.data);
    } catch {
      // 静默处理
    }
  }, [setUser]);

  const isFocused = useIsFocused();

  useEffect(() => {
    if (isFocused) {
      let cancelled = false;
      Promise.resolve().then(() => {
        if (!cancelled) {
          loadRecords();
          refreshProfile();
        }
      });
      return () => { cancelled = true; };
    }
  }, [isFocused, loadRecords, refreshProfile]);

  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    await Promise.all([loadRecords(), refreshProfile()]);
    setRefreshing(false);
  }, [loadRecords, refreshProfile]);

  const recharge = async (amount: number): Promise<boolean> => {
    setRecharging(true);
    try {
      await walletApi.recharge(amount);
      const response = await authApi.getProfile();
      setUser(response.data);
      loadRecords();
      return true;
    } catch {
      return false;
    } finally {
      setRecharging(false);
    }
  };

  return {
    records,
    loading,
    error,
    refreshing,
    recharging,
    loadingMore,
    hasMore,
    loadRecords,
    loadMoreRecords,
    handleRefresh,
    recharge,
    refreshProfile,
  };
}
