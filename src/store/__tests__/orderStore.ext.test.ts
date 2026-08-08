/**
 * orderStore.ext.test.ts — 覆盖 loadMoreOrders guard 分支 + fetchOrderDetail error + edge cases
 *
 * 目标: orderStore.ts branches 66.66% → 90%+
 * 覆盖: loadingMore=true guard, loading=true guard, fetchOrderDetail error catch,
 *        loadMoreOrders success with merged.length >= total (hasMore=false edge)
 */
import { orderApi } from '../../services/api';
import { useOrderStore } from '../orderStore';
import { Order, PaginatedData } from '../../types';

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
// chargingApi is part of the mock but not directly used in these tests

const mockOrder: Order = {
  id: 1,
  orderNo: 'TL001',
  userId: 1,
  stationId: 1,
  stationName: '站1',
  chargerId: 1,
  chargerName: 'A-01',
  status: 'completed',
  startTime: '2026-01-01T00:00:00Z',
  endTime: '2026-01-01T01:00:00Z',
  duration: 60,
  energy: 10,
  power: 0,
  voltage: 0,
  current: 0,
  amount: 13,
  couponDiscount: 0,
  paymentStatus: 'paid',
  paymentMethod: 'wechat',
  createdAt: '2026-01-01T00:00:00Z',
  updatedAt: '2026-01-01T01:00:00Z',
};

describe('orderStore — extension guards & edges', () => {
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

  describe('loadMoreOrders guard branches', () => {
    it('no-ops when loadingMore=true (prevent duplicate concurrent load)', async () => {
      // Setup: hasMore=true but already loading more
      useOrderStore.setState({
        orders: [mockOrder],
        total: 5,
        page: 1,
        pageSize: 20,
        hasMore: true,
        loadingMore: true,
      });

      await useOrderStore.getState().loadMoreOrders();

      // getList should NOT be called
      expect(orderApi.getList).not.toHaveBeenCalled();
    });

    it('no-ops when loading=true (first fetch in progress)', async () => {
      useOrderStore.setState({
        orders: [],
        total: 5,
        page: 1,
        pageSize: 20,
        hasMore: true,
        loadingMore: false,
        loading: true,
      });

      await useOrderStore.getState().loadMoreOrders();

      expect(orderApi.getList).not.toHaveBeenCalled();
    });

    it('no-ops when hasMore=false even if not loading', async () => {
      useOrderStore.setState({
        orders: [mockOrder],
        total: 1,
        page: 1,
        pageSize: 20,
        hasMore: false,
        loadingMore: false,
        loading: false,
      });

      await useOrderStore.getState().loadMoreOrders();

      expect(orderApi.getList).not.toHaveBeenCalled();
    });
  });

  describe('fetchOrderDetail error handling', () => {
    it('sets error message on failure with generic fallback', async () => {
      (orderApi.getDetail as jest.Mock).mockRejectedValue(new Error('detail boom'));

      await useOrderStore.getState().fetchOrderDetail(42);

      const state = useOrderStore.getState();
      expect(state.loading).toBe(false);
      expect(state.error).toBe('detail boom');
    });

    it('sets generic Chinese error for non-Error throws', async () => {
      (orderApi.getDetail as jest.Mock).mockRejectedValue('string error');

      await useOrderStore.getState().fetchOrderDetail(42);

      const state = useOrderStore.getState();
      expect(state.error).toBe('获取订单详情失败');
      expect(state.loading).toBe(false);
    });
  });

  describe('fetchOrders error edge cases', () => {
    it('sets generic Chinese error for non-Error throws', async () => {
      (orderApi.getList as jest.Mock).mockRejectedValue({ code: 500 });

      await useOrderStore.getState().fetchOrders();

      expect(useOrderStore.getState().error).toBe('获取订单列表失败');
    });
  });

  describe('loadMoreOrders — merged exactly equals total (hasMore flips to false)', () => {
    it('sets hasMore=false when merged length equals total', async () => {
      const page1Orders: Order[] = [
        { ...mockOrder, id: 1 },
        { ...mockOrder, id: 2 },
      ];

      useOrderStore.setState({
        orders: page1Orders,
        total: 3,
        page: 1,
        pageSize: 2,
        hasMore: true,
        loadingMore: false,
        loading: false,
        statusFilter: undefined,
      });

      const page2Orders: Order[] = [{ ...mockOrder, id: 3 }];
      (orderApi.getList as jest.Mock).mockResolvedValue({
        data: {
          items: page2Orders,
          total: 3,
          page: 2,
          pageSize: 2,
        } as PaginatedData<Order>,
      });

      await useOrderStore.getState().loadMoreOrders();

      const state = useOrderStore.getState();
      expect(state.orders).toHaveLength(3);
      expect(state.hasMore).toBe(false);
      expect(state.loadingMore).toBe(false);
    });
  });

  describe('cancelOrder edge: response.data is null', () => {
    it('handles null response data from cancel', async () => {
      (orderApi.cancelOrder as jest.Mock).mockResolvedValue({ data: null });

      await useOrderStore.getState().cancelOrder(99);

      expect(useOrderStore.getState().selectedOrder).toBeNull();
    });
  });
});
