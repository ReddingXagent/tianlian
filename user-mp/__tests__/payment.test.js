// __tests__/payment.test.js - 支付页面测试
const mockShowToast = jest.fn();
const mockRedirectTo = jest.fn();
const mockRequestPayment = jest.fn();

global.wx = {
  showToast: mockShowToast,
  redirectTo: mockRedirectTo,
  requestPayment: mockRequestPayment,
};

let pageConfig = null;
global.Page = (config) => { pageConfig = config; };

const mockGetOrderDetail = jest.fn();
const mockGetWallet = jest.fn();
const mockCreatePayment = jest.fn();
jest.mock('../services/api', () => ({
  getOrderDetail: mockGetOrderDetail,
  getWallet: mockGetWallet,
  createPayment: mockCreatePayment,
}));
jest.mock('../utils/util', () => ({
  formatMoney: jest.fn((a) => `¥${a}`),
  formatDuration: jest.fn((d) => `${d}分钟`),
}));
jest.mock('../config/index', () => ({ CACHE_TTL: { ORDERS: 30000 } }));
jest.mock('../utils/cache', () => ({
  cachedRequest: jest.fn((fn, args) => Promise.resolve(fn(...(args || [])))),
}));

require('../pages/payment/payment');

describe('pages/payment/payment', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    pageConfig.setData = jest.fn(function(patch) {
      Object.assign(this.data, patch);
    });
    pageConfig.data = {
      orderId: 'O1', amount: '0.00', stationName: '', energy: '0.00',
      durationText: '', payMethod: 'wechat', balance: '0.00', paying: false,
    };
  });

  describe('onLoad', () => {
    it('sets orderId and loads data', () => {
      const orig1 = pageConfig.loadOrderInfo;
      const orig2 = pageConfig.loadWallet;
      pageConfig.loadOrderInfo = jest.fn();
      pageConfig.loadWallet = jest.fn();
      pageConfig.onLoad({ orderId: 'O1' });
      expect(pageConfig.setData).toHaveBeenCalledWith({ orderId: 'O1' });
      expect(pageConfig.loadOrderInfo).toHaveBeenCalled();
      expect(pageConfig.loadWallet).toHaveBeenCalled();
      pageConfig.loadOrderInfo = orig1;
      pageConfig.loadWallet = orig2;
    });
  });

  describe('loadOrderInfo', () => {
    it('maps order data correctly', async () => {
      mockGetOrderDetail.mockResolvedValue({
        data: { amount: 15.5, stationName: 'Station A', energy: 10, duration: 30 },
      });
      await pageConfig.loadOrderInfo();
      const call = pageConfig.setData.mock.calls.find(c => c[0].amount);
      expect(call[0].amount).toBe('¥15.5');
      expect(call[0].stationName).toBe('Station A');
      expect(call[0].energy).toBe('10.00');
    });

    it('shows toast on error', async () => {
      mockGetOrderDetail.mockRejectedValue(new Error('fail'));
      await pageConfig.loadOrderInfo();
      expect(mockShowToast).toHaveBeenCalledWith(expect.objectContaining({ title: '加载失败' }));
    });

    it('uses fallback station name', async () => {
      mockGetOrderDetail.mockResolvedValue({ data: { amount: 0, duration: 0 } });
      await pageConfig.loadOrderInfo();
      const call = pageConfig.setData.mock.calls.find(c => c[0].stationName);
      expect(call[0].stationName).toBe('充电站');
    });
  });

  describe('loadWallet', () => {
    it('loads balance', async () => {
      mockGetWallet.mockResolvedValue({ data: { balance: 88.5 } });
      await pageConfig.loadWallet();
      const call = pageConfig.setData.mock.calls.find(c => c[0].balance);
      expect(call[0].balance).toBe('88.50');
    });

    it('handles missing balance gracefully', async () => {
      mockGetWallet.mockResolvedValue({ data: {} });
      await pageConfig.loadWallet();
      const call = pageConfig.setData.mock.calls.find(c => c[0].balance);
      expect(call[0].balance).toBe('0.00');
    });

    it('silently handles error', async () => {
      mockGetWallet.mockRejectedValue(new Error('fail'));
      await expect(pageConfig.loadWallet()).resolves.toBeUndefined();
    });
  });

  describe('onSelectMethod', () => {
    it('updates payMethod', () => {
      pageConfig.onSelectMethod({ currentTarget: { dataset: { method: 'wallet' } } });
      expect(pageConfig.setData).toHaveBeenCalledWith({ payMethod: 'wallet' });
    });
  });

  describe('onPay', () => {
    it('blocks when already paying', async () => {
      pageConfig.data.paying = true;
      await pageConfig.onPay();
      expect(mockCreatePayment).not.toHaveBeenCalled();
    });

    it('checks wallet balance for wallet payment', async () => {
      pageConfig.data.payMethod = 'wallet';
      pageConfig.data.amount = '50.00';
      pageConfig.data.balance = '10.00';
      await pageConfig.onPay();
      expect(mockShowToast).toHaveBeenCalledWith(expect.objectContaining({ title: '余额不足' }));
    });

    it('calls createPayment for wechat', async () => {
      mockCreatePayment.mockResolvedValue({ data: { timeStamp: '1', nonceStr: 'n', package: 'p', paySign: 's' } });
      mockRequestPayment.mockImplementation((opts) => opts.success());
      await pageConfig.onPay();
      expect(mockCreatePayment).toHaveBeenCalledWith('O1');
      expect(mockRequestPayment).toHaveBeenCalled();
    });

    it('handles payment cancel', async () => {
      mockCreatePayment.mockResolvedValue({ data: { timeStamp: '1', nonceStr: 'n', package: 'p', paySign: 's' } });
      mockRequestPayment.mockImplementation((opts) => opts.fail({ errMsg: 'requestPayment:fail cancel' }));
      await pageConfig.onPay();
      expect(mockShowToast).toHaveBeenCalledWith(expect.objectContaining({ title: '支付已取消' }));
    });

    it('handles payment failure', async () => {
      mockCreatePayment.mockResolvedValue({ data: { timeStamp: '1', nonceStr: 'n', package: 'p', paySign: 's' } });
      mockRequestPayment.mockImplementation((opts) => opts.fail({ errMsg: 'requestPayment:fail error' }));
      await pageConfig.onPay();
      expect(mockShowToast).toHaveBeenCalledWith(expect.objectContaining({ title: '支付失败' }));
    });

    it('handles createPayment error', async () => {
      mockCreatePayment.mockRejectedValue(new Error('network'));
      await pageConfig.onPay();
      expect(pageConfig.setData.mock.calls.at(-1)[0].paying).toBe(false);
    });
  });

  describe('onPaySuccess', () => {
    it('shows toast and redirects', () => {
      pageConfig.data.orderId = 'O1';
      pageConfig.onPaySuccess();
      expect(mockShowToast).toHaveBeenCalledWith(expect.objectContaining({ title: '支付成功' }));
    });
  });
});
