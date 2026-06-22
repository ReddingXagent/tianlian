import axios from 'axios';
import MockAdapter from 'axios-mock-adapter';
import * as SecureStore from 'expo-secure-store';
import api, {
  tokenStorage,
  authApi,
  workbenchApi,
  workOrderApi,
  alarmApi,
  deviceApi,
  monitorApi,
  scanApi,
  knowledgeApi,
  inspectionApi,
  dashboardApi,
  workOrderTransferApi,
} from '../api';

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

    mockAxios.onGet('/work-orders').reply((config) => {
      expect(config.headers?.Authorization).toBeUndefined();
      return [200, { code: 0, message: 'ok', data: { items: [], total: 0, page: 1, pageSize: 10 } }];
    });

    await api.get('/work-orders');
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
    const responseData = {
      token: TEST_TOKEN,
      user: {
        id: 1, username: 'admin', nickname: '管理员', email: 'admin@test.com',
        phone: '13800138000', role: 'admin' as const, stationIds: [1, 2],
        createdAt: '2024-01-01T00:00:00Z', updatedAt: '2024-01-01T00:00:00Z',
      },
    };
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
    const user = {
      id: 1, username: 'admin', nickname: '管理员', email: 'admin@test.com',
      phone: '13800138000', role: 'admin' as const, stationIds: [1, 2],
      createdAt: '2024-01-01T00:00:00Z', updatedAt: '2024-01-01T00:00:00Z',
    };
    const apiResponse = { code: 0, message: 'success', data: user };
    mockAxios.onGet('/auth/profile').reply(200, apiResponse);

    const result = await authApi.getProfile();
    expect(result).toEqual(apiResponse);
  });
});

