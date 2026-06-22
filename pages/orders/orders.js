// pages/orders/orders.js - 订单列表
const api = require('../../services/api');
const util = require('../../utils/util');

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
    this.loadOrders();
  },

  onShow() {
    // 每次显示时刷新第一页
    this.setData({ page: 1, orders: [], hasMore: true });
    this.loadOrders();
  },

  // 切换筛选
  onTabChange(e) {
    const { value } = e.currentTarget.dataset;
    if (value === this.data.currentTab) return;

    this.setData({
      currentTab: value,
      page: 1,
      orders: [],
      hasMore: true
    });
    this.loadOrders();
  },

  // 加载订单
  async loadOrders() {
    const { currentTab, page, pageSize, loading, loadingMore } = this.data;

    if (loading || loadingMore) return;

    const isFirstPage = page === 1;
    this.setData(isFirstPage ? { loading: true } : { loadingMore: true });

    try {
      const res = await api.getOrders({
        page,
        pageSize,
        status: currentTab || undefined
      });

      const orders = (res.data?.list || res.data || []).map(order => ({
        ...order,
        statusText: STATUS_MAP[order.status]?.text || order.status,
        statusClass: STATUS_MAP[order.status]?.class || 'tag-default',
        durationText: util.formatDuration(order.duration),
        amount: util.formatMoney(order.amount),
        createTime: util.formatTime(order.createTime, 'YYYY-MM-DD HH:mm'),
        showActions: order.status === 'pending' || order.status === 'charging'
      }));

      const total = res.data?.total || orders.length;

      this.setData({
        orders: isFirstPage ? orders : [...this.data.orders, ...orders],
        hasMore: this.data.orders.length + orders.length < total,
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

  // 下拉刷新
  onPullDownRefresh() {
    this.setData({ page: 1, orders: [], hasMore: true });
    this.loadOrders().then(() => {
      wx.stopPullDownRefresh();
    });
  },

  // 上拉加载更多
  onReachBottom() {
    if (this.data.hasMore && !this.data.loadingMore) {
      this.setData({ page: this.data.page + 1 });
      this.loadOrders();
    }
  }
});
