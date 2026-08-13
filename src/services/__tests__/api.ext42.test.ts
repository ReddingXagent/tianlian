import { gatewayApi } from '../api';

// Mock expo-secure-store
jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn(),
  setItemAsync: jest.fn(),
  deleteItemAsync: jest.fn(),
}));

// Mock axios
jest.mock('axios', () => {
  const mockAxios: Record<string, any> = {
    create: jest.fn(() => mockAxios),
    get: jest.fn(),
    post: jest.fn(),
    put: jest.fn(),
    delete: jest.fn(),
    interceptors: {
      request: { use: jest.fn() },
      response: { use: jest.fn() },
    },
    defaults: { headers: { common: {} } },
  };
  return mockAxios;
});

import axios from 'axios';
const mockAxios = axios as jest.Mocked<typeof axios>;

describe('gatewayApi.getStatus (ext42 — GET /gateways/status)', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('maps snake_case to camelCase correctly', async () => {
    mockAxios.get.mockResolvedValue({
      data: {
        code: 200,
        message: 'success',
        data: {
          online_count: 3,
          offline_count: 1,
          maintenance_count: 2,
          fault_count: 1,
          total: 7,
        },
        timestamp: 1786600911,
      },
    });

    const res = await gatewayApi.getStatus();
    expect(res.data.onlineCount).toBe(3);
    expect(res.data.offlineCount).toBe(1);
    expect(res.data.maintenanceCount).toBe(2);
    expect(res.data.faultCount).toBe(1);
    expect(res.data.total).toBe(7);
  });

  it('handles null data with defaults', async () => {
    mockAxios.get.mockResolvedValue({
      data: {
        code: 200,
        message: 'success',
        data: null,
        timestamp: 1786600911,
      },
    });

    const res = await gatewayApi.getStatus();
    expect(res.data.onlineCount).toBe(0);
    expect(res.data.offlineCount).toBe(0);
    expect(res.data.maintenanceCount).toBe(0);
    expect(res.data.faultCount).toBe(0);
    expect(res.data.total).toBe(0);
  });

  it('handles missing fields with defaults', async () => {
    mockAxios.get.mockResolvedValue({
      data: {
        code: 200,
        message: 'success',
        data: { total: 5 },
        timestamp: 1786600911,
      },
    });

    const res = await gatewayApi.getStatus();
    expect(res.data.onlineCount).toBe(0);
    expect(res.data.offlineCount).toBe(0);
    expect(res.data.maintenanceCount).toBe(0);
    expect(res.data.faultCount).toBe(0);
    expect(res.data.total).toBe(5);
  });

  it('calls correct endpoint', async () => {
    mockAxios.get.mockResolvedValue({
      data: {
        code: 200,
        message: 'success',
        data: { online_count: 1, total: 1 },
        timestamp: 1786600911,
      },
    });

    await gatewayApi.getStatus();
    expect(mockAxios.get).toHaveBeenCalledWith('/gateways/status');
  });

  it('preserves top-level response fields', async () => {
    mockAxios.get.mockResolvedValue({
      data: {
        code: 200,
        message: 'success',
        data: {
          online_count: 1,
          offline_count: 0,
          maintenance_count: 0,
          fault_count: 0,
          total: 1,
        },
        timestamp: 1786600911,
      },
    });

    const res = await gatewayApi.getStatus();
    expect(res.code).toBe(200);
    expect(res.message).toBe('success');
  });
});
