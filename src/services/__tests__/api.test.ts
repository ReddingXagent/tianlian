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
  workOrderActionApi,
  workOrderRecordApi,
} from '../api';

// Mock expo-secure-store
jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn(),
  setItemAsync: jest.fn(),
  deleteItemAsync: jest.fn(),
}));

const mockAxios = new MockAdapter(api);

const TEST_TOKEN = 'test-jwt-token-12345';
const BASE_URL =
  process.env.EXPO_PUBLIC_API_URL ||
  (__DEV__ ? 'http://localhost:8000/api/v1' : 'http://8.134.106.166/api/v1');

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

  it('getProfile should GET /auth/me', async () => {
    const rawUser = {
      id: 1, username: 'admin', real_name: '管理员', role: 'super_admin',
      permissions: ['station:view'], team_type: null, team_id: null,
    };
    const apiResponse = { code: 200, message: 'success', data: rawUser };
    mockAxios.onGet('/auth/me').reply(200, apiResponse);

    const result = await authApi.getProfile();
    expect(result.data.id).toBe(1);
    expect(result.data.username).toBe('admin');
    expect(result.data.realName).toBe('管理员');
    expect(result.data.role).toBe('super_admin');
    expect(result.data.permissions).toEqual(['station:view']);
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
    const orders: Record<string, unknown>[] = [];
    const apiResponse = { code: 0, message: 'success', data: orders };
    mockAxios.onGet('/workbench/pending-orders', { params: { limit: 5 } }).reply(200, apiResponse);

    const result = await workbenchApi.getPendingOrders(5);
    expect(result).toEqual(apiResponse);
  });

  it('getRecentAlarms should GET /workbench/recent-alarms with limit', async () => {
    const alarms: Record<string, unknown>[] = [];
    const apiResponse = { code: 0, message: 'success', data: alarms };
    mockAxios.onGet('/workbench/recent-alarms', { params: { limit: 5 } }).reply(200, apiResponse);

    const result = await workbenchApi.getRecentAlarms(5);
    expect(result).toEqual(apiResponse);
  });
});

describe('workOrderApi (真后端契约: snake_case + WO-字符串id)', () => {
  beforeEach(() => {
    mockAxios.reset();
  });

  const RAW_WO = {
    id: 'WO-20260728-100000',
    fault_desc: 'PCS通讯中断',
    type: 'repair',
    level: 'critical',
    status: 'processing',
    station_id: 3,
    device_id: 7,
    assignee_id: 2,
    creator_id: 999,
    create_time: '2026-07-28T10:00:00',
    accept_time: '2026-07-28T10:05:00',
    finish_time: null,
    solution: null,
  };

  it('getList should GET /work-orders and map snake_case items', async () => {
    const apiResponse = {
      code: 200,
      message: 'success',
      data: { items: [RAW_WO], total: 1, page: 1, page_size: 20 },
    };
    mockAxios.onGet('/work-orders').reply(200, apiResponse);

    const result = await workOrderApi.getList();
    expect(result.data.total).toBe(1);
    expect(result.data.pageSize).toBe(20);
    expect(result.data.items[0]).toMatchObject({
      id: 'WO-20260728-100000',
      title: 'PCS通讯中断',
      priority: 'high',
      status: 'in_progress',
      stationId: 3,
      assigneeId: 2,
    });
  });

  it('getList should convert client status filter to backend status + page_size', async () => {
    const apiResponse = {
      code: 200,
      message: 'success',
      data: { items: [], total: 0, page: 1, page_size: 10 },
    };
    mockAxios.onGet('/work-orders').reply(200, apiResponse);

    await workOrderApi.getList({ status: 'in_progress', page: 1, pageSize: 10 });
    const sent = mockAxios.history.get[0].params;
    expect(sent.status).toBe('processing');
    expect(sent.page_size).toBe(10);
  });

  it('getDetail should GET /work-orders/:id (string id) and map payload', async () => {
    const apiResponse = { code: 200, message: 'success', data: RAW_WO };
    mockAxios.onGet('/work-orders/WO-20260728-100000').reply(200, apiResponse);

    const result = await workOrderApi.getDetail('WO-20260728-100000');
    expect(result.data.id).toBe('WO-20260728-100000');
    expect(result.data.status).toBe('in_progress');
  });

  it('create should POST snake_case body and map response', async () => {
    const apiResponse = { code: 200, message: 'success', data: RAW_WO };
    mockAxios.onPost('/work-orders').reply(200, apiResponse);

    await workOrderApi.create({ faultDesc: 'PCS通讯中断', type: 'repair', level: 'critical', stationId: 3, deviceId: 7 });
    const body = JSON.parse(mockAxios.history.post[0].data);
    expect(body).toMatchObject({
      fault_desc: 'PCS通讯中断',
      type: 'repair',
      level: 'critical',
      station_id: 3,
      device_id: 7,
    });
  });

  it('update should PUT snake_case body', async () => {
    const apiResponse = { code: 200, message: 'success', data: RAW_WO };
    mockAxios.onPut('/work-orders/WO-1').reply(200, apiResponse);

    await workOrderApi.update('WO-1', { solution: '已更换通讯模块', assigneeId: 5 });
    const body = JSON.parse(mockAxios.history.put[0].data);
    expect(body).toMatchObject({ solution: '已更换通讯模块', assignee_id: 5 });
  });

  it('updateStatus should PUT mapped backend status', async () => {
    const apiResponse = { code: 200, message: 'success', data: RAW_WO };
    mockAxios.onPut('/work-orders/WO-1').reply(200, apiResponse);

    await workOrderApi.updateStatus('WO-1', 'in_progress');
    const body = JSON.parse(mockAxios.history.put[0].data);
    expect(body.status).toBe('processing');
  });

  it('updateStatus should reject unsupported client status (cancelled)', async () => {
    await expect(workOrderApi.updateStatus('WO-1', 'cancelled')).rejects.toThrow('不支持');
    expect(mockAxios.history.put.length).toBe(0);
  });

  it('assign should PUT assignee_id (manual assign via update)', async () => {
    const apiResponse = { code: 200, message: 'success', data: RAW_WO };
    mockAxios.onPut('/work-orders/WO-1').reply(200, apiResponse);

    await workOrderApi.assign('WO-1', 2);
    const body = JSON.parse(mockAxios.history.put[0].data);
    expect(body.assignee_id).toBe(2);
  });
});

