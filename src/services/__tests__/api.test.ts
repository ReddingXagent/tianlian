import axios from 'axios';
import MockAdapter from 'axios-mock-adapter';
import * as SecureStore from 'expo-secure-store';
import api, { tokenStorage, authApi, stationApi, deviceApi, alarmApi, workOrderApi, dashboardApi, revenueApi, chargerApi, notificationApi } from '../api';

// Mock expo-secure-store
jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn(),
  setItemAsync: jest.fn(),
  deleteItemAsync: jest.fn(),
}));

const mockAxios = new MockAdapter(api);

const TEST_TOKEN = 'test-jwt-token-12345';
const BASE_URL = 'http://8.134.106.166/api/v1';

describe('api instance', () => {
  it('should create an axios instance with correct baseURL', () => {
    expect(api.defaults.baseURL).toBe(BASE_URL);
    expect(api.defaults.timeout).toBe(15000);
    expect(api.defaults.headers['Content-Type']).toBe('application/json');
  });
});

describe('request interceptor', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('should inject Bearer token when token exists', async () => {
    (SecureStore.getItemAsync as jest.Mock).mockResolvedValue(TEST_TOKEN);

    mockAxios.onGet('/auth/profile').reply((config) => {
      expect(config.headers?.Authorization).toBe(`Bearer ${TEST_TOKEN}`);
      return [200, { code: 0, message: 'ok', data: {} }];
    });

    await api.get('/auth/profile');
    expect(SecureStore.getItemAsync).toHaveBeenCalledWith('auth_token');
  });

  it('should not inject Authorization header when no token', async () => {
    (SecureStore.getItemAsync as jest.Mock).mockResolvedValue(null);

    mockAxios.onGet('/stations').reply((config) => {
      expect(config.headers?.Authorization).toBeUndefined();
      return [200, { code: 0, message: 'ok', data: { items: [], total: 0, page: 1, pageSize: 10 } }];
    });

    await api.get('/stations');
  });

  it('should handle SecureStore error gracefully', async () => {
    (SecureStore.getItemAsync as jest.Mock).mockRejectedValue(new Error('SecureStore error'));

    mockAxios.onGet('/auth/profile').reply((config) => {
      expect(config.headers?.Authorization).toBeUndefined();
      return [200, { code: 0, message: 'ok', data: {} }];
    });

    await api.get('/auth/profile');
  });
});

describe('401 response interceptor', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('should clear token on 401 response', async () => {
    mockAxios.onGet('/auth/profile').reply(401, { code: 401, message: 'Unauthorized' });

    await expect(api.get('/auth/profile')).rejects.toThrow();
    expect(SecureStore.deleteItemAsync).toHaveBeenCalledWith('auth_token');
  });

  it('should not clear token on non-401 errors', async () => {
    mockAxios.onGet('/auth/profile').reply(500, { code: 500, message: 'Server Error' });

    await expect(api.get('/auth/profile')).rejects.toThrow();
    expect(SecureStore.deleteItemAsync).not.toHaveBeenCalled();
  });

  it('should propagate the error after handling 401', async () => {
    mockAxios.onGet('/auth/profile').reply(401, { code: 401, message: 'Unauthorized' });

    await expect(api.get('/auth/profile')).rejects.toBeDefined();
  });
});

describe('tokenStorage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('getToken should return token from SecureStore', async () => {
    (SecureStore.getItemAsync as jest.Mock).mockResolvedValue(TEST_TOKEN);
    const token = await tokenStorage.getToken();
    expect(token).toBe(TEST_TOKEN);
    expect(SecureStore.getItemAsync).toHaveBeenCalledWith('auth_token');
  });

  it('getToken should return null on error', async () => {
    (SecureStore.getItemAsync as jest.Mock).mockRejectedValue(new Error('error'));
    const token = await tokenStorage.getToken();
    expect(token).toBeNull();
  });

  it('setToken should store token in SecureStore', async () => {
    await tokenStorage.setToken(TEST_TOKEN);
    expect(SecureStore.setItemAsync).toHaveBeenCalledWith('auth_token', TEST_TOKEN);
  });

  it('removeToken should delete token from SecureStore', async () => {
    await tokenStorage.removeToken();
    expect(SecureStore.deleteItemAsync).toHaveBeenCalledWith('auth_token');
  });
});

