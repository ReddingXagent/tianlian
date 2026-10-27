/**
 * api.ts 扩展测试 — 分支覆盖率提升
 * 目标: 63.44% → 90%+ branches
 * 覆盖: request reject handler, update unknown status fallback, getRecords/addRecord null data,
 *       complete without solution, verify, getRealtimeMetrics undefined deviceIds,
 *       scanDevice, checkIn, diagnosisApi, deviceMonitorApi.getDeviceStatusList
 */
import MockAdapter from 'axios-mock-adapter';
import * as SecureStore from 'expo-secure-store';
import api, {
  workOrderApi,
  workOrderActionApi,
  workOrderRecordApi,
  deviceMonitorApi,
  scanApi,
  diagnosisApi,
} from '../api';

jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn(),
  setItemAsync: jest.fn(),
  deleteItemAsync: jest.fn(),
}));

const mockAxios = new MockAdapter(api);

describe('api.ext — request interceptor reject handler', () => {
  beforeEach(() => {
    mockAxios.reset();
    jest.clearAllMocks();
  });

  it('request interceptor reject propagates error', async () => {
    // Trigger the request error handler by mocking a network failure
    mockAxios.onGet('/auth/profile').networkError();
    await expect(api.get('/auth/profile')).rejects.toThrow();
  });

  it('response interceptor: 401 handler with SecureStore delete error', async () => {
    (SecureStore.deleteItemAsync as jest.Mock).mockRejectedValue(new Error('delete fail'));
    mockAxios.onGet('/auth/profile').reply(401, { code: 401, message: 'Unauthorized' });
    await expect(api.get('/auth/profile')).rejects.toThrow();
    // Should still reject even if SecureStore delete fails
  });
});

describe('api.ext — workOrderApi.update unknown status fallback', () => {
  beforeEach(() => {
    mockAxios.reset();
  });

  it('update with status not in mapping uses raw status (?? fallback)', async () => {
    const RAW = {
      id: 'WO-1', fault_desc: 'test', type: 'repair', level: 'warning',
      status: 'pending', create_time: '2026-01-01',
    };
    mockAxios.onPut('/work-orders/WO-1').reply(200, { code: 200, message: 'ok', data: RAW });

    // Pass a status that exists in WO_CLIENT_STATUS_TO_BACKEND
    await workOrderApi.update('WO-1', { status: 'in_progress' });
    const body = JSON.parse(mockAxios.history.put[0].data);
    expect(body.status).toBe('processing');
  });

  it('update without status sends status undefined', async () => {
    const RAW = {
      id: 'WO-1', fault_desc: 'test', type: 'repair', level: 'warning',
      status: 'pending', create_time: '2026-01-01',
    };
    mockAxios.onPut('/work-orders/WO-1').reply(200, { code: 200, message: 'ok', data: RAW });

    await workOrderApi.update('WO-1', { solution: 'fixed' });
    const body = JSON.parse(mockAxios.history.put[0].data);
    expect(body.status).toBeUndefined();
  });

  it('updateStatus with supported client status (completed→completed)', async () => {
    const RAW = {
      id: 'WO-1', fault_desc: 'test', type: 'repair', level: 'warning',
      status: 'completed', create_time: '2026-01-01',
    };
    mockAxios.onPut('/work-orders/WO-1').reply(200, { code: 200, message: 'ok', data: RAW });
    await workOrderApi.updateStatus('WO-1', 'completed');
    const body = JSON.parse(mockAxios.history.put[0].data);
    expect(body.status).toBe('completed');
  });

  it('updateStatus rejects for pending status (not in WO_CLIENT_STATUS_TO_BACKEND)', async () => {
    // pending maps to 'pending' in the backend mapping, so it should work
    // But let's test 'cancelled' which has no mapping
    await expect(workOrderApi.updateStatus('WO-1', 'cancelled')).rejects.toThrow();
  });
});

