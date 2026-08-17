import { useState, useCallback, useEffect } from 'react';
import { workOrderApi } from '../services/api';
import { WorkOrder, WorkOrderType, WorkOrderPriority } from '../types';

interface UseWorkOrdersParams {
  stationId?: number;
  statusFilter: string;
}

interface UseWorkOrdersReturn {
  orders: WorkOrder[];
  loading: boolean;
  refreshing: boolean;
  page: number;
  total: number;
  error: string | null;
  fetchData: (isRefresh?: boolean, p?: number) => Promise<void>;
  handleLoadMore: () => void;
  createWorkOrder: (params: {
    title: string;
    description: string;
    type: WorkOrderType;
    priority: WorkOrderPriority;
  }) => Promise<boolean>;
  completeWorkOrder: (orderId: string) => Promise<boolean>;
}

export function useWorkOrders({ stationId, statusFilter }: UseWorkOrdersParams): UseWorkOrdersReturn {
  const [orders, setOrders] = useState<WorkOrder[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async (isRefresh = false, p = 1) => {
    if (isRefresh) {
      setRefreshing(true);
    } else if (p === 1) {
      setLoading(true);
    }
    setError(null);

    try {
      const params: { page: number; pageSize: number; stationId?: number; status?: string } = { page: p, pageSize: 20 };
      if (stationId) params.stationId = stationId;
      if (statusFilter !== 'all') params.status = statusFilter;

      const response = await workOrderApi.getList(params);
      const data = response.data;

      if (p === 1) {
        setOrders(data.items);
      } else {
        setOrders((prev) => [...prev, ...data.items]);
      }
      setTotal(data.total);
      setPage(p);
    } catch {
      setError('加载工单列表失败');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [stationId, statusFilter]);

  useEffect(() => {
    Promise.resolve().then(() => fetchData(false, 1));
  }, [fetchData]);

  const handleLoadMore = () => {
    if (orders.length < total && !loading) {
      fetchData(false, page + 1);
    }
  };

  const createWorkOrder = async (params: {
    title: string;
    description: string;
    type: WorkOrderType;
    priority: WorkOrderPriority;
  }): Promise<boolean> => {
    if (!stationId) return false;
    try {
      await workOrderApi.createWorkOrder({
        stationId,
        title: params.title,
        description: params.description,
        type: params.type,
        priority: params.priority,
      });
      fetchData(false, 1);
      return true;
    } catch {
      return false;
    }
  };

  const completeWorkOrder = async (orderId: string): Promise<boolean> => {
    try {
      await workOrderApi.completeWorkOrder(orderId);
      fetchData(false, 1);
      return true;
    } catch {
      return false;
    }
  };

  return {
    orders,
    loading,
    refreshing,
    page,
    total,
    error,
    fetchData,
    handleLoadMore,
    createWorkOrder,
    completeWorkOrder,
  };
}