describe('workbenchApi', () => {
  beforeEach(() => {
    mockAxios.reset();
  });

  it('getStats should GET /workbench/stats', async () => {
    const stats = {
      pendingOrders: 5, inProgressOrders: 3, todayCompleted: 10,
      unhandledAlarms: 2, criticalAlarms: 1,
    };
    const apiResponse = { code: 0, message: 'success', data: stats };
    mockAxios.onGet('/workbench/stats').reply(200, apiResponse);

    const result = await workbenchApi.getStats();
    expect(result).toEqual(apiResponse);
  });

  it('getPendingOrders should GET /workbench/pending-orders with limit', async () => {
    const orders: any[] = [];
    const apiResponse = { code: 0, message: 'success', data: orders };
    mockAxios.onGet('/workbench/pending-orders', { params: { limit: 5 } }).reply(200, apiResponse);

    const result = await workbenchApi.getPendingOrders(5);
    expect(result).toEqual(apiResponse);
  });

  it('getRecentAlarms should GET /workbench/recent-alarms with limit', async () => {
    const alarms: any[] = [];
    const apiResponse = { code: 0, message: 'success', data: alarms };
    mockAxios.onGet('/workbench/recent-alarms', { params: { limit: 5 } }).reply(200, apiResponse);

    const result = await workbenchApi.getRecentAlarms(5);
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

  it('getList should pass filter params', async () => {
    const paginatedData = { items: [], total: 0, page: 1, pageSize: 10 };
    const apiResponse = { code: 0, message: 'success', data: paginatedData };
    mockAxios.onGet('/work-orders', { params: { stationId: 1, status: 'pending', page: 1, pageSize: 20 } }).reply(200, apiResponse);

    const result = await workOrderApi.getList({ stationId: 1, status: 'pending', page: 1, pageSize: 20 });
    expect(result).toEqual(apiResponse);
  });

  it('getDetail should GET /work-orders/:id', async () => {
    const workOrder = {
      id: 1, stationId: 1, stationName: '站A', title: '维修', description: '需要维修',
      type: 'repair' as const, priority: 'high' as const, status: 'pending' as const,
      creatorId: 1, creatorName: 'admin',
      createdAt: '2024-01-01T00:00:00Z', updatedAt: '2024-01-01T00:00:00Z',
    };
    const apiResponse = { code: 0, message: 'success', data: workOrder };
    mockAxios.onGet('/work-orders/1').reply(200, apiResponse);

    const result = await workOrderApi.getDetail(1);
    expect(result).toEqual(apiResponse);
  });

  it('create should POST /work-orders', async () => {
    const newOrder = { title: '新工单', description: '测试', stationId: 1, priority: 'normal' as const };
    const created = { id: 99, ...newOrder, stationName: '站A', type: 'repair' as const, status: 'pending' as const, creatorId: 1, creatorName: 'admin', createdAt: '2024-01-01T00:00:00Z', updatedAt: '2024-01-01T00:00:00Z' };
    const apiResponse = { code: 0, message: 'success', data: created };
    mockAxios.onPost('/work-orders', newOrder).reply(200, apiResponse);

    const result = await workOrderApi.create(newOrder);
    expect(result).toEqual(apiResponse);
  });

  it('update should PUT /work-orders/:id', async () => {
    const updateData = { title: '更新标题' };
    const updated = { id: 1, stationId: 1, stationName: '站A', title: '更新标题', description: '需要维修', type: 'repair' as const, priority: 'high' as const, status: 'pending' as const, creatorId: 1, creatorName: 'admin', createdAt: '2024-01-01T00:00:00Z', updatedAt: '2024-01-01T00:00:00Z' };
    const apiResponse = { code: 0, message: 'success', data: updated };
    mockAxios.onPut('/work-orders/1', updateData).reply(200, apiResponse);

    const result = await workOrderApi.update(1, updateData);
    expect(result).toEqual(apiResponse);
  });

  it('updateStatus should PATCH /work-orders/:id/status', async () => {
    const updated = { id: 1, stationId: 1, stationName: '站A', title: '维修', description: '需要维修', type: 'repair' as const, priority: 'high' as const, status: 'in_progress' as const, creatorId: 1, creatorName: 'admin', createdAt: '2024-01-01T00:00:00Z', updatedAt: '2024-01-01T00:00:00Z' };
    const apiResponse = { code: 0, message: 'success', data: updated };
    mockAxios.onPatch('/work-orders/1/status', { status: 'in_progress' }).reply(200, apiResponse);

    const result = await workOrderApi.updateStatus(1, 'in_progress');
    expect(result).toEqual(apiResponse);
  });

  it('assign should POST /work-orders/:id/assign', async () => {
    const updated = { id: 1, stationId: 1, stationName: '站A', title: '维修', description: '需要维修', type: 'repair' as const, priority: 'high' as const, status: 'in_progress' as const, assigneeId: 2, assigneeName: '张三', creatorId: 1, creatorName: 'admin', createdAt: '2024-01-01T00:00:00Z', updatedAt: '2024-01-01T00:00:00Z' };
    const apiResponse = { code: 0, message: 'success', data: updated };
    mockAxios.onPost('/work-orders/1/assign', { assigneeId: 2 }).reply(200, apiResponse);

    const result = await workOrderApi.assign(1, 2);
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

  it('getList should pass filter params', async () => {
    const paginatedData = { items: [], total: 0, page: 1, pageSize: 10 };
    const apiResponse = { code: 0, message: 'success', data: paginatedData };
    mockAxios.onGet('/alarms', { params: { stationId: 1, level: 'critical', page: 1, pageSize: 10 } }).reply(200, apiResponse);

    const result = await alarmApi.getList({ stationId: 1, level: 'critical', page: 1, pageSize: 10 });
    expect(result).toEqual(apiResponse);
  });

  it('getDetail should GET /alarms/:id', async () => {
    const alarm = {
      id: 1, stationId: 1, stationName: '站A', type: 'device_fault' as const,
      level: 'warning' as const, title: '温度异常', description: '温度过高',
      status: 'unhandled' as const, createdAt: '2024-01-01T00:00:00Z', updatedAt: '2024-01-01T00:00:00Z',
    };
    const apiResponse = { code: 0, message: 'success', data: alarm };
    mockAxios.onGet('/alarms/1').reply(200, apiResponse);

    const result = await alarmApi.getDetail(1);
    expect(result).toEqual(apiResponse);
  });

  it('handleAlarm should POST /alarms/:id/handle', async () => {
    const alarm = {
      id: 1, stationId: 1, stationName: '站A', type: 'device_fault' as const,
      level: 'warning' as const, title: '温度异常', description: '温度过高',
      status: 'resolved' as const, createdAt: '2024-01-01T00:00:00Z', updatedAt: '2024-01-01T00:00:00Z',
    };
    const apiResponse = { code: 0, message: 'success', data: alarm };
    mockAxios.onPost('/alarms/1/handle').reply(200, apiResponse);

    const result = await alarmApi.handleAlarm(1);
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
    const device = {
      id: 1, stationId: 1, name: '充电桩A', code: 'CH001', type: 'charger' as const,
      status: 'online' as const, model: 'CH-2000', manufacturer: '厂商A',
      lastHeartbeat: '2024-01-01T00:00:00Z', createdAt: '2024-01-01T00:00:00Z', updatedAt: '2024-01-01T00:00:00Z',
    };
    const apiResponse = { code: 0, message: 'success', data: device };
    mockAxios.onGet('/devices/1').reply(200, apiResponse);

    const result = await deviceApi.getDetail(1);
    expect(result).toEqual(apiResponse);
  });

  it('getMetrics should GET /devices/:id/metrics', async () => {
    const metrics = {
      deviceId: 1, deviceName: '充电桩A', temperature: 35, humidity: 60,
      voltage: 220, current: 10, power: 2200, status: 'online' as const,
      lastUpdated: '2024-01-01T00:00:00Z',
    };
    const apiResponse = { code: 0, message: 'success', data: metrics };
    mockAxios.onGet('/devices/1/metrics').reply(200, apiResponse);

    const result = await deviceApi.getMetrics(1);
    expect(result).toEqual(apiResponse);
  });
});

describe('monitorApi', () => {
  beforeEach(() => {
    mockAxios.reset();
  });

  it('getSummary should GET /monitor/summary', async () => {
    const summary = { totalDevices: 100, onlineDevices: 85, faultDevices: 5, criticalAlarms: 3 };
    const apiResponse = { code: 0, message: 'success', data: summary };
    mockAxios.onGet('/monitor/summary').reply(200, apiResponse);

    const result = await monitorApi.getSummary();
    expect(result).toEqual(apiResponse);
  });

  it('getFaultDevices should GET /monitor/faults with pagination', async () => {
    const paginatedData = { items: [], total: 0, page: 1, pageSize: 10 };
    const apiResponse = { code: 0, message: 'success', data: paginatedData };
    mockAxios.onGet('/monitor/faults', { params: { page: 1, pageSize: 10 } }).reply(200, apiResponse);

    const result = await monitorApi.getFaultDevices({ page: 1, pageSize: 10 });
    expect(result).toEqual(apiResponse);
  });

  it('getCriticalAlarms should GET /monitor/critical-alarms with pagination', async () => {
    const paginatedData = { items: [], total: 0, page: 1, pageSize: 10 };
    const apiResponse = { code: 0, message: 'success', data: paginatedData };
    mockAxios.onGet('/monitor/critical-alarms', { params: { page: 1, pageSize: 10 } }).reply(200, apiResponse);

    const result = await monitorApi.getCriticalAlarms({ page: 1, pageSize: 10 });
    expect(result).toEqual(apiResponse);
  });
});

describe('scanApi', () => {
  beforeEach(() => {
    mockAxios.reset();
  });

  it('scan should POST /scan with code', async () => {
    const scanResult = { type: 'device' as const, id: 1, code: 'DEV001', name: '充电桩A' };
    const apiResponse = { code: 0, message: 'success', data: scanResult };
    mockAxios.onPost('/scan', { code: 'DEV001' }).reply(200, apiResponse);

    const result = await scanApi.scan('DEV001');
    expect(result).toEqual(apiResponse);
  });
});

describe('knowledgeApi', () => {
  beforeEach(() => {
    mockAxios.reset();
  });

  it('getList should GET /knowledge', async () => {
    const paginatedData = { items: [], total: 0, page: 1, pageSize: 10 };
    const apiResponse = { code: 0, message: 'success', data: paginatedData };
    mockAxios.onGet('/knowledge').reply(200, apiResponse);

    const result = await knowledgeApi.getList();
    expect(result).toEqual(apiResponse);
  });

  it('getList should pass category and search params', async () => {
    const paginatedData = { items: [], total: 0, page: 1, pageSize: 10 };
    const apiResponse = { code: 0, message: 'success', data: paginatedData };
    mockAxios.onGet('/knowledge', { params: { category: 'operation', search: '充电', page: 1, pageSize: 10 } }).reply(200, apiResponse);

    const result = await knowledgeApi.getList({ category: 'operation', search: '充电', page: 1, pageSize: 10 });
    expect(result).toEqual(apiResponse);
  });

  it('getDetail should GET /knowledge/:id', async () => {
    const article = {
      id: 1, title: '操作手册', summary: '操作说明', content: '详细内容...',
      category: 'operation' as const, tags: ['操作'], authorId: 1, authorName: 'admin',
      viewCount: 100, createdAt: '2024-01-01T00:00:00Z', updatedAt: '2024-01-01T00:00:00Z',
    };
    const apiResponse = { code: 0, message: 'success', data: article };
    mockAxios.onGet('/knowledge/1').reply(200, apiResponse);

    const result = await knowledgeApi.getDetail(1);
    expect(result).toEqual(apiResponse);
  });

  it('search should GET /knowledge/search with query', async () => {
    const articles: any[] = [];
    const apiResponse = { code: 0, message: 'success', data: articles };
    mockAxios.onGet('/knowledge/search', { params: { q: '充电' } }).reply(200, apiResponse);

    const result = await knowledgeApi.search('充电');
    expect(result).toEqual(apiResponse);
  });
});

describe('inspectionApi', () => {
  beforeEach(() => {
    mockAxios.reset();
  });

  it('getList should GET /inspections', async () => {
    const paginatedData = { items: [], total: 0, page: 1, pageSize: 10 };
    const apiResponse = { code: 0, message: 'success', data: paginatedData };
    mockAxios.onGet('/inspections').reply(200, apiResponse);

    const result = await inspectionApi.getList();
    expect(result).toEqual(apiResponse);
  });

  it('getList should pass filter params', async () => {
    const paginatedData = { items: [], total: 0, page: 1, pageSize: 10 };
    const apiResponse = { code: 0, message: 'success', data: paginatedData };
    mockAxios.onGet('/inspections', { params: { stationId: 1, status: 'pending' } }).reply(200, apiResponse);

    const result = await inspectionApi.getList({ stationId: 1, status: 'pending' });
    expect(result).toEqual(apiResponse);
  });

  it('getDetail should GET /inspections/:id', async () => {
    const task = {
      id: 1, stationId: 1, stationName: '站A', deviceId: 1, deviceName: '充电桩A',
      type: 'daily' as const, status: 'pending' as const,
      scheduledDate: '2024-01-01T00:00:00Z',
      description: '日检', items: [],
      createdAt: '2024-01-01T00:00:00Z', updatedAt: '2024-01-01T00:00:00Z',
    };
    const apiResponse = { code: 0, message: 'success', data: task };
    mockAxios.onGet('/inspections/1').reply(200, apiResponse);

    const result = await inspectionApi.getDetail(1);
    expect(result).toEqual(apiResponse);
  });

  it('create should POST /inspections', async () => {
    const newTask = { description: '巡检', stationId: 1, deviceId: 1, type: 'daily' as const };
    const apiResponse = { code: 0, message: 'success', data: { id: 1, ...newTask } };
    mockAxios.onPost('/inspections', newTask).reply(200, apiResponse);

    const result = await inspectionApi.create(newTask);
    expect(result).toEqual(apiResponse);
  });

  it('start should POST /inspections/:id/start', async () => {
    const task = { id: 1, status: 'in_progress' as const };
    const apiResponse = { code: 0, message: 'success', data: task };
    mockAxios.onPost('/inspections/1/start').reply(200, apiResponse);

    const result = await inspectionApi.start(1);
    expect(result).toEqual(apiResponse);
  });

  it('updateItem should PATCH /inspections/:taskId/items/:itemId', async () => {
    const apiResponse = { code: 0, message: 'success', data: { id: 1 } };
    mockAxios.onPatch('/inspections/1/items/1', { result: 'pass', note: '正常' }).reply(200, apiResponse);

    const result = await inspectionApi.updateItem(1, 1, { result: 'pass', note: '正常' });
    expect(result).toEqual(apiResponse);
  });

  it('complete should POST /inspections/:id/complete', async () => {
    const apiResponse = { code: 0, message: 'success', data: { id: 1, status: 'completed' as const } };
    mockAxios.onPost('/inspections/1/complete', { summary: '通过', overall: 'pass' }).reply(200, apiResponse);

    const result = await inspectionApi.complete(1, { summary: '通过', overall: 'pass' });
    expect(result).toEqual(apiResponse);
  });
});

describe('dashboardApi', () => {
  beforeEach(() => {
    mockAxios.reset();
  });

  it('getDashboard should GET /dashboard', async () => {
    const dashboardData = {
      stats: { totalOrders: 100, completedOrders: 80, pendingOrders: 20, avgCompletionHours: 3, onTimeRate: 90 },
      deviceHealth: { total: 50, online: 45, offline: 2, fault: 3, maintenance: 0, onlineRate: 90 },
      alarmTrends: [],
      workOrderTrends: [],
      topFaultDevices: [],
    };
    const apiResponse = { code: 0, message: 'success', data: dashboardData };
    mockAxios.onGet('/dashboard').reply(200, apiResponse);

    const result = await dashboardApi.getDashboard();
    expect(result).toEqual(apiResponse);
  });

  it('getAlarmTrends should GET /dashboard/alarm-trends with days', async () => {
    const trends: any[] = [];
    const apiResponse = { code: 0, message: 'success', data: trends };
    mockAxios.onGet('/dashboard/alarm-trends', { params: { days: 7 } }).reply(200, apiResponse);

    const result = await dashboardApi.getAlarmTrends({ days: 7 });
    expect(result).toEqual(apiResponse);
  });

  it('getWorkOrderTrends should GET /dashboard/workorder-trends', async () => {
    const trends: any[] = [];
    const apiResponse = { code: 0, message: 'success', data: trends };
    mockAxios.onGet('/dashboard/workorder-trends', { params: { days: 30 } }).reply(200, apiResponse);

    const result = await dashboardApi.getWorkOrderTrends({ days: 30 });
    expect(result).toEqual(apiResponse);
  });

  it('getDeviceHealth should GET /dashboard/device-health', async () => {
    const health = { total: 50, online: 45, offline: 2, fault: 3, maintenance: 0, onlineRate: 90 };
    const apiResponse = { code: 0, message: 'success', data: health };
    mockAxios.onGet('/dashboard/device-health').reply(200, apiResponse);

    const result = await dashboardApi.getDeviceHealth();
    expect(result).toEqual(apiResponse);
  });
});

describe('workOrderTransferApi', () => {
  beforeEach(() => {
    mockAxios.reset();
  });

  it('transfer should POST /work-orders/:id/transfer', async () => {
    const workOrder = {
      id: 1, stationId: 1, stationName: '站A', title: '维修', description: '需要维修',
      type: 'repair' as const, priority: 'high' as const, status: 'in_progress' as const,
      assigneeId: 3, assigneeName: '李四', creatorId: 1, creatorName: 'admin',
      createdAt: '2024-01-01T00:00:00Z', updatedAt: '2024-01-01T00:00:00Z',
    };
    const apiResponse = { code: 0, message: 'success', data: workOrder };
    mockAxios.onPost('/work-orders/1/transfer', { assigneeId: 3, reason: '需要其他人处理' }).reply(200, apiResponse);

    const result = await workOrderTransferApi.transfer(1, { assigneeId: 3, reason: '需要其他人处理' });
    expect(result).toEqual(apiResponse);
  });

  it('escalate should POST /work-orders/:id/escalate', async () => {
    const workOrder = {
      id: 1, stationId: 1, stationName: '站A', title: '维修', description: '需要维修',
      type: 'repair' as const, priority: 'urgent' as const, status: 'in_progress' as const,
      assigneeId: 2, assigneeName: '张三', creatorId: 1, creatorName: 'admin',
      createdAt: '2024-01-01T00:00:00Z', updatedAt: '2024-01-01T00:00:00Z',
    };
    const apiResponse = { code: 0, message: 'success', data: workOrder };
    mockAxios.onPost('/work-orders/1/escalate', { reason: '需要升级' }).reply(200, apiResponse);

    const result = await workOrderTransferApi.escalate(1, '需要升级');
    expect(result).toEqual(apiResponse);
  });
});
