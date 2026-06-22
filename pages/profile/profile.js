// pages/profile/profile.js - 我的
const api = require('../../services/api');
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

  // 加载钱包
  async loadWallet() {
    try {
      const res = await api.getWallet();
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

  // 登录
  onLogin() {
    if (app.globalData.token) return;

    wx.getUserProfile({
      desc: '用于完善用户资料',
      success: (profileRes) => {
        const userInfo = profileRes.userInfo;
        app.login()
          .then(() => {
            // 更新用户信息
            api.updateUserInfo({
              nickName: userInfo.nickName,
              avatarUrl: userInfo.avatarUrl
            }).then(() => {
              app.globalData.userInfo = {
                ...app.globalData.userInfo,
                ...userInfo
              };
              this.loadUserInfo();
            });
          })
          .catch(() => {
            wx.showToast({ title: '登录失败', icon: 'none' });
          });
      },
      fail: () => {
        // 用户拒绝授权，使用静默登录
        app.login()
          .then(() => {
            this.loadUserInfo();
          })
          .catch(() => {
            wx.showToast({ title: '登录失败', icon: 'none' });
          });
      }
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
    Promise.all([this.loadWallet()]).then(() => {
      wx.stopPullDownRefresh();
    });
  }
});
