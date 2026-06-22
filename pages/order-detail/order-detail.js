// pages/order-detail/order-detail.js - 订单详情
const api = require('../../services/api');
const util = require('../../utils/util');

const STATUS_CONFIG = {
  charging: {
    text: '充电中',
    icon: '⚡',
    desc: '正在充电，请耐心等待',
    class: 'charging'
  },
  finished: {
    text: '已完成',
    icon: '✅',
    desc: '充电已完成',
    class: 'finished'
  },
  cancelled: {
    text: '已取消',
    icon: '❌',
    desc: '订单已取消',
    class: ''
  },
  pending: {
    text: '待支付',
    icon: '💰',
    desc: '请尽快完成支付',
    class: 'pending'
  }
};

Page({
  data: {
    orderId: '',
    order: null,
    loading: false
  },

  onLoad(options) {
    const { orderId } = options;
    this.setData({ orderId });
    this.loadOrderDetail();
  },

  // 加载订单详情
  async loadOrderDetail() {
    this.setData({ loading: true });

    try {
      const res = await api.getOrderDetail(this.data.orderId);
      const data = res.data || {};

      const statusCfg = STATUS_CONFIG[data.status] || STATUS_CONFIG.finished;

      const order = {
        ...data,
        statusText: statusCfg.text,
        statusIcon: statusCfg.icon,
        statusDesc: statusCfg.desc,
        statusClass: statusCfg.class,
        durationText: util.formatDuration(data.duration),
        amount: util.formatMoney(data.amount),
        avgPower: data.duration > 0
          ? (data.energy / (data.duration / 60)).toFixed(2)
          : '0.00',
        startTime: util.formatTime(data.startTime),
        endTime: data.endTime ? util.formatTime(data.endTime) : '',
        showPay: data.status === 'pending'
      };

      this.setData({ order, loading: false });
    } catch (err) {
      this.setData({ loading: false });
      console.error('加载订单详情失败:', err);
    }
  },

  // 去支付
  onPay() {
    wx.navigateTo({
      url: `/pages/payment/payment?orderId=${this.data.orderId}`
    });
  },

  // 下拉刷新
  onPullDownRefresh() {
    this.loadOrderDetail().then(() => {
      wx.stopPullDownRefresh();
    });
  }
});
