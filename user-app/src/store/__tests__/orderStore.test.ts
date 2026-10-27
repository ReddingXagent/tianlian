import { orderApi, chargingApi } from '../../services/api';
import { useOrderStore } from '../orderStore';
import { Order, ChargingStatus, PaginatedData } from '../../types';

jest.mock('../../services/api', () => ({
  orderApi: {
    getList: jest.fn(),
    getDetail: jest.fn(),
    cancelOrder: jest.fn(),
  },
  chargingApi: {
    getActiveOrder: jest.fn(),
    start: jest.fn(),
    stop: jest.fn(),
  },
}));

const mockOrders: Order[] = [
  {
    id: 1,
    orderNo: 'TL20260601001',
    userId: 1,
    stationId: 1,
    stationName: '天链充电站-中心站',
    chargerId: 1,
    chargerName: 'A-01',
    status: 'completed',
    startTime: '2026-06-01T10:00:00Z',
    endTime: '2026-06-01T11:00:00Z',
    duration: 60,
    energy: 45.5,
    power: 0,
    voltage: 0,
    current: 0,
    amount: 59.15,
    couponDiscount: 0,
    paymentStatus: 'paid',
    paymentMethod: 'wechat',
    createdAt: '2026-06-01T10:00:00Z',
    updatedAt: '2026-06-01T11:00:00Z',
  },
  {
    id: 2,
    orderNo: 'TL20260602001',
    userId: 1,
    stationId: 2,
    stationName: '天链充电站-南站',
    chargerId: 3,
    chargerName: 'B-01',
    status: 'completed',
    startTime: '2026-06-02T14:00:00Z',
    endTime: '2026-06-02T15:30:00Z',
    duration: 90,
    energy: 60.2,
    power: 0,
    voltage: 0,
    current: 0,
    amount: 78.26,
    couponDiscount: 5,
    paymentStatus: 'unpaid',
    createdAt: '2026-06-02T14:00:00Z',
    updatedAt: '2026-06-02T15:30:00Z',
  },
];

const mockPaginatedResponse = {
  data: {
    items: mockOrders,
    total: 2,
    page: 1,
    pageSize: 20,
  } as PaginatedData<Order>,
};

const mockChargingStatus: ChargingStatus = {
  orderId: 3,
  orderNo: 'TL20260603001',
  chargerName: 'A-01',
  stationName: '天链充电站-中心站',
  status: 'charging',
  power: 85.5,
  voltage: 380,
  current: 225,
  energy: 22.3,
  duration: 15,
  amount: 28.99,
  startTime: '2026-06-03T08:00:00Z',
};

