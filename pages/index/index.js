// pages/index/index.js - 首页（附近站点）
const api = require('../../services/api');
const util = require('../../utils/util');
const config = require('../../config/index');

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
    this.getLocation();
  },

  onShow() {
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

  // 加载附近站点
  async loadStations() {
    const { latitude, longitude, filterGunType, filterSortBy } = this.data;
    this.setData({ loading: true });

    try {
      const res = await api.filterStations({
        lat: latitude,
        lng: longitude,
        gunType: filterGunType || undefined,
        sortBy: filterSortBy
      });
      const stations = (res.data?.list || res.data || []).map(s => ({
        ...s,
        distance: s.distance || util.calcDistance(latitude, longitude, s.lat, s.lng)
      }));

      const markers = stations.map((s, i) => ({
        id: i,
        latitude: s.lat,
        longitude: s.lng,
        title: s.name,
        iconPath: '/assets/icons/marker.png',
        width: 32,
        height: 32,
        callout: {
          content: s.name,
          color: '#333',
          fontSize: 12,
          borderRadius: 8,
          padding: 8,
          display: 'BYCLICK'
        }
      }));

      this.setData({ stations, markers, loading: false });
    } catch (err) {
      this.setData({ loading: false });
      console.error('加载站点失败:', err);
    }
  },

  // 搜索输入
  onSearchInput(e) {
    this.setData({ keyword: e.detail.value });
  },

  // 搜索
  onSearch() {
    const { keyword } = this.data;
    if (!keyword.trim()) {
      this.loadStations();
      return;
    }
    this.setData({ loading: true });
    api.searchStations(keyword.trim())
      .then(res => {
        const stations = res.data || [];
        const markers = stations.map((s, i) => ({
          id: i,
          latitude: s.lat,
          longitude: s.lng,
          title: s.name,
          iconPath: '/assets/icons/marker.png',
          width: 32,
          height: 32
        }));
        this.setData({ stations, markers, loading: false });
      })
      .catch(() => {
        this.setData({ loading: false });
      });
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
    this.setData({ showFilter: false });
    this.loadStations();
  },

  // 重置筛选
  onResetFilter() {
    this.setData({
      filterGunType: '',
      filterSortBy: 'distance'
    });
  },

  // 收藏站点
  async onStationFavorite(e) {
    const { station } = e.detail;
    try {
      await api.addFavorite(station.id);
      wx.showToast({ title: '已收藏', icon: 'success' });
      // 更新本地状态
      const stations = this.data.stations.map(s =>
        s.id === station.id ? { ...s, isFavorited: true } : s
      );
      this.setData({ stations });
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
    } catch (err) {
      console.error('取消收藏失败:', err);
    }
  },

  // 定位
  onLocate() {
    this.getLocation();
  },

  // 地图标记点击
  onMarkerTap(e) {
    const station = this.data.stations[e.markerId];
    if (station) {
      wx.navigateTo({
        url: `/pages/station-detail/station-detail?id=${station.id}`
      });
    }
  },

  // 地图更新
  onMapUpdated(e) {
    // 可在此处理地图拖动后的中心点变化
  },

  // 站点卡片点击
  onStationTap(e) {
    const { station } = e.detail;
    wx.navigateTo({
      url: `/pages/station-detail/station-detail?id=${station.id}`
    });
  },

  // 刷新
  onRefresh() {
    this.loadStations();
  },

  // 下拉刷新
  onPullDownRefresh() {
    this.loadStations().then(() => {
      wx.stopPullDownRefresh();
    });
  }
});
