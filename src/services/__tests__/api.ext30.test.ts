import { gatewayApi, tenantListApi } from '../api';

// Mock axios
jest.mock('axios', () => {
  const mockAxios: Record<string, any> = {
    create: jest.fn(() => mockAxios),
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
  return mockAxios;
});

// Mock SecureStore
jest.mock('expo-secure-store', () => ({
  getItem: jest.fn().mockResolvedValue('mock-token'),
  setItem: jest.fn(),
  deleteItem: jest.fn(),
}));

import axios from 'axios';
const mockedAxios = axios as jest.Mocked<typeof axios>;

describe('gatewayApi.getList', () => {
  beforeEach(() => jest.clearAllMocks());

  it('maps snake_case fields to camelCase', async () => {
    (mockedAxios.get as jest.Mock).mockResolvedValue({
      data: {
        code: 200,
        message: 'success',
        data: {
          items: [
            {
              id: 1,
              sn: 'MK-GW-001',
              name: '猴王测试网关',
              model: 'v3',
              manufacturer: 'TL',
              station_id: 5,
              status: 'online',
              firmware_version: '1.0.0',
              last_online: '2026-08-01T00:00:00',
              ip_address: '192.168.1.1',
              mac_address: 'AA:BB:CC:DD:EE:FF',
              location: '北京',
              health_score: 95.5,
              created_at: '2026-07-24T10:00:00',
              updated_at: '2026-07-24T10:00:00',
              notes: 'test note',
            },
          ],
          total: 1,
          page: 1,
          page_size: 20,
        },
        timestamp: 0,
      },
    });

    const res = await gatewayApi.getList();
    expect(res.data.items).toHaveLength(1);
    const gw = res.data.items[0];
    expect(gw.sn).toBe('MK-GW-001');
    expect(gw.stationId).toBe(5);
    expect(gw.firmwareVersion).toBe('1.0.0');
    expect(gw.ipAddress).toBe('192.168.1.1');
    expect(gw.macAddress).toBe('AA:BB:CC:DD:EE:FF');
    expect(gw.healthScore).toBe(95.5);
    expect(gw.createdAt).toBe('2026-07-24T10:00:00');
  });

  it('handles null fields with defaults', async () => {
    (mockedAxios.get as jest.Mock).mockResolvedValue({
      data: {
        code: 200,
        message: 'success',
        data: {
          items: [
            { id: 2, sn: 'GW-002', name: 'GW2', status: 'offline' },
          ],
          total: 1,
          page: 1,
          page_size: 20,
        },
        timestamp: 0,
      },
    });

    const res = await gatewayApi.getList();
    const gw = res.data.items[0];
    expect(gw.model).toBeNull();
    expect(gw.manufacturer).toBeNull();
    expect(gw.stationId).toBeNull();
    expect(gw.firmwareVersion).toBeNull();
    expect(gw.ipAddress).toBeNull();
    expect(gw.healthScore).toBe(0);
  });

  it('handles empty list', async () => {
    (mockedAxios.get as jest.Mock).mockResolvedValue({
      data: {
        code: 200,
        message: 'success',
        data: { items: [], total: 0, page: 1, page_size: 20 },
        timestamp: 0,
      },
    });

    const res = await gatewayApi.getList();
    expect(res.data.items).toHaveLength(0);
    expect(res.data.total).toBe(0);
  });

  it('calls correct endpoint', async () => {
    (mockedAxios.get as jest.Mock).mockResolvedValue({
      data: { code: 200, message: 'success', data: { items: [], total: 0, page: 1, page_size: 20 }, timestamp: 0 },
    });

    await gatewayApi.getList();
    expect(mockedAxios.get).toHaveBeenCalledWith('/gateways');
  });
});

describe('gatewayApi.getById', () => {
  beforeEach(() => jest.clearAllMocks());

  it('returns single gateway with camelCase mapping', async () => {
    (mockedAxios.get as jest.Mock).mockResolvedValue({
      data: {
        code: 200,
        message: 'success',
        data: {
          id: 1,
          sn: 'MK-GW-001',
          name: '猴王测试网关',
          model: null,
          manufacturer: null,
          station_id: null,
          status: 'online',
          firmware_version: null,
          last_online: null,
          ip_address: null,
          mac_address: null,
          location: null,
          health_score: 100.0,
          created_at: '2026-07-24T10:44:26',
          updated_at: '2026-07-24T10:44:26',
          notes: null,
        },
        timestamp: 0,
      },
    });

    const res = await gatewayApi.getById(1);
    expect(res.data.id).toBe(1);
    expect(res.data.sn).toBe('MK-GW-001');
    expect(res.data.name).toBe('猴王测试网关');
    expect(res.data.healthScore).toBe(100.0);
  });

  it('calls correct endpoint with id', async () => {
    (mockedAxios.get as jest.Mock).mockResolvedValue({
      data: { code: 200, message: 'success', data: {}, timestamp: 0 },
    });

    await gatewayApi.getById(42);
    expect(mockedAxios.get).toHaveBeenCalledWith('/gateways/42');
  });
});

describe('tenantListApi.getList', () => {
  beforeEach(() => jest.clearAllMocks());

  it('returns empty list for no tenants', async () => {
    (mockedAxios.get as jest.Mock).mockResolvedValue({
      data: {
        code: 200,
        message: 'success',
        data: { items: [], total: 0, page: 1, page_size: 20 },
        timestamp: 0,
      },
    });

    const res = await tenantListApi.getList();
    expect(res.data.items).toHaveLength(0);
    expect(res.data.total).toBe(0);
  });

  it('maps tenant fields correctly', async () => {
    (mockedAxios.get as jest.Mock).mockResolvedValue({
      data: {
        code: 200,
        message: 'success',
        data: {
          items: [
            {
              id: 1,
              name: '默认租户',
              code: 'default',
              status: 'active',
              created_at: '2026-01-01T00:00:00',
              updated_at: '2026-01-01T00:00:00',
            },
          ],
          total: 1,
          page: 1,
          page_size: 20,
        },
        timestamp: 0,
      },
    });

    const res = await tenantListApi.getList();
    const t = res.data.items[0];
    expect(t.name).toBe('默认租户');
    expect(t.code).toBe('default');
    expect(t.status).toBe('active');
    expect(t.createdAt).toBe('2026-01-01T00:00:00');
  });

  it('handles missing fields with defaults', async () => {
    (mockedAxios.get as jest.Mock).mockResolvedValue({
      data: {
        code: 200,
        message: 'success',
        data: {
          items: [{ id: 3 }],
          total: 1,
          page: 1,
          page_size: 20,
        },
        timestamp: 0,
      },
    });

    const res = await tenantListApi.getList();
    const t = res.data.items[0];
    expect(t.name).toBe('');
    expect(t.code).toBe('');
    expect(t.status).toBe('active');
  });

  it('calls correct endpoint', async () => {
    (mockedAxios.get as jest.Mock).mockResolvedValue({
      data: { code: 200, message: 'success', data: { items: [], total: 0, page: 1, page_size: 20 }, timestamp: 0 },
    });

    await tenantListApi.getList();
    expect(mockedAxios.get).toHaveBeenCalledWith('/tenants');
  });
});