describe('orderStore', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    useOrderStore.setState({
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
    });
  });

  describe('fetchOrders', () => {
    it('should fetch order list', async () => {
      (orderApi.getList as jest.Mock).mockResolvedValue(mockPaginatedResponse);

      await useOrderStore.getState().fetchOrders({ status: 'completed' });

      expect(orderApi.getList).toHaveBeenCalledWith({ status: 'completed' });
      const state = useOrderStore.getState();
      expect(state.orders).toEqual(mockOrders);
      expect(state.total).toBe(2);
      expect(state.loading).toBe(false);
    });

    it('should handle error', async () => {
      (orderApi.getList as jest.Mock).mockRejectedValue(new Error('获取失败'));

      await useOrderStore.getState().fetchOrders();

      expect(useOrderStore.getState().error).toBe('获取失败');
      expect(useOrderStore.getState().loading).toBe(false);
    });

    it('should set hasMore=true when items less than total', async () => {
      (orderApi.getList as jest.Mock).mockResolvedValue({
        data: { items: mockOrders, total: 5, page: 1, pageSize: 2 } as PaginatedData<Order>,
      });

      await useOrderStore.getState().fetchOrders({ status: 'completed' });

      const state = useOrderStore.getState();
      expect(state.hasMore).toBe(true);
      expect(state.statusFilter).toBe('completed');
    });
  });

  describe('loadMoreOrders (无限滚动分页)', () => {
    it('should append next page with same filter and dedupe by id', async () => {
      // 首页: total=3 已拉 2 条 → hasMore
      (orderApi.getList as jest.Mock).mockResolvedValueOnce({
        data: { items: mockOrders, total: 3, page: 1, pageSize: 2 } as PaginatedData<Order>,
      });
      await useOrderStore.getState().fetchOrders({ status: 'completed' });
      expect(useOrderStore.getState().hasMore).toBe(true);

      // 第二页: 含 1 条重复(id=2) + 1 条新(id=3)
      const nextOrder: Order = { ...mockOrders[0], id: 3, orderNo: 'TL20260603002' };
      (orderApi.getList as jest.Mock).mockResolvedValueOnce({
        data: { items: [mockOrders[1], nextOrder], total: 3, page: 2, pageSize: 2 } as PaginatedData<Order>,
      });

      await useOrderStore.getState().loadMoreOrders();

      expect(orderApi.getList).toHaveBeenLastCalledWith({ status: 'completed', page: 2, pageSize: 2 });
      const state = useOrderStore.getState();
      expect(state.orders.map((o) => o.id)).toEqual([1, 2, 3]);
      expect(state.hasMore).toBe(false);
      expect(state.loadingMore).toBe(false);
    });

    it('should no-op when hasMore=false', async () => {
      (orderApi.getList as jest.Mock).mockResolvedValue(mockPaginatedResponse);
      await useOrderStore.getState().fetchOrders();
      expect(useOrderStore.getState().hasMore).toBe(false);

      await useOrderStore.getState().loadMoreOrders();

      // 只有首页那一次调用
      expect(orderApi.getList).toHaveBeenCalledTimes(1);
    });

    it('should fail silently and allow retry', async () => {
      (orderApi.getList as jest.Mock).mockResolvedValueOnce({
        data: { items: mockOrders, total: 5, page: 1, pageSize: 2 } as PaginatedData<Order>,
      });
      await useOrderStore.getState().fetchOrders();

      (orderApi.getList as jest.Mock).mockRejectedValueOnce(new Error('网络异常'));
      await useOrderStore.getState().loadMoreOrders();

      const state = useOrderStore.getState();
      expect(state.loadingMore).toBe(false);
      expect(state.orders).toHaveLength(2);
      expect(state.error).toBeNull();
      expect(state.hasMore).toBe(true);
    });
  });

  describe('fetchOrderDetail', () => {
    it('should fetch order detail by id', async () => {
      (orderApi.getDetail as jest.Mock).mockResolvedValue({ data: mockOrders[0] });

      await useOrderStore.getState().fetchOrderDetail(1);

      expect(orderApi.getDetail).toHaveBeenCalledWith(1);
      expect(useOrderStore.getState().selectedOrder).toEqual(mockOrders[0]);
    });
  });

  describe('fetchActiveCharging', () => {
    it('should set active charging status', async () => {
      (chargingApi.getActiveOrder as jest.Mock).mockResolvedValue({ data: mockChargingStatus });

      await useOrderStore.getState().fetchActiveCharging();

      expect(useOrderStore.getState().activeCharging).toEqual(mockChargingStatus);
    });

    it('should set null if no active charging', async () => {
      (chargingApi.getActiveOrder as jest.Mock).mockResolvedValue({ data: null });

      await useOrderStore.getState().fetchActiveCharging();

      expect(useOrderStore.getState().activeCharging).toBeNull();
    });

    it('should handle API error gracefully', async () => {
      (chargingApi.getActiveOrder as jest.Mock).mockRejectedValue(new Error('error'));

      await useOrderStore.getState().fetchActiveCharging();

      expect(useOrderStore.getState().activeCharging).toBeNull();
    });
  });

  describe('startCharging', () => {
    it('should start charging and set active status', async () => {
      (chargingApi.start as jest.Mock).mockResolvedValue({ data: mockChargingStatus });

      const result = await useOrderStore.getState().startCharging(1, 1);

      expect(chargingApi.start).toHaveBeenCalledWith({ chargerId: 1, vehicleId: 1, couponId: undefined });
      expect(result).toEqual(mockChargingStatus);
      expect(useOrderStore.getState().activeCharging).toEqual(mockChargingStatus);
    });
  });

  describe('stopCharging', () => {
    it('should stop charging and clear active status', async () => {
      (chargingApi.stop as jest.Mock).mockResolvedValue({ data: mockOrders[0] });
      useOrderStore.setState({ activeCharging: mockChargingStatus });

      await useOrderStore.getState().stopCharging(3);

      expect(chargingApi.stop).toHaveBeenCalledWith(3);
      expect(useOrderStore.getState().activeCharging).toBeNull();
    });
  });

  describe('cancelOrder', () => {
    it('should cancel order and update selected order', async () => {
      const cancelledOrder = { ...mockOrders[1], status: 'cancelled' as const };
      (orderApi.cancelOrder as jest.Mock).mockResolvedValue({ data: cancelledOrder });

      await useOrderStore.getState().cancelOrder(2);

      expect(orderApi.cancelOrder).toHaveBeenCalledWith(2);
      expect(useOrderStore.getState().selectedOrder).toEqual(cancelledOrder);
    });
  });

  describe('clearActiveCharging', () => {
    it('should clear active charging status', () => {
      useOrderStore.setState({ activeCharging: mockChargingStatus });

      useOrderStore.getState().clearActiveCharging();

      expect(useOrderStore.getState().activeCharging).toBeNull();
    });
  });
});