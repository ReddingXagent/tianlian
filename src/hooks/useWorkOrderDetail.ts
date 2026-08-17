import { useState, useCallback, useEffect } from 'react';
import { useRoute, RouteProp } from '@react-navigation/native';
import { useWorkOrderStore } from '../store/workOrderStore';
import { workOrderRecordApi, workOrderActionApi } from '../services/api';
import { RootStackParamList, WorkOrderRecord } from '../types';

type DetailRouteProp = RouteProp<RootStackParamList, 'WorkOrderDetail'>;

/**
 * 工单详情屏数据 hook — 封装工单详情 + 执行记录的加载、刷新、状态操作。
 *
 * 职责：
 * - 从路由参数获取 orderId
 * - 拉取工单详情（通过 store）+ 执行记录
 * - 下拉刷新
 * - accept/start/complete 状态操作 + 自动刷新
 *
 * 返回纯数据 + 操作函数，不包含任何 UI。
 */
export function useWorkOrderDetail() {
  const route = useRoute<DetailRouteProp>();
  const { orderId } = route.params;
  const { selectedOrder, loading, error, fetchOrderDetail } =
    useWorkOrderStore();

  const [refreshing, setRefreshing] = useState(false);
  const [statusUpdating, setStatusUpdating] = useState(false);
  const [records, setRecords] = useState<WorkOrderRecord[]>([]);
  const [recordsLoading, setRecordsLoading] = useState(false);

  const loadRecords = useCallback(async () => {
    setRecordsLoading(true);
    try {
      const res = await workOrderRecordApi.getRecords(orderId);
      setRecords(res.data);
    } catch {
      // 记录加载失败不阻塞主流程
    } finally {
      setRecordsLoading(false);
    }
  }, [orderId]);

  const loadCore = useCallback(
    () =>
      Promise.all([
        fetchOrderDetail(orderId),
        workOrderRecordApi
          .getRecords(orderId)
          .then((res) => setRecords(res.data))
          .catch(() => {
            // 记录加载失败不阻塞主流程
          }),
      ]),
    [orderId, fetchOrderDetail],
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

  const performAction = useCallback(
    async (
      action: 'accept' | 'execute' | 'complete',
    ): Promise<boolean> => {
      setStatusUpdating(true);
      try {
        if (action === 'accept') {
          await workOrderActionApi.accept(orderId);
        } else if (action === 'execute') {
          await workOrderActionApi.start(orderId);
        } else if (action === 'complete') {
          await workOrderActionApi.complete(orderId);
        }
        await fetchOrderDetail(orderId);
        await loadRecords();
        return true;
      } catch {
        return false;
      } finally {
        setStatusUpdating(false);
      }
    },
    [orderId, fetchOrderDetail, loadRecords],
  );

  return {
    orderId,
    selectedOrder,
    loading,
    error,
    records,
    recordsLoading,
    refreshing,
    statusUpdating,
    loadData,
    performAction,
    fetchOrderDetail,
  };
}
