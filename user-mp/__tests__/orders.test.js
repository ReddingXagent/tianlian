// __tests__/orders.test.js - 订单列表页面测试
const mockNavigateTo = jest.fn();
const mockSwitchTab = jest.fn();
const mockStopPullDown = jest.fn();

global.wx = {
  navigateTo: mockNavigateTo,
  switchTab: mockSwitchTab,
  stopPullDownRefresh: mockStopPullDown,
};

let pageConfig = null;
global.Page = (config) => { pageConfig = config; };

const mockGetOrders = jest.fn();
jest.mock('../services/api', () => ({
  getOrders: mockGetOrders,
}));
jest.mock('../utils/util', () => ({
  formatDuration: jest.fn((d) => `${d}分钟`),
  formatMoney: jest.fn((a) => `¥${a}`),
  formatTime: jest.fn(() => '2026-08-13 12:00'),
}));
jest.mock('../config/index', () => ({ CACHE_TTL: { ORDERS: 30000 } }));

const mockLoadMore = jest.fn();
const mockIsLoading = jest.fn(() => false);
jest.mock('../utils/perf', () => ({
  createPagination: jest.fn(() => ({ loadMore: mockLoadMore, isLoading: mockIsLoading })),
  guardTap: (fn) => fn,
}));

require('../pages/orders/orders');

describe('pages/orders/orders', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockIsLoading.mockReturnValue(false);
    pageConfig.setData = jest.fn(function(patch) {
      Object.assign(this.data, patch);
    });
    pageConfig.data = {
      tabs: [], currentTab: '', orders: [], page: 1, pageSize: 10,
      hasMore: true, loading: false, loadingMore: false,
    };
  });

  describe('onLoad', () => {
    it('initializes pagination and loads orders', () => {
      const orig = pageConfig.loadOrders;
      pageConfig.loadOrders = jest.fn();
      pageConfig.onLoad();
      expect(pageConfig.loadOrders).toHaveBeenCalled();
      pageConfig.loadOrders = orig;
    });
  });

  describe('loadOrders', () => {
    it('maps orders with status text and formatting', async () => {
      mockLoadMore.mockResolvedValue({
        list: [
          { id: 'O1', status: 'charging', duration: 30, amount: 12.5, createTime: 'x' },
          { id: 'O2', status: 'pending', duration: 0, amount: 0, createTime: 'x' },
          { id: 'O3', status: 'weird', duration: 5, amount: 1, createTime: 'x' },
        ],
        hasMore: true,
        page: 1,
      });

      await pageConfig.loadOrders(true);

      const finalCall = pageConfig.setData.mock.calls[pageConfig.setData.mock.calls.length - 1][0];
      expect(finalCall.orders).toHaveLength(3);
      expect(finalCall.orders[0].statusText).toBe('充电中');
      expect(finalCall.orders[0].statusClass).toBe('tag-success');
      expect(finalCall.orders[0].showActions).toBe(true);
      expect(finalCall.orders[1].statusText).toBe('待支付');
      expect(finalCall.orders[1].showActions).toBe(true);
      // 未知状态回退
      expect(finalCall.orders[2].statusText).toBe('weird');
      expect(finalCall.orders[2].statusClass).toBe('tag-default');
      expect(finalCall.orders[2].showActions).toBe(false);
      expect(finalCall.loading).toBe(false);
      expect(finalCall.loadingMore).toBe(false);
    });

    it('skips load when pagination is already loading', async () => {
      mockIsLoading.mockReturnValue(true);
      await pageConfig.loadOrders(true);
      expect(mockLoadMore).not.toHaveBeenCalled();
    });

    it('handles loadMore error gracefully', async () => {
      mockLoadMore.mockRejectedValue(new Error('fail'));
      await pageConfig.loadOrders(true);
      const finalCall = pageConfig.setData.mock.calls[pageConfig.setData.mock.calls.length - 1][0];
      expect(finalCall.loading).toBe(false);
      expect(finalCall.loadingMore).toBe(false);
    });
  });

  describe('onTabChange', () => {
    it('ignores same tab', () => {
      pageConfig.data.currentTab = 'charging';
      const orig = pageConfig.loadOrders;
      pageConfig.loadOrders = jest.fn();
      pageConfig.onTabChange({ currentTarget: { dataset: { value: 'charging' } } });
      expect(pageConfig.loadOrders).not.toHaveBeenCalled();
      pageConfig.loadOrders = orig;
    });

    it('switches tab and reloads', () => {
      pageConfig.data.currentTab = '';
      const orig = pageConfig.loadOrders;
      pageConfig.loadOrders = jest.fn();
      pageConfig.onTabChange({ currentTarget: { dataset: { value: 'pending' } } });
      expect(pageConfig.loadOrders).toHaveBeenCalledWith(true);
      pageConfig.loadOrders = orig;
    });
  });

  describe('navigation handlers', () => {
    it('onOrderTap navigates to detail', () => {
      pageConfig.onOrderTap({ currentTarget: { dataset: { id: 'O1' } } });
      expect(mockNavigateTo).toHaveBeenCalledWith({ url: '/pages/order-detail/order-detail?orderId=O1' });
    });

    it('onPayOrder navigates to payment', () => {
      pageConfig.onPayOrder({ currentTarget: { dataset: { id: 'O2' } } });
      expect(mockNavigateTo).toHaveBeenCalledWith({ url: '/pages/payment/payment?orderId=O2' });
    });

    it('onViewCharging navigates to charging page', () => {
      pageConfig.onViewCharging({ currentTarget: { dataset: { id: 'O3' } } });
      expect(mockNavigateTo).toHaveBeenCalledWith({ url: '/pages/charging/charging?orderId=O3' });
    });

    it('onGoCharge switches to scan tab', () => {
      pageConfig.onGoCharge();
      expect(mockSwitchTab).toHaveBeenCalledWith({ url: '/pages/scan/scan' });
    });
  });

  describe('onReachBottom', () => {
    it('loads more when hasMore and not loading', () => {
      pageConfig.data.hasMore = true;
      pageConfig.data.loadingMore = false;
      const orig = pageConfig.loadOrders;
      pageConfig.loadOrders = jest.fn();
      pageConfig.onReachBottom();
      expect(pageConfig.loadOrders).toHaveBeenCalled();
      pageConfig.loadOrders = orig;
    });

    it('does not load when !hasMore', () => {
      pageConfig.data.hasMore = false;
      const orig = pageConfig.loadOrders;
      pageConfig.loadOrders = jest.fn();
      pageConfig.onReachBottom();
      expect(pageConfig.loadOrders).not.toHaveBeenCalled();
      pageConfig.loadOrders = orig;
    });
  });
});
