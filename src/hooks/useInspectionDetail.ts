import { useState, useCallback, useEffect } from 'react';
import { useRoute, RouteProp } from '@react-navigation/native';
import { useInspectionStore } from '../store/inspectionStore';
import { RootStackParamList, InspectionItem } from '../types';

type DetailRouteProp = RouteProp<RootStackParamList, 'InspectionDetail'>;

/**
 * 巡检详情屏数据 hook — 封装详情加载、刷新、状态操作。
 *
 * 职责：
 * - 从路由参数获取 taskId
 * - 拉取巡检详情（通过 store）
 * - 下拉刷新
 * - 开始巡检 / 更新检查项 / 完成巡检
 *
 * 返回纯数据 + 操作函数，不包含任何 UI。
 */
export function useInspectionDetail() {
  const route = useRoute<DetailRouteProp>();
  const { taskId } = route.params;
  const {
    selectedTask,
    loading,
    error,
    submitting,
    fetchTaskDetail,
    startTask,
    updateItem,
    completeTask,
  } = useInspectionStore();

  const [refreshing, setRefreshing] = useState(false);

  const loadCore = useCallback(
    () => fetchTaskDetail(taskId),
    [taskId, fetchTaskDetail],
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

  const handleStart = useCallback(
    () => startTask(taskId),
    [taskId, startTask],
  );

  const handleItemResult = useCallback(
    (item: InspectionItem, result: 'pass' | 'fail' | 'na') =>
      updateItem(taskId, item.id, result),
    [taskId, updateItem],
  );

  const handleComplete = useCallback(
    async (summary: string) => {
      const passedCount = selectedTask?.items.filter((i) => i.result === 'pass').length ?? 0;
      const totalCount = selectedTask?.items.length ?? 0;
      const overall = totalCount === 0
        ? 'fail'
        : passedCount === totalCount
          ? 'pass'
          : passedCount > 0
            ? 'partial'
            : 'fail';
      await completeTask(taskId, summary, overall);
    },
    [taskId, completeTask, selectedTask],
  );

  return {
    taskId,
    selectedTask,
    loading,
    error,
    submitting,
    refreshing,
    loadData,
    handleStart,
    handleItemResult,
    handleComplete,
  };
}
