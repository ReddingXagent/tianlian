// pages/index/index.js - 首页（附近站点）
// 性能优化：API缓存 + 搜索防抖 + 筛选状态本地缓存
const api = require('../../services/api');
const util = require('../../utils/util');
const config = require('../../config/index');
const { cachedRequest } = require('../../utils/cache');
const { guardTap, buildMarkers } = require('../../utils/perf');

// 搜索防抖
const debouncedSearch = util.debounce(function(fn) { fn(); }, 400);

Page({
  data: {
    latitude: 30.5728,    // 默认成都
    longitude: 104.0668,
    keyword: '',
    stations: [],
    markers: [],
    loading: false,
    // 筛选条件
    showFilter: false,
    filterGunType: '',     // '' | 'ac' | 'dc'
    filterSortBy: 'distance', // distance | price | rating
    // 筛选选项
    gunTypes: [
      { label: '全部', value: '' },
      { label: '快充', value: 'dc' },
      { label: '慢充', value: 'ac' }
    ],
    sortOptions: [
      { label: '距离最近', value: 'distance' },
      { label: '价格最低', value: 'price' },
      { label: '评分最高', value: 'rating' }
    ]
  },

  onLoad() {
    // 恢复上次筛选状态
    const lastFilter = wx.getStorageSync('station_filter');
    if (lastFilter) {
      this.setData({
        filterGunType: lastFilter.gunType || '',
        filterSortBy: lastFilter.sortBy || 'distance'
      });
    }
    this.getLocation();
  },

  onShow() {
    // 使用缓存：只有缓存过期或强制刷新才请求
    if (this.data.latitude && this.data.longitude) {
      this.loadStations();
    }
  },

  // 获取用户位置
  getLocation() {
    wx.getLocation({
      type: 'gcj02',
      success: (res) => {
        this.setData({
          latitude: res.latitude,
          longitude: res.longitude
        });
        this.loadStations();
      },
      fail: () => {
        this.loadStations();
      }
    });
  },

  // 加载附近站点（带缓存）
  async loadStations(force = false) {
    const { latitude, longitude, filterGunType, filterSortBy } = this.data;
    this.setData({ loading: true });

    const cacheKey = `stations_${latitude}_${longitude}_${filterGunType}_${filterSortBy}`;

    try {
      const res = await cachedRequest(
        (params) => api.filterStations(params),
        [{
          lat: latitude,
          lng: longitude,
          gunType: filterGunType || undefined,
          sortBy: filterSortBy
        }],
        { cacheKey, ttl: config.CACHE_TTL.STATIONS, force }
      );

      const stations = (res.data?.list || res.data || []).map(s => ({
        ...s,
        distance: s.distance || util.calcDistance(latitude, longitude, s.lat, s.lng),
        distanceText: util.formatDistance(
          s.distance || util.calcDistance(latitude, longitude, s.lat, s.lng)
        )
      }));

      // 增量更新 markers（复用未变化的标记，减少 setData 数据量）
      const markers = buildMarkers(stations, this.data._prevMarkers || []);

      this.setData({ stations, markers, loading: false });
      this.data._prevMarkers = markers;
    } catch (err) {
      this.setData({ loading: false });
      console.error('加载站点失败:', err);
    }
  },

  // 搜索输入（防抖）
  onSearchInput(e) {
    this.setData({ keyword: e.detail.value });
    // 防抖搜索
    if (e.detail.value.trim()) {
      debouncedSearch(() => this.onSearch());
    }
  },

  // 搜索
  async onSearch() {
    const { keyword } = this.data;
    if (!keyword.trim()) {
      this.loadStations(true);
      return;
    }

    const cacheKey = `search_${keyword.trim()}`;
    this.setData({ loading: true });

    try {
      const res = await cachedRequest(
        (kw) => api.searchStations(kw),
        [keyword.trim()],
        { cacheKey, ttl: config.CACHE_TTL.STATIONS }
      );

      const stations = res.data || [];
      const markers = buildMarkers(stations, this.data._prevMarkers || []);
      this.setData({ stations, markers, loading: false });
      this.data._prevMarkers = markers;
    } catch (err) {
      this.setData({ loading: false });
    }
  },

  // 显示/隐藏筛选面板
  onToggleFilter() {
    this.setData({ showFilter: !this.data.showFilter });
  },

  // 选择充电类型
  onSelectGunType(e) {
    const { value } = e.currentTarget.dataset;
    this.setData({ filterGunType: value });
  },

  // 选择排序方式
  onSelectSortBy(e) {
    const { value } = e.currentTarget.dataset;
    this.setData({ filterSortBy: value });
  },

  // 应用筛选
  onApplyFilter() {
    // 持久化筛选状态
    wx.setStorageSync('station_filter', {
      gunType: this.data.filterGunType,
      sortBy: this.data.filterSortBy
    });
    this.setData({ showFilter: false });
    this.loadStations(true); // 强制刷新
  },

  // 重置筛选
  onResetFilter() {
    this.setData({
      filterGunType: '',
      filterSortBy: 'distance'
    });
    wx.removeStorageSync('station_filter');
  },

  // 收藏站点
  async onStationFavorite(e) {
    const { station } = e.detail;
    try {
      await api.addFavorite(station.id);
      wx.showToast({ title: '已收藏', icon: 'success' });
      // 局部更新，不清缓存
      const stations = this.data.stations.map(s =>
        s.id === station.id ? { ...s, isFavorited: true } : s
      );
      this.setData({ stations });
      // 刷新收藏缓存
      const { cache } = require('../../utils/cache');
      cache.delete('favorites');
    } catch (err) {
      console.error('收藏失败:', err);
    }
  },

  // 取消收藏
  async onStationUnfavorite(e) {
    const { station } = e.detail;
    try {
      await api.removeFavorite(station.id);
      wx.showToast({ title: '已取消收藏', icon: 'success' });
      const stations = this.data.stations.map(s =>
        s.id === station.id ? { ...s, isFavorited: false } : s
      );
      this.setData({ stations });
      const { cache } = require('../../utils/cache');
      cache.delete('favorites');
    } catch (err) {
      console.error('取消收藏失败:', err);
    }
  },

  // 定位（防连点）
  onLocate: guardTap(function() {
    this.getLocation();
  }, 2000),

  // 地图标记点击 (F70: station-detail页未创建,临时toast提示)
  onMarkerTap(e) {
    const station = this.data.stations[e.markerId];
    if (station) {
      wx.showToast({ title: '站点详情开发中', icon: 'none' });
    }
  },

  // 站点卡片点击 (F70: station-detail页未创建)
  onStationTap(_e) {
    wx.showToast({ title: '站点详情开发中', icon: 'none' });
  },

  // 刷新（防连点）
  onRefresh: guardTap(function() {
    this.loadStations(true);
  }, 1000),

  // 下拉刷新
  onPullDownRefresh() {
    this.loadStations(true).then(() => {
      wx.stopPullDownRefresh();
    }).catch(() => {
      wx.stopPullDownRefresh();
    });
  }
});