describe('authApi', () => {
  beforeEach(() => {
    mockAxios.reset();
    jest.clearAllMocks();
  });

  it('login should POST /auth/login and return data', async () => {
    const loginData = { username: 'admin', password: '123456' };
    const responseData = { token: TEST_TOKEN, user: { id: 1, username: 'admin', nickname: '管理员', email: 'admin@test.com', phone: '13800138000', role: 'admin' as const, stationIds: [1, 2], createdAt: '2024-01-01T00:00:00Z', updatedAt: '2024-01-01T00:00:00Z' } };
    const apiResponse = { code: 0, message: 'success', data: responseData };

    mockAxios.onPost('/auth/login', loginData).reply(200, apiResponse);

    const result = await authApi.login(loginData);
    expect(result).toEqual(apiResponse);
  });

  it('logout should POST /auth/logout', async () => {
    const apiResponse = { code: 0, message: 'success', data: null };
    mockAxios.onPost('/auth/logout').reply(200, apiResponse);

    const result = await authApi.logout();
    expect(result).toEqual(apiResponse);
  });

  it('getProfile should GET /auth/profile', async () => {
    const user = { id: 1, username: 'admin', nickname: '管理员', email: 'admin@test.com', phone: '13800138000', role: 'admin' as const, stationIds: [1, 2], createdAt: '2024-01-01T00:00:00Z', updatedAt: '2024-01-01T00:00:00Z' };
    const apiResponse = { code: 0, message: 'success', data: user };
    mockAxios.onGet('/auth/profile').reply(200, apiResponse);

    const result = await authApi.getProfile();
    expect(result).toEqual(apiResponse);
  });
});

describe('stationApi', () => {
  beforeEach(() => {
    mockAxios.reset();
  });

  it('getList should GET /stations with params', async () => {
    const paginatedData = { items: [{ id: 1, name: '站A', code: 'ST001', address: '地址A', status: 'online' as const, latitude: 23.1, longitude: 113.3, deviceCount: 5, onlineDeviceCount: 3, alarmCount: 1, createdAt: '2024-01-01T00:00:00Z', updatedAt: '2024-01-01T00:00:00Z' }], total: 1, page: 1, pageSize: 10 };
    const apiResponse = { code: 0, message: 'success', data: paginatedData };
    mockAxios.onGet('/stations', { params: { page: 1, pageSize: 10 } }).reply(200, apiResponse);

    const result = await stationApi.getList({ page: 1, pageSize: 10 });
    expect(result).toEqual(apiResponse);
  });

  it('getList should work without params', async () => {
    const paginatedData = { items: [], total: 0, page: 1, pageSize: 10 };
    const apiResponse = { code: 0, message: 'success', data: paginatedData };
    mockAxios.onGet('/stations').reply(200, apiResponse);

    const result = await stationApi.getList();
    expect(result).toEqual(apiResponse);
  });

  it('getDetail should GET /stations/:id', async () => {
    const station = { id: 1, name: '站A', code: 'ST001', address: '地址A', status: 'online' as const, latitude: 23.1, longitude: 113.3, deviceCount: 5, onlineDeviceCount: 3, alarmCount: 1, createdAt: '2024-01-01T00:00:00Z', updatedAt: '2024-01-01T00:00:00Z' };
    const apiResponse = { code: 0, message: 'success', data: station };
    mockAxios.onGet('/stations/1').reply(200, apiResponse);

    const result = await stationApi.getDetail(1);
    expect(result).toEqual(apiResponse);
  });

  it('getDevices should GET /stations/:stationId/devices', async () => {
    const devices = [{ id: 1, stationId: 1, name: '充电桩A', code: 'CH001', type: 'charger' as const, status: 'online' as const, model: 'CH-2000', manufacturer: '厂商A', lastHeartbeat: '2024-01-01T00:00:00Z', createdAt: '2024-01-01T00:00:00Z', updatedAt: '2024-01-01T00:00:00Z' }];
    const apiResponse = { code: 0, message: 'success', data: devices };
    mockAxios.onGet('/stations/1/devices').reply(200, apiResponse);

    const result = await stationApi.getDevices(1);
    expect(result).toEqual(apiResponse);
  });

  it('getAlarms should GET /stations/:stationId/alarms with params', async () => {
    const paginatedData = { items: [], total: 0, page: 1, pageSize: 10 };
    const apiResponse = { code: 0, message: 'success', data: paginatedData };
    mockAxios.onGet('/stations/1/alarms', { params: { page: 1, pageSize: 10 } }).reply(200, apiResponse);

    const result = await stationApi.getAlarms(1, { page: 1, pageSize: 10 });
    expect(result).toEqual(apiResponse);
  });
});

