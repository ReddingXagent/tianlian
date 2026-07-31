// pages/profile/profile.js - 我的
// 性能优化：API缓存 + 钱包数据缓存
const api = require('../../services/api');
const { cachedRequest } = require('../../utils/cache');
const config = require('../../config/index');
const app = getApp();

Page({
  data: {
    userInfo: {},
    wallet: {
      balance: '0.00',
      couponCount: 0
    }
  },

  onLoad() {
    this.loadUserInfo();
    this.loadWallet();
  },

  onShow() {
    this.loadUserInfo();
    this.loadWallet();
  },

  // 加载用户信息
  loadUserInfo() {
    const userInfo = app.globalData.userInfo;
    if (userInfo) {
      this.setData({ userInfo });
    }
  },

  // 加载钱包（带缓存）
  async loadWallet(force = false) {
    try {
      const res = await cachedRequest(
        () => api.getWallet(),
        [],
        { cacheKey: 'wallet_info', ttl: config.CACHE_TTL.ORDERS, force }
      );
      this.setData({
        wallet: {
          balance: (res.data?.balance || 0).toFixed(2),
          couponCount: res.data?.couponCount || 0
        }
      });
    } catch (err) {
      // 未登录或加载失败
    }
  },

  // 登录（静默登录）
  // 注: wx.getUserProfile已于基础库2.27.1废弃，调用仅返回匿名"微信用户"+灰色默认头像，
  // 继续上行会污染服务端用户资料，故移除(F41)。
  // 头像/昵称采集需改用 <button open-type="chooseAvatar"> + <input type="nickname"> 组件方案(待UI排期)。
  onLogin() {
    if (app.globalData.token) return;

    app.login()
      .then(() => {
        this.loadUserInfo();
      })
      .catch(() => {
        wx.showToast({ title: '登录失败', icon: 'none' });
      });
  },

  // 钱包
  onWalletTap() {
    wx.navigateTo({ url: '/pages/wallet/wallet' });
  },

  // 充值
  onRecharge() {
    wx.showToast({ title: '充值功能开发中', icon: 'none' });
  },

  // 优惠券
  onCoupons() {
    wx.navigateTo({ url: '/pages/coupons/coupons' });
  },

  // 积分中心
  onPoints() {
    wx.navigateTo({ url: '/pages/points/points' });
  },

  // 我的车辆
  onMyVehicles() {
    wx.showToast({ title: '车辆管理开发中', icon: 'none' });
  },

  // 充电记录
  onMyOrders() {
    wx.switchTab({ url: '/pages/orders/orders' });
  },

  // 交易明细
  onTransactions() {
    wx.navigateTo({ url: '/pages/transactions/transactions' });
  },

  // 收藏站点
  onFavorites() {
    wx.navigateTo({ url: '/pages/favorites/favorites' });
  },

  // 消息通知
  onNotifications() {
    wx.navigateTo({ url: '/pages/notifications/notifications' });
  },

  // 帮助中心
  onHelp() {
    wx.showToast({ title: '帮助中心开发中', icon: 'none' });
  },

  // 意见反馈
  onFeedback() {
    wx.showToast({ title: '意见反馈开发中', icon: 'none' });
  },

  // 设置
  onSettings() {
    wx.showToast({ title: '设置功能开发中', icon: 'none' });
  },

  // 关于
  onAbout() {
    wx.showModal({
      title: '关于天链充电',
      content: '天链充电 v1.0.0\n\n新能源智能充电服务平台\n为您提供便捷的充电服务',
      showCancel: false,
      confirmText: '知道了'
    });
  },

  // 下拉刷新
  onPullDownRefresh() {
    this.loadWallet(true).then(() => {
      wx.stopPullDownRefresh();
    }).catch(() => wx.stopPullDownRefresh());
  }
});
