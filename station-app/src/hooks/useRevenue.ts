import { useState, useCallback, useEffect } from 'react';
import { revenueApi } from '../services/api';
import { RevenueRecord } from '../types';

type PeriodType = 'day' | 'week' | 'month';

interface UseRevenueParams {
  period: PeriodType;
}

interface UseRevenueReturn {
  records: RevenueRecord[];
  summary: { today: number; week: number; month: number; total: number };
  loading: boolean;
  refreshing: boolean;
  fetchData: (isRefresh?: boolean) => Promise<void>;
}

export function useRevenue({ period }: UseRevenueParams): UseRevenueReturn {
  const [records, setRecords] = useState<RevenueRecord[]>([]);
  const [summary, setSummary] = useState({ today: 0, week: 0, month: 0, total: 0 });
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const fetchData = useCallback(async (isRefresh = false) => {
    if (isRefresh) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }

    try {
      const [recordsRes, summaryRes] = await Promise.all([
        revenueApi.getRecords({ type: period }),
        revenueApi.getSummary(),
      ]);
      setRecords(recordsRes.data);
      setSummary(summaryRes.data);
    } catch {
      // 静默处理
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [period]);

  useEffect(() => {
    Promise.resolve().then(() => fetchData());
  }, [fetchData]);

  return {
    records,
    summary,
    loading,
    refreshing,
    fetchData,
  };
}
