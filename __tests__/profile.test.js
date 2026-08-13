// __tests__/profile.test.js - 我的页面测试
const mockShowToast = jest.fn();
const mockShowModal = jest.fn();
const mockNavigateTo = jest.fn();
const mockSwitchTab = jest.fn();

global.wx = {
  showToast: mockShowToast,
  showModal: mockShowModal,
  navigateTo: mockNavigateTo,
  switchTab: mockSwitchTab,
};

let pageConfig = null;
global.Page = (config) => { pageConfig = config; };

const mockGetWallet = jest.fn();
const mockApp = {
  getUserInfo: jest.fn(),
  getToken: jest.fn(),
  login: jest.fn(),
  globalData: {},
};
global.getApp = jest.fn(() => mockApp);

jest.mock('../services/api', () => ({
  getWallet: mockGetWallet,
}));
jest.mock('../config/index', () => ({
  CACHE_TTL: { ORDERS: 30000 },
}));
jest.mock('../utils/cache', () => ({
  cachedRequest: jest.fn(async (fn, args) => fn(...(args || []))),
}));

require('../pages/profile/profile');

describe('pages/profile/profile', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    pageConfig.setData = jest.fn(function(patch) {
      Object.assign(this.data, patch);
    });
    pageConfig.data = {
      userInfo: {},
      wallet: { balance: '0.00', couponCount: 0 },
    };
  });

  describe('loadUserInfo', () => {
    it('sets userInfo when available', () => {
      mockApp.getUserInfo.mockReturnValue({ nickName: 'Test', avatar: 'x' });
      pageConfig.loadUserInfo();
      expect(pageConfig.setData).toHaveBeenCalledWith({ userInfo: { nickName: 'Test', avatar: 'x' } });
    });

    it('does nothing when userInfo is null', () => {
      mockApp.getUserInfo.mockReturnValue(null);
      pageConfig.loadUserInfo();
      expect(pageConfig.setData).not.toHaveBeenCalled();
    });
  });

  describe('loadWallet', () => {
    it('loads wallet balance and couponCount', async () => {
      mockGetWallet.mockResolvedValue({ data: { balance: 88.5, couponCount: 3 } });
      await pageConfig.loadWallet();
      const call = pageConfig.setData.mock.calls.find(c => c[0].wallet);
      expect(call[0].wallet.balance).toBe('88.50');
      expect(call[0].wallet.couponCount).toBe(3);
    });

    it('handles missing fields with defaults', async () => {
      mockGetWallet.mockResolvedValue({ data: {} });
      await pageConfig.loadWallet();
      const call = pageConfig.setData.mock.calls.find(c => c[0].wallet);
      expect(call[0].wallet.balance).toBe('0.00');
      expect(call[0].wallet.couponCount).toBe(0);
    });

    it('handles error silently', async () => {
      mockGetWallet.mockRejectedValue(new Error('fail'));
      await expect(pageConfig.loadWallet()).resolves.toBeUndefined();
    });
  });

  describe('onLogin', () => {
    it('skips when already logged in', () => {
      mockApp.getToken.mockReturnValue('token123');
      pageConfig.onLogin();
      expect(mockApp.login).not.toHaveBeenCalled();
    });

    it('calls login when not logged in', () => {
      mockApp.getToken.mockReturnValue(null);
      mockApp.login.mockResolvedValue({});
      mockApp.getUserInfo.mockReturnValue({ name: 'X' });
      pageConfig.onLogin();
      expect(mockApp.login).toHaveBeenCalled();
    });

    it('shows toast on login failure', async () => {
      mockApp.getToken.mockReturnValue(null);
      mockApp.login.mockRejectedValue(new Error('fail'));
      pageConfig.onLogin();
      await new Promise((r) => setTimeout(r, 0));
      expect(mockShowToast).toHaveBeenCalledWith(expect.objectContaining({ title: '登录失败' }));
    });
  });

  describe('placeholder features', () => {
    it('onWalletTap shows toast', () => {
      pageConfig.onWalletTap();
      expect(mockShowToast).toHaveBeenCalledWith(expect.objectContaining({ title: '钱包功能开发中' }));
    });

    it('onRecharge shows toast', () => {
      pageConfig.onRecharge();
      expect(mockShowToast).toHaveBeenCalledWith(expect.objectContaining({ title: '充值功能开发中' }));
    });

    it('onMyVehicles shows toast', () => {
      pageConfig.onMyVehicles();
      expect(mockShowToast).toHaveBeenCalledWith(expect.objectContaining({ title: '车辆管理开发中' }));
    });

    it('onTransactions shows toast', () => {
      pageConfig.onTransactions();
      expect(mockShowToast).toHaveBeenCalledWith(expect.objectContaining({ title: '交易明细开发中' }));
    });

    it('onHelp shows toast', () => {
      pageConfig.onHelp();
      expect(mockShowToast).toHaveBeenCalledWith(expect.objectContaining({ title: '帮助中心开发中' }));
    });

    it('onFeedback shows toast', () => {
      pageConfig.onFeedback();
      expect(mockShowToast).toHaveBeenCalledWith(expect.objectContaining({ title: '意见反馈开发中' }));
    });

    it('onSettings shows toast', () => {
      pageConfig.onSettings();
      expect(mockShowToast).toHaveBeenCalledWith(expect.objectContaining({ title: '设置功能开发中' }));
    });
  });

  describe('navigation handlers', () => {
    it('onMyOrders switches tab', () => {
      pageConfig.onMyOrders();
      expect(mockSwitchTab).toHaveBeenCalledWith({ url: '/pages/orders/orders' });
    });

    it('onFavorites navigates', () => {
      pageConfig.onFavorites();
      expect(mockNavigateTo).toHaveBeenCalledWith({ url: '/pages/favorites/favorites' });
    });

    it('onNotifications navigates', () => {
      pageConfig.onNotifications();
      expect(mockNavigateTo).toHaveBeenCalledWith({ url: '/pages/notifications/notifications' });
    });

    it('onPoints navigates', () => {
      pageConfig.onPoints();
      expect(mockNavigateTo).toHaveBeenCalledWith({ url: '/pages/points/points' });
    });
  });

  describe('onAbout', () => {
    it('shows modal with app info', () => {
      pageConfig.onAbout();
      expect(mockShowModal).toHaveBeenCalledWith(expect.objectContaining({
        title: '关于天链充电',
        showCancel: false,
      }));
    });
  });
});