describe('deviceApi', () => {
  beforeEach(() => {
    mockAxios.reset();
  });

  it('getList should GET /devices', async () => {
    const paginatedData = { items: [], total: 0, page: 1, pageSize: 10 };
    const apiResponse = { code: 0, message: 'success', data: paginatedData };
    mockAxios.onGet('/devices').reply(200, apiResponse);

    const result = await deviceApi.getList();
    expect(result).toEqual(apiResponse);
  });

  it('getList should pass stationId param', async () => {
    const paginatedData = { items: [], total: 0, page: 1, pageSize: 10 };
    const apiResponse = { code: 0, message: 'success', data: paginatedData };
    mockAxios.onGet('/devices', { params: { stationId: 1 } }).reply(200, apiResponse);

    const result = await deviceApi.getList({ stationId: 1 });
    expect(result).toEqual(apiResponse);
  });

  it('getDetail should GET /devices/:id', async () => {
    const device = { id: 1, stationId: 1, name: '充电桩A', code: 'CH001', type: 'charger' as const, status: 'online' as const, model: 'CH-2000', manufacturer: '厂商A', lastHeartbeat: '2024-01-01T00:00:00Z', createdAt: '2024-01-01T00:00:00Z', updatedAt: '2024-01-01T00:00:00Z' };
    const apiResponse = { code: 0, message: 'success', data: device };
    mockAxios.onGet('/devices/1').reply(200, apiResponse);

    const result = await deviceApi.getDetail(1);
    expect(result).toEqual(apiResponse);
  });
});

describe('alarmApi', () => {
  beforeEach(() => {
    mockAxios.reset();
  });

  it('getList should GET /alarms', async () => {
    const paginatedData = { items: [], total: 0, page: 1, pageSize: 10 };
    const apiResponse = { code: 0, message: 'success', data: paginatedData };
    mockAxios.onGet('/alarms').reply(200, apiResponse);

    const result = await alarmApi.getList();
    expect(result).toEqual(apiResponse);
  });

  it('getDetail should GET /alarms/:id', async () => {
    const alarm = { id: 1, stationId: 1, stationName: '站A', type: 'device_fault' as const, level: 'warning' as const, title: '温度异常', description: '温度过高', status: 'unhandled' as const, createdAt: '2024-01-01T00:00:00Z', updatedAt: '2024-01-01T00:00:00Z' };
    const apiResponse = { code: 0, message: 'success', data: alarm };
    mockAxios.onGet('/alarms/1').reply(200, apiResponse);

    const result = await alarmApi.getDetail(1);
    expect(result).toEqual(apiResponse);
  });

  it('handleAlarm should POST /alarms/:id/handle', async () => {
    const alarm = { id: 1, stationId: 1, stationName: '站A', type: 'device_fault' as const, level: 'warning' as const, title: '温度异常', description: '温度过高', status: 'resolved' as const, createdAt: '2024-01-01T00:00:00Z', updatedAt: '2024-01-01T00:00:00Z' };
    const apiResponse = { code: 0, message: 'success', data: alarm };
    mockAxios.onPost('/alarms/1/handle').reply(200, apiResponse);

    const result = await alarmApi.handleAlarm(1);
    expect(result).toEqual(apiResponse);
  });
});

