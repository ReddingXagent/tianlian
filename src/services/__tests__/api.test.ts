import MockAdapter from 'axios-mock-adapter';
import * as SecureStore from 'expo-secure-store';
import api, {
  tokenStorage,
  authApi,
  stationApi,
  deviceApi,
  alarmApi,
  workOrderApi,
  dashboardApi,
  revenueApi,
  mapAlarm,
  mapWorkOrder,
  mapStation,
  mapPagination,
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

beforeEach(() => {
  jest.clearAllMocks();
  mockAxios.reset();
  (SecureStore.getItemAsync as jest.Mock).mockResolvedValue(TEST_TOKEN);
});

describe('api instance', () => {
  it('should target the real cloud baseURL', () => {
    expect(api.defaults.baseURL).toBe(BASE_URL);
    expect(api.defaults.timeout).toBe(15000);
  });

  it('401 clears stored token', async () => {
    mockAxios.onGet('/alarms').reply(401, { detail: 'Unauthorized' });
    await expect(alarmApi.getList()).rejects.toBeDefined();
    expect(SecureStore.deleteItemAsync).toHaveBeenCalledWith('auth_token');
  });

  it('request interceptor proceeds when SecureStore fails (no Authorization header)', async () => {
    (SecureStore.getItemAsync as jest.Mock).mockRejectedValueOnce(new Error('store down'));
    let authHeader: unknown = 'sentinel';
    mockAxios.onGet('/alarms').reply((config) => {
      authHeader = config.headers?.Authorization;
      return [200, { code: 200, message: 'success', data: { items: [], total: 0, page: 1, page_size: 1 } }];
    });
    await alarmApi.getList();
    expect(authHeader).toBeUndefined();
  });

  it('request interceptor error handler passes rejection through', async () => {
    // 后加的 request 拦截器先执行(axios LIFO), 其失败走token拦截器的rejected分支
    const failId = api.interceptors.request.use(() => Promise.reject(new Error('pre-fail')));
    mockAxios.onGet('/alarms').reply(200, { code: 200, message: 'success', data: { items: [], total: 0, page: 1, page_size: 1 } });
    await expect(alarmApi.getList()).rejects.toThrow('pre-fail');
    api.interceptors.request.eject(failId);
  });
});

describe('tokenStorage', () => {
  it('set/get/remove delegate to SecureStore', async () => {
    await tokenStorage.setToken('t1');
    expect(SecureStore.setItemAsync).toHaveBeenCalledWith('auth_token', 't1');
    await tokenStorage.getToken();
    expect(SecureStore.getItemAsync).toHaveBeenCalledWith('auth_token');
    await tokenStorage.removeToken();
    expect(SecureStore.deleteItemAsync).toHaveBeenCalledWith('auth_token');
  });
});

describe('auth contract (real cloud)', () => {
  it('login posts OAuth2 form-urlencoded and reads token key', async () => {
    let captured: Record<string, unknown> = {};
    mockAxios.onPost('/auth/login').reply((config) => {
      captured = {
        body: config.data,
        contentType: config.headers?.['Content-Type'],
      };
      return [200, { code: 200, message: 'success', data: { token: 'tok-1', user: { id: 3, username: 'admin' } } }];
    });
    const resp = await authApi.login({ username: 'admin', password: 'pw' });
    expect(captured.contentType).toBe('application/x-www-form-urlencoded');
    expect(captured.body).toBe('username=admin&password=pw');
    expect(resp.data.token).toBe('tok-1');
    expect(resp.data.user.username).toBe('admin');
  });
});

describe('mappers (snake_case → camelCase)', () => {
  it('mapAlarm maps real cloud alarm fields', () => {
    const a = mapAlarm({
      id: 2983,
      device_id: 1,
      station_id: 15,
      station_name: '济南光伏电站',
      device_name: '充电桩#1',
      alarm_type: 'high_temperature',
      level: 'fatal',
      content: 'Charger temperature high: 52.2°C',
      status: 'active',
      created_at: '2026-07-28T20:00:53+08:00',
      handled_at: null,
    });
    expect(a.id).toBe(2983);
    expect(a.stationId).toBe(15);
    expect(a.stationName).toBe('济南光伏电站');
    expect(a.level).toBe('critical'); // fatal → critical
    expect(a.status).toBe('unhandled'); // active → unhandled
    expect(a.title).toBe('温度过高');
    expect(a.description).toBe('Charger temperature high: 52.2°C');
    expect(a.handledAt).toBeUndefined();
  });

  it('mapAlarm status mapping acknowledged/ignored', () => {
    expect(mapAlarm({ status: 'acknowledged' }).status).toBe('processing');
    expect(mapAlarm({ status: 'ignored' }).status).toBe('resolved');
    expect(mapAlarm({ status: 'resolved' }).status).toBe('resolved');
    expect(mapAlarm({ level: 'warning' }).level).toBe('warning');
  });

  it('mapWorkOrder maps WO- string id + level/status', () => {
    const w = mapWorkOrder({
      id: 'WO-20260711174343-f74b',
      fault_desc: '设备健康度告警: TL-TR-100KVA-017 健康度 78.1%',
      type: 'repair',
      level: 'P0',
      status: 'processing',
      station_id: 13,
      device_id: 17,
      assignee_id: null,
      creator_id: null,
      create_time: '2026-07-11T09:43:43+08:00',
      finish_time: null,
      solution: null,
    });
    expect(w.id).toBe('WO-20260711174343-f74b');
    expect(typeof w.id).toBe('string');
    expect(w.title).toContain('设备健康度告警');
    expect(w.priority).toBe('urgent'); // P0 → urgent
    expect(w.status).toBe('in_progress'); // processing → in_progress
    expect(w.solution).toBeUndefined();
    expect(w.createdAt).toBe('2026-07-11T09:43:43+08:00');
  });

  it('mapWorkOrder accepted/pending_verify/verified status mapping', () => {
    expect(mapWorkOrder({ status: 'accepted' }).status).toBe('in_progress');
    expect(mapWorkOrder({ status: 'pending_verify' }).status).toBe('completed');
    expect(mapWorkOrder({ status: 'verified' }).status).toBe('completed');
    expect(mapWorkOrder({ level: 'P1' }).priority).toBe('high');
    expect(mapWorkOrder({ level: 'P2' }).priority).toBe('normal');
    expect(mapWorkOrder({ level: 'warning' }).priority).toBe('low');
  });

  it('mapStation maps lat/lon + status normal→online', () => {
    const s = mapStation({
      id: 16,
      name: '济南光伏电站',
      code: 'ST2026016',
      address: '济南市高新区',
      lat: 36.6681,
      lon: 116.9972,
      status: 'normal',
      total_devices: 7,
      health_score: 0.91,
      total_power: 1750.0,
      created_at: '2026-06-23T03:20:01+08:00',
    });
    expect(s.latitude).toBe(36.6681);
    expect(s.longitude).toBe(116.9972);
    expect(s.status).toBe('online');
    expect(s.deviceCount).toBe(7);
    expect(s.healthScore).toBe(0.91);
  });

  it('mapPagination normalizes page_size → pageSize', () => {
    const p = mapPagination(
      { items: [{ id: 1, status: 'active' }], total: 2952, page: 1, page_size: 50 },
      mapAlarm
    );
    expect(p.total).toBe(2952);
    expect(p.pageSize).toBe(50);
    expect(p.items).toHaveLength(1);
    expect(p.items[0].status).toBe('unhandled');
  });
});

describe('alarmApi contract', () => {
  it('getList sends snake_case params + reverses UI status filter', async () => {
    let params: Record<string, unknown> = {};
    mockAxios.onGet('/alarms').reply((config) => {
      params = config.params ?? {};
      return [200, { code: 200, message: 'success', data: { items: [], total: 0, page: 1, page_size: 50 } }];
    });
    await alarmApi.getList({ stationId: 15, status: 'unhandled', page: 1, pageSize: 50 });
    expect(params.station_id).toBe(15);
    expect(params.status).toBe('active');
    expect(params.page_size).toBe(50);
    expect(params.pageSize).toBeUndefined();
  });

  it('handleAlarm hits PUT /alarms/{id}/ack (no /handle on real cloud)', async () => {
    let method = '';
    mockAxios.onPut('/alarms/2983/ack').reply((config) => {
      method = config.method ?? '';
      return [200, { code: 200, message: 'success', data: { id: 2983, status: 'acknowledged' } }];
    });
    const resp = await alarmApi.handleAlarm(2983);
    expect(method).toBe('put');
    expect(resp.data?.status).toBe('processing');
  });

  it('getDetail maps alarm fields + tolerates empty payload', async () => {
    mockAxios.onGet('/alarms/2983').reply(200, {
      code: 200, message: 'success',
      data: { id: 2983, alarm_type: 'high_temperature', level: 'fatal', status: 'active', content: 'x' },
    });
    const resp = await alarmApi.getDetail(2983);
    expect(resp.data.id).toBe(2983);
    expect(resp.data.level).toBe('critical');
    expect(resp.data.status).toBe('unhandled');

    mockAxios.onGet('/alarms/0').reply(200, { code: 200, message: 'success' });
    const empty = await alarmApi.getDetail(0);
    expect(empty.data).toBeDefined();
  });
});

describe('workOrderApi contract', () => {
  it('getList hits /work-orders with snake params + maps items', async () => {
    let params: Record<string, unknown> = {};
    mockAxios.onGet('/work-orders').reply((config) => {
      params = config.params ?? {};
      return [200, {
        code: 200, message: 'success',
        data: {
          items: [{ id: 'WO-20260711174343-f74b', fault_desc: 'x', level: 'P1', status: 'pending', create_time: 't' }],
          total: 113, page: 1, page_size: 20,
        },
      }];
    });
    const resp = await workOrderApi.getList({ status: 'in_progress', page: 1, pageSize: 20 });
    expect(params.status).toBe('processing');
    expect(params.page_size).toBe(20);
    expect(resp.data.items[0].id).toBe('WO-20260711174343-f74b');
    expect(resp.data.items[0].priority).toBe('high');
    expect(resp.data.total).toBe(113);
  });

  it('createWorkOrder posts snake_case body with level mapping', async () => {
    let body: Record<string, unknown> = {};
    mockAxios.onPost('/work-orders').reply((config) => {
      body = JSON.parse(config.data ?? '{}');
      return [200, { code: 200, message: 'success', data: { id: 'WO-1', fault_desc: 't', level: 'P0', status: 'pending' } }];
    });
    await workOrderApi.createWorkOrder({
      stationId: 13,
      title: '检修',
      description: '详情',
      type: 'repair',
      priority: 'urgent',
    });
    expect(body.fault_desc).toBe('检修');
    expect(body.level).toBe('P0');
    expect(body.station_id).toBe(13);
    expect(body.type).toBe('repair');
  });

  it('completeWorkOrder sends solution as query param', async () => {
    let params: Record<string, unknown> = {};
    mockAxios.onPost('/work-orders/WO-1/complete').reply((config) => {
      params = config.params ?? {};
      return [200, { code: 200, message: 'success', data: { id: 'WO-1', status: 'completed' } }];
    });
    await workOrderApi.completeWorkOrder('WO-1', '已更换模块');
    expect(params.solution).toBe('已更换模块');
  });

  it('getDetail accepts string id', async () => {
    mockAxios.onGet('/work-orders/WO-20260711174343-f74b').reply(200, {
      code: 200, message: 'success',
      data: { id: 'WO-20260711174343-f74b', status: 'pending', level: 'warning', fault_desc: 'd', create_time: 't' },
    });
    const resp = await workOrderApi.getDetail('WO-20260711174343-f74b');
    expect(resp.data.id).toBe('WO-20260711174343-f74b');
    expect(resp.data.status).toBe('pending');
  });
});

describe('stationApi contract', () => {
  it('getList maps snake pagination + station fields', async () => {
    let params: Record<string, unknown> = {};
    mockAxios.onGet('/stations').reply((config) => {
      params = config.params ?? {};
      return [200, {
        code: 200, message: 'success',
        data: {
          items: [{ id: 16, name: '济南光伏电站', lat: 36.6, lon: 116.9, status: 'normal', total_devices: 7 }],
          total: 20, page: 1, page_size: 100,
        },
      }];
    });
    const resp = await stationApi.getList({ page: 1, pageSize: 100 });
    expect(params.page_size).toBe(100);
    expect(resp.data.items[0].status).toBe('online');
    expect(resp.data.items[0].latitude).toBe(36.6);
    expect(resp.data.pageSize).toBe(100);
  });

  it('getList tolerates missing search param', async () => {
    let params: Record<string, unknown> = {};
    mockAxios.onGet('/stations').reply((config) => {
      params = config.params ?? {};
      return [200, { code: 200, message: 'success', data: { items: [], total: 0, page: 1, page_size: 20 } }];
    });
    await stationApi.getList();
    expect(params.search).toBeUndefined();
  });

  it('getDetail maps station fields + tolerates empty payload', async () => {
    mockAxios.onGet('/stations/16').reply(200, {
      code: 200, message: 'success',
      data: { id: 16, name: '济南光伏电站', lat: 36.6, lon: 116.9, status: 'normal', total_devices: 7 },
    });
    const resp = await stationApi.getDetail(16);
    expect(resp.data.id).toBe(16);
    expect(resp.data.status).toBe('online');
    expect(resp.data.latitude).toBe(36.6);

    mockAxios.onGet('/stations/99').reply(200, { code: 200, message: 'success' });
    const empty = await stationApi.getDetail(99);
    expect(empty.data).toBeDefined();
  });

  it('getDevices returns raw device list payload', async () => {
    mockAxios.onGet('/stations/16/devices').reply(200, {
      code: 200, message: 'success',
      data: [{ id: 1, code: 'CP-01' }, { id: 2, code: 'CP-02' }],
    });
    const resp = await stationApi.getDevices(16);
    expect(resp.data).toHaveLength(2);
    expect(resp.data[0].code).toBe('CP-01');
  });

  it('getAlarms maps snake pagination + alarm fields', async () => {
    let params: Record<string, unknown> = {};
    mockAxios.onGet('/stations/16/alarms').reply((config) => {
      params = config.params ?? {};
      return [200, {
        code: 200, message: 'success',
        data: {
          items: [{ id: 1, alarm_type: 'offline', level: 'info', status: 'active', content: 'c' }],
          total: 1, page: 2, page_size: 20,
        },
      }];
    });
    const resp = await stationApi.getAlarms(16, { page: 2, pageSize: 20 });
    expect(params.page).toBe(2);
    expect(params.page_size).toBe(20);
    expect(resp.data.items[0].status).toBe('unhandled');
    expect(resp.data.pageSize).toBe(20);
  });
});

describe('deviceApi contract', () => {
  it('getList passes params through untouched', async () => {
    let params: Record<string, unknown> = {};
    mockAxios.onGet('/devices').reply((config) => {
      params = config.params ?? {};
      return [200, { code: 200, message: 'success', data: { items: [], total: 0, page: 1, page_size: 10 } }];
    });
    const resp = await deviceApi.getList({ stationId: 16, page: 1, pageSize: 10, status: 'online', search: 'CP' });
    expect(params.stationId).toBe(16);
    expect(params.pageSize).toBe(10);
    expect(params.search).toBe('CP');
    expect(resp.code).toBe(200);
  });
});

describe('dashboardApi aggregation (real cloud has no dashboard endpoint)', () => {
  it('aggregates work-orders/stats + alarms + stations', async () => {
    mockAxios.onGet('/work-orders/stats').reply(200, {
      code: 200, message: 'success',
      data: { total: 113, status_distribution: { pending: 100, processing: 4, accepted: 2, completed: 7 } },
    });
    mockAxios.onGet('/alarms').reply((config) => {
      const p = config.params ?? {};
      const total = p.status === 'active' ? 2900 : 2952;
      return [200, { code: 200, message: 'success', data: { items: [], total, page: 1, page_size: 1 } }];
    });
    mockAxios.onGet('/stations').reply(200, {
      code: 200, message: 'success',
      data: {
        items: [
          { id: 1, name: 'a', status: 'normal', lat: 0, lon: 0 },
          { id: 2, name: 'b', status: 'offline', lat: 0, lon: 0 },
        ],
        total: 2, page: 1, page_size: 100,
      },
    });
    const resp = await dashboardApi.getStats();
    expect(resp.data.totalStations).toBe(2);
    expect(resp.data.onlineStations).toBe(1);
    expect(resp.data.offlineStations).toBe(1);
    expect(resp.data.totalAlarms).toBe(2952);
    expect(resp.data.unhandledAlarms).toBe(2900);
    expect(resp.data.pendingWorkOrders).toBe(100);
    expect(resp.data.totalWorkOrders).toBe(113);
  });

  it('getRecentAlarms maps items', async () => {
    mockAxios.onGet('/alarms').reply(200, {
      code: 200, message: 'success',
      data: { items: [{ id: 1, alarm_type: 'offline', level: 'info', status: 'active', content: 'c' }], total: 1, page: 1, page_size: 5 },
    });
    const resp = await dashboardApi.getRecentAlarms(5);
    expect(resp.data).toHaveLength(1);
    expect(resp.data[0].title).toBe('设备离线');
  });
});

describe('revenueApi contract (A3 /business domain)', () => {
  it('getSummary aggregates total + daily windows', async () => {
    mockAxios.onGet('/business/revenue/summary').reply(200, {
      code: 200, message: 'success',
      data: { order_count: 10, net_revenue: 1000.5, gross_amount: 1100, discount_total: 99.5 },
    });
    const daily = Array.from({ length: 30 }, (_, i) => ({
      date: `2026-07-${String(i + 1).padStart(2, '0')}`,
      order_count: 1,
      net_revenue: 10,
    }));
    mockAxios.onGet('/business/revenue/daily').reply(200, { code: 200, message: 'success', data: daily });
    const resp = await revenueApi.getSummary();
    expect(resp.data.total).toBe(1000.5);
    expect(resp.data.month).toBe(300);
    expect(resp.data.week).toBe(70);
    expect(resp.data.today).toBe(10);
  });

  it('getRecords maps daily → RevenueRecord (month → 30 days)', async () => {
    let params: Record<string, unknown> = {};
    mockAxios.onGet('/business/revenue/daily').reply((config) => {
      params = config.params ?? {};
      return [200, { code: 200, message: 'success', data: [{ date: '2026-07-28', order_count: 3, net_revenue: 25.5 }] }];
    });
    const resp = await revenueApi.getRecords({ type: 'month' });
    expect(params.days).toBe(30);
    expect(resp.data[0]).toEqual({ date: '2026-07-28', amount: 25.5, orderCount: 3 });
    await revenueApi.getRecords({ type: 'day' });
    expect(params.days).toBe(7);
  });
});
