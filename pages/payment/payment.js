// pages/payment/payment.js - 支付页
const api = require('../../services/api');
const util = require('../../utils/util');

Page({
  data: {
    orderId: '',
    amount: '0.00',
    stationName: '',
    energy: '0.00',
    durationText: '',
    payMethod: 'wechat',
    balance: '0.00',
    paying: false
  },

  onLoad(options) {
    const { orderId } = options;
    this.setData({ orderId });
    this.loadOrderInfo();
    this.loadWallet();
  },

  // 加载订单信息
  async loadOrderInfo() {
    try {
      const res = await api.getOrderDetail(this.data.orderId);
      const data = res.data || {};

      this.setData({
        amount: util.formatMoney(data.amount),
        stationName: data.stationName || '充电站',
        energy: (data.energy || 0).toFixed(2),
        durationText: util.formatDuration(data.duration)
      });
    } catch (err) {
      console.error('加载订单信息失败:', err);
      wx.showToast({ title: '加载失败', icon: 'none' });
    }
  },

  // 加载钱包余额
  async loadWallet() {
    try {
      const res = await api.getWallet();
      this.setData({
        balance: (res.data?.balance || 0).toFixed(2)
      });
    } catch (err) {
      // 钱包信息非必需
    }
  },

  // 选择支付方式
  onSelectMethod(e) {
    const { method } = e.currentTarget.dataset;
    this.setData({ payMethod: method });
  },

  // 确认支付
  async onPay() {
    if (this.data.paying) return;

    const { orderId, payMethod, amount } = this.data;

    // 钱包支付检查余额
    if (payMethod === 'wallet') {
      if (parseFloat(this.data.balance) < parseFloat(amount)) {
        wx.showToast({ title: '余额不足', icon: 'none' });
        return;
      }
    }

    this.setData({ paying: true });

    try {
      // 创建支付
      const res = await api.createPayment(orderId);

      if (payMethod === 'wechat') {
        // 微信支付
        const payParams = res.data?.payParams || res.data;

        wx.requestPayment({
          timeStamp: String(payParams.timeStamp),
          nonceStr: payParams.nonceStr,
          package: payParams.package,
          signType: payParams.signType || 'MD5',
          paySign: payParams.paySign,
          success: () => {
            this.onPaySuccess();
          },
          fail: (err) => {
            this.setData({ paying: false });
            if (err.errMsg.includes('cancel')) {
              wx.showToast({ title: '支付已取消', icon: 'none' });
            } else {
              wx.showToast({ title: '支付失败', icon: 'none' });
            }
          }
        });
      } else {
        // 钱包支付
        this.onPaySuccess();
      }
    } catch (err) {
      this.setData({ paying: false });
      console.error('支付失败:', err);
    }
  },

  // 支付成功
  onPaySuccess() {
    this.setData({ paying: false });

    wx.showToast({
      title: '支付成功',
      icon: 'success',
      duration: 1500
    });

    setTimeout(() => {
      // 跳转到订单详情
      wx.redirectTo({
        url: `/pages/order-detail/order-detail?orderId=${this.data.orderId}`
      });
    }, 1500);
  }
});
