// __tests__/notifications.test.js - 消息通知页面测试
const mockSetTabBarBadge = jest.fn();
const mockRemoveTabBarBadge = jest.fn();
const mockNavigateTo = jest.fn();

global.wx = {
  setTabBarBadge: mockSetTabBarBadge,
  removeTabBarBadge: mockRemoveTabBarBadge,
  navigateTo: mockNavigateTo,
};

let pageConfig = null;
global.Page = (config) => { pageConfig = config; };

const mockGetNotifications = jest.fn();
const mockGetUnreadCount = jest.fn();
const mockMarkRead = jest.fn().mockResolvedValue({});
const mockMarkAllRead = jest.fn().mockResolvedValue({});
jest.mock('../services/api', () => ({
  getNotifications: mockGetNotifications,
  getUnreadNotificationCount: mockGetUnreadCount,
  markNotificationRead: mockMarkRead,
  markAllNotificationsRead: mockMarkAllRead,
}));
jest.mock('../utils/util', () => ({
  formatTime: jest.fn(() => '08-13 12:00'),
}));
jest.mock('../config/index', () => ({
  CACHE_TTL: { NOTIFICATIONS: 30000 },
  NOTIFICATION_TYPES: {
    CHARGE_FINISH: 'charge_finish',
    CHARGE_START: 'charge_start',
    PAYMENT_SUCCESS: 'payment_success',
    COUPON_EXPIRE: 'coupon_expire',
    SYSTEM: 'system',
    PROMOTION: 'promotion',
  },
}));
jest.mock('../utils/cache', () => ({
  cachedRequest: jest.fn(async (fn, args) => {
    const res = await fn(...(args || []));
    return res;
  }),
  cache: { delete: jest.fn(), clearByPrefix: jest.fn() },
}));
jest.mock('../utils/perf', () => ({ guardTap: (fn) => fn }));

require('../pages/notifications/notifications');

