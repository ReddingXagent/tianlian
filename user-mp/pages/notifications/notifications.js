// pages/notifications/notifications.js - 消息通知中心
// 性能优化：API缓存 + 分页数据合并
const api = require('../../services/api');
const util = require('../../utils/util');
const config = require('../../config/index');
const { cachedRequest } = require('../../utils/cache');
const { guardTap } = require('../../utils/perf');

const TYPE_CONFIG = {
  [config.NOTIFICATION_TYPES.CHARGE_FINISH]: { icon: '⚡', color: '#07C160', text: '充电完成' },
  [config.NOTIFICATION_TYPES.CHARGE_START]: { icon: '🔌', color: '#1890FF', text: '充电开始' },
  [config.NOTIFICATION_TYPES.PAYMENT_SUCCESS]: { icon: '💰', color: '#FF6B00', text: '支付成功' },
  [config.NOTIFICATION_TYPES.COUPON_EXPIRE]: { icon: '🎫', color: '#FA5151', text: '券到期提醒' },
  [config.NOTIFICATION_TYPES.SYSTEM]: { icon: '📢', color: '#666', text: '系统通知' },
  [config.NOTIFICATION_TYPES.PROMOTION]: { icon: '🎉', color: '#FF9500', text: '活动促销' }
};

Page({
  data: {
    tabs: [
      { label: '全部', value: '' },
      { label: '充电', value: 'charge' },
      { label: '优惠', value: 'coupon_expire' },
      { label: '系统', value: 'system' }
    ],
    currentTab: '',
    notifications: [],
    unreadCount: 0,
    page: 1,
    hasMore: true,
    loading: false,
    loadingMore: false
  },

  onLoad() {
    this.loadNotifications();
    this.loadUnreadCount();
  },

  onShow() {
    // 使用缓存减少重复请求
    this.loadNotifications();
    this.loadUnreadCount();
  },

  // 加载未读数量（带缓存）
  async loadUnreadCount(force = false) {
    try {
      const res = await cachedRequest(
        () => api.getUnreadNotificationCount(),
        [],
        { cacheKey: 'unread_count', ttl: config.CACHE_TTL.NOTIFICATIONS, force }
      );
      const count = res.data?.count || 0;
      this.setData({ unreadCount: count });

      if (count > 0) {
        wx.setTabBarBadge({ index: 3, text: String(count) });
      } else {
        wx.removeTabBarBadge({ index: 3 });
      }
    } catch (err) {
      // ignore
    }
  },

  // 切换tab（防连点）
  onTabChange: guardTap(function(e) {
    const { value } = e.currentTarget.dataset;
    if (value === this.data.currentTab) return;
    this.setData({ currentTab: value, page: 1, notifications: [], hasMore: true });
    this.loadNotifications(true);
  }, 500),

  // 加载通知列表
  async loadNotifications(force = false) {
    const { currentTab, page, loading, loadingMore } = this.data;
    if (loading || loadingMore) return;

    const isFirstPage = page === 1;
    const cacheKey = `notifications_${currentTab}_${page}`;

    if (force || !isFirstPage) {
      this.setData(isFirstPage ? { loading: true } : { loadingMore: true });
    }

    try {
      const res = await cachedRequest(
        (p, t) => api.getNotifications(p, t),
        [page, currentTab || undefined],
        { cacheKey, ttl: config.CACHE_TTL.NOTIFICATIONS, force }
      );

      const list = (res.data?.list || res.data || []).map(item => ({
        ...item,
        typeCfg: TYPE_CONFIG[item.type] || TYPE_CONFIG[config.NOTIFICATION_TYPES.SYSTEM],
        timeText: util.formatTime(item.createTime, 'MM-DD HH:mm'),
        isUnread: item.status === 'unread'
      }));

      const total = res.data?.total || list.length;
      this.setData({
        notifications: isFirstPage ? list : [...this.data.notifications, ...list],
        hasMore: this.data.notifications.length + list.length < total,
        loading: false,
        loadingMore: false
      });
    } catch (err) {
      this.setData({ loading: false, loadingMore: false });
    }
  },

  // 点击通知
  onNotificationTap(e) {
    const { id, status } = e.currentTarget.dataset;
    if (status === 'unread') {
      // eslint-disable-next-line no-empty-function -- fire-and-forget: 标记已读失败不阻塞本地状态更新
      api.markNotificationRead(id).catch(() => {});
      const notifications = this.data.notifications.map(n =>
        n.id === id ? { ...n, isUnread: false, status: 'read' } : n
      );
      this.setData({
        notifications,
        unreadCount: Math.max(0, this.data.unreadCount - 1)
      });
      // 更新未读缓存
      const { cache } = require('../../utils/cache');
      cache.delete('unread_count');
    }

    const item = this.data.notifications.find(n => n.id === id);
    if (item) {
      this.navigateByType(item);
    }
  },

  // 根据通知类型跳转
  navigateByType(item) {
    switch (item.type) {
      case config.NOTIFICATION_TYPES.CHARGE_FINISH:
      case config.NOTIFICATION_TYPES.CHARGE_START:
        if (item.orderId) {
          wx.navigateTo({ url: `/pages/order-detail/order-detail?orderId=${item.orderId}` });
        }
        break;
      case config.NOTIFICATION_TYPES.COUPON_EXPIRE:
        wx.navigateTo({ url: '/pages/coupons/coupons' });
        break;
      default:
        break;
    }
  },

  // 全部标记已读（防连点）
  onMarkAllRead: guardTap(async function() {
    try {
      await api.markAllNotificationsRead();
      const notifications = this.data.notifications.map(n => ({
        ...n, isUnread: false, status: 'read'
      }));
      this.setData({ notifications, unreadCount: 0 });
      wx.removeTabBarBadge({ index: 3 });
      // 清除相关缓存
      const { cache } = require('../../utils/cache');
      cache.clearByPrefix('notifications_');
      cache.delete('unread_count');
      wx.showToast({ title: '已全部标为已读', icon: 'success' });
    } catch (err) {
      console.error('标记失败:', err);
    }
  }, 2000),

  // 下拉刷新（防连点）
  onPullDownRefresh: guardTap(function() {
    this.setData({ page: 1, notifications: [], hasMore: true });
    Promise.all([
      this.loadNotifications(true),
      this.loadUnreadCount(true)
    ]).then(() => wx.stopPullDownRefresh()).catch(() => wx.stopPullDownRefresh());
  }, 1000),

  // 上拉加载更多
  onReachBottom() {
    if (this.data.hasMore && !this.data.loadingMore) {
      this.setData({ page: this.data.page + 1 });
      this.loadNotifications();
    }
  }
});
