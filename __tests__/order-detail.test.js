// __tests__/order-detail.test.js - 订单详情页面测试
const mockNavigateTo = jest.fn();
const mockStopPullDown = jest.fn();

global.wx = {
  navigateTo: mockNavigateTo,
  stopPullDownRefresh: mockStopPullDown,
};

let pageConfig = null;
global.Page = (config) => { pageConfig = config; };

const mockGetOrderDetail = jest.fn();
jest.mock('../services/api', () => ({
  getOrderDetail: mockGetOrderDetail,
}));
jest.mock('../utils/util', () => ({
  formatDuration: jest.fn((d) => `${d}分钟`),
  formatMoney: jest.fn((a) => `¥${a}`),
  formatTime: jest.fn((_t) => '08-13 12:00'),
}));
jest.mock('../config/index', () => ({ CACHE_TTL: { ORDERS: 30000 } }));
jest.mock('../utils/cache', () => ({
  cachedRequest: jest.fn(async (fn, args) => {
    const res = await fn(...(args || []));
    return res;
  }),
}));

require('../pages/order-detail/order-detail');

describe('pages/order-detail/order-detail', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    pageConfig.setData = jest.fn();
    pageConfig.data = { orderId: 'ORD001', order: null, loading: false };
  });

  describe('onLoad', () => {
    it('sets orderId and loads detail', () => {
      const orig = pageConfig.loadOrderDetail;
      pageConfig.loadOrderDetail = jest.fn();
      pageConfig.onLoad({ orderId: 'ORD123' });
      expect(pageConfig.setData).toHaveBeenCalledWith({ orderId: 'ORD123' });
      expect(pageConfig.loadOrderDetail).toHaveBeenCalled();
      pageConfig.loadOrderDetail = orig;
    });
  });

  describe('loadOrderDetail', () => {
    it('loads and maps charging order correctly', async () => {
      mockGetOrderDetail.mockResolvedValue({
        data: {
          id: 'ORD001', status: 'charging', duration: 30,
          amount: 15.50, energy: 10.5, startTime: '2026-08-13T10:00:00',
          endTime: null,
        }
      });

      await pageConfig.loadOrderDetail(true);
      const call = pageConfig.setData.mock.calls.find(c => c[0].order);
      expect(call).toBeTruthy();
      const order = call[0].order;
      expect(order.statusText).toBe('充电中');
      expect(order.statusIcon).toBe('⚡');
      expect(order.durationText).toBe('30分钟');
      expect(order.amount).toBe('¥15.5');
      expect(order.avgPower).toBe('21.00');
      expect(order.showPay).toBe(false);
    });

    it('maps pending status with showPay=true', async () => {
      mockGetOrderDetail.mockResolvedValue({
        data: { id: 'ORD002', status: 'pending', duration: 0, amount: 0, energy: 0, startTime: null, endTime: null }
      });

      await pageConfig.loadOrderDetail(true);
      const call = pageConfig.setData.mock.calls.find(c => c[0].order);
      const order = call[0].order;
      expect(order.statusText).toBe('待支付');
      expect(order.showPay).toBe(true);
    });

    it('maps finished status correctly', async () => {
      mockGetOrderDetail.mockResolvedValue({
        data: { id: 'ORD003', status: 'finished', duration: 60, amount: 42.0, energy: 30, startTime: '2026-08-13T10:00:00', endTime: '2026-08-13T11:00:00' }
      });

      await pageConfig.loadOrderDetail(true);
      const call = pageConfig.setData.mock.calls.find(c => c[0].order);
      expect(call[0].order.statusText).toBe('已完成');
      expect(call[0].order.endTime).toBe('08-13 12:00');
    });

    it('handles unknown status with fallback', async () => {
      mockGetOrderDetail.mockResolvedValue({
        data: { id: 'ORD004', status: 'unknown_status', duration: 0, amount: 0, energy: 0, startTime: null, endTime: null }
      });

      await pageConfig.loadOrderDetail(true);
      const call = pageConfig.setData.mock.calls.find(c => c[0].order);
      expect(call[0].order.statusText).toBe('已完成'); // fallback
    });

    it('handles API error gracefully', async () => {
      mockGetOrderDetail.mockRejectedValue(new Error('network'));
      await pageConfig.loadOrderDetail(true);
      expect(pageConfig.setData).toHaveBeenCalledWith(expect.objectContaining({ loading: false }));
    });
  });

  describe('onPay', () => {
    it('navigates to payment page', () => {
      pageConfig.data = { orderId: 'ORD001' };
      pageConfig.onPay();
      expect(mockNavigateTo).toHaveBeenCalledWith({ url: '/pages/payment/payment?orderId=ORD001' });
    });
  });

  describe('onPullDownRefresh', () => {
    it('reloads and stops refresh', async () => {
      // F1208 弱假绿加固: 源码loadOrderDetail的catch吞错后promise仍resolve,
      // .then里stopPullDownRefresh在成功/失败两条路径都会调用 — 裸toHaveBeenCalled()
      // 无法区分真重载与catch兜底凑数。加请求计数+order值断言锚定成功路径。
      mockGetOrderDetail.mockClear();
      mockGetOrderDetail.mockResolvedValue({ data: { status: 'finished', duration: 0, amount: 0, energy: 0, startTime: null, endTime: null } });
      pageConfig.onPullDownRefresh();
      // 页面方法返回 void，内部 .then 需要额外微任务冲刷
      await new Promise((r) => { setTimeout(r, 0); });
      expect(mockGetOrderDetail).toHaveBeenCalledTimes(1); // 真实触发了重载请求(非零调用凑数)
      const call = pageConfig.setData.mock.calls.find(c => c[0].order);
      expect(call).toBeTruthy(); // fail-fast: 成功路径必须写order数据(走catch则无)
      expect(call[0].order.statusText).toBe('已完成');
      expect(mockStopPullDown).toHaveBeenCalledTimes(1);
    });
  });
});
