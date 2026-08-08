// F664: api.js branch coverage — L280 (favorites truthy) + L348 (unknown status fallback)
const mockWxRequest = jest.fn();
const mockGetStorageSync = jest.fn();
const mockSetStorageSync = jest.fn();
const mockRemoveStorageSync = jest.fn();

global.wx = {
  request: mockWxRequest,
  getStorageSync: mockGetStorageSync,
  setStorageSync: mockSetStorageSync,
  removeStorageSync: mockRemoveStorageSync,
  showLoading: jest.fn(),
  hideLoading: jest.fn(),
  showToast: jest.fn(),
};

const api = require('../api');

describe('api.ext3: uncovered branches', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  // L280: getFavorites with existing favorites data (truthy)
  test('getFavorites: 返回已存储的收藏列表', async () => {
    const existingFavs = [1, 5, 10];
    mockGetStorageSync.mockImplementation((k) => {
      if (k === 'favorites') return existingFavs;
      return null;
    });

    const result = await api.getFavorites();
    expect(result.code).toBe(200);
    expect(result.data).toEqual([1, 5, 10]);
    expect(mockGetStorageSync).toHaveBeenCalledWith('favorites');
  });

  // L348: getOrders with status that has no mapping → fallback to raw status
  test('getOrders: 未知status → ORDER_STATUS_TO_BACKEND miss, fallback to raw status', async () => {
    mockGetStorageSync.mockImplementation((k) => {
      if (k === 'token') return 'mock-token';
      return null;
    });
    mockWxRequest.mockImplementation((opts) => {
      opts.success({ statusCode: 200, data: { code: 200, message: 'ok', data: { list: [], total: 0, page: 1, page_size: 10 } } });
    });

    await api.getOrders({ status: 'unknown_status_xyz' });

    const callArgs = mockWxRequest.mock.calls[0][0];
    expect(callArgs.data.status).toBe('unknown_status_xyz');
  });
});
