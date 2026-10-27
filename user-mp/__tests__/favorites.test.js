// __tests__/favorites.test.js - 收藏页面测试
const mockShowToast = jest.fn();
const mockShowModal = jest.fn();
const mockSwitchTab = jest.fn();
const mockOpenLocation = jest.fn();
const mockStopPullDown = jest.fn();

global.wx = {
  showToast: mockShowToast,
  showModal: mockShowModal,
  switchTab: mockSwitchTab,
  openLocation: mockOpenLocation,
  stopPullDownRefresh: mockStopPullDown,
};

let pageConfig = null;
global.Page = (config) => { pageConfig = config; };

const mockGetFavorites = jest.fn();
const mockRemoveFavorite = jest.fn();
jest.mock('../services/api', () => ({
  getFavorites: mockGetFavorites,
  removeFavorite: mockRemoveFavorite,
}));
jest.mock('../utils/util', () => ({
  formatDistance: jest.fn((d) => d < 1000 ? `${d}m` : `${(d / 1000).toFixed(1)}km`),
}));
jest.mock('../config/index', () => ({ CACHE_TTL: { FAVORITES: 60000 } }));
jest.mock('../utils/cache', () => ({
  cachedRequest: jest.fn(async (fn, args) => {
    const res = await fn(...(args || []));
    return res;
  }),
  cache: { delete: jest.fn() },
}));
jest.mock('../utils/perf', () => ({ guardTap: (fn) => fn }));

require('../pages/favorites/favorites');

describe('pages/favorites/favorites', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    pageConfig.setData = jest.fn();
    mockGetFavorites.mockResolvedValue({ data: { list: [] } });
  });

  describe('onLoad / onShow', () => {
    it('calls loadFavorites on onLoad', () => {
      const orig = pageConfig.loadFavorites;
      pageConfig.loadFavorites = jest.fn();
      pageConfig.onLoad();
      expect(pageConfig.loadFavorites).toHaveBeenCalled();
      pageConfig.loadFavorites = orig;
    });
  });

  describe('loadFavorites', () => {
    it('loads and maps favorites correctly', async () => {
      mockGetFavorites.mockResolvedValue({
        data: {
          list: [
            { id: 1, name: 'Station A', distance: 500, status: 'online', availableGuns: 2, totalGuns: 4 },
            { id: 2, name: 'Station B', distance: 2000, status: 'offline', availableGuns: 0, totalGuns: 4 },
          ]
        }
      });

      await pageConfig.loadFavorites(true);
      const setDataCall = pageConfig.setData.mock.calls.find(c => c[0].favorites);
      expect(setDataCall).toBeTruthy();
      const favs = setDataCall[0].favorites;
      expect(favs).toHaveLength(2);
      expect(favs[0].distanceText).toBe('500m');
      expect(favs[0].statusText).toBe('营业中');
      expect(favs[0].availableGuns).toBe('2/4 空闲');
      expect(favs[1].distanceText).toBe('2.0km');
      expect(favs[1].statusText).toBe('休息中');
    });

    it('handles empty favorites', async () => {
      mockGetFavorites.mockResolvedValue({ data: { list: [] } });
      await pageConfig.loadFavorites();
      const setDataCall = pageConfig.setData.mock.calls.find(c => c[0].favorites);
      expect(setDataCall[0].favorites).toHaveLength(0);
    });

    it('handles API error gracefully', async () => {
      mockGetFavorites.mockRejectedValue(new Error('network'));
      await pageConfig.loadFavorites(true);
      expect(pageConfig.setData).toHaveBeenCalledWith(expect.objectContaining({ loading: false }));
    });
  });

  describe('onStationTap', () => {
    it('shows toast', () => {
      pageConfig.onStationTap({});
      expect(mockShowToast).toHaveBeenCalledWith(expect.objectContaining({ title: '站点详情开发中' }));
    });
  });

  describe('onNavigate', () => {
    it('calls wx.openLocation with correct params', () => {
      pageConfig.onNavigate({ currentTarget: { dataset: { lat: 30.5, lng: 114.3, name: 'Test' } } });
      expect(mockOpenLocation).toHaveBeenCalledWith(expect.objectContaining({ latitude: 30.5, longitude: 114.3, name: 'Test' }));
    });
  });

  describe('onGoHome', () => {
    it('switches to index tab', () => {
      pageConfig.onGoHome();
      expect(mockSwitchTab).toHaveBeenCalledWith({ url: '/pages/index/index' });
    });
  });

  describe('onRemoveFavorite', () => {
    it('shows confirmation modal', () => {
      pageConfig.data = { favorites: [] };
      pageConfig.onRemoveFavorite({ currentTarget: { dataset: { id: 1, name: 'Test Station' } } });
      expect(mockShowModal).toHaveBeenCalledWith(expect.objectContaining({ title: '取消收藏' }));
    });
  });
});
