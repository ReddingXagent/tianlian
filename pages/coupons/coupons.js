// pages/coupons/coupons.js - 优惠券中心
const api = require('../../services/api');
const util = require('../../utils/util');
const config = require('../../config/index');

const STATUS_MAP = {
  [config.COUPON_STATUS.UNUSED]: { text: '可使用', class: 'status-usable', color: '#07C160' },
  [config.COUPON_STATUS.USED]: { text: '已使用', class: 'status-used', color: '#999' },
  [config.COUPON_STATUS.EXPIRED]: { text: '已过期', class: 'status-expired', color: '#ccc' }
};

const TYPE_MAP = {
  [config.COUPON_TYPE.AMOUNT]: '满减券',
  [config.COUPON_TYPE.DISCOUNT]: '折扣券',
  [config.COUPON_TYPE.FREIGHT]: '免运券'
};

Page({
  data: {
    tabs: [
      { label: '可使用', value: config.COUPON_STATUS.UNUSED },
      { label: '已使用', value: config.COUPON_STATUS.USED },
      { label: '已过期', value: config.COUPON_STATUS.EXPIRED }
    ],
    currentTab: config.COUPON_STATUS.UNUSED,
    coupons: [],
    loading: false,
    // 兑换码
    couponCode: '',
    showClaimInput: false,
    claiming: false
  },

  onLoad() {
    this.loadCoupons();
  },

  onShow() {
    this.loadCoupons();
  },

  // 切换tab
  onTabChange(e) {
    const { value } = e.currentTarget.dataset;
    if (value === this.data.currentTab) return;
    this.setData({ currentTab: value });
    this.loadCoupons();
  },

  // 加载优惠券
  async loadCoupons() {
    this.setData({ loading: true });
    try {
      const res = await api.getCoupons(this.data.currentTab);
      const coupons = (res.data?.list || res.data || []).map(coupon => ({
        ...coupon,
        typeText: TYPE_MAP[coupon.type] || coupon.type,
        statusCfg: STATUS_MAP[coupon.status] || STATUS_MAP[config.COUPON_STATUS.USED],
        amountText: coupon.type === config.COUPON_TYPE.DISCOUNT
          ? `${coupon.value}折`
          : `¥${coupon.value}`,
        minAmountText: coupon.minAmount ? `满¥${coupon.minAmount}可用` : '无门槛',
        expireText: coupon.expireTime
          ? `${util.formatTime(coupon.expireTime, 'YYYY.MM.DD')} 前有效`
          : '长期有效'
      }));
      this.setData({ coupons, loading: false });
    } catch (err) {
      this.setData({ loading: false });
      console.error('加载优惠券失败:', err);
    }
  },

  // 显示/隐藏兑换输入
  onToggleClaim() {
    this.setData({ showClaimInput: !this.data.showClaimInput, couponCode: '' });
  },

  // 兑换码输入
  onCodeInput(e) {
    this.setData({ couponCode: e.detail.value });
  },

  // 领取优惠券
  async onClaim() {
    const code = this.data.couponCode.trim();
    if (!code) {
      wx.showToast({ title: '请输入兑换码', icon: 'none' });
      return;
    }
    this.setData({ claiming: true });
    try {
      await api.claimCoupon(code);
      wx.showToast({ title: '领取成功', icon: 'success' });
      this.setData({ showClaimInput: false, couponCode: '', claiming: false });
      this.loadCoupons();
    } catch (err) {
      this.setData({ claiming: false });
    }
  },

  // 立即使用（跳转到首页充电）
  onUseCoupon(e) {
    const { id } = e.currentTarget.dataset;
    // 将优惠券信息存到全局，支付时使用
    const app = getApp();
    app.globalData.selectedCoupon = this.data.coupons.find(c => c.id === id);
    wx.switchTab({ url: '/pages/index/index' });
  },

  // 下拉刷新
  onPullDownRefresh() {
    this.loadCoupons().then(() => wx.stopPullDownRefresh());
  }
});