describe('workOrderApi', () => {
  beforeEach(() => {
    mockAxios.reset();
  });

  it('getList should GET /work-orders', async () => {
    const paginatedData = { items: [], total: 0, page: 1, pageSize: 10 };
    const apiResponse = { code: 0, message: 'success', data: paginatedData };
    mockAxios.onGet('/work-orders').reply(200, apiResponse);

    const result = await workOrderApi.getList();
    expect(result).toEqual(apiResponse);
  });

  it('getDetail should GET /work-orders/:id', async () => {
    const workOrder = { id: 1, stationId: 1, stationName: '站A', title: '维修', description: '需要维修', type: 'repair' as const, priority: 'high' as const, status: 'pending' as const, creatorId: 1, creatorName: 'admin', createdAt: '2024-01-01T00:00:00Z', updatedAt: '2024-01-01T00:00:00Z' };
    const apiResponse = { code: 0, message: 'success', data: workOrder };
    mockAxios.onGet('/work-orders/1').reply(200, apiResponse);

    const result = await workOrderApi.getDetail(1);
    expect(result).toEqual(apiResponse);
  });
});

describe('dashboardApi', () => {
  beforeEach(() => {
    mockAxios.reset();
  });

  it('getStats should GET /dashboard/stats', async () => {
    const stats = { totalStations: 10, onlineStations: 8, offlineStations: 2, totalAlarms: 5, unhandledAlarms: 2, revenueSummary: { today: 1000, week: 7000, month: 30000, total: 500000 } };
    const apiResponse = { code: 0, message: 'success', data: stats };
    mockAxios.onGet('/dashboard/stats').reply(200, apiResponse);

    const result = await dashboardApi.getStats();
    expect(result).toEqual(apiResponse);
  });

  it('getRecentAlarms should GET /dashboard/recent-alarms', async () => {
    const alarms: never[] = [];
    const apiResponse = { code: 0, message: 'success', data: alarms };
    mockAxios.onGet('/dashboard/recent-alarms', { params: { limit: 5 } }).reply(200, apiResponse);

    const result = await dashboardApi.getRecentAlarms(5);
    expect(result).toEqual(apiResponse);
  });
});

describe('revenueApi', () => {
  beforeEach(() => {
    mockAxios.reset();
  });

  it('getSummary should GET /revenue/summary', async () => {
    const summary = { today: 1000, week: 7000, month: 30000, total: 500000 };
    const apiResponse = { code: 0, message: 'success', data: summary };
    mockAxios.onGet('/revenue/summary').reply(200, apiResponse);

    const result = await revenueApi.getSummary();
    expect(result).toEqual(apiResponse);
  });

  it('getRecords should GET /revenue/records', async () => {
    const records = [{ date: '2024-01-01', amount: 1000, orderCount: 10 }];
    const apiResponse = { code: 0, message: 'success', data: records };
    mockAxios.onGet('/revenue/records', { params: { type: 'day' } }).reply(200, apiResponse);

    const result = await revenueApi.getRecords({ type: 'day' });
    expect(result).toEqual(apiResponse);
  });
});