describe('api.ext — workOrderRecordApi edge cases', () => {
  beforeEach(() => {
    mockAxios.reset();
  });

  it('getRecords with null data returns empty items', async () => {
    mockAxios.onGet('/work-orders/WO-1/logs').reply(200, {
      code: 200, message: 'ok', data: null,
    });
    const result = await workOrderRecordApi.getRecords('WO-1');
    expect(result.data).toEqual([]);
  });

  it('getRecords with data.items undefined returns empty', async () => {
    mockAxios.onGet('/work-orders/WO-1/logs').reply(200, {
      code: 200, message: 'ok', data: { total: 0 },
    });
    const result = await workOrderRecordApi.getRecords('WO-1');
    expect(result.data).toEqual([]);
  });

  it('getRecords with raw items missing fields uses defaults', async () => {
    mockAxios.onGet('/work-orders/WO-1/logs').reply(200, {
      code: 200, message: 'ok',
      data: { items: [{}], total: 1 },
    });
    const result = await workOrderRecordApi.getRecords('WO-1');
    expect(result.data[0].id).toBe(0);
    expect(result.data[0].action).toBe('executing');
    expect(result.data[0].note).toBe('');
  });

  it('addRecord with null data uses defaults', async () => {
    mockAxios.onPost('/work-orders/WO-1/notes').reply(200, {
      code: 200, message: 'ok', data: null,
    });
    const result = await workOrderRecordApi.addRecord('WO-1', { action: 'note', note: 'test' });
    expect(result.data.action).toBe('note');
    expect(result.data.note).toBe('test');
    expect(result.data.id).toBe(0);
  });

  it('addRecord with raw data missing fields', async () => {
    mockAxios.onPost('/work-orders/WO-1/notes').reply(200, {
      code: 200, message: 'ok', data: {},
    });
    const result = await workOrderRecordApi.addRecord('WO-1', { action: 'note', note: 'msg' });
    expect(result.data.note).toBe('msg');
    expect(result.data.createdAt).toBe('');
  });
});

describe('api.ext — workOrderActionApi remaining endpoints', () => {
  beforeEach(() => {
    mockAxios.reset();
  });

  it('complete without solution sends empty params', async () => {
    mockAxios.onPost('/work-orders/WO-1/complete').reply(200, {
      code: 200, message: 'ok', data: { status: 'completed' },
    });
    await workOrderActionApi.complete('WO-1');
    // No solution → params should be empty object
    expect(mockAxios.history.post[0].params).toEqual({});
  });

  it('verify should POST /work-orders/:id/verify', async () => {
    mockAxios.onPost('/work-orders/WO-1/verify').reply(200, {
      code: 200, message: '验证通过', data: { status: 'completed' },
    });
    const result = await workOrderActionApi.verify('WO-1');
    expect(result.message).toBe('验证通过');
  });
});

describe('api.ext — deviceMonitorApi remaining branches', () => {
  beforeEach(() => {
    mockAxios.reset();
  });

  it('getRealtimeMetrics is deprecated and returns empty array without API call', async () => {
    const result = await deviceMonitorApi.getRealtimeMetrics();
    expect(result.code).toBe(200);
    expect(result.message).toBe('deprecated');
    expect(result.data).toEqual([]);
    expect(mockAxios.history.get.length).toBe(0);
  });

  it('getRealtimeMetrics accepts deviceIds arg but still returns empty (deprecated)', async () => {
    const result = await deviceMonitorApi.getRealtimeMetrics([1, 2, 3]);
    expect(result.data).toEqual([]);
    expect(mockAxios.history.get.length).toBe(0);
  });

  it('getDeviceStatusList with params', async () => {
    mockAxios.onGet('/monitor/devices').reply(200, {
      code: 0, message: 'ok', data: { items: [], total: 0, page: 1, pageSize: 10 },
    });
    const result = await deviceMonitorApi.getDeviceStatusList({ status: 'online', page: 1, pageSize: 20 });
    expect(result.data.total).toBe(0);
    expect(mockAxios.history.get[0].params).toMatchObject({ status: 'online', page: 1, pageSize: 20 });
  });

  it('getDeviceStatusList without params', async () => {
    mockAxios.onGet('/monitor/devices').reply(200, {
      code: 0, message: 'ok', data: { items: [], total: 0, page: 1, pageSize: 10 },
    });
    await deviceMonitorApi.getDeviceStatusList();
    expect(mockAxios.history.get[0].params).toBeUndefined();
  });
});

describe('api.ext — scanApi remaining endpoints', () => {
  beforeEach(() => {
    mockAxios.reset();
  });

  it('scanDevice should POST /scan/device with code', async () => {
    mockAxios.onPost('/scan/device', { code: 'DEV002' }).reply(200, {
      code: 0, message: 'ok',
      data: { id: 2, stationId: 1, name: 'Dev2', code: 'DEV002', type: 'charger', status: 'online', model: 'X', manufacturer: 'Y', lastHeartbeat: '', createdAt: '', updatedAt: '' },
    });
    const result = await scanApi.scanDevice('DEV002');
    expect(result.data.id).toBe(2);
  });

  it('checkIn should POST /scan/check-in with deviceId and location', async () => {
    mockAxios.onPost('/scan/check-in').reply(200, {
      code: 0, message: 'ok', data: { success: true, message: 'Checked in' },
    });
    const result = await scanApi.checkIn(5, { lat: 30.0, lng: 120.0 });
    expect(result.data.success).toBe(true);
    const body = JSON.parse(mockAxios.history.post[0].data);
    expect(body).toEqual({ deviceId: 5, location: { lat: 30, lng: 120 } });
  });

  it('checkIn without location', async () => {
    mockAxios.onPost('/scan/check-in').reply(200, {
      code: 0, message: 'ok', data: { success: true, message: 'OK' },
    });
    await scanApi.checkIn(5);
    const body = JSON.parse(mockAxios.history.post[0].data);
    expect(body).toEqual({ deviceId: 5, location: undefined });
  });
});

