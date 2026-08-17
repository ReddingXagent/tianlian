/**
 * api ext75 — coverage: mapper fallback branch push (batch 2)
 * Targets uncovered binary-expr branches in:
 *   deviceApi.getHealthHistory (lines 530-540)
 *   deviceApi.getConfig (lines 545+)
 *   roleApi.getList (lines 1139-1147)
 *   roleApi.getById (lines 1155-1163)
 *   roleApi.getTree (lines 1240-1250)
 *   reportApi.getRevenueTrend (lines 1318-1330)
 *   userApi.getDetail (lines 1340-1360)
 *   workOrderRecordApi.getRecords (lines 896-908)
 */
import {
  deviceApi,
  roleApi,
  energyApi,
  userApi,
  workOrderRecordApi,
} from '../api';
import axios from 'axios';

jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn(),
  setItemAsync: jest.fn(),
  deleteItemAsync: jest.fn(),
}));

jest.mock('axios', () => {
  const mockInstance = {
    get: jest.fn(),
    post: jest.fn(),
    put: jest.fn(),
    delete: jest.fn(),
    patch: jest.fn(),
    interceptors: {
      request: { use: jest.fn() },
      response: { use: jest.fn() },
    },
  };
  return {
    create: jest.fn(() => mockInstance),
    __mockInstance: mockInstance,
  };
});

// F1205: any收窄 — mock工厂返回结构已知, 用具体Mock接口替代any
const mockAxios = (axios as unknown as { __mockInstance: { get: jest.Mock; post: jest.Mock; put: jest.Mock; delete: jest.Mock; patch: jest.Mock } }).__mockInstance;

describe('ext75 — mapper fallback branch coverage batch 2', () => {

  beforeEach(() => {
    jest.clearAllMocks();
  });

  // deviceApi.getHealthHistory — empty-item fields → fallback
  it('getHealthHistory: empty-item → fallback values', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: [{}] },
    });
    const res = await deviceApi.getHealthHistory(1);
    expect(res.data[0]).toEqual({
      deviceId: 1,
      healthScore: 0,
      healthStatus: '',
      healthStatusDisplay: '',
      dimensionScores: {},
      checkedAt: '',
    });
  });

  // deviceApi.getHealthHistory — null data → empty array
  it('getHealthHistory: null data → empty array', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: null },
    });
    const res = await deviceApi.getHealthHistory(1);
    expect(res.data).toEqual([]);
  });

  // roleApi.getList — empty-item fields → fallback
  it('roleApi.getList: empty-item → fallback values', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: { items: [{}] } },
    });
    const res = await roleApi.getList();
    expect(res.data[0]).toEqual({
      id: 0,
      name: '',
      displayName: '',
      description: '',
      isSystem: false,
      permissions: [],
    });
  });

  // roleApi.getList — null data.items → empty array
  it('roleApi.getList: null data → empty array', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: null },
    });
    const res = await roleApi.getList();
    expect(res.data).toEqual([]);
  });

  // roleApi.getById — empty fields → fallback
  it('roleApi.getById: empty fields → fallback values', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: {} },
    });
    const res = await roleApi.getById(1);
    expect(res.data).toEqual({
      id: 0,
      name: '',
      displayName: '',
      description: '',
      isSystem: false,
      permissions: [],
    });
  });

  // roleApi.getById — null data → fallback
  it('roleApi.getById: null data → fallback values', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: null },
    });
    const res = await roleApi.getById(1);
    expect(res.data).toEqual({
      id: 0,
      name: '',
      displayName: '',
      description: '',
      isSystem: false,
      permissions: [],
    });
  });

  // roleApi.getTree — empty-item fields → fallback
  it('roleApi.getTree: empty-item → fallback values', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: { tree: [{}] } },
    });
    const res = await roleApi.getTree();
    expect(res.data[0]).toEqual({
      key: '',
      title: '',
      resource: '',
      name: undefined,
      action: undefined,
      label: undefined,
      isLeaf: false,
      children: undefined,
    });
  });

  // energyApi.getTrend — empty-item → fallback
  it('energyApi.getTrend: empty-item → fallback values', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: { trend: [{}] } },
    });
    const res = await energyApi.getTrend();
    expect(res.data[0]).toEqual({
      date: '',
      pvGeneration: 0,
      chargingAmount: 0,
      dischargeAmount: 0,
      pvRevenue: 0,
      chargingRevenue: 0,
      dischargeRevenue: 0,
      totalRevenue: 0,
    });
  });

  // energyApi.getTrend — null trend → empty
  it('energyApi.getTrend: null trend → empty array', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: null },
    });
    const res = await energyApi.getTrend();
    expect(res.data).toEqual([]);
  });

  // userApi.getDetail — empty fields → fallback
  it('userApi.getDetail: empty fields → fallback values', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: {} },
    });
    const res = await userApi.getDetail(1);
    expect(res.data).toEqual({
      id: 0,
      username: '',
      realName: '',
      phone: null,
      role: '',
      level: '',
      teamId: null,
      teamName: null,
      status: '',
      lastLogin: '',
      createdAt: '',
      updatedAt: '',
    });
  });

  // userApi.getDetail — null data → fallback
  it('userApi.getDetail: null data → fallback values', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: null },
    });
    const res = await userApi.getDetail(1);
    expect(res.data).toEqual({
      id: 0,
      username: '',
      realName: '',
      phone: null,
      role: '',
      level: '',
      teamId: null,
      teamName: null,
      status: '',
      lastLogin: '',
      createdAt: '',
      updatedAt: '',
    });
  });

  // workOrderRecordApi.getRecords — empty-item → fallback values
  it('workOrderRecordApi.getRecords: empty-item → fallback values', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: { items: [{}] } },
    });
    const res = await workOrderRecordApi.getRecords('WO-001');
    expect(res.data[0]).toEqual({
      id: 0,
      orderId: 'WO-001',
      action: 'executing',
      operatorId: 0,
      operatorName: '系统',
      note: '',
      createdAt: '',
    });
  });

  // workOrderRecordApi.getRecords — item with fields → mapped
  it('workOrderRecordApi.getRecords: item with raw fields → mapped', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: {
        code: 200, message: 'ok',
        data: { items: [{ id: 42, description: 'test note', created_at: '2024-01-01' }] },
      },
    });
    const res = await workOrderRecordApi.getRecords('WO-001');
    expect(res.data[0]).toEqual({
      id: 42,
      orderId: 'WO-001',
      action: 'executing',
      operatorId: 0,
      operatorName: '系统',
      note: 'test note',
      createdAt: '2024-01-01',
    });
  });

  // workOrderRecordApi.getRecords — null data → empty
  it('workOrderRecordApi.getRecords: null data → empty array', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: null },
    });
    const res = await workOrderRecordApi.getRecords('WO-001');
    expect(res.data).toEqual([]);
  });
});
