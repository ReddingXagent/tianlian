/**
 * Tests for chargerApi, notificationApi, and edge paths in api.ts
 * Covers the remaining uncovered api.ts functions (F131)
 */
import MockAdapter from 'axios-mock-adapter';
import * as SecureStore from 'expo-secure-store';
import api, {
  chargerApi,
  notificationApi,
  authApi,
  tokenStorage,
} from '../api';

jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn(),
  setItemAsync: jest.fn(),
  deleteItemAsync: jest.fn(),
}));

const mockAxios = new MockAdapter(api);

beforeEach(() => {
  jest.clearAllMocks();
  mockAxios.reset();
  (SecureStore.getItemAsync as jest.Mock).mockResolvedValue('test-token');
});

describe('chargerApi contract', () => {
  it('getMonitorList hits /stations/{id}/chargers/monitor', async () => {
    mockAxios.onGet('/stations/15/chargers/monitor').reply(200, {
      code: 200, message: 'success',
      data: [{ id: 1, name: 'CP-01', status: 'charging' }],
    });
    const resp = await chargerApi.getMonitorList(15);
    expect(resp.data).toHaveLength(1);
  });

  it('getMonitorSummary hits /stations/{id}/chargers/summary', async () => {
    mockAxios.onGet('/stations/15/chargers/summary').reply(200, {
      code: 200, message: 'success',
      data: { totalChargers: 10, chargingCount: 5, idleCount: 3, faultCount: 2 },
    });
    const resp = await chargerApi.getMonitorSummary(15);
    expect(resp.data.totalChargers).toBe(10);
  });

  it('getFaultRecords sends params', async () => {
    let params: Record<string, unknown> = {};
    mockAxios.onGet('/chargers/faults').reply((config) => {
      params = config.params ?? {};
      return [200, { code: 200, message: 'success', data: { items: [], total: 0, page: 1, page_size: 20 } }];
    });
    await chargerApi.getFaultRecords({ stationId: 15, page: 1, pageSize: 20 });
    expect(params.stationId).toBe(15);
    expect(params.page).toBe(1);
    expect(params.pageSize).toBe(20);
  });

  it('clearFault posts to /chargers/faults/{id}/clear', async () => {
    let url = '';
    mockAxios.onPost('/chargers/faults/42/clear').reply((config) => {
      url = config.url ?? '';
      return [200, { code: 200, message: 'success', data: { success: true, message: 'cleared' } }];
    });
    const resp = await chargerApi.clearFault(42);
    expect(url).toBe('/chargers/faults/42/clear');
    expect(resp.data.success).toBe(true);
  });

  it('getTrend hits /devices/{id}/charger-trend with optional params', async () => {
    let params: Record<string, unknown> = {};
    mockAxios.onGet('/devices/7/charger-trend').reply((config) => {
      params = config.params ?? {};
      return [200, { code: 200, message: 'success', data: { deviceId: 7, points: [] } }];
    });
    await chargerApi.getTrend(7, { points: 50 });
    expect(params.points).toBe(50);
  });

  it('getTrend works without optional params', async () => {
    mockAxios.onGet('/devices/7/charger-trend').reply(200, {
      code: 200, message: 'success', data: { deviceId: 7, points: [] },
    });
    const resp = await chargerApi.getTrend(7);
    expect(resp.data.deviceId).toBe(7);
  });
});

describe('notificationApi contract', () => {
  it('getList sends pagination params', async () => {
    let params: Record<string, unknown> = {};
    mockAxios.onGet('/notifications').reply((config) => {
      params = config.params ?? {};
      return [200, { code: 200, message: 'success', data: { items: [], total: 0, page: 1, page_size: 20 } }];
    });
    await notificationApi.getList({ page: 2, pageSize: 10 });
    expect(params.page).toBe(2);
    expect(params.pageSize).toBe(10);
  });

  it('getList works without params', async () => {
    mockAxios.onGet('/notifications').reply(200, {
      code: 200, message: 'success', data: { items: [], total: 0, page: 1, page_size: 20 },
    });
    const resp = await notificationApi.getList();
    expect(resp.data.total).toBe(0);
  });

  it('getUnreadCount hits /notifications/unread-count', async () => {
    mockAxios.onGet('/notifications/unread-count').reply(200, {
      code: 200, message: 'success', data: { count: 7 },
    });
    const resp = await notificationApi.getUnreadCount();
    expect(resp.data.count).toBe(7);
  });

  it('markAsRead posts to /notifications/{id}/read', async () => {
    mockAxios.onPost('/notifications/99/read').reply(200, {
      code: 200, message: 'success', data: { id: 99, isRead: true },
    });
    const resp = await notificationApi.markAsRead(99);
    expect(resp.data.id).toBe(99);
  });

  it('markAllAsRead posts to /notifications/read-all', async () => {
    mockAxios.onPost('/notifications/read-all').reply(200, {
      code: 200, message: 'success', data: null,
    });
    const resp = await notificationApi.markAllAsRead();
    expect(resp.code).toBe(200);
  });
});

describe('authApi additional methods', () => {
  it('logout posts to /auth/logout', async () => {
    mockAxios.onPost('/auth/logout').reply(200, {
      code: 200, message: 'success', data: null,
    });
    const resp = await authApi.logout();
    expect(resp.code).toBe(200);
  });

  it('getProfile hits /auth/profile', async () => {
    mockAxios.onGet('/auth/profile').reply(200, {
      code: 200, message: 'success', data: { id: 1, username: 'tl' },
    });
    const resp = await authApi.getProfile();
    expect(resp.data.username).toBe('tl');
  });
});

describe('tokenStorage edge cases', () => {
  it('getToken returns null on SecureStore failure', async () => {
    (SecureStore.getItemAsync as jest.Mock).mockRejectedValue(new Error('fail'));
    const token = await tokenStorage.getToken();
    expect(token).toBeNull();
  });

  it('request interceptor catches SecureStore error and still sends request', async () => {
    (SecureStore.getItemAsync as jest.Mock).mockRejectedValue(new Error('fail'));
    mockAxios.onGet('/notifications').reply(200, {
      code: 200, message: 'success', data: { items: [], total: 0, page: 1, page_size: 20 },
    });
    const resp = await notificationApi.getList();
    expect(resp.code).toBe(200);
  });
});