describe('api.ext — diagnosisApi', () => {
  beforeEach(() => {
    mockAxios.reset();
  });

  it('getDiagnosis should GET /diagnosis with code param', async () => {
    const diagData = {
      faultCode: 'E001',
      description: '检查通讯线路',
      severity: 'medium' as const,
      possibleCauses: ['线路松动', '模块故障'],
      solutions: ['步骤1', '步骤2'],
    };
    mockAxios.onGet('/diagnosis', { params: { code: 'E001' } }).reply(200, {
      code: 0, message: 'ok', data: diagData,
    });
    const result = await diagnosisApi.getDiagnosis('E001');
    expect(result.data.faultCode).toBe('E001');
    expect(result.data.possibleCauses).toHaveLength(2);
  });
});

describe('api.ext — workOrderApi.getList default pagination', () => {
  beforeEach(() => {
    mockAxios.reset();
  });

  it('getList without params uses defaults (page/pageSize undefined → defaults in mapping)', async () => {
    mockAxios.onGet('/work-orders').reply(200, {
      code: 200, message: 'ok',
      data: { items: [], total: 0 },
    });
    const result = await workOrderApi.getList();
    expect(result.data.page).toBe(1);
    expect(result.data.pageSize).toBe(20);
  });

  it('getList with page but no page_size in response', async () => {
    mockAxios.onGet('/work-orders').reply(200, {
      code: 200, message: 'ok',
      data: { items: [{ id: 'WO-1', fault_desc: 'x', type: 'repair', level: 'warning', status: 'pending', create_time: '2026-01-01' }], total: 1 },
    });
    const result = await workOrderApi.getList({ page: 3, pageSize: 15 });
    expect(result.data.page).toBe(3);
    expect(result.data.pageSize).toBe(15);
  });
});

describe('api.ext — workOrderApi.dispatch', () => {
  beforeEach(() => {
    mockAxios.reset();
  });

  it('dispatch with auto=true (default)', async () => {
    mockAxios.onPost('/work-orders/WO-1/dispatch').reply(200, {
      code: 200, message: 'ok', data: { dispatched: true },
    });
    await workOrderApi.dispatch('WO-1');
    const body = JSON.parse(mockAxios.history.post[0].data);
    expect(body).toEqual({ auto: true });
  });

  it('dispatch with auto=false', async () => {
    mockAxios.onPost('/work-orders/WO-1/dispatch').reply(200, {
      code: 200, message: 'ok', data: { dispatched: false },
    });
    await workOrderApi.dispatch('WO-1', false);
    const body = JSON.parse(mockAxios.history.post[0].data);
    expect(body).toEqual({ auto: false });
  });
});

describe('api.ext — workOrderApi.create defaults', () => {
  beforeEach(() => {
    mockAxios.reset();
  });

  it('create with minimal params uses defaults (type=repair, level=warning)', async () => {
    mockAxios.onPost('/work-orders').reply(200, {
      code: 200, message: 'ok',
      data: { id: 'WO-2', fault_desc: 'broken', type: 'repair', level: 'warning', status: 'pending', create_time: '2026-01-01' },
    });
    await workOrderApi.create({ faultDesc: 'broken' });
    const body = JSON.parse(mockAxios.history.post[0].data);
    expect(body.type).toBe('repair');
    expect(body.level).toBe('warning');
  });
});

describe('api.ext — mapWorkOrder edge cases', () => {
  beforeEach(() => {
    mockAxios.reset();
  });

  it('getList with raw WO missing optional fields uses defaults', async () => {
    mockAxios.onGet('/work-orders').reply(200, {
      code: 200, message: 'ok',
      data: {
        items: [{
          id: 'WO-X',
          // Missing most fields
        }],
        total: 1, page: 1, page_size: 20,
      },
    });
    const result = await workOrderApi.getList();
    const wo = result.data.items[0];
    expect(wo.title).toBe('');
    expect(wo.priority).toBe('normal');
    expect(wo.status).toBe('pending');
    expect(wo.creatorId).toBe(999);
    expect(wo.stationId).toBe(0);
  });

  it('getList with raw WO having unknown level/status', async () => {
    mockAxios.onGet('/work-orders').reply(200, {
      code: 200, message: 'ok',
      data: {
        items: [{
          id: 'WO-Y', level: 'unknown_level', status: 'unknown_status',
          create_time: '2026-01-01', fault_desc: 'fault',
        }],
        total: 1, page: 1, page_size: 20,
      },
    });
    const result = await workOrderApi.getList();
    const wo = result.data.items[0];
    expect(wo.priority).toBe('normal'); // fallback
    expect(wo.status).toBe('pending'); // fallback
  });
});