describe('pages/notifications/notifications', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    pageConfig.setData = jest.fn(function(patch) {
      Object.assign(this.data, patch);
    });
    pageConfig.data = {
      tabs: [], currentTab: '', notifications: [], unreadCount: 0,
      page: 1, hasMore: true, loading: false, loadingMore: false,
    };
  });

  describe('loadUnreadCount', () => {
    it('sets badge when count > 0', async () => {
      mockGetUnreadCount.mockResolvedValue({ data: { count: 5 } });
      await pageConfig.loadUnreadCount(true);
      expect(mockSetTabBarBadge).toHaveBeenCalledWith({ index: 3, text: '5' });
    });

    it('removes badge when count = 0', async () => {
      mockGetUnreadCount.mockResolvedValue({ data: { count: 0 } });
      await pageConfig.loadUnreadCount(true);
      expect(mockRemoveTabBarBadge).toHaveBeenCalledWith({ index: 3 });
    });

    it('handles error silently', async () => {
      mockGetUnreadCount.mockRejectedValue(new Error('x'));
      await expect(pageConfig.loadUnreadCount(true)).resolves.toBeUndefined();
    });
  });

  describe('loadNotifications', () => {
    it('maps notifications with type config and unread flag', async () => {
      mockGetNotifications.mockResolvedValue({
        data: {
          list: [
            { id: 1, type: 'charge_finish', status: 'unread', createTime: 'x' },
            { id: 2, type: 'unknown_type', status: 'read', createTime: 'x' },
          ],
        },
      });

      await pageConfig.loadNotifications(true);

      const calls = pageConfig.setData.mock.calls;
      const finalCall = calls[calls.length - 1][0];
      expect(finalCall.notifications).toHaveLength(2);
      expect(finalCall.notifications[0].typeCfg.text).toBe('充电完成');
      expect(finalCall.notifications[0].isUnread).toBe(true);
      // 未知类型回退到系统通知
      expect(finalCall.notifications[1].typeCfg.text).toBe('系统通知');
      expect(finalCall.notifications[1].isUnread).toBe(false);
    });

    it('skips load when already loading', async () => {
      pageConfig.data.loading = true;
      await pageConfig.loadNotifications(true);
      expect(mockGetNotifications).not.toHaveBeenCalled();
    });

    it('handles API error gracefully', async () => {
      mockGetNotifications.mockRejectedValue(new Error('fail'));
      await pageConfig.loadNotifications(true);
      const calls = pageConfig.setData.mock.calls;
      const finalCall = calls[calls.length - 1][0];
      expect(finalCall.loading).toBe(false);
      expect(finalCall.loadingMore).toBe(false);
    });
  });

  describe('onTabChange', () => {
    it('ignores same tab', () => {
      pageConfig.data.currentTab = 'charge';
      const orig = pageConfig.loadNotifications;
      pageConfig.loadNotifications = jest.fn();
      pageConfig.onTabChange({ currentTarget: { dataset: { value: 'charge' } } });
      expect(pageConfig.loadNotifications).not.toHaveBeenCalled();
      pageConfig.loadNotifications = orig;
    });

    it('switches tab and reloads', () => {
      pageConfig.data.currentTab = '';
      const orig = pageConfig.loadNotifications;
      pageConfig.loadNotifications = jest.fn();
      pageConfig.onTabChange({ currentTarget: { dataset: { value: 'system' } } });
      expect(pageConfig.loadNotifications).toHaveBeenCalledWith(true);
      pageConfig.loadNotifications = orig;
    });
  });

  describe('navigateByType', () => {
    it('navigates to order detail for charge_finish with orderId', () => {
      pageConfig.navigateByType({ type: 'charge_finish', orderId: 'O9' });
      expect(mockNavigateTo).toHaveBeenCalledWith({ url: '/pages/order-detail/order-detail?orderId=O9' });
    });

    it('does not navigate for charge_finish without orderId', () => {
      pageConfig.navigateByType({ type: 'charge_finish' });
      expect(mockNavigateTo).not.toHaveBeenCalled();
    });

    it('navigates to coupons for coupon_expire', () => {
      pageConfig.navigateByType({ type: 'coupon_expire' });
      expect(mockNavigateTo).toHaveBeenCalledWith({ url: '/pages/coupons/coupons' });
    });

    it('does not navigate for other types', () => {
      pageConfig.navigateByType({ type: 'system' });
      expect(mockNavigateTo).not.toHaveBeenCalled();
    });
  });

  describe('onNotificationTap', () => {
    it('marks unread notification read and decrements count', () => {
      pageConfig.data.notifications = [
        { id: 1, type: 'system', status: 'unread', isUnread: true },
      ];
      pageConfig.data.unreadCount = 2;
      pageConfig.onNotificationTap({ currentTarget: { dataset: { id: 1, status: 'unread' } } });
      expect(mockMarkRead).toHaveBeenCalledWith(1);
      const call = pageConfig.setData.mock.calls.find((c) => c[0].notifications);
      expect(call[0].notifications[0].isUnread).toBe(false);
      expect(call[0].unreadCount).toBe(1);
    });

    it('does not call markRead for already-read notification', () => {
      pageConfig.data.notifications = [
        { id: 2, type: 'system', status: 'read', isUnread: false },
      ];
      pageConfig.onNotificationTap({ currentTarget: { dataset: { id: 2, status: 'read' } } });
      expect(mockMarkRead).not.toHaveBeenCalled();
    });
  });

  describe('onMarkAllRead', () => {
    it('marks all read and clears badge', async () => {
      const mockShowToast = jest.fn();
      global.wx.showToast = mockShowToast;
      pageConfig.data.notifications = [
        { id: 1, status: 'unread', isUnread: true },
        { id: 2, status: 'unread', isUnread: true },
      ];
      pageConfig.data.unreadCount = 2;
      await pageConfig.onMarkAllRead();
      expect(mockMarkAllRead).toHaveBeenCalled();
      const call = pageConfig.setData.mock.calls.find((c) => c[0].notifications);
      expect(call[0].unreadCount).toBe(0);
      expect(call[0].notifications.every((n) => !n.isUnread)).toBe(true);
    });
  });
});
