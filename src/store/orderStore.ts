import { create } from 'zustand';
import { Order, ChargingStatus, PaginatedData } from '../types';
import { orderApi, chargingApi } from '../services/api';

interface OrderState {
  orders: Order[];
  selectedOrder: Order | null;
  activeCharging: ChargingStatus | null;
  total: number;
  page: number;
  loading: boolean;
  error: string | null;
  fetchOrders: (params?: { status?: string; page?: number; pageSize?: number }) => Promise<void>;
  fetchOrderDetail: (id: number) => Promise<void>;
  fetchActiveCharging: () => Promise<void>;
  startCharging: (chargerId: number, vehicleId?: number, couponId?: number) => Promise<ChargingStatus>;
  stopCharging: (orderId: number) => Promise<void>;
  cancelOrder: (id: number) => Promise<void>;
  clearActiveCharging: () => void;
}

export const useOrderStore = create<OrderState>((set, get) => ({
  orders: [],
  selectedOrder: null,
  activeCharging: null,
  total: 0,
  page: 1,
  loading: false,
  error: null,

  fetchOrders: async (params) => {
    set({ loading: true, error: null });
    try {
      const response = await orderApi.getList(params);
      const data: PaginatedData<Order> = response.data;
      set({
        orders: data.items,
        total: data.total,
        page: data.page,
        loading: false,
      });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : '获取订单列表失败';
      set({ loading: false, error: message });
    }
  },

  fetchOrderDetail: async (id: number) => {
    set({ loading: true, error: null });
    try {
      const response = await orderApi.getDetail(id);
      set({ selectedOrder: response.data, loading: false });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : '获取订单详情失败';
      set({ loading: false, error: message });
    }
  },

  fetchActiveCharging: async () => {
    try {
      const response = await chargingApi.getActiveOrder();
      set({ activeCharging: response.data });
    } catch {
      set({ activeCharging: null });
    }
  },

  startCharging: async (chargerId: number, vehicleId?: number, couponId?: number) => {
    const response = await chargingApi.start({ chargerId, vehicleId, couponId });
    const status = response.data;
    set({ activeCharging: status });
    return status;
  },

  stopCharging: async (orderId: number) => {
    await chargingApi.stop(orderId);
    set({ activeCharging: null });
  },

  cancelOrder: async (id: number) => {
    const response = await orderApi.cancelOrder(id);
    set({ selectedOrder: response.data });
  },

  clearActiveCharging: () => {
    set({ activeCharging: null });
  },
}));