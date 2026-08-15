// __tests__/coupons.test.js - 优惠券页面测试
const mockShowToast = jest.fn();
const mockSwitchTab = jest.fn();

global.wx = {
  showToast: mockShowToast,
  switchTab: mockSwitchTab,
};

let pageConfig = null;
global.Page = (config) => { pageConfig = config; };
global.getApp = jest.fn(() => ({ globalData: {} }));

const mockGetCoupons = jest.fn();
const mockClaimCoupon = jest.fn();
jest.mock('../services/api', () => ({
  getCoupons: mockGetCoupons,
  claimCoupon: mockClaimCoupon,
}));
jest.mock('../utils/util', () => ({
  formatTime: jest.fn(() => '2026.08.13'),
}));
jest.mock('../config/index', () => ({
  CACHE_TTL: { COUPONS: 60000 },
  COUPON_STATUS: { UNUSED: 'unused', USED: 'used', EXPIRED: 'expired' },
  COUPON_TYPE: { AMOUNT: 'amount', DISCOUNT: 'discount', FREIGHT: 'freight' },
}));
jest.mock('../utils/cache', () => ({
  cachedRequest: jest.fn((fn, args) => Promise.resolve(fn(...(args || [])))),
}));
jest.mock('../utils/perf', () => ({ guardTap: (fn) => fn }));

require('../pages/coupons/coupons');

describe('pages/coupons/coupons', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    pageConfig.setData = jest.fn(function(patch) {
      Object.assign(this.data, patch);
    });
    pageConfig.data = {
      tabs: [], currentTab: 'unused', coupons: [], loading: false,
      couponCode: '', showClaimInput: false, claiming: false,
    };
  });

  describe('loadCoupons', () => {
    it('maps coupons with type text and formatting', async () => {
      mockGetCoupons.mockResolvedValue({
        data: {
          list: [
            { id: 1, type: 'amount', status: 'unused', value: 5, minAmount: 20, expireTime: 'x' },
            { id: 2, type: 'discount', status: 'used', value: 8, minAmount: 0, expireTime: null },
          ],
        },
      });

      await pageConfig.loadCoupons(true);
      const call = pageConfig.setData.mock.calls.find(c => c[0].coupons);
      expect(call).toBeTruthy();
      const cs = call[0].coupons;
      expect(cs).toHaveLength(2);
      expect(cs[0].typeText).toBe('满减券');
      expect(cs[0].amountText).toBe('¥5');
      expect(cs[0].minAmountText).toBe('满¥20可用');
      expect(cs[0].statusCfg.text).toBe('可使用');
      expect(cs[1].typeText).toBe('折扣券');
      expect(cs[1].amountText).toBe('8折');
      expect(cs[1].minAmountText).toBe('无门槛');
      expect(cs[1].expireText).toBe('长期有效');
    });

    it('handles empty list', async () => {
      mockGetCoupons.mockResolvedValue({ data: { list: [] } });
      await pageConfig.loadCoupons(true);
      const call = pageConfig.setData.mock.calls.find(c => c[0].coupons);
      expect(call[0].coupons).toHaveLength(0);
    });

    it('handles API error', async () => {
      mockGetCoupons.mockRejectedValue(new Error('fail'));
      await pageConfig.loadCoupons(true);
      expect(pageConfig.setData.mock.calls.at(-1)[0].loading).toBe(false);
    });
  });

  describe('onTabChange', () => {
    it('ignores same tab', () => {
      pageConfig.data.currentTab = 'unused';
      const orig = pageConfig.loadCoupons;
      pageConfig.loadCoupons = jest.fn();
      pageConfig.onTabChange({ currentTarget: { dataset: { value: 'unused' } } });
      expect(pageConfig.loadCoupons).not.toHaveBeenCalled();
      pageConfig.loadCoupons = orig;
    });

    it('switches tab and reloads', () => {
      pageConfig.data.currentTab = 'unused';
      const orig = pageConfig.loadCoupons;
      pageConfig.loadCoupons = jest.fn();
      pageConfig.onTabChange({ currentTarget: { dataset: { value: 'used' } } });
      expect(pageConfig.setData).toHaveBeenCalledWith(expect.objectContaining({ currentTab: 'used' }));
      expect(pageConfig.loadCoupons).toHaveBeenCalled();
      pageConfig.loadCoupons = orig;
    });
  });

  describe('onToggleClaim', () => {
    it('toggles claim input visibility', () => {
      pageConfig.data.showClaimInput = false;
      pageConfig.onToggleClaim();
      expect(pageConfig.setData).toHaveBeenCalledWith(expect.objectContaining({ showClaimInput: true, couponCode: '' }));
    });
  });

  describe('onCodeInput', () => {
    it('updates couponCode', () => {
      pageConfig.onCodeInput({ detail: { value: 'ABC123' } });
      expect(pageConfig.setData).toHaveBeenCalledWith({ couponCode: 'ABC123' });
    });
  });

  describe('onClaim', () => {
    it('shows toast when code is empty', async () => {
      pageConfig.data.couponCode = '';
      await pageConfig.onClaim();
      expect(mockShowToast).toHaveBeenCalledWith(expect.objectContaining({ title: '请输入兑换码' }));
    });

    it('claims coupon successfully', async () => {
      mockClaimCoupon.mockResolvedValue({});
      const orig = pageConfig.loadCoupons;
      pageConfig.loadCoupons = jest.fn();
      pageConfig.data.couponCode = 'CODE123';
      await pageConfig.onClaim();
      expect(mockClaimCoupon).toHaveBeenCalledWith('CODE123');
      expect(mockShowToast).toHaveBeenCalledWith(expect.objectContaining({ title: '领取成功' }));
      pageConfig.loadCoupons = orig;
    });
  });

  describe('onUseCoupon', () => {
    it('stores selected coupon and navigates', () => {
      global.getApp = jest.fn(() => ({ globalData: {} }));
      pageConfig.data.coupons = [{ id: 1, type: 'amount' }];
      pageConfig.onUseCoupon({ currentTarget: { dataset: { id: 1 } } });
      expect(mockSwitchTab).toHaveBeenCalledWith({ url: '/pages/index/index' });
    });
  });
});
