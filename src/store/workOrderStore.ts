import { create } from 'zustand';
import { WorkOrder, PaginatedData, CreateWorkOrderData } from '../types';
import { workOrderApi } from '../services/api';

interface WorkOrderState {
  orders: WorkOrder[];
  selectedOrder: WorkOrder | null;
  total: number;
  page: number;
  loading: boolean;
  error: string | null;
  fetchOrders: (params?: { stationId?: number; status?: string; page?: number; pageSize?: number }) => Promise<void>;
  fetchOrderDetail: (id: number) => Promise<void>;
  createOrder: (data: CreateWorkOrderData) => Promise<void>;
  completeOrder: (id: number) => Promise<void>;
  setSelectedOrder: (order: WorkOrder | null) => void;
  reset: () => void;
}

export const useWorkOrderStore = create<WorkOrderState>((set, get) => ({
  orders: [],
  selectedOrder: null,
  total: 0,
  page: 1,
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

  createOrder: async (data: CreateWorkOrderData) => {
    set({ loading: true, error: null });
    try {
      await workOrderApi.createWorkOrder(data);
      set({ loading: false });
      // Refresh the list after creation
      const currentState = get();
      get().fetchOrders({ page: currentState.page, pageSize: 20 });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : '创建工单失败';
      set({ loading: false, error: message });
      throw err;
    }
  },

  completeOrder: async (id: number) => {
    set({ loading: true, error: null });
    try {
      await workOrderApi.completeWorkOrder(id);
      set({ loading: false });
      // Refresh the list
      const currentState = get();
      get().fetchOrders({ page: currentState.page, pageSize: 20 });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : '完成工单失败';
      set({ loading: false, error: message });
      throw err;
    }
  },

  setSelectedOrder: (order: WorkOrder | null) => {
    set({ selectedOrder: order });
  },

  reset: () => {
    set({
      orders: [],
      selectedOrder: null,
      total: 0,
      page: 1,
      loading: false,
      error: null,
    });
  },
}));