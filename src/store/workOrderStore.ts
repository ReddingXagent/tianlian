import { create } from 'zustand';
import { WorkOrder, PaginatedData } from '../types';
import { workOrderApi } from '../services/api';

interface WorkOrderState {
  orders: WorkOrder[];
  selectedOrder: WorkOrder | null;
  total: number;
  page: number;
  pageSize: number;
  loading: boolean;
  error: string | null;
  fetchOrders: (params?: {
    stationId?: number;
    status?: string;
    priority?: string;
    page?: number;
    pageSize?: number;
  }) => Promise<void>;
  fetchOrderDetail: (id: number) => Promise<void>;
  updateOrderStatus: (id: number, status: string) => Promise<void>;
  setSelectedOrder: (order: WorkOrder | null) => void;
}

export const useWorkOrderStore = create<WorkOrderState>((set, get) => ({
  orders: [],
  selectedOrder: null,
  total: 0,
  page: 1,
  pageSize: 20,
  loading: false,
  error: null,

  fetchOrders: async (params) => {
    set({ loading: true, error: null });
    try {
      const response = await workOrderApi.getList(params);
      const data: PaginatedData<WorkOrder> = response.data;
      set({
        orders: data.items,
        total: data.total,
        page: data.page,
        pageSize: data.pageSize,
        loading: false,
      });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : '获取工单列表失败';
      set({ loading: false, error: message });
    }
  },

  fetchOrderDetail: async (id: number) => {
    set({ loading: true, error: null });
    try {
      const response = await workOrderApi.getDetail(id);
      set({ selectedOrder: response.data, loading: false });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : '获取工单详情失败';
      set({ loading: false, error: message });
    }
  },

  updateOrderStatus: async (id: number, status: string) => {
    try {
      const response = await workOrderApi.updateStatus(id, status);
      const { orders } = get();
      set({
        selectedOrder: response.data,
        orders: orders.map((o) => (o.id === id ? response.data : o)),
      });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : '更新工单状态失败';
      set({ error: message });
      throw new Error(message);
    }
  },

  setSelectedOrder: (order: WorkOrder | null) => {
    set({ selectedOrder: order });
  },
}));