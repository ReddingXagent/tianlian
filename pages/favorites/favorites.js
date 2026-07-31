// pages/favorites/favorites.js - 收藏站点
// 性能优化：API缓存
const api = require('../../services/api');
const util = require('../../utils/util');
const config = require('../../config/index');
const { cachedRequest } = require('../../utils/cache');
const { guardTap } = require('../../utils/perf');

Page({
  data: {
    favorites: [],
    loading: false
  },

  onLoad() {
    this.loadFavorites();
  },

  onShow() {
    this.loadFavorites();
  },

  // 加载收藏（带缓存）
  async loadFavorites(force = false) {
    if (force) this.setData({ loading: true });

    try {
      const res = await cachedRequest(
        () => api.getFavorites(),
        [],
        { cacheKey: 'favorites', ttl: config.CACHE_TTL.FAVORITES, force }
      );

      const favorites = (res.data?.list || res.data || []).map(item => ({
        ...item,
        distanceText: item.distance ? util.formatDistance(item.distance) : '未知',
        statusText: item.status === 'online' ? '营业中' : '休息中',
        availableGuns: `${item.availableGuns || 0}/${item.totalGuns || 0} 空闲`
      }));
      this.setData({ favorites, loading: false });
    } catch (err) {
      this.setData({ loading: false });
      console.error('加载收藏失败:', err);
    }
  },

  // 站点点击 (F70: station-detail页未创建,临时toast提示)
  onStationTap(_e) {
    wx.showToast({ title: '站点详情开发中', icon: 'none' });
  },

  // 取消收藏（防连点）
  onRemoveFavorite: guardTap(function(e) {
    const { id, name } = e.currentTarget.dataset;
    wx.showModal({
      title: '取消收藏',
      content: `确定取消收藏"${name}"吗？`,
      success: async (modalRes) => {
        if (modalRes.confirm) {
          try {
            await api.removeFavorite(id);
            wx.showToast({ title: '已取消收藏', icon: 'success' });
            const favorites = this.data.favorites.filter(f => f.id !== id);
            this.setData({ favorites });
            // 清除收藏缓存
            const { cache } = require('../../utils/cache');
            cache.delete('favorites');
          } catch (err) {
            console.error('取消收藏失败:', err);
          }
        }
      }
    });
  }, 2000),

  // 导航
  onNavigate(e) {
    const { lat, lng, name } = e.currentTarget.dataset;
    wx.openLocation({
      latitude: lat,
      longitude: lng,
      name: name,
      scale: 16
    });
  },

  // 下拉刷新
  onPullDownRefresh() {
    this.loadFavorites(true).then(() => wx.stopPullDownRefresh()).catch(() => wx.stopPullDownRefresh());
  }
});
