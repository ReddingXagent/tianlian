// pages/orders/orders.js - 订单列表
// 性能优化：API缓存 + createPagination 分页控制器
const api = require('../../services/api');
const util = require('../../utils/util');
const config = require('../../config/index');
const { createPagination, guardTap } = require('../../utils/perf');

const STATUS_MAP = {
  charging: { text: '充电中', class: 'tag-success' },
  finished: { text: '已完成', class: 'tag-default' },
  cancelled: { text: '已取消', class: 'tag-default' },
  pending: { text: '待支付', class: 'tag-warning' }
};

Page({
  data: {
    tabs: [
      { label: '全部', value: '' },
      { label: '充电中', value: 'charging' },
      { label: '待支付', value: 'pending' },
      { label: '已完成', value: 'finished' }
    ],
    currentTab: '',
    orders: [],
    page: 1,
    pageSize: 10,
    hasMore: true,
    loading: false,
    loadingMore: false
  },

  onLoad() {
    this._initPagination('');
    this.loadOrders();
  },

  // 初始化分页控制器
  _initPagination(tab) {
    this._pagination = createPagination(
      async (page, pageSize) => {
        const res = await api.getOrders({ page, pageSize, status: tab || undefined });
        return res;
      },
      {
        pageSize: 10,
        cacheKey: `orders_${tab}`,
        cacheTtl: config.CACHE_TTL.ORDERS
      }
    );
  },

  onShow() {
    // 页面返回时刷新首页（使用缓存避免闪烁）
    if (this.data.currentTab !== undefined) {
      this.setData({ page: 1 });
      this.loadOrders(true);
    }
  },

  // 切换筛选（防连点）
  onTabChange: guardTap(function(e) {
    const { value } = e.currentTarget.dataset;
    if (value === this.data.currentTab) return;

    this.setData({ currentTab: value, orders: [], page: 1, hasMore: true });
    this._initPagination(value);
    this.loadOrders(true);
  }, 500),

  // 加载订单（使用分页控制器）
  async loadOrders(reload = false) {
    if (this._pagination && this._pagination.isLoading()) return;

    const isFirstPage = reload || this.data.page === 1;
    this.setData(isFirstPage ? { loading: true } : { loadingMore: true });

    try {
      const { list, hasMore, page } = await this._pagination.loadMore(reload);

      const orders = list.map(order => ({
        ...order,
        statusText: STATUS_MAP[order.status]?.text || order.status,
        statusClass: STATUS_MAP[order.status]?.class || 'tag-default',
        durationText: util.formatDuration(order.duration),
        amount: util.formatMoney(order.amount),
        createTime: util.formatTime(order.createTime, 'YYYY-MM-DD HH:mm'),
        showActions: order.status === 'pending' || order.status === 'charging'
      }));

      this.setData({
        orders,
        page,
        hasMore,
        loading: false,
        loadingMore: false
      });
    } catch (err) {
      this.setData({ loading: false, loadingMore: false });
      console.error('加载订单失败:', err);
    }
  },

  // 订单点击
  onOrderTap(e) {
    const { id } = e.currentTarget.dataset;
    wx.navigateTo({
      url: `/pages/order-detail/order-detail?orderId=${id}`
    });
  },

  // 去支付
  onPayOrder(e) {
    const { id } = e.currentTarget.dataset;
    wx.navigateTo({
      url: `/pages/payment/payment?orderId=${id}`
    });
  },

  // 查看充电
  onViewCharging(e) {
    const { id } = e.currentTarget.dataset;
    wx.navigateTo({
      url: `/pages/charging/charging?orderId=${id}`
    });
  },

  // 去充电
  onGoCharge() {
    wx.switchTab({
      url: '/pages/scan/scan'
    });
  },

  // 下拉刷新（防连点）
  onPullDownRefresh: guardTap(function() {
    this.setData({ page: 1 });
    this.loadOrders(true).then(() => {
      wx.stopPullDownRefresh();
    }).catch(() => wx.stopPullDownRefresh());
  }, 1000),

  // 上拉加载更多
  onReachBottom() {
    if (this.data.hasMore && !this.data.loadingMore) {
      this.setData({ page: this.data.page + 1 });
      this.loadOrders();
    }
  }
});
