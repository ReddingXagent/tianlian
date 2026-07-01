// pages/coupons/coupons.js - 优惠券中心
// 性能优化：API缓存 + tab切换缓存
const api = require('../../services/api');
const util = require('../../utils/util');
const config = require('../../config/index');
const { cachedRequest } = require('../../utils/cache');
const { guardTap } = require('../../utils/perf');

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
    // 使用缓存：缓存有效则不显示loading
    this.loadCoupons();
  },

  // 加载优惠券（带缓存）
  async loadCoupons(force = false) {
    const { currentTab } = this.data;
    const cacheKey = `coupons_${currentTab}`;

    // 首次/强制才显示loading
    if (force) this.setData({ loading: true });

    try {
      const res = await cachedRequest(
        (status) => api.getCoupons(status),
        [currentTab],
        { cacheKey, ttl: config.CACHE_TTL.COUPONS, force }
      );

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

  // 切换tab（防连点）
  onTabChange: guardTap(function(e) {
    const { value } = e.currentTarget.dataset;
    if (value === this.data.currentTab) return;
    this.setData({ currentTab: value });
    this.loadCoupons();
  }, 500),

  // 显示/隐藏兑换输入
  onToggleClaim() {
    this.setData({ showClaimInput: !this.data.showClaimInput, couponCode: '' });
  },

  // 兑换码输入
  onCodeInput(e) {
    this.setData({ couponCode: e.detail.value });
  },

  // 领取优惠券（防连点）
  onClaim: guardTap(async function() {
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
      // 领取后强制刷新
      this.loadCoupons(true);
    } catch (err) {
      this.setData({ claiming: false });
    }
  }, 2000),

  // 立即使用（跳转到首页充电）
  onUseCoupon(e) {
    const { id } = e.currentTarget.dataset;
    const app = getApp();
    app.globalData.selectedCoupon = this.data.coupons.find(c => c.id === id);
    wx.switchTab({ url: '/pages/index/index' });
  },

  // 下拉刷新（防连点）
  onPullDownRefresh: guardTap(function() {
    this.loadCoupons(true).then(() => wx.stopPullDownRefresh()).catch(() => wx.stopPullDownRefresh());
  }, 1000)
});
