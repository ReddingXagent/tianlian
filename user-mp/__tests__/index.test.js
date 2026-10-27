// __tests__/index.test.js - 首页（附近站点）测试
const mockGetLocation = jest.fn();
const mockGetStorageSync = jest.fn();
const mockSetStorageSync = jest.fn();
const mockRemoveStorageSync = jest.fn();
const mockShowToast = jest.fn();
const mockStopPullDown = jest.fn();

global.wx = {
  getLocation: mockGetLocation,
  getStorageSync: mockGetStorageSync,
  setStorageSync: mockSetStorageSync,
  removeStorageSync: mockRemoveStorageSync,
  showToast: mockShowToast,
  stopPullDownRefresh: mockStopPullDown,
};

let pageConfig = null;
let _origLoadStations = null;
global.Page = (config) => { pageConfig = config; };

const mockFilterStations = jest.fn();
const mockSearchStations = jest.fn();
const mockAddFavorite = jest.fn();
const mockRemoveFavorite = jest.fn();
jest.mock('../services/api', () => ({
  filterStations: mockFilterStations,
  searchStations: mockSearchStations,
  addFavorite: mockAddFavorite,
  removeFavorite: mockRemoveFavorite,
}));
jest.mock('../utils/util', () => ({
  debounce: jest.fn((fn) => {
    let timer;
    return function (...args) {
      clearTimeout(timer);
      timer = setTimeout(() => fn(...args), 0);
    };
  }),
  formatDistance: jest.fn((d) => d < 1000 ? `${d}m` : `${(d / 1000).toFixed(1)}km`),
  calcDistance: jest.fn(() => 500),
}));
jest.mock('../config/index', () => ({ CACHE_TTL: { STATIONS: 60000 } }));
jest.mock('../utils/cache', () => ({
  cachedRequest: jest.fn((fn, args) => Promise.resolve(fn(...(args || [])))),
  cache: { delete: jest.fn() },
}));
jest.mock('../utils/perf', () => ({
  guardTap: (fn) => fn,
  buildMarkers: jest.fn((stations) => stations.map((s, i) => ({ id: i, ...s }))),
}));

require('../pages/index/index');

