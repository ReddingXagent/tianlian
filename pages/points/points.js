// pages/points/points.js - 积分中心
const api = require('../../services/api');
const util = require('../../utils/util');
const config = require('../../config/index');

Page({
  data: {
    points: 0,
    signedIn: false,
    signInDays: 0,
    history: [],
    loading: false,
    historyLoading: false,
    // 兑换商品
    rewards: [
      { id: 'r1', name: '5元充电券', points: 100, icon: '🎫', desc: '满10元可用' },
      { id: 'r2', name: '10元充电券', points: 200, icon: '🎟️', desc: '满20元可用' },
      { id: 'r3', name: '20元充电券', points: 350, icon: '💎', desc: '满30元可用' },
      { id: 'r4', name: '充电免单', points: 1000, icon: '👑', desc: '单次最高免50元' }
    ]
  },

  onLoad() {
    this.loadPoints();
    this.loadHistory();
  },

  onShow() {
    this.loadPoints();
  },

  // 加载积分
  async loadPoints() {
    this.setData({ loading: true });
    try {
      const res = await api.getPoints();
      const data = res.data || {};
      // 检查今日是否已签到
      const today = util.formatTime(new Date(), 'YYYY-MM-DD');
      const signedIn = data.lastSignInDate === today;
      this.setData({
        points: data.points || 0,
        signedIn,
        signInDays: data.signInDays || 0,
        loading: false
      });
    } catch (err) {
      this.setData({ loading: false });
      console.error('加载积分失败:', err);
    }
  },

  // 加载积分记录
  async loadHistory() {
    this.setData({ historyLoading: true });
    try {
      const res = await api.getPointsHistory();
      const history = (res.data?.list || res.data || []).map(item => ({
        ...item,
        timeText: util.formatTime(item.createTime, 'YYYY-MM-DD HH:mm'),
        amountText: item.amount > 0 ? `+${item.amount}` : `${item.amount}`,
        isPositive: item.amount > 0
      }));
      this.setData({ history, historyLoading: false });
    } catch (err) {
      this.setData({ historyLoading: false });
    }
  },

  // 每日签到
  async onSignIn() {
    if (this.data.signedIn) {
      wx.showToast({ title: '今日已签到', icon: 'none' });
      return;
    }
    try {
      const res = await api.dailySignIn();
      const earnedPoints = res.data?.points || config.POINTS_RULES.SIGN_IN_DAILY;
      wx.showToast({ title: `签到成功 +${earnedPoints}积分`, icon: 'success' });
      this.setData({
        signedIn: true,
        points: this.data.points + earnedPoints,
        signInDays: this.data.signInDays + 1
      });
      this.loadHistory();
    } catch (err) {
      console.error('签到失败:', err);
    }
  },

  // 兑换
  onRedeem(e) {
    const { id, name, points } = e.currentTarget.dataset;
    if (this.data.points < points) {
      wx.showToast({ title: '积分不足', icon: 'none' });
      return;
    }

    wx.showModal({
      title: '确认兑换',
      content: `使用${points}积分兑换"${name}"？`,
      success: async (modalRes) => {
        if (modalRes.confirm) {
          try {
            await api.redeemPoints(id);
            wx.showToast({ title: '兑换成功', icon: 'success' });
            this.setData({ points: this.data.points - points });
            this.loadHistory();
          } catch (err) {
            console.error('兑换失败:', err);
          }
        }
      }
    });
  },

  // 积分规则说明
  onShowRules() {
    const rules = [
      `每日签到 +${config.POINTS_RULES.SIGN_IN_DAILY}积分`,
      `每消费1元 +${config.POINTS_RULES.CHARGE_PER_YUAN}积分`,
      `邀请好友注册 +${config.POINTS_RULES.INVITE_FRIEND}积分`,
      `评价订单 +${config.POINTS_RULES.REVIEW_ORDER}积分`
    ].join('\n');

    wx.showModal({
      title: '积分规则',
      content: rules,
      showCancel: false,
      confirmText: '知道了'
    });
  },

  // 下拉刷新
  onPullDownRefresh() {
    Promise.all([this.loadPoints(), this.loadHistory()]).then(() => {
      wx.stopPullDownRefresh();
    });
  }
});