describe('chargerApi', () => {
  beforeEach(() => {
    mockAxios.reset();
  });

  it('getMonitorList should GET /stations/:id/chargers/monitor', async () => {
    const chargers = [{ id: 1, deviceId: 101, deviceName: '充电桩1', connectorStatus: 'idle', power: 0, voltage: 220, current: 0, temperature: 25, energyTotal: 1000, sessionEnergy: 0, sessionDuration: 0, state: 'idle', faultCode: null, faultMessage: null, lastHeartbeat: '2024-01-01T00:00:00Z', updatedAt: '2024-01-01T00:00:00Z' }];
    const apiResponse = { code: 0, message: 'success', data: chargers };
    mockAxios.onGet('/stations/1/chargers/monitor').reply(200, apiResponse);

    const result = await chargerApi.getMonitorList(1);
    expect(result).toEqual(apiResponse);
  });

  it('getMonitorSummary should GET /stations/:id/chargers/summary', async () => {
    const summary = { totalChargers: 5, chargingCount: 2, idleCount: 2, faultCount: 1, totalPower: 120.5, todayEnergy: 500, todaySessions: 20, avgPowerPerCharger: 24.1 };
    const apiResponse = { code: 0, message: 'success', data: summary };
    mockAxios.onGet('/stations/1/chargers/summary').reply(200, apiResponse);

    const result = await chargerApi.getMonitorSummary(1);
    expect(result).toEqual(apiResponse);
  });

  it('getFaultRecords should GET /chargers/faults', async () => {
    const paginatedData = { items: [], total: 0, page: 1, pageSize: 10 };
    const apiResponse = { code: 0, message: 'success', data: paginatedData };
    mockAxios.onGet('/chargers/faults', { params: { stationId: 1 } }).reply(200, apiResponse);

    const result = await chargerApi.getFaultRecords({ stationId: 1 });
    expect(result).toEqual(apiResponse);
  });

  it('clearFault should POST /chargers/faults/:id/clear', async () => {
    const apiResponse = { code: 0, message: 'success', data: { success: true, message: '故障已清除' } };
    mockAxios.onPost('/chargers/faults/1/clear').reply(200, apiResponse);

    const result = await chargerApi.clearFault(1);
    expect(result).toEqual(apiResponse);
  });

  it('getTrend should GET /devices/:id/charger-trend', async () => {
    const trend = {
      deviceId: 101,
      points: [
        { timestamp: '2024-01-15T10:00:00Z', power: 10, voltage: 380, current: 30, soc: 20 },
        { timestamp: '2024-01-15T10:05:00Z', power: 30, voltage: 381, current: 80, soc: 45 },
      ],
    };
    const apiResponse = { code: 0, message: 'success', data: trend };
    mockAxios.onGet('/devices/101/charger-trend', { params: { points: 20 } }).reply(200, apiResponse);

    const result = await chargerApi.getTrend(101, { points: 20 });
    expect(result).toEqual(apiResponse);
  });
});

describe('notificationApi', () => {
  beforeEach(() => {
    mockAxios.reset();
  });

  it('getList should GET /notifications', async () => {
    const paginatedData = { items: [], total: 0, page: 1, pageSize: 20 };
    const apiResponse = { code: 0, message: 'success', data: paginatedData };
    mockAxios.onGet('/notifications').reply(200, apiResponse);

    const result = await notificationApi.getList();
    expect(result).toEqual(apiResponse);
  });

  it('getUnreadCount should GET /notifications/unread-count', async () => {
    const apiResponse = { code: 0, message: 'success', data: { count: 5 } };
    mockAxios.onGet('/notifications/unread-count').reply(200, apiResponse);

    const result = await notificationApi.getUnreadCount();
    expect(result).toEqual(apiResponse);
  });

  it('markAsRead should POST /notifications/:id/read', async () => {
    const notification = { id: 1, type: 'alarm', title: '告警', message: '温度异常', level: 'critical', isRead: true, createdAt: '2024-01-01T00:00:00Z' };
    const apiResponse = { code: 0, message: 'success', data: notification };
    mockAxios.onPost('/notifications/1/read').reply(200, apiResponse);

    const result = await notificationApi.markAsRead(1);
    expect(result).toEqual(apiResponse);
  });

  it('markAllAsRead should POST /notifications/read-all', async () => {
    const apiResponse = { code: 0, message: 'success', data: null };
    mockAxios.onPost('/notifications/read-all').reply(200, apiResponse);

    const result = await notificationApi.markAllAsRead();
    expect(result).toEqual(apiResponse);
  });
});