describe('pages/index/index', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockGetStorageSync.mockReturnValue(null);
    mockGetLocation.mockImplementation((opts) => opts.success({ latitude: 30.5, longitude: 104.0 }));
    pageConfig.setData = jest.fn(function(patch) {
      Object.assign(this.data, patch);
    });
    pageConfig.data = {
      latitude: 30.5728, longitude: 104.0668, keyword: '',
      stations: [], markers: [], loading: false,
      showFilter: false, filterGunType: '', filterSortBy: 'distance',
      gunTypes: [], sortOptions: [],
    };
    // Restore loadStations if a previous test replaced it
    if (_origLoadStations) pageConfig.loadStations = _origLoadStations;
    else _origLoadStations = pageConfig.loadStations;
  });

  describe('onLoad', () => {
    it('restores filter from storage and gets location', () => {
      mockGetStorageSync.mockReturnValue({ gunType: 'dc', sortBy: 'price' });
      const orig = pageConfig.getLocation;
      pageConfig.getLocation = jest.fn();
      pageConfig.onLoad();
      expect(pageConfig.setData).toHaveBeenCalledWith(expect.objectContaining({
        filterGunType: 'dc', filterSortBy: 'price',
      }));
      expect(pageConfig.getLocation).toHaveBeenCalled();
      pageConfig.getLocation = orig;
    });

    it('defaults when no saved filter', () => {
      mockGetStorageSync.mockReturnValue(null);
      const orig = pageConfig.getLocation;
      pageConfig.getLocation = jest.fn();
      pageConfig.onLoad();
      expect(pageConfig.getLocation).toHaveBeenCalled();
      pageConfig.getLocation = orig;
    });
  });

  describe('getLocation', () => {
    it('updates location and loads stations on success', () => {
      const origLoad = pageConfig.loadStations;
      pageConfig.loadStations = jest.fn();
      pageConfig.getLocation();
      expect(mockGetLocation).toHaveBeenCalled();
      expect(pageConfig.setData).toHaveBeenCalledWith(expect.objectContaining({
        latitude: 30.5, longitude: 104.0,
      }));
      expect(pageConfig.loadStations).toHaveBeenCalled();
      pageConfig.loadStations = origLoad;
    });

    it('still loads stations on fail', () => {
      mockGetLocation.mockImplementation((opts) => opts.fail());
      const origLoad = pageConfig.loadStations;
      pageConfig.loadStations = jest.fn();
      pageConfig.getLocation();
      expect(pageConfig.loadStations).toHaveBeenCalled();
      pageConfig.loadStations = origLoad;
    });
  });

  describe('loadStations', () => {
    it('maps stations with distance text', async () => {
      mockFilterStations.mockResolvedValue({
        data: { list: [
          { id: 1, name: 'A', lat: 30.5, lng: 104.0, distance: 300 },
          { id: 2, name: 'B', lat: 30.6, lng: 104.1 },
        ]},
      });

      await pageConfig.loadStations(true);
      const call = pageConfig.setData.mock.calls.find(c => c[0].stations);
      expect(call).toBeTruthy();
      const ss = call[0].stations;
      expect(ss).toHaveLength(2);
      expect(ss[0].distanceText).toBe('300m');
      expect(ss[1].distanceText).toBe('500m'); // calcDistance mock returns 500
    });

    it('handles API error', async () => {
      mockFilterStations.mockRejectedValue(new Error('fail'));
      await pageConfig.loadStations(true);
      const call = pageConfig.setData.mock.calls.find(c => c[0].loading === false);
      expect(call).toBeTruthy();
    });
  });

  describe('onSearchInput', () => {
    it('updates keyword and triggers search', () => {
      const orig = pageConfig.onSearch;
      pageConfig.onSearch = jest.fn();
      pageConfig.onSearchInput({ detail: { value: 'test' } });
      expect(pageConfig.setData).toHaveBeenCalledWith({ keyword: 'test' });
      pageConfig.onSearch = orig;
    });
  });

  describe('onSearch', () => {
    it('reloads stations when keyword empty', async () => {
      pageConfig.data.keyword = '';
      const orig = pageConfig.loadStations;
      pageConfig.loadStations = jest.fn();
      await pageConfig.onSearch();
      expect(pageConfig.loadStations).toHaveBeenCalledWith(true);
      pageConfig.loadStations = orig;
    });

    it('searches with keyword', async () => {
      pageConfig.data.keyword = 'StationA';
      mockSearchStations.mockResolvedValue({ data: [{ id: 1, name: 'StationA' }] });
      await pageConfig.onSearch();
      const call = pageConfig.setData.mock.calls.find(c => c[0].stations);
      expect(call[0].stations).toHaveLength(1);
    });
  });

  describe('filter controls', () => {
    it('onToggleFilter toggles', () => {
      pageConfig.data.showFilter = false;
      pageConfig.onToggleFilter();
      expect(pageConfig.setData).toHaveBeenCalledWith({ showFilter: true });
    });

    it('onSelectGunType updates value', () => {
      pageConfig.onSelectGunType({ currentTarget: { dataset: { value: 'dc' } } });
      expect(pageConfig.setData).toHaveBeenCalledWith({ filterGunType: 'dc' });
    });

    it('onSelectSortBy updates value', () => {
      pageConfig.onSelectSortBy({ currentTarget: { dataset: { value: 'rating' } } });
      expect(pageConfig.setData).toHaveBeenCalledWith({ filterSortBy: 'rating' });
    });

    it('onApplyFilter saves and reloads', () => {
      pageConfig.data.filterGunType = 'dc';
      pageConfig.data.filterSortBy = 'price';
      const orig = pageConfig.loadStations;
      pageConfig.loadStations = jest.fn();
      pageConfig.onApplyFilter();
      expect(mockSetStorageSync).toHaveBeenCalledWith('station_filter', { gunType: 'dc', sortBy: 'price' });
      expect(pageConfig.setData).toHaveBeenCalledWith(expect.objectContaining({ showFilter: false }));
      expect(pageConfig.loadStations).toHaveBeenCalledWith(true);
      pageConfig.loadStations = orig;
    });

    it('onResetFilter resets and clears storage', () => {
      pageConfig.onResetFilter();
      expect(pageConfig.setData).toHaveBeenCalledWith(expect.objectContaining({
        filterGunType: '', filterSortBy: 'distance',
      }));
      expect(mockRemoveStorageSync).toHaveBeenCalledWith('station_filter');
    });
  });

  describe('favorites', () => {
    it('onStationFavorite adds favorite', async () => {
      mockAddFavorite.mockResolvedValue({});
      pageConfig.data.stations = [{ id: 1, isFavorited: false }];
      await pageConfig.onStationFavorite({ detail: { station: { id: 1 } } });
      expect(mockAddFavorite).toHaveBeenCalledWith(1);
      expect(mockShowToast).toHaveBeenCalledWith(expect.objectContaining({ title: '已收藏' }));
    });

    it('onStationUnfavorite removes favorite', async () => {
      mockRemoveFavorite.mockResolvedValue({});
      pageConfig.data.stations = [{ id: 2, isFavorited: true }];
      await pageConfig.onStationUnfavorite({ detail: { station: { id: 2 } } });
      expect(mockRemoveFavorite).toHaveBeenCalledWith(2);
      expect(mockShowToast).toHaveBeenCalledWith(expect.objectContaining({ title: '已取消收藏' }));
    });
  });

  describe('placeholder taps', () => {
    it('onMarkerTap shows toast for valid station', () => {
      pageConfig.data.stations = [{ id: 1, name: 'A' }];
      pageConfig.onMarkerTap({ markerId: 0 });
      expect(mockShowToast).toHaveBeenCalledWith(expect.objectContaining({ title: '站点详情开发中' }));
    });

    it('onMarkerTap does nothing for invalid index', () => {
      pageConfig.data.stations = [];
      pageConfig.onMarkerTap({ markerId: 99 });
      expect(mockShowToast).not.toHaveBeenCalled();
    });

    it('onStationTap shows toast', () => {
      pageConfig.onStationTap({});
      expect(mockShowToast).toHaveBeenCalledWith(expect.objectContaining({ title: '站点详情开发中' }));
    });
  });

  describe('onRefresh', () => {
    it('calls loadStations with force', () => {
      const orig = pageConfig.loadStations;
      pageConfig.loadStations = jest.fn();
      pageConfig.onRefresh();
      expect(pageConfig.loadStations).toHaveBeenCalledWith(true);
      pageConfig.loadStations = orig;
    });
  });
});
