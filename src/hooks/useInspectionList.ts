import { useState, useCallback, useEffect } from 'react';
import { useInspectionStore } from '../store/inspectionStore';
import { InspectionStatus } from '../types';

/**
 * 巡检列表屏数据 hook — 封装状态筛选、加载、刷新。
 *
 * 职责：
 * - 从 store 获取 tasks/total/loading/error
 * - 状态筛选切换 + 自动加载
 * - 下拉刷新
 *
 * 返回纯数据 + 操作函数，不包含任何 UI。
 */
export function useInspectionList() {
  const { tasks, loading, error, total, fetchTasks } = useInspectionStore();
  const [activeFilter, setActiveFilter] = useState<InspectionStatus | 'all'>('all');
  const [refreshing, setRefreshing] = useState(false);

  const loadCore = useCallback(
    () =>
      fetchTasks(
        activeFilter === 'all' ? undefined : { status: activeFilter }
      ),
    [fetchTasks, activeFilter],
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
    tasks,
    loading,
    error,
    total,
    activeFilter,
    refreshing,
    setActiveFilter,
    loadData,
  };
}
