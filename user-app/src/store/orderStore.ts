import { create } from 'zustand';
import { Order, ChargingStatus, PaginatedData } from '../types';
import { orderApi, chargingApi } from '../services/api';

interface OrderState {
  orders: Order[];
  selectedOrder: Order | null;
  activeCharging: ChargingStatus | null;
  total: number;
  page: number;
  pageSize: number;
  hasMore: boolean;
  loadingMore: boolean;
  /** 当前列表的筛选条件(loadMore 需与首页保持一致) */
  statusFilter?: string;
  loading: boolean;
  error: string | null;
  fetchOrders: (params?: { status?: string; page?: number; pageSize?: number }) => Promise<void>;
  /** 无限滚动加载下一页(追加);无更多/加载中时静默返回 */
  loadMoreOrders: () => Promise<void>;
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
  pageSize: 20,
  hasMore: false,
  loadingMore: false,
  statusFilter: undefined,
  loading: false,
  error: null,

  fetchOrders: async (params) => {
    set({ loading: true, error: null, statusFilter: params?.status });
    try {
      const response = await orderApi.getList(params);
      const data: PaginatedData<Order> = response.data;
      set({
        orders: data.items,
        total: data.total,
        page: data.page,
        pageSize: data.pageSize,
        hasMore: data.items.length < data.total,
        loading: false,
      });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : '获取订单列表失败';
      set({ loading: false, error: message });
    }
  },

  loadMoreOrders: async () => {
    const { hasMore, loadingMore, loading, page, pageSize, statusFilter } = get();
    if (!hasMore || loadingMore || loading) return;
    set({ loadingMore: true });
    try {
      const response = await orderApi.getList({
        status: statusFilter,
        page: page + 1,
        pageSize,
      });
      const data: PaginatedData<Order> = response.data;
      const prev = get().orders;
      // 按id去重: 防止并发刷新/接口重复返回导致列表出现重复项
      const seen = new Set(prev.map((o) => o.id));
      const appended = data.items.filter((o) => !seen.has(o.id));
      const merged = [...prev, ...appended];
      set({
        orders: merged,
        total: data.total,
        page: data.page,
        pageSize: data.pageSize,
        hasMore: merged.length < data.total,
        loadingMore: false,
      });
    } catch {
      // 加载更多失败静默处理, 不打断已有列表; 下次触边可重试
      set({ loadingMore: false });
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