import { useState, useCallback, useEffect } from 'react';
import { useWorkOrderStore } from '../store/workOrderStore';
import { WorkOrderStatus } from '../types';

/**
 * 工单列表屏数据 hook — 封装状态筛选、加载、刷新。
 *
 * 职责：
 * - 从 store 获取 orders/total/loading/error
 * - 状态筛选切换 + 自动加载
 * - 下拉刷新
 *
 * 返回纯数据 + 操作函数，不包含任何 UI。
 */
export function useWorkOrderList() {
  const { orders, loading, error, total, fetchOrders } = useWorkOrderStore();
  const [activeFilter, setActiveFilter] = useState<WorkOrderStatus | 'all'>('all');
  const [refreshing, setRefreshing] = useState(false);

  const loadCore = useCallback(
    () =>
      fetchOrders(
        activeFilter === 'all' ? undefined : { status: activeFilter }
      ),
    [fetchOrders, activeFilter],
  );

  const loadData = useCallback(
    async (isRefresh = false) => {
      if (isRefresh) setRefreshing(true);
      try {
        await loadCore();
      } finally {
        if (isRefresh) setRefreshing(false);
      }
    },
    [loadCore],
  );

  useEffect(() => {
    void loadCore();
  }, [loadCore]);

  return {
    orders,
    loading,
    error,
    total,
    activeFilter,
    refreshing,
    setActiveFilter,
    loadData,
  };
}