describe('workOrderActionApi (真端点 accept/start/complete)', () => {
  beforeEach(() => {
    mockAxios.reset();
  });

  it('accept should POST /work-orders/:id/accept', async () => {
    mockAxios.onPost('/work-orders/WO-1/accept').reply(200, { code: 200, message: '接单成功', data: { status: 'accepted' } });
    const result = await workOrderActionApi.accept('WO-1');
    expect(result.message).toBe('接单成功');
  });

  it('start should POST /work-orders/:id/start', async () => {
    mockAxios.onPost('/work-orders/WO-1/start').reply(200, { code: 200, message: '开始处理', data: { status: 'processing' } });
    const result = await workOrderActionApi.start('WO-1');
    expect(result.message).toBe('开始处理');
  });

  it('complete should POST /work-orders/:id/complete with solution query param', async () => {
    mockAxios.onPost('/work-orders/WO-1/complete').reply(200, { code: 200, message: '完成申请已提交', data: { status: 'pending_verify' } });
    await workOrderActionApi.complete('WO-1', '更换模块');
    expect(mockAxios.history.post[0].params).toEqual({ solution: '更换模块' });
  });
});

describe('workOrderRecordApi (真端点 logs/notes)', () => {
  beforeEach(() => {
    mockAxios.reset();
  });

  it('getRecords should GET /work-orders/:id/logs and map items', async () => {
    mockAxios.onGet('/work-orders/WO-1/logs').reply(200, {
      code: 200,
      message: 'success',
      data: {
        items: [{ id: 11, action: 'accepted', description: '工程师已接单', created_at: '2026-07-28T10:05:00' }],
        total: 1,
      },
    });
    const result = await workOrderRecordApi.getRecords('WO-1');
    expect(result.data[0]).toMatchObject({
      id: 11,
      orderId: 'WO-1',
      action: 'accepted',
      note: '工程师已接单',
      createdAt: '2026-07-28T10:05:00',
    });
  });

  it('addRecord should POST /work-orders/:id/notes', async () => {
    mockAxios.onPost('/work-orders/WO-1/notes').reply(200, {
      code: 200,
      message: '备注已添加',
      data: { id: 12, action: 'note', description: '现场拍照留档', created_at: '2026-07-28T11:00:00' },
    });
    const result = await workOrderRecordApi.addRecord('WO-1', { action: 'note', note: '现场拍照留档' });
    expect(result.data.note).toBe('现场拍照留档');
    const body = JSON.parse(mockAxios.history.post[0].data);
    expect(body).toEqual({ action: 'note', note: '现场拍照留档' });
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

  it('getArticles should GET /knowledge/articles with default pagination', async () => {
    const apiResponse = {
      code: 200, message: 'success',
      data: { items: [], total: 0, page: 1, page_size: 20 },
      timestamp: 0,
    };
    mockAxios.onGet('/knowledge/articles').reply(200, apiResponse);

    const result = await knowledgeApi.getArticles();
    expect(result.data.items).toHaveLength(0);
    expect(result.data.total).toBe(0);
  });

  it('getArticles should pass pagination params', async () => {
    const apiResponse = {
      code: 200, message: 'success',
      data: { items: [], total: 0, page: 2, page_size: 5 },
      timestamp: 0,
    };
    mockAxios.onGet('/knowledge/articles?page=2&page_size=5').reply(200, apiResponse);

    const result = await knowledgeApi.getArticles({ page: 2, page_size: 5 });
    expect(result.data.page).toBe(2);
  });

  it('getCategories should GET /knowledge/categories', async () => {
    const apiResponse = { code: 200, message: 'success', data: [], timestamp: 0 };
    mockAxios.onGet('/knowledge/categories').reply(200, apiResponse);

    const result = await knowledgeApi.getCategories();
    expect(result.data).toHaveLength(0);
  });

  it('search should GET /knowledge/search with encoded query', async () => {
    const apiResponse = {
      code: 200, message: 'success',
      data: { items: [], total: 0, page: 1, page_size: 20 },
      timestamp: 0,
    };
    mockAxios.onGet('/knowledge/search?q=%E5%85%85%E7%94%B5&page=1&page_size=20').reply(200, apiResponse);

    const result = await knowledgeApi.search('充电');
    expect(result.data.items).toHaveLength(0);
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
    const trends: Record<string, unknown>[] = [];
    const apiResponse = { code: 0, message: 'success', data: trends };
    mockAxios.onGet('/dashboard/alarm-trends', { params: { days: 7 } }).reply(200, apiResponse);

    const result = await dashboardApi.getAlarmTrends({ days: 7 });
    expect(result).toEqual(apiResponse);
  });

  it('getWorkOrderTrends should GET /dashboard/workorder-trends', async () => {
    const trends: Record<string, unknown>[] = [];
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

describe('workOrderTransferApi (真端点 transfer/urge)', () => {
  beforeEach(() => {
    mockAxios.reset();
  });

  it('transfer should POST snake_case target_engineer_id body', async () => {
    const apiResponse = { code: 200, message: '转单成功', data: { status: 'pending', new_engineer: '李四' } };
    mockAxios.onPost('/work-orders/WO-1/transfer').reply(200, apiResponse);

    const result = await workOrderTransferApi.transfer('WO-1', { targetEngineerId: 3, reason: '需要其他人处理' });
    expect(result.message).toBe('转单成功');
    const body = JSON.parse(mockAxios.history.post[0].data);
    expect(body).toEqual({ target_engineer_id: 3, reason: '需要其他人处理' });
  });

  it('urge should POST /work-orders/:id/urge with message', async () => {
    const apiResponse = { code: 200, message: '催单成功', data: { message: '已催单给工程师 2' } };
    mockAxios.onPost('/work-orders/WO-1/urge').reply(200, apiResponse);

    const result = await workOrderTransferApi.urge('WO-1', '客户催了');
    expect(result.message).toBe('催单成功');
    const body = JSON.parse(mockAxios.history.post[0].data);
    expect(body).toEqual({ message: '客户催了' });
  });

  it('urge should default message', async () => {
    mockAxios.onPost('/work-orders/WO-1/urge').reply(200, { code: 200, message: '催单成功', data: {} });
    await workOrderTransferApi.urge('WO-1');
    const body = JSON.parse(mockAxios.history.post[0].data);
    expect(body.message).toBe('请尽快处理');
  });
});
